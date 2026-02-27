"""In-memory sender for test assertions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from cqrs_ddd_notifications.delivery import (
    DeliveryRecord,
    NotificationChannel,
    RenderedNotification,
)
from cqrs_ddd_notifications.ports.sender import INotificationSender

logger = logging.getLogger(__name__)


@dataclass
class SentMessage:
    """Record of a sent message for test assertions."""

    recipient: str
    content: RenderedNotification
    channel: NotificationChannel
    metadata: dict[str, object] | None


class InMemorySender(INotificationSender):
    """
    Test double (Fake) that stores messages in a list for assertions.
    """

    def __init__(self) -> None:
        self.sent_messages: list[SentMessage] = []

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        self.sent_messages.append(SentMessage(recipient, content, channel, metadata))
        return DeliveryRecord.sent(recipient, channel, provider_id="test-id")

    def assert_sent(
        self,
        recipient: str,
        channel: NotificationChannel,
        count: int = 1,
    ) -> None:
        """Helper for test assertions."""
        matches = [
            m for m in self.sent_messages if m.recipient == recipient and m.channel == channel
        ]
        if len(matches) != count:
            raise AssertionError(
                f"Expected {count} messages to {recipient} via {channel.value}, "
                f"but found {len(matches)}."
            )

    def clear(self) -> None:
        """Clear all sent messages."""
        self.sent_messages.clear()
