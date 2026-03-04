"""Tests for PermissionDecisionCache."""

from __future__ import annotations

import json
from typing import Any

import pytest

from cqrs_ddd_access_control.cache import PermissionDecisionCache
from cqrs_ddd_access_control.models import AuthorizationDecision

# ---------------------------------------------------------------------------
# Stub ICacheService
# ---------------------------------------------------------------------------


class _StubCacheService:
    """Minimal in-memory cache service matching ICacheService protocol."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        self._store[key] = value

    async def clear_namespace(self, namespace: str) -> None:
        # Simple prefix-based clear (strip trailing wildcards)
        prefix = namespace.rstrip("*")
        self._store = {k: v for k, v in self._store.items() if not k.startswith(prefix)}


class _BrokenCacheService:
    """Cache service that raises on operations."""

    async def get(self, key: str) -> str | None:
        return "not valid json {"

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        pass

    async def clear_namespace(self, namespace: str) -> None:
        raise RuntimeError("cache broke")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPermissionDecisionCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc, default_ttl=120)

        decision = AuthorizationDecision(
            allowed=True,
            reason="rbac match",
            evaluator="rbac",
        )
        await cache.set("user-1", "order", "123", "read", decision)
        result = await cache.get("user-1", "order", "123", "read")
        assert result is not None
        assert result.allowed is True
        assert result.reason == "rbac match"
        assert result.evaluator == "rbac"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc)

        result = await cache.get("user-1", "order", "123", "read")
        assert result is None

    @pytest.mark.asyncio
    async def test_wildcard_resource_id(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc)

        decision = AuthorizationDecision(
            allowed=True,
            reason="type-level",
            evaluator="acl",
        )
        await cache.set("u1", "order", None, "read", decision)
        result = await cache.get("u1", "order", None, "read")
        assert result is not None
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_custom_ttl(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc, default_ttl=60)

        decision = AuthorizationDecision(
            allowed=False,
            reason="denied",
            evaluator="pep",
        )
        await cache.set("u1", "doc", "d1", "write", decision, ttl=300)
        result = await cache.get("u1", "doc", "d1", "write")
        assert result is not None
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_invalidate(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc)

        decision = AuthorizationDecision(allowed=True, reason="ok", evaluator="rbac")
        await cache.set("u1", "order", "123", "read", decision)
        await cache.set("u1", "order", "456", "write", decision)

        # Confirm data exists
        assert await cache.get("u1", "order", "123", "read") is not None

        await cache.invalidate("order", "123")
        # After invalidation the key should be removed
        # (our stub uses prefix-based clear)

    @pytest.mark.asyncio
    async def test_invalidate_type_level(self) -> None:
        svc = _StubCacheService()
        cache = PermissionDecisionCache(svc)

        decision = AuthorizationDecision(allowed=True, reason="ok", evaluator="rbac")
        await cache.set("u1", "order", None, "read", decision)
        await cache.invalidate("order")

    @pytest.mark.asyncio
    async def test_parse_error_returns_none(self) -> None:
        svc = _BrokenCacheService()
        cache = PermissionDecisionCache(svc)
        result = await cache.get("u1", "order", "123", "read")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_error_handled(self) -> None:
        svc = _BrokenCacheService()
        cache = PermissionDecisionCache(svc)
        # Should not raise
        await cache.invalidate("order", "123")
