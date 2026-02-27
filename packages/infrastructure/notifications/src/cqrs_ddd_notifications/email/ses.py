"""AWS SES email implementation (optional)."""

from __future__ import annotations

import importlib.util
import logging
from typing import Any

from ..delivery import DeliveryRecord, NotificationChannel, RenderedNotification
from ..ports.sender import INotificationSender

logger = logging.getLogger(__name__)


class SesEmailSender(INotificationSender):
    """
    AWS SES email sender using aiobotocore.

    Requires AWS credentials and region configuration.
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        timeout: float = 10.0,
        from_email: str | None = None,
    ):
        self.region_name = region_name
        self.timeout = timeout
        self.from_email = from_email
        self._client = None

    async def _get_client(self) -> Any:
        """Lazy-initialize AWS SES client."""
        if self._client is None:
            if importlib.util.find_spec("aiobotocore") is None:
                raise ImportError(
                    "aiobotocore is required for SesEmailSender. "
                    "Install with: pip install 'cqrs-ddd-notifications[aws]'"
                )

            from aiobotocore import AioSession

            session = AioSession()
            self._client = session.create_client("ses", region_name=self.region_name)

        return self._client

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        if channel != NotificationChannel.EMAIL:
            raise ValueError(f"SesEmailSender does not support {channel}")

        from_addr = (metadata or {}).get("from_email") or self.from_email
        if not from_addr:
            raise ValueError("Sender email (from_email) is required.")

        try:
            client = await self._get_client()

            # Build SES message parameters
            message_params: dict[str, Any] = {
                "Source": from_addr,
                "Destination": {"ToAddresses": [recipient]},
            }

            # Handle HTML content
            if content.body_html:
                message_params["Message"] = {
                    "Subject": {"Data": content.subject or ""},
                    "Body": {
                        "Text": {"Data": content.body_text, "Charset": "UTF-8"},
                        "Html": {"Data": content.body_html, "Charset": "UTF-8"},
                    },
                }
            else:
                message_params["Message"] = {
                    "Subject": {"Data": content.subject or ""},
                    "Body": {
                        "Text": {"Data": content.body_text, "Charset": "UTF-8"},
                    },
                }

            # Handle attachments
            if content.attachments:
                message_params["Message"]["Attachments"] = []
                for attachment in content.attachments:
                    import base64

                    message_params["Message"]["Attachments"].append(
                        {
                            "Data": base64.b64encode(attachment.content).decode(),
                            "Filename": attachment.filename,
                        }
                    )

            response = await client.send_email(**message_params)

            logger.info(f"Email sent to {recipient} via SES (MessageId: {response['MessageId']})")
            return DeliveryRecord.sent(recipient, channel, provider_id=response["MessageId"])

        except Exception as e:
            logger.error(f"Failed to send email via SES to {recipient}: {str(e)}")
            return DeliveryRecord.failed(recipient, channel, error=str(e))
