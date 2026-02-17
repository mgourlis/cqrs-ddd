"""IRepository — generic repository protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from ..domain.aggregate import AggregateRoot

if TYPE_CHECKING:
    from ..domain.specification import ISpecification
    from ..ports.search_result import SearchResult
    from ..ports.unit_of_work import UnitOfWork

T = TypeVar("T", bound=AggregateRoot[Any])
# Explicitly list constraints to satisfy mypy
ID = TypeVar("ID", str, int, UUID)


@runtime_checkable
class IRepository(Protocol[T, ID]):
    """
    Generic Repository interface for managing state-stored aggregates.

    The ``search`` method accepts either an ``ISpecification[T]`` or a
    ``QueryOptions`` instance (which wraps a specification together with
    pagination, ordering, and projection).  It returns a
    :class:`SearchResult[T]` — ``await`` it for a ``list[T]``, or call
    ``.stream(batch_size=…)`` for an ``AsyncIterator[T]``::

        # batch
        result = await repo.search(spec)
        items = await result

        # stream
        result = await repo.search(spec)
        async for item in result.stream(batch_size=100):
            ...
    """

    async def add(self, entity: T, uow: UnitOfWork | None = None) -> ID: ...

    async def get(self, entity_id: ID, uow: UnitOfWork | None = None) -> T | None: ...

    async def delete(self, entity_id: ID, uow: UnitOfWork | None = None) -> ID: ...

    async def list_all(
        self, entity_ids: list[ID] | None = None, uow: UnitOfWork | None = None
    ) -> list[T]: ...

    async def search(
        self,
        criteria: ISpecification[T] | Any,  # ISpecification | QueryOptions
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]: ...
