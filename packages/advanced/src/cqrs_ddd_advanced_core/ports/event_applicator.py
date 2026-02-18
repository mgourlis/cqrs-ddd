"""
IEventApplicator — protocol for applying domain events to aggregates on replay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

from cqrs_ddd_core.domain.aggregate import AggregateRoot

T = TypeVar("T", bound=AggregateRoot[Any])


@runtime_checkable
class IEventApplicator(Protocol[T]):
    """Port for applying a domain event to an aggregate during event-sourced replay.

    Implementations may dispatch by event type name (e.g. call
    ``aggregate.apply_OrderCreated(event)``) or use a single fold function.
    """

    def apply(self, aggregate: T, event: DomainEvent) -> T:
        """Apply the event to the aggregate and return the aggregate (possibly mutated).

        Args:
            aggregate: The aggregate instance to update.
            event: The domain event to apply.

        Returns:
            The same aggregate after applying the event (possibly mutated in place).
        """
        ...
