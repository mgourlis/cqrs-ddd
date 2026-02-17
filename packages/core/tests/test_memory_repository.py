"""Tests for InMemoryRepository."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.adapters.memory.repository import InMemoryRepository
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.specification import ISpecification


class DummyAggregate(AggregateRoot[str]):
    """Test aggregate for repository tests."""

    name: str = ""
    age: int = 0


class DummySpecification(ISpecification[DummyAggregate]):
    """Test specification that matches entities with age > 18."""

    def is_satisfied_by(self, entity: DummyAggregate) -> bool:
        return entity.age > 18


@pytest.mark.asyncio
class TestInMemoryRepository:
    """Test InMemoryRepository CRUD operations and search."""

    @pytest.fixture
    def repo(self) -> InMemoryRepository:
        """Create fresh repository for each test."""
        return InMemoryRepository()

    async def test_add_entity(self, repo: InMemoryRepository) -> None:
        """Add stores entity and returns its ID."""
        entity = DummyAggregate(id="e1", name="Alice", age=25)

        result_id = await repo.add(entity)

        assert result_id == "e1"
        assert len(repo) == 1

    async def test_get_existing_entity(self, repo: InMemoryRepository) -> None:
        """Get retrieves existing entity by ID."""
        entity = DummyAggregate(id="e1", name="Alice", age=25)
        await repo.add(entity)

        result = await repo.get("e1")

        assert result is not None
        assert result.id == "e1"
        assert result.name == "Alice"

    async def test_get_nonexistent_entity(self, repo: InMemoryRepository) -> None:
        """Get returns None for nonexistent ID."""
        result = await repo.get("nonexistent")

        assert result is None

    async def test_delete_existing_entity(self, repo: InMemoryRepository) -> None:
        """Delete removes entity and returns its ID."""
        entity = DummyAggregate(id="e1", name="Alice", age=25)
        await repo.add(entity)

        result_id = await repo.delete("e1")

        assert result_id == "e1"
        assert len(repo) == 0
        assert await repo.get("e1") is None

    async def test_delete_nonexistent_entity(self, repo: InMemoryRepository) -> None:
        """Delete nonexistent entity returns ID without error."""
        result_id = await repo.delete("nonexistent")

        assert result_id == "nonexistent"
        assert len(repo) == 0

    async def test_list_all_without_ids(self, repo: InMemoryRepository) -> None:
        """list_all without IDs returns all entities."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        entity2 = DummyAggregate(id="e2", name="Bob", age=30)
        await repo.add(entity1)
        await repo.add(entity2)

        result = await repo.list_all()

        assert len(result) == 2
        assert entity1 in result
        assert entity2 in result

    async def test_list_all_with_empty_repo(self, repo: InMemoryRepository) -> None:
        """list_all returns empty list for empty repository."""
        result = await repo.list_all()

        assert result == []

    async def test_list_all_with_specific_ids(self, repo: InMemoryRepository) -> None:
        """list_all with IDs returns only specified entities."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        entity2 = DummyAggregate(id="e2", name="Bob", age=30)
        entity3 = DummyAggregate(id="e3", name="Charlie", age=35)
        await repo.add(entity1)
        await repo.add(entity2)
        await repo.add(entity3)

        result = await repo.list_all(entity_ids=["e1", "e3"])

        assert len(result) == 2
        ids = [e.id for e in result]
        assert "e1" in ids
        assert "e3" in ids
        assert "e2" not in ids

    async def test_list_all_with_nonexistent_ids(self, repo: InMemoryRepository) -> None:
        """list_all with nonexistent IDs returns empty list."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        await repo.add(entity1)

        result = await repo.list_all(entity_ids=["e99", "e100"])

        assert result == []

    async def test_search_with_matching_specification(self, repo: InMemoryRepository) -> None:
        """search returns entities matching specification."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)  # Matches (>18)
        entity2 = DummyAggregate(id="e2", name="Bob", age=15)  # Does not match
        entity3 = DummyAggregate(id="e3", name="Charlie", age=30)  # Matches (>18)
        await repo.add(entity1)
        await repo.add(entity2)
        await repo.add(entity3)

        spec = DummySpecification()
        search_result = await repo.search(spec)

        # Test list mode
        results = await search_result

        assert len(results) == 2
        ids = [e.id for e in results]
        assert "e1" in ids
        assert "e3" in ids
        assert "e2" not in ids

    async def test_search_with_no_matches(self, repo: InMemoryRepository) -> None:
        """search returns empty list when no entities match."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=10)
        entity2 = DummyAggregate(id="e2", name="Bob", age=15)
        await repo.add(entity1)
        await repo.add(entity2)

        spec = DummySpecification()
        search_result = await repo.search(spec)

        results = await search_result

        assert results == []

    async def test_search_stream_mode(self, repo: InMemoryRepository) -> None:
        """search.stream() yields entities one by one."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        entity2 = DummyAggregate(id="e2", name="Bob", age=30)
        entity3 = DummyAggregate(id="e3", name="Charlie", age=35)
        await repo.add(entity1)
        await repo.add(entity2)
        await repo.add(entity3)

        spec = DummySpecification()
        search_result = await repo.search(spec)

        # Test stream mode
        results = []
        async for entity in search_result.stream():
            results.append(entity)

        assert len(results) == 3
        ids = [e.id for e in results]
        assert set(ids) == {"e1", "e2", "e3"}

    async def test_search_stream_with_batch_size(self, repo: InMemoryRepository) -> None:
        """search.stream(batch_size) processes in batches."""
        for i in range(10):
            entity = DummyAggregate(id=f"e{i}", name=f"Person{i}", age=20 + i)
            await repo.add(entity)

        spec = DummySpecification()
        search_result = await repo.search(spec)

        # Stream with batch size
        results = []
        async for entity in search_result.stream(batch_size=3):
            results.append(entity)

        # All entities should be yielded
        assert len(results) == 10

    async def test_clear_helper_method(self, repo: InMemoryRepository) -> None:
        """clear() removes all entities."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        entity2 = DummyAggregate(id="e2", name="Bob", age=30)
        await repo.add(entity1)
        await repo.add(entity2)

        repo.clear()

        assert len(repo) == 0
        assert await repo.list_all() == []

    async def test_len_reflects_entity_count(self, repo: InMemoryRepository) -> None:
        """len() returns number of entities in repository."""
        assert len(repo) == 0

        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        await repo.add(entity1)
        assert len(repo) == 1

        entity2 = DummyAggregate(id="e2", name="Bob", age=30)
        await repo.add(entity2)
        assert len(repo) == 2

        await repo.delete("e1")
        assert len(repo) == 1

    async def test_update_entity(self, repo: InMemoryRepository) -> None:
        """Adding entity with same ID updates the stored entity."""
        entity1 = DummyAggregate(id="e1", name="Alice", age=25)
        await repo.add(entity1)

        # Update entity
        entity1_updated = DummyAggregate(id="e1", name="Alice Updated", age=26)
        await repo.add(entity1_updated)

        result = await repo.get("e1")
        assert result is not None
        assert result.name == "Alice Updated"
        assert result.age == 26
        assert len(repo) == 1  # Still only one entity
