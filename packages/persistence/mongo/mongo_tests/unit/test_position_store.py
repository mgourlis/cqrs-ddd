"""Unit tests for MongoProjectionPositionStore — get/save/reset with and without UoW."""

import pytest

from cqrs_ddd_persistence_mongo.advanced.position_store import MongoProjectionPositionStore
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def mock_connection():
    from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager

    connection = MongoConnectionManager.__new__(MongoConnectionManager)
    client = AsyncMongoMockClient(default_database_name="test_db")
    connection._client = client  # .client property returns _client
    connection._database = "test_db"
    connection._url = "mongodb://mock:27017"
    return connection


@pytest.mark.asyncio
async def test_save_and_get_position_without_uow(mock_connection):
    store = MongoProjectionPositionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.save_position("my_projection", 100)
    pos = await store.get_position("my_projection")
    assert pos == 100


@pytest.mark.asyncio
async def test_get_position_none_when_never_saved(mock_connection):
    store = MongoProjectionPositionStore(
        connection=mock_connection,
        database="test_db",
    )
    pos = await store.get_position("unknown")
    assert pos is None


@pytest.mark.asyncio
async def test_reset_position_removes_entry(mock_connection):
    store = MongoProjectionPositionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.save_position("my_projection", 50)
    await store.reset_position("my_projection")
    pos = await store.get_position("my_projection")
    assert pos is None


@pytest.mark.asyncio
async def test_save_position_overwrites(mock_connection):
    store = MongoProjectionPositionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.save_position("my_projection", 10)
    await store.save_position("my_projection", 20)
    pos = await store.get_position("my_projection")
    assert pos == 20


@pytest.mark.asyncio
async def test_multiple_projections_independent(mock_connection):
    store = MongoProjectionPositionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.save_position("proj_a", 1)
    await store.save_position("proj_b", 2)
    assert await store.get_position("proj_a") == 1
    assert await store.get_position("proj_b") == 2
    await store.reset_position("proj_a")
    assert await store.get_position("proj_a") is None
    assert await store.get_position("proj_b") == 2
