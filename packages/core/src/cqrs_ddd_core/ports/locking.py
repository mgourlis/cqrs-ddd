"""ILockStrategy — protocol for pessimistic and distributed locking.

Lock TTL guidance:
- Short-lived operations (e.g. command handlers): default ttl (e.g. 30s) is usually fine.
- DDL / schema / initialize-once (e.g. creating collections, geospatial or heavy indexes):
  Use a conservative TTL (e.g. DDL_LOCK_TTL_SECONDS = 300) or run a background
  heartbeat that calls extend(resource, token, ttl=...) periodically while holding
  the lock. If the lock TTL is too low (e.g. 60s), slow DDL can expire so another
  pod acquires the lock and runs the same DDL, causing races or duplicate work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

# Conservative TTL for DDL / schema / "initialize once" locks (e.g. create collection,
# create 2dsphere or heavy composite indexes). Use this or a heartbeat via extend().
DDL_LOCK_TTL_SECONDS: float = 300.0  # 5 minutes

if TYPE_CHECKING:
    from datetime import datetime

    from ..primitives.locking import ResourceIdentifier


@dataclass
class ActiveLock:
    """
    Information about an active lock for monitoring and debugging.

    Used by get_active_locks() to provide visibility into which
    resources are currently locked and by whom.
    """

    resource_type: str
    resource_id: str
    token: str
    acquired_at: datetime
    ttl_seconds: float
    session_id: str | None = None


@runtime_checkable
class ILockStrategy(Protocol):
    """
    Lock strategy protocol for pessimistic concurrency control.

    Implementations can use Redis (Redlock), database locks (SELECT FOR UPDATE),
    or in-memory semaphores for testing.

    Example:
        ```python
        from uuid import UUID

        class RedisLockStrategy(ILockStrategy):
            async def acquire(self, resource: ResourceIdentifier, ...) -> str:
                ...
        ```
    """

    async def acquire(
        self,
        resource: ResourceIdentifier,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        session_id: str | None = None,
    ) -> str:
        """
        Acquire a lock for the given resource.

        Args:
            resource: The resource to lock (includes type, ID, and lock mode).
            timeout: Maximum time to wait for the lock.
            ttl: Time-to-live for the lock (seconds). Lock auto-expires to prevent
                orphaned locks if the process crashes.
            session_id: Optional unique identifier for the execution context.
                Used to support Reentrancy (nested locks in the same command).

        Returns:
            A unique lock token required for release.

        Raises:
            ConcurrencyError: If the lock cannot be acquired within the timeout.
        """
        ...

    async def extend(
        self,
        resource: ResourceIdentifier,
        token: str,
        ttl: float,
    ) -> bool:
        """
        Extend the TTL of an existing lock.

        Use for long-running operations (e.g. DDL, schema migration, initialize-once)
        to keep the lock alive. Either pass a conservative TTL at acquire (see
        :data:`DDL_LOCK_TTL_SECONDS`) or run a background heartbeat that calls
        extend() periodically (e.g. every ttl/2 seconds) while the work is in progress.

        Args:
            resource: The resource that was locked.
            token: The token returned by :meth:`acquire`.
            ttl: New time-to-live (seconds) from now.

        Returns:
            True if lock was extended, False if lock no longer exists.
        """
        ...

    async def release(
        self,
        resource: ResourceIdentifier,
        token: str,
    ) -> None:
        """
        Release a previously acquired lock.

        Args:
            resource: The resource that was locked.
            token: The token returned by :meth:`acquire`.
        """
        ...

    async def health_check(self) -> bool:
        """
        Verify that the lock service is responsive and healthy.

        Implementations should perform a lightweight check such as:
        - Acquiring and immediately releasing a test lock
        - Pinging the underlying service (Redis, database, etc.)

        This method is useful for:
        - Application startup readiness checks
        - Health monitoring endpoints
        - Circuit breaker patterns

        Returns:
            True if the lock service is healthy and responsive, False otherwise.

        Example:
            ```python
            if not await lock_strategy.health_check():
                logger.error("Lock service is down!")
                # Trigger alert or disable feature
            ```
        """
        ...

    async def get_active_locks(self) -> list[ActiveLock]:
        """
        Get all active locks for monitoring and debugging.

        This is useful for:
        - Admin dashboards showing locked resources
        - Debugging deadlocks or contention issues
        - Monitoring lock usage patterns

        Returns:
            List of active locks with metadata (resource, token, TTL, etc.)

        Example:
            ```python
            active = await lock_strategy.get_active_locks()
            for lock in active:
                print(f"{lock.resource_type}:{lock.resource_id} locked by {lock.token}")
            ```

        Note:
            This method may be expensive for large-scale deployments.
            Use sparingly and consider caching the results.
        """
        ...
