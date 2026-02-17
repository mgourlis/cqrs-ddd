"""Domain Event base class with auto-registration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Base class for all Domain Events.

    Events are immutable and carry full tracing context.
    Event types must be explicitly registered with an ``EventTypeRegistry`` instance.

    Aggregate metadata fields (``aggregate_id`` and ``aggregate_type``) MUST be set
    by subclasses to enable proper event sourcing, undo/redo, and upcasting.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    aggregate_id: str | None = Field(
        default=None, description="ID of the aggregate instance this event belongs to"
    )
    aggregate_type: str | None = Field(
        default=None,
        description=(
            "Class name or type identifier of the aggregate (e.g., 'Order', 'User')"
        ),
    )
    metadata: dict[str, object] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None


def enrich_event_metadata(
    event: DomainEvent,
    *,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> DomainEvent:
    """Return a copy of *event* with tracing IDs injected.

    If the event already carries the requested ID the original value is kept.
    """
    updates: dict[str, str] = {}
    if correlation_id and not event.correlation_id:
        updates["correlation_id"] = correlation_id
    if causation_id and not event.causation_id:
        updates["causation_id"] = causation_id

    if not updates:
        return event

    return event.model_copy(update=updates)
