"""Notification sender port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..delivery import DeliveryRecord, NotificationChannel, RenderedNotification


@runtime_checkable
class INotificationSender(Protocol):
    """
    Framework-agnostic port for sending notifications across different channels.

    Adapters must explicitly declare: class SmtpSender(INotificationSender):
    """

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        """Send notification and return delivery record."""
        ...
