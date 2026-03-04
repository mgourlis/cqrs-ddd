"""Multitenant Redis lock mixin for automatic tenant namespacing.

This mixin automatically namespaces lock keys with tenant_id when composed with
a base lock strategy class via MRO.

Usage:
    class MyLockStrategy(MultitenantRedisLockMixin, RedlockLockStrategy):
        pass

The mixin must appear BEFORE the base strategy in the MRO to ensure
    method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import Any

from ...context import get_current_tenant_or_none, is_system_tenant
from ...exceptions import TenantContextMissingError

__all__ = [
    "MultitenantRedisLockMixin",
]

logger = logging.getLogger(__name__)


class MultitenantRedisLockMixin:
    """Mixin that adds automatic tenant namespacing to Redis lock operations.

    This mixin intercepts all lock methods to namespace lock keys with tenant_id.
    It should be used via MRO composition:

        class MyLock(MultitenantRedisLockMixin, RedlockLockStrategy):
            pass

    Key behaviors:
    - **acquire()**: Prepends tenant namespace to resource name
    - **release()**: Prepends tenant namespace to resource name
    - **extend()**: Prepends tenant namespace to resource name
    - Prevents cross-tenant lock interference

    The namespace format is: `{tenant_id}:{resource_name}`

    Attributes:
        _tenant_namespace_separator: Separator between tenant and resource (default: ":")

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base lock strategy class.
    """

    # These can be overridden in subclasses
    _tenant_namespace_separator: str = ":"

    def _get_namespace_separator(self) -> str:
        """Get the namespace separator.

        Override this to customize the separator per lock strategy.

        Returns:
            The namespace separator.
        """
        return getattr(self, "_tenant_namespace_separator", ":")

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
                "Tenant context required for lock operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_aware_resource(self, resource: str) -> str:
        """Build tenant-aware lock resource name.

        Args:
            resource: The original resource name.

        Returns:
            The tenant-namespaced resource name.
        """
        tenant_id = self._require_tenant_context()
        separator = self._get_namespace_separator()
        return f"{tenant_id}{separator}{resource}"

    # ── ILockStrategy Protocol Methods ─────────────────────────────

    async def acquire(
        self,
        resource: str,
        ttl: float = 10.0,
        timeout: float = 5.0,
        **kwargs: Any,
    ) -> Any:
        """Acquire a lock with tenant namespacing.

        Args:
            resource: The resource name to lock.
            ttl: Time-to-live for the lock in seconds.
            timeout: Maximum time to wait for lock acquisition.
            **kwargs: Additional arguments passed to base strategy.

        Returns:
            Lock token/handle from base strategy.
        """
        tenant_resource = self._build_tenant_aware_resource(resource)
        logger.debug(
            f"Acquiring lock for tenant-aware resource: {tenant_resource} "
            f"(original: {resource})"
        )
        return await super().acquire(  # type: ignore[misc]
            tenant_resource, ttl=ttl, timeout=timeout, **kwargs
        )

    async def release(self, resource: str, **kwargs: Any) -> None:
        """Release a lock with tenant namespacing.

        Args:
            resource: The resource name to unlock.
            **kwargs: Additional arguments passed to base strategy.
        """
        tenant_resource = self._build_tenant_aware_resource(resource)
        logger.debug(
            f"Releasing lock for tenant-aware resource: {tenant_resource} "
            f"(original: {resource})"
        )
        await super().release(tenant_resource, **kwargs)  # type: ignore[misc]

    async def extend(
        self,
        resource: str,
        ttl: float = 10.0,
        **kwargs: Any,
    ) -> Any:
        """Extend a lock with tenant namespacing.

        Args:
            resource: The resource name to extend lock for.
            ttl: New time-to-live for the lock in seconds.
            **kwargs: Additional arguments passed to base strategy.

        Returns:
            Extended lock token/handle from base strategy.
        """
        tenant_resource = self._build_tenant_aware_resource(resource)
        logger.debug(
            f"Extending lock for tenant-aware resource: {tenant_resource} "
            f"(original: {resource})"
        )
        return await super().extend(tenant_resource, ttl=ttl, **kwargs)  # type: ignore[misc]

    async def is_locked(self, resource: str, **kwargs: Any) -> bool:
        """Check if a resource is locked with tenant namespacing.

        Args:
            resource: The resource name to check.
            **kwargs: Additional arguments passed to base strategy.

        Returns:
            True if the resource is locked, False otherwise.
        """
        tenant_resource = self._build_tenant_aware_resource(resource)
        return await super().is_locked(tenant_resource, **kwargs)  # type: ignore[misc, no-any-return]
