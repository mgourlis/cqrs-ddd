"""Domain-specific exceptions for event sourcing and event handling."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import CQRSDDDError, ValidationError


class EventSourcingConfigurationError(ValidationError):
    """Raised when event sourcing or persistence orchestrator configuration is invalid.

    E.g. missing default_event_store, no event_store available for aggregate type,
    or orchestrator not provided when configuring mediator.
    """


class EventHandlerError(CQRSDDDError):
    """Base exception for event handler errors."""

    @property
    def message(self) -> str:
        """Get the exception message for compatibility."""
        return str(self)


class MissingEventHandlerError(EventHandlerError, AttributeError):
    """Raised when an aggregate has no handler for a specific event type.

    Also inherits from AttributeError for backward compatibility with
    code that expects AttributeError for missing handlers.
    """

    def __init__(
        self,
        aggregate_type: str,
        event_type: str,
    ) -> None:
        self.aggregate_type = aggregate_type
        self.event_type = event_type
        message = (
            f"Aggregate '{aggregate_type}' has no handler for event '{event_type}'. "
            f"Expected method: apply_{event_type}(event) or apply_<snake_case>(event)"
        )
        AttributeError.__init__(self, message)
        EventHandlerError.__init__(self, message)

    @property
    def message(self) -> str:
        """Get the exception message for compatibility."""
        return str(self)


class InvalidEventHandlerError(EventHandlerError):
    """Raised when an event handler method is invalid (signature/callable)."""


class StrictValidationViolationError(EventHandlerError):
    """Raised when strict validation mode is violated."""

    def __init__(
        self,
        aggregate_type: str,
        event_type: str,
        reason: str,
    ) -> None:
        self.aggregate_type = aggregate_type
        self.event_type = event_type
        self.reason = reason
        message = (
            f"Strict validation violation for {aggregate_type}.{event_type}: {reason}"
        )
        super().__init__(message)

    @property
    def message(self) -> str:
        """Get the exception message for compatibility."""
        return str(self)


class EventSourcedAggregateRequiredError(CQRSDDDError):
    """Raised when an event references an unregistered aggregate that should
    be event-sourced.

    **Data Integrity**: This exception prevents accidental data loss. If an
    aggregate produces events but is not registered as event-sourced, those
    events would be lost on transaction failure. This is prevented by requiring
    explicit registration.
    """

    def __init__(self, aggregate_type: str) -> None:
        self.aggregate_type = aggregate_type
        reg = f"orchestrator.register_event_sourced_type('{aggregate_type}')"
        lenient = "EventSourcedPersistenceOrchestrator(..., enforce_registration=False)"
        message = (
            f"DATA INTEGRITY: Aggregate type '{aggregate_type}' produces events "
            f"but is not registered as event-sourced. Events would be lost on "
            f"transaction failure. To fix:\n"
            f"  1. Register as event-sourced: {reg}\n"
            f"  2. Or mark as non-event-sourced: @non_event_sourced decorator\n"
            f"  3. Or use lenient mode: {lenient}"
        )
        super().__init__(message)

    @property
    def message(self) -> str:
        """Get the exception message for compatibility."""
        return str(self)
