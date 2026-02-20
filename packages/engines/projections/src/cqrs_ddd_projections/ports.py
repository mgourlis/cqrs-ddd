"""Protocols for projection engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent


@runtime_checkable
class IProjectionHandler(Protocol):
    """Protocol for a single projection handler: handle(event)
    and declares which events it handles."""

    handles: set[type[DomainEvent]]

    async def handle(self, event: DomainEvent) -> None:
        """Process one domain event (update read model)."""
        ...


@runtime_checkable
class ICheckpointStore(Protocol):
    """Protocol for persisting projection position
    (e.g. last processed event index or broker offset)."""

    async def get_position(self, projection_name: str) -> int | None:
        """Return last processed position; None if never run."""
        ...

    async def save_position(self, projection_name: str, position: int) -> None:
        """Persist position after a batch."""
        ...


@runtime_checkable
class IProjectionRegistry(Protocol):
    """Maps event types to handlers; supports multiple handlers per event."""

    def get_handlers(self, event_type: str) -> list[Any]:
        """Return list of handlers for this event type."""
        ...

    def register(self, handler: IProjectionHandler) -> None:
        """Register a handler (its .handles defines event types)."""
        ...
