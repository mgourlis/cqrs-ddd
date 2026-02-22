"""Unit tests for MongoRepository[T] generic repository."""

from __future__ import annotations

from uuid import uuid4

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from cqrs_ddd_persistence_mongo.core.repository import MongoRepository
from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork


# Sample model (name avoids pytest collecting it as a test class)
class SampleReadModel(BaseModel):
    """Simple read model for repository tests."""

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
    connection._database = "test_db"
    connection._url = "mongodb://mock:27017"

    async def _mock_connect():
        return connection._client

    connection.connect = _mock_connect
    return connection


@pytest.fixture
def repository(mock_connection):
    """Create a MongoRepository instance for testing."""
    return MongoRepository(
        connection=mock_connection,
        collection="test_collection",
        model_cls=SampleReadModel,
        id_field="id",
    )


@pytest.fixture
def test_entity():
    """Create a test entity."""
    return SampleReadModel(id=str(uuid4()), name="Test Entity", value=42)


# Phase 1, Step 1: MongoRepository Unit Tests (15 tests)


class TestMongoRepositoryAdd:
    """Tests for add() method."""

    @pytest.mark.asyncio
    async def test_add_inserts_new_entity(self, repository, test_entity):
        """Test that add inserts a new entity with auto-generated ID."""
        # Create entity without ID to test auto-generation
        entity_without_id = SampleReadModel(name="New Entity", value=10)

        result_id = await repository.add(entity_without_id)

        assert result_id is not None
        assert len(result_id) > 0

        # Verify entity was inserted
        retrieved = await repository.get(result_id)
        assert retrieved is not None
        assert retrieved.name == "New Entity"
        assert retrieved.value == 10

    @pytest.mark.asyncio
    async def test_add_with_existing_id_upserts(self, repository, test_entity):
        """Test that add with existing ID performs upsert (update)."""
        # Add initial entity
        entity_id = await repository.add(test_entity)
        initial = await repository.get(entity_id)
        assert initial.value == 42

        # Update with same ID
        updated_entity = SampleReadModel(id=entity_id, name="Updated Name", value=99)
        result_id = await repository.add(updated_entity)

        assert result_id == entity_id
        retrieved = await repository.get(entity_id)
        assert retrieved.name == "Updated Name"
        assert retrieved.value == 99

    @pytest.mark.asyncio
    async def test_add_with_uow_uses_session(self, mock_connection, test_entity):
        """Test that add respects UnitOfWork session."""
        from mongo_tests.conftest import MockSession

        repository = MongoRepository(
            connection=mock_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
        )

        # Create UoW with mock session
        session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session

        # Verify session is in transaction
        session._in_transaction = True

        result_id = await repository.add(test_entity, uow=uow)

        assert result_id is not None
        assert session._in_transaction  # Session should still be in transaction


class TestMongoRepositoryGet:
    """Tests for get() method."""

    @pytest.mark.asyncio
    async def test_get_retrieves_existing_entity(self, repository, test_entity):
        """Test that get retrieves an existing entity by ID."""
        entity_id = await repository.add(test_entity)

        retrieved = await repository.get(entity_id)

        assert retrieved is not None
        assert retrieved.id == entity_id
        assert retrieved.name == test_entity.name
        assert retrieved.value == test_entity.value

    @pytest.mark.asyncio
    async def test_get_returns_none_for_nonexistent(self, repository):
        """Test that get returns None for non-existent entity."""
        nonexistent_id = str(ObjectId())

        result = await repository.get(nonexistent_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_uow_uses_session(self, mock_connection, test_entity):
        """Test that get respects UnitOfWork session."""
        from mongo_tests.conftest import MockSession

        repository = MongoRepository(
            connection=mock_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
        )

        # Add entity first
        entity_id = await repository.add(test_entity)

        # Create UoW with mock session
        session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session

        retrieved = await repository.get(entity_id, uow=uow)

        assert retrieved is not None
        assert retrieved.id == entity_id


class TestMongoRepositoryDelete:
    """Tests for delete() method."""

    @pytest.mark.asyncio
    async def test_delete_removes_entity(self, repository, test_entity):
        """Test that delete removes an entity by ID."""
        entity_id = await repository.add(test_entity)

        # Verify entity exists
        assert await repository.get(entity_id) is not None

        # Delete entity
        deleted_id = await repository.delete(entity_id)

        assert deleted_id == entity_id
        assert await repository.get(entity_id) is None

    @pytest.mark.asyncio
    async def test_delete_is_idempotent(self, repository):
        """Test that delete on non-existent entity doesn't raise."""
        nonexistent_id = str(ObjectId())

        # Should not raise
        result_id = await repository.delete(nonexistent_id)

        assert result_id == nonexistent_id

    @pytest.mark.asyncio
    async def test_delete_with_uow_uses_session(self, mock_connection, test_entity):
        """Test that delete respects UnitOfWork session."""
        from mongo_tests.conftest import MockSession

        repository = MongoRepository(
            connection=mock_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
        )

        entity_id = await repository.add(test_entity)

        # Create UoW with mock session
        session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session

        session._in_transaction = True

        deleted_id = await repository.delete(entity_id, uow=uow)

        assert deleted_id == entity_id
        assert session._in_transaction


class TestMongoRepositoryListAll:
    """Tests for list_all() method."""

    @pytest.mark.asyncio
    async def test_list_all_returns_all_entities(self, repository):
        """Test that list_all returns all entities in collection."""
        entities = [
            SampleReadModel(id=str(uuid4()), name=f"Entity {i}", value=i)
            for i in range(3)
        ]

        for entity in entities:
            await repository.add(entity)

        results = await repository.list_all()

        assert len(results) == 3
        assert all(isinstance(r, SampleReadModel) for r in results)

    @pytest.mark.asyncio
    async def test_list_all_with_ids_filters(self, repository):
        """Test that list_all with entity_ids filters correctly."""
        entities = [
            SampleReadModel(id=str(uuid4()), name=f"Entity {i}", value=i)
            for i in range(5)
        ]

        entity_ids = []
        for entity in entities:
            entity_id = await repository.add(entity)
            entity_ids.append(entity_id)

        # Get only first 3
        results = await repository.list_all(entity_ids=entity_ids[:3])

        assert len(results) == 3
        result_ids = {r.id for r in results}
        assert result_ids == set(entity_ids[:3])

    @pytest.mark.asyncio
    async def test_list_all_with_uow_uses_session(self, mock_connection):
        """Test that list_all respects UnitOfWork session."""
        from mongo_tests.conftest import MockSession

        repository = MongoRepository(
            connection=mock_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
        )

        entity = SampleReadModel(name="Test", value=1)
        await repository.add(entity)

        # Create UoW with mock session
        session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session

        results = await repository.list_all(uow=uow)

        assert len(results) == 1
        assert results[0].name == "Test"


class TestMongoRepositorySerialization:
    """Tests for model serialization/deserialization."""

    @pytest.mark.asyncio
    async def test_model_serialization(self, repository):
        """Test that model_to_doc and model_from_doc work correctly."""
        entity = SampleReadModel(id=str(uuid4()), name="Test", value=42)

        entity_id = await repository.add(entity)
        retrieved = await repository.get(entity_id)

        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.name == entity.name
        assert retrieved.value == entity.value
        assert type(retrieved) == SampleReadModel


class TestMongoRepositoryConfiguration:
    """Tests for repository configuration."""

    @pytest.mark.asyncio
    async def test_custom_database_name(self, mock_connection):
        """Test that custom database name is respected."""
        repository = MongoRepository(
            connection=mock_connection,
            collection="test_collection",
            model_cls=SampleReadModel,
            database="custom_db",
        )

        entity = SampleReadModel(name="Test", value=1)
        entity_id = await repository.add(entity)

        retrieved = await repository.get(entity_id)
        assert retrieved is not None

        # Verify database was used
        db = repository._db()
        assert db.name == "custom_db"

    @pytest.mark.asyncio
    async def test_collection_name_from_generic(self, mock_connection):
        """Test that collection name is correctly set from constructor."""
        repository = MongoRepository(
            connection=mock_connection,
            collection="my_custom_collection",
            model_cls=SampleReadModel,
        )

        assert repository._collection_name == "my_custom_collection"

        entity = SampleReadModel(name="Test", value=1)
        await repository.add(entity)

        results = await repository.list_all()
        assert len(results) == 1
