"""Multitenant repository mixin for automatic tenant filtering.

This mixin automatically injects tenant_id filters into all repository
operations when composed with a base repository class via MRO.

Usage:
    class MyRepository(MultitenantRepositoryMixin, SQLAlchemyRepository):
        pass

The mixin must appear BEFORE the base repository in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import CrossTenantAccessError, TenantContextMissingError

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantRepositoryMixin",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")
ID = TypeVar("ID", str, int)


class MultitenantRepositoryMixin:
    """Mixin that adds automatic tenant filtering to repository operations.

    This mixin intercepts all repository methods to inject tenant_id
    filtering. It should be used via MRO composition:

        class MyRepo(MultitenantRepositoryMixin, SQLAlchemyRepository):
            pass

    Key behaviors:
    - **add()**: Injects tenant_id into entity before persisting
    - **get()**: Returns None for cross-tenant access (silent denial)
    - **delete()**: Adds tenant filter to prevent cross-tenant deletion
    - **list_all()**: Filters by tenant_id
    - **search()**: Composes tenant specification with query criteria

    Attributes:
        _tenant_column: The column name for tenant filtering (default: "tenant_id")
        _allow_cross_tenant_delete: Whether to raise on cross-tenant delete (default: False)

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base repository class.
    """

    # These can be overridden in subclasses
    _tenant_column: str = "tenant_id"
    _allow_cross_tenant_delete: bool = False

    def _get_tenant_column(self) -> str:
        """Get the tenant column name.

        Override this to customize the tenant column name per repository.

        Returns:
            The tenant column name.
        """
        return getattr(self, "_tenant_column", "tenant_id")

    def _require_tenant_context(self) -> str:
        """Require and return the current tenant ID.

        Returns:
            The current tenant ID.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant = get_current_tenant_or_none()
        if tenant is None and not is_system_tenant():
            raise TenantContextMissingError(
                "Tenant context required for repository operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _get_tenant_id_from_entity(self, entity: Any) -> str | None:
        """Extract tenant_id from an entity.

        Args:
            entity: The entity to extract tenant_id from.

        Returns:
            The tenant_id, or None if not present.
        """
        if hasattr(entity, self._get_tenant_column()):
            return getattr(entity, self._get_tenant_column())  # type: ignore[no-any-return]
        if hasattr(entity, "model_dump"):
            data = entity.model_dump()
            return data.get(self._get_tenant_column())  # type: ignore[no-any-return]
        return None

    def _set_tenant_id_on_entity(self, entity: T, tenant_id: str) -> T:
        """Set tenant_id on an entity.

        Args:
            entity: The entity to modify.
            tenant_id: The tenant ID to set.

        Returns:
            The entity with tenant_id set.
        """
        tenant_column = self._get_tenant_column()

        # Try direct attribute set (for mutable entities)
        if hasattr(entity, "__setattr__"):
            try:
                setattr(entity, tenant_column, tenant_id)
                return entity
            except (AttributeError, TypeError):
                pass

        # Try Pydantic model_copy (for immutable entities)
        if hasattr(entity, "model_copy"):
            try:
                return entity.model_copy(update={tenant_column: tenant_id})  # type: ignore[no-any-return]
            except Exception:
                pass

        # Cannot set tenant_id
        logger.warning(
            "Could not set tenant_id on entity",
            extra={
                "entity_type": type(entity).__name__,
                "tenant_column": tenant_column,
            },
        )
        return entity

    def _build_tenant_specification(self, tenant_id: str) -> ISpecification[T]:  # type: ignore[type-var]
        """Build a tenant specification using ISpecification pattern.

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An ISpecification that filters by tenant_id.

        Raises:
            ImportError: If cqrs-ddd-specifications is not installed.
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            # Create tenant specification with default registry
            return AttributeSpecification(  # type: ignore[return-value]
                attr=self._get_tenant_column(),
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fall back to dict if specifications not available
            # This should only happen in environments without the package
            logger.warning(
                "cqrs-ddd-specifications not installed, using dict filter fallback",
                extra={"tenant_id": tenant_id},
            )
            return {  # type: ignore[return-value]
                "attr": self._get_tenant_column(),
                "op": "=",
                "val": tenant_id,
            }

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

    # -----------------------------------------------------------------------
    # Repository method overrides
    # -----------------------------------------------------------------------

    async def add(self: Any, entity: T, uow: UnitOfWork | None = None) -> ID:
        """Add entity with tenant_id injection.

        Args:
            entity: The entity to add.
            uow: Optional unit of work.

        Returns:
            The entity ID.

        Raises:
            TenantContextMissingError: If no tenant context.
        """
        if is_system_tenant():
            # System operations bypass tenant injection
            return await super().add(entity, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()

        # Check if entity already has a tenant_id
        existing_tenant = self._get_tenant_id_from_entity(entity)
        if existing_tenant is not None and existing_tenant != tenant_id:
            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=existing_tenant,
                resource_type=type(entity).__name__,
            )

        # Inject tenant_id
        entity = self._set_tenant_id_on_entity(entity, tenant_id)

        logger.debug(
            "Adding entity with tenant",
            extra={
                "tenant_id": tenant_id,
                "entity_type": type(entity).__name__,
            },
        )

        return await super().add(entity, uow)  # type: ignore[misc, no-any-return]

    async def get(
        self: Any,
        entity_id: ID,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> T | None:
        """Get entity with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            entity_id: The entity ID.
            uow: Optional unit of work.
            specification: Optional additional specification to compose with.

        Returns:
            The entity if found and passes tenant filter, None otherwise.
        """
        if is_system_tenant():
            return await super().get(entity_id, uow, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        return await super().get(entity_id, uow, specification=combined)  # type: ignore[misc, no-any-return]

    async def delete(
        self: Any,
        entity_id: ID,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> ID:
        """Delete entity with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            entity_id: The entity ID.
            uow: Optional unit of work.
            specification: Optional additional specification to compose with.

        Returns:
            The deleted entity ID.
        """
        if is_system_tenant():
            return await super().delete(entity_id, uow, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        return await super().delete(entity_id, uow, specification=combined)  # type: ignore[misc, no-any-return]

    async def list_all(
        self: Any,
        entity_ids: list[ID] | None = None,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> list[T]:
        """List all entities with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            entity_ids: Optional list of entity IDs to filter.
            uow: Optional unit of work.
            specification: Optional additional specification to compose with.

        Returns:
            List of entities filtered by tenant (via specification).
        """
        if is_system_tenant():
            return await super().list_all(entity_ids, uow, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        return await super().list_all(entity_ids, uow, specification=combined)  # type: ignore[misc, no-any-return]

    async def search(
        self: Any,
        criteria: ISpecification[T] | Any,  # type: ignore[type-var]
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]:
        """Search with automatic tenant filtering.

        Composes the provided criteria with a tenant specification.

        Args:
            criteria: The search criteria (ISpecification or QueryOptions).
            uow: Optional unit of work.

        Returns:
            SearchResult filtered by tenant.
        """
        if is_system_tenant():
            return await super().search(criteria, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()

        # Try to compose tenant filter with existing criteria
        combined_criteria = self._compose_tenant_filter(criteria, tenant_id)

        return await super().search(combined_criteria, uow)  # type: ignore[misc, no-any-return]

    def _compose_tenant_filter(
        self,
        criteria: ISpecification[T] | Any,  # type: ignore[type-var]
        tenant_id: str,
    ) -> ISpecification[T] | Any:  # type: ignore[type-var]
        """Compose tenant filter with existing criteria using ISpecification.

        Args:
            criteria: The original criteria.
            tenant_id: The tenant ID to filter by.

        Returns:
            Combined criteria with tenant filter.
        """
        # Build tenant specification
        tenant_spec: Any = self._build_tenant_specification(tenant_id)

        # If criteria is already an ISpecification, compose with & operator
        if hasattr(criteria, "__and__"):
            try:
                # Use specification composition
                return tenant_spec & criteria
            except (TypeError, AttributeError):
                # Composition failed, fall through
                pass

        # If criteria is a dict, convert to specification or compose as dict
        if isinstance(criteria, dict):
            if isinstance(tenant_spec, dict):
                # Both are dicts, compose as dicts
                return {
                    "op": "and",
                    "conditions": [tenant_spec, criteria],
                }
            # tenant_spec is ISpecification, criteria is dict
            # Try to convert criteria to ISpecification
            try:
                from cqrs_ddd_specifications import SpecificationFactory
                from cqrs_ddd_specifications.operators_memory import (
                    build_default_registry,
                )

                factory_spec: Any = SpecificationFactory.from_dict(
                    criteria, registry=build_default_registry()
                )
                return tenant_spec & factory_spec
            except (ImportError, Exception):
                # Fall back to dict composition
                return {
                    "op": "and",
                    "conditions": [tenant_spec.to_dict(), criteria],
                }

        # Return tenant spec if no criteria provided or composition failed
        if criteria is None:
            return tenant_spec

        # Last resort: return criteria as-is (may result in in-memory filtering)
        logger.warning(
            "Could not compose tenant filter with criteria, tenant filtering may happen in-memory",
            extra={"tenant_id": tenant_id, "criteria_type": type(criteria).__name__},
        )
        return criteria


class StrictMultitenantRepositoryMixin(MultitenantRepositoryMixin):
    """Strict variant that raises errors on cross-tenant operations.

    Unlike the base mixin which silently denies cross-tenant access,
    this variant raises CrossTenantAccessError for all cross-tenant
    operations. Use when you need to detect and log potential security issues.

    Usage:
        class MyRepo(StrictMultitenantRepositoryMixin, SQLAlchemyRepository):
            pass
    """

    _allow_cross_tenant_delete: bool = True  # Raise on cross-tenant delete

    async def get(
        self: Any,
        entity_id: ID,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> T | None:
        """Get entity with strict tenant validation.

        Raises CrossTenantAccessError for cross-tenant access attempts.

        Args:
            entity_id: The entity ID.
            uow: Optional unit of work.
            specification: Optional additional specification to compose with.

        Returns:
            The entity if found and belongs to current tenant.

        Raises:
            CrossTenantAccessError: If entity belongs to different tenant.
        """
        result = await super().get(entity_id, uow, specification=specification)  # type: ignore[func-returns-value]

        if result is None:
            return None

        if is_system_tenant():
            return result

        tenant_id = get_current_tenant_or_none()
        entity_tenant = self._get_tenant_id_from_entity(result)

        if (
            entity_tenant is not None
            and tenant_id is not None
            and entity_tenant != tenant_id
        ):
            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=entity_tenant,
                resource_type=type(result).__name__,
                resource_id=str(entity_id),
            )

        return result
