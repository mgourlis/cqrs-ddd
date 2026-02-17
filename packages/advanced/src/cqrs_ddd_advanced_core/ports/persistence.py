from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import UUID

from cqrs_ddd_core.domain.aggregate import AggregateRoot, Modification
from cqrs_ddd_core.domain.specification import ISpecification

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])  # Aggregate Root type
T_Result = TypeVar("T_Result")  # Query result type

# Contravariant ID type for handlers
T_ID = TypeVar("T_ID", str, int, UUID, contravariant=True)

T_Criteria = Sequence[T_ID] | ISpecification[Any]


class IOperationPersistence(ABC, Generic[T_Entity, T_ID]):
    """
    Base class for command-side persistence (Writes).
    Generic over the Entity type and its ID type.
    """

    @abstractmethod
    async def persist(self, modification: Modification[T_ID], uow: UnitOfWork) -> T_ID:
        """
        Persist the modification (entity changes + events).
        Returns the result of the operation (usually the entity ID).
        """
        ...


class IRetrievalPersistence(ABC, Generic[T_Entity, T_ID]):
    """
    Base class for aggregate retrieval (Command-side Reads).
    Generic over the Entity type and its ID type.
    """

    @abstractmethod
    async def retrieve(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T_Entity]:
        """Retrieve aggregates by their IDs."""
        ...


class IQueryPersistence(ABC, Generic[T_Result, T_ID]):
    """
    Base class for ID-based query-side persistence (Read Models).
    Generic over the Result DTO type and the underlying Entity ID type.
    Allows for easy caching of results by ID.
    """

    @abstractmethod
    async def fetch(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T_Result]:
        """Fetch result DTOs by their IDs."""
        ...


class IQuerySpecificationPersistence(ABC, Generic[T_Result]):
    """
    Base class for Specification-based query-side persistence (Read Models).
    Generic over the Result DTO type.

    ``criteria`` accepts either an ``ISpecification`` or a ``QueryOptions``
    instance (which wraps a specification together with pagination, ordering,
    and projection).

    Returns a :class:`SearchResult[T_Result]` — ``await`` it for a
    ``list[T_Result]``, or call ``.stream(batch_size=…)`` for an
    ``AsyncIterator[T_Result]``::

        # batch
        dtos = await handler.fetch(spec, uow)

        # stream
        async for dto in handler.fetch(spec, uow).stream(batch_size=100):
            ...
    """

    @abstractmethod
    def fetch(
        self,
        criteria: ISpecification[Any] | Any,  # ISpecification | QueryOptions
        uow: UnitOfWork,
    ) -> SearchResult[T_Result]:
        """Fetch result DTOs by specification or QueryOptions."""
        ...
