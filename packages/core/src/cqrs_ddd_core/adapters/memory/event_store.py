"""InMemoryEventStore — list-backed fake for unit tests."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent


class InMemoryEventStore(IEventStore):
    """In-memory implementation of ``IEventStore``.

    Stores events in a flat list with index-based queries.
    """

    def __init__(self) -> None:
        self._events: list[StoredEvent] = []

    async def append(self, stored_event: StoredEvent) -> None:
        registry = get_hook_registry()
        event_type = getattr(stored_event, "event_type", type(stored_event).__name__)
        aggregate_type = getattr(stored_event, "aggregate_type", None)
        aggregate_id = getattr(stored_event, "aggregate_id", None)
        event_id = getattr(stored_event, "event_id", None)
        correlation_id = getattr(stored_event, "correlation_id", None)
        await registry.execute_all(
            f"event_store.append.{aggregate_type or 'unknown'}",
            {
                "aggregate.type": aggregate_type,
                "aggregate.id": aggregate_id,
                "event.id": event_id,
                "event.type": event_type,
                "event_count": 1,
                "correlation_id": correlation_id or get_correlation_id(),
            },
            lambda: self._append_internal(stored_event),
        )

    async def append_batch(self, events: list[StoredEvent]) -> None:
        if not events:
            return
        registry = get_hook_registry()
        first = events[0]
        first_aggregate_type = getattr(first, "aggregate_type", None)
        first_aggregate_id = getattr(first, "aggregate_id", None)
        first_correlation_id = getattr(first, "correlation_id", None)
        await registry.execute_all(
            f"event_store.append.{first_aggregate_type or 'unknown'}",
            {
                "aggregate.type": first_aggregate_type,
                "aggregate.id": first_aggregate_id,
                "event_count": len(events),
                "correlation_id": first_correlation_id or get_correlation_id(),
            },
            lambda: self._append_batch_internal(events),
        )

    async def _append_internal(self, stored_event: StoredEvent) -> None:
        position = len(self._events)
        if isinstance(stored_event, StoredEvent):
            existing = getattr(stored_event, "position", None)
            event_with_position = dataclasses.replace(
                stored_event,
                position=position if existing is None else existing,
            )
        else:
            event_with_position = stored_event
        self._events.append(event_with_position)

    async def _append_batch_internal(self, events: list[StoredEvent]) -> None:
        start = len(self._events)
        for i, e in enumerate(events):
            if isinstance(e, StoredEvent):
                pos = start + i if getattr(e, "position", None) is None else e.position
                self._events.append(dataclasses.replace(e, position=pos))
            else:
                self._events.append(e)

    async def get_events_after(
        self, position: int, limit: int = 1000
    ) -> list[StoredEvent]:
        """Return events after a given position (exclusive), up to limit."""
        out: list[StoredEvent] = []
        for i, e in enumerate(self._events):
            p = getattr(e, "position", None)
            if p is None:
                p = i
            if p > position:
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    async def get_events_from_position(
        self,
        position: int,
        *,
        limit: int | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """Stream events starting from position (exclusive)."""
        batch_size = limit if limit is not None else 1000
        current = position
        while True:
            batch = await self.get_events_after(current, batch_size)
            for e in batch:
                yield e
            if len(batch) < batch_size:
                break
            last = batch[-1]
            p = getattr(last, "position", None)
            current = current + len(batch) if p is None else p

    async def get_latest_position(self) -> int | None:
        """Return the highest position in the store, or None if empty."""
        if not self._events:
            return None
        positions = [
            getattr(e, "position", None)
            for e in self._events
            if getattr(e, "position", None) is not None
        ]
        if not positions:
            return len(self._events) - 1
        return max(positions)

    def get_all_streaming(
        self, batch_size: int = 1000
    ) -> AsyncIterator[list[StoredEvent]]:
        """Stream all events in batches."""

        async def _stream() -> AsyncIterator[list[StoredEvent]]:
            pos = -1
            while True:
                batch = await self.get_events_after(pos, batch_size)
                if not batch:
                    break
                yield batch
                last = batch[-1]
                p = getattr(last, "position", None)
                pos = pos + len(batch) if p is None else p

        return _stream()

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        return [
            e
            for e in self._events
            if e.aggregate_id == aggregate_id and e.version > after_version
        ]

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        results = [e for e in self._events if e.aggregate_id == aggregate_id]
        if aggregate_type is not None:
            results = [e for e in results if e.aggregate_type == aggregate_type]
        return results

    async def get_all(self) -> list[StoredEvent]:
        return list(self._events)

    # ── Test helpers ─────────────────────────────────────────────

    def clear(self) -> None:
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)
