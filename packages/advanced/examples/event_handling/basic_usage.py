"""
Basic usage of EventSourcedAggregateMixin for event handling.

This example shows the simplest way to add event handler support
to your aggregates using the mixin.
"""

from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
    EventSourcedAggregateMixin,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Define Domain Events ─────────────────────────────────────────────


class OrderCreated(DomainEvent):
    """Event emitted when an order is created."""

    order_id: str = ""
    amount: float = 0.0
    currency: str = "EUR"


class OrderPaid(DomainEvent):
    """Event emitted when an order is paid."""

    order_id: str = ""
    transaction_id: str = ""


class OrderCancelled(DomainEvent):
    """Event emitted when an order is cancelled."""

    order_id: str = ""
    reason: str = ""


# ── Define Aggregate with Mixin ───────────────────────────────────────


class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate with event handler support.

    Inherits from EventSourcedAggregateMixin to get helper methods
    for event handler introspection and validation.
    """

    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"

    def apply_order_created(self, event: OrderCreated) -> None:
        """Handle OrderCreated event."""
        self.status = "created"
        self.amount = event.amount
        self.currency = event.currency

    def apply_order_paid(self, _event: OrderPaid) -> None:
        """Handle OrderPaid event."""
        self.status = "paid"

    def apply_order_cancelled(self, _event: OrderCancelled) -> None:
        """Handle OrderCancelled event."""
        self.status = "cancelled"


# ── Usage Examples ───────────────────────────────────────────────────


def main() -> None:
    """Demonstrate basic event handler usage."""

    # Create an order
    order = Order(id="order-123")

    print(f"Initial status: {order.status}")

    # Check if handler exists
    print(
        f"Has handler for OrderCreated: {order.has_handler_for_event('OrderCreated')}"
    )
    print(f"Has handler for OrderPaid: {order.has_handler_for_event('OrderPaid')}")

    # Get handler and apply event
    handler = order.get_handler_for_event("OrderCreated")
    if handler:
        event = OrderCreated(
            order_id="order-123",
            amount=100.0,
            currency="EUR",
        )
        handler(event)
        print(f"After OrderCreated: {order.status}")
        print(f"Order amount: {order.amount} {order.currency}")

    # Apply another event
    paid_handler = order.get_handler_for_event("OrderPaid")
    if paid_handler:
        paid_event = OrderPaid(
            order_id="order-123",
            transaction_id="tx-456",
        )
        paid_handler(paid_event)
        print(f"After OrderPaid: {order.status}")

    # Get all supported event types
    supported = order._get_supported_event_types()
    print(f"Supported event types: {supported}")

    # Using internal apply method
    order2 = Order(id="order-456")
    cancel_event = OrderCancelled(
        order_id="order-456",
        reason="Customer request",
    )
    order2._apply_event_internal(cancel_event)
    print(f"Order2 status after cancellation: {order2.status}")


if __name__ == "__main__":
    main()
