"""Domain-level utilities for event-sourced aggregates and aggregate event handling."""

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
from cqrs_ddd_advanced_core.domain.exceptions import (
    EventHandlerError,
    InvalidEventHandlerError,
    MissingEventHandlerError,
    StrictValidationViolationError,
)

__all__ = [
    # Mixin
    "EventSourcedAggregateMixin",
    # Decorators
    "aggregate_event_handler",
    "aggregate_event_handler_validator",
    "get_event_handler_config",
    "get_handler_event_type",
    "is_aggregate_event_handler",
    # Validation
    "EventValidationConfig",
    "EventValidator",
    # Exceptions
    "EventHandlerError",
    "InvalidEventHandlerError",
    "MissingEventHandlerError",
    "StrictValidationViolationError",
]
