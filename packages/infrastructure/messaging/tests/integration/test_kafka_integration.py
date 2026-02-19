"""Integration tests for Kafka adapter (require aiokafka and testcontainers)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("aiokafka")
pytest.importorskip("testcontainers")

import contextlib

from testcontainers.kafka import KafkaContainer

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.kafka import (
    KafkaConnectionManager,
    KafkaConsumer,
    KafkaPublisher,
)
from cqrs_ddd_messaging.serialization import EnvelopeSerializer


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    with KafkaContainer("confluentinc/cp-kafka:7.5.0") as kafka:
        yield kafka.get_bootstrap_server()


@pytest.mark.asyncio
async def test_kafka_publish_consume(kafka_bootstrap_servers: str) -> None:
    conn = KafkaConnectionManager(bootstrap_servers=kafka_bootstrap_servers)
    serializer = EnvelopeSerializer()
    pub = KafkaPublisher(connection=conn, serializer=serializer)
    consumer = KafkaConsumer(
        connection=conn,
        group_id="test-group",
        serializer=serializer,
    )
    received: list[dict] = []

    async def handler(payload: object) -> None:
        received.append(payload if isinstance(payload, dict) else {})

    await consumer.subscribe("test-topic", handler)
    task = asyncio.create_task(consumer.run())
    try:
        await pub.publish(
            "test-topic",
            MessageEnvelope(event_type="OrderCreated", payload={"order_id": "1"}),
        )
        await asyncio.sleep(5.0)
        assert len(received) >= 1
        assert received[0].get("order_id") == "1"
    finally:
        await consumer.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await pub.close()


@pytest.mark.asyncio
async def test_kafka_health_check(kafka_bootstrap_servers: str) -> None:
    conn = KafkaConnectionManager(bootstrap_servers=kafka_bootstrap_servers)
    assert await conn.health_check() is True
