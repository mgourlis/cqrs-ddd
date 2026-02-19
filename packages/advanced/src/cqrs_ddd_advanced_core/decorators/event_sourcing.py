"""Decorators for event-sourcing configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot


T = TypeVar("T", bound="AggregateRoot[Any]")


def non_event_sourced(agg_cls: type[T]) -> type[T]:
    """Decorator to mark an aggregate as non-event-sourced.

    Aggregates marked as non-event-sourced can still produce events,
    but those events will NOT be persisted to the EventStore.

    Use this for:
    - In-memory caches
    - Ephemeral state
    - Audit logs (if stored elsewhere)
    - Temporary aggregates

    **Data Integrity**: Non-event-sourced aggregates should NOT be used
    for critical business state. Use event-sourced aggregates for
    data that must be durable and replayable.

    Example:
        ```python
        from cqrs_ddd_advanced_core.decorators.event_sourcing import non_event_sourced

        @non_event_sourced
        class CacheEntry(AggregateRoot[str]):
            # Events are NOT persisted to EventStore
            def apply_CacheUpdated(self, event: CacheUpdated) -> None:
                self.value = event.new_value
        ```
    """
    agg_cls._is_non_event_sourced = True  # type: ignore[attr-defined]
    return agg_cls
