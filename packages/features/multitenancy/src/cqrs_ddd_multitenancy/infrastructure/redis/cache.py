"""Multitenant Redis cache mixin for automatic tenant namespacing.

This mixin automatically namespaces cache keys with tenant_id when composed with
a base cache service class via MRO.

Usage:
    class MyCacheService(MultitenantRedisCacheMixin, RedisCacheService):
        pass

The mixin must appear BEFORE the base service in the MRO to ensure
    method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import Any

from ...context import get_current_tenant_or_none, is_system_tenant
from ...exceptions import TenantContextMissingError

__all__ = [
    "MultitenantRedisCacheMixin",
]

logger = logging.getLogger(__name__)


class MultitenantRedisCacheMixin:
    """Mixin that adds automatic tenant namespacing to Redis cache operations.

    This mixin intercepts all cache methods to namespace keys with tenant_id.
    It should be used via MRO composition:

        class MyCache(MultitenantRedisCacheMixin, RedisCacheService):
            pass

    Key behaviors:
    - **get()**: Prepends tenant namespace to key
    - **set()**: Prepares tenant namespace to key
    - **delete()**: Prepares tenant namespace to key
    - **exists()**: Prepares tenant namespace to key
    - All other methods namespace keys with tenant

    The namespace format is: `{tenant_id}:{original_key}`

    Attributes:
        _tenant_namespace_separator: Separator between tenant and key (default: ":")

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base cache service class.
    """

    # These can be overridden in subclasses
    _tenant_namespace_separator: str = ":"

    def _get_namespace_separator(self) -> str:
        """Get the namespace separator.

        Override this to customize the separator per cache service.

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
                "Tenant context required for cache operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_aware_key(self, key: str) -> str:
        """Build tenant-aware cache key.

        Args:
            key: The original cache key.

        Returns:
            The tenant-namespaced key.
        """
        tenant_id = self._require_tenant_context()
        separator = self._get_namespace_separator()
        return f"{tenant_id}{separator}{key}"

    # ── ICacheService Protocol Methods ─────────────────────────────

    async def get(self, key: str, cls: type[Any] | None = None) -> Any | None:
        """Get a value from cache with tenant namespacing.

        Args:
            key: The cache key.
            cls: Optional type to deserialize to.

        Returns:
            The cached value or None.
        """
        tenant_key = self._build_tenant_aware_key(key)
        return await super().get(tenant_key, cls)  # type: ignore[misc]

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in cache with tenant namespacing.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional time-to-live in seconds.
        """
        tenant_key = self._build_tenant_aware_key(key)
        await super().set(tenant_key, value, ttl)  # type: ignore[misc]

    async def delete(self, key: str) -> None:
        """Delete a value from cache with tenant namespacing.

        Args:
            key: The cache key.
        """
        tenant_key = self._build_tenant_aware_key(key)
        await super().delete(tenant_key)  # type: ignore[misc]

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache with tenant namespacing.

        Args:
            key: The cache key.

        Returns:
            True if the key exists, False otherwise.
        """
        tenant_key = self._build_tenant_aware_key(key)
        return await super().exists(tenant_key)  # type: ignore[misc, no-any-return]

    async def clear(self) -> None:
        """Clear all cache entries for current tenant.

        WARNING: This clears ALL keys for the current tenant namespace.
        Use with caution.
        """
        tenant_id = self._require_tenant_context()
        separator = self._get_namespace_separator()
        pattern = f"{tenant_id}{separator}*"

        # Redis SCAN to find all keys for this tenant
        # Note: This is a simplified implementation
        # In production, you'd want to use SCAN with COUNT for pagination
        logger.warning(
            f"Clearing all cache keys for tenant {tenant_id}. "
            "This operation may be expensive for large datasets."
        )

        # Get base Redis client
        redis_client = self._redis  # type: ignore[attr-defined]

        # Find all keys matching the pattern
        keys = []
        async for key in redis_client.scan_iter(match=pattern.encode()):
            keys.append(key)

        # Delete all keys
        if keys:
            await redis_client.delete(*keys)
            logger.info(f"Deleted {len(keys)} cache keys for tenant {tenant_id}")
