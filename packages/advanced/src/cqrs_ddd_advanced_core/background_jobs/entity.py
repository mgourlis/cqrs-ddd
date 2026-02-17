"""BaseBackgroundJob — aggregate root for background jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field

from cqrs_ddd_advanced_core.exceptions import JobStateError
from cqrs_ddd_core.domain.aggregate import AggregateRoot

from .events import (
    JobCancelled,
    JobCompleted,
    JobCreated,
    JobFailed,
    JobRetried,
    JobStarted,
)

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent


class BackgroundJobStatus(str, Enum):
    """Lifecycle states for a background job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BaseBackgroundJob(AggregateRoot[str]):
    """Aggregate root representing a background job.

    Status transitions::

        PENDING  → RUNNING  (start_processing)
        RUNNING  → COMPLETED (complete)
        RUNNING  → FAILED    (fail)
        PENDING  → CANCELLED (cancel)
        RUNNING  → CANCELLED (cancel)
        FAILED   → RUNNING   (retry)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: str = ""
    status: BackgroundJobStatus = BackgroundJobStatus.PENDING
    total_items: int = 0
    processed_items: int = 0
    result_data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    broker_message_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None

    # -- helpers ----------------------------------------------------------

    def _touch(self) -> None:
        """Bump updated_at."""
        self.updated_at = datetime.now(timezone.utc)

    def _emit(self, event: DomainEvent) -> None:
        """Emit event with aggregate context automatically populated."""
        update_data = {}
        if not event.aggregate_id:
            update_data["aggregate_id"] = self.id
        if not event.aggregate_type:
            update_data["aggregate_type"] = self.__class__.__name__

        if update_data:
            event = event.model_copy(update=update_data)

        self.add_event(event)

    # -- factory ----------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        job_type: str,
        total_items: int = 0,
        max_retries: int = 3,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **extra: Any,
    ) -> BaseBackgroundJob:
        """Create a new job and emit ``JobCreated``."""
        job = cls(
            job_type=job_type,
            total_items=total_items,
            max_retries=max_retries,
            correlation_id=correlation_id,
            metadata=metadata or {},
            **extra,
        )
        job._emit(
            JobCreated(
                job_type=job.job_type,
                total_items=job.total_items,
                correlation_id=correlation_id,
            )
        )
        return job

    # -- transitions ------------------------------------------------------

    def start_processing(self) -> None:
        """PENDING → RUNNING."""
        if self.status != BackgroundJobStatus.PENDING:
            raise JobStateError(f"Cannot start job in {self.status.value} state")
        self.status = BackgroundJobStatus.RUNNING
        self._touch()
        self._emit(JobStarted(correlation_id=self.correlation_id))

    def update_progress(self, processed_items: int) -> None:
        """Update processed-items counter while RUNNING."""
        if self.status != BackgroundJobStatus.RUNNING:
            raise JobStateError(f"Cannot update progress in {self.status.value} state")
        self.processed_items = processed_items
        self._touch()

    def complete(self, result_data: dict[str, Any] | None = None) -> None:
        """RUNNING → COMPLETED."""
        if self.status != BackgroundJobStatus.RUNNING:
            raise JobStateError(f"Cannot complete job in {self.status.value} state")
        self.status = BackgroundJobStatus.COMPLETED
        if result_data:
            self.result_data.update(result_data)
        self._touch()
        self._emit(JobCompleted(correlation_id=self.correlation_id))

    def fail(self, error_message: str) -> None:
        """RUNNING → FAILED."""
        if self.status not in (
            BackgroundJobStatus.RUNNING,
            BackgroundJobStatus.PENDING,
        ):
            raise JobStateError(f"Cannot fail job in {self.status.value} state")
        self.status = BackgroundJobStatus.FAILED
        self.error_message = error_message
        self._touch()
        self._emit(
            JobFailed(
                error_message=error_message,
                correlation_id=self.correlation_id,
            )
        )

    def retry(self) -> None:
        """FAILED → RUNNING (if retries remain)."""
        if self.status != BackgroundJobStatus.FAILED:
            raise JobStateError(f"Cannot retry job in {self.status.value} state")
        if self.retry_count >= self.max_retries:
            raise JobStateError(f"Max retries ({self.max_retries}) exceeded")
        self.retry_count += 1
        self.status = BackgroundJobStatus.RUNNING
        self.error_message = None
        self._touch()
        self._emit(
            JobRetried(
                retry_count=self.retry_count,
                correlation_id=self.correlation_id,
            )
        )

    def cancel(self) -> None:
        """PENDING | RUNNING → CANCELLED."""
        if self.status in (
            BackgroundJobStatus.COMPLETED,
            BackgroundJobStatus.CANCELLED,
        ):
            raise JobStateError(f"Cannot cancel job in {self.status.value} state")
        self.status = BackgroundJobStatus.CANCELLED
        self.error_message = "Cancelled by user"
        self._touch()
        self._emit(JobCancelled(correlation_id=self.correlation_id))
