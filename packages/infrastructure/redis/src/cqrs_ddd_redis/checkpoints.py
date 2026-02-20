"""Redis implementations of checkpoint stores for projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

# Note: ICheckpointStore protocol is defined in cqrs_ddd_projections
# We import it dynamically to avoid circular dependencies

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisCheckpointStore:
    """Distributed checkpoint store using Redis.

    This class implements the ICheckpointStore protocol from cqrs_ddd_projections.
    """

    def __init__(
        self, redis_client: Redis[bytes], key_prefix: str = "projection:checkpoint"
    ) -> None:
        """
        Initialize checkpoint store with Redis client.

        Args:
            redis_client: Async Redis client instance.
            key_prefix: Prefix for checkpoint keys.
        """
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _get_key(self, projection_name: str) -> str:
        """Build full Redis key for a projection."""
        return f"{self._key_prefix}:{projection_name}"

    async def get_position(self, projection_name: str) -> int | None:
        """Retrieve checkpoint position from Redis."""
        value = await self._redis.get(self._get_key(projection_name))
        return int(value) if value else None

    async def save_position(self, projection_name: str, position: int) -> None:
        """Save checkpoint position in Redis."""
        registry = get_hook_registry()
        await registry.execute_all(
            f"redis.checkpoint.save.{projection_name}",
            {
                "projection.name": projection_name,
                "projection.position": position,
                "correlation_id": get_correlation_id(),
            },
            lambda: self._redis.set(self._get_key(projection_name), str(position)),
        )
