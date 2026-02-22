from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_health.checks import (
    DatabaseHealthCheck,
    MessageBrokerHealthCheck,
    RedisHealthCheck,
)


@pytest.mark.asyncio
async def test_database_health_check_ok() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=1)

    class _SessionContext:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return session

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return False

    def session_factory():  # type: ignore[no-untyped-def]
        return _SessionContext()

    check = DatabaseHealthCheck(session_factory)
    assert await check() is True


@pytest.mark.asyncio
async def test_redis_health_check_ok() -> None:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    check = RedisHealthCheck(redis)
    assert await check() is True


@pytest.mark.asyncio
async def test_broker_health_check_fail() -> None:
    class _Broker:
        async def is_connected(self) -> bool:
            raise RuntimeError("boom")

    broker = _Broker()
    check = MessageBrokerHealthCheck(broker)
    assert await check() is False


@pytest.mark.asyncio
async def test_broker_health_check_uses_health_check_when_available() -> None:
    class _Broker:
        async def health_check(self) -> bool:
            return True

        async def is_connected(self) -> bool:
            return False

    broker = _Broker()
    check = MessageBrokerHealthCheck(broker)
    assert await check() is True


@pytest.mark.asyncio
async def test_broker_health_check_falls_back_to_is_connected() -> None:
    class _Broker:
        async def is_connected(self) -> bool:
            return True

    broker = _Broker()
    check = MessageBrokerHealthCheck(broker)
    assert await check() is True
