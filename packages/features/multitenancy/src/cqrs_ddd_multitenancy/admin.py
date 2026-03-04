"""Tenant administration operations.

Provides functionality for provisioning, deactivating, and managing tenants.
All admin operations require the  context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from .context import SYSTEM_TENANT, get_current_tenant_or_none, is_system_tenant
from .exceptions import (
    CrossTenantAccessError,
    TenantDeactivatedError,
    TenantNotFoundError,
    TenantProvisioningError,
)
from .isolation import IsolationConfig, TenantIsolationStrategy

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "TenantAdmin",
    "TenantStatus",
    "TenantInfo",
    "TenantRegistry",
]

logger = logging.getLogger(__name__)

import functools

_F = TypeVar("_F", bound="Callable[..., Any]")


def _require_system_tenant(func: _F) -> _F:
    """Decorator ensuring the current context is the system tenant."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_system_tenant():
            raise CrossTenantAccessError(
                current_tenant=get_current_tenant_or_none(),
                target_tenant=SYSTEM_TENANT,
                resource_type="TenantAdmin",
                resource_id="*",
            )
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


class TenantStatus(str, Enum):
    """Status of a tenant."""

    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"
    PROVISIONING = "provisioning"


@dataclass(frozen=True)
class TenantInfo:
    """Information about a tenant.

    Attributes:
        tenant_id: The unique tenant identifier.
        name: Human-readable tenant name.
        status: Current tenant status.
        isolation_strategy: The isolation strategy used.
        created_at: When the tenant was created.
        updated_at: When the tenant was last updated.
        deactivated_at: When the tenant was deactivated (if applicable).
        metadata: Additional tenant metadata.
    """

    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    isolation_strategy: TenantIsolationStrategy = (
        TenantIsolationStrategy.DISCRIMINATOR_COLUMN
    )
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deactivated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TenantRegistry:
    """Registry for tenant metadata.

    This is an abstract interface for storing and retrieving tenant information.
    Implementations can use databases, files, or other storage backends.
    """

    async def get(self, tenant_id: str) -> TenantInfo | None:
        """Get tenant info by ID.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            TenantInfo if found, None otherwise.
        """
        raise NotImplementedError

    async def list_all(self, *, include_deactivated: bool = False) -> list[TenantInfo]:
        """List all tenants.

        Args:
            include_deactivated: Whether to include deactivated tenants.

        Returns:
            List of tenant info objects.
        """
        raise NotImplementedError

    async def save(self, tenant: TenantInfo) -> None:
        """Save tenant info.

        Args:
            tenant: The tenant info to save.
        """
        raise NotImplementedError

    async def delete(self, tenant_id: str) -> None:
        """Delete tenant info.

        Args:
            tenant_id: The tenant identifier.
        """
        raise NotImplementedError


class InMemoryTenantRegistry(TenantRegistry):
    """In-memory tenant registry for testing and development."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantInfo] = {}

    async def get(self, tenant_id: str) -> TenantInfo | None:
        return self._tenants.get(tenant_id)

    async def list_all(self, *, include_deactivated: bool = False) -> list[TenantInfo]:
        tenants = list(self._tenants.values())
        if not include_deactivated:
            tenants = [t for t in tenants if t.status != TenantStatus.DEACTIVATED]
        return tenants

    async def save(self, tenant: TenantInfo) -> None:
        self._tenants[tenant.tenant_id] = tenant

    async def delete(self, tenant_id: str) -> None:
        self._tenants.pop(tenant_id, None)


class TenantAdmin:
    """Admin operations for tenant management.

    This class provides methods for provisioning, deactivating, and
    managing tenants. All operations require system context and should
    be gated by proper authorization checks.

    Attributes:
        registry: The tenant registry for metadata storage.
        config: The isolation configuration.
        on_provision: Optional callback after tenant provisioning.
        on_deactivate: Optional callback after tenant deactivation.

    Example:
        ```python
        admin = TenantAdmin(
            registry=db_registry,
            config=IsolationConfig(strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT),
            on_provision=create_schema,
        )

        # Provision a new tenant
        tenant = await admin.provision_tenant(
            tenant_id="tenant-123",
            name="Acme Corp",
        )

        # Deactivate a tenant
        await admin.deactivate_tenant("tenant-123")
        ```
    """

    __slots__ = (
        "_config",
        "_on_deactivate",
        "_on_provision",
        "_registry",
    )

    def __init__(
        self,
        registry: TenantRegistry,
        config: IsolationConfig,
        *,
        on_provision: Callable[[TenantInfo, AsyncSession | None], Awaitable[None]]
        | None = None,
        on_deactivate: Callable[[TenantInfo], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the tenant admin.

        Args:
            registry: The tenant registry for metadata storage.
            config: The isolation configuration.
            on_provision: Callback after provisioning (e.g., create schema).
            on_deactivate: Callback after deactivation (e.g., revoke access).
        """
        self._registry = registry
        self._config = config
        self._on_provision = on_provision
        self._on_deactivate = on_deactivate

    @property
    def registry(self) -> TenantRegistry:
        """The tenant registry."""
        return self._registry

    @property
    def config(self) -> IsolationConfig:
        """The isolation configuration."""
        return self._config

    @_require_system_tenant
    async def provision_tenant(
        self,
        tenant_id: str,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> TenantInfo:
        """Provision a new tenant.

        This creates the tenant metadata and optionally provisions
        the tenant infrastructure (schema, database, etc.).

        Args:
            tenant_id: The unique tenant identifier.
            name: Human-readable tenant name.
            metadata: Additional tenant metadata.
            session: Optional database session for provisioning.

        Returns:
            The created TenantInfo.

        Raises:
            TenantProvisioningError: If provisioning fails.
        """
        logger.info(
            "Provisioning tenant",
            extra={"tenant_id": tenant_id, "name": name},
        )

        # Check if tenant already exists
        existing = await self._registry.get(tenant_id)
        if existing is not None:
            if existing.status == TenantStatus.DEACTIVATED:
                raise TenantProvisioningError(
                    tenant_id,
                    "Tenant exists but is deactivated. Use reactivate_tenant() instead.",
                )
            raise TenantProvisioningError(
                tenant_id,
                "Tenant already exists",
                strategy=self._config.strategy.value,
            )

        # Create tenant info
        now = datetime.now(timezone.utc)
        tenant = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            status=TenantStatus.PROVISIONING,
            isolation_strategy=self._config.strategy,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        try:
            # Save to registry
            await self._registry.save(tenant)

            # Call provisioning callback
            if self._on_provision:
                await self._on_provision(tenant, session)

            # Update status to active
            tenant = TenantInfo(
                tenant_id=tenant.tenant_id,
                name=tenant.name,
                status=TenantStatus.ACTIVE,
                isolation_strategy=tenant.isolation_strategy,
                created_at=tenant.created_at,
                updated_at=datetime.now(timezone.utc),
                metadata=tenant.metadata,
            )
            await self._registry.save(tenant)

            logger.info(
                "Tenant provisioned successfully",
                extra={
                    "tenant_id": tenant_id,
                    "strategy": self._config.strategy.value,
                },
            )

            return tenant

        except Exception as e:
            # Rollback: delete from registry
            await self._registry.delete(tenant_id)

            if isinstance(e, TenantProvisioningError):
                raise

            raise TenantProvisioningError(
                tenant_id,
                f"Provisioning failed: {e}",
                strategy=self._config.strategy.value,
            ) from e

    @_require_system_tenant
    async def deactivate_tenant(
        self,
        tenant_id: str,
        *,
        reason: str | None = None,
    ) -> TenantInfo:
        """Deactivate a tenant.

        Deactivated tenants cannot perform operations but their data
        is retained for audit/compliance purposes.

        Args:
            tenant_id: The tenant identifier.
            reason: Optional reason for deactivation.

        Returns:
            The updated TenantInfo.

        Raises:
            TenantNotFoundError: If tenant doesn't exist.
        """
        logger.info(
            "Deactivating tenant",
            extra={"tenant_id": tenant_id, "reason": reason},
        )

        tenant = await self._registry.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        if tenant.status == TenantStatus.DEACTIVATED:
            logger.warning(
                "Tenant already deactivated",
                extra={"tenant_id": tenant_id},
            )
            return tenant

        now = datetime.now(timezone.utc)
        updated_metadata = dict(tenant.metadata)
        if reason:
            updated_metadata["deactivation_reason"] = reason

        updated_tenant = TenantInfo(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            status=TenantStatus.DEACTIVATED,
            isolation_strategy=tenant.isolation_strategy,
            created_at=tenant.created_at,
            updated_at=now,
            deactivated_at=now,
            metadata=updated_metadata,
        )

        await self._registry.save(updated_tenant)

        # Call deactivation callback
        if self._on_deactivate:
            await self._on_deactivate(updated_tenant)

        logger.info(
            "Tenant deactivated",
            extra={"tenant_id": tenant_id},
        )

        return updated_tenant

    @_require_system_tenant
    async def reactivate_tenant(
        self,
        tenant_id: str,
    ) -> TenantInfo:
        """Reactivate a deactivated tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The updated TenantInfo.

        Raises:
            TenantNotFoundError: If tenant doesn't exist.
        """
        logger.info(
            "Reactivating tenant",
            extra={"tenant_id": tenant_id},
        )

        tenant = await self._registry.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        if tenant.status != TenantStatus.DEACTIVATED:
            logger.warning(
                "Tenant is not deactivated",
                extra={"tenant_id": tenant_id, "status": tenant.status},
            )
            return tenant

        updated_tenant = TenantInfo(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            status=TenantStatus.ACTIVE,
            isolation_strategy=tenant.isolation_strategy,
            created_at=tenant.created_at,
            updated_at=datetime.now(timezone.utc),
            metadata=tenant.metadata,
        )

        await self._registry.save(updated_tenant)

        logger.info(
            "Tenant reactivated",
            extra={"tenant_id": tenant_id},
        )

        return updated_tenant

    @_require_system_tenant
    async def list_tenants(
        self,
        *,
        include_deactivated: bool = False,
    ) -> list[TenantInfo]:
        """List all tenants.

        Args:
            include_deactivated: Whether to include deactivated tenants.

        Returns:
            List of tenant info objects.
        """
        return await self._registry.list_all(include_deactivated=include_deactivated)

    @_require_system_tenant
    async def get_tenant(self, tenant_id: str) -> TenantInfo:
        """Get tenant info.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The tenant info.

        Raises:
            TenantNotFoundError: If tenant doesn't exist.
            TenantDeactivatedError: If tenant is deactivated.
        """
        tenant = await self._registry.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        if tenant.status == TenantStatus.DEACTIVATED:
            raise TenantDeactivatedError(tenant_id)

        return tenant

    @_require_system_tenant
    async def update_tenant_metadata(
        self,
        tenant_id: str,
        metadata: dict[str, Any],
        *,
        merge: bool = True,
    ) -> TenantInfo:
        """Update tenant metadata.

        Args:
            tenant_id: The tenant identifier.
            metadata: The metadata to set/merge.
            merge: Whether to merge with existing metadata.

        Returns:
            The updated TenantInfo.

        Raises:
            TenantNotFoundError: If tenant doesn't exist.
        """
        tenant = await self._registry.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        updated_metadata = dict(tenant.metadata) if merge else {}
        updated_metadata.update(metadata)

        updated_tenant = TenantInfo(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            status=tenant.status,
            isolation_strategy=tenant.isolation_strategy,
            created_at=tenant.created_at,
            updated_at=datetime.now(timezone.utc),
            deactivated_at=tenant.deactivated_at,
            metadata=updated_metadata,
        )

        await self._registry.save(updated_tenant)

        logger.info(
            "Updated tenant metadata",
            extra={"tenant_id": tenant_id},
        )

        return updated_tenant

    @_require_system_tenant
    async def delete_tenant(
        self,
        tenant_id: str,
        *,
        on_delete: Callable[[TenantInfo], Awaitable[None]] | None = None,
    ) -> None:
        """Delete a tenant permanently.

        This is a destructive operation that removes all tenant data.
        Use with extreme caution and ensure proper authorization.

        Args:
            tenant_id: The tenant identifier.
            on_delete: Callback to delete tenant resources (schema, database, etc.).

        Raises:
            TenantNotFoundError: If tenant doesn't exist.
        """
        logger.warning(
            "Deleting tenant",
            extra={"tenant_id": tenant_id},
        )

        tenant = await self._registry.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        # Call delete callback
        if on_delete:
            await on_delete(tenant)

        # Remove from registry
        await self._registry.delete(tenant_id)

        logger.warning(
            "Tenant deleted permanently",
            extra={"tenant_id": tenant_id},
        )
