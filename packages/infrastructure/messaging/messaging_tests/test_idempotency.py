"""Tests for IdempotencyFilter."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.ports.cache import ICacheService
from cqrs_ddd_messaging.idempotency import IdempotencyFilter


@pytest.mark.asyncio
async def test_in_memory_is_duplicate_after_mark() -> None:
    f = IdempotencyFilter()
    assert await f.is_duplicate("msg-1") is False
    await f.mark_processed("msg-1")
    assert await f.is_duplicate("msg-1") is True


@pytest.mark.asyncio
async def test_in_memory_clear() -> None:
    f = IdempotencyFilter()
    await f.mark_processed("msg-1")
    f.clear_memory()
    assert await f.is_duplicate("msg-1") is False


class _FakeCacheForIdempotency(ICacheService):
    """Minimal ICacheService implementation for IdempotencyFilter tests."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str, cls: type | None = None) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: object, ttl: int | None = None) -> None:
        self._data[key] = str(value)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def get_batch(self, keys: list[str], cls: type | None = None) -> list:
        return [self._data.get(k) for k in keys]

    async def set_batch(self, items: list[dict], ttl: int | None = None) -> None:
        for it in items:
            self._data[it["cache_key"]] = str(it["value"])

    async def delete_batch(self, keys: list[str]) -> None:
        for k in keys:
            self._data.pop(k, None)

    async def clear_namespace(self, prefix: str) -> None:
        to_del = [k for k in self._data if k.startswith(prefix)]
        for k in to_del:
            del self._data[k]


@pytest.mark.asyncio
async def test_with_cache() -> None:
    cache: ICacheService = _FakeCacheForIdempotency()
    f = IdempotencyFilter(cache=cache, key_prefix="idem:")
    assert await f.is_duplicate("msg-1") is False
    await f.mark_processed("msg-1")
    assert await f.is_duplicate("msg-1") is True
