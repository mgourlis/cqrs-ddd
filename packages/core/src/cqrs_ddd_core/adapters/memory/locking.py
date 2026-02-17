"""InMemoryLockStrategy — testing and single-process implementation of ILockStrategy."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from ...ports.locking import ActiveLock, ILockStrategy
from ...primitives.exceptions import ConcurrencyError

if TYPE_CHECKING:
    from ...primitives.locking import ResourceIdentifier

logger = logging.getLogger("cqrs_ddd.locking")


@dataclass
class _FIFOLock:
    """
    FIFO lock that ensures waiters are served in order.

    Prevents starvation by maintaining a strict queue of waiters.
    Queue size is bounded to prevent unbounded memory growth.
    """

    _locked: bool = False
    _waiters: asyncio.Queue[asyncio.Event] = field(default_factory=asyncio.Queue)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    max_queue_size: int = 100  # Prevent unbounded growth

    async def acquire(self, timeout: float = 10.0) -> None:
        """Acquire lock - waits in FIFO order if already locked."""
        async with self._lock:
            if not self._locked:
                # Lock is free - take it immediately
                self._locked = True
                logger.debug("Lock acquired immediately (no queue)")
                return

        # Lock is busy - check if queue has space
        queue_size = self._waiters.qsize()
        if queue_size >= self.max_queue_size:
            raise ConcurrencyError(
                f"Lock queue full ({queue_size}/{self.max_queue_size}). "
                "Too many concurrent requests - apply backpressure."
            )

        # Get in line
        event = asyncio.Event()
        await self._waiters.put(event)
        position = self._waiters.qsize()
        logger.debug(
            "Waiting in queue at position %d/%d", position, self.max_queue_size
        )

        try:
            # Wait for our turn with timeout
            await asyncio.wait_for(event.wait(), timeout=timeout)

            async with self._lock:
                self._locked = True
                logger.debug("Lock acquired from queue")
        except asyncio.TimeoutError as err:
            # Remove ourselves from queue if we timed out
            # (best effort - may have already been removed)
            logger.warning("Lock acquisition timed out after %.1fs", timeout)
            raise ConcurrencyError(
                f"Lock acquisition timeout after {timeout}s"
            ) from err

    def release(self) -> None:
        """Release lock and wake up next waiter in FIFO order."""
        if not self._waiters.empty():
            # Wake up next waiter
            try:
                event = self._waiters.get_nowait()
                event.set()
                logger.debug(
                    "Woke up next waiter (queue size: %d)", self._waiters.qsize()
                )
            except asyncio.QueueEmpty:
                self._locked = False
        else:
            self._locked = False
            logger.debug("Lock released (no waiters)")


@dataclass
class _LockState:
    """State for a single resource lock."""

    fifo_lock: _FIFOLock
    token: str
    session_id: str | None
    ref_count: int = 0


class InMemoryLockStrategy(ILockStrategy):
    """
    In-memory implementation of ILockStrategy with FIFO queuing.

    Features:
    - FIFO lock ordering (prevents starvation)
    - Reentrancy support via session_id
    - Useful for testing and single-process applications
    """

    def __init__(self) -> None:
        self._locks: dict[tuple[str, str], _LockState] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(
        self,
        resource: ResourceIdentifier,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,  # noqa: ARG002
        session_id: str | None = None,
    ) -> str:
        key = (resource.resource_type, resource.resource_id)

        async with self._global_lock:
            state = self._locks.get(key)
            if state is None:
                # Create new lock for this resource
                state = _LockState(
                    fifo_lock=_FIFOLock(),
                    token=str(uuid4()),
                    session_id=None,
                )
                self._locks[key] = state

            # Reentrancy check
            if session_id is not None and state.session_id == session_id:
                state.ref_count += 1
                logger.debug(
                    "Reentrant lock acquired: %s (count=%d)", key, state.ref_count
                )
                return state.token

        # Acquire FIFO lock (waits in queue if necessary)
        await state.fifo_lock.acquire(timeout=timeout)

        # Update state after acquiring
        async with self._global_lock:
            if state.session_id is None:
                state.session_id = session_id
            state.ref_count = 1

        logger.debug("Lock acquired: %s", resource)
        return state.token

    async def extend(
        self,
        resource: ResourceIdentifier,
        token: str,
        ttl: float,
    ) -> bool:
        """
        Extend lock TTL.

        For in-memory implementation, just verify the lock is still held.
        Real implementations (Redis) would update the TTL.
        """
        key = (resource.resource_type, resource.resource_id)

        async with self._global_lock:
            state = self._locks.get(key)
            if state is None or state.token != token:
                return False

            # In-memory: TTL not tracked, just verify ownership
            logger.debug("Lock extended: %s (ttl=%.1fs)", key, ttl)
            return True

    async def release(
        self,
        resource: ResourceIdentifier,
        token: str,
    ) -> None:
        key = (resource.resource_type, resource.resource_id)

        async with self._global_lock:
            state = self._locks.get(key)
            if state is None or state.token != token:
                logger.warning("Attempted to release invalid or expired lock: %s", key)
                return

            state.ref_count -= 1
            if state.ref_count <= 0:
                state.session_id = None
                state.fifo_lock.release()
                # Clean up to prevent memory leaks
                self._locks.pop(key)
                logger.debug("Lock cleaned up: %s", key)

    async def health_check(self) -> bool:
        """
        Verify lock service is healthy.

        For in-memory implementation, this always returns True
        since there's no external dependency that could fail.

        Subclasses using Redis, database, etc. should override
        this to ping the external service.
        """
        return True

    async def get_active_locks(self) -> list[ActiveLock]:
        """Get all currently active locks."""
        from datetime import datetime, timezone

        async with self._global_lock:
            locks = []
            for (resource_type, resource_id), state in self._locks.items():
                locks.append(
                    ActiveLock(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        token=state.token,
                        acquired_at=datetime.now(timezone.utc),  # Approximate
                        ttl_seconds=30.0,  # Default TTL
                        session_id=state.session_id,
                    )
                )
            return locks
