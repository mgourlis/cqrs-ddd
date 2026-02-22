"""Unit tests for RabbitMQPublisher with mocked connection (no real broker)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.exceptions import MessagingSerializationError
from cqrs_ddd_messaging.rabbitmq.publisher import RabbitMQPublisher
from cqrs_ddd_messaging.serialization import EnvelopeSerializer


@pytest.fixture
def mock_connection() -> MagicMock:
    conn = MagicMock()
    conn.connect = AsyncMock()
    conn.health_check = AsyncMock(return_value=True)
    mock_channel = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    conn.channel = mock_channel
    return conn


@pytest.fixture
def publisher(mock_connection: MagicMock) -> RabbitMQPublisher:
    return RabbitMQPublisher(connection=mock_connection, exchange_name="test.ex")


@pytest.mark.asyncio
async def test_publish_dict_message(
    publisher: RabbitMQPublisher, mock_connection: MagicMock
) -> None:
    await publisher.publish("orders", {"event_type": "OrderCreated", "order_id": "1"})
    mock_connection.connect.assert_called_once()
    exchange = mock_connection.channel.declare_exchange.return_value
    exchange.publish.assert_called_once()
    call = exchange.publish.call_args
    assert call.kwargs["routing_key"] == "orders"
    assert b"OrderCreated" in call.args[0].body


@pytest.mark.asyncio
async def test_publish_plain_object_event_type_from_kwargs(
    publisher: RabbitMQPublisher, mock_connection: MagicMock
) -> None:
    await publisher.publish("orders", 42, event_type="CustomEvent")
    exchange = mock_connection.channel.declare_exchange.return_value
    call = exchange.publish.call_args
    assert b"CustomEvent" in call.args[0].body
    assert b"42" in call.args[0].body or b"value" in call.args[0].body


@pytest.mark.asyncio
async def test_publish_message_envelope_passthrough(
    publisher: RabbitMQPublisher, mock_connection: MagicMock
) -> None:
    envelope = MessageEnvelope(event_type="X", payload={"a": 1}, correlation_id="c1")
    await publisher.publish("t", envelope)
    exchange = mock_connection.channel.declare_exchange.return_value
    exchange.publish.assert_called_once()
    msg = exchange.publish.call_args[0][0]
    assert isinstance(msg.body, bytes)
    assert b"X" in msg.body
    assert b"a" in msg.body


@pytest.mark.asyncio
async def test_publish_serializer_raises_messaging_error(
    mock_connection: MagicMock,
) -> None:
    serializer = MagicMock(spec=EnvelopeSerializer)
    serializer.serialize = MagicMock(side_effect=TypeError("bad"))
    publisher = RabbitMQPublisher(connection=mock_connection, serializer=serializer)
    with pytest.raises(MessagingSerializationError) as exc_info:
        await publisher.publish("t", MessageEnvelope(event_type="X", payload={}))
    assert "bad" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_health_check_delegates_to_connection(
    publisher: RabbitMQPublisher, mock_connection: MagicMock
) -> None:
    mock_connection.health_check.return_value = True
    result = await publisher.health_check()
    assert result is True
    mock_connection.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_returns_false_when_connection_unhealthy(
    publisher: RabbitMQPublisher, mock_connection: MagicMock
) -> None:
    mock_connection.health_check.return_value = False
    result = await publisher.health_check()
    assert result is False
