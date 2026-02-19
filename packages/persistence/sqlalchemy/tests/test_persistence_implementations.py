from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cqrs_ddd_core.ports.event_store import StoredEvent
from cqrs_ddd_core.ports.outbox import OutboxMessage
from cqrs_ddd_persistence_sqlalchemy import (
    Base,
    OutboxStatus,
    SQLAlchemyEventStore,
    SQLAlchemyOutboxStorage,
    SQLAlchemyUnitOfWork,
)
from cqrs_ddd_persistence_sqlalchemy import (
    OutboxMessage as OutboxMessageModel,
)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_uow_auto_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Test Auto-Commit on Success
    async with session_factory() as session:
        uow = SQLAlchemyUnitOfWork(session)
        async with uow:
            msg = OutboxMessageModel(
                event_id="test-auto-1",
                event_type="TestEvent",
                payload={},
                status=OutboxStatus.PENDING,
                occurred_at=datetime.now(timezone.utc),
                event_metadata={"aggregate_id": "agg-1"},
            )
            session.add(msg)
        # Session is closed here, but data should be committed.

    # Verify in a new session
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id == "test-auto-1"
            )
        )
        assert result.scalar_one() is not None


@pytest.mark.asyncio
async def test_uow_auto_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Test Auto-Rollback on Exception
    async with session_factory() as session:
        uow = SQLAlchemyUnitOfWork(session)
        try:
            async with uow:
                msg = OutboxMessageModel(
                    event_id="test-fail-1",
                    event_type="TestEvent",
                    payload={},
                    status=OutboxStatus.PENDING,
                    occurred_at=datetime.now(timezone.utc),
                    event_metadata={"aggregate_id": "agg-1"},
                )
                session.add(msg)
                raise ValueError("Force rollback")
        except ValueError:
            pass

    # Verify it does NOT exist
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id == "test-fail-1"
            )
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_outbox_storage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        storage = SQLAlchemyOutboxStorage(session)

        # Save
        msg1 = OutboxMessage(
            message_id="msg-1",
            event_type="Event1",
            payload={"a": 1},
            metadata={"aggregate_id": "agg-1"},
            correlation_id="test-correlation-1",
        )
        msg2 = OutboxMessage(
            message_id="msg-2",
            event_type="Event2",
            payload={"b": 2},
            metadata={"aggregate_id": "agg-1"},
            correlation_id="test-correlation-1",
            causation_id="msg-1",
        )

        await storage.save_messages([msg1, msg2])
        await session.commit()

        # Get Pending
        pending = await storage.get_pending(limit=10)
        assert len(pending) == 2

        # Mark Published
        await storage.mark_published(["msg-1"])
        await session.commit()

        pending = await storage.get_pending(limit=10)
        assert len(pending) == 1

        # Mark Failed
        await storage.mark_failed("msg-2", "Something wrong")
        await session.commit()

        # Verify failed status
        result = await session.execute(
            select(OutboxMessageModel).where(OutboxMessageModel.event_id == "msg-2")
        )
        model = result.scalar_one()
        assert model.retry_count == 1


@pytest.mark.asyncio
async def test_event_store(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        store = SQLAlchemyEventStore(session)

        event1 = StoredEvent(
            event_id="evt-1",
            event_type="Created",
            aggregate_id="agg-1",
            aggregate_type="Agg",
            version=1,
            payload={"foo": "bar"},
        )
        event2 = StoredEvent(
            event_id="evt-2",
            event_type="Updated",
            aggregate_id="agg-1",
            aggregate_type="Agg",
            version=2,
            payload={"foo": "baz"},
        )

        # Append
        await store.append(event1)
        await store.append_batch([event2])
        await session.commit()

        # Get by aggregate
        events = await store.get_by_aggregate("agg-1")
        assert len(events) == 2

        # Get events after version
        events_after = await store.get_events("agg-1", after_version=1)
        assert len(events_after) == 1

        # Get all
        all_events = await store.get_all()
        assert len(all_events) == 2
