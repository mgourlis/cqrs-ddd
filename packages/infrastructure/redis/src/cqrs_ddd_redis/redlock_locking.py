"""Redis-based distributed locking using Redlock algorithm via redlock-ng."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from redlock import AsyncRedlock

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.locking import ActiveLock
from cqrs_ddd_core.primitives.exceptions import (
    ConcurrencyError,
    LockAcquisitionError,
)

from .exceptions import RedisLockError

if TYPE_CHECKING:
    from cqrs_ddd_core.primitives.locking import ResourceIdentifier

logger = logging.getLogger("cqrs_ddd.redis.locking")


class RedlockLockStrategy:
    """
    Distributed lock strategy using Redis and the Redlock algorithm.

    This implementation uses redlock-ng (alwaysvivek/redlock) which:
    - Implements the Redlock algorithm for distributed locks
    - Supports multiple Redis instances for high availability
    - Fully asynchronous (asyncio) and Python 3.12 compatible
    - Provides automatic lock expiration (TTL)

    Hardened Reliability Features:
    - Unique tokens to prevent unauthorized releases (Redlock safety)
    - Atomic extensions via Lua scripts
    - Reentrancy support with Reference Counting
      (prevents early release in nested flows)
    - Proactive Memory Management (metadata pruning to prevent leaks)
    - Protocol-compliant health checks (Quorum-aware)

    Example:
        ```python
        strategy = RedlockLockStrategy([
            "redis://localhost:6379/0",
            "redis://localhost:6380/0",
        ])

        resource = ResourceIdentifier("Account", "123")
        token = await strategy.acquire(resource, timeout=10.0, ttl=30.0)
        try:
            # Do work
            ...
        finally:
            await strategy.release(resource, token)
        ```
    """

    def __init__(
        self,
        redis_urls: list[str],
        *,
        retry_count: int = 1000,
        retry_delay_min: float = 0.1,
        retry_delay_max: float = 0.3,
    ) -> None:
        """
        Initialize Redis lock strategy.

        Args:
            redis_urls: List of Redis URLs
            retry_count: Number of times to retry acquisition
            retry_delay_min: Minimum delay between retries
            retry_delay_max: Maximum delay between retries
        """
        self._redis_urls = redis_urls
        self._redlock = AsyncRedlock(
            redis_urls,
            retry_count=retry_count,
            retry_delay_min=retry_delay_min,
            retry_delay_max=retry_delay_max,
        )

        # Access internal clients for our manual Lua script extensions
        # and health checks. This prevents creating duplicate connection pools.
        # redlock-ng uses AsyncRedlockClient which has an 'instances'
        # list of Redis objects.
        self._redis_clients = dict(
            zip(redis_urls, self._redlock.client.instances, strict=False)
        )

        # Store metadata for monitoring and reentrancy
        # Key -> (acquired_at, ttl, session_id, redlock_id, ref_count)
        self._lock_metadata: dict[str, list[Any]] = {}

        logger.info(
            "Initialized RedlockLockStrategy with %d Redis instances (redlock-ng)",
            len(redis_urls),
        )

    def _make_key(self, resource: ResourceIdentifier) -> str:
        """Create Redis key from resource identifier."""
        return (
            f"lock:{resource.resource_type}:{resource.resource_id}:{resource.lock_mode}"
        )

    def _prune_expired_metadata(self) -> None:
        """Remove naturally expired locks from local metadata.

        Prevents memory leaks.
        """
        now = datetime.now(timezone.utc)
        expired_keys = [
            k
            for k, meta in self._lock_metadata.items()
            if now > meta[0] + timedelta(seconds=meta[1])
        ]
        for k in expired_keys:
            self._lock_metadata.pop(k, None)
            logger.debug("Pruned expired metadata for %s", k)

    async def _handle_reentrant_lock(
        self,
        key: str,
        resource: ResourceIdentifier,
        session_id: str,
        ttl: float,
    ) -> str | None:
        """Handle reentrant lock acquisition.

        Returns token if successful, None otherwise.
        """
        if key not in self._lock_metadata:
            return None

        (
            acquired_at,
            existing_ttl,
            existing_session,
            redlock_id,
            _,
        ) = self._lock_metadata[key]

        if existing_session != session_id:
            return None

        # Check if it hasn't expired yet locally
        if datetime.now(timezone.utc) >= acquired_at + timedelta(seconds=existing_ttl):
            return None

        # Safety: ensure the lock is also extended in Redis
        if await self.extend(resource, f"{key}:{redlock_id}", ttl):
            self._lock_metadata[key][4] += 1
            logger.debug(
                "Reentrant lock granted for session %s (count=%d)",
                session_id,
                self._lock_metadata[key][4],
            )
            return f"{key}:{redlock_id}"

        logger.warning(
            "Reentrant extension failed for %s (lock may have expired in Redis). "
            "Falling back to fresh acquisition.",
            key,
        )
        # Remove stale metadata to force fresh acquisition
        self._lock_metadata.pop(key, None)
        return None

    async def _acquire_new_lock(
        self, key: str, resource: ResourceIdentifier, timeout: float, ttl_ms: int
    ) -> str:
        """Acquire a new lock via redlock-ng. Returns redlock_id."""
        import asyncio

        try:
            lock = await asyncio.wait_for(
                self._redlock.acquire(key, ttl=ttl_ms), timeout=timeout
            )
        except asyncio.TimeoutError as err:
            raise LockAcquisitionError(
                resource, timeout, reason=f"Acquisition timed out after {timeout}s"
            ) from err

        if not lock or not lock.valid:
            raise LockAcquisitionError(
                resource,
                timeout,
                reason=f"Quorum not reached or lock busy for {key}",
            )

        return str(lock.value)

    def _store_lock_metadata(
        self, key: str, redlock_id: str, ttl: float, session_id: str | None
    ) -> None:
        """Store lock metadata."""
        self._lock_metadata[key] = [
            datetime.now(timezone.utc),
            ttl,
            session_id,
            redlock_id,
            1,
        ]

    async def acquire(
        self,
        resource: ResourceIdentifier,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        session_id: str | None = None,
    ) -> str:
        """
        Acquire a distributed lock.

        Note:
            This method uses asyncio.wait_for to respect the 'timeout' parameter.
            The 'retry_count' and 'retry_delay' configured at initialization
            determine the frequency and total attempts of the underlying
            Redlock algorithm.

        Args:
            resource: The resource to lock
            timeout: Maximum time to wait for lock acquisition (seconds)
            ttl: Lock expiration time (seconds)
            session_id: Optional session ID for reentrancy support

        Returns:
            Lock composite token: "key:redlock_id" for releasing the lock
        """
        registry = get_hook_registry()
        return cast(
            "str",
            await registry.execute_all(
                f"redis.lock.acquire.{resource.resource_type}",
                {
                    "resource": str(resource),
                    "resource_type": resource.resource_type,
                    "resource_id": resource.resource_id,
                    "timeout": timeout,
                    "ttl": ttl,
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._acquire_internal(
                    resource,
                    timeout=timeout,
                    ttl=ttl,
                    session_id=session_id,
                ),
            ),
        )

    async def _acquire_internal(
        self,
        resource: ResourceIdentifier,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        session_id: str | None = None,
    ) -> str:
        key = self._make_key(resource)
        ttl_ms = int(ttl * 1000)

        # Proactively prune to keep memory usage stable
        self._prune_expired_metadata()

        try:
            logger.debug("Acquiring lock: %s (timeout=%.1fs)", key, timeout)

            # Reentrancy check using local metadata with reference counting
            if session_id:
                token = await self._handle_reentrant_lock(
                    key, resource, session_id, ttl
                )
                if token:
                    return token

            # Acquire new lock via redlock-ng
            redlock_id = await self._acquire_new_lock(key, resource, timeout, ttl_ms)

            # Store metadata
            self._store_lock_metadata(key, redlock_id, ttl, session_id)

            return f"{key}:{redlock_id}"

        except ConcurrencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Catch all unexpected errors during Redis lock operations
            logger.error(
                "Unexpected error during lock acquisition for %s: %s", key, exc
            )
            raise RedisLockError(
                f"Technical failure acquiring lock on {key}: {exc}"
            ) from exc

    async def release(self, resource: ResourceIdentifier, token: str) -> None:
        """
        Release the lock using token validation and reference counting.

        Args:
            resource: The resource that was locked.
            token: The composite token returned by :meth:`acquire`.

        Note:
            If the lock was acquired reentrantly (nested flow), this only
            decrements the reference count. The Redis lock is only released
            when the ref_count reaches zero.
        """
        registry = get_hook_registry()
        await registry.execute_all(
            f"redis.lock.release.{resource.resource_type}",
            {
                "resource": str(resource),
                "resource_type": resource.resource_type,
                "resource_id": resource.resource_id,
                "correlation_id": get_correlation_id(),
            },
            lambda: self._release_internal(token),
        )

    async def _release_internal(self, token: str) -> None:
        try:
            key, redlock_id = token.rsplit(":", 1)
        except ValueError:
            logger.error("Invalid lock token format: %s", token)
            return

        metadata = self._lock_metadata.get(key)
        if metadata:
            # Reentrancy safety: decrement ref_count
            metadata[4] -= 1
            if metadata[4] > 0:
                logger.debug(
                    "Reentrant release for %s (remaining count=%d)", key, metadata[4]
                )
                return

        try:
            # unlock() takes resource name and token string
            await self._redlock.unlock(key, redlock_id)
            self._lock_metadata.pop(key, None)
            logger.debug("Lock fully released in Redis: %s", key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to release lock %s: %s (will auto-expire)", key, exc)
            # Remove from metadata anyway since it's compromised or expired
            self._lock_metadata.pop(key, None)

    async def extend(
        self, _resource: ResourceIdentifier, token: str, ttl: float
    ) -> bool:
        """
        Extend lock TTL using an atomic Lua script (safety check on token).

        Args:
            resource: The resource that was locked.
            token: The composite token returned by :meth:`acquire`.
            ttl: New time-to-live (seconds) from now.

        Returns:
            True if the lock was successfully extended on a quorum of instances,
            False otherwise.
        """
        try:
            key, redlock_id = token.rsplit(":", 1)
        except ValueError:
            return False

        lua_extend = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("pexpire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        ttl_ms = int(ttl * 1000)

        try:
            success_count = 0
            for _url, client in self._redis_clients.items():
                try:
                    result = await client.eval(lua_extend, 1, key, redlock_id, ttl_ms)
                    if result:
                        success_count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Lock extension failed on node: %s", exc)
                    continue

            # Quorum check for extension
            if success_count > len(self._redis_urls) // 2:
                if key in self._lock_metadata:
                    # Update local TTL/acquired_at
                    self._lock_metadata[key][0] = datetime.now(timezone.utc)
                    self._lock_metadata[key][1] = ttl
                return True
            return False
        except Exception:  # noqa: BLE001
            return False

    async def health_check(self) -> bool:
        """
        Verify Redis health.

        Strictly follows boolean protocol. Returns True only if a quorum
        of Redis nodes are reachable, as required by the Redlock algorithm.
        """
        try:
            connected_count = 0
            for client in self._redis_clients.values():
                try:
                    await client.ping()
                    connected_count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Health check ping failed: %s", exc)
                    continue

            # Quorum check for operational health (needs > N/2)
            return connected_count > len(self._redis_urls) // 2
        except Exception as exc:  # noqa: BLE001
            logger.error("Health check failed critically: %s", exc)
            return False

    async def get_active_locks(self) -> list[ActiveLock]:
        """Get active locks, filtering out locally expired ones."""
        self._prune_expired_metadata()

        locks = []
        for key, meta in self._lock_metadata.items():
            acquired_at, ttl, session_id, redlock_id, _ = meta
            parts = key.split(":", 3)
            # lock:resource_type:resource_id:lock_mode
            if len(parts) >= 4:
                _, r_type, r_id, mode = parts
                locks.append(
                    ActiveLock(
                        resource_type=r_type,
                        resource_id=r_id,
                        token=f"{key}:{redlock_id}",
                        acquired_at=acquired_at,
                        ttl_seconds=ttl,
                        session_id=session_id,
                    )
                )
        return locks

    async def close(self) -> None:
        """Cleanup pooled Redis clients."""
        try:
            # redlock-ng doesn't have a close(), so we clean up our shared clients
            for client in self._redis_clients.values():
                with contextlib.suppress(Exception):
                    await client.aclose()

            logger.info("RedlockLockStrategy closed")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing RedlockLockStrategy: %s", exc)
