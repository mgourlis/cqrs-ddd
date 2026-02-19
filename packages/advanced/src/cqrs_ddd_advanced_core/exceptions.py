"""Exceptions for the advanced-core package."""

from cqrs_ddd_core.primitives.exceptions import (
    CQRSDDDError,
    DomainError,
    HandlerError,
    PersistenceError,
    ValidationError,
)

# ── Event handler exceptions (canonical definitions in domain.exceptions) ───
# Re-export for backward compatibility; internal code should use domain.exceptions.
from .domain.exceptions import (
    EventHandlerError,
    EventSourcedAggregateRequiredError,
    EventSourcingConfigurationError,
    InvalidEventHandlerError,
    MissingEventHandlerError,
    StrictValidationViolationError,
)


class HandlerNotRegisteredError(HandlerError, PersistenceError):
    """Raised when a persistence handler is requested but not registered."""


class SourceNotRegisteredError(PersistenceError):
    """Raised when a data source (e.g., UoW factory) is requested but not registered."""


class ResilienceError(PersistenceError):
    """Base exception for all resiliency-related errors."""


class MergeStrategyRegistryMissingError(ResilienceError):
    """Raised when a strategy is requested but no registry is provided."""


# ── Saga exceptions ─────────────────────────────────────────────────────


class SagaConfigurationError(ValidationError):
    """Raised when saga builder or orchestration configuration is invalid.

    E.g. invalid .on() args, TCC step names, duplicate events,
    on_tcc_begin called twice.
    """


class SagaStateError(CQRSDDDError):
    """Raised when saga is in an invalid state for the requested operation.

    E.g. no TCC steps registered, TCC already started, message_registry required.
    """


class SagaHandlerNotFoundError(HandlerError):
    """Raised when no event handler is registered for the received event type."""


# ── Background job exceptions ───────────────────────────────────────────


class JobStateError(DomainError):
    """Raised when a background job state machine transition is not allowed.

    E.g. cannot start/complete/fail/cancel in current state, max retries exceeded.
    """


__all__ = [
    "EventHandlerError",
    "EventSourcedAggregateRequiredError",
    "EventSourcingConfigurationError",
    "InvalidEventHandlerError",
    "MissingEventHandlerError",
    "StrictValidationViolationError",
    "HandlerNotRegisteredError",
    "JobStateError",
    "MergeStrategyRegistryMissingError",
    "ResilienceError",
    "SagaConfigurationError",
    "SagaHandlerNotFoundError",
    "SagaStateError",
    "SourceNotRegisteredError",
]
