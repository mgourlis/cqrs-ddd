"""Tests for RedisCacheService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from cqrs_ddd_redis.cache import RedisCacheService


@pytest.mark.asyncio()
class TestRedisCacheService:
    @pytest_asyncio.fixture
    async def redis_client(self):
        client = AsyncMock()
        # Mock pipeline properly as a synchronous method returning a context manager
        pipeline_mock = AsyncMock()

        # Pipeline methods are synchronous (builder pattern)
        pipeline_mock.set = MagicMock()
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
