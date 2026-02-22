"""Unit tests for KafkaPublisher with mocked connection and producer (no real broker)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.exceptions import MessagingSerializationError
from cqrs_ddd_messaging.kafka.publisher import KafkaPublisher
from cqrs_ddd_messaging.serialization import EnvelopeSerializer


@pytest.fixture
def mock_connection() -> MagicMock:
    conn = MagicMock()
    conn.producer_config.return_value = {"bootstrap_servers": "localhost:9092"}
    conn.health_check = AsyncMock(return_value=True)
    return conn


@pytest.fixture
def mock_producer() -> MagicMock:
    prod = MagicMock()
    prod.start = AsyncMock()
    prod.stop = AsyncMock()
    prod.send_and_wait = AsyncMock()
    return prod


@pytest.mark.asyncio
async def test_publish_with_aggregate_id_on_message(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        publisher = KafkaPublisher(connection=mock_connection)

        class Msg:
            aggregate_id = "agg-123"

            def model_dump(self):
                return {"aggregate_id": "agg-123", "x": 1}

        await publisher.publish("orders", Msg())
    mock_producer.send_and_wait.assert_called_once()
    assert mock_producer.send_and_wait.call_args[1].get("key") == b"agg-123"


@pytest.mark.asyncio
async def test_publish_message_envelope_with_aggregate_id_in_payload(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        publisher = KafkaPublisher(connection=mock_connection)
        envelope = MessageEnvelope(
            event_type="OrderCreated", payload={"aggregate_id": "ord-456", "amount": 10}
        )
        await publisher.publish("orders", envelope)
    mock_producer.send_and_wait.assert_called_once()
    call_kw = mock_producer.send_and_wait.call_args[1]
    assert call_kw.get("key") == b"ord-456"


@pytest.mark.asyncio
async def test_publish_partition_key_from_kwargs(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        publisher = KafkaPublisher(connection=mock_connection)
        await publisher.publish("orders", {"event_type": "X"}, partition_key="key-789")
    mock_producer.send_and_wait.assert_called_once()
    assert mock_producer.send_and_wait.call_args[1].get("key") == b"key-789"


@pytest.mark.asyncio
async def test_publish_serializer_raises_messaging_error(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        serializer = MagicMock(spec=EnvelopeSerializer)
        serializer.serialize = MagicMock(side_effect=ValueError("serialize failed"))
        publisher = KafkaPublisher(connection=mock_connection, serializer=serializer)
        with pytest.raises(MessagingSerializationError) as exc_info:
            await publisher.publish("t", MessageEnvelope(event_type="X", payload={}))
        assert "serialize failed" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_close_stops_producer(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        publisher = KafkaPublisher(connection=mock_connection)
        await publisher.publish("t", MessageEnvelope(event_type="X", payload={}))
        await publisher.close()
    mock_producer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_close_idempotent_when_not_started(mock_connection: MagicMock) -> None:
    publisher = KafkaPublisher(connection=mock_connection)
    await publisher.close()
    # No exception; producer was never created


@pytest.mark.asyncio
async def test_health_check_delegates_to_connection(
    mock_connection: MagicMock, mock_producer: MagicMock
) -> None:
    with patch(
        "cqrs_ddd_messaging.kafka.publisher.AIOKafkaProducer",
        return_value=mock_producer,
    ):
        publisher = KafkaPublisher(connection=mock_connection)
        mock_connection.health_check.return_value = True
        result = await publisher.health_check()
    assert result is True
    mock_connection.health_check.assert_called_once()
