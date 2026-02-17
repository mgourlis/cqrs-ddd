"""Redis-specific exceptions for cqrs-ddd-redis."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import (
    ConcurrencyError,
    InfrastructureError,
)


class RedisError(InfrastructureError):
    """Base class for all Redis-related infrastructure errors."""


class RedisConnectionError(RedisError):
    """Raised when connectivity to Redis fails."""


class RedisLockError(RedisError, ConcurrencyError):
    """Raised when a Redlock-specific error occurs.

    This combines technical infrastructure failure with semantic
    concurrency failure, allowing handlers to catch it as either.
    """
