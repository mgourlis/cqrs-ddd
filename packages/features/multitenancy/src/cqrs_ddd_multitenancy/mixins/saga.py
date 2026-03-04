"""Multitenant saga repository mixin for automatic tenant filtering.

This mixin automatically injects tenant_id filters into all saga repository
operations when composed with a base saga repository class via MRO.

Filtering is pushed to the persistence layer via specification
composition — no in-memory post-fetch filtering.

Usage:
    class MySagaRepository(MultitenantSagaMixin, SQLAlchemySagaRepository):
        pass

The mixin must appear BEFORE the base repository in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import TenantContextMissingError

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.sagas.state import SagaState
    from cqrs_ddd_core.ports.search_result import SearchResult

__all__ = [
    "MultitenantSagaMixin",
]

logger = logging.getLogger(__name__)


class MultitenantSagaMixin:
    """Mixin that adds automatic tenant filtering to saga repository operations.

    This mixin intercepts all saga repository methods to inject tenant_id
    filtering. It should be used via MRO composition:

        class MySagaRepo(MultitenantSagaMixin, SQLAlchemySagaRepository):
            pass

    Key behaviors:
    - **add()**: Injects tenant_id into saga state metadata before persisting
    - **get()**: Returns None for cross-tenant access (silent denial)
    - **find_by_correlation_id()**: Validates tenant on result
    - **find_stalled_sagas()**: Passes tenant spec for DB-level filtering
    - **find_suspended_sagas()**: Passes tenant spec for DB-level filtering
    - All other query methods use specification-based filtering

    Attributes:
        _tenant_column: The column name for tenant filtering (default: "tenant_id")

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base repository class.
    """

    # These can be overridden in subclasses
    _tenant_column: str = "tenant_id"

    def _get_tenant_column(self) -> str:
        """Get the tenant column name."""
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
                "Tenant context required for saga operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for saga filtering.

        Uses ``AttributeSpecification`` targeting the dedicated ``tenant_id``
        column for DB-level WHERE clause filtering (not in-memory metadata).
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr=self._get_tenant_column(),
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            logger.warning(
                "cqrs-ddd-specifications not installed, using dict filter fallback",
                extra={"tenant_id": tenant_id},
            )
            return {
                "attr": self._get_tenant_column(),
                "op": "eq",
                "val": tenant_id,
            }

    def _get_tenant_id_from_saga(self, saga_state: SagaState) -> str | None:
        """Extract tenant_id from a saga state.

        Resolution order:
        1. Dedicated ``tenant_id`` attribute (DB column)
        2. Metadata dict fallback (backward compatibility)
        """
        tenant_column = self._get_tenant_column()
        # 1. Dedicated attribute
        val = getattr(saga_state, tenant_column, None)
        if val is not None:
            return val  # type: ignore[no-any-return]
        # 2. Metadata fallback
        return saga_state.metadata.get(tenant_column)

    def _inject_tenant_to_saga(self, saga_state: SagaState, tenant_id: str) -> None:
        """Inject tenant_id into saga state.

        Sets BOTH the dedicated ``tenant_id`` attribute (for DB-level spec
        filtering) and the metadata key (for backward compatibility).

        Raises:
            CrossTenantAccessError: If saga belongs to different tenant.
        """
        tenant_column = self._get_tenant_column()
        current_tenant = self._get_tenant_id_from_saga(saga_state)

        if current_tenant is not None and current_tenant != tenant_id:
            from ..exceptions import CrossTenantAccessError

            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=current_tenant,
                resource_type="SagaState",
                resource_id=saga_state.id,
            )

        # Always ensure dedicated attribute is set
        if getattr(saga_state, tenant_column, None) is None:
            object.__setattr__(saga_state, tenant_column, tenant_id)

        # Always ensure metadata has tenant for backward compat
        if tenant_column not in saga_state.metadata:
            metadata = dict(saga_state.metadata)
            metadata[tenant_column] = tenant_id
            object.__setattr__(saga_state, "metadata", metadata)

    # ── IRepository Protocol Methods ─────────────────────────────────────

    async def add(self, saga_state: SagaState) -> None:
        """Add a new saga state with automatic tenant injection."""
        if is_system_tenant():
            return await super().add(saga_state)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        self._inject_tenant_to_saga(saga_state, tenant_id)
        await super().add(saga_state)  # type: ignore[misc]

    async def get(self, saga_id: str) -> SagaState | None:
        """Get a saga state by ID with tenant filtering (silent denial)."""
        if is_system_tenant():
            return await super().get(saga_id)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        saga_state = await super().get(saga_id)  # type: ignore[misc]

        if saga_state is None:
            return None

        saga_tenant = self._get_tenant_id_from_saga(saga_state)
        if saga_tenant is not None and saga_tenant != tenant_id:
            logger.debug(
                "Cross-tenant saga access attempt: saga tenant=%s, context tenant=%s",
                saga_tenant,
                tenant_id,
            )
            return None

        return saga_state  # type: ignore[no-any-return]

    async def update(self, saga_state: SagaState) -> None:
        """Update a saga state with tenant validation."""
        if is_system_tenant():
            return await super().update(saga_state)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        saga_tenant = self._get_tenant_id_from_saga(saga_state)

        if saga_tenant is not None and saga_tenant != tenant_id:
            from ..exceptions import CrossTenantAccessError

            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=saga_tenant,
                resource_type="SagaState",
                resource_id=saga_state.id,
            )

        await super().update(saga_state)  # type: ignore[misc]

    async def delete(self, saga_state: SagaState) -> None:
        """Delete a saga state with tenant validation."""
        if is_system_tenant():
            return await super().delete(saga_state)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        saga_tenant = self._get_tenant_id_from_saga(saga_state)

        if saga_tenant is not None and saga_tenant != tenant_id:
            from ..exceptions import CrossTenantAccessError

            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=saga_tenant,
                resource_type="SagaState",
                resource_id=saga_state.id,
            )

        await super().delete(saga_state)  # type: ignore[misc]

    async def list_all(
        self: Any,
        entity_ids: list[str] | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[SagaState]:
        """List sagas with spec-based tenant filtering.

        Composes tenant specification with any provided specification
        and delegates to the base implementation for DB-level filtering.
        """
        if is_system_tenant():
            return await super().list_all(  # type: ignore[misc, no-any-return]
                entity_ids, uow, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().list_all(  # type: ignore[misc, no-any-return]
            entity_ids, uow, specification=combined
        )

    async def search(
        self: Any,
        criteria: Any,
        uow: Any = None,
    ) -> SearchResult[SagaState]:
        """Search sagas with automatic tenant filtering via specification.

        Composes the tenant specification with the provided criteria.
        """
        if is_system_tenant():
            return await super().search(criteria, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)

        # Compose tenant spec with criteria
        if criteria is not None and hasattr(criteria, "__and__"):
            combined = tenant_spec & criteria
        else:
            combined = tenant_spec

        return await super().search(combined, uow)  # type: ignore[misc, no-any-return]

    # ── ISagaRepository Protocol Methods ─────────────────────────────────

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        """Find saga by correlation ID with tenant filtering (silent denial)."""
        if is_system_tenant():
            return await super().find_by_correlation_id(  # type: ignore[misc, no-any-return]
                correlation_id, saga_type
            )

        tenant_id = self._require_tenant_context()
        saga_state = await super().find_by_correlation_id(  # type: ignore[misc]
            correlation_id, saga_type
        )

        if saga_state is None:
            return None

        saga_tenant = self._get_tenant_id_from_saga(saga_state)
        if saga_tenant is not None and saga_tenant != tenant_id:
            logger.debug(
                "Cross-tenant saga access attempt: saga tenant=%s, context tenant=%s",
                saga_tenant,
                tenant_id,
            )
            return None

        return saga_state  # type: ignore[no-any-return]

    async def find_stalled_sagas(
        self: Any, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        """Find stalled sagas via specification-based tenant filtering.

        System tenant returns ALL stalled sagas (e.g. recovery workers).
        """
        if is_system_tenant():
            return await super().find_stalled_sagas(  # type: ignore[misc, no-any-return]
                limit=limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().find_stalled_sagas(  # type: ignore[misc, no-any-return]
            limit=limit, specification=combined
        )

    async def find_suspended_sagas(
        self: Any, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        """Find suspended sagas via specification-based tenant filtering."""
        if is_system_tenant():
            return await super().find_suspended_sagas(  # type: ignore[misc, no-any-return]
                limit=limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().find_suspended_sagas(  # type: ignore[misc, no-any-return]
            limit=limit, specification=combined
        )

    async def find_expired_suspended_sagas(
        self: Any, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        """Find expired suspended sagas via specification-based tenant filtering."""
        if is_system_tenant():
            return await super().find_expired_suspended_sagas(  # type: ignore[misc, no-any-return]
                limit=limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().find_expired_suspended_sagas(  # type: ignore[misc, no-any-return]
            limit=limit, specification=combined
        )

    async def find_running_sagas_with_tcc_steps(
        self: Any, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        """Find running sagas with TCC steps via spec-based tenant filtering."""
        if is_system_tenant():
            return await super().find_running_sagas_with_tcc_steps(  # type: ignore[misc, no-any-return]
                limit=limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().find_running_sagas_with_tcc_steps(  # type: ignore[misc, no-any-return]
            limit=limit, specification=combined
        )
