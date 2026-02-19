"""
Demonstrates error handling for event handlers.

Shows how to handle MissingEventHandlerError, StrictValidationViolationError,
and other event handler errors gracefully.
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
    EventHandlerError,
    MissingEventHandlerError,
    StrictValidationViolationError,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Define Domain Events ─────────────────────────────────────────────


class TaskCreated(DomainEvent):
    """Event emitted when a task is created."""

    task_id: str = ""
    title: str = ""
    priority: str = "medium"


class TaskAssigned(DomainEvent):
    """Event emitted when a task is assigned."""

    task_id: str = ""
    assignee: str = ""


class TaskCompleted(DomainEvent):
    """Event emitted when a task is completed."""

    task_id: str = ""
    completed_at: str = ""


class TaskFailed(DomainEvent):
    """Event emitted when a task fails."""

    task_id: str = ""
    failure_reason: str = ""


# ── Define Aggregates ───────────────────────────────────────────────


class StrictTask(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Task aggregate with exact handlers only (no fallback)."""

    title: str = ""
    status: str = "pending"
    assignee: str = ""

    def apply_task_created(self, event: TaskCreated) -> None:
        """Handle TaskCreated event."""
        self.title = event.title
        self.status = "in_progress"

    def apply_task_assigned(self, event: TaskAssigned) -> None:
        """Handle TaskAssigned event."""
        self.assignee = event.assignee

    def apply_task_completed(self, _event: TaskCompleted) -> None:
        """Handle TaskCompleted event."""
        self.status = "completed"


class FlexibleTask(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Task aggregate with fallback handler."""

    title: str = ""
    status: str = "pending"
    assignee: str = ""

    def apply_event(self, event: DomainEvent) -> None:
        """Generic fallback for other events."""
        event_type = type(event).__name__

        if event_type == "TaskAssigned":
            self.assignee = getattr(event, "assignee", "")
        elif event_type == "TaskCompleted":
            self.status = "completed"
        elif event_type == "TaskFailed":
            self.status = "failed"


# ── Error Handling Examples ───────────────────────────────────────


def handle_missing_handler_error(task: AggregateRoot[str], event: DomainEvent) -> None:
    """Handle MissingEventHandlerError gracefully."""
    print("\n--- Handling Missing Handler Error ---")

    try:
        validator = EventValidator(EventValidationConfig(enabled=True))
        applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
            validator=validator
        )
        applicator.apply(task, event)
    except MissingEventHandlerError as e:
        print("❌ MissingEventHandlerError caught!")
        print(f"   Aggregate: {e.aggregate_type}")
        print(f"   Event: {e.event_type}")
        print(f"   Expected method: apply_{e.event_type}")
        print("\n   Recovery options:")
        print(f"   1. Add apply_{e.event_type}() method to {e.aggregate_type}")
        print("   2. Add apply_event() fallback handler")
        print("   3. Disable validation (not recommended)")


def handle_strict_violation_error(task: AggregateRoot[str], event: DomainEvent) -> None:
    """Handle StrictValidationViolationError gracefully."""
    print("\n--- Handling Strict Violation Error ---")

    try:
        validator = EventValidator(
            EventValidationConfig(enabled=True, strict_mode=True)
        )
        applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
            validator=validator
        )
        applicator.apply(task, event)
    except StrictValidationViolationError as e:
        print("❌ StrictValidationViolationError caught!")
        print(f"   Aggregate: {e.aggregate_type}")
        print(f"   Event: {e.event_type}")
        print(f"   Reason: {e.reason}")
        print("\n   Recovery options:")
        print(f"   1. Add apply_{e.event_type}() exact handler to {e.aggregate_type}")
        print("   2. Disable strict mode (allow fallback handler)")
        print("   3. Configure strict mode with allow_fallback_handler=True")


def handle_event_handler_error_generic(
    task: AggregateRoot[str], event: DomainEvent
) -> None:
    """Handle any EventHandlerError using base class."""
    print("\n--- Handling Generic Event Handler Error ---")

    try:
        validator = EventValidator(
            EventValidationConfig(enabled=True, strict_mode=True)
        )
        applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
            validator=validator
        )
        applicator.apply(task, event)
    except EventHandlerError as e:
        print("❌ EventHandlerError caught!")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Message: {str(e)}")

        # Check specific error type
        if isinstance(e, MissingEventHandlerError):
            print(f"   Specific: Handler missing for {e.event_type}")
        elif isinstance(e, StrictValidationViolationError):
            print(f"   Specific: Strict violation - {e.reason}")
        else:
            print("   Specific: Unknown error type")


def safe_apply_event(
    task: AggregateRoot[str],
    event: DomainEvent,
    validator: EventValidator | None = None,
) -> bool:
    """Safely apply an event with comprehensive error handling.

    Returns True if event was applied successfully, False otherwise.
    """
    if validator is None:
        validator = EventValidator(
            EventValidationConfig(enabled=True, strict_mode=False)
        )

    applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
        validator=validator
    )

    try:
        applicator.apply(task, event)
        return True
    except MissingEventHandlerError as e:
        print(f"⚠️  Cannot apply {type(event).__name__}: {str(e)}")
        print(f"   Task ID: {task.id}")
        return False
    except StrictValidationViolationError as e:
        print(f"⚠️  Strict validation failed for {type(event).__name__}: {str(e)}")
        print(f"   Reason: {e.reason}")
        return False
    except EventHandlerError as e:
        print(f"⚠️  Event handler error: {str(e)}")
        return False
    except Exception as e:  # noqa: BLE001 - demo: catch any unexpected error
        print(f"⚠️  Unexpected error: {e}")
        return False


def example_graceful_degradation() -> None:
    """Show graceful degradation when handlers are missing."""
    print("\n=== Graceful Degradation Example ===")

    # Scenario: Try to apply event to incomplete aggregate
    incomplete_task = StrictTask(id="task-incomplete")
    assigned_event = TaskAssigned(task_id="task-incomplete", assignee="jane.doe")

    if not safe_apply_event(incomplete_task, assigned_event):
        print("\nEvent application failed, degrading gracefully...")
        print("Option 1: Add missing handler")
        print("Option 2: Use flexible aggregate with fallback")
        print("Option 3: Disable validation")

    # Option 1: Dynamically add handler (not recommended, but possible)
    def dynamic_apply_task_assigned(self: StrictTask, event: TaskAssigned) -> None:
        self.assignee = event.assignee

    StrictTask.apply_task_assigned = dynamic_apply_task_assigned  # type: ignore[method-assign]

    print("\nRetrying with dynamically added handler...")
    if safe_apply_event(incomplete_task, assigned_event):
        print("✓ Dynamic handler worked!")
        print(f"   Status: {incomplete_task.status}")


def example_strict_vs_lenient() -> None:
    """Compare strict and lenient validation behavior."""
    print("\n=== Strict vs Lenient Validation ===")

    # Test with exact handlers - should work in both modes
    strict_task = StrictTask(id="task-strict")
    created_event = TaskCreated(task_id="task-strict", title="Setup database")

    # Lenient validation
    print("\n--- Lenient Validation ---")
    validator = EventValidator(
        EventValidationConfig(
            enabled=True, strict_mode=False, allow_fallback_handler=True
        )
    )
    lenient_applicator: DefaultEventApplicator[AggregateRoot[str]] = (
        DefaultEventApplicator(validator=validator)
    )
    lenient_applicator.apply(strict_task, created_event)
    print(f"✓ Lenient mode works - Status: {strict_task.status}")

    # Strict validation - should also work (exact handler exists)
    print("\n--- Strict Validation ---")
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))
    strict_applicator: DefaultEventApplicator[AggregateRoot[str]] = (
        DefaultEventApplicator(validator=validator)
    )
    strict_applicator.apply(strict_task, created_event)
    print(f"✓ Strict mode works - Status: {strict_task.status}")


def example_validation_with_fallback() -> None:
    """Test validation behavior with fallback handlers."""
    print("\n=== Validation with Fallback Handler ===")

    # Configure lenient validator (allows fallback)
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
    item1 = StrictTask(id="task-1")
    event1 = TaskCreated(task_id="task-1", title="Widget A")
    applicator.apply(item1, event1)
    print(f"✓ Exact handler works - Status: {item1.status}")

    # Test with fallback handler - should work in lenient mode
    item2 = FlexibleTask(id="task-2")
    event2 = TaskCreated(task_id="task-2", title="Widget B")
    applicator.apply(item2, event2)
    print(f"✓ Fallback handler works - Status: {item2.status}")


def example_strict_mode_rejects_fallback() -> None:
    """Show strict mode rejecting fallback handler."""
    print("\n=== Strict Mode Rejects Fallback ===")

    # Configure strict validator (no fallback)
    config = EventValidationConfig(
        enabled=True,
        strict_mode=True,
        allow_fallback_handler=False,
    )
    validator = EventValidator(config)
    applicator: DefaultEventApplicator[AggregateRoot[str]] = DefaultEventApplicator(
        validator=validator
    )

    # Test with fallback handler - should fail
    flexible_task = FlexibleTask(id="task-flexible")
    failed_event = TaskFailed(task_id="task-flexible", failure_reason="Database error")

    try:
        applicator.apply(flexible_task, failed_event)
        print("✗ Fallback handler should have failed!")
    except StrictValidationViolationError as e:
        print(f"✓ Fallback handler rejected as expected: {str(e)}")


def example_error_recovery() -> None:
    """Show how to recover from handler errors."""
    print("\n=== Error Recovery Example ===")

    # Scenario: Try to apply event, catch error, and recover
    task = StrictTask(id="task-recover")
    failed_event = TaskFailed(task_id="task-recover", failure_reason="Timeout")

    print("Attempting to apply TaskFailed event to strict Task aggregate...")
    if not safe_apply_event(task, failed_event):
        print("\nRecovering from error...")
        print("Option 1: Add handler manually")

        # Option 1: Dynamically add handler (not recommended, but possible)
        def dynamic_apply_task_failed(self: StrictTask, _event: TaskFailed) -> None:
            self.status = "failed"

        StrictTask.apply_task_failed = dynamic_apply_task_failed  # type: ignore[attr-defined]

        print("Retrying with new handler...")
        if safe_apply_event(task, failed_event):
            print("✓ Recovery successful!")
            print(f"   Status: {task.status}")

        print("\nOption 2: Use fallback handler (better approach)")
        task2 = FlexibleTask(id="task-recover-2")
        if safe_apply_event(task2, failed_event):
            print("✓ Recovery successful!")
            print(f"   Status: {task2.status}")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run all error handling examples."""
    print("=" * 60)
    print("Event Handler Error Handling Examples")
    print("=" * 60)

    # Example 1: Missing handler error
    incomplete_task = StrictTask(id="task-1")
    assigned_event = TaskAssigned(task_id="task-1", assignee="jane.doe")
    handle_missing_handler_error(incomplete_task, assigned_event)

    # Example 2: Strict violation error
    strict_task = StrictTask(id="task-2")
    failed_event = TaskFailed(task_id="task-2", failure_reason="System error")
    handle_strict_violation_error(strict_task, failed_event)

    # Example 3: Generic error handling
    generic_task = StrictTask(id="task-3")
    completed_event = TaskCompleted(
        task_id="task-3", completed_at="2026-02-18T10:00:00Z"
    )
    handle_event_handler_error_generic(generic_task, completed_event)

    # Example 4: Graceful degradation
    example_graceful_degradation()

    # Example 5: Strict vs lenient validation
    example_strict_vs_lenient()

    # Example 6: Validation with fallback handler
    example_validation_with_fallback()

    # Example 7: Strict mode rejects fallback
    example_strict_mode_rejects_fallback()

    # Example 8: Error recovery
    example_error_recovery()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
