"""Event handler validation utilities for event-sourced aggregates.

Provides configurable validation for event handler existence and correctness.
Validation can be enabled/disabled per-environment for performance control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .exceptions import (
    MissingEventHandlerError,
    StrictValidationViolationError,
)


def event_type_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case (e.g. OrderCreated -> order_created).

    Use for ruff-compliant handler names: apply_order_created instead of
    apply_OrderCreated. The framework tries both apply_<EventType> and
    apply_<snake_case>.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot
    from cqrs_ddd_core.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class EventValidationConfig:
    """Configuration for event handler validation.

    Attributes:
        enabled: Whether validation is enabled. If False, no validation occurs.
        strict_mode: If True, requires exact apply_<EventType> methods.
        allow_fallback_handler: If True, allow generic apply_event. When
            strict_mode=False, DefaultEventApplicator overrides to True.
            When strict_mode=True, defaults to False (no fallback).
    """

    enabled: bool = True
    strict_mode: bool = False
    allow_fallback_handler: bool = False


class EventValidator:
    """Validator for event handler existence and correctness.

    This validator checks that aggregates have appropriate handlers
    for events before attempting to apply them. It supports both
    strict and lenient validation modes.

    Example:
        # Strict mode - requires exact apply_<EventType> methods
        strict_validator = EventValidator(EventValidationConfig(
            enabled=True,
            strict_mode=True,
        ))

        # Lenient mode - allows apply_event fallback
        lenient_validator = EventValidator(EventValidationConfig(
            enabled=True,
            strict_mode=False,
        ))

        # Disabled - no validation (performance mode)
        no_validation = EventValidator(EventValidationConfig(
            enabled=False,
        ))
    """

    def __init__(self, config: EventValidationConfig | None = None) -> None:
        """Initialize the validator with configuration.

        Args:
            config: Validation configuration. Defaults to enabled lenient mode.
        """
        self._config = config or EventValidationConfig()

    def validate_handler_exists(
        self, aggregate: AggregateRoot[Any], event: DomainEvent
    ) -> None:
        """Validate that aggregate has a handler for this event type.

        Checks for apply_<EventType> method first, then apply_event fallback
        (if allowed by configuration). Raises appropriate errors if no handler found.

        Args:
            aggregate: The aggregate to validate.
            event: The event to find a handler for.

        Raises:
            MissingEventHandlerError: If no handler exists and validation is enabled.
            StrictValidationViolationError: If strict mode and only fallback exists.
            EventHandlerError: For other validation errors.
        """
        if not self._config.enabled:
            return

        event_type = type(event).__name__
        aggregate_type = type(aggregate).__name__

        # Check for exact handler (PascalCase or snake_case for ruff compliance)
        event_type_snake = event_type_to_snake(event_type)
        has_exact = hasattr(aggregate, f"apply_{event_type}") or hasattr(
            aggregate, f"apply_{event_type_snake}"
        )

        # Check for fallback handler
        has_fallback = hasattr(aggregate, "apply_event")

        # Determine if validation passes
        if self._config.strict_mode:
            # Strict mode: require exact handler (unless fallback explicitly allowed)
            if not has_exact:
                # Check if fallback is allowed in strict mode
                fallback_allowed = self._config.allow_fallback_handler

                if has_fallback and fallback_allowed:
                    # Fallback explicitly allowed in strict mode
                    pass
                elif has_fallback:
                    raise StrictValidationViolationError(
                        aggregate_type=aggregate_type,
                        event_type=event_type,
                        reason=(
                            "Strict mode requires exact apply_<EventType> method, "
                            "not apply_event fallback. Set allow_fallback_handler=True "
                            "to use fallback in strict mode."
                        ),
                    )
                else:
                    raise MissingEventHandlerError(
                        aggregate_type=aggregate_type,
                        event_type=event_type,
                    )
        else:
            # Lenient mode: allow exact or fallback (if configured)
            fallback_allowed = self._config.allow_fallback_handler

            if not has_exact and not (has_fallback and fallback_allowed):
                raise MissingEventHandlerError(
                    aggregate_type=aggregate_type,
                    event_type=event_type,
                )

    def get_config(self) -> EventValidationConfig:
        """Get the current validation configuration.

        Returns:
            The current EventValidationConfig instance.
        """
        return self._config

    def is_enabled(self) -> bool:
        """Check if validation is currently enabled.

        Returns:
            True if validation is enabled, False otherwise.
        """
        return self._config.enabled

    def is_strict_mode(self) -> bool:
        """Check if strict mode is enabled.

        Returns:
            True if strict mode is enabled, False otherwise.
        """
        return self._config.strict_mode
