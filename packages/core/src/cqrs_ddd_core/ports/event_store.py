"""IEventStore protocol + StoredEvent dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import uuid4

from ..utils import default_dict_factory


@dataclass(frozen=True)
class StoredEvent:
    """Persistent representation of a domain event.

    - ``version``: aggregate event sequence number (1st, 2nd, 3rd event...).
    - ``schema_version``: event payload schema version for upcasting (v1, v2, v3...).
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    aggregate_id: str = ""
    aggregate_type: str = ""
    version: int = 0
    schema_version: int = 1
    payload: dict[str, object] = field(default_factory=default_dict_factory)
    metadata: dict[str, object] = field(default_factory=default_dict_factory)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    causation_id: str | None = None


@runtime_checkable
class IEventStore(Protocol):
    """Protocol for persisting domain events."""

    async def append(self, stored_event: StoredEvent) -> None:
        """Append a single stored event."""
        ...

    async def append_batch(self, events: list[StoredEvent]) -> None:
        """Append multiple stored events atomically."""
        ...

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        """Return events for an aggregate after *after_version*."""
        ...

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        """Return all events for an aggregate, optionally filtered by type."""
        ...

    async def get_all(self) -> list[StoredEvent]:
        """Return every stored event (for projections / catch-up)."""
        ...
