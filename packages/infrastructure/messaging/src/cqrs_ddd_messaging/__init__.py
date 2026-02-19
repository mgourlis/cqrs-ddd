"""Message transport adapters for CQRS/DDD — RabbitMQ, Kafka, SQS, and in-memory."""

from __future__ import annotations

from .dead_letter import DeadLetterHandler
from .envelope import MessageEnvelope
from .exceptions import (
    DeadLetterError,
    MessagingConnectionError,
    MessagingError,
    MessagingSerializationError,
)
from .idempotency import IdempotencyFilter
from .memory import InMemoryConsumer, InMemoryMessageBus, InMemoryPublisher
from .retry import RetryPolicy
from .serialization import EnvelopeSerializer

__all__ = [
    "DeadLetterError",
    "DeadLetterHandler",
    "EnvelopeSerializer",
    "IdempotencyFilter",
    "InMemoryConsumer",
    "InMemoryMessageBus",
    "InMemoryPublisher",
    "MessageEnvelope",
    "MessagingConnectionError",
    "MessagingError",
    "MessagingSerializationError",
    "RetryPolicy",
]
