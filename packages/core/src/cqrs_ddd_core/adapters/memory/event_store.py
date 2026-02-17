"""InMemoryEventStore — list-backed fake for unit tests."""

from __future__ import annotations

from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent


class InMemoryEventStore(IEventStore):
    """In-memory implementation of ``IEventStore``.

    Stores events in a flat list with index-based queries.
    """

    def __init__(self) -> None:
        self._events: list[StoredEvent] = []

    async def append(self, stored_event: StoredEvent) -> None:
        self._events.append(stored_event)

    async def append_batch(self, events: list[StoredEvent]) -> None:
        self._events.extend(events)

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
