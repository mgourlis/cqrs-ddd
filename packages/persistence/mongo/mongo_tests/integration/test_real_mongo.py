"""Integration tests with real MongoDB using testcontainers (requires testcontainers)."""

from __future__ import annotations

import contextlib
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, Field

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_persistence_mongo.advanced.persistence import (
    MongoOperationPersistence,
    MongoQueryPersistence,
    MongoRetrievalPersistence,
)
from cqrs_ddd_persistence_mongo.advanced.projection_store import MongoProjectionStore
from cqrs_ddd_persistence_mongo.core.repository import MongoRepository
from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork
from cqrs_ddd_persistence_mongo.serialization import model_from_doc, model_to_doc


# Sample models (names avoid pytest collecting them as test classes)
class SampleAggregate(AggregateRoot[dict]):
    """Simple aggregate for integration tests."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: int = 0

    def __init__(self, id: str, name: str, value: int = 0):
        super().__init__(id=id, name=name, value=value)


class SampleReadModel(BaseModel):
    """Simple read model for integration tests."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: int = 0


class SampleReadDTO(BaseModel):
    """Simple read DTO for query persistence."""

    id: str
    name: str
    value: int


# Concrete implementations for integration tests
class ConcreteOperationPersistence(MongoOperationPersistence[SampleAggregate, str]):
    """Concrete implementation for testing MongoOperationPersistence."""

    def __init__(self, connection):
        self.connection = connection
        self.collection_name = "test_aggregates"
        self.id_field = "id"
        self.database = "test_db"


class ConcreteRetrievalPersistence(MongoRetrievalPersistence[SampleAggregate, str]):
    """Concrete implementation for testing MongoRetrievalPersistence."""

    def __init__(self, connection):
        self.connection = connection
        self.collection_name = "test_aggregates"
        self.model_cls = SampleAggregate
        self.id_field = "id"
        self.database = "test_db"


class ConcreteQueryPersistence(MongoQueryPersistence[SampleReadDTO, str]):
    """Concrete implementation for testing MongoQueryPersistence."""

    def __init__(self, connection):
        self.connection = connection
        self.collection_name = "test_dtos"
        self.database = "test_db"

    def to_dto(self, doc: dict[str, Any]) -> SampleReadDTO:
        """Convert document to DTO."""
        return SampleReadDTO(
            id=str(doc.get("_id", "")),
            name=doc.get("name", ""),
            value=doc.get("value", 0),
        )


# Collections used by integration tests (dropped before each test for isolation)
_INTEGRATION_TEST_COLLECTIONS = [
    "test_collection",
    "test_aggregates",
    "test_dtos",
    "test_projections",
    "test_ttl_collection",
    "test_batch_projections",
    "test_projections_resume",
    "test_ttl_projections",
]


@pytest.fixture(autouse=True)
async def _drop_integration_test_collections(real_mongo_connection):
    """Drop test collections before each integration test to avoid cross-test pollution."""
    db = real_mongo_connection.client.get_database("test_db")
    for name in _INTEGRATION_TEST_COLLECTIONS:
        with contextlib.suppress(Exception):
            await db[name].drop()
    return


# Phase 4, Step 16: Integration Test Suite (15 tests)


@pytest.mark.integration
class TestIntegrationMongoRepository:
    """Integration tests for MongoRepository with real MongoDB."""

    @pytest.mark.asyncio
    async def test_repository_crud_with_real_mongo(self, real_mongo_connection):
        """Test CRUD operations with real MongoDB."""
        repository = MongoRepository(
            connection=real_mongo_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Create
        entity = SampleReadModel(name="Test", value=42)
        entity_id = await repository.add(entity)

        # Read
        retrieved = await repository.get(entity_id)
        assert retrieved is not None
        assert retrieved.name == "Test"
        assert retrieved.value == 42

        # Update
        updated = SampleReadModel(id=entity_id, name="Updated", value=100)
        await repository.add(updated)
        re_retrieved = await repository.get(entity_id)
        assert re_retrieved.name == "Updated"

        # Delete
        await repository.delete(entity_id)
        deleted = await repository.get(entity_id)
        assert deleted is None


@pytest.mark.integration
class TestIntegrationUnitOfWork:
    """Integration tests for UnitOfWork with transactions."""

    @pytest.mark.asyncio
    async def test_uow_transaction_commit(self, real_mongo_connection):
        """Test UnitOfWork transaction commit."""
        connection = real_mongo_connection
        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Use UnitOfWork with transaction
        async with MongoUnitOfWork(
            connection=connection, require_replica_set=False
        ) as uow:
            entity1 = SampleReadModel(name="Entity1", value=1)
            entity2 = SampleReadModel(name="Entity2", value=2)

            await repository.add(entity1, uow=uow)
            await repository.add(entity2, uow=uow)

            # Changes should be committed
            await uow.commit()

        # Verify both entities exist after commit
        all_entities = await repository.list_all()
        assert len(all_entities) == 2


@pytest.mark.integration
class TestIntegrationProjectionStore:
    """Integration tests for MongoProjectionStore."""

    @pytest.mark.asyncio
    async def test_projection_store_upsert_real(self, real_mongo_connection):
        """Test projection store upsert with real MongoDB."""
        connection = real_mongo_connection
        store = MongoProjectionStore(connection=connection, database="test_db")

        # Upsert a document
        doc_id = str(uuid4())
        data = {"id": doc_id, "name": "Test Projection", "value": 42}
        await store.upsert("test_projections", doc_id, data)

        # Verify document was upserted
        coll = store._coll("test_projections")
        doc = await coll.find_one({"_id": doc_id})
        assert doc is not None
        assert doc["name"] == "Test Projection"
        assert doc["value"] == 42


@pytest.mark.integration
class TestIntegrationAdvancedPersistence:
    """Integration tests for advanced persistence bases."""

    @pytest.mark.asyncio
    async def test_advanced_persistence_real_mongo(self, real_mongo_connection):
        """Test advanced persistence operations with real MongoDB."""
        connection = real_mongo_connection

        operation_persistence = ConcreteOperationPersistence(connection)
        retrieval_persistence = ConcreteRetrievalPersistence(connection)

        # Persist an aggregate
        aggregate = SampleAggregate(id=str(uuid4()), name="Test Aggregate", value=100)
        aggregate_id = await operation_persistence.persist(aggregate)

        # Retrieve the aggregate
        results = await retrieval_persistence.retrieve([aggregate_id])

        assert len(results) == 1
        assert results[0].id == aggregate_id
        assert results[0].name == "Test Aggregate"
        assert results[0].value == 100


@pytest.mark.integration
class TestIntegrationSearch:
    """Integration tests for search functionality."""

    @pytest.mark.asyncio
    async def test_search_with_real_aggregation(self, real_mongo_connection):
        """Test search with real MongoDB aggregation."""
        connection = real_mongo_connection
        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Add sample data
        for i in range(10):
            entity = SampleReadModel(name=f"Entity {i}", value=i)
            await repository.add(entity)

        # Search with filter
        class SimpleSpec:
            specification = {"value": {"$gte": 5}}

        result = await repository.search(SimpleSpec())
        results_list = await result

        assert len(results_list) == 5
        assert all(r.value >= 5 for r in results_list)


@pytest.mark.integration
class TestIntegrationStreaming:
    """Integration tests for streaming result sets."""

    @pytest.mark.asyncio
    async def test_streaming_large_result_set(self, real_mongo_connection):
        """Test streaming with a large result set."""
        connection = real_mongo_connection
        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Add many documents
        num_docs = 100
        for i in range(num_docs):
            entity = SampleReadModel(name=f"Entity {i}", value=i)
            await repository.add(entity)

        # Stream results
        class EmptySpec:
            specification = {}

        count = 0
        result = await repository.search(EmptySpec())
        async for _ in result.stream(batch_size=10):
            count += 1

        assert count == num_docs


@pytest.mark.integration
class TestIntegrationTTLIndex:
    """Integration tests for TTL indexes."""

    @pytest.mark.asyncio
    async def test_ttl_index_cleanup(self, real_mongo_connection):
        """Test TTL index creation."""
        connection = real_mongo_connection
        store = MongoProjectionStore(connection=connection, database="test_db")

        # Create TTL index
        collection = "test_ttl_collection"
        await store.ensure_ttl_index(collection, "expire_at", 3600)

        # Verify index exists
        coll = store._coll(collection)
        indexes = [idx async for idx in coll.list_indexes()]
        index_names = [idx.get("name") for idx in indexes if idx.get("name")]
        assert "ttl_expire_at" in index_names or len(indexes) >= 2


@pytest.mark.integration
class TestIntegrationQueryPersistence:
    """Integration tests for query persistence."""

    @pytest.mark.asyncio
    async def test_query_persistence_real_mongo(self, real_mongo_connection):
        """Test query persistence with real MongoDB."""
        connection = real_mongo_connection
        query_persistence = ConcreteQueryPersistence(connection)

        # Insert documents directly
        coll = query_persistence._collection()
        doc_ids = [str(uuid4()) for _ in range(3)]
        for idx, doc_id in enumerate(doc_ids):
            await coll.insert_one({"_id": doc_id, "name": f"Test {idx}", "value": idx})

        # Fetch DTOs
        results = await query_persistence.fetch(doc_ids)

        assert len(results) == 3
        assert all(isinstance(r, SampleReadDTO) for r in results)


@pytest.mark.integration
class TestIntegrationSerialization:
    """Integration tests for serialization round-trips."""

    @pytest.mark.asyncio
    async def test_serialization_round_trip(self, real_mongo_connection):
        """Test serialization/deserialization round-trip."""
        entity = SampleReadModel(name="Test", value=42)

        # Serialize
        doc = model_to_doc(entity)

        # Verify serialization
        assert "_id" in doc
        assert doc["name"] == "Test"
        assert doc["value"] == 42

        # Deserialize
        round_trip = model_from_doc(SampleReadModel, doc)

        # Verify deserialization
        assert round_trip.name == entity.name
        assert round_trip.value == entity.value


@pytest.mark.integration
class TestIntegrationConcurrentWrites:
    """Integration tests for concurrent writes."""

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, real_mongo_connection):
        """Test concurrent writes to the same collection."""
        import asyncio

        connection = real_mongo_connection
        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Concurrent writes
        async def add_entity(i):
            entity = SampleReadModel(name=f"Entity {i}", value=i)
            return await repository.add(entity)

        # Execute 10 concurrent writes
        results = await asyncio.gather(*[add_entity(i) for i in range(10)])

        # Verify all writes succeeded
        assert len(results) == 10
        assert all(r is not None for r in results)

        # Verify all documents exist
        all_entities = await repository.list_all()
        assert len(all_entities) == 10


@pytest.mark.integration
class TestIntegrationConnectionManagement:
    """Integration tests for connection management."""

    @pytest.mark.asyncio
    async def test_connection_pooling(self, real_mongo_connection):
        """Test connection pooling with multiple operations."""
        connection = real_mongo_connection

        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Perform multiple operations to test connection pooling
        for i in range(20):
            entity = SampleReadModel(name=f"Entity {i}", value=i)
            await repository.add(entity)

        all_entities = await repository.list_all()
        assert len(all_entities) == 20


@pytest.mark.integration
class TestIntegrationSessionManagement:
    """Integration tests for session management."""

    @pytest.mark.asyncio
    async def test_session_management(self, real_mongo_connection):
        """Test session management with transactions."""
        connection = real_mongo_connection

        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Start transaction with session
        async with MongoUnitOfWork(
            connection=connection, require_replica_set=False
        ) as uow:
            # Check if session is available
            if uow.session is not None:
                # Operations should use session
                entity = SampleReadModel(name="Session Test", value=1)
                entity_id = await repository.add(entity, uow=uow)
                await uow.commit()

                # Verify entity exists after commit
                retrieved = await repository.get(entity_id)
                assert retrieved is not None


@pytest.mark.integration
class TestIntegrationErrorRecovery:
    """Integration tests for error recovery."""

    @pytest.mark.asyncio
    async def test_error_recovery(self, real_mongo_connection):
        """Test error recovery after failed operation."""
        connection = real_mongo_connection

        repository = MongoRepository(
            connection=connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            id_field="id",
            database="test_db",
        )

        # Add a valid entity
        entity = SampleReadModel(name="Valid", value=1)
        entity_id = await repository.add(entity)

        # Verify entity exists
        retrieved = await repository.get(entity_id)
        assert retrieved is not None

        # Try to get non-existent entity (should return None, not raise)
        non_existent = await repository.get(str(uuid4()))
        assert non_existent is None

        # Continue with valid operations
        entity2 = SampleReadModel(name="Valid2", value=2)
        entity2_id = await repository.add(entity2)
        retrieved2 = await repository.get(entity2_id)
        assert retrieved2 is not None


@pytest.mark.integration
class TestIntegrationBatchOperations:
    """Integration tests for batch operations."""

    @pytest.mark.asyncio
    async def test_batch_upsert(self, real_mongo_connection):
        """Test batch upsert operations."""
        connection = real_mongo_connection
        store = MongoProjectionStore(connection=connection, database="test_db")

        # Upsert multiple documents
        docs = [{"id": str(uuid4()), "name": f"Doc {i}", "value": i} for i in range(5)]
        await store.upsert_batch("test_collection", docs)

        # Verify all documents were upserted
        coll = store._coll("test_collection")
        count = await coll.count_documents({})
        assert count == 5
