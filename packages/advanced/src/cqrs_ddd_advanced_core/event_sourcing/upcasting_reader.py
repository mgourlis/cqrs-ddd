"""UpcastingEventReader — wraps IEventStore reads with transparent upcasting."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

    from ..upcasting.registry import UpcasterRegistry


class UpcastingEventReader:
    """Wraps IEventStore reads with transparent upcasting of event payloads.

    Use for projections and catch-up reads so that stored events are
    returned in the current schema version.
    """

    def __init__(
        self,
        event_store: IEventStore,
        upcaster_registry: UpcasterRegistry,
    ) -> None:
        self._event_store = event_store
        self._upcaster_registry = upcaster_registry

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        """Load events for an aggregate and upcast their payloads in place."""
        registry = get_hook_registry()
        return cast(
            "list[StoredEvent]",
            await registry.execute_all(
                "upcast.apply.get_events",
                {
                    "aggregate.id": aggregate_id,
                    "after_version": after_version,
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._get_events_internal(
                    aggregate_id, after_version=after_version
                ),
            ),
        )

    async def _get_events_internal(
        self, aggregate_id: str, *, after_version: int = 0
    ) -> list[StoredEvent]:
        raw = await self._event_store.get_events(
            aggregate_id, after_version=after_version
        )
        return [self._upcast_one(e) for e in raw]

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        """Load all events for an aggregate and upcast their payloads."""
        registry = get_hook_registry()
        return cast(
            "list[StoredEvent]",
            await registry.execute_all(
                "upcast.apply.get_by_aggregate",
                {
                    "aggregate.id": aggregate_id,
                    "aggregate.type": aggregate_type,
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._get_by_aggregate_internal(
                    aggregate_id, aggregate_type=aggregate_type
                ),
            ),
        )

    async def _get_by_aggregate_internal(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        raw = await self._event_store.get_by_aggregate(
            aggregate_id, aggregate_type=aggregate_type
        )
        return [self._upcast_one(e) for e in raw]

    async def get_all(self) -> list[StoredEvent]:
        """Load all events and upcast their payloads."""
        raw = await self._event_store.get_all()
        return [self._upcast_one(e) for e in raw]

    def _upcast_one(self, stored: StoredEvent) -> StoredEvent:
        if not self._upcaster_registry.has_upcasters(stored.event_type):
            return stored
        schema_ver = getattr(stored, "schema_version", 1)
        payload, new_ver = self._upcaster_registry.upcast(
            stored.event_type, dict(stored.payload), schema_ver
        )
        return replace(
            stored,
            payload=payload,
            schema_version=new_ver,
        )
