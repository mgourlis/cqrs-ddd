import pytest
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyRepository, SQLAlchemyUnitOfWork
from cqrs_ddd_persistence_sqlalchemy.exceptions import (
    OptimisticConcurrencyError,
)


class Base(DeclarativeBase):
    pass


class VersionedModel(Base):
    __tablename__ = "versioned_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }

    @classmethod
    def model_validate(cls, obj, *, from_attributes=True):
        if isinstance(obj, dict):
            return MockAggregate(id=obj["id"], name=obj["name"], version=obj["version"])
        return MockAggregate(id=obj.id, name=obj.name, version=obj.version)


class MockAggregate:
    """Simulates an AggregateRoot for testing purposes."""

    def __init__(self, id: str, name: str, version: int = 0):
        self.id = id
        self.name = name
        self._version = version
        self._original_version = version

    @property
    def version(self) -> int:
        return self._version

    @property
    def original_version(self) -> int:
        return self._original_version

    def increment_version(self, count: int = 1):
        self._version += count

    def model_dump(self, **kwargs):
        return {"id": self.id, "name": self.name, "version": self._version}


@pytest.fixture()
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio()
async def test_occ_mismatch_raises_error(session_factory):
    repo = SQLAlchemyRepository(VersionedModel)

    # 1. Create and persist
    agg = MockAggregate(id="item-1", name="Original")
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        await repo.add(agg, uow=uow)
        await uow.commit()

    # 2. User A loads and updates
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_load_a:
        agg_a = await repo.get("item-1", uow=uow_load_a)

    agg_a.increment_version()  # 0 -> 1

    # 3. User B loads concurrently
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_load_b:
        agg_b = await repo.get("item-1", uow=uow_load_b)

    agg_b.increment_version()  # 0 -> 1

    # 4. User A saves
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_a:
        await repo.add(agg_a, uow=uow_a)
        await uow_a.commit()

    # 5. User B fails
    async def _user_b_operation():
        async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_b:
            await repo.add(agg_b, uow=uow_b)
            await uow_b.commit()

    with pytest.raises(OptimisticConcurrencyError):
        await _user_b_operation()


@pytest.mark.asyncio()
async def test_occ_multi_increment_success(session_factory):
    repo = SQLAlchemyRepository(VersionedModel)

    # 1. Create and persist
    agg = MockAggregate(id="item-2", name="Original")
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        await repo.add(agg, uow=uow)
        await uow.commit()

    # 2. Load and multi-increment
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_load:
        agg_loaded = await repo.get("item-2", uow=uow_load)

    assert agg_loaded.version == 0
    assert agg_loaded.original_version == 0

    agg_loaded.increment_version(3)  # 0 -> 3
    assert agg_loaded.version == 3
    assert agg_loaded.original_version == 0

    # 3. Save should succeed because original (0) matches DB (0)
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_save:
        await repo.add(agg_loaded, uow=uow_save)
        await uow_save.commit()

    # 4. Verify new version in DB is 3
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_verify:
        agg_final = await repo.get("item-2", uow=uow_verify)
        assert agg_final.version == 3
        assert agg_final.original_version == 3


@pytest.mark.asyncio()
async def test_occ_multi_increment_conflict(session_factory):
    repo = SQLAlchemyRepository(VersionedModel)

    # 1. Create and persist
    agg = MockAggregate(id="item-3", name="Original")
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        await repo.add(agg, uow=uow)
        await uow.commit()

    # 2. User A loads and multi-increments
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_load_a:
        agg_a = await repo.get("item-3", uow=uow_load_a)
    agg_a.increment_version(2)  # 0 -> 2

    # 3. User B loads concurrently and increments
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_load_b:
        agg_b = await repo.get("item-3", uow=uow_load_b)
    agg_b.increment_version(1)  # 0 -> 1

    # 4. User B saves first
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_b:
        await repo.add(agg_b, uow=uow_b)
        await uow_b.commit()

    # 5. User A fails because original (0) != DB (1)
    async def _user_a_operation():
        async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow_a:
            await repo.add(agg_a, uow=uow_a)
            await uow_a.commit()

    with pytest.raises(OptimisticConcurrencyError) as excinfo:
        await _user_a_operation()

    assert "Current domain version: 2 (original: 0)" in str(excinfo.value)
