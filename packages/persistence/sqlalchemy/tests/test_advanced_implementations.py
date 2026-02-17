"""
Tests for Advanced Persistence Implementations.
Refactored to test all advanced components in one file for simplicity.
"""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyUnitOfWork
from cqrs_ddd_persistence_sqlalchemy.advanced import (
    SagaStateModel,
    SQLAlchemyBackgroundJobRepository,
    SQLAlchemyCommandScheduler,
    SQLAlchemySagaRepository,
    SQLAlchemySnapshotStore,
)
from cqrs_ddd_persistence_sqlalchemy.core.models import Base

# Try exporting advanced modules
try:
    from pydantic import Field

    from cqrs_ddd_advanced_core.background_jobs.entity import (
        BackgroundJobStatus,
        BaseBackgroundJob,
    )
    from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
    from cqrs_ddd_core.cqrs.command import Command

    HAS_ADVANCED_CORE = True
except ImportError:
    HAS_ADVANCED_CORE = False

    # Mock classes or just pass, as tests will be skipped
    class SagaState:
        pass

    class SagaStatus:
        pass

    class BaseBackgroundJob:
        pass

    class BackgroundJobStatus:
        pass

    class Command:
        pass


@pytest.fixture()
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio()
@pytest.mark.skipif(
    not HAS_ADVANCED_CORE, reason="cqrs-ddd-advanced-core not installed"
)
async def test_saga_repository(session_factory):
    """Test Saga persistence."""

    # Define a concrete SagaState class
    class MySagaState(SagaState):
        pass

    async with session_factory() as session:

        def uow_factory():
            return SQLAlchemyUnitOfWork(session=session)

        repo = SQLAlchemySagaRepository(MySagaState, uow_factory=uow_factory)

        saga_id = str(uuid4())
        correlation_id = str(uuid4())

        saga = MySagaState(
            id=saga_id,
            correlation_id=correlation_id,
            status=SagaStatus.RUNNING,
            # state={"foo": "bar"},  <-- SagaState doesn't have generic state, uses dedicated fields or metadata
            metadata={"foo": "bar"},
            # events=[{"type": "Event1"}], <-- doesn't have events
        )
        saga.record_step("step1", "Event1")

        # Add
        await repo.add(saga)
        await session.commit()

        # Get
        loaded = await repo.get(saga_id)
        assert loaded is not None
        assert loaded.id == saga_id
        assert loaded.correlation_id == correlation_id
        assert loaded.metadata == {"foo": "bar"}
        assert loaded.status == SagaStatus.RUNNING
        assert loaded.current_step == "step1"

        # Find by correlation
        found = await repo.find_by_correlation_id(correlation_id, "MySagaState")
        assert found is not None
        assert found.id == saga_id

        # Find stalled
        # Force update date.
        from sqlalchemy import update

        await session.execute(
            update(SagaStateModel)
            .where(SagaStateModel.id == saga_id)
            .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        )
        await session.commit()

        stalled = await repo.find_stalled_sagas()
        assert len(stalled) == 1
        assert stalled[0].id == saga_id


@pytest.mark.asyncio()
@pytest.mark.skipif(
    not HAS_ADVANCED_CORE, reason="cqrs-ddd-advanced-core not installed"
)
async def test_job_repository(session_factory):
    """Test Background Job persistence."""

    class MyJob(BaseBackgroundJob):
        queue: str = "default"
        payload: dict[str, Any] = Field(default_factory=dict)
        started_at: datetime | None = None
        completed_at: datetime | None = None
        failed_at: datetime | None = None
        scheduled_at: datetime | None = None
        last_error: str | None = None

    async with session_factory() as session:

        def uow_factory():
            return SQLAlchemyUnitOfWork(session=session)

        repo = SQLAlchemyBackgroundJobRepository(MyJob, uow_factory=uow_factory)

        job_id = str(uuid4())
        job = MyJob(
            id=job_id,
            job_type="email_job",
            payload={"to": "user@example.com"},
            status=BackgroundJobStatus.PENDING,
        )

        # Add
        await repo.add(job)
        await session.commit()

        # Get
        loaded = await repo.get(job.id)
        assert loaded is not None
        assert loaded.id == job.id
        assert loaded.job_type == "email_job"
        assert loaded.status == BackgroundJobStatus.PENDING
        assert loaded.version == job.version  # Verify version starts at 0

        # Update
        job.status = BackgroundJobStatus.RUNNING
        # Simulate business logic touching the aggregate (which increments version)
        # We manually increment here if the test object doesn't use the real base logic fully
        # BaseBackgroundJob._touch() does object.__setattr__(self, "_version", self.version + 1)
        # Let's assume start_processing or similar method is called, or we manually simulate it
        job._touch()

        await repo.add(job)  # Upsert/Merge logic
        await session.commit()

        loaded_again = await repo.get(job.id)
        assert loaded_again.status == BackgroundJobStatus.RUNNING
        assert loaded_again.version == 1  # Verify version incremented


@pytest.mark.asyncio()
@pytest.mark.skipif(
    not HAS_ADVANCED_CORE, reason="cqrs-ddd-advanced-core not installed"
)
async def test_command_scheduler(session_factory):
    """Test Command Scheduler persistence."""

    # Mock Command
    class MyCommand(Command):
        data: str

    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

    async with session_factory() as session:
        registry = MessageRegistry()
        registry.register_command("MyCommand", MyCommand)

        def uow_factory():
            return SQLAlchemyUnitOfWork(session=session)

        scheduler = SQLAlchemyCommandScheduler(uow_factory, registry)

        cmd = MyCommand(data="test")
        exec_time = datetime.now(timezone.utc) - timedelta(seconds=1)  # Due now

        # Schedule
        schedule_id = await scheduler.schedule(cmd, exec_time)
        await session.commit()

        assert schedule_id is not None

        # Get Due
        due = await scheduler.get_due_commands()
        assert len(due) == 1
        s_id, payload = due[0]
        assert s_id == schedule_id
        assert payload.data == "test"
        assert payload.__class__.__name__ == "MyCommand"

        # Cancel
        cancelled = await scheduler.cancel(schedule_id)
        await session.commit()
        assert cancelled is True

        # Verify status
        due_again = await scheduler.get_due_commands()
        assert len(due_again) == 0


@pytest.mark.asyncio()
@pytest.mark.skipif(
    not HAS_ADVANCED_CORE, reason="cqrs-ddd-advanced-core not installed"
)
async def test_snapshot_store(session_factory):
    """Test Snapshot Store."""

    async with session_factory() as session:

        def uow_factory():
            return SQLAlchemyUnitOfWork(session=session)

        store = SQLAlchemySnapshotStore(uow_factory)
        agg_id = "agg-123"
        agg_type = "Order"

        # Save V1
        await store.save_snapshot(agg_type, agg_id, {"total": 100}, 1)
        # Save V5
        await store.save_snapshot(agg_type, agg_id, {"total": 200}, 5)
        await session.commit()

        # Get Latest
        snap = await store.get_latest_snapshot(agg_type, agg_id)
        assert snap is not None
        assert snap["version"] == 5
        assert snap["snapshot_data"] == {"total": 200}

        # Delete
        await store.delete_snapshot(agg_type, agg_id)
        await session.commit()

        snap_after = await store.get_latest_snapshot(agg_type, agg_id)
        assert snap_after is None
