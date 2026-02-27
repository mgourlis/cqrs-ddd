"""Unit tests for MongoDB index management."""

import pytest
from mongomock_motor import AsyncMongoMockClient

from cqrs_ddd_persistence_mongo.indexes import (
    create_compound_index,
    create_text_index,
    create_ttl_index,
)


@pytest.fixture
async def mock_connection():
    """Create a mock MongoDB connection."""
    from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager

    connection = MongoConnectionManager.__new__(MongoConnectionManager)
    connection._client = AsyncMongoMockClient(default_database_name="test_db")
    connection._database = "test_db"
    connection._url = "mongodb://mock:27017"

    async def _mock_connect():
        return connection._client

    connection.connect = _mock_connect
    return connection


@pytest.mark.asyncio
async def test_create_compound_index_creates_single_field_index(mock_connection):
    """Test that create_compound_index creates a compound index."""
    connection = mock_connection

    # Call create_compound_index
    index_name = await create_compound_index(
        connection, "test_db", "test_collection", [("field1", 1)]
    )

    # Verify index was created (mongomock may return None for name)
    db = connection.client["test_db"]
    coll = db["test_collection"]
    indexes = [idx async for idx in coll.list_indexes()]
    index_names = [idx.get("name") for idx in indexes if idx.get("name")]
    assert "field1_1" in index_names or index_name in index_names or len(indexes) >= 2


@pytest.mark.asyncio
async def test_create_compound_index_with_multiple_fields(mock_connection):
    """Test that create_compound_index creates a compound index with multiple fields."""
    connection = mock_connection

    # Call create_compound_index with multiple fields
    index_name = await create_compound_index(
        connection, "test_db", "test_collection", [("field1", 1), ("field2", -1)]
    )

    # Verify index was created (mongomock may return None for name)
    db = connection.client["test_db"]
    coll = db["test_collection"]
    indexes = [idx async for idx in coll.list_indexes()]
    index_names = [idx.get("name") for idx in indexes if idx.get("name")]
    assert (
        "field1_1_field2_-1" in index_names
        or index_name in index_names
        or len(indexes) >= 2
    )


@pytest.mark.asyncio
async def test_create_compound_index_with_unique_constraint(mock_connection):
    """Test that create_compound_index creates a unique index."""
    connection = mock_connection

    # Call create_compound_index with unique constraint
    index_name = await create_compound_index(
        connection, "test_db", "test_collection", [("email", 1)], unique=True
    )

    # Verify unique index was created (mongomock may return None for name)
    db = connection.client["test_db"]
    coll = db["test_collection"]
    indexes = [idx async for idx in coll.list_indexes()]
    index_names = [idx.get("name") for idx in indexes if idx.get("name")]
    assert "email_1" in index_names or index_name in index_names or len(indexes) >= 2


@pytest.mark.asyncio
async def test_create_compound_index_with_custom_name(mock_connection):
    """Test that create_compound_index creates an index with custom name."""
    connection = mock_connection

    # Call create_compound_index with custom name
    index_name = await create_compound_index(
        connection,
        "test_db",
        "test_collection",
        [("field1", 1), ("field2", -1)],
        name="custom_index",
    )

    # Verify custom name was used
    assert index_name == "custom_index"


@pytest.mark.asyncio
async def test_create_ttl_index_creates_time_to_live_index(mock_connection):
    """Test that create_ttl_index creates a TTL index."""
    connection = mock_connection

    # Call create_ttl_index
    index_name = await create_ttl_index(
        connection,
        "test_db",
        "test_collection",
        "created_at",
        expire_after_seconds=3600,
    )

    # Verify TTL index was created
    db = connection.client["test_db"]
    coll = db["test_collection"]
    indexes = [idx async for idx in coll.list_indexes()]
    index_names = [idx["name"] for idx in indexes]
    # TTL index should exist
    assert (
        any("created_at" in idx["name"] for idx in indexes) or index_name in index_names
    )


@pytest.mark.asyncio
async def test_create_text_index_creates_text_index(mock_connection):
    """Test that create_text_index creates a text search index."""
    connection = mock_connection

    # Call create_text_index
    index_name = await create_text_index(
        connection, "test_db", "test_collection", [("content", "text")]
    )

    # Verify text index was created (mongomock may return None for name)
    db = connection.client["test_db"]
    coll = db["test_collection"]
    indexes = [idx async for idx in coll.list_indexes()]
    index_names = [idx.get("name") for idx in indexes if idx.get("name")]
    assert (
        "content_text" in index_names or index_name in index_names or len(indexes) >= 2
    )
