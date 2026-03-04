"""Multitenancy exception hierarchy.

All multitenancy exceptions inherit from either DomainError or InfrastructureError
to align with the core exception hierarchy.
"""

from __future__ import annotations

__all__ = [
    "TenantError",
    "TenantContextMissingError",
    "TenantNotFoundError",
    "TenantDeactivatedError",
    "CrossTenantAccessError",
    "TenantIsolationError",
    "TenantProvisioningError",
]

from cqrs_ddd_core.primitives.exceptions import (  # noqa: E402
    DomainError,
    InfrastructureError,
)


class TenantError(DomainError):
    """Base class for all tenant-related domain errors.

    Inherit from this for business-rule violations related to tenants.
    """

    def __init__(self, message: str, *, tenant_id: str | None = None) -> None:
        self.tenant_id = tenant_id
        super().__init__(message)


class TenantContextMissingError(TenantError):
    """Raised when a tenant context is required but not set.

    This typically indicates:
    - TenantMiddleware not configured or not processing the request
    - Tenant resolver failed to extract tenant from the message
    - Background job spawned without tenant context propagation
    """

    def __init__(
        self,
        message: str = "Tenant context is required but not set",
        *,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(message, tenant_id=tenant_id)


class TenantNotFoundError(TenantError):
    """Raised when a referenced tenant does not exist.

    This is raised during tenant lookup operations, not during
    cross-tenant access attempts (which use silent denial).
    """

    def __init__(
        self,
        tenant_id: str,
        message: str | None = None,
    ) -> None:
        if message is None:
            message = f"Tenant '{tenant_id}' not found"
        super().__init__(message, tenant_id=tenant_id)


class TenantDeactivatedError(TenantError):
    """Raised when attempting to operate on a deactivated tenant.

    Deactivated tenants cannot perform any operations but their data
    is retained for audit/compliance purposes.
    """

    def __init__(
        self,
        tenant_id: str,
        message: str | None = None,
    ) -> None:
        if message is None:
            message = f"Tenant '{tenant_id}' is deactivated"
        super().__init__(message, tenant_id=tenant_id)


class CrossTenantAccessError(TenantError):
    """Raised when explicit cross-tenant access is detected and blocked.

    Note: By default, cross-tenant get() operations return None silently
    to prevent information leakage. This exception is raised when:
    - Attempting to modify another tenant's data
    - System operation decorator is not present for admin operations
    - Explicit cross-tenant validation is enabled
    """

    def __init__(
        self,
        current_tenant: str | None,
        target_tenant: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        self.current_tenant = current_tenant
        self.target_tenant = target_tenant
        self.resource_type = resource_type
        self.resource_id = resource_id

        parts = ["Cross-tenant access denied"]
        if resource_type:
            parts.append(f"for {resource_type}")
        if resource_id:
            parts.append(f"with id={resource_id!r}")
        parts.append(f"(current: {current_tenant!r}, target: {target_tenant!r})")

        super().__init__(" ".join(parts), tenant_id=current_tenant)


class TenantIsolationError(InfrastructureError):
    """Raised when tenant isolation infrastructure fails.

    This covers technical failures in:
    - Schema routing (PostgreSQL search_path errors)
    - Database routing (connection failures)
    - Connection pool management
    """

    def __init__(
        self,
        message: str,
        *,
        tenant_id: str | None = None,
        strategy: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.strategy = strategy
        super().__init__(message)


class TenantProvisioningError(TenantIsolationError):
    """Raised when tenant provisioning fails.

    This includes:
    - Schema creation failures
    - Database creation failures
    - Migration application failures
    """

    def __init__(
        self,
        tenant_id: str,
        reason: str,
        *,
        strategy: str | None = None,
    ) -> None:
        message = f"Failed to provision tenant '{tenant_id}': {reason}"
        super().__init__(message, tenant_id=tenant_id, strategy=strategy)
