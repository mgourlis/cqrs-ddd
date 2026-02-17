from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Generic,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from ..domain.events import DomainEvent

E = TypeVar("E", bound="DomainEvent")
E_contra = TypeVar("E_contra", bound="DomainEvent", contravariant=True)


class EventHandlerProtocol(Protocol[E_contra]):
    """
    Protocol for handler objects with a handle(event) method.

    Contravariant TypeVar ensures proper Liskov substitution:
    a handler for a supertype can be used where a handler for
    a subtype is expected.
    """

    def handle(self, event: E_contra) -> Awaitable[None] | None:
        ...


class EventHandlerCallable(Protocol[E_contra]):
    def __call__(self, event: E_contra) -> Awaitable[None] | None:
        ...


EventHandler: TypeAlias = EventHandlerCallable[E] | EventHandlerProtocol[E]


@runtime_checkable
class IEventDispatcher(Protocol, Generic[E]):
    """Protocol for local event dispatching."""

    def register(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """Register a local handler for a specific event type."""
        ...

    async def dispatch(self, events: list[DomainEvent]) -> None:
        """Dispatch events to all registered local handlers."""
        ...

    def clear(self) -> None:
        """Remove all handler registrations."""
        ...
