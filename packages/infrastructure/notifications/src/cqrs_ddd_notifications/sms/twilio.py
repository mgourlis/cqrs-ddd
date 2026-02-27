"""Twilio SMS implementation (optional)."""

from __future__ import annotations

import logging

from ..delivery import DeliveryRecord, NotificationChannel, RenderedNotification
from ..ports.sender import INotificationSender

logger = logging.getLogger(__name__)


class TwilioSMSSender(INotificationSender):
    """
    Twilio SMS implementation.

    Requires twilio library:
    pip install twilio
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        timeout: float = 10.0,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.timeout = timeout

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        if channel != NotificationChannel.SMS:
            raise ValueError(f"TwilioSMSSender does not support {channel}")

        # Lazy import of twilio
        try:
            from twilio.base.exceptions import TwilioRestException
            from twilio.rest import Client as TwilioClient
        except ImportError as e:
            raise ImportError(
                "twilio is required for TwilioSMSSender. Install with: pip install twilio"
            ) from e

        try:
            client = TwilioClient(self.account_sid, self.auth_token)

            message = client.messages.create(
                to=recipient,
                from_=self.from_number,
                body=content.body_text,
            )

            logger.info(f"SMS sent via Twilio to {recipient} (SID: {message.sid})")
            return DeliveryRecord.sent(recipient, channel, provider_id=message.sid)

        except TwilioRestException as e:
            logger.error(f"Twilio API error: {str(e)}")
            return DeliveryRecord.failed(recipient, channel, error=str(e))
        except Exception as e:
            logger.error(f"Failed to send SMS via Twilio: {str(e)}")
            return DeliveryRecord.failed(recipient, channel, error=str(e))
