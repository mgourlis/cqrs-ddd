"""SQS transport adapter (optional extra: cqrs-ddd-messaging[sqs])."""

from __future__ import annotations

from .connection import SQSConnectionManager
from .consumer import SQSConsumer
from .publisher import SQSPublisher

__all__ = [
    "SQSConnectionManager",
    "SQSConsumer",
    "SQSPublisher",
]
