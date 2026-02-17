from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_persistence_sqlalchemy import Base as OutboxBase
from cqrs_ddd_persistence_sqlalchemy import (
    OutboxMessage,
    SQLAlchemyRepository,
    SQLAlchemyUnitOfWork,
)


@pytest.fixture()
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create tables once for the engine
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
        await conn.run_sync(OutboxBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# --- Setup for Test Models ---
class ModelBase(DeclarativeBase):
    pass


# Mocking Aggregate Behavior to avoid Pydantic Metaclass conflict
class AggregateMixin:
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._domain_events: list[Any] = []
        self._version = kwargs.get("_version", 0)
        self._original_version = kwargs.get("_version", 0)
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def version(self) -> int:
        return self._version

    @property
    def original_version(self) -> int:
        return self._original_version

    @classmethod
    def model_validate(cls, obj, *, from_attributes=False):
        if from_attributes:
            data = {k: getattr(obj, k) for k in obj.__dict__ if not k.startswith("_")}
            # Also pick up version
            if hasattr(obj, "version"):
                data["_version"] = obj.version
            return cls(**data)
        return cls(**obj)

    def add_event(self, event: Any) -> None:
        if not hasattr(self, "_domain_events"):
            self._domain_events = []
        self._domain_events.append(event)

    def collect_events(self) -> list[Any]:
        if not hasattr(self, "_domain_events"):
            self._domain_events = []
        events = list(self._domain_events)
        self._domain_events.clear()
        return events


if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot

    class IntAggregate(AggregateRoot, ModelBase):
        __tablename__ = "int_aggregates"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String)

    class UUIDAggregate(AggregateRoot, ModelBase):
        __tablename__ = "uuid_aggregates"
        id: Mapped[str] = mapped_column(
            String, primary_key=True, default=lambda: str(uuid4())
        )
        name: Mapped[str] = mapped_column(String)
else:

    class IntAggregate(AggregateMixin, ModelBase):
        __tablename__ = "int_aggregates"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String)

    class UUIDAggregate(AggregateMixin, ModelBase):
        __tablename__ = "uuid_aggregates"
        id: Mapped[str] = mapped_column(
            String, primary_key=True, default=lambda: str(uuid4())
        )
        name: Mapped[str] = mapped_column(String)


class SomethingHappened(DomainEvent):
    what: str


# --- Test ---
@pytest.mark.asyncio()
async def test_polymorphic_id_outbox_insertion(async_session: AsyncSession) -> None:
    """
    Verifies that the repository can handle both Integer and UUID primary keys,
    correctly casting them to strings in the Outbox table.
    """
    # 1. Setup - Tables are already created by the fixture

    # 2. Test Integer ID Aggregate
    def uow_factory():
        return SQLAlchemyUnitOfWork(session=async_session)

    int_repo = SQLAlchemyRepository(IntAggregate, uow_factory=uow_factory)
    int_agg = IntAggregate(name="Int AGG")
    # Manually init since we aren't using Pydantic init
    int_agg.add_event(SomethingHappened(what="Int Created"))

    await int_repo.add(int_agg)
    await async_session.flush()  # Trigger ID generation

    # Manually simulate UoW outbox persistence
    for event in int_agg.collect_events():
        msg = OutboxMessage(
            event_id=str(uuid4()),
            event_type=event.__class__.__name__,
            payload={"what": event.what},
            occurred_at=datetime.now(timezone.utc),
            event_metadata={
                "aggregate_id": str(int_agg.id),
                "aggregate_type": "IntAggregate",
            },
        )
        async_session.add(msg)
    await async_session.flush()

    # 3. Test UUID ID Aggregate
    uuid_repo = SQLAlchemyRepository(UUIDAggregate, uow_factory=uow_factory)
    uuid_agg = UUIDAggregate(name="UUID AGG")
    uuid_agg.add_event(SomethingHappened(what="UUID Created"))

    await uuid_repo.add(uuid_agg)
    await async_session.flush()

    # Manually simulate UoW outbox persistence
    for event in uuid_agg.collect_events():
        msg = OutboxMessage(
            event_id=str(uuid4()),
            event_type=event.__class__.__name__,
            payload={"what": event.what},
            occurred_at=datetime.now(timezone.utc),
            event_metadata={
                "aggregate_id": str(uuid_agg.id),
                "aggregate_type": "UUIDAggregate",
            },
        )
        async_session.add(msg)
    await async_session.flush()

    # 4. Verify Outbox
    result = await async_session.execute(select(OutboxMessage))
    messages = result.scalars().all()

    print(f"DEBUG: Messages in outbox: {len(messages)}")
    for m in messages:
        meta = m.event_metadata or {}
        print(
            f"DEBUG: Msg - ID: {m.event_id}, "
            f"AggregateID: {meta.get('aggregate_id')}, Type: {m.event_type}"
        )
    print(f"DEBUG: int_agg.id: {int_agg.id}")
    print(f"DEBUG: uuid_agg.id: {uuid_agg.id}")

    assert len(messages) == 2

    # Check Int ID was cast to string
    int_msg = next(
        (
            m
            for m in messages
            if (m.event_metadata or {}).get("aggregate_id") == str(int_agg.id)
        ),
        None,
    )
    assert int_msg is not None, f"Outbox message for Int ID {int_agg.id} not found"
    assert int_msg.event_type == "SomethingHappened"
    assert int_msg.payload["what"] == "Int Created"

    # Check UUID ID was cast to string
    uuid_msg = next(
        (
            m
            for m in messages
            if (m.event_metadata or {}).get("aggregate_id") == str(uuid_agg.id)
        ),
        None,
    )
    assert uuid_msg is not None, f"Outbox message for UUID ID {uuid_agg.id} not found"
    assert uuid_msg.event_type == "SomethingHappened"
    assert uuid_msg.payload["what"] == "UUID Created"
