"""IPersistenceDispatcher - Protocol for persistence dispatchers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from cqrs_ddd_core.domain.aggregate import AggregateRoot

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cqrs_ddd_advanced_core.ports import T_ID, T_Criteria
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])
T_Result = TypeVar("T_Result")


@runtime_checkable
class IPersistenceDispatcher(Protocol):
    """
    Interface for persistence dispatchers.
    Allows decorating the dispatcher with cross-cutting concerns
    (Caching, Logging, etc).

    ``fetch`` returns a :class:`SearchResult` — ``await`` for a list,
    or ``.stream()`` for an ``AsyncIterator``::

        dtos = await dispatcher.fetch(OrderDTO, spec)
        async for dto in dispatcher.fetch(OrderDTO, spec).stream():
            ...
    """

    async def apply(
        self,
        entity: AggregateRoot[T_ID],
        uow: UnitOfWork | None = None,
        events: list[DomainEvent] | None = None,
    ) -> T_ID:
        """Apply a write (persist entity, optionally with events)."""
        ...

    async def fetch_domain(
        self,
        entity_type: type[T_Entity],
        ids: Sequence[T_ID],
        uow: UnitOfWork | None = None,
    ) -> list[T_Entity]:
        """Fetch domain entities by ID."""
        ...

    async def fetch(
        self,
        result_type: type[T_Result],
        criteria: T_Criteria[Any],
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T_Result]:
        """Fetch read models by criteria (IDs, ISpecification, or QueryOptions)."""
        ...
