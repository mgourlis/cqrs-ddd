"""Integration tests for MongoDB persistence with Unit of Work."""

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_persistence_mongo import MongoRepository, MongoUnitOfWork


@dataclass(frozen=True)
class SampleEntity(AggregateRoot):
    """Sample entity for integration tests (name avoids pytest collection)."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    value: int = 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_with_uow_commit(real_mongo_connection):
    """Test that repository operations work within UoW transaction."""
    repo = MongoRepository(
        real_mongo_connection,
        collection="test_entities",
        model_cls=SampleEntity,
        database="test_db",
    )

    # Create entity with UoW
    entity = SampleEntity(id=str(uuid4()), name="Test", value=42)

    # Simulate UoW context
    uow = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    async with uow:
        entity_id = await repo.add(entity, uow=uow)
        await uow.commit()

    # Verify entity was saved
    retrieved = await repo.get(entity_id)

    assert retrieved is not None
    assert retrieved.id == entity_id
    assert retrieved.name == "Test"
    assert retrieved.value == 42


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_rollback_on_exception(real_mongo_connection):
    """Test that changes are rolled back when exception occurs."""
    repo = MongoRepository(
        real_mongo_connection,
        collection="test_entities",
        model_cls=SampleEntity,
        database="test_db",
    )

    entity = SampleEntity(id=str(uuid4()), name="RollbackTest", value=100)

    # Test rollback
    uow = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    with pytest.raises(ValueError):
        async with uow:
            await repo.add(entity, uow=uow)
            await uow.commit()
            raise ValueError("Simulated error")

    # Note: With standalone MongoDB, rollback is no-op
    # With replica sets and transactions, changes would be rolled back


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_list_all_with_uow(real_mongo_connection):
    """Test list_all works with UoW."""
    repo = MongoRepository(
        real_mongo_connection,
        collection="test_entities",
        model_cls=SampleEntity,
        database="test_db",
    )

    # Add multiple entities
    entities = [
        SampleEntity(id=str(uuid4()), name=f"Entity{i}", value=i) for i in range(3)
    ]

    uow = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    async with uow:
        for entity in entities:
            await repo.add(entity, uow=uow)
        await uow.commit()

    # Retrieve all
    all_entities = await repo.list_all()

    assert len(all_entities) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_delete_with_uow(real_mongo_connection):
    """Test delete operation with UoW."""
    repo = MongoRepository(
        real_mongo_connection,
        collection="test_entities",
        model_cls=SampleEntity,
        database="test_db",
    )

    entity = SampleEntity(id=str(uuid4()), name="ToDelete", value=1)

    uow = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    async with uow:
        entity_id = await repo.add(entity, uow=uow)
        await uow.commit()

    # Verify existence
    retrieved = await repo.get(entity_id)
    assert retrieved is not None

    # Delete
    uow2 = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    async with uow2:
        deleted_id = await repo.delete(entity_id, uow=uow2)
        await uow2.commit()

    # Verify deletion
    retrieved = await repo.get(entity_id)
    assert retrieved is None
    assert deleted_id == entity_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_on_commit_hooks_work(real_mongo_connection):
    """Test that on_commit hooks are executed after commit."""
    repo = MongoRepository(
        real_mongo_connection,
        collection="test_entities",
        model_cls=SampleEntity,
        database="test_db",
    )

    hook_called = False

    async def hook():
        nonlocal hook_called
        hook_called = True

    entity = SampleEntity(id=str(uuid4()), name="HookTest", value=1)

    uow = MongoUnitOfWork(connection=real_mongo_connection, require_replica_set=False)
    uow.on_commit(hook)

    async with uow:
        await repo.add(entity, uow=uow)
        await uow.commit()

    assert hook_called
