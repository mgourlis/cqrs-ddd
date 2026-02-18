"""Tests for EventSourcedLoader, EventSourcedRepository, UpcastingEventReader, snapshots."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_advanced_core.adapters.memory import InMemorySnapshotStore
from cqrs_ddd_advanced_core.event_sourcing import (
    DefaultEventApplicator,
    EventSourcedLoader,
    EventSourcedRepository,
    UpcastingEventReader,
)
from cqrs_ddd_advanced_core.snapshots import (
    EveryNEventsStrategy,
    SnapshotStrategyRegistry,
)
from cqrs_ddd_advanced_core.upcasting.registry import (
    EventUpcaster,
    UpcasterRegistry,
)
from cqrs_ddd_core.adapters.memory.event_store import InMemoryEventStore
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.ports.event_store import StoredEvent

# --- Test doubles ---


class OrderCreated(DomainEvent):
    order_id: str = ""
    amount: float = 0.0
    currency: str = "EUR"


class OrderPaid(DomainEvent):
    order_id: str = ""
    transaction_id: str = ""


class Order(AggregateRoot[str]):
    """Minimal event-sourced aggregate."""

    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"

    def apply_OrderCreated(self, event: OrderCreated) -> None:  # noqa: N802
        self.__dict__.update(
            status="created",
            amount=event.amount,
            currency=getattr(event, "currency", "EUR"),
        )

    def apply_OrderPaid(self, event: OrderPaid) -> None:  # noqa: N802
        object.__setattr__(self, "status", "paid")


class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    target_version = 2

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        event_data.setdefault("currency", "USD")
        return event_data


# --- EventSourcedLoader ---


@pytest.mark.asyncio
class TestEventSourcedLoader:
    """Test EventSourcedLoader with in-memory stores."""

    @pytest.fixture
    def event_store(self) -> InMemoryEventStore:
        return InMemoryEventStore()

    @pytest.fixture
    def event_registry(self) -> EventTypeRegistry:
        reg = EventTypeRegistry()
        reg.register("OrderCreated", OrderCreated)
        reg.register("OrderPaid", OrderPaid)
        return reg

    @pytest.fixture
    def snapshot_store(self) -> InMemorySnapshotStore:
        return InMemorySnapshotStore()

    async def test_load_returns_none_when_no_events_no_snapshot(
        self, event_store: InMemoryEventStore, event_registry: EventTypeRegistry
    ) -> None:
        """load() returns None when aggregate has no events and no snapshot."""
        loader = EventSourcedLoader(
            Order,
            event_store,
            event_registry,
        )
        result = await loader.load("order-1")
        assert result is None

    async def test_load_reconstitutes_from_events_only(
        self, event_store: InMemoryEventStore, event_registry: EventTypeRegistry
    ) -> None:
        """load() reconstitutes aggregate from events when no snapshot."""
        await event_store.append_batch(
            [
                StoredEvent(
                    event_type="OrderCreated",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=1,
                    schema_version=1,
                    payload={
                        "event_id": "e1",
                        "aggregate_id": "order-1",
                        "aggregate_type": "Order",
                        "order_id": "order-1",
                        "amount": 100.0,
                        "currency": "EUR",
                    },
                ),
                StoredEvent(
                    event_type="OrderPaid",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=2,
                    schema_version=1,
                    payload={
                        "event_id": "e2",
                        "aggregate_id": "order-1",
                        "aggregate_type": "Order",
                        "order_id": "order-1",
                        "transaction_id": "tx-1",
                    },
                ),
            ]
        )
        loader = EventSourcedLoader(Order, event_store, event_registry)
        agg = await loader.load("order-1")
        assert agg is not None
        assert agg.id == "order-1"
        assert agg.status == "paid"
        assert agg.amount == 100.0
        assert agg.version == 2

    async def test_load_uses_snapshot_then_replays_events(
        self,
        event_store: InMemoryEventStore,
        event_registry: EventTypeRegistry,
        snapshot_store: InMemorySnapshotStore,
    ) -> None:
        """load() restores from snapshot and replays only events after snapshot version."""
        await snapshot_store.save_snapshot(
            "Order",
            "order-1",
            {"id": "order-1", "status": "created", "amount": 50.0, "currency": "EUR"},
            version=1,
        )
        await event_store.append_batch(
            [
                StoredEvent(
                    event_type="OrderPaid",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=2,
                    schema_version=1,
                    payload={
                        "event_id": "e2",
                        "aggregate_id": "order-1",
                        "aggregate_type": "Order",
                        "order_id": "order-1",
                        "transaction_id": "tx-1",
                    },
                ),
            ]
        )
        loader = EventSourcedLoader(
            Order,
            event_store,
            event_registry,
            snapshot_store=snapshot_store,
        )
        agg = await loader.load("order-1")
        assert agg is not None
        assert agg.id == "order-1"
        assert agg.status == "paid"
        assert agg.amount == 50.0
        assert agg.version == 2

    async def test_load_applies_upcasting(
        self, event_store: InMemoryEventStore, event_registry: EventTypeRegistry
    ) -> None:
        """load() upcasts event payloads when upcaster_registry is provided."""
        await event_store.append_batch(
            [
                StoredEvent(
                    event_type="OrderCreated",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=1,
                    schema_version=1,
                    payload={
                        "event_id": "e1",
                        "aggregate_id": "order-1",
                        "aggregate_type": "Order",
                        "order_id": "order-1",
                        "amount": 100.0,
                    },
                ),
            ]
        )
        upcast = UpcasterRegistry()
        upcast.register(OrderCreatedV1ToV2())
        loader = EventSourcedLoader(
            Order,
            event_store,
            event_registry,
            upcaster_registry=upcast,
        )
        agg = await loader.load("order-1")
        assert agg is not None
        assert agg.currency == "USD"

    async def test_maybe_snapshot_saves_when_strategy_says_yes(
        self,
        event_store: InMemoryEventStore,
        event_registry: EventTypeRegistry,
        snapshot_store: InMemorySnapshotStore,
    ) -> None:
        """maybe_snapshot() saves snapshot when strategy returns True."""
        strategy_reg = SnapshotStrategyRegistry()
        strategy_reg.register("Order", EveryNEventsStrategy(n=1))
        loader = EventSourcedLoader(
            Order,
            event_store,
            event_registry,
            snapshot_store=snapshot_store,
            snapshot_strategy_registry=strategy_reg,
        )
        order = Order(id="order-1", status="created", amount=100.0)
        object.__setattr__(order, "_version", 1)
        await loader.maybe_snapshot(order)
        snap = await snapshot_store.get_latest_snapshot("Order", "order-1")
        assert snap is not None
        assert snap["version"] == 1
        assert snap["snapshot_data"]["amount"] == 100.0


class TestDefaultEventApplicator:
    """Test DefaultEventApplicator dispatch (sync, no asyncio)."""

    def test_apply_dispatches_to_apply_event_type(self) -> None:
        applicator = DefaultEventApplicator[Order]()
        order = Order(id="o1", status="pending")
        event = OrderCreated(aggregate_id="o1", order_id="o1", amount=99.0)
        result = applicator.apply(order, event)
        assert result is order
        assert order.amount == 99.0
        assert order.status == "created"

    def test_apply_raises_when_no_handler(self) -> None:
        class OtherEvent(DomainEvent):
            pass

        applicator = DefaultEventApplicator[Order]()
        order = Order(id="o1")
        event = OtherEvent(aggregate_id="o1")
        with pytest.raises(AttributeError, match="no apply_OtherEvent or apply_event"):
            applicator.apply(order, event)


@pytest.mark.asyncio
class TestUpcastingEventReader:
    """Test UpcastingEventReader."""

    async def test_get_events_upcasts_payloads(self) -> None:
        store = InMemoryEventStore()
        await store.append_batch(
            [
                StoredEvent(
                    event_type="OrderCreated",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=1,
                    schema_version=1,
                    payload={"order_id": "order-1", "amount": 50.0},
                ),
            ]
        )
        upcast = UpcasterRegistry()
        upcast.register(OrderCreatedV1ToV2())
        reader = UpcastingEventReader(store, upcast)
        events = await reader.get_events("order-1")
        assert len(events) == 1
        assert events[0].payload.get("currency") == "USD"
        assert events[0].schema_version == 2

    async def test_get_events_passthrough_when_no_upcasters(self) -> None:
        store = InMemoryEventStore()
        await store.append(
            StoredEvent(
                event_type="OrderCreated",
                aggregate_id="order-1",
                aggregate_type="Order",
                version=1,
                schema_version=1,
                payload={"order_id": "order-1", "amount": 50.0},
            )
        )
        reader = UpcastingEventReader(store, UpcasterRegistry())
        events = await reader.get_events("order-1")
        assert len(events) == 1
        assert events[0].payload == {"order_id": "order-1", "amount": 50.0}


@pytest.mark.asyncio
class TestInMemorySnapshotStore:
    """Test InMemorySnapshotStore implements ISnapshotStore."""

    async def test_save_and_get_latest(self) -> None:
        store = InMemorySnapshotStore()
        await store.save_snapshot("Order", "o1", {"id": "o1", "amount": 10}, version=1)
        snap = await store.get_latest_snapshot("Order", "o1")
        assert snap is not None
        assert snap["snapshot_data"]["amount"] == 10
        assert snap["version"] == 1
        assert "created_at" in snap

    async def test_get_latest_nonexistent_returns_none(self) -> None:
        store = InMemorySnapshotStore()
        assert await store.get_latest_snapshot("Order", "o1") is None

    async def test_delete_snapshot(self) -> None:
        store = InMemorySnapshotStore()
        await store.save_snapshot("Order", "o1", {}, version=1)
        await store.delete_snapshot("Order", "o1")
        assert await store.get_latest_snapshot("Order", "o1") is None


@pytest.mark.asyncio
class TestEventSourcedRepository:
    """Test EventSourcedRepository retrieve and persist."""

    async def test_retrieve_loads_via_loader(self) -> None:
        event_store = InMemoryEventStore()
        await event_store.append_batch(
            [
                StoredEvent(
                    event_type="OrderCreated",
                    aggregate_id="order-1",
                    aggregate_type="Order",
                    version=1,
                    schema_version=1,
                    payload={
                        "event_id": "e1",
                        "aggregate_id": "order-1",
                        "aggregate_type": "Order",
                        "order_id": "order-1",
                        "amount": 100.0,
                        "currency": "EUR",
                    },
                ),
            ]
        )
        event_registry = EventTypeRegistry()
        event_registry.register("OrderCreated", OrderCreated)
        event_registry.register("OrderPaid", OrderPaid)

        repo = EventSourcedRepository(
            Order,
            get_event_store=lambda _: event_store,
            event_registry=event_registry,
        )
        # Pass a minimal UoW-like object (repository only needs get_event_store(None))
        class FakeUoW:
            pass

        uow = FakeUoW()
        result = await repo.retrieve(["order-1"], uow)
        assert len(result) == 1
        assert result[0].id == "order-1"
        assert result[0].amount == 100.0
