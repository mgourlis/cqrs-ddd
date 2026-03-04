"""Tests for HealthRegistry (lives in cqrs-ddd-health package)."""

from __future__ import annotations

import pytest

pytest.importorskip("cqrs_ddd_health", reason="cqrs-ddd-health not installed")
from cqrs_ddd_health.registry import HealthRegistry


def test_singleton() -> None:
    a = HealthRegistry.get_instance()
    b = HealthRegistry.get_instance()
    assert a is b


@pytest.mark.asyncio
async def test_check_all() -> None:
    reg = HealthRegistry()
    reg.register("a", lambda: True)
    reg.register("b", lambda: False)
    result = await reg.check_all()
    assert result["a"] == "up"
    assert result["b"] == "down"


@pytest.mark.asyncio
async def test_status_contains_timestamp() -> None:
    reg = HealthRegistry()
    reg.register("x", lambda: True)
    st = await reg.status()
    assert "status" in st
    assert "components" in st
    assert "timestamp" in st
