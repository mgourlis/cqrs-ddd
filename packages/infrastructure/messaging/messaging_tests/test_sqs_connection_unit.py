"""Unit tests for SQSConnectionManager with mocked aiobotocore (no real AWS)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_messaging.exceptions import MessagingConnectionError
from cqrs_ddd_messaging.sqs.connection import SQSConnectionManager


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    mock_cm = MagicMock()
    mock_client = MagicMock()
    mock_client.get_queue_url = AsyncMock(
        return_value={"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/my-queue"}
    )
    mock_client.create_queue = AsyncMock(
        return_value={"QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/new-queue"}
    )
    mock_client.list_queues = AsyncMock(return_value={"QueueUrls": []})
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    session.create_client = MagicMock(return_value=mock_cm)
    return session


@pytest.mark.asyncio
async def test_get_client_creates_and_caches(mock_session: MagicMock) -> None:
    conn = SQSConnectionManager(region_name="us-east-1", session=mock_session)
    client1 = await conn.get_client()
    client2 = await conn.get_client()
    assert client1 is client2
    mock_session.create_client.assert_called_once()
    assert mock_session.create_client.call_args.kwargs["region_name"] == "us-east-1"
    assert mock_session.create_client.call_args.args[0] == "sqs"


@pytest.mark.asyncio
async def test_get_queue_url_returns_url(mock_session: MagicMock) -> None:
    conn = SQSConnectionManager(session=mock_session)
    url = await conn.get_queue_url("my-queue")
    assert url == "https://sqs.us-east-1.amazonaws.com/123/my-queue"
    client = await conn.get_client()
    client.get_queue_url.assert_called_once_with(QueueName="my-queue")


@pytest.mark.asyncio
async def test_get_queue_url_creates_queue_if_not_exists(
    mock_session: MagicMock,
) -> None:
    client = mock_session.create_client.return_value.__aenter__.return_value
    err_response = {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}}

    class QueueNotFound(Exception):  # noqa: N818
        response = err_response

    client.get_queue_url = AsyncMock(side_effect=QueueNotFound())
    conn = SQSConnectionManager(session=mock_session)
    url = await conn.get_queue_url("new-queue")
    assert url == "https://sqs.us-east-1.amazonaws.com/123/new-queue"
    client.create_queue.assert_called_once_with(QueueName="new-queue")


@pytest.mark.asyncio
async def test_get_queue_url_raises_on_other_errors(mock_session: MagicMock) -> None:
    client = mock_session.create_client.return_value.__aenter__.return_value
    client.get_queue_url = AsyncMock(side_effect=RuntimeError("network error"))
    conn = SQSConnectionManager(session=mock_session)
    with pytest.raises(MessagingConnectionError) as exc_info:
        await conn.get_queue_url("my-queue")
    assert "network error" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_close_cleans_up_client(mock_session: MagicMock) -> None:
    mock_cm = mock_session.create_client.return_value
    conn = SQSConnectionManager(session=mock_session)
    await conn.get_client()
    await conn.close()
    mock_cm.__aexit__.assert_called_once()
    assert conn._client is None
    assert conn._client_cm is None


@pytest.mark.asyncio
async def test_close_idempotent_when_never_opened(mock_session: MagicMock) -> None:
    conn = SQSConnectionManager(session=mock_session)
    await conn.close()
    mock_session.create_client.return_value.__aexit__.assert_not_called()


@pytest.mark.asyncio
async def test_health_check_returns_true_when_list_queues_succeeds(
    mock_session: MagicMock,
) -> None:
    conn = SQSConnectionManager(session=mock_session)
    result = await conn.health_check()
    assert result is True
    client = await conn.get_client()
    client.list_queues.assert_called_once_with(MaxResults=1)


@pytest.mark.asyncio
async def test_health_check_returns_false_on_failure(mock_session: MagicMock) -> None:
    client = mock_session.create_client.return_value.__aenter__.return_value
    client.list_queues = AsyncMock(side_effect=RuntimeError("timeout"))
    conn = SQSConnectionManager(session=mock_session)
    result = await conn.health_check()
    assert result is False
