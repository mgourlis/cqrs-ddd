"""Tests for the Consumers package."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_core.cqrs import BaseEventConsumer
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.ports.event_dispatcher import IEventDispatcher
from cqrs_ddd_core.ports.messaging import IMessageConsumer

# ============================================================================
# Test Events
# ============================================================================


class OrderCreated(DomainEvent):
    """Test event."""

    order_id: str
    amount: float = 100.0


class OrderShipped(DomainEvent):
    """Test event."""

    order_id: str


# ============================================================================
# Mock Implementations
# ============================================================================


class DummyMessageConsumer(IMessageConsumer):
    """In-memory mock broker consumer."""

    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, Any, str | None]] = []

    async def subscribe(
        self,
        topic: str,
        handler: Any,
        queue_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.subscriptions.append((topic, handler, queue_name))

    async def send_test_message(self, topic: str, payload: dict[str, Any]) -> None:
        """Simulate receiving a message from the broker."""
        for sub_topic, handler, _ in self.subscriptions:
            if sub_topic == topic:
                await handler(payload)


class DummyEventDispatcher(IEventDispatcher):
    """Mock event dispatcher that records dispatched events."""

    def __init__(self) -> None:
        self.priority_events: list[Any] = []
        self.background_events: list[Any] = []

    async def dispatch_priority(self, events: list[DomainEvent]) -> None:
        self.priority_events.extend(events)

    async def dispatch_background(self, events: list[DomainEvent]) -> None:
        self.background_events.extend(events)

    async def dispatch(self, events: list[DomainEvent]) -> None:
        await self.dispatch_priority(events)
        await self.dispatch_background(events)


# ============================================================================
# Tests: BaseEventConsumer
# ============================================================================


class TestBaseEventConsumer:
    """Test the BaseEventConsumer."""

    @pytest.mark.asyncio
    async def test_consumer_subscribes_to_topics(self) -> None:
        """Consumer should subscribe to configured topics."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events", "user-events"],
        )

        await consumer.start()

        assert len(broker.subscriptions) == 2
        topics = [sub[0] for sub in broker.subscriptions]
        assert "order-events" in topics
        assert "user-events" in topics

    @pytest.mark.asyncio
    async def test_consumer_hydrates_and_dispatches_event(self) -> None:
        """Consumer should hydrate payload and dispatch event."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()
        registry.register("OrderCreated", OrderCreated)

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        await consumer.start()

        # Simulate receiving a message
        payload = {
            "event_type": "OrderCreated",
            "order_id": "ord-123",
            "amount": 250.0,
            "event_id": "evt-456",
            "occurred_at": "2025-01-01T00:00:00Z",
            "version": 1,
            "metadata": {},
        }
        await broker.send_test_message("order-events", payload)

        # Verify event was dispatched
        assert len(dispatcher.background_events) == 1
        event = dispatcher.background_events[0]
        assert isinstance(event, OrderCreated)
        assert event.order_id == "ord-123"
        assert event.amount == 250.0

    @pytest.mark.asyncio
    async def test_consumer_warns_on_unregistered_event(self, caplog: Any) -> None:
        """Consumer should warn if event type is not registered."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()
        # OrderCreated is NOT registered

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        await consumer.start()

        payload = {
            "event_type": "OrderCreated",
            "order_id": "ord-123",
        }
        await broker.send_test_message("order-events", payload)

        assert "failed to hydrate" in caplog.text.lower()
        assert "OrderCreated" in caplog.text

    @pytest.mark.asyncio
    async def test_consumer_warns_on_missing_event_type(self, caplog: Any) -> None:
        """Consumer should warn if payload lacks 'event_type'."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        await consumer.start()

        payload = {"order_id": "ord-123"}  # Missing event_type
        await broker.send_test_message("order-events", payload)

        assert "event_type" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_consumer_warns_on_non_dict_payload(self, caplog: Any) -> None:
        """Consumer should warn if payload is not a dict."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        await consumer.start()

        # Send non-dict payload
        await broker.send_test_message("order-events", "not a dict")  # type: ignore

        assert "non-dict" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_consumer_respects_queue_name(self) -> None:
        """Consumer should pass queue_name to broker."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
            queue_name="my-queue",
        )

        await consumer.start()

        assert broker.subscriptions[0][2] == "my-queue"

    @pytest.mark.asyncio
    async def test_consumer_stop_changes_running_state(self) -> None:
        """Consumer should stop when stop() is called."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        assert not consumer._running
        await consumer.start()
        assert consumer._running
        await consumer.stop()
        assert not consumer._running

    @pytest.mark.asyncio
    async def test_consumer_multiple_events(self) -> None:
        """Consumer should handle multiple different events."""
        broker = DummyMessageConsumer()
        dispatcher = DummyEventDispatcher()
        registry = EventTypeRegistry()
        registry.register("OrderCreated", OrderCreated)
        registry.register("OrderShipped", OrderShipped)

        consumer = BaseEventConsumer(
            broker=broker,
            dispatcher=dispatcher,
            registry=registry,
            topics=["order-events"],
        )

        await consumer.start()

        # Send OrderCreated
        await broker.send_test_message(
            "order-events",
            {
                "event_type": "OrderCreated",
                "order_id": "ord-123",
                "event_id": "evt-1",
                "occurred_at": "2025-01-01T00:00:00Z",
                "version": 1,
                "metadata": {},
            },
        )

        # Send OrderShipped
        await broker.send_test_message(
            "order-events",
            {
                "event_type": "OrderShipped",
                "order_id": "ord-123",
                "event_id": "evt-2",
                "occurred_at": "2025-01-01T00:01:00Z",
                "version": 1,
                "metadata": {},
            },
        )

        assert len(dispatcher.background_events) == 2
        assert isinstance(dispatcher.background_events[0], OrderCreated)
        assert isinstance(dispatcher.background_events[1], OrderShipped)
