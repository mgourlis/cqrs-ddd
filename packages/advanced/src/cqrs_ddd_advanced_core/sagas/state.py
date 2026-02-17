"""Saga state model with 20+ fields for full lifecycle tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.mixins import AuditableMixin


class SagaStatus(str, Enum):
    """Possible lifecycle states for a saga instance."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"


class ReservationType(str, Enum):
    """Type of TCC reservation.

    * ``RESOURCE`` — reservation is held indefinitely until explicit
      confirm/cancel.  Suitable for inventory locks, seat holds, etc.
    * ``TIME_BASED`` — reservation auto-expires after a TTL.  Suitable
      for payment holds, temporary blocks, etc.
    """

    RESOURCE = "RESOURCE"
    TIME_BASED = "TIME_BASED"


class TCCPhase(str, Enum):
    """Phase of a single TCC step."""

    PENDING = "PENDING"
    TRYING = "TRYING"
    TRIED = "TRIED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TCCStepRecord(BaseModel):
    """Serialisable state of a single TCC step, stored in ``SagaState.tcc_steps``."""

    model_config = ConfigDict(frozen=True)

    name: str
    phase: TCCPhase = TCCPhase.PENDING
    reservation_type: ReservationType = ReservationType.RESOURCE
    try_command_type: str = ""
    try_command_module: str = ""
    try_command_data: dict[str, Any] = Field(default_factory=dict)
    confirm_command_type: str = ""
    confirm_command_module: str = ""
    confirm_command_data: dict[str, Any] = Field(default_factory=dict)
    cancel_command_type: str = ""
    cancel_command_module: str = ""
    cancel_command_data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    tried_at: datetime | None = None
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    timeout_at: datetime | None = None


class StepRecord(BaseModel):
    """Immutable record of a single saga step transition."""

    model_config = ConfigDict(frozen=True)

    step_name: str
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompensationRecord(BaseModel):
    """Serialised compensating command for LIFO execution on failure."""

    model_config = ConfigDict(frozen=True)

    command_type: str
    module_name: str
    data: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class SagaState(AuditableMixin, AggregateRoot[str]):
    """
    Full-featured saga state tracked for persistence and idempotency.

    Aggregate root with 20+ fields covering: identity, lifecycle, step history,
    idempotency, pending commands, TCC steps, compensation stack, suspension,
    timeouts, retries, audit timestamps, distributed tracing, and optimistic
    concurrency. Uses :class:`AuditableMixin` for ``created_at`` / ``updated_at``.
    """

    # ── Schema version for state migration ───────────────────────────
    state_version: int = 1

    # ── Identity ────────────────────────────────────────────────────
    saga_type: str = ""
    status: SagaStatus = SagaStatus.PENDING

    # ── Step Tracking ────────────────────────────────────────────────
    current_step: str = "init"
    step_history: list[StepRecord] = Field(default_factory=list)

    # ── TCC steps (first-class; was in metadata["tcc_steps"]) ───────
    tcc_steps: list[TCCStepRecord] = Field(default_factory=list)

    # ── Idempotency ─────────────────────────────────────────────────
    processed_event_ids: list[str] = Field(default_factory=list)
    _processed_ids_set: set[str] = PrivateAttr(default_factory=set)

    # ── Pending Commands ─────────────────────────────────────────────
    pending_commands: list[dict[str, Any]] = Field(default_factory=list)

    # ── Compensation ─────────────────────────────────────────────────
    compensation_stack: list[CompensationRecord] = Field(default_factory=list)
    failed_compensations: list[dict[str, Any]] = Field(default_factory=list)

    # ── Suspension / Human-in-the-Loop ──────────────────────────────
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    timeout_at: datetime | None = None

    # ── Retries ──────────────────────────────────────────────────────
    retry_count: int = 0
    max_retries: int = 3

    # ── Error Tracking ──────────────────────────────────────────────
    error: str | None = None

    # ── Completion timestamps (AuditableMixin has created_at/updated_at) ─
    completed_at: datetime | None = None
    failed_at: datetime | None = None

    # ── Distributed Tracing ──────────────────────────────────────────
    correlation_id: str | None = None

    # ── Arbitrary Context ────────────────────────────────────────────
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ── Helpers ──────────────────────────────────────────────────────

    def model_post_init(self, __context: object) -> None:
        """Sync _processed_ids_set and migrate legacy tcc_steps from metadata."""
        super().model_post_init(__context)
        self._processed_ids_set = set(self.processed_event_ids)
        # Migrate legacy tcc_steps from metadata to first-class field
        if not self.tcc_steps and self.metadata.get("tcc_steps"):
            raw = self.metadata["tcc_steps"]
            object.__setattr__(
                self,
                "tcc_steps",
                [
                    TCCStepRecord.model_validate(r) if isinstance(r, dict) else r
                    for r in raw
                ],
            )
            meta = dict(self.metadata)
            meta.pop("tcc_steps", None)
            object.__setattr__(self, "metadata", meta)

    def is_event_processed(self, event_id: str) -> bool:
        """Return *True* if the event has already been handled.

        Idempotency. O(1) lookup.
        """
        return event_id in self._processed_ids_set

    def mark_event_processed(self, event_id: str) -> None:
        """Record an event id to prevent duplicate processing."""
        if event_id not in self._processed_ids_set:
            self._processed_ids_set.add(event_id)
            self.processed_event_ids.append(event_id)

    def record_step(
        self,
        step_name: str,
        event_type: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a step record and update ``current_step``."""
        self.current_step = step_name
        self.step_history.append(
            StepRecord(
                step_name=step_name,
                event_type=event_type,
                metadata=metadata or {},
            )
        )
        self.touch()

    def touch(self) -> None:
        """Bump ``updated_at`` and version (extends AuditableMixin)."""
        super().touch()
        self.increment_version()

    @property
    def is_terminal(self) -> bool:
        """Return *True* if the saga has reached a final state."""
        return self.status in (
            SagaStatus.COMPLETED,
            SagaStatus.FAILED,
            SagaStatus.COMPENSATED,
        )
