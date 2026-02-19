"""Kafka transport adapter (optional extra: cqrs-ddd-messaging[kafka])."""

from __future__ import annotations

from .connection import KafkaConnectionManager
from .consumer import KafkaConsumer
from .publisher import KafkaPublisher

__all__ = [
    "KafkaConnectionManager",
    "KafkaConsumer",
    "KafkaPublisher",
]
