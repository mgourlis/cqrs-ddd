"""Multitenant command scheduler mixin for automatic tenant filtering.

This mixin automatically injects tenant_id filters into all command scheduler
operations when composed with a base scheduler class via MRO.

Filtering is pushed to the persistence layer via specification
composition — no in-memory post-fetch filtering.

Usage:
    class MyCommandScheduler(MultitenantCommandSchedulerMixin, RedisCommandScheduler):
        pass

The mixin must appear BEFORE the base scheduler in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import TenantContextMissingError

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command

__all__ = [
    "MultitenantCommandSchedulerMixin",
]

logger = logging.getLogger(__name__)


class MultitenantCommandSchedulerMixin:
    """Mixin that adds automatic tenant filtering to command scheduler operations.

    This mixin intercepts all scheduler methods to inject tenant_id
    filtering. It should be used via MRO composition:

        class MyScheduler(MultitenantCommandSchedulerMixin, RedisCommandScheduler):
            pass

    Key behaviors:
    - **schedule()**: Injects tenant_id into command metadata
    - **get_due_commands()**: Passes tenant spec for DB-level filtering
    - **cancel()**: Validates tenant ownership
    - **delete_executed()**: Validates tenant ownership

    Attributes:
        _tenant_metadata_key: The metadata key for tenant ID (default: "_tenant_id")
    """

    # These can be overridden in subclasses
    _tenant_metadata_key: str = "_tenant_id"

    def _get_tenant_metadata_key(self) -> str:
        """Get the tenant metadata key."""
        return getattr(self, "_tenant_metadata_key", "_tenant_id")

    def _require_tenant_context(self) -> str:
        """Require and return the current tenant ID.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant = get_current_tenant_or_none()
        if tenant is None and not is_system_tenant():
            raise TenantContextMissingError(
                "Tenant context required for scheduling operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for scheduling filtering.

        Uses ``AttributeSpecification`` targeting the dedicated ``tenant_id``
        attribute for DB-level WHERE clause filtering.
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
            logger.warning(
                "cqrs-ddd-specifications not installed, using dict filter fallback",
                extra={"tenant_id": tenant_id},
            )
            return {
                "attr": "tenant_id",
                "op": "eq",
                "val": tenant_id,
            }

    def _inject_tenant_to_command(
        self, command: Command[Any], tenant_id: str
    ) -> Command[Any]:
        """Inject tenant_id into command.

        Sets BOTH the dedicated ``tenant_id`` attribute (for DB-level spec
        filtering) and the ``_metadata`` dict key (for backward compat).
        """
        tenant_key = self._get_tenant_metadata_key()

        # Set dedicated attribute for spec evaluation
        object.__setattr__(command, "tenant_id", tenant_id)

        # Also set metadata for backward compatibility
        if hasattr(command, "_metadata"):
            metadata = getattr(command, "_metadata", {})
            if tenant_key not in metadata:
                metadata[tenant_key] = tenant_id
                object.__setattr__(command, "_metadata", metadata)
        else:
            object.__setattr__(command, "_metadata", {tenant_key: tenant_id})

        return command

    def _get_tenant_from_command(self, command: Command[Any]) -> str | None:
        """Extract tenant_id from command.

        Resolution order:
        1. Dedicated ``tenant_id`` attribute
        2. ``_metadata`` dict fallback (backward compatibility)
        """
        # 1. Dedicated attribute
        val = getattr(command, "tenant_id", None)
        if val is not None:
            return val  # type: ignore[no-any-return]
        # 2. Metadata fallback
        tenant_key = self._get_tenant_metadata_key()
        metadata = getattr(command, "_metadata", {})
        return metadata.get(tenant_key)

    # ── ICommandScheduler Protocol Methods ───────────────────────────────

    async def schedule(
        self: Any,
        command: Command[Any],
        execute_at: datetime,
        description: str | None = None,
    ) -> str:
        """Schedule a command for future execution with tenant context."""
        if is_system_tenant():
            return await super().schedule(command, execute_at, description)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        command = self._inject_tenant_to_command(command, tenant_id)

        return await super().schedule(command, execute_at, description)  # type: ignore[misc, no-any-return]

    async def get_due_commands(
        self: Any,
        *,
        specification: Any | None = None,
    ) -> list[tuple[str, Command[Any]]]:
        """Retrieve due commands via specification-based tenant filtering.

        System tenant returns ALL due commands (e.g. background workers).
        """
        if is_system_tenant():
            return await super().get_due_commands(  # type: ignore[misc, no-any-return]
                specification=specification,
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().get_due_commands(  # type: ignore[misc, no-any-return]
            specification=combined,
        )

    async def cancel(self: Any, schedule_id: str) -> bool:
        """Cancel a scheduled command with tenant validation."""
        if is_system_tenant():
            return await super().cancel(schedule_id)  # type: ignore[misc, no-any-return]

        self._require_tenant_context()
        return await super().cancel(schedule_id)  # type: ignore[misc, no-any-return]

    async def delete_executed(self: Any, schedule_id: str) -> None:
        """Remove a command from the schedule after execution."""
        if is_system_tenant():
            return await super().delete_executed(schedule_id)  # type: ignore[misc, no-any-return]

        self._require_tenant_context()
        await super().delete_executed(schedule_id)  # type: ignore[misc]
