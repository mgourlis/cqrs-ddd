"""
Projection-backed query persistence bases for dispatcher integration.

These abstract bases adapt the low-level IProjectionReader/IProjectionWriter
to the high-level IQueryPersistence/IQuerySpecificationPersistence interfaces
used by the persistence dispatcher.

This enables:

1. **Type-safe DTO queries:** Typed read models backed by projection collections
2. **Specification support:** Query projections using ISpecification
3. **Dispatcher integration:** Register projection-backed queries in PersistenceRegistry

Usage Example:

```python
from cqrs_ddd_advanced_core.projections.backed_persistence import (
    ProjectionBackedQueryPersistence,
    ProjectionBackedSpecPersistence,
)
from cqrs_ddd_advanced_core.ports.projection import IProjectionReader

class CustomerSummaryDTO(BaseModel):
    id: str
    name: str
    total_orders: int

class CustomerSummaryQueryPersistence(
    ProjectionBackedQueryPersistence[CustomerSummaryDTO, str]
):
    collection = "customer_summaries"

    def to_dto(self, doc: dict) -> CustomerSummaryDTO:
        return CustomerSummaryDTO(**doc)

# Register with dispatcher
registry.register_query(CustomerSummaryDTO, CustomerSummaryQueryPersistence)
```
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_advanced_core.ports.persistence import (
    IQueryPersistence,
    IQuerySpecificationPersistence,
)
from cqrs_ddd_core.ports.search_result import SearchResult

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.ports.projection import IProjectionReader, IProjectionWriter
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int)


class ProjectionBackedQueryPersistence(
    IQueryPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    Abstract base for ID-based query persistence backed by projections.

    Adapts the low-level IProjectionReader to the typed IQueryPersistence
    interface used by the persistence dispatcher.

    Subclasses must define:
        - ``collection``: Projection collection/table name
        - ``to_dto(doc: dict) -> T_Result``: Convert raw doc to DTO
        - ``get_reader() -> IProjectionReader``: Provide projection reader
    """

    collection: str

    @abstractmethod
    def to_dto(self, doc: dict[str, Any]) -> T_Result:
        """Convert raw document dict to typed DTO."""
        ...

    @abstractmethod
    def get_reader(self) -> IProjectionReader:
        """Get the projection reader instance."""
        ...

    @property
    def reader(self) -> IProjectionReader:
        """Convenience property for accessing reader."""
        return self.get_reader()

    async def fetch(
        self,
        ids: Sequence[T_ID],
        uow: UnitOfWork | None = None,
    ) -> list[T_Result]:
        """Fetch result DTOs by their IDs."""
        # Use batch fetch if available
        if hasattr(self.reader, "get_batch"):
            docs = await self.reader.get_batch(
                self.collection,
                list(ids),
                uow=uow,
            )
            return [self.to_dto(doc) for doc in docs if doc is not None]

        # Fallback to individual fetches
        results = []
        for id_ in ids:
            doc = await self.reader.get(self.collection, id_, uow=uow)
            if doc is not None:
                results.append(self.to_dto(doc))
        return results


class ProjectionBackedSpecPersistence(
    IQuerySpecificationPersistence[T_Result],
    Generic[T_Result],
):
    """
    Abstract base for specification-based query persistence backed by projections.

    Adapts the low-level IProjectionReader to the typed IQuerySpecificationPersistence
    interface used by the persistence dispatcher.

    Subclasses must define:
        - ``collection``: Projection collection/table name
        - ``to_dto(doc: dict) -> T_Result``: Convert raw doc to DTO
        - ``get_reader() -> IProjectionReader``: Provide projection reader
        - ``build_filter(spec) -> dict``: Convert ISpecification to filter dict (optional)
    """

    collection: str

    @abstractmethod
    def to_dto(self, doc: dict[str, Any]) -> T_Result:
        """Convert raw document dict to typed DTO."""
        ...

    @abstractmethod
    def get_reader(self) -> IProjectionReader:
        """Get the projection reader instance."""
        ...

    @property
    def reader(self) -> IProjectionReader:
        """Convenience property for accessing reader."""
        return self.get_reader()

    def build_filter(
        self,
        criteria: ISpecification[Any] | Any,
    ) -> dict[str, Any]:
        """
        Convert specification to filter dict.

        Override this method to support specification-based queries.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement build_filter() "
            "to support specification-based queries"
        )

    def fetch(
        self,
        criteria: ISpecification[Any] | Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T_Result]:
        """Fetch result DTOs by specification or QueryOptions."""
        from cqrs_ddd_core.ports.search_result import SearchResult

        # Check if reader supports find()
        if not hasattr(self.reader, "find"):
            raise NotImplementedError(
                f"{self.__class__.__name__} requires a reader with find() support "
                "for specification-based queries"
            )

        # Extract pagination and filter
        if hasattr(criteria, "specification"):
            # QueryOptions-like object
            spec = criteria.specification  # type: ignore[union-attr]
            limit = getattr(criteria, "limit", 100)
            offset = getattr(criteria, "offset", 0)
        else:
            # Raw specification
            spec = criteria
            limit = 100
            offset = 0

        filter_dict = self.build_filter(spec)

        async def _execute() -> list[T_Result]:
            docs = await self.reader.find(
                self.collection,
                filter_dict,
                limit=limit,
                offset=offset,
                uow=uow,
            )
            return [self.to_dto(doc) for doc in docs]

        async def _stream(batch_size: int | None = 100) -> AsyncIterator[T_Result]:
            actual_batch_size = batch_size or 100
            current_offset = offset
            while True:
                docs = await self.reader.find(
                    self.collection,
                    filter_dict,
                    limit=actual_batch_size,
                    offset=current_offset,
                    uow=uow,
                )
                if not docs:
                    break
                for doc in docs:
                    yield self.to_dto(doc)
                current_offset += actual_batch_size

        return SearchResult(_execute, _stream)


class ProjectionBackedDualPersistence(
    ProjectionBackedQueryPersistence[T_Result, T_ID],
    ProjectionBackedSpecPersistence[T_Result],
    Generic[T_Result, T_ID],
):
    """
    Combined ID-based and specification-based query persistence.

    Implements both IQueryPersistence and IQuerySpecificationPersistence,
    useful for read models that need both access patterns.
    """

    @abstractmethod
    def get_writer(self) -> IProjectionWriter:
        """Get the projection writer instance."""
        ...

    @property
    def writer(self) -> IProjectionWriter:
        """Convenience property for accessing writer."""
        return self.get_writer()

    async def refresh(
        self,
        id_: T_ID,
        data: dict[str, Any] | T_Result,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """
        Refresh a projection document from event handler.

        Convenience method for projection handlers that need to update
        a single projection document.
        """
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")  # type: ignore[union-attr]
        return await self.writer.upsert(
            self.collection,
            id_,
            data,  # type: ignore[arg-type]
            event_position=event_position,
            event_id=event_id,
            uow=uow,
        )

    async def refresh_batch(
        self,
        docs: list[dict[str, Any] | T_Result],
        *,
        id_field: str = "id",
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Refresh multiple projection documents in batch.

        Convenience method for projection handlers that need to update
        multiple projection documents atomically.
        """
        await self.writer.upsert_batch(
            self.collection,
            docs,
            id_field=id_field,
            uow=uow,
        )
