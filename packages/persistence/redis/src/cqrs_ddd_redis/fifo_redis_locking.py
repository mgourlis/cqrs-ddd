"""Simple Redis-based distributed locking with Fair (FCFS) semantics."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.locking import ActiveLock
from cqrs_ddd_core.primitives.exceptions import (
    LockAcquisitionError,
)

from .exceptions import RedisLockError

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from cqrs_ddd_core.primitives.locking import ResourceIdentifier

logger = logging.getLogger("cqrs_ddd.redis.fifo_locking")


class FifoRedisLockStrategy:
    """
    Simpler Redis-based distributed lock implementation with Fair (FCFS) semantics.

    Designed for single-instance Redis setups. Unlike Redlock, this strategy
    guarantees that requests are served in the order they were received (FCFS)
    using a ZSET-based queue.

    Features:
    - Fair Locking: Requests are served in order of arrival via a Redis ZSET.
    - Atomic Operations: Lua scripts ensure queue and lock consistency.
    - Reentrancy: Supported via session_id and local reference counting.
    - Automatic Expiration: TTL-based cleanup.
    """

    def __init__(
        self,
        redis: Redis,  # type: ignore[type-arg]
        prefix: str = "lock",
        retry_interval: float = 0.1,
    ) -> None:
        """
        Initialize FifoRedisLockStrategy.

        Args:
            redis: An initialized redis.asyncio.Redis client.
            prefix: Key prefix for Redis keys.
            retry_interval: Delay between polling attempts while in queue.
        """
        self._redis = redis
        self._prefix = prefix
        self._retry_interval = retry_interval

        # Metadata for reentrancy and monitoring
        # Key -> (acquired_at, ttl, session_id, token, ref_count)
        self._lock_metadata: dict[str, list[Any]] = {}

    def _lock_key(self, resource: ResourceIdentifier) -> str:
        return (
            f"{self._prefix}:{resource.resource_type}:"
            f"{resource.resource_id}:{resource.lock_mode}"
        )

    def _queue_key(self, resource: ResourceIdentifier) -> str:
        return (
            f"{self._prefix}:queue:{resource.resource_type}:"
            f"{resource.resource_id}:{resource.lock_mode}"
        )

    def _prune_expired_metadata(self) -> None:
        """Remove naturally expired locks from local metadata."""
        now = datetime.now(timezone.utc)
        expired_keys = [
            k
            for k, meta in self._lock_metadata.items()
            if now > meta[0] + timedelta(seconds=meta[1])
        ]
        for k in expired_keys:
            self._lock_metadata.pop(k, None)

    async def acquire(
        self,
        resource: ResourceIdentifier,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        session_id: str | None = None,
    ) -> str:
        """Acquire a lock using the Fair (FCFS) algorithm."""
        lock_key = self._lock_key(resource)
        queue_key = self._queue_key(resource)
        token = str(uuid.uuid4())
        ttl_ms = int(ttl * 1000)

        self._prune_expired_metadata()

        # Check for reentrancy
        reentrant_token = await self._try_reentrant_acquire(
            resource, lock_key, session_id, ttl
        )
        if reentrant_token:
            return reentrant_token

        # Attempt fair lock acquisition with retries
        try:
            return await self._try_fair_acquire_with_retry(
                lock_key, queue_key, token, ttl_ms, timeout, ttl, session_id
            )
        except asyncio.TimeoutError:
            # Cleanup queue if timed out
            await self._redis.zrem(queue_key, token)
            raise LockAcquisitionError(
                resource, timeout, reason="Fair lock acquisition timed out"
            ) from None

    async def _try_reentrant_acquire(
        self,
        resource: ResourceIdentifier,
        lock_key: str,
        session_id: str | None,
        ttl: float,
    ) -> str | None:
        """Check if this is a reentrant lock request and handle it if so."""
        if not session_id or lock_key not in self._lock_metadata:
            return None

        (
            acquired_at,
            existing_ttl,
            existing_session,
            existing_token,
            ref_count,
        ) = self._lock_metadata[lock_key]

        is_same_session = existing_session == session_id
        is_not_expired = datetime.now(timezone.utc) < acquired_at + timedelta(
            seconds=existing_ttl
        )

        if (
            is_same_session
            and is_not_expired
            and await self.extend(resource, existing_token, ttl)
        ):
            self._lock_metadata[lock_key][4] += 1
            return str(existing_token)

        return None

    async def _try_fair_acquire_with_retry(
        self,
        lock_key: str,
        queue_key: str,
        token: str,
        ttl_ms: int,
        timeout: float,
        ttl: float,
        session_id: str | None,
    ) -> str:
        """Retry acquiring a fair lock until timeout."""
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                acquired = await self._execute_fair_acquire_script(
                    queue_key, lock_key, token, ttl_ms
                )

                if acquired:
                    self._lock_metadata[lock_key] = [
                        datetime.now(timezone.utc),
                        ttl,
                        session_id,
                        token,
                        1,
                    ]
                    return token

                await asyncio.sleep(self._retry_interval)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error during fair lock acquisition: %s", exc)
                raise RedisLockError(f"Technical failure: {exc}") from exc

        raise asyncio.TimeoutError

    async def _execute_fair_acquire_script(
        self,
        queue_key: str,
        lock_key: str,
        token: str,
        ttl_ms: int,
    ) -> bool:
        """Execute the Lua script for fair lock acquisition.

        Lua script uses Redis EVAL with:
        - KEYS: [queue_key, lock_key]
        - ARGV: [token, ttl_ms, now_ts]
        """
        fair_acquire_script = """
        local queue_key = KEYS[1]
        local lock_key = KEYS[2]
        local token = ARGV[1]
        local ttl_ms = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        -- Add to queue if not present
        redis.call('ZADD', queue_key, 'NX', now, token)

        -- Check Rank
        local rank = redis.call('ZRANK', queue_key, token)

        if rank == 0 then
            -- We are at the head, try to SET lock
            local acquired = redis.call('SET', lock_key, token, 'NX', 'PX', ttl_ms)
            if acquired then
                redis.call('ZREM', queue_key, token)
                return 1
            end
        end
        return 0
        """

        now_ts = datetime.now(timezone.utc).timestamp()
        result_raw = self._redis.eval(  # type: ignore[no-untyped-call]
            fair_acquire_script,
            2,
            queue_key,
            lock_key,
            token,
            str(ttl_ms),
            str(now_ts),
        )
        result = await result_raw if hasattr(result_raw, "__await__") else result_raw
        result = int(result) if isinstance(result, str | bytes) else result

        return bool(result == 1)

    async def release(self, resource: ResourceIdentifier, token: str) -> None:
        """Release the lock."""
        lock_key = self._lock_key(resource)
        queue_key = self._queue_key(resource)

        metadata = self._lock_metadata.get(lock_key)
        if metadata and metadata[3] == token:
            metadata[4] -= 1
            if metadata[4] > 0:
                return

        # Lua script for safe release
        release_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            redis.call("DEL", KEYS[1])
        end
        redis.call("ZREM", KEYS[2], ARGV[1])
        return 1
        """

        try:
            result_raw = self._redis.eval(release_script, 2, lock_key, queue_key, token)  # type: ignore[no-untyped-call]
            if hasattr(result_raw, "__await__"):
                await result_raw
            self._lock_metadata.pop(lock_key, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to release simple lock %s: %s", lock_key, exc)

    async def extend(
        self, resource: ResourceIdentifier, token: str, ttl: float
    ) -> bool:
        """Extend lock TTL."""
        lock_key = self._lock_key(resource)
        ttl_ms = int(ttl * 1000)

        extend_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("PEXPIRE", KEYS[1], ARGV[2])
        end
        return 0
        """
        try:
            result_raw = self._redis.eval(  # type: ignore[no-untyped-call]
                extend_script, 1, lock_key, token, str(ttl_ms)
            )
            result = (
                await result_raw if hasattr(result_raw, "__await__") else result_raw
            )
            result = int(result) if isinstance(result, str | bytes) else result
            if result == 1:
                if lock_key in self._lock_metadata:
                    self._lock_metadata[lock_key][0] = datetime.now(timezone.utc)
                    self._lock_metadata[lock_key][1] = ttl
                return True
            return False
        except Exception:  # noqa: BLE001
            return False

    async def health_check(self) -> bool:
        """Verify Redis health."""
        try:
            await self._redis.ping()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def get_active_locks(self) -> list[ActiveLock]:
        """Get active locks."""
        self._prune_expired_metadata()
        locks = []
        for lock_key, meta in self._lock_metadata.items():
            acquired_at, ttl, session_id, token, _ = meta
            # prefix:resource_type:resource_id:lock_mode
            parts = lock_key.split(":")
            if len(parts) >= 4:
                _, r_type, r_id, mode = parts[-4:]
                locks.append(
                    ActiveLock(
                        resource_type=r_type,
                        resource_id=r_id,
                        token=token,
                        acquired_at=acquired_at,
                        ttl_seconds=ttl,
                        session_id=session_id,
                    )
                )
        return locks

    async def close(self) -> None:
        """Close Redis connection."""
        await self._redis.close()
