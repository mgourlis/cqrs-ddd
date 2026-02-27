"""IEventStore protocol + StoredEvent dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

from ..utils import default_dict_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(frozen=True)
class StoredEvent:
    """Persistent representation of a domain event.

    - ``version``: aggregate event sequence number (1st, 2nd, 3rd event...).
    - ``schema_version``: event payload schema version for upcasting (v1, v2, v3...).
    - ``position``: cursor-based position for efficient pagination.
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
    position: int | None = None


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

    async def get_events_after(
        self, position: int, limit: int = 1000
    ) -> list[StoredEvent]:
        """Return events after a given position for cursor-based pagination.

        Uses a numeric position column for efficient
        pagination without loading all events.
        This is the preferred method for projections
        to avoid memory exhaustion.

        Args:
            position: The last processed event position (exclusive).
            limit: Maximum number of events to return.

        Returns:
            List of stored events in position order, up to ``limit`` events.
        """
        ...

    def get_events_from_position(
        self,
        position: int,
        *,
        limit: int | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """Stream events starting from a specific position.

        Used by ProjectionWorker to resume after crash.

        Args:
            position: Starting position (exclusive).
            limit: Optional batch size limit per internal batch.

        Yields:
            StoredEvent objects with incrementing positions.
        """
        ...

    async def get_latest_position(self) -> int | None:
        """Get the highest event position in the store.

        Used by ProjectionWorker to resume after crash.

        Args:
            position: Starting position (exclusive).
            limit: Optional batch size limit per internal batch.

        Yields:
            StoredEvent objects with incrementing positions.
        """
        ...

    def get_all_streaming(
        self, batch_size: int = 1000
    ) -> AsyncIterator[list[StoredEvent]]:
        """Stream all events in batches for memory-efficient processing.

        Yields batches of events until all events are consumed. This is the
        preferred method for replay operations and large-scale projections.

        Args:
            batch_size: Number of events per batch.

        Yields:
            Lists of stored events in position order.
        """
        ...
