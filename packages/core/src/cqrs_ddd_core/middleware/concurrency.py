"""ConcurrencyGuardMiddleware — automatically locks resources before command
execution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..ports.middleware import IMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..ports.locking import ILockStrategy
    from ..primitives.locking import ResourceIdentifier

logger = logging.getLogger("cqrs_ddd.middleware.concurrency")


class ConcurrencyGuardMiddleware(IMiddleware):
    """
    Middleware that automatically locks resources before command execution.

    Commands that need locking should implement a `get_critical_resources()` method
    that returns a list of `ResourceIdentifier` objects.

    Example:
        ```python
        @dataclass
        class TransferFundsCommand:
            from_account: UUID
            to_account: UUID
            amount: Decimal

            def get_critical_resources(self) -> list[ResourceIdentifier]:
                return [
                    ResourceIdentifier("Account", str(self.from_account)),
                    ResourceIdentifier("Account", str(self.to_account)),
                ]
        ```

    Usage:
        ```python
        concurrency_guard = ConcurrencyGuardMiddleware(lock_strategy)
        mediator = Mediator(
            registry=handler_registry,
            uow_factory=uow_factory,
            middleware_registry=middleware_registry,
        )
        middleware_registry.register(concurrency_guard, order=10)
        ```
    """

    def __init__(
        self,
        lock_strategy: ILockStrategy,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
        fail_open: bool = False,
    ) -> None:
        """
        Initialize concurrency guard middleware.

        Args:
            lock_strategy: Strategy for acquiring/releasing locks
            timeout: Maximum time to wait for each lock acquisition (seconds)
            ttl: Time-to-live for locks - auto-expire to prevent orphans (seconds)
            fail_open: If True, continue execution even if locking fails
                (for graceful degradation)
        """
        self._lock_strategy = lock_strategy
        self._timeout = timeout
        self._ttl = ttl
        self._fail_open = fail_open

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """
        Execute with resource locking if command declares critical resources.

        Args:
            message: The command/query/event being processed
            next_handler: The next step in the middleware pipeline

        Returns:
            The result from the handler
        """
        from ..primitives.exceptions import ConcurrencyError

        # Check if command declares critical resources
        if hasattr(message, "get_critical_resources"):
            resources: list[ResourceIdentifier] = message.get_critical_resources()

            if resources:
                from ..cqrs.concurrency import CriticalSection

                try:
                    # Extract session_id for reentrancy support
                    # (use correlation_id if available)
                    session_id = getattr(message, "correlation_id", None)
                    if session_id is None:
                        # Check metadata if it's a message-like object
                        metadata = getattr(message, "metadata", {})
                        session_id = metadata.get("correlation_id")

                    # Lock all resources before execution
                    async with CriticalSection(
                        resources,
                        self._lock_strategy,
                        timeout=self._timeout,
                        ttl=self._ttl,
                        session_id=session_id,
                    ):
                        return await next_handler(message)
                except ConcurrencyError as exc:
                    if self._fail_open:
                        logger.warning(
                            "Lock acquisition failed but continuing "
                            "(fail-open mode): %s",
                            exc,
                        )
                        return await next_handler(message)
                    raise

        # No locking needed
        return await next_handler(message)
