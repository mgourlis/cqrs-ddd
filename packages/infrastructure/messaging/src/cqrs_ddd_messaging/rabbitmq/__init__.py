"""RabbitMQ transport adapter (optional extra: cqrs-ddd-messaging[rabbitmq])."""

from __future__ import annotations

from .connection import RabbitMQConnectionManager
from .consumer import RabbitMQConsumer
from .publisher import RabbitMQPublisher

__all__ = [
    "RabbitMQConnectionManager",
    "RabbitMQConsumer",
    "RabbitMQPublisher",
]
