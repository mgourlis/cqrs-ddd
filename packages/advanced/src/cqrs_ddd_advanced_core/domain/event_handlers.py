"""Decorator utilities for event handler metadata and configuration.

Provides decorators to mark event handlers and configure validation
at the aggregate level. These decorators are optional - they add
metadata for documentation and validation but don't change behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.domain.aggregate import AggregateRoot
    from cqrs_ddd_core.domain.events import DomainEvent

from cqrs_ddd_advanced_core.domain.event_validation import EventValidationConfig

P = ParamSpec("P")
R = TypeVar("R")


def aggregate_event_handler(
    event_type: type[DomainEvent] | None = None,
    *,
    validate_on_load: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to mark a method as an event handler.

    This decorator adds metadata to event handler methods for documentation
    and optional validation. It does not change the method's behavior.

    Args:
        event_type: Optional explicit event type class. If None, inferred from
                   method name (e.g., apply_OrderCreated → OrderCreated).
        validate_on_load: Whether to validate handler on aggregate load.
                        Metadata only - actual validation depends on EventValidator.

    Example:
        from cqrs_ddd_core.domain.aggregate import AggregateRoot
        from cqrs_ddd_core.domain.events import DomainEvent
        from cqrs_ddd_advanced_core.domain.event_handlers import event_handler

        class OrderCreated(DomainEvent):
            order_id: str

        class Order(AggregateRoot[str]):
            status: str = "pending"

            @event_handler()
            def apply_OrderCreated(self, event: OrderCreated) -> None:
                self.status = "created"

            # Or with explicit event type:
            @event_handler(event_type=OrderCreated)
            def handle_order_created(self, event: OrderCreated) -> None:
                self.status = "created"
    """

    def decorator(method: Callable[P, R]) -> Callable[P, R]:
        # Store metadata for validation/inspection
        if not hasattr(method, "_is_aggregate_event_handler"):
            method._is_aggregate_event_handler = True  # type: ignore[attr-defined]

        if event_type is not None:
            method._event_type = event_type.__name__  # type: ignore[attr-defined]

        method._validate_on_load = validate_on_load  # type: ignore[attr-defined]

        return method

    return decorator


def aggregate_event_handler_validator(
    *,
    enabled: bool = True,
    strict: bool = False,
    allow_fallback: bool = True,
) -> Callable[[type[AggregateRoot[Any]]], type[AggregateRoot[Any]]]:
    """Class decorator to configure event handler validation for an aggregate.

    This decorator attaches a validation configuration to the aggregate class.
    The configuration is read by EventValidator when validating handlers.

    Args:
        enabled: Enable validation for this aggregate. Defaults to True.
        strict: Require exact apply_<EventType> methods (no apply_event fallback).
        allow_fallback: Allow the generic apply_event method when strict=False.

    Example:
        from cqrs_ddd_core.domain.aggregate import AggregateRoot
        from cqrs_ddd_advanced_core.domain.event_handlers import (
            aggregate_event_handler_validator,
        )

        @aggregate_event_handler_validator(enabled=True, strict=True)
        class Order(AggregateRoot[str]):
            status: str = "pending"

            def apply_OrderCreated(self, event: OrderCreated) -> None:
                self.status = "created"

            # This would fail validation in strict mode:
            # def apply_event(self, event: DomainEvent) -> None:
            #     pass
    """

    def decorator(aggregate_cls: type[AggregateRoot[Any]]) -> type[AggregateRoot[Any]]:
        config = EventValidationConfig(
            enabled=enabled,
            strict_mode=strict,
            allow_fallback_handler=allow_fallback,
        )
        aggregate_cls._event_validation_config = config  # type: ignore[attr-defined]
        return aggregate_cls

    return decorator


def get_event_handler_config(
    aggregate: AggregateRoot[Any] | type[AggregateRoot[Any]],
) -> EventValidationConfig | None:
    """Get the event validation configuration for an aggregate.

    Checks if the aggregate class has a _event_validation_config
    attribute set by the @event_handler_validator decorator.

    Args:
        aggregate: The aggregate instance or class to check.

    Returns:
        The EventValidationConfig if set, None otherwise.
    """
    # Get the class (handle both instances and classes)
    cls = aggregate if isinstance(aggregate, type) else type(aggregate)

    # Check for configuration attribute
    config = getattr(cls, "_event_validation_config", None)

    if config is not None and isinstance(config, EventValidationConfig):
        return cast("EventValidationConfig", config)

    return None


def is_aggregate_event_handler(method: Any) -> bool:
    """Check if a method is marked as an aggregate event handler.

    Checks for the _is_aggregate_event_handler metadata attribute set by
    the @aggregate_event_handler decorator.

    Args:
        method: The method to check.

    Returns:
        True if the method is marked as an aggregate event handler, False otherwise.
    """
    return getattr(method, "_is_aggregate_event_handler", False)


def get_handler_event_type(method: Any) -> str | None:
    """Get the event type for an event handler method.

    Returns the _event_type metadata if set by the @event_handler
    decorator, otherwise None.

    Args:
        method: The event handler method.

    Returns:
        The event type name if explicitly set, None otherwise.
    """
    return getattr(method, "_event_type", None)
