from __future__ import annotations

import asyncio

import pytest

from cqrs_ddd_health.registry import HealthRegistry


def test_singleton() -> None:
    a = HealthRegistry.get_instance()
    b = HealthRegistry.get_instance()
    assert a is b


@pytest.mark.asyncio
async def test_check_all_and_status() -> None:
    registry = HealthRegistry(heartbeat_timeout_seconds=1)
    registry.register("ok", lambda: True)
    registry.register("bad", lambda: False)
    registry.heartbeat("worker-a")
    result = await registry.check_all()
    assert result["ok"] == "up"
    assert result["bad"] == "down"
    assert result["worker-a"] == "up"

    status = await registry.status()
    assert "components" in status
    assert "timestamp" in status
    assert "heartbeats" in status


@pytest.mark.asyncio
async def test_heartbeat_timeout_marks_down() -> None:
    registry = HealthRegistry(heartbeat_timeout_seconds=0)
    registry.heartbeat("worker-b")
    await asyncio.sleep(0)
    result = await registry.check_all()
    assert result["worker-b"] == "down"
