"""Routing decorators for domain events."""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def route_to(destination_key: str) -> Any:
    """Decorator to mark an event class for a specific routing destination.

    Used by :class:`~cqrs_ddd_core.cqrs.publishers.routing.TopicRoutingPublisher`
    to resolve which publisher should handle a specific event.

    Usage::

        @route_to("slow")
        class HeavyProcessingEvent(DomainEvent):
            ...
    """

    def decorator(cls: T) -> T:
        cls.__route_to__ = destination_key  # type: ignore[attr-defined]
        return cls

    return decorator
