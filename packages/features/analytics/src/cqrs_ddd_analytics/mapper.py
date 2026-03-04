"""EventToRowMapper — configurable event-to-row flattening."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar, overload

from .ports import IRowMapper

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

logger = logging.getLogger(__name__)

E = TypeVar("E", bound="DomainEvent")

MapperFunc = Callable[[E], dict[str, object] | list[dict[str, object]] | None]


class EventToRowMapper(IRowMapper):
    """Configurable mapper that routes events to per-type mapping functions.

    Register mapping functions for specific event types.  Events without a
    registered mapper are silently skipped (returns ``None``).

    Usage::

        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def map_order(event: OrderCreated) -> dict:
            return {"order_id": str(event.aggregate_id), ...}
    """

    def __init__(self) -> None:
        self._mappers: dict[type[DomainEvent], MapperFunc[DomainEvent]] = {}

    @overload
    def register(
        self, event_type: type[E]
    ) -> Callable[[MapperFunc[E]], MapperFunc[E]]: ...

    @overload
    def register(self, event_type: type[E], func: MapperFunc[E]) -> None: ...

    def register(
        self,
        event_type: type[E],
        func: MapperFunc[E] | None = None,
    ) -> Callable[[MapperFunc[E]], MapperFunc[E]] | None:
        """Register a mapping function for an event type.

        Can be used as a decorator::

            @mapper.register(OrderCreated)
            def map_order(event: OrderCreated) -> dict: ...

        Or called directly::

            mapper.register(OrderCreated, map_order)
        """
        if func is not None:
            self._mappers[event_type] = func  # type: ignore[assignment]
            return None

        def decorator(fn: MapperFunc[E]) -> MapperFunc[E]:
            self._mappers[event_type] = fn  # type: ignore[assignment]
            return fn

        return decorator

    def map(
        self, event: DomainEvent
    ) -> dict[str, object] | list[dict[str, object]] | None:
        """Map a domain event to row dict(s) using the registered mapper.

        Returns ``None`` if no mapper is registered for the event type.
        """
        mapper_func = self._mappers.get(type(event))
        if mapper_func is None:
            logger.debug("No mapper registered for %s, skipping", type(event).__name__)
            return None
        return mapper_func(event)

    @property
    def registered_types(self) -> frozenset[type[DomainEvent]]:
        """Return the set of event types with registered mappers."""
        return frozenset(self._mappers.keys())
