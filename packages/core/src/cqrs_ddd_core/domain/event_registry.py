"""EventTypeRegistry — maps event type names to their classes for hydration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .events import DomainEvent


class EventTypeRegistry:
    """Registry for mapping ``event_type_name: str`` → ``Type[DomainEvent]``.

    Used to reconstruct domain events from stored payloads.

    **Explicit registration** is required via ``register(name, cls)``.
    Create instances per application context for isolation.

    Usage::

        registry = EventTypeRegistry()
        registry.register("OrderCreated", OrderCreated)
        event = registry.hydrate("OrderCreated", {"order_id": "123"})
    """

    def __init__(self) -> None:
        self._registry: dict[str, type[DomainEvent]] = {}

    def register(self, name: str, event_class: type[DomainEvent]) -> None:
        """Register an event class under *name*."""
        self._registry[name] = event_class

    def get(self, event_type: str) -> type[DomainEvent] | None:
        """Look up an event class by type name."""
        return self._registry.get(event_type)

    def has(self, event_type: str) -> bool:
        """Return ``True`` if *event_type* is registered."""
        return event_type in self._registry

    def hydrate(self, event_type: str, data: dict[str, Any]) -> DomainEvent | None:
        """Reconstruct a domain event from its type name and payload dict.

        Returns ``None`` if the event type is not registered.
        """
        event_class = self.get(event_type)
        if event_class is None:
            return None

        try:
            return event_class.model_validate(data)
        except (TypeError, ValueError):
            return None

    def list_registered(self) -> list[str]:
        """Return all registered event type names."""
        return list(self._registry.keys())

    def clear(self) -> None:
        """Remove all registrations (testing utility)."""
        self._registry.clear()
