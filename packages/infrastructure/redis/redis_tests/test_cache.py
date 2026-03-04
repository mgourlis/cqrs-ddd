"""Tests for RedisCacheService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from cqrs_ddd_redis.cache import RedisCacheService


@pytest.mark.asyncio
class TestRedisCacheService:
    @pytest_asyncio.fixture
    async def redis_client(self):
        client = AsyncMock()
        # Mock pipeline properly as a synchronous method returning a context manager
        pipeline_mock = AsyncMock()

        # Pipeline methods are synchronous (builder pattern)
        pipeline_mock.set = MagicMock()
        pipeline_mock.setex = MagicMock()
        pipeline_mock.mget = MagicMock()
        pipeline_mock.delete = MagicMock()

        # Only execute is async
        pipeline_mock.execute = AsyncMock()

        client.pipeline = MagicMock(return_value=pipeline_mock)
        pipeline_mock.__aenter__.return_value = pipeline_mock
        pipeline_mock.__aexit__.return_value = None
        return client

    @pytest_asyncio.fixture
    async def cache_service(self, redis_client):
        return RedisCacheService(redis_client)

    async def test_get_set(self, cache_service, redis_client):
        key = "test:key"
        value = {"foo": "bar"}
        json_val = json.dumps(value)

        redis_client.get.return_value = json_val

        await cache_service.set(key, value)
        result = await cache_service.get(key)

        assert result == value
        redis_client.set.assert_called_with(key, json_val)
        redis_client.get.assert_called_with(key)

    async def test_get_missing(self, cache_service, redis_client):
        redis_client.get.return_value = None
        result = await cache_service.get("missing")
        assert result is None

    async def test_delete(self, cache_service, redis_client):
        key = "test:del"
        await cache_service.delete(key)
        redis_client.delete.assert_called_with(key)

    async def test_batch_ops(self, cache_service, redis_client):
        items = [
            {"cache_key": "k1", "value": 1},
            {"cache_key": "k2", "value": 2},
        ]

        # Test set_batch
        await cache_service.set_batch(items)
        pipeline = redis_client.pipeline.return_value
        assert pipeline.execute.called

        # Test get_batch
        redis_client.mget.return_value = [json.dumps(1), json.dumps(2), None]
        results = await cache_service.get_batch(["k1", "k2", "k3"])
        assert results == [1, 2, None]

    async def test_pydantic_serialization(self, cache_service, redis_client):
        from pydantic import BaseModel

        class User(BaseModel):
            id: int
            name: str

        user = User(id=1, name="Alice")
        key = "user:1"

        # 1. Test Set (should convert to JSON string)
        await cache_service.set(key, user)
        expected_json = user.model_dump_json()
        redis_client.set.assert_called_with(key, expected_json)

        # 2. Test Get with Class (should return User object)
        redis_client.get.return_value = expected_json
        result = await cache_service.get(key, cls=User)

        assert isinstance(result, User)
        assert result.id == 1
        assert result.name == "Alice"

        # 3. Test Get without Class (should return dict)
        result_dict = await cache_service.get(key)
        assert isinstance(result_dict, dict)
        assert result_dict["id"] == 1

    async def test_set_with_ttl(self, cache_service, redis_client):
        """set() with TTL calls setex."""
        key = "test:ttl"
        value = {"data": "value"}
        ttl = 300

        await cache_service.set(key, value, ttl=ttl)

        redis_client.setex.assert_called_once()
        call_args = redis_client.setex.call_args[0]
        assert call_args[0] == key
        assert call_args[1] == ttl

    async def test_set_without_ttl(self, cache_service, redis_client):
        """set() without TTL uses regular set."""
        key = "test:no-ttl"
        value = {"data": "value"}

        await cache_service.set(key, value)

        redis_client.set.assert_called_once()
        redis_client.setex.assert_not_called()

    async def test_get_cache_miss_returns_none(self, cache_service, redis_client):
        """get() returns None for cache miss."""
        redis_client.get.return_value = None

        result = await cache_service.get("missing_key")

        assert result is None

    async def test_get_with_pydantic_model_returns_instance(
        self, cache_service, redis_client
    ):
        """get() with Pydantic cls returns model instance."""
        from pydantic import BaseModel

        class Product(BaseModel):
            id: int
            name: str
            price: float

        product = Product(id=1, name="Widget", price=9.99)
        redis_client.get.return_value = product.model_dump_json()

        result = await cache_service.get("product:1", cls=Product)

        assert isinstance(result, Product)
        assert result.id == 1
        assert result.name == "Widget"
        assert result.price == 9.99

    async def test_get_error_handling(self, cache_service, redis_client):
        """get() handles Redis errors gracefully."""
        redis_client.get.side_effect = Exception("Redis connection error")

        result = await cache_service.get("key")

        assert result is None

    async def test_set_error_handling(self, cache_service, redis_client):
        """set() handles Redis errors gracefully."""
        redis_client.set.side_effect = Exception("Redis connection error")

        # Should not raise
        await cache_service.set("key", "value")

    async def test_delete_error_handling(self, cache_service, redis_client):
        """delete() handles Redis errors gracefully."""
        redis_client.delete.side_effect = Exception("Redis connection error")

        # Should not raise
        await cache_service.delete("key")

    async def test_get_batch_with_empty_keys(self, cache_service, redis_client):
        """get_batch() with empty keys returns empty list."""
        result = await cache_service.get_batch([])

        assert result == []
        redis_client.mget.assert_not_called()

    async def test_get_batch_with_pydantic_cls(self, cache_service, redis_client):
        """get_batch() with Pydantic cls deserializes each item."""
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int
            name: str

        item1 = Item(id=1, name="First")
        item2 = Item(id=2, name="Second")

        redis_client.mget.return_value = [
            item1.model_dump_json(),
            item2.model_dump_json(),
            None,  # Cache miss
        ]

        results = await cache_service.get_batch(
            ["item:1", "item:2", "item:3"], cls=Item
        )

        assert len(results) == 3
        assert isinstance(results[0], Item)
        assert isinstance(results[1], Item)
        assert results[2] is None
        assert results[0].id == 1
        assert results[1].name == "Second"

    async def test_get_batch_error_handling(self, cache_service, redis_client):
        """get_batch() handles Redis errors gracefully."""
        redis_client.mget.side_effect = Exception("Redis connection error")

        results = await cache_service.get_batch(["k1", "k2"])

        assert results == [None, None]

    async def test_set_batch_with_empty_items(self, cache_service, redis_client):
        """set_batch() with empty items does nothing."""
        await cache_service.set_batch([])

        # Pipeline should not be called
        redis_client.pipeline.assert_not_called()

    async def test_set_batch_with_ttl(self, cache_service, redis_client):
        """set_batch() with TTL uses setex for each item."""
        items = [
            {"cache_key": "k1", "value": {"data": "v1"}},
            {"cache_key": "k2", "value": {"data": "v2"}},
        ]
        ttl = 600

        await cache_service.set_batch(items, ttl=ttl)

        pipeline = redis_client.pipeline.return_value
        # Verify setex was called on pipeline
        assert pipeline.setex.call_count == 2

    async def test_set_batch_with_pydantic_models(self, cache_service, redis_client):
        """set_batch() serializes Pydantic models correctly."""
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int
            value: str

        items = [
            {"cache_key": "k1", "value": Item(id=1, value="first")},
            {"cache_key": "k2", "value": Item(id=2, value="second")},
        ]

        await cache_service.set_batch(items)

        pipeline = redis_client.pipeline.return_value
        assert pipeline.execute.called

    async def test_set_batch_error_handling(self, cache_service, redis_client):
        """set_batch() handles Redis errors gracefully."""
        pipeline = redis_client.pipeline.return_value
        pipeline.execute.side_effect = Exception("Redis connection error")

        items = [{"cache_key": "k1", "value": "v1"}]

        # Should not raise
        await cache_service.set_batch(items)

    async def test_delete_batch(self, cache_service, redis_client):
        """delete_batch() deletes multiple keys."""
        keys = ["k1", "k2", "k3"]

        await cache_service.delete_batch(keys)

        redis_client.delete.assert_called_once_with(*keys)

    async def test_delete_batch_with_empty_keys(self, cache_service, redis_client):
        """delete_batch() with empty keys does nothing."""
        await cache_service.delete_batch([])

        redis_client.delete.assert_not_called()

    async def test_delete_batch_error_handling(self, cache_service, redis_client):
        """delete_batch() handles Redis errors gracefully."""
        redis_client.delete.side_effect = Exception("Redis connection error")

        # Should not raise
        await cache_service.delete_batch(["k1", "k2"])

    async def test_clear_namespace(self, cache_service, redis_client):
        """clear_namespace() scans and deletes keys with prefix."""
        # Mock SCAN to simulate cursor-based iteration
        # Redis SCAN returns (cursor, keys) where cursor=0 means done
        call_count = [0]

        async def scan_side_effect(cursor, match):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return non-zero cursor with keys
                return (1, [b"prefix:key1", b"prefix:key2"])
            # Second call: return cursor=0 (done) with final keys
            return (0, [b"prefix:key3"])

        redis_client.scan = AsyncMock(side_effect=scan_side_effect)

        await cache_service.clear_namespace("prefix")

        # Verify SCAN was called twice (once with cursor=0, once with cursor=1)
        assert redis_client.scan.call_count == 2
        # Verify DELETE was called for both batches
        assert redis_client.delete.call_count == 2
        # Verify the keys were deleted
        redis_client.delete.assert_any_call(b"prefix:key1", b"prefix:key2")
        redis_client.delete.assert_any_call(b"prefix:key3")

    async def test_clear_namespace_error_handling(self, cache_service, redis_client):
        """clear_namespace() handles Redis errors gracefully."""
        redis_client.scan.side_effect = Exception("Redis connection failed")

        # Should not raise, just log warning
        await cache_service.clear_namespace("prefix")

        redis_client.scan.assert_called_once()
