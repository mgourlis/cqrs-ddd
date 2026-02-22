"""Tests for InMemoryPublisher and InMemoryConsumer."""

from __future__ import annotations

import pytest

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.memory import InMemoryConsumer, InMemoryPublisher


@pytest.mark.asyncio
async def test_publish_get_published() -> None:
    pub = InMemoryPublisher()
    await pub.publish(
        "orders", MessageEnvelope(event_type="OrderCreated", payload={"id": "1"})
    )
    await pub.publish("orders", {"event_type": "OrderShipped", "order_id": "1"})
    published = pub.get_published()
    assert len(published) == 2
    assert published[0][0] == "orders"
    assert published[0][1].event_type == "OrderCreated"
    assert published[1][1]["event_type"] == "OrderShipped"


@pytest.mark.asyncio
async def test_assert_published() -> None:
    pub = InMemoryPublisher()
    await pub.publish("orders", MessageEnvelope(event_type="OrderCreated", payload={}))
    pub.assert_published("OrderCreated", count=1)
    pub.assert_published("OrderCreated", count=1, topic="orders")


@pytest.mark.asyncio
async def test_assert_published_fails_wrong_count() -> None:
    pub = InMemoryPublisher()
    await pub.publish("orders", MessageEnvelope(event_type="OrderCreated", payload={}))
    with pytest.raises(AssertionError):
        pub.assert_published("OrderCreated", count=2)
    with pytest.raises(AssertionError):
        pub.assert_published("Other", count=1)


@pytest.mark.asyncio
async def test_consumer_receives_on_publish() -> None:
    pub = InMemoryPublisher()
    consumer = InMemoryConsumer(pub.bus)
    received: list[object] = []

    async def handler(payload: object) -> None:
        received.append(payload)

    await consumer.subscribe("orders", handler)
    await pub.publish(
        "orders", MessageEnvelope(event_type="OrderCreated", payload={"id": "1"})
    )
    assert len(received) == 1
    assert received[0] == {"id": "1"}


@pytest.mark.asyncio
async def test_protocol_compliance() -> None:
    from cqrs_ddd_core.ports.messaging import IMessageConsumer, IMessagePublisher

    pub = InMemoryPublisher()
    consumer = InMemoryConsumer(pub.bus)
    assert isinstance(pub, IMessagePublisher)
    assert isinstance(consumer, IMessageConsumer)
