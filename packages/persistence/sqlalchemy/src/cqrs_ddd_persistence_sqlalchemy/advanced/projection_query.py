"""
SQLAlchemy projection-backed query persistence for dispatcher integration.

Provides concrete implementations that adapt SQLAlchemyProjectionStore
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

    from .projection_store import SQLAlchemyProjectionStore

T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int)


class SQLAlchemyProjectionQueryPersistence(
    ProjectionBackedQueryPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    SQLAlchemy-based ID query persistence backed by projections.

    Usage:
        class CustomerSummaryQuery(
            SQLAlchemyProjectionQueryPersistence[CustomerSummaryDTO, str]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)
    """

    _store: SQLAlchemyProjectionStore

    def __init__(self, store: SQLAlchemyProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store


class SQLAlchemyProjectionSpecPersistence(
    ProjectionBackedSpecPersistence[T_Result],
    Generic[T_Result],
):
    """
    SQLAlchemy-based specification query persistence backed by projections.

    Requires implementing build_filter() to convert ISpecification to
    SQL WHERE clause conditions.

    Usage:
        class CustomerSummarySpecQuery(
            SQLAlchemyProjectionSpecPersistence[CustomerSummaryDTO]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)

            def build_filter(self, spec) -> dict:
                # Convert specification to SQL-like filter dict
                if hasattr(spec, 'status'):
                    return {'status': spec.status}
                return {}
    """

    _store: SQLAlchemyProjectionStore

    def __init__(self, store: SQLAlchemyProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store

    def build_filter(
        self,
        criteria: ISpecification[Any] | Any,
    ) -> dict[str, Any]:
        """
        Convert specification to filter dict for SQLAlchemy find().

        Override this method to support specification-based queries.
        The filter dict keys should match column names in the projection table.
        """
        # Default: try to extract common attributes
        if hasattr(criteria, "to_filter_dict"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_filter_dict())

        # Fallback: raise NotImplementedError
        return super().build_filter(criteria)


class SQLAlchemyProjectionDualPersistence(
    ProjectionBackedDualPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    Combined SQLAlchemy projection-backed query persistence.

    Implements both ID-based and specification-based query interfaces,
    plus convenience methods for projection handlers.

    Usage:
        class CustomerSummaryDual(
            SQLAlchemyProjectionDualPersistence[CustomerSummaryDTO, str]
        ):
            collection = "customer_summaries"

            def to_dto(self, doc: dict) -> CustomerSummaryDTO:
                return CustomerSummaryDTO(**doc)

            def build_filter(self, spec) -> dict:
                return {'status': spec.status} if hasattr(spec, 'status') else {}

        # Register with dispatcher
        registry.register_query(CustomerSummaryDTO, CustomerSummaryDual)
        registry.register_query_spec(CustomerSummaryDTO, CustomerSummaryDual)
    """

    _store: SQLAlchemyProjectionStore

    def __init__(self, store: SQLAlchemyProjectionStore) -> None:
        self._store = store

    def get_reader(self) -> IProjectionReader:
        return self._store

    def get_writer(self) -> IProjectionWriter:
        return self._store

    def build_filter(
        self,
        criteria: ISpecification[Any] | Any,
    ) -> dict[str, Any]:
        """Convert specification to filter dict."""
        if hasattr(criteria, "to_filter_dict"):
            from typing import cast

            return cast("dict[str, Any]", criteria.to_filter_dict())
        return super().build_filter(criteria)
