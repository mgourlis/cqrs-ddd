"""Unit tests for SQSPublisher with mocked connection (no real AWS)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.exceptions import MessagingSerializationError
from cqrs_ddd_messaging.serialization import EnvelopeSerializer
from cqrs_ddd_messaging.sqs.publisher import SQSPublisher


@pytest.fixture
def mock_connection() -> MagicMock:
    conn = MagicMock()
    conn.get_client = AsyncMock()
    conn.get_queue_url = AsyncMock(
        return_value="https://sqs.us-east-1.amazonaws.com/123/my-queue"
    )
    conn.health_check = AsyncMock(return_value=True)
    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()
    conn.get_client.return_value = mock_client
    return conn


@pytest.fixture
def publisher(mock_connection: MagicMock) -> SQSPublisher:
    return SQSPublisher(connection=mock_connection)


@pytest.mark.asyncio
async def test_publish_dict_message(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    await publisher.publish("my-queue", {"event_type": "OrderCreated", "order_id": "1"})
    mock_connection.get_queue_url.assert_called_once_with("my-queue")
    client = mock_connection.get_client.return_value
    client.send_message.assert_called_once()
    call = client.send_message.call_args
    assert call.kwargs["QueueUrl"] == "https://sqs.us-east-1.amazonaws.com/123/my-queue"
    assert "OrderCreated" in call.kwargs["MessageBody"]
    assert "order_id" in call.kwargs["MessageBody"]


@pytest.mark.asyncio
async def test_publish_with_queue_url_in_kwargs(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    await publisher.publish(
        "ignored",
        {"x": 1},
        queue_url="https://sqs.eu-west-1.amazonaws.com/456/custom",
    )
    mock_connection.get_queue_url.assert_not_called()
    client = mock_connection.get_client.return_value
    client.send_message.assert_called_once()
    assert client.send_message.call_args.kwargs["QueueUrl"] == (
        "https://sqs.eu-west-1.amazonaws.com/456/custom"
    )


@pytest.mark.asyncio
async def test_publish_plain_object_event_type_from_kwargs(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    await publisher.publish("q", 42, event_type="CustomEvent")
    client = mock_connection.get_client.return_value
    body = client.send_message.call_args.kwargs["MessageBody"]
    assert "CustomEvent" in body
    assert "42" in body or "value" in body


@pytest.mark.asyncio
async def test_publish_message_envelope_passthrough(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    envelope = MessageEnvelope(event_type="X", payload={"a": 1}, correlation_id="c1")
    await publisher.publish("t", envelope)
    client = mock_connection.get_client.return_value
    client.send_message.assert_called_once()
    body = client.send_message.call_args.kwargs["MessageBody"]
    assert "X" in body
    assert "a" in body


@pytest.mark.asyncio
async def test_publish_fifo_adds_dedup_and_group_id(
    mock_connection: MagicMock,
) -> None:
    mock_connection.get_queue_url = AsyncMock(
        return_value="https://sqs.us-east-1.amazonaws.com/123/my-queue.fifo"
    )
    publisher = SQSPublisher(connection=mock_connection)
    await publisher.publish(
        "my-queue.fifo", {"aggregate_id": "agg-1", "event_type": "E"}
    )
    client = mock_connection.get_client.return_value
    call = client.send_message.call_args.kwargs
    assert "MessageDeduplicationId" in call
    assert call["MessageGroupId"] == "agg-1"


@pytest.mark.asyncio
async def test_publish_fifo_default_group_id(mock_connection: MagicMock) -> None:
    mock_connection.get_queue_url = AsyncMock(
        return_value="https://sqs.us-east-1.amazonaws.com/123/queue.fifo"
    )
    publisher = SQSPublisher(connection=mock_connection)
    await publisher.publish("queue.fifo", {"event_type": "E"})
    call = mock_connection.get_client.return_value.send_message.call_args.kwargs
    assert call["MessageGroupId"] == "default"


@pytest.mark.asyncio
async def test_publish_serializer_raises_messaging_error(
    mock_connection: MagicMock,
) -> None:
    serializer = MagicMock(spec=EnvelopeSerializer)
    serializer.serialize = MagicMock(side_effect=TypeError("bad"))
    publisher = SQSPublisher(connection=mock_connection, serializer=serializer)
    with pytest.raises(MessagingSerializationError) as exc_info:
        await publisher.publish("t", MessageEnvelope(event_type="X", payload={}))
    assert "bad" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_health_check_delegates_to_connection(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    mock_connection.health_check.return_value = True
    result = await publisher.health_check()
    assert result is True
    mock_connection.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_returns_false_when_connection_unhealthy(
    publisher: SQSPublisher, mock_connection: MagicMock
) -> None:
    mock_connection.health_check.return_value = False
    result = await publisher.health_check()
    assert result is False
