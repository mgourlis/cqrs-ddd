"""LoggingMiddleware — logs command execution details."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..ports.middleware import IMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger("cqrs_ddd.middleware")


class LoggingMiddleware(IMiddleware):
    """Logs command execution — name, duration, correlation_id."""

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Log the command execution."""
        msg_name = type(message).__name__
        correlation_id = getattr(message, "correlation_id", None)
        logger.info(
            "Handling %s (correlation_id=%s)",
            msg_name,
            correlation_id,
        )
        start = time.perf_counter()
        try:
            result = await next_handler(message)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("%s completed in %.2fms", msg_name, elapsed)
            return result
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception("%s failed after %.2fms", msg_name, elapsed)
            raise
