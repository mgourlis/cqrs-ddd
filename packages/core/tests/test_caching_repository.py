"""Tests for CachingRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_core.adapters.decorators.caching_repository import CachingRepository
from cqrs_ddd_core.ports.repository import IRepository


@pytest.mark.asyncio
class TestCachingRepository:
    @pytest.fixture
    def inner_repo(self):
        return AsyncMock(spec=IRepository)

    @pytest.fixture
    def cache_service(self):
        return AsyncMock()

    @pytest.fixture
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

    async def test_list_all_without_ids(self, caching_repo, cache_service, inner_repo):
        """list_all without IDs delegates to inner repo."""
        inner_repo.list_all.return_value = ["entity1", "entity2"]

        result = await caching_repo.list_all()

        assert result == ["entity1", "entity2"]
        inner_repo.list_all.assert_called_with(None, None)
        cache_service.get_batch.assert_not_called()

    async def test_list_all_with_ids_full_cache_hit(
        self, caching_repo, cache_service, inner_repo
    ):
        """list_all with IDs uses read-through caching - all cached."""
        cache_service.get_batch.return_value = ["entity1", "entity2", "entity3"]

        result = await caching_repo.list_all(entity_ids=["id1", "id2", "id3"])

        assert result == ["entity1", "entity2", "entity3"]
        cache_service.get_batch.assert_called_once()
        inner_repo.list_all.assert_not_called()

    async def test_list_all_with_ids_partial_cache_hit(
        self, caching_repo, cache_service, inner_repo
    ):
        """list_all with IDs - some cached, some fetched from DB."""
        # id1 cached, id2 and id3 not cached
        entity1 = MagicMock(id="id1")
        cache_service.get_batch.return_value = [entity1, None, None]
        entity2 = MagicMock(id="id2")
        entity3 = MagicMock(id="id3")
        inner_repo.list_all.return_value = [entity2, entity3]

        result = await caching_repo.list_all(entity_ids=["id1", "id2", "id3"])

        # Should return all entities
        assert len(result) == 3
        # Should fetch missing from inner repo
        inner_repo.list_all.assert_called_once()
        # Should cache newly fetched entities
        cache_service.set_batch.assert_called_once()

    async def test_list_all_with_ids_full_cache_miss(
        self, caching_repo, cache_service, inner_repo
    ):
        """list_all with IDs - all miss cache, fetched from DB."""
        cache_service.get_batch.return_value = [None, None, None]
        entity1 = MagicMock(id="id1")
        entity2 = MagicMock(id="id2")
        entity3 = MagicMock(id="id3")
        inner_repo.list_all.return_value = [entity1, entity2, entity3]

        result = await caching_repo.list_all(entity_ids=["id1", "id2", "id3"])

        assert len(result) == 3
        inner_repo.list_all.assert_called_once()
        cache_service.set_batch.assert_called_once()

    async def test_execute_read_through_batch_key_generation(
        self, caching_repo, cache_service, inner_repo
    ):
        """_execute_read_through generates correct cache keys."""
        cache_service.get_batch.return_value = [None, None]
        inner_repo.list_all.return_value = [
            MagicMock(id="id1"),
            MagicMock(id="id2"),
        ]

        await caching_repo.list_all(entity_ids=["id1", "id2"])

        # Verify cache keys
        cache_keys = cache_service.get_batch.call_args[0][0]
        assert cache_keys == ["TestEntity:id1", "TestEntity:id2"]

    async def test_execute_read_through_collects_missing_ids(
        self, caching_repo, cache_service, inner_repo
    ):
        """_execute_read_through correctly identifies missing IDs."""
        # id1 and id3 cached, id2 missing
        cache_service.get_batch.return_value = ["entity1", None, "entity3"]
        missing_entity = MagicMock(id="id2")
        inner_repo.list_all.return_value = [missing_entity]

        result = await caching_repo.list_all(entity_ids=["id1", "id2", "id3"])

        # Should only fetch id2 from inner repo
        call_args = inner_repo.list_all.call_args[0]
        assert call_args[0] == ["id2"]
        # Result should include all three
        assert len(result) == 3

    async def test_search_bypasses_cache(self, caching_repo, cache_service, inner_repo):
        """search() bypasses cache and delegates to inner repo."""
        from cqrs_ddd_core.ports.search_result import SearchResult

        mock_spec = MagicMock()
        search_result = SearchResult(
            list_fn=AsyncMock(return_value=["entity1", "entity2"]),
            stream_fn=AsyncMock(),
        )
        inner_repo.search.return_value = search_result

        result = await caching_repo.search(mock_spec)

        inner_repo.search.assert_called_with(mock_spec, None)
        cache_service.get_batch.assert_not_called()
        cache_service.set_batch.assert_not_called()
        assert result == search_result

    async def test_get_cache_failure_degrades_gracefully(
        self, caching_repo, cache_service, inner_repo
    ):
        """Cache get failure falls back to inner repo."""
        cache_service.get.side_effect = Exception("Cache unavailable")
        inner_repo.get.return_value = "db_entity"

        result = await caching_repo.get("id1")

        assert result == "db_entity"
        inner_repo.get.assert_called_once()

    async def test_set_cache_failure_degrades_gracefully(
        self, caching_repo, cache_service, inner_repo
    ):
        """Cache set failure doesn't break get operation."""
        cache_service.get.return_value = None
        cache_service.set.side_effect = Exception("Cache unavailable")
        inner_repo.get.return_value = "db_entity"

        result = await caching_repo.get("id1")

        # Should still return entity despite cache failure
        assert result == "db_entity"
        inner_repo.get.assert_called_once()

    async def test_get_batch_cache_failure_degrades_gracefully(
        self, caching_repo, cache_service, inner_repo
    ):
        """Cache get_batch failure falls back to inner repo."""
        cache_service.get_batch.side_effect = Exception("Cache unavailable")
        entity1 = MagicMock(id="id1")
        entity2 = MagicMock(id="id2")
        inner_repo.list_all.return_value = [entity1, entity2]

        result = await caching_repo.list_all(entity_ids=["id1", "id2"])

        assert len(result) == 2
        inner_repo.list_all.assert_called_once()

    async def test_set_batch_cache_failure_degrades_gracefully(
        self, caching_repo, cache_service, inner_repo
    ):
        """Cache set_batch failure doesn't break list_all operation."""
        cache_service.get_batch.return_value = [None, None]
        cache_service.set_batch.side_effect = Exception("Cache unavailable")
        entity1 = MagicMock(id="id1")
        entity2 = MagicMock(id="id2")
        inner_repo.list_all.return_value = [entity1, entity2]

        result = await caching_repo.list_all(entity_ids=["id1", "id2"])

        # Should still return entities despite cache failure
        assert len(result) == 2
        inner_repo.list_all.assert_called_once()

    async def test_delete_cache_invalidation_failure_degrades_gracefully(
        self, caching_repo, cache_service, inner_repo
    ):
        """Cache delete failure doesn't break delete operation."""
        cache_service.delete.side_effect = Exception("Cache unavailable")
        inner_repo.delete.return_value = "id1"

        result = await caching_repo.delete("id1")

        # Delete should still succeed despite cache failure
        assert result == "id1"
        inner_repo.delete.assert_called_once()

    async def test_list_all_caches_fetched_entities(
        self, caching_repo, cache_service, inner_repo
    ):
        """list_all caches entities fetched from inner repo."""
        cache_service.get_batch.return_value = [None, None]
        entity1 = MagicMock(id="id1")
        entity2 = MagicMock(id="id2")
        inner_repo.list_all.return_value = [entity1, entity2]

        await caching_repo.list_all(entity_ids=["id1", "id2"])

        # Verify entities were cached
        cache_service.set_batch.assert_called_once()
        cached_items = cache_service.set_batch.call_args[0][0]
        assert len(cached_items) == 2
        assert cached_items[0]["cache_key"] == "TestEntity:id1"
        assert cached_items[1]["cache_key"] == "TestEntity:id2"
