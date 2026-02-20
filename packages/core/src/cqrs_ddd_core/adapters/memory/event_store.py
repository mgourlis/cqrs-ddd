"""InMemoryEventStore — list-backed fake for unit tests."""

from __future__ import annotations

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
        self._events.append(stored_event)

    async def _append_batch_internal(self, events: list[StoredEvent]) -> None:
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
