"""
Tests for SQLAlchemy persistence dispatcher bases.

Covers:
- SQLAlchemyOperationPersistence
- SQLAlchemyRetrievalPersistence
- SQLAlchemyQueryPersistence
- SQLAlchemyQuerySpecificationPersistence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_persistence_sqlalchemy.advanced.persistence import (
    SQLAlchemyOperationPersistence,
    SQLAlchemyQueryPersistence,
    SQLAlchemyQuerySpecificationPersistence,
    SQLAlchemyRetrievalPersistence,
)
from cqrs_ddd_persistence_sqlalchemy.core.uow import SQLAlchemyUnitOfWork

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class AggregateMixin:
    """Lightweight mixin mimicking AggregateRoot."""

    def __init__(self, **kwargs: Any) -> None:
        self._domain_events: list[Any] = []
        self._version = kwargs.pop("_version", 0)
        self._original_version = kwargs.pop("_original_version", self._version)
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def version(self) -> int:
        return self._version

    @property
    def original_version(self) -> int:
        return self._original_version

    @classmethod
    def model_validate(cls, obj: Any, *, from_attributes: bool = False) -> Any:
        if from_attributes:
            data = {k: getattr(obj, k) for k in obj.__dict__ if not k.startswith("_")}
            if hasattr(obj, "version"):
                data["_version"] = obj.version
            return cls(**data)
        return cls(**obj)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def collect_events(self) -> list[Any]:
        return []


class OrderModel(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer: Mapped[str] = mapped_column(String)
    total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending")


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cqrs_ddd_core.domain.aggregate import AggregateRoot

    class Order(AggregateRoot):
        id: str
        customer: str
        total: int
        status: str
else:

    class Order(AggregateMixin):
        pass


@dataclass
class Modification:
    entity: Any
    events: list[Any]


@dataclass
class OrderDTO:
    id: str
    customer: str
    total: int
    status: str


class SimpleSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return self._data

    def is_satisfied_by(self, candidate: Any) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture()
async def uow(session) -> AsyncGenerator[SQLAlchemyUnitOfWork, None]:
    async with SQLAlchemyUnitOfWork(session=session) as unit:
        yield unit


def _seed_orders(session: AsyncSession) -> None:
    orders = [
        OrderModel(
            id=f"o{i}",
            customer=f"C{i}",
            total=i * 100,
            status="active" if i % 2 == 0 else "pending",
        )
        for i in range(1, 6)
    ]
    session.add_all(orders)


# ---------------------------------------------------------------------------
# Operation Persistence
# ---------------------------------------------------------------------------


class ConcreteOperationPersistence(SQLAlchemyOperationPersistence[Order, str]):
    entity_cls = Order
    db_model_cls = OrderModel


@pytest.mark.asyncio()
async def test_operation_persistence_add(session, uow):
    handler = ConcreteOperationPersistence()
    entity = Order(id="op1", customer="Alice", total=500, status="new")
    mod = Modification(entity=entity, events=[])
    result_id = await handler.persist(mod, uow)
    await uow.commit()
    assert result_id == "op1"

    # Verify persisted
    found = await session.get(OrderModel, "op1")
    assert found is not None
    assert found.customer == "Alice"


# ---------------------------------------------------------------------------
# Retrieval Persistence
# ---------------------------------------------------------------------------


class ConcreteRetrievalPersistence(SQLAlchemyRetrievalPersistence[Order, str]):
    entity_cls = Order
    db_model_cls = OrderModel


@pytest.mark.asyncio()
async def test_retrieval_persistence(session, uow):
    _seed_orders(session)
    await session.commit()

    handler = ConcreteRetrievalPersistence()
    results = await handler.retrieve(["o1", "o3"], uow)
    assert len(results) == 2
    ids = {r.id for r in results}
    assert ids == {"o1", "o3"}


# ---------------------------------------------------------------------------
# Query Persistence (by ID)
# ---------------------------------------------------------------------------


class ConcreteQueryPersistence(SQLAlchemyQueryPersistence[OrderDTO, str]):
    db_model_cls = OrderModel

    def to_dto(self, model: Any) -> OrderDTO:
        return OrderDTO(
            id=model.id,
            customer=model.customer,
            total=model.total,
            status=model.status,
        )


@pytest.mark.asyncio()
async def test_query_persistence_by_ids(session, uow):
    _seed_orders(session)
    await session.commit()

    handler = ConcreteQueryPersistence()
    results = await handler.fetch(["o2", "o4"], uow)
    assert len(results) == 2
    assert all(isinstance(r, OrderDTO) for r in results)


# ---------------------------------------------------------------------------
# Query by Specification Persistence
# ---------------------------------------------------------------------------


class ConcreteQuerySpecPersistence(SQLAlchemyQuerySpecificationPersistence[OrderDTO]):
    db_model_cls = OrderModel

    def to_dto(self, model: Any) -> OrderDTO:
        return OrderDTO(
            id=model.id,
            customer=model.customer,
            total=model.total,
            status=model.status,
        )


@pytest.mark.asyncio()
async def test_query_spec_persistence_fetch(session, uow):
    _seed_orders(session)
    await session.commit()

    handler = ConcreteQuerySpecPersistence()
    spec = SimpleSpec({"op": "=", "attr": "status", "val": "active"})
    results = await handler.fetch(spec, uow)
    # Items 2, 4 are active
    assert len(results) == 2
    assert all(r.status == "active" for r in results)


@pytest.mark.asyncio()
async def test_query_spec_persistence_stream(session, uow):
    _seed_orders(session)
    await session.commit()

    handler = ConcreteQuerySpecPersistence()
    spec = SimpleSpec({"op": "=", "attr": "status", "val": "pending"})

    collected = []
    async for dto in handler.fetch(spec, uow).stream(batch_size=2):
        collected.append(dto)

    # Items 1, 3, 5 are pending
    assert len(collected) == 3
    assert all(isinstance(d, OrderDTO) for d in collected)


@pytest.mark.asyncio()
async def test_query_spec_with_options(session, uow):
    from cqrs_ddd_specifications import QueryOptions

    _seed_orders(session)
    await session.commit()

    handler = ConcreteQuerySpecPersistence()
    opts = QueryOptions(limit=2, order_by=["-total"])

    # Fetch with query options via unified fetch(criteria, uow)
    results = await handler.fetch(opts, uow)
    assert len(results) == 2
    assert results[0].total >= results[1].total


@pytest.mark.asyncio()
async def test_uow_type_check():
    """Passing non-SQLAlchemy UoW raises TypeError."""
    handler = ConcreteQuerySpecPersistence()
    spec = SimpleSpec({"op": "=", "attr": "id", "val": "x"})

    class FakeUow:
        pass

    with pytest.raises(TypeError, match="Expected SQLAlchemyUnitOfWork"):
        await handler.fetch(spec, FakeUow())  # type: ignore
