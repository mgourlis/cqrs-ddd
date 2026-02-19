"""In-memory messaging adapters for testing."""

from __future__ import annotations

from .bus import InMemoryMessageBus
from .consumer import InMemoryConsumer
from .publisher import InMemoryPublisher

__all__ = [
    "InMemoryMessageBus",
    "InMemoryConsumer",
    "InMemoryPublisher",
]
