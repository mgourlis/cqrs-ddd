"""Redis implementations of cache services."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.cache import ICacheService

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("cqrs_ddd.redis_cache")


class RedisCacheService(ICacheService):
    """
    Redis implementation of ICacheService.
    Uses generic JSON serialization.
    """

    def __init__(self, redis_client: Redis[bytes]) -> None:
        self._redis = redis_client

    async def get(self, key: str, cls: type[Any] | None = None) -> Any | None:
        try:
            val = await self._redis.get(key)
            if not val:
                return None

            if cls and hasattr(cls, "model_validate_json"):
                # Pydantic V2 optimized loading
                return cls.model_validate_json(val)
            return json.loads(val)
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis get failed for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            if hasattr(value, "model_dump_json"):
                # Pydantic V2 optimized dumping
                val = value.model_dump_json()
            else:
                val = json.dumps(value, default=str)

            if ttl:
                await self._redis.setex(key, ttl, val)
            else:
                await self._redis.set(key, val)
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis set failed for key %s: %s", key, e)

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis delete failed for key %s: %s", key, e)

    async def get_batch(
        self, keys: list[str], cls: type[Any] | None = None
    ) -> list[Any | None]:
        if not keys:
            return []
        try:
            values = await self._redis.mget(keys)
            results: list[Any] = []
            for v in values:
                if not v:
                    results.append(None)
                    continue

                if cls and hasattr(cls, "model_validate_json"):
                    results.append(cls.model_validate_json(v))
                else:
                    results.append(json.loads(v))
            return results
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis mget failed: %s", e)
            return [None] * len(keys)

    async def set_batch(
        self, items: list[dict[str, Any]], ttl: int | None = None
    ) -> None:
        if not items:
            return

        try:
            # Use pipeline for atomicity/efficiency
            async with self._redis.pipeline() as pipe:
                for item in items:
                    key = item["cache_key"]
                    value = item["value"]

                    if hasattr(value, "model_dump_json"):
                        val = value.model_dump_json()
                    else:
                        val = json.dumps(value, default=str)

                    if ttl:
                        pipe.setex(key, ttl, val)
                    else:
                        pipe.set(key, val)
                await pipe.execute()
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis batch set failed: %s", e)

    async def delete_batch(self, keys: list[str]) -> None:
        if not keys:
            return
        try:
            await self._redis.delete(*keys)
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis batch delete failed: %s", e)

    async def clear_namespace(self, prefix: str) -> None:
        """Caution: This is expensive (SCAN)."""
        try:
            cursor: int = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=f"{prefix}*")
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis clear_namespace failed: %s", e)
