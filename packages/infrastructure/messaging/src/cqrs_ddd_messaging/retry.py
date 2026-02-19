"""RetryPolicy — exponential backoff, max attempts, jitter."""

from __future__ import annotations

import random


class RetryPolicy:
    """Configurable retry with exponential backoff and jitter."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> None:
        """Configure retry behavior.

        Args:
            max_attempts: Maximum number of delivery attempts (including first).
            base_delay: Initial delay in seconds before first retry.
            max_delay: Cap on delay in seconds.
            jitter: If True, add random jitter to delays to avoid thundering herd.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if base_delay < 0 or max_delay < 0:
            raise ValueError("base_delay and max_delay must be >= 0")
        if base_delay > max_delay:
            raise ValueError("base_delay must be <= max_delay")
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def should_retry(self, attempt: int) -> bool:
        """Return True if another attempt is allowed (attempt is 1-based)."""
        return 1 <= attempt < self.max_attempts

    def delay_for_attempt(self, attempt: int) -> float:
        """Return delay in seconds for the given 1-based attempt.

        Uses exponential backoff: base_delay * 2^(attempt-1), capped by max_delay.
        If jitter is enabled, multiplies by a random factor in [0.5, 1.5].
        """
        if attempt < 1:
            return 0.0
        delay = min(
            self.base_delay * (2 ** (attempt - 1)),
            self.max_delay,
        )
        if self.jitter:
            delay = delay * (0.5 + random.random())  # noqa: S311
        return float(max(0.0, delay))

    async def wait_before_retry(self, attempt: int) -> None:
        """Async sleep for the delay of the given attempt (for use in consumers)."""
        d = self.delay_for_attempt(attempt)
        if d > 0:
            await _sleep(d)


async def _sleep(seconds: float) -> None:
    """Async sleep (overridable for tests)."""
    import asyncio

    await asyncio.sleep(seconds)
