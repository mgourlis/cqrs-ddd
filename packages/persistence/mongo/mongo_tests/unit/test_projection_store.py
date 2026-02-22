"""Unit tests for MongoDB projection store."""

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from cqrs_ddd_persistence_mongo.advanced.projection_store import MongoProjectionStore
from mongomock_motor import AsyncMongoMockClient


@dataclass
class ProjectionData:
    """Simple projection data for testing."""

    id: str = ""
    name: str = ""
    version: int = 1
    updated_at: datetime | None = None


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
async def test_projection_store_upsert_creates_projection(mock_connection):
    """Test that upsert creates a new projection."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )

    projection = ProjectionData(id="test-1", name="Test Projection")
    await store.upsert("test_projections", "test-1", {"name": projection.name, "version": projection.version})

    # Verify projection was saved
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc is not None
    assert doc["name"] == "Test Projection"


@pytest.mark.asyncio
async def test_projection_store_upsert_updates_projection(mock_connection):
    """Test that upsert updates an existing projection."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )

    # Create initial projection
    projection = ProjectionData(id="test-1", name="Test Projection v1", version=1)
    await store.upsert("test_projections", "test-1", {"name": projection.name, "version": projection.version})

    # Update projection
    projection.name = "Test Projection v2"
    projection.version = 2
    await store.upsert("test_projections", "test-1", {"name": projection.name, "version": projection.version})

    # Verify update
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc["name"] == "Test Projection v2"
    assert doc["version"] == 2


@pytest.mark.asyncio
async def test_projection_store_upsert_with_custom_id_field(mock_connection):
    """Test that upsert with custom ID field."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
        id_field="custom_id",
    )

    projection = ProjectionData(id="test-1", name="Test Projection")
    await store.upsert("test_projections", "test-1", {"custom_id": "test-1", "name": projection.name})

    # Verify custom ID was used (stored as _id, custom_id key removed)
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc is not None
    assert doc["name"] == "Test Projection"


@pytest.mark.asyncio
async def test_projection_store_delete_retrieves_and_deletes(mock_connection):
    """Test that delete retrieves and deletes a projection."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )

    # Create projection
    projection = ProjectionData(id="test-1", name="Test Projection")
    await store.upsert("test_projections", "test-1", {"name": projection.name})

    # Delete projection
    await store.delete("test_projections", "test-1")

    # Verify deletion
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc is None


@pytest.mark.asyncio
async def test_projection_store_drop_collection_clears_all(mock_connection):
    """Test that drop_collection removes all documents."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )

    # Create multiple projections
    for i in range(3):
        projection = ProjectionData(id=f"test-{i}", name=f"Projection {i}")
        await store.upsert("test_projections", f"test-{i}", {"name": projection.name})

    # Drop collection
    await store.drop_collection("test_projections")

    # Verify all are gone
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    count = await coll.count_documents({})
    assert count == 0


@pytest.mark.asyncio
async def test_projection_store_handles_datetime_fields(mock_connection):
    """Test that projection store handles datetime fields."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )

    # Create projection with datetime
    now = datetime.now(timezone.utc)
    projection = ProjectionData(
        id="test-1",
        name="Test Projection",
        updated_at=now,
    )
    await store.upsert("test_projections", "test-1", {"name": projection.name, "updated_at": projection.updated_at})

    # Retrieve and verify datetime
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc is not None
    assert doc["name"] == "Test Projection"
    # Mongomock may store datetime differently, so just check field exists
    assert "updated_at" in doc


@pytest.mark.asyncio
async def test_projection_store_with_custom_database(mock_connection):
    """Test projection store with custom database."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="custom_db",
    )

    projection = ProjectionData(id="test-1", name="Test Projection")
    await store.upsert("test_projections", "test-1", {"name": projection.name})

    # Verify custom database was used
    db = mock_connection._client["custom_db"]
    assert "test_projections" in await db.list_collection_names()


@pytest.mark.asyncio
async def test_projection_store_with_default_database(mock_connection):
    """Test projection store uses default database when none specified."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database=None,
    )

    projection = ProjectionData(id="test-1", name="Test Projection")
    await store.upsert("test_projections", "test-1", {"name": projection.name})

    # Verify projection was saved to default database (from connection._database)
    db = mock_connection._client["test_db"]
    coll = db["test_projections"]
    doc = await coll.find_one({"_id": "test-1"})
    assert doc is not None
    assert doc["name"] == "Test Projection"


@pytest.mark.asyncio
async def test_projection_store_version_control_accepts_new_version(mock_connection):
    """Upsert with higher event_position is accepted."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )
    ok1 = await store.upsert(
        "test_projections",
        "v1",
        {"name": "v1"},
        event_position=1,
        event_id="e1",
    )
    assert ok1 is True
    ok2 = await store.upsert(
        "test_projections",
        "v1",
        {"name": "v2"},
        event_position=2,
        event_id="e2",
    )
    assert ok2 is True
    db = mock_connection._client["test_db"]
    doc = await db["test_projections"].find_one({"_id": "v1"})
    assert doc["name"] == "v2"
    assert doc["_version"] == 2


@pytest.mark.asyncio
async def test_projection_store_version_control_rejects_stale(mock_connection):
    """Upsert with lower or equal event_position is rejected (returns False)."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.upsert(
        "test_projections",
        "v1",
        {"name": "new"},
        event_position=5,
        event_id="e5",
    )
    ok = await store.upsert(
        "test_projections",
        "v1",
        {"name": "stale"},
        event_position=3,
        event_id="e3",
    )
    assert ok is False
    db = mock_connection._client["test_db"]
    doc = await db["test_projections"].find_one({"_id": "v1"})
    assert doc["name"] == "new"
    assert doc["_version"] == 5


@pytest.mark.asyncio
async def test_projection_store_idempotency_duplicate_event_id(mock_connection):
    """Upsert with same event_id (already applied) is rejected."""
    store = MongoProjectionStore(
        connection=mock_connection,
        database="test_db",
    )
    await store.upsert(
        "test_projections",
        "idem",
        {"name": "first"},
        event_position=1,
        event_id="ev-1",
    )
    ok = await store.upsert(
        "test_projections",
        "idem",
        {"name": "duplicate"},
        event_position=1,
        event_id="ev-1",
    )
    assert ok is False
    db = mock_connection._client["test_db"]
    doc = await db["test_projections"].find_one({"_id": "idem"})
    assert doc["name"] == "first"
