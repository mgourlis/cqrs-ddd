"""Tests for in-memory sender."""

import pytest

from cqrs_ddd_notifications.delivery import NotificationChannel, RenderedNotification
from cqrs_ddd_notifications.memory.fake import InMemorySender


@pytest.mark.asyncio
async def test_in_memory_sender_records_messages():
    """Test InMemorySender records sent messages."""
    sender = InMemorySender()

    content = RenderedNotification(body_text="Test message")

    await sender.send(
        recipient="+1234567890",
        content=content,
        channel=NotificationChannel.SMS,
    )

    assert len(sender.sent_messages) == 1
    assert sender.sent_messages[0].recipient == "+1234567890"
    assert sender.sent_messages[0].channel == NotificationChannel.SMS


@pytest.mark.asyncio
async def test_in_memory_sender_assert_sent_success():
    """Test assert_sent passes with correct count."""
    sender = InMemorySender()

    content = RenderedNotification(body_text="Message 1")
    await sender.send("+1234567890", content, NotificationChannel.SMS)

    content2 = RenderedNotification(body_text="Message 2")
    await sender.send("+1234567890", content2, NotificationChannel.SMS)

    # Should not raise
    sender.assert_sent("+1234567890", NotificationChannel.SMS, count=2)


@pytest.mark.asyncio
async def test_in_memory_sender_assert_sent_failure():
    """Test assert_sent raises with wrong count."""
    sender = InMemorySender()

    content = RenderedNotification(body_text="Message")
    await sender.send("+1234567890", content, NotificationChannel.SMS)

    with pytest.raises(AssertionError) as exc_info:
        sender.assert_sent("+1234567890", NotificationChannel.SMS, count=2)

    assert "Expected 2 messages" in str(exc_info.value)


@pytest.mark.asyncio
async def test_in_memory_sender_clear():
    """Test clear resets sent messages."""
    sender = InMemorySender()

    content = RenderedNotification(body_text="Message")
    await sender.send("+1234567890", content, NotificationChannel.SMS)

    assert len(sender.sent_messages) == 1

    sender.clear()

    assert len(sender.sent_messages) == 0
