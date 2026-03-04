"""Multitenant persistence mixins for operation, retrieval, and query persistence.

These mixins add tenant context propagation to the advanced persistence
interfaces when composed with base persistence classes via MRO.

CRITICAL REQUIREMENT:
    The underlying persistence implementations MUST filter by tenant_id
    at the DATABASE QUERY LEVEL using a DEDICATED COLUMN (not JSONB metadata).
    This file contains NO in-memory filtering - all filtering happens at DB level.

    Example (SQLAlchemy):
        # Retrieval/query persistence should add WHERE clause
        SELECT * FROM entities
        WHERE id IN (...) AND tenant_id = :tenant_id

    Your entities MUST have a dedicated tenant_id field.
    Use MultitenantMixin from cqrs_ddd_multitenancy.domain to add this field.

Usage:
    class MyOperationPersistence(
        MultitenantOperationPersistenceMixin,
        SQLAlchemyOperationPersistence
    ):
        pass

    class MyQueryPersistence(
        MultitenantQueryPersistenceMixin,
        SQLAlchemyQueryPersistence
    ):
        pass

The mixins must appear BEFORE the base classes in the MRO.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from ..context import (
    is_system_tenant,
    require_tenant,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cqrs_ddd_core.domain.aggregate import AggregateRoot
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantOperationPersistenceMixin",
    "MultitenantRetrievalPersistenceMixin",
    "MultitenantQueryPersistenceMixin",
    "MultitenantQuerySpecificationPersistenceMixin",
]

logger = logging.getLogger(__name__)

T_Entity = TypeVar("T_Entity", bound="AggregateRoot[Any]")
T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int)


class MultitenantOperationPersistenceMixin:
    """Mixin for IOperationPersistence with tenant context injection.

    Ensures tenant_id is injected into entities and events during persist.

    Usage:
        class MyOperationPersistence(
            MultitenantOperationPersistenceMixin,
            SQLAlchemyOperationPersistence
        ):
            pass
    """

    async def persist(
        self,
        entity: T_Entity,
        uow: UnitOfWork,
        events: list[DomainEvent] | None = None,
    ) -> T_ID:
        """Persist entity with tenant context injection.

        Injects tenant_id into entity's dedicated tenant_id field.
        Also injects tenant_id into event metadata for outbox pattern.

        Args:
            entity: Aggregate root to persist (must have tenant_id field)
            uow: Unit of work
            events: Optional domain events

        Returns:
            Entity ID

        Raises:
            TenantContextMissingError: If no tenant context is set
            ValueError: If entity doesn't have tenant_id field

        Note:
            Entity MUST have a dedicated tenant_id field (use MultitenantMixin).
            Event metadata is used for outbox pattern only.
        """
        tenant_id = require_tenant()

        # Set tenant_id on entity (dedicated field required)
        if not hasattr(entity, "tenant_id"):
            raise ValueError(
                f"Entity {type(entity).__name__} must have a 'tenant_id' field. "
                "Use MultitenantMixin from cqrs_ddd_multitenancy.domain."
            )

        try:
            if hasattr(entity, "model_copy"):
                # Pydantic v2 immutable update
                entity = entity.model_copy(update={"tenant_id": tenant_id})
            else:
                # Mutable entity
                entity.tenant_id = tenant_id
        except (AttributeError, TypeError) as e:
            logger.warning(
                "Could not set tenant_id on entity",
                extra={
                    "entity_type": type(entity).__name__,
                    "error": str(e),
                },
            )

        # Inject tenant_id into events
        if events:
            for event in events:
                if hasattr(event, "metadata"):
                    event.metadata["tenant_id"] = tenant_id
                else:
                    event.metadata = {"tenant_id": tenant_id}  # type: ignore[misc]

        logger.debug(
            "Persisting entity with tenant context",
            extra={"tenant_id": tenant_id, "entity_type": type(entity).__name__},
        )

        return await super().persist(entity, uow, events)  # type: ignore[misc, no-any-return]


class MultitenantRetrievalPersistenceMixin:
    """Mixin for IRetrievalPersistence with specification-based tenant filtering.

    Uses the Specification pattern to compose tenant filters with ID-based queries.
    The underlying implementation evaluates the specification at the database level.

    Requires entities to have a dedicated tenant_id field (use MultitenantMixin).

    How it works:
        1. Mixin creates an AttributeSpecification for tenant_id
        2. Specification is evaluated by underlying implementation
        3. SQLAlchemy adds WHERE tenant_id = ? clause
        4. MongoDB adds {tenant_id: '...'} filter
        5. In-memory implementations filter Python objects

    Usage:
        class MyRetrievalPersistence(
            MultitenantRetrievalPersistenceMixin,
            SQLAlchemyRetrievalPersistence
        ):
            # Base implementation already handles specifications
            pass
    """

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for database queries.

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An ISpecification that filters by tenant_id.
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr="tenant_id",
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fallback to dict-based specification
            return {"attr": "tenant_id", "op": "eq", "value": tenant_id}

    def _compose_specs(self, tenant_spec: Any, other: Any | None) -> Any:
        """Compose tenant specification with an optional additional specification.

        Args:
            tenant_spec: The tenant specification.
            other: Optional additional specification to compose with.

        Returns:
            The composed specification, or just tenant_spec if other is None.
        """
        if other is None:
            return tenant_spec
        if hasattr(tenant_spec, "__and__") and hasattr(other, "__and__"):
            try:
                return tenant_spec & other
            except (TypeError, AttributeError):
                pass
        return tenant_spec

    async def retrieve(
        self,
        ids: Sequence[T_ID],
        uow: UnitOfWork,
        *,
        specification: Any | None = None,
    ) -> list[T_Entity]:
        """Retrieve aggregates with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            ids: Sequence of aggregate IDs
            uow: Unit of work
            specification: Optional additional specification to compose with.

        Returns:
            List of aggregates filtered by tenant (via specification)

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        if is_system_tenant():
            return await super().retrieve(ids, uow, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = require_tenant()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Retrieving entities with tenant specification",
            extra={"tenant_id": tenant_id, "ids_count": len(ids)},
        )

        return await super().retrieve(ids, uow, specification=combined)  # type: ignore[misc, no-any-return]


class MultitenantQueryPersistenceMixin:
    """Mixin for IQueryPersistence with specification-based tenant filtering.

    Uses the Specification pattern to compose tenant filters with queries.
    The underlying implementation evaluates the specification at the database level.

    DTOs without tenant_id field are allowed through (tenant-agnostic DTOs).

    How it works:
        1. Mixin creates an AttributeSpecification for tenant_id
        2. Specification is evaluated by underlying implementation
        3. SQLAlchemy adds WHERE tenant_id = ? clause
        4. MongoDB adds {tenant_id: '...'} filter

    Usage:
        class MyQueryPersistence(
            MultitenantQueryPersistenceMixin,
            SQLAlchemyQueryPersistence
        ):
            # Base implementation already handles specifications
            pass
    """

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for database queries.

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An ISpecification that filters by tenant_id.
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr="tenant_id",
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fallback to dict-based specification
            return {"attr": "tenant_id", "op": "eq", "value": tenant_id}

    def _compose_specs(self, tenant_spec: Any, other: Any | None) -> Any:
        """Compose tenant specification with an optional additional specification.

        Args:
            tenant_spec: The tenant specification.
            other: Optional additional specification to compose with.

        Returns:
            The composed specification, or just tenant_spec if other is None.
        """
        if other is None:
            return tenant_spec
        if hasattr(tenant_spec, "__and__") and hasattr(other, "__and__"):
            try:
                return tenant_spec & other
            except (TypeError, AttributeError):
                pass
        return tenant_spec

    async def fetch(
        self,
        ids: Sequence[T_ID],
        uow: UnitOfWork,
        *,
        specification: Any | None = None,
    ) -> list[T_Result]:
        """Fetch result DTOs with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            ids: Sequence of entity IDs
            uow: Unit of work
            specification: Optional additional specification to compose with.

        Returns:
            List of result DTOs filtered by tenant (via specification)

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        if is_system_tenant():
            return await super().fetch(ids, uow, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = require_tenant()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Fetching results with tenant specification",
            extra={"tenant_id": tenant_id, "ids_count": len(ids)},
        )

        return await super().fetch(ids, uow, specification=combined)  # type: ignore[misc, no-any-return]


class MultitenantQuerySpecificationPersistenceMixin:
    """Mixin for IQuerySpecificationPersistence with specification-based tenant filtering.

    Composes the user's specification with a tenant specification using AND logic.
    The underlying implementation evaluates the combined specification at the database level.

    How it works:
        1. Mixin creates an AttributeSpecification for tenant_id
        2. Composes with user's criteria: (tenant_spec AND user_spec)
        3. Implementation evaluates combined specification
        4. SQLAlchemy: WHERE tenant_id = ? AND (user criteria)
        5. MongoDB: {$and: [{tenant_id: '...'}, (user criteria)]}

    Usage:
        class MyQuerySpecPersistence(
            MultitenantQuerySpecificationPersistenceMixin,
            SQLAlchemyQuerySpecificationPersistence
        ):
            # Base implementation already handles specification composition
            pass
    """

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for database queries.

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An ISpecification that filters by tenant_id.
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr="tenant_id",
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fallback to dict-based specification
            return {"attr": "tenant_id", "op": "eq", "value": tenant_id}

    def _compose_specifications(self, tenant_spec: Any, user_criteria: Any) -> Any:
        """Compose tenant specification with user criteria using AND.

        Args:
            tenant_spec: The tenant specification.
            user_criteria: The user's query criteria.

        Returns:
            Combined specification (tenant_spec AND user_criteria).
        """
        if user_criteria is None:
            return tenant_spec

        # Try ISpecification composition with & operator
        if hasattr(tenant_spec, "__and__") and hasattr(user_criteria, "__and__"):
            try:
                return tenant_spec & user_criteria
            except (TypeError, AttributeError):
                pass

        # Try dict-based composition
        if isinstance(tenant_spec, dict) and isinstance(user_criteria, dict):
            return {"op": "and", "conditions": [tenant_spec, user_criteria]}

        # Fallback: wrap in AND structure
        return {"op": "and", "conditions": [tenant_spec, user_criteria]}

    def fetch(
        self,
        criteria: ISpecification[Any] | Any,
        uow: UnitOfWork,
    ) -> SearchResult[T_Result]:
        """Fetch results with specification-based tenant filtering.

        Composes tenant specification with user's criteria:
            WHERE tenant_id = ? AND (user criteria)

        Args:
            criteria: Specification or QueryOptions
            uow: Unit of work

        Returns:
            Search results filtered by tenant (via composed specification)

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        if is_system_tenant():
            return super().fetch(criteria, uow)  # type: ignore[misc, no-any-return]

        tenant_id = require_tenant()
        tenant_spec = self._build_tenant_specification(tenant_id)

        # Compose tenant filter with user criteria
        combined_criteria = self._compose_specifications(tenant_spec, criteria)

        logger.debug(
            "Fetching results with composed tenant specification",
            extra={
                "tenant_id": tenant_id,
                "has_user_criteria": criteria is not None,
            },
        )

        # Evaluate combined specification at database level
        return super().fetch(combined_criteria, uow)  # type: ignore[misc, no-any-return]
