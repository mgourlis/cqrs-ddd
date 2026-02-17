"""Tests for InMemoryEventStore."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.adapters.memory.event_store import InMemoryEventStore
from cqrs_ddd_core.domain.events import DomainEvent


class OrderCreated(DomainEvent):
    """Test event for event store tests."""

    order_id: str = ""
    amount: float = 0.0


class PaymentReceived(DomainEvent):
    """Another test event."""

    order_id: str = ""
    transaction_id: str = ""


@pytest.mark.asyncio
class TestInMemoryEventStore:
    """Test InMemoryEventStore storage and retrieval."""

    @pytest.fixture
    def store(self) -> InMemoryEventStore:
        """Create fresh event store for each test."""
        return InMemoryEventStore()

    async def test_append_single_event(self, store: InMemoryEventStore) -> None:
        """append() stores a single event."""
        event = OrderCreated(
            aggregate_id="order-123",
            order_id="order-123",
            amount=100.0,
        )

        await store.append(event)

        events = await store.get_events("order-123")
        assert len(events) == 1
        assert events[0].aggregate_id == "order-123"

    async def test_append_multiple_events(self, store: InMemoryEventStore) -> None:
        """append() stores multiple events for same aggregate."""
        event1 = OrderCreated(
            aggregate_id="order-123",
            order_id="order-123",
            amount=100.0,
        )
        event2 = PaymentReceived(
            aggregate_id="order-123",
            order_id="order-123",
            transaction_id="tx-456",
        )

        await store.append(event1)
        await store.append(event2)

        events = await store.get_events("order-123")
        assert len(events) == 2

    async def test_get_events_by_aggregate_id(self, store: InMemoryEventStore) -> None:
        """get_events filters by aggregate_id."""
        event1 = OrderCreated(aggregate_id="order-123", order_id="order-123")
        event2 = OrderCreated(aggregate_id="order-456", order_id="order-456")
        event3 = PaymentReceived(
            aggregate_id="order-123", order_id="order-123", transaction_id="tx-1"
        )

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        events = await store.get_events("order-123")

        assert len(events) == 2
        assert all(e.aggregate_id == "order-123" for e in events)

    async def test_get_events_with_version_filter(
        self, store: InMemoryEventStore
    ) -> None:
        """get_events filters by version when specified."""
        event1 = OrderCreated(aggregate_id="order-123", order_id="order-123", version=1)
        event2 = PaymentReceived(
            aggregate_id="order-123",
            order_id="order-123",
            transaction_id="tx-1",
            version=2,
        )
        event3 = PaymentReceived(
            aggregate_id="order-123",
            order_id="order-123",
            transaction_id="tx-2",
            version=3,
        )

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Get events after version 1 (using after_version parameter)
        events = await store.get_events("order-123", after_version=1)

        assert len(events) == 2
        assert events[0].version == 2
        assert events[1].version == 3

    async def test_get_events_nonexistent_aggregate(
        self, store: InMemoryEventStore
    ) -> None:
        """get_events returns empty list for nonexistent aggregate."""
        events = await store.get_events("nonexistent")

        assert events == []

    async def test_get_by_aggregate_all_events(self, store: InMemoryEventStore) -> None:
        """get_by_aggregate returns all events for aggregate."""
        event1 = OrderCreated(aggregate_id="order-123", order_id="order-123")
        event2 = PaymentReceived(
            aggregate_id="order-123", order_id="order-123", transaction_id="tx-1"
        )

        await store.append(event1)
        await store.append(event2)

        events = await store.get_by_aggregate("order-123")

        assert len(events) == 2

    async def test_get_by_aggregate_with_type_filter(
        self, store: InMemoryEventStore
    ) -> None:
        """get_by_aggregate filters by aggregate_type when specified."""
        # Create events with aggregate_type set during construction
        event1 = OrderCreated(
            aggregate_id="order-123", order_id="order-123", aggregate_type="Order"
        )
        event2 = PaymentReceived(
            aggregate_id="payment-456",
            order_id="order-123",
            transaction_id="tx-1",
            aggregate_type="Payment",
        )
        event3 = OrderCreated(
            aggregate_id="order-789", order_id="order-789", aggregate_type="Order"
        )

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        # Get all Order events for order-123
        events = await store.get_by_aggregate("order-123", aggregate_type="Order")

        assert len(events) == 1
        assert events[0].aggregate_id == "order-123"

    async def test_get_by_aggregate_nonexistent_type(
        self, store: InMemoryEventStore
    ) -> None:
        """get_by_aggregate returns empty list for nonexistent type."""
        event1 = OrderCreated(
            aggregate_id="order-123", order_id="order-123", aggregate_type="Order"
        )

        await store.append(event1)

        events = await store.get_by_aggregate("order-123", aggregate_type="Payment")

        assert events == []

    async def test_events_maintain_order(self, store: InMemoryEventStore) -> None:
        """Events are returned in the order they were appended."""
        for i in range(5):
            event = OrderCreated(
                aggregate_id="order-123",
                order_id="order-123",
                amount=float(i * 100),
                version=i + 1,
            )
            await store.append(event)

        events = await store.get_events("order-123")

        assert len(events) == 5
        for i, event in enumerate(events):
            assert event.amount == float(i * 100)
            assert event.version == i + 1

    async def test_multiple_aggregates_isolation(
        self, store: InMemoryEventStore
    ) -> None:
        """Events for different aggregates are isolated."""
        event1 = OrderCreated(aggregate_id="order-123", order_id="order-123")
        event2 = OrderCreated(aggregate_id="order-456", order_id="order-456")
        event3 = OrderCreated(aggregate_id="order-789", order_id="order-789")

        await store.append(event1)
        await store.append(event2)
        await store.append(event3)

        events_123 = await store.get_events("order-123")
        events_456 = await store.get_events("order-456")

        assert len(events_123) == 1
        assert len(events_456) == 1
        assert events_123[0].aggregate_id == "order-123"
        assert events_456[0].aggregate_id == "order-456"
