"""InMemoryConsumer — IMessageConsumer with synchronous dispatch for tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.messaging import IMessageConsumer

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from .bus import InMemoryMessageBus


class InMemoryConsumer(IMessageConsumer):
    """In-memory consumer that registers handlers on a shared bus.

    Use the same InMemoryMessageBus as InMemoryPublisher so that publish()
    triggers handlers synchronously in tests.
    """

    def __init__(self, bus: InMemoryMessageBus) -> None:
        """Requires a shared bus (typically from InMemoryPublisher.bus)."""
        self._bus = bus

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        queue_name: str | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Register handler for the topic. queue_name and kwargs are ignored."""
        self._bus.register(topic, handler)
