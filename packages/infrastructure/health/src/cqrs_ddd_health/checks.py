"""Health check implementations."""

from __future__ import annotations

import inspect
from typing import Any


class DatabaseHealthCheck:
    """Health check for database connectivity."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def __call__(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False


class RedisHealthCheck:
    """Health check for Redis connectivity."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def __call__(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:  # noqa: BLE001
            return False


class MessageBrokerHealthCheck:
    """Health check for message broker connectivity."""

    def __init__(self, broker_client: Any) -> None:
        self._broker = broker_client

    async def __call__(self) -> bool:
        try:
            health_check = getattr(self._broker, "health_check", None)
            if callable(health_check):
                result = health_check()
                if inspect.isawaitable(result):
                    result = await result
                return bool(result)

            is_connected = getattr(self._broker, "is_connected", None)
            if callable(is_connected):
                result = is_connected()
                if inspect.isawaitable(result):
                    result = await result
                return bool(result)

            return False
        except Exception:  # noqa: BLE001
            return False
