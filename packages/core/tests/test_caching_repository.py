"""Tests for CachingRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_core.adapters.decorators.caching_repository import CachingRepository
from cqrs_ddd_core.ports.repository import IRepository


@pytest.mark.asyncio()
class TestCachingRepository:
    @pytest.fixture()
    def inner_repo(self):
        return AsyncMock(spec=IRepository)

    @pytest.fixture()
    def cache_service(self):
        return AsyncMock()

    @pytest.fixture()
    def caching_repo(self, inner_repo, cache_service):
        return CachingRepository(inner_repo, cache_service, "TestEntity")

    async def test_get_with_cls(self, inner_repo, cache_service):
        repo = CachingRepository(
            inner_repo, cache_service, "TestEntity", entity_cls=dict
        )
        cache_service.get.return_value = {}

        await repo.get("id1")

        cache_service.get.assert_called_with("TestEntity:id1", cls=dict)

    async def test_get_hit(self, caching_repo, cache_service, inner_repo):
        cache_service.get.return_value = "cached_entity"

        result = await caching_repo.get("id1")

        assert result == "cached_entity"
        # Since we didn't pass entity_cls in fixture, cls should be None
        cache_service.get.assert_called_with("TestEntity:id1", cls=None)
        inner_repo.get.assert_not_called()

    async def test_get_miss(self, caching_repo, cache_service, inner_repo):
        cache_service.get.return_value = None
        inner_repo.get.return_value = "db_entity"

        result = await caching_repo.get("id1")

        assert result == "db_entity"
        inner_repo.get.assert_called_with("id1", None)
        cache_service.set.assert_called_with("TestEntity:id1", "db_entity", ttl=300)

    async def test_add(self, caching_repo, cache_service, inner_repo):
        entity = MagicMock()
        entity.id = "id1"
        inner_repo.add.return_value = "id1"

        await caching_repo.add(entity)

        inner_repo.add.assert_called_with(entity, None)
        cache_service.delete.assert_called_with("TestEntity:id1")

    async def test_delete(self, caching_repo, cache_service, inner_repo):
        inner_repo.delete.return_value = "id1"

        await caching_repo.delete("id1")

        inner_repo.delete.assert_called_with("id1", None)
        cache_service.delete.assert_called_with("TestEntity:id1")
