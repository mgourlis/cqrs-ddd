"""Tests for InMemorySessionStore."""

from __future__ import annotations

import asyncio

import pytest

from cqrs_ddd_identity.session import InMemorySessionStore


class TestInMemorySessionStore:
    """Test InMemorySessionStore."""

    @pytest.fixture
    def store(self) -> InMemorySessionStore:
        return InMemorySessionStore()

    @pytest.mark.asyncio
    async def test_store_and_get(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"a": 1, "b": "two"})
        data = await store.get("k1")
        assert data == {"a": 1, "b": "two"}

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store: InMemorySessionStore) -> None:
        assert await store.get("missing") is None

    @pytest.mark.asyncio
    async def test_store_without_ttl_no_expiry(
        self, store: InMemorySessionStore
    ) -> None:
        await store.store("k1", {"x": 1}, ttl=None)
        await asyncio.sleep(0.05)
        assert await store.get("k1") == {"x": 1}

    @pytest.mark.asyncio
    async def test_store_with_ttl_expires(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"x": 1}, ttl=1)
        await asyncio.sleep(1.1)
        assert await store.get("k1") is None

    @pytest.mark.asyncio
    async def test_store_with_ttl_zero_no_expiry_set(
        self, store: InMemorySessionStore
    ) -> None:
        await store.store("k1", {"x": 1}, ttl=0)
        assert await store.get("k1") == {"x": 1}

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"a": 1})
        await store.delete("k1")
        assert await store.get("k1") is None

    @pytest.mark.asyncio
    async def test_delete_missing_no_error(self, store: InMemorySessionStore) -> None:
        await store.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_exists_true_when_stored(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"a": 1})
        assert await store.exists("k1") is True

    @pytest.mark.asyncio
    async def test_exists_false_when_missing(self, store: InMemorySessionStore) -> None:
        assert await store.exists("missing") is False

    @pytest.mark.asyncio
    async def test_exists_false_after_expiry(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"x": 1}, ttl=1)
        await asyncio.sleep(1.1)
        assert await store.exists("k1") is False

    @pytest.mark.asyncio
    async def test_clear_all_removes_all(self, store: InMemorySessionStore) -> None:
        await store.store("k1", {"a": 1})
        await store.store("k2", {"b": 2})
        store.clear_all()
        assert await store.get("k1") is None
        assert await store.get("k2") is None
