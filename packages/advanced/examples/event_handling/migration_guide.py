"""
Migration guide for existing aggregates to use event handler formalization.

This guide shows how to migrate existing aggregates to use the new
event handler formalization features gradually, without breaking changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
    EventSourcedAggregateMixin,
)
from cqrs_ddd_advanced_core.domain.event_handlers import (
    aggregate_event_handler,
    aggregate_event_handler_validator,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Define Domain Events ─────────────────────────────────────────────


class InvoiceCreated(DomainEvent):
    """Event emitted when an invoice is created."""

    invoice_id: str = ""
    customer_id: str = ""
    amount: float = 0.0


class InvoicePaid(DomainEvent):
    """Event emitted when an invoice is paid."""

    invoice_id: str = ""
    payment_id: str = ""
    amount: float = 0.0


class InvoiceCancelled(DomainEvent):
    """Event emitted when an invoice is cancelled."""

    invoice_id: str = ""
    reason: str = ""


# ── Step 1: Existing Aggregate (No Changes) ──────────────────


class OldInvoice(AggregateRoot[str]):
    """Existing aggregate - no changes needed for backward compatibility."""

    customer_id: str = ""
    amount: float = 0.0
    status: str = "draft"

    def apply_invoice_created(self, event: InvoiceCreated) -> None:
        """Handle InvoiceCreated event."""
        self.customer_id = event.customer_id
        self.amount = event.amount
        self.status = "created"

    def apply_invoice_paid(self, _event: InvoicePaid) -> None:
        """Handle InvoicePaid event."""
        self.status = "paid"

    def apply_invoice_cancelled(self, _event: InvoiceCancelled) -> None:
        """Handle InvoiceCancelled event."""
        self.status = "cancelled"


# ── Step 2: Add Mixin for Introspection ───────────────────


class InvoiceWithMixin(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Add mixin for introspection - minimal changes.

    Benefits:
    - Can check if handlers exist: has_handler_for_event()
    - Can get handler methods: get_handler_for_event()
    - Can list supported events: _get_supported_event_types()
    """

    customer_id: str = ""
    amount: float = 0.0
    status: str = "draft"

    # Existing handlers - no changes needed!
    def apply_invoice_created(self, event: InvoiceCreated) -> None:
        """Handle InvoiceCreated event."""
        self.customer_id = event.customer_id
        self.amount = event.amount
        self.status = "created"

    def apply_invoice_paid(self, _event: InvoicePaid) -> None:
        """Handle InvoicePaid event."""
        self.status = "paid"

    def apply_invoice_cancelled(self, _event: InvoiceCancelled) -> None:
        """Handle InvoiceCancelled event."""
        self.status = "cancelled"


# ── Step 3: Add Class-Level Validation Config ───────────────────


@aggregate_event_handler_validator(enabled=True, strict=False)
class InvoiceWithValidation(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Add validation configuration - one-line change at class level.

    Benefits:
    - Runtime validation catches missing handlers early
    - Configurable strict/lenient mode
    - Clear error messages for debugging
    """

    customer_id: str = ""
    amount: float = 0.0
    status: str = "draft"

    # Existing handlers - no changes needed!
    def apply_invoice_created(self, event: InvoiceCreated) -> None:
        """Handle InvoiceCreated event."""
        self.customer_id = event.customer_id
        self.amount = event.amount
        self.status = "created"

    def apply_invoice_paid(self, _event: InvoicePaid) -> None:
        """Handle InvoicePaid event."""
        self.status = "paid"

    def apply_invoice_cancelled(self, _event: InvoiceCancelled) -> None:
        """Handle InvoiceCancelled event."""
        self.status = "cancelled"


# ── Step 4: Add Method-Level Decorators (Optional) ─────────────


@aggregate_event_handler_validator(enabled=True, strict=False)
class InvoiceWithDecorators(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Add decorators for documentation and metadata.

    Benefits:
    - Documentation through metadata
    - IDE support for event handlers
    - Explicit intent marking
    """

    customer_id: str = ""
    amount: float = 0.0
    status: str = "draft"

    @aggregate_event_handler()
    def apply_invoice_created(self, event: InvoiceCreated) -> None:
        """Handle InvoiceCreated event."""
        self.customer_id = event.customer_id
        self.amount = event.amount
        self.status = "created"

    @aggregate_event_handler()
    def apply_invoice_paid(self, _event: InvoicePaid) -> None:
        """Handle InvoicePaid event."""
        self.status = "paid"

    @aggregate_event_handler()
    def apply_invoice_cancelled(self, _event: InvoiceCancelled) -> None:
        """Handle InvoiceCancelled event."""
        self.status = "cancelled"


# ── Step 5: Full Migration with Strict Mode ───────────────────────


@aggregate_event_handler_validator(enabled=True, strict=True)
class ModernInvoice(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Fully migrated aggregate with all features.

    Benefits:
    - Strict validation ensures exact handlers
    - Introspection capabilities
    - Clear documentation
    - Production safety
    """

    customer_id: str = ""
    amount: float = 0.0
    status: str = "draft"

    @aggregate_event_handler()
    def apply_invoice_created(self, event: InvoiceCreated) -> None:
        """Handle InvoiceCreated event."""
        self.customer_id = event.customer_id
        self.amount = event.amount
        self.status = "created"

    @aggregate_event_handler()
    def apply_invoice_paid(self, _event: InvoicePaid) -> None:
        """Handle InvoicePaid event."""
        self.status = "paid"

    @aggregate_event_handler()
    def apply_invoice_cancelled(self, _event: InvoiceCancelled) -> None:
        """Handle InvoiceCancelled event."""
        self.status = "cancelled"


# ── Migration Examples ───────────────────────────────────────────────


def example_backward_compatibility() -> None:
    """Show that old aggregates still work without changes."""
    print("\n=== Step 1: Backward Compatibility ===")
    print("Existing aggregates work without any changes!")

    old_invoice = OldInvoice(id="inv-001")
    event = InvoiceCreated(
        invoice_id="inv-001",
        customer_id="customer-123",
        amount=1000.0,
    )

    # Apply event using DefaultEventApplicator (still works!)
    from cqrs_ddd_advanced_core.event_sourcing.loader import (
        DefaultEventApplicator,
    )

    applicator: DefaultEventApplicator[OldInvoice] = DefaultEventApplicator()
    applicator.apply(old_invoice, event)

    print(f"✓ Old aggregate works: {old_invoice.status}")
    print(f"  Customer: {old_invoice.customer_id}")
    print(f"  Amount: ${old_invoice.amount}")


def example_add_mixin() -> None:
    """Show benefit of adding mixin with minimal changes."""
    print("\n=== Step 2: Add Mixin ===")
    print("Just add EventSourcedAggregateMixin to inheritance - no handler changes!")

    invoice = InvoiceWithMixin(id="inv-002")

    # New capabilities from mixin
    print(f"Supported events: {invoice._get_supported_event_types()}")
    print(
        f"Has InvoiceCreated handler: {invoice.has_handler_for_event('InvoiceCreated')}"
    )

    # Still works with existing handlers
    event = InvoiceCreated(
        invoice_id="inv-002",
        customer_id="customer-456",
        amount=1500.0,
    )
    invoice._apply_event_internal(event)

    print(f"✓ Aggregate with mixin works: {invoice.status}")


def example_add_validation() -> None:
    """Show benefit of adding validation configuration."""
    print("\n=== Step 3: Add Validation ===")
    print("Add @event_handler_validator decorator - one line at class level!")

    invoice = InvoiceWithValidation(id="inv-003")

    # Get validation configuration
    from cqrs_ddd_advanced_core.domain.event_handlers import (
        get_event_handler_config,
    )

    config = get_event_handler_config(InvoiceWithValidation)
    if config:
        print(f"Validation enabled: {config.enabled}")
        print(f"Strict mode: {config.strict_mode}")

    # Still works with existing handlers
    event = InvoiceCreated(
        invoice_id="inv-003",
        customer_id="customer-789",
        amount=2000.0,
    )
    invoice._apply_event_internal(event)

    print(f"✓ Aggregate with validation works: {invoice.status}")


def example_add_decorators() -> None:
    """Show benefit of adding method decorators."""
    print("\n=== Step 4: Add Method Decorators ===")
    print("Add @event_handler decorators for documentation - optional!")

    invoice = InvoiceWithDecorators(id="inv-004")

    # Check decorator metadata
    from cqrs_ddd_advanced_core.domain.event_handlers import (
        is_aggregate_event_handler,
    )

    created_decorated = is_aggregate_event_handler(
        InvoiceWithDecorators.apply_invoice_created
    )
    print(f"apply_invoice_created is decorated: {created_decorated}")

    # Still works with existing handlers
    event = InvoiceCreated(
        invoice_id="inv-004",
        customer_id="customer-012",
        amount=2500.0,
    )
    invoice._apply_event_internal(event)

    print(f"✓ Aggregate with decorators works: {invoice.status}")


def example_full_migration() -> None:
    """Show fully migrated aggregate."""
    print("\n=== Step 5: Full Migration ===")
    print("All features enabled - strict mode, validation, decorators!")

    invoice = ModernInvoice(id="inv-005")

    # Show all features
    print(f"Introspection: {invoice._get_supported_event_types()}")
    print(f"Has InvoiceCreated: {invoice.has_handler_for_event('InvoiceCreated')}")

    from cqrs_ddd_advanced_core.domain.event_handlers import (
        get_event_handler_config,
        is_aggregate_event_handler,
    )

    config = get_event_handler_config(ModernInvoice)
    if config is not None:
        print(f"Validation: enabled={config.enabled}, strict={config.strict_mode}")
    print(
        f"Decorated: {is_aggregate_event_handler(ModernInvoice.apply_invoice_created)}"
    )

    # Apply events
    events = [
        InvoiceCreated(invoice_id="inv-005", customer_id="customer-345", amount=3000.0),
        InvoicePaid(invoice_id="inv-005", payment_id="pay-123", amount=3000.0),
    ]

    for event in events:
        invoice._apply_event_internal(event)
        print(f"After {type(event).__name__}: {invoice.status}")


def example_gradual_migration() -> None:
    """Show gradual migration approach for large codebases."""
    if TYPE_CHECKING:
        from collections.abc import Sequence
        from typing import Any

    print("\n=== Gradual Migration Strategy ===")
    print("Migrate aggregates incrementally based on priority:")

    migration_steps: Sequence[tuple[str, Sequence[type[Any]]]] = [
        ("High Priority - Financial", [ModernInvoice]),
        ("Medium Priority - Orders", [InvoiceWithValidation]),
        ("Low Priority - Legacy", [OldInvoice]),
    ]

    for priority, aggregates in migration_steps:
        print(f"\n{priority}:")
        for agg_cls in aggregates:
            print(f"  - {agg_cls.__name__}")

    print("\nRecommended approach:")
    print("1. Start with critical aggregates (financial, security)")
    print("2. Add mixin first (Step 2)")
    print("3. Add validation config (Step 3)")
    print("4. Add decorators for new handlers (Step 4)")
    print("5. Gradually migrate to strict mode (Step 5)")


def example_migration_checklist() -> None:
    """Provide a checklist for migration."""
    print("\n=== Migration Checklist ===")

    checklist = [
        ("✓", "Identify aggregates to migrate"),
        (" ", "Add EventSourcedAggregateMixin to inheritance"),
        (" ", "Add @event_handler_validator decorator"),
        (" ", "Test with lenient mode first"),
        (" ", "Add @event_handler to methods"),
        (" ", "Enable strict mode for critical aggregates"),
        (" ", "Update documentation"),
        (" ", "Run tests to ensure backward compatibility"),
        (" ", "Monitor for missing handler errors"),
    ]

    print("\nPre-Migration:")
    for i, (status, item) in enumerate(checklist[:2], 1):
        print(f"  [{i}] [{status}] {item}")

    print("\nStep 1 - Add Mixin:")
    for i, (status, item) in enumerate(checklist[2:4], 3):
        print(f"  [{i}] [{status}] {item}")

    print("\nStep 2 - Add Validation:")
    for i, (status, item) in enumerate(checklist[4:6], 5):
        print(f"  [{i}] [{status}] {item}")

    print("\nStep 3 - Full Migration:")
    for i, (status, item) in enumerate(checklist[6:], 7):
        print(f"  [{i}] [{status}] {item}")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run all migration examples."""
    print("=" * 60)
    print("Event Handler Formalization - Migration Guide")
    print("=" * 60)

    print("\nThis guide shows how to migrate existing aggregates")
    print("to use the new event handler formalization features.")
    print("All steps are backward compatible!")

    example_backward_compatibility()
    example_add_mixin()
    example_add_validation()
    example_add_decorators()
    example_full_migration()
    example_gradual_migration()
    example_migration_checklist()

    print("\n" + "=" * 60)
    print("Migration guide completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
