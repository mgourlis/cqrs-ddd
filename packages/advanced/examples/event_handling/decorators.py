"""
Demonstrates the use of event handler decorators for metadata and validation.

Shows @aggregate_event_handler and @aggregate_event_handler_validator
to add metadata to handlers and configure validation at the aggregate level.
"""

from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
    EventSourcedAggregateMixin,
)
from cqrs_ddd_advanced_core.domain.event_handlers import (
    aggregate_event_handler,
    aggregate_event_handler_validator,
    get_event_handler_config,
    get_handler_event_type,
    is_aggregate_event_handler,
)
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidationConfig,
    EventValidator,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Define Domain Events ─────────────────────────────────────────────


class ProductCreated(DomainEvent):
    """Event emitted when a product is created."""

    product_id: str = ""
    name: str = ""
    price: float = 0.0


class ProductPriceChanged(DomainEvent):
    """Event emitted when product price changes."""

    product_id: str = ""
    old_price: float = 0.0
    new_price: float = 0.0


class ProductDiscontinued(DomainEvent):
    """Event emitted when a product is discontinued."""

    product_id: str = ""
    reason: str = ""


# ── Aggregate with Decorators ───────────────────────────────────────


@aggregate_event_handler_validator(enabled=True, strict=False)
class Product(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Product aggregate with decorated event handlers.

    Uses @aggregate_event_handler_validator to configure validation at the class level.
    Uses @aggregate_event_handler to add metadata to individual handler methods.
    """

    name: str = ""
    price: float = 0.0
    status: str = "active"

    @aggregate_event_handler()
    def apply_product_created(self, event: ProductCreated) -> None:
        """Handle ProductCreated event.

        The @aggregate_event_handler decorator marks this method as an event handler
        and adds metadata for validation and inspection.
        """
        self.name = event.name
        self.price = event.price
        self.status = "active"

    @aggregate_event_handler()
    def apply_product_price_changed(self, event: ProductPriceChanged) -> None:
        """Handle ProductPriceChanged event."""
        self.price = event.new_price

    @aggregate_event_handler()
    def apply_product_discontinued(self, _event: ProductDiscontinued) -> None:
        """Handle ProductDiscontinued event."""
        self.status = "discontinued"

    # Alternative handler name with explicit event type
    @aggregate_event_handler(event_type=ProductCreated)
    def on_creation(self, event: ProductCreated) -> None:
        """Alternative handler with explicit event type.

        Note: This would conflict with apply_ProductCreated since both
        handle the same event. In practice, you would use one or the other.
        """
        # This is just for demonstration - not actually called
        self.name = event.name


# ── Aggregate Without Decorators ─────────────────────────────────────


class SimpleProduct(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Product aggregate without decorators.

    Shows that decorators are optional - the mixin works fine without them.
    """

    name: str = ""
    price: float = 0.0
    status: str = "active"

    def apply_product_created(self, event: ProductCreated) -> None:
        """No decorator, but still works as a handler."""
        self.name = event.name
        self.price = event.price

    def apply_product_price_changed(self, event: ProductPriceChanged) -> None:
        """No decorator, but still works as a handler."""
        self.price = event.new_price


# ── Decorator Inspection Examples ────────────────────────────────────


def inspect_decorated_handlers() -> None:
    """Show how to inspect decorator metadata."""

    print("\n=== Inspecting Decorated Handlers ===")

    # Check if methods are marked as event handlers
    created_ok = is_aggregate_event_handler(Product.apply_product_created)
    print(f"apply_product_created is event handler: {created_ok}")
    price_ok = is_aggregate_event_handler(Product.apply_product_price_changed)
    print(f"apply_product_price_changed is event handler: {price_ok}")

    # Get event type from metadata (if explicitly set)
    event_type = get_handler_event_type(Product.on_creation)
    print(f"on_creation explicit event type: {event_type}")

    # Get class-level validation configuration
    config = get_event_handler_config(Product)
    if config:
        print(f"Product validation enabled: {config.enabled}")
        print(f"Product strict mode: {config.strict_mode}")

    # Simple product has no decorator metadata
    simple_config = get_event_handler_config(SimpleProduct)
    print(f"SimpleProduct has config: {simple_config is not None}")


# ── Usage Examples ───────────────────────────────────────────────────


def example_with_decorators() -> None:
    """Use aggregate with decorated handlers."""
    print("\n=== Using Decorated Aggregate ===")

    # Create product
    product = Product(id="prod-123")

    # Apply events using internal method
    create_event = ProductCreated(
        product_id="prod-123",
        name="Widget A",
        price=99.99,
    )
    product._apply_event_internal(create_event)
    print(f"After creation: {product.name}, ${product.price}, {product.status}")

    price_event = ProductPriceChanged(
        product_id="prod-123",
        old_price=99.99,
        new_price=89.99,
    )
    product._apply_event_internal(price_event)
    print(f"After price change: ${product.price}")

    discontinue_event = ProductDiscontinued(
        product_id="prod-123",
        reason="No longer manufactured",
    )
    product._apply_event_internal(discontinue_event)
    print(f"After discontinuation: {product.status}")


def example_without_decorators() -> None:
    """Use aggregate without decorators (they work fine!)."""
    print("\n=== Using Undecorated Aggregate ===")

    # Create product
    product = SimpleProduct(id="prod-456")

    # Apply events - decorators are optional
    create_event = ProductCreated(
        product_id="prod-456",
        name="Widget B",
        price=149.99,
    )
    product._apply_event_internal(create_event)
    print(f"After creation: {product.name}, ${product.price}")

    price_event = ProductPriceChanged(
        product_id="prod-456",
        old_price=149.99,
        new_price=129.99,
    )
    product._apply_event_internal(price_event)
    print(f"After price change: ${product.price}")


def example_validation_with_decorators() -> None:
    """Show how class-level validator decorator works."""
    print("\n=== Validation with Class Decorator ===")

    # Get validation config from class
    config = get_event_handler_config(Product)
    if config is not None:
        print(
            f"Validation config: enabled={config.enabled}, strict={config.strict_mode}"
        )

    # Create validator with same config
    validator = EventValidator(config or EventValidationConfig())

    # Test validation
    product = Product(id="prod-789")
    create_event = ProductCreated(
        product_id="prod-789",
        name="Widget C",
        price=199.99,
    )

    # Should pass validation (handler exists)
    validator.validate_handler_exists(product, create_event)
    print("✓ Validation passed for ProductCreated")

    # Test with non-existent event type
    from cqrs_ddd_advanced_core import MissingEventHandlerError

    class UnknownEvent(DomainEvent):
        event_id: str = ""

    unknown_event = UnknownEvent(event_id="test")

    try:
        validator.validate_handler_exists(product, unknown_event)
        print("✗ Validation should have failed!")
    except MissingEventHandlerError as e:
        print(f"✓ Validation failed as expected: {e.message}")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run all decorator examples."""
    inspect_decorated_handlers()
    example_with_decorators()
    example_without_decorators()
    example_validation_with_decorators()


if __name__ == "__main__":
    main()
