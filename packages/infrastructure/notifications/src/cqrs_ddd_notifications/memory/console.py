"""Console sender for development debugging."""

from __future__ import annotations

import logging

from cqrs_ddd_notifications.delivery import (
    DeliveryRecord,
    NotificationChannel,
    RenderedNotification,
)
from cqrs_ddd_notifications.ports.sender import INotificationSender

logger = logging.getLogger(__name__)


class ConsoleSender(INotificationSender):
    """
    Development adapter that prints notifications to the console.
    """

    def __init__(self, output_to_stdout: bool = True):
        self.output_to_stdout = output_to_stdout

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        output = [
            "═" * 50,
            f"NOTIFICATION SENT VIA {channel.value.upper()}",
            f"To:      {recipient}",
            f"Subject: {content.subject or '(No Subject)'}",
            f"Body:    {content.body_text}",
        ]

        if content.body_html:
            output.append(f"HTML:    [Available: {len(content.body_html)} bytes]")

        if content.attachments:
            files = ", ".join([a.filename for a in content.attachments])
            output.append(f"Files:   {files}")

        output.append("═" * 50)

        full_output = "\n".join(output)
        logger.info(full_output)

        if self.output_to_stdout:
            print(full_output)

        return DeliveryRecord.sent(recipient, channel, provider_id="console-debug")
