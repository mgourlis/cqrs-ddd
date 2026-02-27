"""Memory adapters for testing and development."""

from __future__ import annotations

from .console import ConsoleSender
from .fake import InMemorySender

__all__ = ["ConsoleSender", "InMemorySender"]
