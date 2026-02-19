"""InMemoryPublisher — IMessagePublisher with assertion helpers for tests."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core.ports.messaging import IMessagePublisher

from ..envelope import MessageEnvelope
from .bus import InMemoryMessageBus


class InMemoryPublisher(IMessagePublisher):
    """In-memory publisher that buffers messages for testing and optional sync dispatch.

    Pass a shared InMemoryMessageBus to connect with InMemoryConsumer so that
    publish() triggers subscribed handlers. get_published() and assert_published()
    support test assertions.
    """

    def __init__(self, bus: InMemoryMessageBus | None = None) -> None:
        """If bus is None, a new bus is created (no consumer connection)."""
        self._bus = bus or InMemoryMessageBus()

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Publish to the in-memory bus (and trigger any subscribed handlers)."""
        await self._bus.publish(topic, message, **kwargs)

    def get_published(
        self,
    ) -> list[tuple[str, Any, dict[str, Any]]]:
        """Return all (topic, message, kwargs) published so far."""
        return self._bus.get_published()

    def _event_type_of(self, message: Any) -> str | None:
        """Extract event_type from message (envelope or dict)."""
        if isinstance(message, MessageEnvelope):
            return message.event_type
        if isinstance(message, dict):
            return message.get("event_type")
        return None

    def assert_published(
        self,
        event_type: str,
        count: int = 1,
        topic: str | None = None,
    ) -> None:
        """Assert that exactly `count` messages with this event_type were published.

        Optionally restrict to a specific topic. Raises AssertionError if not met.
        """
        published = self.get_published()
        if topic is not None:
            published = [(t, m, k) for t, m, k in published if t == topic]
        matching = [m for _, m, _ in published if self._event_type_of(m) == event_type]
        assert len(matching) == count, (
            f"Expected {count} message(s) with event_type={event_type!r}, "
            f"got {len(matching)}. Published: "
            f"{[self._event_type_of(m) for _, m, _ in published]}"
        )

    @property
    def bus(self) -> InMemoryMessageBus:
        """Return the bus (e.g. to pass to InMemoryConsumer)."""
        return self._bus
