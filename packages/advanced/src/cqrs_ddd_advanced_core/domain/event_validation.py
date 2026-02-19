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

    def _check_strict_mode(
        self,
        aggregate_type: str,
        event_type: str,
        has_exact: bool,
        has_fallback: bool,
        allow_fallback: bool,
    ) -> None:
        """Strict mode: require exact handler or allowed fallback. Raises if invalid."""
        if has_exact:
            return
        if has_fallback and allow_fallback:
            return
        if has_fallback:
            raise StrictValidationViolationError(
                aggregate_type=aggregate_type,
                event_type=event_type,
                reason=(
                    "Strict mode requires exact apply_<EventType> method, "
                    "not apply_event fallback. Set allow_fallback_handler=True "
                    "to use fallback in strict mode."
                ),
            )
        raise MissingEventHandlerError(
            aggregate_type=aggregate_type,
            event_type=event_type,
        )

    def _check_lenient_mode(
        self,
        aggregate_type: str,
        event_type: str,
        has_exact: bool,
        has_fallback: bool,
        allow_fallback: bool,
    ) -> None:
        """Lenient mode: allow exact or fallback when allowed. Raises if no handler."""
        if has_exact or (has_fallback and allow_fallback):
            return
        raise MissingEventHandlerError(
            aggregate_type=aggregate_type,
            event_type=event_type,
        )

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
        event_type_snake = event_type_to_snake(event_type)
        has_exact = hasattr(aggregate, f"apply_{event_type}") or hasattr(
            aggregate, f"apply_{event_type_snake}"
        )
        has_fallback = hasattr(aggregate, "apply_event")
        allow_fallback = self._config.allow_fallback_handler

        if self._config.strict_mode:
            self._check_strict_mode(
                aggregate_type, event_type, has_exact, has_fallback, allow_fallback
            )
        else:
            self._check_lenient_mode(
                aggregate_type, event_type, has_exact, has_fallback, allow_fallback
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
