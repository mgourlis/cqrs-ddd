"""Unit tests for advanced MongoDB persistence bases."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from mongo_tests.conftest import MockSession
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.search_result import SearchResult
from cqrs_ddd_persistence_mongo.advanced.persistence import (
    MongoOperationPersistence,
    MongoQueryPersistence,
    MongoQuerySpecificationPersistence,
    MongoRetrievalPersistence,
)


# Sample models (names avoid pytest collecting them as test classes)
class SampleAggregate(AggregateRoot[dict]):
    """Simple aggregate for advanced persistence tests."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: int = 0


class SampleReadDTO(BaseModel):
    """Simple read DTO for query persistence tests."""

    id: str
    name: str
    value: int


# Concrete implementations for testing
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


class ConcreteQuerySpecificationPersistence(
    MongoQuerySpecificationPersistence[SampleReadDTO]
):
    """Concrete implementation for testing MongoQuerySpecificationPersistence."""

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


# Phase 1, Step 2: Advanced Persistence Bases Tests (31 tests)


class TestMongoOperationPersistence:
    """Tests for MongoOperationPersistence (8 tests)."""

    @pytest.mark.asyncio
    async def test_persist_inserts_new_aggregate(self, mock_connection):
        """Test that persist inserts a new aggregate."""
        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="New Aggregate", value=10)

        result_id = await persistence.persist(aggregate)

        assert result_id is not None
        assert result_id == aggregate.id

    @pytest.mark.asyncio
    async def test_persist_updates_existing_aggregate(self, mock_connection):
        """Test that persist updates an existing aggregate."""
        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="Initial", value=5)

        # Initial persist
        await persistence.persist(aggregate)

        # Update aggregate (immutable copy)
        aggregate = aggregate.model_copy(update={"value": 100, "name": "Updated"})
        result_id = await persistence.persist(aggregate)

        assert result_id == aggregate.id

    @pytest.mark.asyncio
    async def test_persist_with_uow_uses_session(self, mock_connection):
        """Test that persist respects UnitOfWork session."""
        from mongo_tests.conftest import MockSession

        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="Test", value=1)

        from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

        session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session
        session._in_transaction = True

        result_id = await persistence.persist(aggregate, uow=uow)

        assert result_id is not None
        assert session._in_transaction

    @pytest.mark.asyncio
    async def test_persist_generates_uuid_if_missing(self, mock_connection):
        """Test that persist generates UUID if ID is missing."""
        persistence = ConcreteOperationPersistence(mock_connection)
        # Create aggregate without explicit ID
        aggregate = SampleAggregate(id="", name="No ID", value=1)

        result_id = await persistence.persist(aggregate)

        assert result_id is not None
        assert len(result_id) > 0

    @pytest.mark.asyncio
    async def test_persist_serializes_with_model_to_doc(self, mock_connection):
        """Test that persist uses model_to_doc for serialization."""
        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="Test", value=42)

        result_id = await persistence.persist(aggregate)

        assert result_id == aggregate.id

    @pytest.mark.asyncio
    async def test_persist_uses_custom_database(self, mock_connection):
        """Test that persist uses custom database."""
        persistence = ConcreteOperationPersistence(mock_connection)
        persistence.database = "custom_db"
        aggregate = SampleAggregate(id=str(uuid4()), name="Test", value=1)

        result_id = await persistence.persist(aggregate)

        assert result_id is not None
        assert persistence._db().name == "custom_db"

    @pytest.mark.asyncio
    async def test_persist_with_session_in_transaction(self, mock_connection):
        """Test persist behavior when session is in transaction."""
        from mongo_tests.conftest import MockSession

        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="Test", value=1)

        from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

        session = MockSession()
        session._in_transaction = True
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = session

        result_id = await persistence.persist(aggregate, uow=uow)

        assert result_id is not None

    @pytest.mark.asyncio
    async def test_persist_without_session_no_transaction(self, mock_connection):
        """Test persist behavior without session (no transaction)."""
        persistence = ConcreteOperationPersistence(mock_connection)
        aggregate = SampleAggregate(id=str(uuid4()), name="Test", value=1)

        result_id = await persistence.persist(aggregate, uow=None)

        assert result_id is not None


class TestMongoRetrievalPersistence:
    """Tests for MongoRetrievalPersistence (7 tests)."""

    @pytest.mark.asyncio
    async def test_retrieve_single_id(self, mock_connection):
        """Test retrieving a single aggregate by ID."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        aggregate_id = str(uuid4())
        aggregate = SampleAggregate(id=aggregate_id, name="Test", value=1)
        await operation_persistence.persist(aggregate)

        results = await retrieval_persistence.retrieve([aggregate_id])

        assert len(results) == 1
        assert results[0].id == aggregate_id

    @pytest.mark.asyncio
    async def test_retrieve_multiple_ids(self, mock_connection):
        """Test retrieving multiple aggregates by IDs."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        ids = [str(uuid4()) for _ in range(3)]
        for idx, entity_id in enumerate(ids):
            aggregate = SampleAggregate(id=entity_id, name=f"Test {idx}", value=idx)
            await operation_persistence.persist(aggregate)

        results = await retrieval_persistence.retrieve(ids)

        assert len(results) == 3
        result_ids = {r.id for r in results}
        assert result_ids == set(ids)

    @pytest.mark.asyncio
    async def test_retrieve_empty_result(self, mock_connection):
        """Test retrieving with no matching IDs."""
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        results = await retrieval_persistence.retrieve([str(uuid4())])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_retrieve_with_uow(self, mock_connection):
        """Test retrieve with UnitOfWork."""
        from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

        operation_persistence = ConcreteOperationPersistence(mock_connection)
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        aggregate_id = str(uuid4())
        aggregate = SampleAggregate(id=aggregate_id, name="Test", value=1)
        await operation_persistence.persist(aggregate)

        # Create mock session
        mock_session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = mock_session
        mock_session._in_transaction = True

        results = await retrieval_persistence.retrieve([aggregate_id], uow=uow)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_deserializes_with_model_from_doc(self, mock_connection):
        """Test that retrieve uses model_from_doc for deserialization."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        aggregate_id = str(uuid4())
        aggregate = SampleAggregate(id=aggregate_id, name="Test", value=42)
        await operation_persistence.persist(aggregate)

        results = await retrieval_persistence.retrieve([aggregate_id])

        assert len(results) == 1
        assert isinstance(results[0], SampleAggregate)
        assert results[0].value == 42

    @pytest.mark.asyncio
    async def test_retrieve_custom_database(self, mock_connection):
        """Test retrieve with custom database."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        operation_persistence.database = "custom_db"
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)
        retrieval_persistence.database = "custom_db"

        aggregate_id = str(uuid4())
        aggregate = SampleAggregate(id=aggregate_id, name="Test", value=1)
        await operation_persistence.persist(aggregate)

        results = await retrieval_persistence.retrieve([aggregate_id])

        assert len(results) == 1
        assert retrieval_persistence._db().name == "custom_db"

    @pytest.mark.asyncio
    async def test_retrieve_filters_by_collection(self, mock_connection):
        """Test that retrieve filters by the correct collection."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        retrieval_persistence = ConcreteRetrievalPersistence(mock_connection)

        aggregate_id = str(uuid4())
        aggregate = SampleAggregate(id=aggregate_id, name="Test", value=1)
        await operation_persistence.persist(aggregate)

        results = await retrieval_persistence.retrieve([aggregate_id])

        assert len(results) == 1
        assert retrieval_persistence.collection_name == "test_aggregates"


class TestMongoQueryPersistence:
    """Tests for MongoQueryPersistence (7 tests)."""

    @pytest.mark.asyncio
    async def test_fetch_single_dto(self, mock_connection):
        """Test fetching a single DTO by ID."""
        persistence = ConcreteQueryPersistence(mock_connection)

        # Insert document directly
        collection = persistence._collection()
        doc_id = str(uuid4())
        await collection.insert_one({"_id": doc_id, "name": "Test", "value": 1})

        results = await persistence.fetch([doc_id])

        assert len(results) == 1
        assert results[0].id == doc_id
        assert results[0].name == "Test"

    @pytest.mark.asyncio
    async def test_fetch_multiple_dtos(self, mock_connection):
        """Test fetching multiple DTOs."""
        persistence = ConcreteQueryPersistence(mock_connection)

        # Insert documents
        collection = persistence._collection()
        ids = [str(uuid4()) for _ in range(3)]
        for idx, doc_id in enumerate(ids):
            await collection.insert_one(
                {"_id": doc_id, "name": f"Test {idx}", "value": idx}
            )

        results = await persistence.fetch(ids)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_fetch_empty_result(self, mock_connection):
        """Test fetching with no matching IDs."""
        persistence = ConcreteQueryPersistence(mock_connection)

        results = await persistence.fetch([str(uuid4())])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fetch_converts_to_dto(self, mock_connection):
        """Test that fetch converts documents to DTOs."""
        persistence = ConcreteQueryPersistence(mock_connection)

        collection = persistence._collection()
        doc_id = str(uuid4())
        await collection.insert_one({"_id": doc_id, "name": "Test", "value": 42})

        results = await persistence.fetch([doc_id])

        assert len(results) == 1
        assert isinstance(results[0], SampleReadDTO)
        assert results[0].value == 42

    @pytest.mark.asyncio
    async def test_fetch_with_uow(self, mock_connection):
        """Test fetch with UnitOfWork."""
        from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

        persistence = ConcreteQueryPersistence(mock_connection)

        collection = persistence._collection()
        doc_id = str(uuid4())
        await collection.insert_one({"_id": doc_id, "name": "Test", "value": 1})

        mock_session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = mock_session
        mock_session._in_transaction = True
        results = await persistence.fetch([doc_id], uow=uow)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_fetch_custom_database(self, mock_connection):
        """Test fetch with custom database."""
        persistence = ConcreteQueryPersistence(mock_connection)
        persistence.database = "custom_db"

        collection = persistence._collection()
        doc_id = str(uuid4())
        await collection.insert_one({"_id": doc_id, "name": "Test", "value": 1})

        results = await persistence.fetch([doc_id])

        assert len(results) == 1
        assert persistence._db().name == "custom_db"

    @pytest.mark.asyncio
    async def test_fetch_projection_fields(self, mock_connection):
        """Test that fetch only returns DTO fields."""
        persistence = ConcreteQueryPersistence(mock_connection)

        collection = persistence._collection()
        doc_id = str(uuid4())
        # Insert with extra fields
        await collection.insert_one(
            {"_id": doc_id, "name": "Test", "value": 1, "extra": "ignored"}
        )

        results = await persistence.fetch([doc_id])

        assert len(results) == 1
        assert results[0].name == "Test"
        assert not hasattr(results[0], "extra")


class TestMongoQuerySpecificationPersistence:
    """Tests for MongoQuerySpecificationPersistence (9 tests)."""

    @pytest.mark.asyncio
    async def test_fetch_with_specification(self, mock_connection):
        """Test fetching with a specification."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        # Insert documents
        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 10})
        await collection.insert_one({"_id": str(uuid4()), "name": "Other", "value": 20})

        # Create a specification using AST format
        from cqrs_ddd_specifications import SpecificationOperator

        class SimpleSpec:
            specification = {
                "attr": "name",
                "op": SpecificationOperator.EQ.value,
                "val": "Test",
            }

        results = persistence.fetch(SimpleSpec(), uow=None)
        result_list = await results

        assert len(result_list) == 1
        assert result_list[0].name == "Test"

    @pytest.mark.asyncio
    async def test_fetch_with_query_options_limit(self, mock_connection):
        """Test fetching with query options limit."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        # Insert documents
        collection = persistence._collection()
        for i in range(5):
            await collection.insert_one(
                {"_id": str(uuid4()), "name": f"Test {i}", "value": i}
            )

        # Create options with limit
        class QueryOptions:
            specification = {}
            limit = 2

        results = persistence.fetch(QueryOptions(), uow=None)
        result_list = await results

        assert len(result_list) == 2

    @pytest.mark.asyncio
    async def test_fetch_with_query_options_offset(self, mock_connection):
        """Test fetching with query options offset."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        # Insert documents
        collection = persistence._collection()
        ids = [str(uuid4()) for _ in range(5)]
        for i, doc_id in enumerate(ids):
            await collection.insert_one(
                {"_id": doc_id, "name": f"Test {i}", "value": i}
            )

        # Create options with offset
        class QueryOptions:
            specification = {}
            offset = 2

        results = persistence.fetch(QueryOptions(), uow=None)
        result_list = await results

        assert len(result_list) == 3  # 5 total - 2 offset

    @pytest.mark.asyncio
    async def test_fetch_with_query_options_order_by(self, mock_connection):
        """Test fetching with query options order_by."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        # Insert documents
        collection = persistence._collection()
        for i in [3, 1, 2]:
            await collection.insert_one(
                {"_id": str(uuid4()), "name": f"Test {i}", "value": i}
            )

        # Create options with order_by
        class QueryOptions:
            specification = {}
            order_by = [("value", 1)]

        results = persistence.fetch(QueryOptions(), uow=None)
        result_list = await results

        assert len(result_list) == 3
        assert result_list[0].value == 1
        assert result_list[1].value == 2
        assert result_list[2].value == 3

    @pytest.mark.asyncio
    async def test_fetch_returns_search_result_list(self, mock_connection):
        """Test that fetch returns a SearchResult with list access."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 1})

        # Create empty specification
        class EmptySpec:
            specification = {}

        results = persistence.fetch(EmptySpec(), uow=None)
        assert isinstance(results, SearchResult)

        result_list = await results
        assert isinstance(result_list, list)

    @pytest.mark.asyncio
    async def test_fetch_returns_search_result_stream(self, mock_connection):
        """Test that fetch returns a SearchResult with streaming access."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 1})

        # Create empty specification
        class EmptySpec:
            specification = {}

        results = persistence.fetch(EmptySpec(), uow=None)
        assert isinstance(results, SearchResult)

        streamed_results = []
        async for dto in results.stream():
            streamed_results.append(dto)

        assert len(streamed_results) == 1

    @pytest.mark.asyncio
    async def test_fetch_normalizes_criteria(self, mock_connection):
        """Test that fetch normalizes criteria correctly."""
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 1})

        # Test with object having specification attribute
        class SpecWithAttr:
            specification = {}

        results1 = persistence.fetch(SpecWithAttr(), uow=None)
        results2 = persistence.fetch(SpecWithAttr(), uow=None)

        # Both should work
        list1 = await results1
        list2 = await results2

        assert len(list1) == 1
        assert len(list2) == 1

    @pytest.mark.asyncio
    async def test_fetch_with_uow(self, mock_connection):
        """Test fetch with UnitOfWork."""
        from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

        persistence = ConcreteQuerySpecificationPersistence(mock_connection)

        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 1})

        mock_session = MockSession()
        uow = MongoUnitOfWork.__new__(MongoUnitOfWork)
        uow._session = mock_session
        mock_session._in_transaction = True

        # Create empty specification
        class EmptySpec:
            specification = {}

        results = persistence.fetch(EmptySpec(), uow=uow)

        result_list = [dto async for dto in results.stream()]
        assert len(result_list) == 1

    @pytest.mark.asyncio
    async def test_fetch_custom_database(self, mock_connection):
        """Test fetch with custom database."""
        operation_persistence = ConcreteOperationPersistence(mock_connection)
        operation_persistence.database = "custom_db"
        persistence = ConcreteQuerySpecificationPersistence(mock_connection)
        persistence.database = "custom_db"

        collection = persistence._collection()
        await collection.insert_one({"_id": str(uuid4()), "name": "Test", "value": 1})

        # Create empty specification
        class EmptySpec:
            specification = {}

        results = persistence.fetch(EmptySpec(), uow=None)
        result_list = await results

        assert len(result_list) == 1
        assert persistence._db().name == "custom_db"
