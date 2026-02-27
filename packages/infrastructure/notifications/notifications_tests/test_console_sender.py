"""Tests for console sender."""

import pytest

from cqrs_ddd_notifications.delivery import AttachmentVO, NotificationChannel, RenderedNotification
from cqrs_ddd_notifications.memory.console import ConsoleSender


@pytest.mark.asyncio
async def test_console_sender_prints_output(capsys):
    """Test ConsoleSender prints notification."""
    sender = ConsoleSender()

    content = RenderedNotification(
        body_text="Test body",
        subject="Test Subject",
    )

    await sender.send(
        recipient="+1234567890",
        content=content,
        channel=NotificationChannel.SMS,
    )

    captured = capsys.readouterr()
    assert "NOTIFICATION SENT VIA SMS" in captured.out
    assert "+1234567890" in captured.out
    assert "Test Subject" in captured.out
    assert "Test body" in captured.out


@pytest.mark.asyncio
async def test_console_sender_with_html_and_attachments(capsys):
    """Test ConsoleSender shows HTML and attachments info."""
    sender = ConsoleSender()

    content = RenderedNotification(
        body_text="Plain text",
        body_html="<html><body>HTML content</body></html>",
        subject="Test",
        attachments=[
            AttachmentVO(
                filename="file.pdf",
                content=b"fake pdf content",
                mimetype="application/pdf",
            )
        ],
    )

    await sender.send(
        recipient="user@example.com",
        content=content,
        channel=NotificationChannel.EMAIL,
    )

    captured = capsys.readouterr()
    assert "HTML:" in captured.out
    assert "Files:" in captured.out
    assert "file.pdf" in captured.out
