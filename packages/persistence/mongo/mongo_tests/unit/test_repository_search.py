"""Unit tests for MongoRepository search functionality."""

from __future__ import annotations

from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from cqrs_ddd_persistence_mongo.core.repository import MongoRepository


# Sample model (name avoids pytest collecting it as a test class)
class SampleReadModel(BaseModel):
    """Simple read model for repository search tests."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    value: int = 0
    category: str = "default"


# Fixtures
@pytest.fixture
def mock_client():
    """Create a mock MongoDB client."""
    return AsyncMongoMockClient(default_database_name="test_db")


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
async def repository_with_data(mock_connection):
    """Create a repository with sample test data."""
    repository = MongoRepository(
        connection=mock_connection,
        collection="test_collection",
        model_cls=SampleReadModel,
        id_field="id",
    )

    # Add sample data
    entities = [
        SampleReadModel(id=str(uuid4()), name=f"Entity {i}", value=i, category="A")
        for i in range(10)
    ]
    for entity in entities:
        await repository.add(entity)

    return repository


# Phase 2, Step 5: Repository Search Tests (10 tests)


class TestMongoRepositorySearch:
    """Tests for search() method."""

    @pytest.mark.asyncio
    async def test_search_with_eq_specification(self, repository_with_data):
        """Test search with equality specification."""
        # Create simple specification-like object
        class SimpleSpec:
            specification = {"attr": "value", "op": "=", "val": 5}

        result = await repository_with_data.search(SimpleSpec())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        assert len(results_list) == 1
        assert results_list[0].value == 5

    @pytest.mark.asyncio
    async def test_search_with_and_specification(self, repository_with_data):
        """Test search with AND specification."""
        # Create specification with multiple conditions using AST format
        class AndSpec:
            specification = {
                "op": "and",
                "conditions": [
                    {"attr": "value", "op": ">=", "val": 3},
                    {"attr": "category", "op": "=", "val": "A"}
                ]
            }

        result = await repository_with_data.search(AndSpec())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        assert len(results_list) == 7  # values 3,4,5,6,7,8,9

    @pytest.mark.asyncio
    async def test_search_with_or_specification(self, repository_with_data):
        """Test search with OR specification."""
        # Create specification with OR logic using AST format
        class OrSpec:
            specification = {
                "op": "or",
                "conditions": [
                    {"attr": "value", "op": "=", "val": 0},
                    {"attr": "value", "op": "=", "val": 9}
                ]
            }

        result = await repository_with_data.search(OrSpec())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        assert len(results_list) == 2
        values = {r.value for r in results_list}
        assert values == {0, 9}

    @pytest.mark.asyncio
    async def test_search_with_limit(self, repository_with_data):
        """Test search with limit option."""
        # Create options with limit
        class QueryOptions:
            specification = {}
            limit = 5

        result = await repository_with_data.search(QueryOptions())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        # Should limit results to 5
        assert len(results_list) == 5

    @pytest.mark.asyncio
    async def test_search_with_offset(self, repository_with_data):
        """Test search with offset option."""
        # Create specification-like object with offset in options
        class QueryOptions:
            specification = {}
            offset = 5

        result = await repository_with_data.search(QueryOptions())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        # Should skip first 5 results
        assert len(results_list) == 5
        # Verify we got the last 5
        all_results = await repository_with_data.list_all()
        assert results_list == all_results[5:]

    @pytest.mark.asyncio
    async def test_search_with_order_by(self, repository_with_data):
        """Test search with order_by option."""
        # Create options with order_by
        class QueryOptions:
            specification = {}
            order_by = ["-value"]  # Descending (uses MongoDB-like syntax)

        result = await repository_with_data.search(QueryOptions())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        # Verify descending order
        if len(results_list) > 1:
            for i in range(len(results_list) - 1):
                assert results_list[i].value >= results_list[i + 1].value

    @pytest.mark.asyncio
    async def test_search_with_projection(self, repository_with_data):
        """Test search with projection (select fields)."""
        # Create options with select_fields
        class QueryOptions:
            specification = {}
            select_fields = ["name", "value"]

        result = await repository_with_data.search(QueryOptions())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        # Results should still be complete models
        # (projection in aggregation is applied, but model_from_doc hydrates)
        assert len(results_list) >= 1
        assert all(isinstance(r, SampleReadModel) for r in results_list)

    @pytest.mark.asyncio
    async def test_search_returns_search_result(self, repository_with_data):
        """Test that search returns a SearchResult object."""
        from cqrs_ddd_core.ports.search_result import SearchResult

        class EmptySpec:
            specification = {}

        result = await repository_with_data.search(EmptySpec())

        assert isinstance(result, SearchResult)

    @pytest.mark.asyncio
    async def test_search_stream_mode(self, repository_with_data):
        """Test search with streaming mode."""
        class EmptySpec:
            specification = {}

        result = await repository_with_data.search(EmptySpec())

        # Stream results
        streamed = []
        async for entity in result.stream(batch_size=3):
            streamed.append(entity)

        assert len(streamed) == 10

    @pytest.mark.asyncio
    async def test_search_with_complex_nested_spec(self, repository_with_data):
        """Test search with complex nested specification."""
        # Create complex specification using AST format
        class ComplexSpec:
            specification = {
                "op": "and",
                "conditions": [
                    {"attr": "value", "op": "between", "val": [2, 8]},
                    {"attr": "category", "op": "=", "val": "A"},
                ]
            }

        result = await repository_with_data.search(ComplexSpec())
        results_list = []
        async for item in result.stream():
            results_list.append(item)

        # Should match values 2-8 with category A (7 values)
        assert len(results_list) == 7
        assert all(2 <= r.value <= 8 for r in results_list)
        assert all(r.category == "A" for r in results_list)
