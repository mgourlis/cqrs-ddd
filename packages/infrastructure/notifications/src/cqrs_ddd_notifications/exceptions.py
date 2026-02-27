"""Exception hierarchy for notifications."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError


class NotificationError(InfrastructureError):
    """Base exception for notification infrastructure failures."""


class NotificationDeliveryError(NotificationError):
    """Raised when delivery fails (network, provider error, etc.)."""

    def __init__(self, channel: str, recipient: str, reason: str):
        self.channel = channel
        self.recipient = recipient
        super().__init__(f"Failed to deliver via {channel} to {recipient}: {reason}")


class TemplateNotFoundError(NotificationError):
    """Raised when no template is registered for event/channel/locale combo."""

    def __init__(self, event_type: str, channel: str, locale: str):
        self.event_type = event_type
        self.channel = channel
        self.locale = locale
        super().__init__(f"No template for {event_type}/{channel}/{locale}")


class RecipientResolutionError(NotificationError):
    """Raised when ChannelRouter cannot resolve recipient information."""
