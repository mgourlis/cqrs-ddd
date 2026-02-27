"""
MongoDB projection-backed query persistence for dispatcher integration.

Provides concrete implementations that adapt MongoProjectionStore
to the high-level IQueryPersistence/IQuerySpecificationPersistence interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_advanced_core.projections.backed_persistence import (
    ProjectionBackedDualPersistence,
    ProjectionBackedQueryPersistence,
    ProjectionBackedSpecPersistence,
)

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.ports.projection import (
        IProjectionReader,
        IProjectionWriter,
    )
    from cqrs_ddd_core.domain.specification import ISpecification

    from .projection_store import MongoProjectionStore

T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int)


class MongoProjectionQueryPersistence(
    ProjectionBackedQueryPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    MongoDB-based ID query persistence backed by projections.

    Usage:
        class CustomerSummaryQuery(
            MongoProjectionQueryPersistence[CustomerSummaryDTO, str]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)
    """

    _store: MongoProjectionStore

    def __init__(self, store: MongoProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store


class MongoProjectionSpecPersistence(
    ProjectionBackedSpecPersistence[T_Result],
    Generic[T_Result],
):
    """
    MongoDB-based specification query persistence backed by projections.

    Supports MongoDB-specific query operators ($gt, $in, $regex, etc.)
    via build_filter().

    Usage:
        class CustomerSummarySpecQuery(
            MongoProjectionSpecPersistence[CustomerSummaryDTO]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)

            def build_filter(self, spec) -> dict:
                if hasattr(spec, 'status'):
                    return {'status': spec.status}
                if hasattr(spec, 'min_total'):
                    return {'total': {'$gte': spec.min_total}}
                return {}
    """

    _store: MongoProjectionStore

    def __init__(self, store: MongoProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store

    def build_filter(
        self,
        criteria: ISpecification[Any] | Any,
    ) -> dict[str, Any]:
        """
        Convert specification to MongoDB filter dict.

        Override this method to support specification-based queries.
        The filter dict supports MongoDB query operators:
        - {"field": value} - equality
        - {"field": {"$gt": value}} - greater than
        - {"field": {"$in": [values]}} - in list
        - {"field": {"$regex": pattern}} - regex match
        """
        # Default: try to extract common attributes
        if hasattr(criteria, "to_mongo_filter"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_mongo_filter())

        if hasattr(criteria, "to_filter_dict"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_filter_dict())

        # Fallback: raise NotImplementedError
        return super().build_filter(criteria)


class MongoProjectionDualPersistence(
    ProjectionBackedDualPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    Combined MongoDB projection-backed query persistence.

    Implements both ID-based and specification-based query interfaces,
    plus convenience methods for projection handlers.

    Usage:
        class CustomerSummaryDual(
            MongoProjectionDualPersistence[CustomerSummaryDTO, str]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)

            def build_filter(self, spec) -> dict:
                if hasattr(spec, 'status'):
                    return {'status': spec.status}
                if hasattr(spec, 'min_total'):
                    return {'total': {'$gte': spec.min_total}}
                return {}

        # Register with dispatcher
        registry.register_query(CustomerSummaryDTO, CustomerSummaryDual)
        registry.register_query_spec(CustomerSummaryDTO, CustomerSummaryDual)

        # Use in projection handler
        async def handle(self, event: OrderCreated, uow: UnitOfWork):
            await self.persistence.refresh(
                event.customer_id,
                {"id": event.customer_id, "total_orders": new_total},
                event_position=event.position,
                event_id=event.id,
                uow=uow,
            )
    """

    _store: MongoProjectionStore

    def __init__(self, store: MongoProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store

    def get_writer(self) -> IProjectionWriter:
        return self._store

    def build_filter(
        self,
        criteria: ISpecification[Any] | Any,
    ) -> dict[str, Any]:
        """Convert specification to MongoDB filter dict."""
        if hasattr(criteria, "to_mongo_filter"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_mongo_filter())

        if hasattr(criteria, "to_filter_dict"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_filter_dict())

        return super().build_filter(criteria)
