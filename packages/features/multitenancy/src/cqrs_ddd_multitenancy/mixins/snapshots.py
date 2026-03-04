"""Multitenant snapshot store mixin for automatic tenant filtering.

This mixin automatically injects tenant_id filters into all snapshot store
operations when composed with a base snapshot store class via MRO.

Usage:
    class MySnapshotStore(MultitenantSnapshotMixin, SQLAlchemySnapshotStore):
        pass

The mixin must appear BEFORE the base store in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import TenantContextMissingError

__all__ = [
    "MultitenantSnapshotMixin",
]

logger = logging.getLogger(__name__)


class MultitenantSnapshotMixin:
    """Mixin that adds automatic tenant filtering to snapshot store operations.

    This mixin intercepts all snapshot store methods to inject tenant_id
    filtering **via the specification parameter**. It should be used via
    MRO composition:

        class MySnapshotStore(MultitenantSnapshotMixin, SQLAlchemySnapshotStore):
            pass

    Key behaviors:
    - **save_snapshot()**: Passes tenant specification so the store can
      persist ``tenant_id`` alongside the snapshot.
    - **get_latest_snapshot()**: Composes a tenant specification so the
      store filters at the DB level.
    - **delete_snapshot()**: Composes a tenant specification for deletion.

    Attributes:
        _tenant_column: The column name for tenant filtering (default: "tenant_id")

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base store class.
    """

    # These can be overridden in subclasses
    _tenant_column: str = "tenant_id"

    def _get_tenant_column(self) -> str:
        """Get the tenant column name.

        Override this to customize the tenant column name per store.

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
                "Tenant context required for snapshot operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

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
                attr=self._get_tenant_column(),
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fallback to dict-based specification
            return {"attr": self._get_tenant_column(), "op": "eq", "value": tenant_id}

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

    # ── ISnapshotStore Protocol Methods ─────────────────────────────────

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
        *,
        specification: Any | None = None,
    ) -> None:
        """Save a snapshot with tenant specification.

        Injects ``tenant_id`` into ``snapshot_data`` and passes a tenant
        specification so the persistence layer stores it in the
        dedicated column.

        Args:
            aggregate_type: Type name of the aggregate (e.g., "Order").
            aggregate_id: The aggregate's ID.
            snapshot_data: Serialized state dict.
            version: The event version at the time of snapshot.
            specification: Optional additional specification to compose with.
        """
        if is_system_tenant():
            return await super().save_snapshot(  # type: ignore[misc, no-any-return]
                aggregate_type,
                aggregate_id,
                snapshot_data,
                version,
                specification=specification,
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        # Inject tenant_id into snapshot data for redundancy
        tenant_column = self._get_tenant_column()
        if tenant_column not in snapshot_data:
            snapshot_data = {**snapshot_data, tenant_column: tenant_id}

        logger.debug(
            "Saving snapshot with tenant specification",
            extra={
                "tenant_id": tenant_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
            },
        )

        await super().save_snapshot(  # type: ignore[misc]
            aggregate_type,
            aggregate_id,
            snapshot_data,
            version,
            specification=combined,
        )

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: Any | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve the most recent snapshot for an aggregate with tenant filtering.

        Uses specification-based filtering at the DB level.

        Args:
            aggregate_type: Type name of the aggregate.
            aggregate_id: The aggregate's ID.
            specification: Optional additional specification to compose with.

        Returns:
            Dict with snapshot_data, version, and created_at.
            None if no snapshot exists for this tenant.
        """
        if is_system_tenant():
            return await super().get_latest_snapshot(  # type: ignore[misc, no-any-return]
                aggregate_type, aggregate_id, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting latest snapshot with tenant specification",
            extra={
                "tenant_id": tenant_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
            },
        )

        return await super().get_latest_snapshot(  # type: ignore[misc, no-any-return]
            aggregate_type, aggregate_id, specification=combined
        )

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: Any | None = None,
    ) -> None:
        """Delete all snapshots for an aggregate with tenant filtering.

        Uses specification-based filtering at the DB level.

        Args:
            aggregate_type: Type name of the aggregate.
            aggregate_id: The aggregate's ID.
            specification: Optional additional specification to compose with.
        """
        if is_system_tenant():
            return await super().delete_snapshot(  # type: ignore[misc, no-any-return]
                aggregate_type, aggregate_id, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Deleting snapshot with tenant specification",
            extra={
                "tenant_id": tenant_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
            },
        )

        await super().delete_snapshot(  # type: ignore[misc]
            aggregate_type, aggregate_id, specification=combined
        )
