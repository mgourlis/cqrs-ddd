"""
IEventApplicator — protocol for applying domain events to aggregates on replay.
IEventApplicable — protocol for aggregates that can handle domain events.
"""

from __future__ import annotations

from collections.abc import Callable  # noqa: TC003 - used in Protocol method signature
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

from cqrs_ddd_core.domain.aggregate import AggregateRoot

T = TypeVar("T", bound=AggregateRoot[Any])


@runtime_checkable
class IEventApplicator(Protocol[T]):
    """Port for applying a domain event to an aggregate during event-sourced replay.

    Implementations may dispatch by event type name (e.g. call
    ``aggregate.apply_OrderCreated(event)``) or use a single fold function.
    """

    def apply(self, aggregate: T, event: DomainEvent) -> T:
        """Apply the event to the aggregate and return the aggregate (possibly mutated).

        Args:
            aggregate: The aggregate instance to update.
            event: The domain event to apply.

        Returns:
            The same aggregate after applying the event (possibly mutated in place).
        """
        ...


@runtime_checkable
class IEventApplicable(Protocol):
    """Protocol for aggregates that handle domain events via apply_<EventType>.

    This protocol provides type safety and IDE support for aggregates that
    implement event handling methods. Validation utilities use it to check
    handler existence before applying events.

    Example:
        class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
            def apply_OrderCreated(self, event: OrderCreated) -> None:
                self.status = "created"

        # Order implements IEventApplicable
    """

    def has_handler_for_event(self, event_type: str) -> bool:
        """Check if the aggregate has a handler for a specific event type.

        Args:
            event_type: The name of the event type (e.g., "OrderCreated").

        Returns:
            True if apply_<event_type> or apply_event exists, False otherwise.
        """
        ...

    def get_handler_for_event(
        self, event_type: str
    ) -> Callable[[DomainEvent], None] | None:
        """Get the handler method for a specific event type, or None if not found.

        Args:
            event_type: The name of the event type (e.g., "OrderCreated").

        Returns:
            The apply_<event_type> or apply_event method, or None if not found.
        """
        ...
