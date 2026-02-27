"""Unit tests for MongoProjectionStore."""

from __future__ import annotations

from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from cqrs_ddd_persistence_mongo.advanced.projection_store import MongoProjectionStore
from cqrs_ddd_persistence_mongo.exceptions import MongoPersistenceError


# Sample model (name avoids pytest collecting it as a test class)
class SampleProjectionModel(BaseModel):
    """Simple projection model for testing."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: int = 0


# Fixtures
@pytest.fixture
def mock_client():
    """Create a mock MongoDB client."""
    return AsyncMongoMockClient()


@pytest.fixture
def mock_connection(mock_client):
    """Create a mock MongoDB connection."""
    from cqrs_ddd_persistence_mongo import MongoConnectionManager

    connection = MongoConnectionManager.__new__(MongoConnectionManager)
    connection._client = mock_client
    connection._url = "mongodb://mock:27017"

    async def _mock_connect():
        return connection._client

    connection.connect = _mock_connect
    return connection


@pytest.fixture
def projection_store(mock_connection):
    """Create a MongoProjectionStore instance for testing."""
    return MongoProjectionStore(connection=mock_connection, database="test_db")


# Phase 1, Step 3: Expand MongoProjectionStore Tests (10 tests)


class TestMongoProjectionStoreUpsert:
    """Tests for upsert() method."""

    @pytest.mark.asyncio
    async def test_upsert_single_document(self, projection_store):
        """Test upserting a single document as dict."""
        doc_id = str(uuid4())
        data = {"id": doc_id, "name": "Test", "value": 42}

        await projection_store.upsert("test_collection", doc_id, data)

        # Verify document was upserted
        coll = projection_store._coll("test_collection")
        doc = await coll.find_one({"_id": doc_id})
        assert doc is not None
        assert doc["name"] == "Test"
        assert doc["value"] == 42

    @pytest.mark.asyncio
    async def test_upsert_pydantic_model(self, projection_store):
        """Test upserting a Pydantic model."""
        model = SampleProjectionModel(name="Model Test", value=100)
        doc_id = model.id

        await projection_store.upsert("test_collection", doc_id, model)

        # Verify document was upserted
        coll = projection_store._coll("test_collection")
        doc = await coll.find_one({"_id": doc_id})
        assert doc is not None
        assert doc["name"] == "Model Test"
        assert doc["value"] == 100

    @pytest.mark.asyncio
    async def test_upsert_with_custom_id_field(self, mock_connection):
        """Test upsert with custom ID field (store built with id_field='custom_id')."""
        store = MongoProjectionStore(
            connection=mock_connection,
            database="test_db",
            id_field="custom_id",
        )
        doc_id = str(uuid4())
        data = {"custom_id": doc_id, "name": "Test", "value": 1}

        await store.upsert("test_collection", doc_id, data)

        # Verify document was upserted; custom_id moved to _id so not in doc
        coll = store._coll("test_collection")
        doc = await coll.find_one({"_id": doc_id})
        assert doc is not None
        assert "custom_id" not in doc
        assert doc.get("name") == "Test"


class TestMongoProjectionStoreUpsertBatch:
    """Tests for upsert_batch() method."""

    @pytest.mark.asyncio
    async def test_upsert_batch_multiple_documents(self, projection_store):
        """Test upserting multiple documents."""
        docs = [{"id": str(uuid4()), "name": f"Test {i}", "value": i} for i in range(3)]

        await projection_store.upsert_batch("test_collection", docs)

        # Verify all documents were upserted
        coll = projection_store._coll("test_collection")
        count = await coll.count_documents({})
        assert count == 3

    @pytest.mark.asyncio
    async def test_upsert_batch_with_mixed_types(self, projection_store):
        """Test upserting batch with mixed dict and Pydantic types."""
        dict_doc = {"id": str(uuid4()), "name": "Dict Doc", "value": 1}
        model_doc = SampleProjectionModel(name="Model Doc", value=2)

        await projection_store.upsert_batch("test_collection", [dict_doc, model_doc])

        # Verify both were upserted
        coll = projection_store._coll("test_collection")
        count = await coll.count_documents({})
        assert count == 2

    @pytest.mark.asyncio
    async def test_upsert_batch_raises_on_missing_id(self, projection_store):
        """Test that upsert_batch raises on missing ID."""
        docs = [{"name": "No ID"}]  # Missing id field

        with pytest.raises(MongoPersistenceError, match="must have an id"):
            await projection_store.upsert_batch("test_collection", docs)


class TestMongoProjectionStoreDropCollection:
    """Tests for drop_collection() method."""

    @pytest.mark.asyncio
    async def test_drop_collection(self, projection_store):
        """Test dropping a collection."""
        # Add some documents
        docs = [{"id": str(uuid4()), "name": "Test", "value": i} for i in range(3)]
        await projection_store.upsert_batch("test_collection", docs)

        # Verify documents exist
        coll = projection_store._coll("test_collection")
        count_before = await coll.count_documents({})
        assert count_before == 3

        # Drop collection
        await projection_store.drop_collection("test_collection")

        # Verify collection is empty
        count_after = await coll.count_documents({})
        assert count_after == 0


class TestMongoProjectionStoreTTLIndex:
    """Tests for ensure_ttl_index() method."""

    @pytest.mark.asyncio
    async def test_ensure_ttl_index_creates_index(self, projection_store):
        """Test that ensure_ttl_index creates a TTL index."""
        collection = "test_collection"

        await projection_store.ensure_ttl_index(collection, "expire_at", 3600)

        # Verify index was created
        coll = projection_store._coll(collection)
        indexes = [idx async for idx in coll.list_indexes()]
        index_names = [idx.get("name") for idx in indexes if idx.get("name")]
        assert "ttl_expire_at" in index_names or len(indexes) >= 2

    @pytest.mark.asyncio
    async def test_ensure_ttl_index_idempotent(self, projection_store):
        """Test that ensure_ttl_index is idempotent (can call multiple times)."""
        collection = "test_collection"

        # Create index twice
        await projection_store.ensure_ttl_index(collection, "expire_at", 3600)
        await projection_store.ensure_ttl_index(collection, "expire_at", 3600)

        # Verify only one index exists
        coll = projection_store._coll(collection)
        indexes = [idx async for idx in coll.list_indexes()]
        ttl_indexes = [idx for idx in indexes if idx.get("name", "").startswith("ttl_")]
        assert len(ttl_indexes) == 1


class TestMongoProjectionStoreConfiguration:
    """Tests for store configuration."""

    @pytest.mark.asyncio
    async def test_custom_database(self, projection_store):
        """Test that custom database name is respected."""
        doc_id = str(uuid4())
        data = {"id": doc_id, "name": "Test", "value": 1}

        await projection_store.upsert("test_collection", doc_id, data)

        # Verify database was used
        db = projection_store._db()
        assert db.name == "test_db"

    @pytest.mark.asyncio
    async def test_upsert_batch_requires_id(self, projection_store):
        """Documents in upsert_batch must have an id field."""
        with pytest.raises(MongoPersistenceError, match="must have an id"):
            await projection_store.upsert_batch("coll", [{"name": "no-id"}])
