"""Tests for MongoCheckpointStore."""

import pytest

from cqrs_ddd_persistence_mongo import MongoCheckpointStore


@pytest.mark.asyncio
async def test_get_position_returns_none_for_new_projection(mongo_connection):
    """Test that get_position returns None for a projection that has never run."""
    store = MongoCheckpointStore(mongo_connection)

    position = await store.get_position("test_projection")

    assert position is None


@pytest.mark.asyncio
async def test_save_and_get_position(mongo_connection):
    """Test that save_position persists and get_position retrieves the position."""
    store = MongoCheckpointStore(mongo_connection)

    await store.save_position("test_projection", 42)
    position = await store.get_position("test_projection")

    assert position == 42


@pytest.mark.asyncio
async def test_save_position_upserts_existing(mongo_connection):
    """Test that save_position updates existing position."""
    store = MongoCheckpointStore(mongo_connection)

    await store.save_position("test_projection", 10)
    await store.save_position("test_projection", 20)
    position = await store.get_position("test_projection")

    assert position == 20


@pytest.mark.asyncio
async def test_multiple_projections(mongo_connection):
    """Test that multiple projections maintain separate positions."""
    store = MongoCheckpointStore(mongo_connection)

    await store.save_position("projection_1", 100)
    await store.save_position("projection_2", 200)

    assert await store.get_position("projection_1") == 100
    assert await store.get_position("projection_2") == 200


@pytest.mark.asyncio
async def test_custom_database(mongo_connection):
    """Test that checkpoint store can use a custom database."""
    store = MongoCheckpointStore(mongo_connection, database="test_db")

    await store.save_position("test_projection", 99)
    position = await store.get_position("test_projection")

    assert position == 99
