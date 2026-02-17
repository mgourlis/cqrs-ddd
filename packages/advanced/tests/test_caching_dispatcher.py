from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_advanced_core.persistence.caching import CachingPersistenceDispatcher
from cqrs_ddd_advanced_core.ports.dispatcher import IPersistenceDispatcher
from cqrs_ddd_core.domain.aggregate import AggregateRoot, Modification
from cqrs_ddd_core.ports.cache import ICacheService


class MockEntity(AggregateRoot):
    pass


@pytest.mark.asyncio()
class TestCachingPersistenceDispatcher:
    @pytest.fixture()
    def inner_dispatcher(self):
        return AsyncMock(spec=IPersistenceDispatcher)

    @pytest.fixture()
    def cache_service(self):
        return AsyncMock(spec=ICacheService)

    @pytest.fixture()
    def caching_dispatcher(self, inner_dispatcher, cache_service):
        return CachingPersistenceDispatcher(inner_dispatcher, cache_service)

    async def test_apply_invalidates_cache(
        self, caching_dispatcher, inner_dispatcher, cache_service
    ):
        modification = MagicMock(spec=Modification)
        entity = MockEntity(id="id1")
        modification.entity = entity
        inner_dispatcher.apply.return_value = "id1"

        await caching_dispatcher.apply(modification)

        inner_dispatcher.apply.assert_called_once()
        cache_service.delete_batch.assert_called()
        # Check keys
        keys = cache_service.delete_batch.call_args[0][0]
        assert "MockEntity:id1" in keys

    async def test_fetch_domain_cache_hit(
        self, caching_dispatcher, inner_dispatcher, cache_service
    ):
        cache_service.get_batch.return_value = ["cached_entity"]

        result = await caching_dispatcher.fetch_domain(MockEntity, ["id1"])

        assert result == ["cached_entity"]
        cache_service.get_batch.assert_called_with(["MockEntity:id1"], cls=MockEntity)
        inner_dispatcher.fetch_domain.assert_not_called()

    async def test_fetch_domain_cache_miss(
        self, caching_dispatcher, inner_dispatcher, cache_service
    ):
        cache_service.get_batch.return_value = [None]
        metric = MagicMock()
        metric.id = "id1"
        inner_dispatcher.fetch_domain.return_value = [metric]

        result = await caching_dispatcher.fetch_domain(MockEntity, ["id1"])

        assert result == [metric]
        inner_dispatcher.fetch_domain.assert_called_with(MockEntity, ["id1"], None)
        cache_service.set_batch.assert_called()
