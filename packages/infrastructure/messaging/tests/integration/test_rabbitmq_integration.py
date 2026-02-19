"""Integration tests for RabbitMQ adapter (require aio-pika and testcontainers)."""

from __future__ import annotations

import pytest

pytest.importorskip("aio_pika")
pytest.importorskip("testcontainers")
pytest.importorskip("pika")  # required by testcontainers.rabbitmq

from testcontainers.rabbitmq import RabbitMqContainer

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.rabbitmq import (
    RabbitMQConnectionManager,
    RabbitMQConsumer,
    RabbitMQPublisher,
)
from cqrs_ddd_messaging.serialization import EnvelopeSerializer


def _rabbitmq_url_from_params(params: object) -> str:
    """Build amqp URL from pika connection params (e.g. from get_connection_params())."""
    # get_connection_params() returns a pika.ConnectionParameters-like object
    host = getattr(params, "host", "localhost")
    port = getattr(params, "port", 5672)
    creds = getattr(params, "credentials", None)
    if creds is not None:
        user = getattr(creds, "username", "guest")
        pwd = getattr(creds, "password", "guest")
    else:
        user, pwd = "guest", "guest"
    return f"amqp://{user}:{pwd}@{host}:{port}/"


@pytest.fixture(scope="module")
def rabbitmq_url() -> str:
    with RabbitMqContainer("rabbitmq:3-management") as rabbit:
        yield _rabbitmq_url_from_params(rabbit.get_connection_params())


@pytest.mark.asyncio
async def test_rabbitmq_publish_consume(rabbitmq_url: str) -> None:
    conn = RabbitMQConnectionManager(url=rabbitmq_url)
    await conn.connect()
    try:
        serializer = EnvelopeSerializer()
        pub = RabbitMQPublisher(
            connection=conn, exchange_name="test.ex", serializer=serializer
        )
        consumer = RabbitMQConsumer(
            connection=conn,
            exchange_name="test.ex",
            serializer=serializer,
        )
        received: list[dict] = []

        async def handler(payload: object) -> None:
            received.append(payload if isinstance(payload, dict) else {})

        await consumer.subscribe("orders", handler)
        await pub.publish(
            "orders",
            MessageEnvelope(event_type="OrderCreated", payload={"order_id": "1"}),
        )
        # Consumer is async callback-based; give it a moment
        import asyncio

        await asyncio.sleep(0.5)
        assert len(received) == 1
        assert received[0].get("order_id") == "1"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_rabbitmq_health_check(rabbitmq_url: str) -> None:
    conn = RabbitMQConnectionManager(url=rabbitmq_url)
    await conn.connect()
    try:
        assert await conn.health_check() is True
    finally:
        await conn.close()
