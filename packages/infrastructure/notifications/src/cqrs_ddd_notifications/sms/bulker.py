"""Bulker.gr SMS implementation using httpx."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..delivery import DeliveryRecord, NotificationChannel
from ..ports.sender import INotificationSender

if TYPE_CHECKING:
    from ..delivery import RenderedNotification

logger = logging.getLogger(__name__)


class BulkerSMSSender(INotificationSender):
    """
    Pure-Python implementation of Bulker.gr SMS API using httpx.
    No framework dependencies (Django/FastAPI).
    """

    def __init__(
        self,
        auth_key: str,
        default_from: str | None = None,
        sms_url: str = "https://www.bulker.gr/api/v1/sms/send",
        validity: int = 1,
        timeout: float = 10.0,
    ):
        self.auth_key = auth_key
        self.default_from = default_from
        self.sms_url = sms_url
        self.validity = validity
        self.timeout = timeout

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        if channel != NotificationChannel.SMS:
            raise ValueError(f"BulkerSMSSender does not support {channel}")

        originator = (metadata or {}).get("from_number") or self.default_from
        if not originator:
            raise ValueError("Sender number (originator) is required.")

        # Bulker expects recipient numbers without leading '+'
        clean_recipient = recipient.lstrip("+")

        # Unique message ID based on nanoseconds
        msg_id = int(time.time_ns() / 1_000_000)

        data = {
            "auth_key": self.auth_key,
            "id": msg_id,
            "from": originator,
            "to": clean_recipient,
            "text": content.body_text,
            "validity": self.validity,
        }

        # Lazy import of httpx
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx is required for BulkerSMSSender. "
                "Install with: pip install 'cqrs-ddd-notifications[http]'"
            ) from e

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.sms_url, data=data)
                response.raise_for_status()

                # Bulker returns "OK;MSG_ID;CHARGE" or "ERROR;CODE;DESCRIPTION"
                result = response.text
                if result.startswith("OK"):
                    logger.info(f"SMS sent successfully to {recipient} (ID: {msg_id})")
                    return DeliveryRecord.sent(recipient, channel, provider_id=str(msg_id))

                raise Exception(f"Bulker API Error: {result}")

            except Exception as e:
                logger.error(f"Failed to send SMS to {recipient}: {str(e)}")
                return DeliveryRecord.failed(recipient, channel, error=str(e))
