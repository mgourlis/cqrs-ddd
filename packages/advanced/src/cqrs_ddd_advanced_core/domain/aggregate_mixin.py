"""Event-sourced aggregate mixin for event handler support.

Provides helper methods for aggregates that handle domain events.
Complements the core AggregateRootMixin with event-specific utilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.domain.events import DomainEvent

from cqrs_ddd_advanced_core.ports.event_applicator import IEventApplicable

T_ID = TypeVar("T_ID", bound=str | int | Any)


class EventSourcedAggregateMixin(Generic[T_ID]):
    """Mixin providing helper methods for event-sourced aggregates.

    This mixin implements IEventApplicable and provides introspection
    utilities for event handler methods. It composes with the core
    AggregateRootMixin to provide full event-sourcing capabilities.

    Example:
        from cqrs_ddd_core.domain.aggregate import AggregateRoot
        from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
            EventSourcedAggregateMixin,
        )

        class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
            status: str = "pending"

            def apply_OrderCreated(self, event: OrderCreated) -> None:
                self.status = "created"

            def apply_OrderPaid(self, event: OrderPaid) -> None:
                self.status = "paid"

        # Use introspection
        order = Order(id="1")
        order.has_handler_for_event("OrderCreated")  # True
        order.get_handler_for_event("OrderCreated")  # apply_* method
        order.get_supported_event_types()  # {"OrderCreated", "OrderPaid"}
    """

    def has_handler_for_event(self, event_type: str) -> bool:
        """Check if aggregate has a handler for a specific event type.

        Checks for apply_<event_type> method first, then apply_event fallback.

        Args:
            event_type: The name of the event type (e.g., "OrderCreated").

        Returns:
            True if apply_<event_type> or apply_event exists, False otherwise.
        """
        # Check for exact handler (PascalCase or snake_case for ruff compliance)
        from .event_validation import event_type_to_snake

        event_type_snake = event_type_to_snake(event_type)
        if hasattr(self, f"apply_{event_type}") or hasattr(
            self, f"apply_{event_type_snake}"
        ):
            return True

        # Check for fallback handler
        return hasattr(self, "apply_event")

    def get_handler_for_event(
        self, event_type: str
    ) -> Callable[[DomainEvent], None] | None:
        """Get the handler method for a specific event type, or None if not found.

        Returns the apply_<event_type> method if it exists and is callable.
        Falls back to the apply_event method if no exact handler exists.

        Args:
            event_type: The name of the event type (e.g., "OrderCreated").

        Returns:
            The apply_<event_type> method, apply_event fallback, or None.
        """
        # Try exact handler first (PascalCase, then snake_case for ruff compliance)
        from .event_validation import event_type_to_snake

        method = getattr(self, f"apply_{event_type}", None)
        if method is None or not callable(method):
            event_type_snake = event_type_to_snake(event_type)
            method = getattr(self, f"apply_{event_type_snake}", None)
        if method is not None and callable(method):
            return cast("Callable[[DomainEvent], None]", method)

        # Try fallback handler
        method = getattr(self, "apply_event", None)
        if method is not None and callable(method):
            return cast("Callable[[DomainEvent], None]", method)

        return None

    def _get_supported_event_types(self) -> set[str]:
        """Return set of event type names this aggregate can handle.

        Scans the class for all apply_<EventType> methods and returns
        the event type names (without the "apply_" prefix).

        Returns:
            Set of event type names that this aggregate can handle.
        """
        supported: set[str] = set()

        # Get all attributes from the instance and its classes
        for name in dir(self):
            if name.startswith("apply_") and name != "apply_event":
                # Extract event type name
                event_type = name.removeprefix("apply_")
                # Check if it's callable
                method = getattr(self, name, None)
                if method is not None and callable(method):
                    supported.add(event_type)

        # Include apply_event fallback as special marker
        if hasattr(self, "apply_event"):
            method = getattr(self, "apply_event", None)
            if method is not None and callable(method):
                # Add a marker for generic fallback
                supported.add("*")

        return supported

    def _apply_event_internal(self, event: DomainEvent) -> None:
        """Internal method to apply an event using the handler resolution strategy.

        This method is used by EventSourcedLoader and other components
        that need to apply events to the aggregate. It follows the same
        resolution strategy as DefaultEventApplicator.

        Args:
            event: The domain event to apply.

        Raises:
            MissingEventHandlerError: If no handler exists for the event.
        """
        event_type = type(event).__name__

        # Get handler using mixin method
        handler = self.get_handler_for_event(event_type)

        if handler is None:
            # Import here to avoid circular dependency
            from .exceptions import MissingEventHandlerError

            raise MissingEventHandlerError(
                aggregate_type=type(self).__name__,
                event_type=event_type,
            )

        # Call the handler
        handler(event)


# Register that EventSourcedAggregateMixin implements IEventApplicable
# This is for type checking - the actual implementation is above
IEventApplicable.register(EventSourcedAggregateMixin)
