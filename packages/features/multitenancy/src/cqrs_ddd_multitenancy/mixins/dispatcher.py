"""Multitenant persistence dispatcher mixin for automatic tenant context propagation.

This mixin wraps all dispatcher operations with tenant context injection
and filtering when composed with a base dispatcher class via MRO.

CRITICAL REQUIREMENT:
    The underlying persistence implementation MUST filter by tenant_id
    at the DATABASE QUERY LEVEL, not in memory. This mixin only ensures
    tenant context is available - it does NOT do in-memory filtering.

    Example (SQLAlchemy):
        SELECT * FROM entities
        WHERE id IN (...) AND tenant_id = :tenant_id

    Your entities MUST have a dedicated tenant_id column (not JSONB metadata).
    Use MultitenantMixin from cqrs_ddd_multitenancy.domain to add this field.

Usage:
    class MyDispatcher(MultitenantDispatcherMixin, PersistenceDispatcher):
        pass

The mixin must appear BEFORE the base dispatcher in the MRO to ensure
method resolution overrides the base methods correctly.
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

    from cqrs_ddd_advanced_core.ports import T_Criteria
    from cqrs_ddd_core.domain.aggregate import AggregateRoot
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantDispatcherMixin",
]

logger = logging.getLogger(__name__)

T_Entity = TypeVar("T_Entity", bound="AggregateRoot[Any]")
T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int)


class MultitenantDispatcherMixin:
    """Mixin that adds tenant context propagation to persistence dispatcher.

    This mixin ensures all dispatcher operations maintain tenant context:
    - **apply()**: Injects tenant_id into entity and event metadata
    - **fetch_domain()**: Filters entities by tenant_id via specification
    - **fetch()**: Composes queries with tenant specification

    The mixin uses MRO composition pattern:
        class MyDispatcher(MultitenantDispatcherMixin, PersistenceDispatcher):
            pass

    Requirements:
        - Entities MUST have a dedicated tenant_id field
        - Use MultitenantMixin from cqrs_ddd_multitenancy.domain
        - Database MUST have tenant_id as a dedicated column (not JSONB)
    """

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for database queries."""
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
            return {"attr": "tenant_id", "op": "eq", "value": tenant_id}

    def _compose_specs(self, tenant_spec: Any, other: Any | None) -> Any:
        """Compose tenant specification with an optional additional specification."""
        if other is None:
            return tenant_spec
        if hasattr(tenant_spec, "__and__") and hasattr(other, "__and__"):
            try:
                return tenant_spec & other
            except (TypeError, AttributeError):
                pass
        return tenant_spec

    def _set_tenant_on_entity(
        self, entity: AggregateRoot[T_ID], tenant_id: str
    ) -> AggregateRoot[T_ID]:
        """Return entity with tenant_id set, respecting immutability."""
        try:
            if hasattr(entity, "model_copy"):
                return entity.model_copy(update={"tenant_id": tenant_id})
            entity.tenant_id = tenant_id  # type: ignore[attr-defined]
            return entity
        except (AttributeError, TypeError) as e:
            logger.warning(
                "Could not set tenant_id on entity",
                extra={"entity_type": type(entity).__name__, "error": str(e)},
            )
            return entity

    @staticmethod
    def _inject_tenant_into_events(events: list[DomainEvent], tenant_id: str) -> None:
        """Stamp tenant_id into each event's metadata dict."""
        for event in events:
            if hasattr(event, "metadata"):
                if isinstance(event.metadata, dict):
                    event.metadata["tenant_id"] = tenant_id
                else:
                    event.metadata = {"tenant_id": tenant_id}
            else:
                try:
                    event.metadata = {"tenant_id": tenant_id}  # type: ignore[misc]
                except (AttributeError, TypeError):
                    pass

    async def apply(
        self,
        entity: AggregateRoot[T_ID],
        uow: UnitOfWork | None = None,
        events: list[DomainEvent] | None = None,
    ) -> T_ID:
        """Apply write operation with tenant context injection.

        Injects tenant_id into entity's dedicated tenant_id field.
        Also injects tenant_id into event metadata for outbox pattern.

        Args:
            entity: Aggregate root to persist (must have tenant_id field)
            uow: Optional unit of work
            events: Optional list of domain events

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

        entity = self._set_tenant_on_entity(entity, tenant_id)

        if events:
            self._inject_tenant_into_events(events, tenant_id)

        logger.debug(
            "Applying entity with tenant context",
            extra={"tenant_id": tenant_id, "entity_type": type(entity).__name__},
        )

        # Call parent apply method via super()
        return await super().apply(entity, uow, events)  # type: ignore[misc, no-any-return]

    async def fetch_domain(
        self,
        entity_type: type[T_Entity],
        ids: Sequence[T_ID],
        uow: UnitOfWork | None = None,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[T_Entity]:
        """Fetch domain entities with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            entity_type: Type of entity to fetch
            ids: Sequence of entity IDs
            uow: Optional unit of work
            specification: Optional additional specification to compose with.

        Returns:
            List of entities filtered by tenant (via specification)

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        if is_system_tenant():
            return await super().fetch_domain(  # type: ignore[misc, no-any-return]
                entity_type, ids, uow, specification=specification
            )

        tenant_id = require_tenant()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Fetching domain entities with tenant specification",
            extra={
                "tenant_id": tenant_id,
                "entity_type": entity_type.__name__,
                "ids_count": len(ids),
            },
        )

        return await super().fetch_domain(  # type: ignore[misc, no-any-return]
            entity_type, ids, uow, specification=combined
        )

    async def fetch(
        self,
        result_type: type[T_Result],
        criteria: T_Criteria[Any],
        uow: UnitOfWork | None = None,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> SearchResult[T_Result]:
        """Fetch read models with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            result_type: Type of result DTO
            criteria: Query criteria (IDs, ISpecification, or QueryOptions)
            uow: Optional unit of work
            specification: Optional additional specification to compose with.

        Returns:
            Search results filtered by tenant

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        if is_system_tenant():
            return await super().fetch(  # type: ignore[misc, no-any-return]
                result_type, criteria, uow, specification=specification
            )

        tenant_id = require_tenant()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Fetching results with tenant specification",
            extra={"tenant_id": tenant_id, "result_type": result_type.__name__},
        )

        return await super().fetch(  # type: ignore[misc, no-any-return]
            result_type, criteria, uow, specification=combined
        )
