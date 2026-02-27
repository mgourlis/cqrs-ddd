"""ProjectionManager — distributed initialization with locking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cqrs_ddd_core.ports.locking import DDL_LOCK_TTL_SECONDS, ILockStrategy
from cqrs_ddd_core.primitives.locking import ResourceIdentifier

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.ports.projection import IProjectionWriter
    from cqrs_ddd_advanced_core.projections.schema import ProjectionSchemaRegistry


class ProjectionManager:
    """
    Ensures projection collections/tables are initialized once, with optional
    distributed locking so only one process performs DDL in multi-pod deployments.

    Uses ILockStrategy (e.g. Redis-based) with ResourceIdentifier
    resource_type="projection_initialization", resource_id=collection,
    lock_mode="write".
    """

    def __init__(
        self,
        writer: IProjectionWriter,
        registry: ProjectionSchemaRegistry,
        lock_strategy: ILockStrategy,
    ) -> None:
        self._writer = writer
        self._registry = registry
        self._lock_strategy = lock_strategy

    async def initialize_once(
        self,
        collection: str,
        *,
        timeout: float = 10.0,
        ttl: float = DDL_LOCK_TTL_SECONDS,
    ) -> None:
        """
        Ensure a single collection/table exists: acquire lock, double-check,
        ensure_collection, release lock.
        """
        resource = ResourceIdentifier(
            resource_type="projection_initialization",
            resource_id=collection,
            lock_mode="write",
        )
        token = await self._lock_strategy.acquire(
            resource,
            timeout=timeout,
            ttl=ttl,
        )
        try:
            if await self._writer.collection_exists(collection):
                return
            schema = self._registry.get(collection)
            await self._writer.ensure_collection(collection, schema=schema)
        finally:
            await self._lock_strategy.release(resource, token)

    async def initialize_all(
        self,
        *,
        timeout: float = 10.0,
        ttl: float = DDL_LOCK_TTL_SECONDS,
    ) -> None:
        """Initialize all schemas in the registry in dependency order."""
        for name in self._registry.get_initialization_order():
            await self.initialize_once(name, timeout=timeout, ttl=ttl)
