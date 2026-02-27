"""Delivery tracking types and channel enum."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Supported notification channels."""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class DeliveryStatus(Enum):
    """Delivery status outcomes."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass(frozen=True)
class DeliveryRecord:
    """Immutable record of a notification delivery attempt."""

    recipient: str
    channel: NotificationChannel
    status: DeliveryStatus
    provider_id: str | None = None
    sent_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.sent_at is None:
            object.__setattr__(self, "sent_at", datetime.now(timezone.utc))

    @classmethod
    def sent(
        cls,
        recipient: str,
        channel: NotificationChannel,
        provider_id: str | None = None,
    ) -> DeliveryRecord:
        """Create a successful delivery record."""
        return cls(
            recipient=recipient,
            channel=channel,
            status=DeliveryStatus.SENT,
            provider_id=provider_id,
        )

    @classmethod
    def failed(
        cls,
        recipient: str,
        channel: NotificationChannel,
        error: str | None = None,
    ) -> DeliveryRecord:
        """Create a failed delivery record."""
        return cls(
            recipient=recipient,
            channel=channel,
            status=DeliveryStatus.FAILED,
            error=error,
        )


@dataclass(frozen=True)
class AttachmentVO:
    """Immutable attachment value object."""

    filename: str
    content: bytes
    mimetype: str


@dataclass(frozen=True)
class RenderedNotification:
    """Immutable rendered notification ready for delivery."""

    body_text: str
    subject: str | None = None
    body_html: str | None = None
    attachments: list[AttachmentVO] | None = None

    def __post_init__(self) -> None:
        if self.attachments is None:
            object.__setattr__(self, "attachments", [])
