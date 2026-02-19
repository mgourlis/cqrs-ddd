"""
Demonstrates different validation modes for event handlers.

Shows lenient mode, strict mode, and disabled validation.
"""

from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
    EventSourcedAggregateMixin,
)
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidationConfig,
    EventValidator,
)
from cqrs_ddd_advanced_core.event_sourcing.loader import (
    DefaultEventApplicator,
)
from cqrs_ddd_advanced_core.exceptions import (
    MissingEventHandlerError,
    StrictValidationViolationError,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Define Domain Events ─────────────────────────────────────────────


class ItemCreated(DomainEvent):
    """Event emitted when an item is created."""

    item_id: str = ""
    name: str = ""


class ItemUpdated(DomainEvent):
    """Event emitted when an item is updated."""

    item_id: str = ""
    new_name: str = ""


class ItemDeleted(DomainEvent):
    """Event emitted when an item is deleted."""

    item_id: str = ""


# ── Define Aggregates for Different Modes ───────────────────────────


class ItemWithExactHandlers(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Item aggregate with exact handlers for all events."""

    name: str = ""
    status: str = "active"

    def apply_item_created(self, event: ItemCreated) -> None:
        """Handle ItemCreated event."""
        self.name = event.name
        self.status = "active"

    def apply_item_updated(self, event: ItemUpdated) -> None:
        """Handle ItemUpdated event."""
        self.name = event.new_name

    def apply_item_deleted(self, _event: ItemDeleted) -> None:
        """Handle ItemDeleted event."""
        self.status = "deleted"


class ItemWithFallback(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Item aggregate with only generic fallback handler."""

    name: str = ""
    status: str = "active"

    def apply_event(self, event: DomainEvent) -> None:
        """Generic fallback handler for all events."""
        event_type = type(event).__name__

        if event_type == "ItemCreated":
            self.name = getattr(event, "name", "")
            self.status = "active"
        elif event_type == "ItemUpdated":
            self.name = getattr(event, "new_name", "")
        elif event_type == "ItemDeleted":
            self.status = "deleted"


class ItemWithMixedHandlers(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Item aggregate with some exact handlers and a fallback."""

    name: str = ""
    status: str = "active"

    def apply_item_created(self, event: ItemCreated) -> None:
        """Exact handler for ItemCreated."""
        self.name = event.name
        self.status = "active"

    def apply_event(self, event: DomainEvent) -> None:
        """Generic fallback for other events."""
        event_type = type(event).__name__

        if event_type == "ItemUpdated":
            self.name = getattr(event, "new_name", "")
        elif event_type == "ItemDeleted":
            self.status = "deleted"


# ── Validation Mode Examples ───────────────────────────────────────


def example_lenient_mode() -> None:
    """Lenient mode allows both exact handlers and fallback."""
    print("\n=== Lenient Mode ===")

    # Configure lenient validator
    config = EventValidationConfig(
        enabled=True,
        strict_mode=False,
        allow_fallback_handler=True,
    )
    validator = EventValidator(config)
    applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
        validator=validator
    )

    # Test with exact handlers
    item1 = ItemWithExactHandlers(id="item-1")
    event1 = ItemCreated(item_id="item-1", name="Widget A")
    applicator.apply(item1, event1)
    print(f"Exact handler - Status: {item1.status}, Name: {item1.name}")

    # Test with fallback handler
    item2 = ItemWithFallback(id="item-2")
    event2 = ItemCreated(item_id="item-2", name="Widget B")
    applicator.apply(item2, event2)
    print(f"Fallback handler - Status: {item2.status}, Name: {item2.name}")

    # Test with mixed handlers
    item3 = ItemWithMixedHandlers(id="item-3")
    event3 = ItemCreated(item_id="item-3", name="Widget C")
    applicator.apply(item3, event3)
    print(f"Mixed handlers - Status: {item3.status}, Name: {item3.name}")


def example_strict_mode() -> None:
    """Strict mode requires exact handlers only."""
    print("\n=== Strict Mode ===")

    # Configure strict validator
    config = EventValidationConfig(
        enabled=True,
        strict_mode=True,
        allow_fallback_handler=False,
    )
    validator = EventValidator(config)
    applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
        validator=validator
    )

    # Test with exact handlers - should work
    item1 = ItemWithExactHandlers(id="item-1")
    event1 = ItemCreated(item_id="item-1", name="Widget A")
    applicator.apply(item1, event1)
    print(f"✓ Exact handler works - Status: {item1.status}, Name: {item1.name}")

    # Test with fallback handler - should fail
    item2 = ItemWithFallback(id="item-2")
    event2 = ItemCreated(item_id="item-2", name="Widget B")
    try:
        applicator.apply(item2, event2)
        print("✗ Fallback handler should have failed!")
    except StrictValidationViolationError as e:
        print(f"✓ Fallback handler rejected as expected: {str(e)}")

    # Test with mixed handlers - should fail for fallback
    item3 = ItemWithMixedHandlers(id="item-3")
    event3_created = ItemCreated(item_id="item-3", name="Widget C")
    event3_updated = ItemUpdated(item_id="item-3", new_name="Widget C Updated")
    applicator.apply(item3, event3_created)
    print(f"✓ Exact handler works - Status: {item3.status}, Name: {item3.name}")

    try:
        applicator.apply(item3, event3_updated)
        print("✗ Fallback should have failed!")
    except StrictValidationViolationError as e:
        print(f"✓ Fallback rejected as expected: {str(e)}")


def example_disabled_validation() -> None:
    """Disabled validation allows any handler configuration."""
    print("\n=== Disabled Validation ===")

    # Configure disabled validation
    config = EventValidationConfig(
        enabled=False,
    )
    validator = EventValidator(config)
    applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
        validator=validator
    )

    # All aggregates work without validation
    item1 = ItemWithExactHandlers(id="item-1")
    item2 = ItemWithFallback(id="item-2")
    item3 = ItemWithMixedHandlers(id="item-3")

    event = ItemCreated(item_id="test", name="Test Item")

    applicator.apply(item1, event)
    applicator.apply(item2, event)
    applicator.apply(item3, event)

    print("✓ All aggregates work without validation")
    print(f"  Exact handlers: {item1.status}, {item1.name}")
    print(f"  Fallback handler: {item2.status}, {item2.name}")
    print(f"  Mixed handlers: {item3.status}, {item3.name}")


def example_missing_handler_behavior() -> None:
    """Show behavior when handlers are missing."""
    print("\n=== Missing Handler Behavior ===")

    class IncompleteItem(AggregateRoot[str], EventSourcedAggregateMixin[str]):
        """Item with only some handlers."""

        name: str = ""

        def apply_item_created(self, event: ItemCreated) -> None:
            self.name = event.name

        # Missing apply_item_updated and apply_item_deleted

    # Test with raise_on_missing_handler=True (default)
    print("\nWith raise_on_missing_handler=True:")
    validator = EventValidator(EventValidationConfig(enabled=True))
    applicator: DefaultEventApplicator[IncompleteItem] = DefaultEventApplicator(
        validator=validator,
        raise_on_missing_handler=True,
    )

    item = IncompleteItem(id="item-1")
    created_event = ItemCreated(item_id="item-1", name="Widget")
    updated_event = ItemUpdated(item_id="item-1", new_name="Updated")

    applicator.apply(item, created_event)
    print(f"✓ ItemCreated handled: {item.name}")

    try:
        applicator.apply(item, updated_event)
        print("✗ Should have raised MissingEventHandlerError!")
    except MissingEventHandlerError as e:
        print(f"✓ MissingEventHandlerError raised: {str(e)}")

    # Test with raise_on_missing_handler=False
    print("\nWith raise_on_missing_handler=False:")
    applicator_no_raise: DefaultEventApplicator[IncompleteItem] = (
        DefaultEventApplicator(
            validator=validator,
            raise_on_missing_handler=False,
        )
    )

    item2 = IncompleteItem(id="item-2")
    applicator_no_raise.apply(item2, created_event)
    applicator_no_raise.apply(item2, updated_event)  # Silently ignored
    print(f"✓ Events applied (missing handler ignored): {item2.name}")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run all validation mode examples."""
    example_lenient_mode()
    example_strict_mode()
    example_disabled_validation()
    example_missing_handler_behavior()


if __name__ == "__main__":
    main()
