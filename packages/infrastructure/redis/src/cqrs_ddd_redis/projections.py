"""Redis implementation of IProjectionPositionStore."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cqrs_ddd_advanced_core.ports.projection import IProjectionPositionStore

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


KEY_PREFIX = "projection_position"


class RedisProjectionPositionStore(IProjectionPositionStore):
    """
    Redis implementation of IProjectionPositionStore.

    Keys: projection_position:{projection_name}. uow is accepted for
    protocol compliance but ignored (Redis has no transaction with
    the projection database).
    """

    def __init__(
        self,
        redis_client: Redis[bytes],
        *,
        key_prefix: str = KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _key(self, projection_name: str) -> str:
        return f"{self._key_prefix}:{projection_name}"

    async def get_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> int | None:
        value = await self._redis.get(self._key(projection_name))
        return int(value) if value else None

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        await self._redis.set(self._key(projection_name), str(position))

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        await self._redis.delete(self._key(projection_name))
