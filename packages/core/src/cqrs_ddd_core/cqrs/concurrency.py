"""Concurrency utilities for message processing."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..ports.locking import ILockStrategy
    from ..primitives.locking import ResourceIdentifier

logger = logging.getLogger("cqrs_ddd.locking")


class CriticalSection:
    """
    Async context manager that acquires locks on multiple resources.

    Features:
    - Locks multiple resources atomically
    - Prevents deadlocks via sorted acquisition
    - Supports reentrancy via session_id
    - Auto-releases on exit
    - Rolls back partial locks on failure

    Usage:
        ```python
        resources = [
            ResourceIdentifier("Account", "123"),
            ResourceIdentifier("Account", "456"),
        ]

        async with CriticalSection(resources, lock_strategy):
            # Both accounts are locked here
            await transfer_funds()
            # Auto-released on exit
        ```
    """

    def __init__(
        self,
        resources: list[ResourceIdentifier],
        lock_strategy: ILockStrategy,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        session_id: str | None = None,
    ) -> None:
        """
        Initialize critical section.

        Args:
            resources: List of resources to lock (will be deduplicated and sorted)
            lock_strategy: Strategy for acquiring/releasing locks
            timeout: Maximum time to wait for each lock acquisition
            ttl: Time-to-live for locks (auto-expire to prevent orphans)
            session_id: Optional session ID for reentrancy support
        """
        # Deduplicate and consolidate lock modes (write takes precedence over read)
        consolidated: dict[tuple[str, str], ResourceIdentifier] = {}
        for res in resources:
            key = (res.resource_type, res.resource_id)
            if key not in consolidated or res.lock_mode == "write":
                consolidated[key] = res

        # Sort to prevent deadlocks
        self._resources = sorted(consolidated.values())
        self._lock_strategy = lock_strategy
        self._timeout = timeout
        self._ttl = ttl
        self._session_id = session_id

        # Track acquired locks for rollback
        self._acquired: list[tuple[ResourceIdentifier, str]] = []

    async def __aenter__(self) -> CriticalSection:
        """
        Acquire all locks in sorted order.

        If any lock fails, rolls back all previously acquired locks.

        Raises:
            ConcurrencyError: If lock acquisition fails
        """
        from ..primitives.exceptions import LockAcquisitionError

        start = time.time()
        logger.debug(
            "Acquiring %d locks: %s",
            len(self._resources),
            [str(r) for r in self._resources],
        )

        try:
            for resource in self._resources:
                token = await self._lock_strategy.acquire(
                    resource,
                    timeout=self._timeout,
                    ttl=self._ttl,
                    session_id=self._session_id,
                )
                self._acquired.append((resource, token))

            duration = time.time() - start
            logger.info(
                "Locks acquired",
                extra={
                    "resource_types": [r.resource_type for r in self._resources],
                    "resource_count": len(self._resources),
                    "duration_ms": duration * 1000,
                },
            )
            return self

        except Exception as exc:  # noqa: BLE001
            # Roll back already-acquired locks
            # Broad exception catch is intentional: we need to rollback locks
            # for any error (network, timeout, validation, etc.) during acquisition
            await self._rollback()

            if isinstance(exc, LockAcquisitionError):
                raise  # Re-raise with full context

            # Wrap unknown errors
            failed_resource = (
                self._resources[len(self._acquired)]
                if len(self._acquired) < len(self._resources)
                else self._resources[-1]
            )
            raise LockAcquisitionError(
                failed_resource,
                self._timeout,
                reason=f"Rolled back {len(self._acquired)} locks. {exc}",
            ) from exc

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Release all acquired locks in reverse order."""
        await self._rollback()

    async def _rollback(self) -> list[Exception]:
        """Release acquired locks in reverse order (LIFO).

        Returns:
            List of errors encountered during rollback (empty if all successful)
        """
        errors: list[Exception] = []
        attempted = len(self._acquired)

        for resource, token in reversed(self._acquired):
            try:
                await self._lock_strategy.release(resource, token)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to release lock during rollback: %s "
                    "(resource=%s, token=%s)",
                    exc,
                    resource,
                    token,
                )
                errors.append(exc)

        self._acquired.clear()

        if errors:
            logger.warning(
                "Lock rollback incomplete: %d/%d releases failed",
                len(errors),
                attempted,
            )

        return errors
