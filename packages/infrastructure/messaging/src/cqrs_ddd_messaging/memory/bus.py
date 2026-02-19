"""In-memory message bus for testing — connects publisher and consumer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..envelope import MessageEnvelope

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


class InMemoryMessageBus:
    """Shared bus: publish appends messages and
    synchronously invokes registered handlers."""

    def __init__(self) -> None:
        self._messages: list[tuple[str, Any, dict[str, Any]]] = []
        self._handlers: dict[str, list[Callable[..., Coroutine[Any, Any, None]]]] = {}

    def register(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        """Register a handler for the topic."""
        self._handlers.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Append message and invoke all handlers for the topic."""
        self._messages.append((topic, message, kwargs))
        # Pass payload to handlers when message is
        # MessageEnvelope (same as broker consumers)
        payload = message.payload if isinstance(message, MessageEnvelope) else message
        for h in self._handlers.get(topic, []):
            await h(payload, **kwargs)

    def get_published(
        self,
    ) -> list[tuple[str, Any, dict[str, Any]]]:
        """Return all published (topic, message, kwargs) in order."""
        return list(self._messages)

    def clear(self) -> None:
        """Clear published messages and handlers (for test teardown)."""
        self._messages.clear()
        self._handlers.clear()
