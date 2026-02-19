"""Messaging-specific exceptions for cqrs-ddd-messaging."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError


class MessagingError(InfrastructureError):
    """Base class for all messaging-related infrastructure errors."""


class MessagingConnectionError(MessagingError):
    """Raised when connectivity to the message broker fails."""


class MessagingSerializationError(MessagingError):
    """Raised when message serialization or deserialization fails."""


class DeadLetterError(MessagingError):
    """Raised when a message is routed to the dead-letter queue after max retries."""

    def __init__(self, message: str, message_id: str | None = None) -> None:
        self.message_id = message_id
        super().__init__(message)
