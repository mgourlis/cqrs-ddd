"""EventSourcedRepository — retrieval and persistence for event-sourced aggregates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeVar, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

from ..ports.persistence import IOperationPersistence, IRetrievalPersistence
from .loader import EventSourcedLoader

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..ports.snapshots import ISnapshotStore
    from ..snapshots.strategy_registry import SnapshotStrategyRegistry

T = TypeVar("T", bound=AggregateRoot[Any])
T_ID = TypeVar("T_ID", str, int, Any)


class EventSourcedRepository(
    IRetrievalPersistence[T, T_ID], IOperationPersistence[T, T_ID]
):
    """Repository for event-sourced aggregates.

    - **Retrieve:** loads via EventSourcedLoader (snapshot + events + upcasting).
    - **Persist:** appends the entity's events to the event store and optionally
      saves a snapshot if the strategy says so.

    Requires callables to resolve event store and snapshot store from the current
    UnitOfWork so that persistence uses the same transaction/session.
    """

    def __init__(
        self,
        aggregate_type: type[T],
        get_event_store: Callable[[UnitOfWork | None], IEventStore],
        event_registry: EventTypeRegistry,
        *,
        get_snapshot_store: Callable[[UnitOfWork | None], ISnapshotStore | None]
        | None = None,
        snapshot_strategy_registry: SnapshotStrategyRegistry | None = None,
        create_aggregate: Callable[[str], T] | None = None,
        upcaster_registry: Any = None,
        applicator: Any = None,
    ) -> None:
        self._aggregate_type = aggregate_type
        self._get_event_store = get_event_store
        self._get_snapshot_store = get_snapshot_store or (lambda _: None)
        self._event_registry = event_registry
        self._snapshot_strategy_registry = snapshot_strategy_registry
        self._create_aggregate = create_aggregate
        self._upcaster_registry = upcaster_registry
        self._applicator = applicator
        self._aggregate_type_name = aggregate_type.__name__

    def _loader(self, uow: UnitOfWork | None) -> EventSourcedLoader[T]:
        event_store = self._get_event_store(uow)
        snapshot_store = self._get_snapshot_store(uow)
        return EventSourcedLoader(
            self._aggregate_type,
            event_store,
            self._event_registry,
            snapshot_store=snapshot_store,
            upcaster_registry=self._upcaster_registry,
            snapshot_strategy_registry=self._snapshot_strategy_registry,
            applicator=self._applicator,
            create_aggregate=self._create_aggregate,
        )

    async def retrieve(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T]:
        """Load aggregates by ID from snapshot + event store (with upcasting)."""
        registry = get_hook_registry()
        return cast(
            "list[T]",
            await registry.execute_all(
                f"event_sourcing.load.{self._aggregate_type_name}",
                {
                    "aggregate.type": self._aggregate_type_name,
                    "aggregate.count": len(ids),
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._retrieve_internal(ids, uow),
            ),
        )

    async def _retrieve_internal(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T]:
        loader = self._loader(uow)
        result: list[T] = []
        for id_val in ids:
            agg = await loader.load(str(id_val))
            if agg is not None:
                result.append(agg)
        return result

    async def persist(
        self,
        entity: T,
        uow: UnitOfWork,
        events: list[Any] | None = None,
    ) -> T_ID:
        """Append the entity's events to the event store and maybe snapshot."""
        registry = get_hook_registry()
        events_to_persist = events if events is not None else entity.collect_events()
        return cast(
            "T_ID",
            await registry.execute_all(
                f"event_sourcing.persist.{self._aggregate_type_name}",
                {
                    "aggregate.type": self._aggregate_type_name,
                    "aggregate.id": str(getattr(entity, "id", "")),
                    "event_count": len(events_to_persist),
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._persist_internal(entity, uow, events_to_persist),
            ),
        )

    async def _persist_internal(
        self,
        entity: T,
        uow: UnitOfWork,
        events: list[Any],
    ) -> T_ID:
        event_store = self._get_event_store(uow)
        snapshot_store = self._get_snapshot_store(uow)
        base_version = getattr(entity, "version", 0) - len(events)

        stored: list[StoredEvent] = []
        for i, event in enumerate(events):
            stored.append(
                StoredEvent(
                    event_id=getattr(event, "event_id", ""),
                    event_type=type(event).__name__,
                    aggregate_id=str(getattr(event, "aggregate_id", "")),
                    aggregate_type=getattr(event, "aggregate_type", "")
                    or self._aggregate_type_name,
                    version=base_version + i + 1,
                    schema_version=getattr(event, "version", 1),
                    payload=event.model_dump(),
                    metadata=getattr(event, "metadata", {}),
                    occurred_at=getattr(event, "occurred_at", None)
                    or datetime.now(timezone.utc),
                    correlation_id=getattr(event, "correlation_id", None),
                    causation_id=getattr(event, "causation_id", None),
                )
            )
        await event_store.append_batch(stored)

        if snapshot_store and self._snapshot_strategy_registry:
            loader = self._loader(uow)
            await loader.maybe_snapshot(entity)

        return cast("T_ID", entity.id)
