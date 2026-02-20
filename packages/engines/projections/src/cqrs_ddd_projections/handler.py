"""ProjectionHandler base class — type-safe event -> projection mapping."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

AsyncEventHandler: TypeAlias = Callable[["DomainEvent"], Awaitable[None]]


class ProjectionHandler:
    """Base class that dispatches events to registered async handlers."""

    def __init__(self) -> None:
        self._event_handlers: dict[type[DomainEvent], AsyncEventHandler] = {}

    @property
    def handles(self) -> set[type[DomainEvent]]:
        """Return registered event types handled by this projection."""
        return set(self._event_handlers.keys())

    def add_handler(
        self,
        event_type: type[DomainEvent],
        handler: AsyncEventHandler,
    ) -> None:
        """Register an async handler for a specific event type."""
        self._event_handlers[event_type] = handler

    async def handle(self, event: DomainEvent) -> None:
        """Resolve and execute the mapped async handler for an event."""
        handler = self._event_handlers.get(type(event))

        if handler is None:
            # Fallback allows handlers registered for a parent event class.
            for event_type, candidate in self._event_handlers.items():
                if isinstance(event, event_type):
                    handler = candidate
                    break

        if handler is None:
            return

        await handler(event)
