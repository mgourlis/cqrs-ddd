"""
Tests for the rewritten SQLAlchemy repository.

Covers:
- Separate entity_cls / db_model_cls mapping (to_model / from_model via ModelMapper)
- Unified search() accepting ISpecification or QueryOptions
- Streaming via search(...).stream()
- Hooks support
- Single-model mode (entity is also the DB model)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyRepository, SQLAlchemyUnitOfWork
from cqrs_ddd_specifications import QueryOptions
from cqrs_ddd_specifications.hooks import HookResult, ResolutionContext

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class AggregateMixin:
    """Lightweight mixin that mimics AggregateRoot without pydantic dep."""

    def __init__(self, **kwargs: Any) -> None:
        self._domain_events: list[Any] = []
        self._version = kwargs.pop("_version", 0)
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def version(self) -> int:
        return self._version

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


# -- pure DB model (no domain logic) ---------------------------------------


class ItemModel(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="active")


# -- domain entity (Pydantic-like) -----------------------------------------


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cqrs_ddd_core.domain.aggregate import AggregateRoot

    class Item(AggregateRoot):
        id: str
        name: str
        price: int
        status: str
else:

    class Item(AggregateMixin):
        pass


# -- single-model (legacy) -------------------------------------------------


if TYPE_CHECKING:

    class LegacyProduct(AggregateRoot, Base):
        __tablename__ = "legacy_products"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        name: Mapped[str] = mapped_column(String)
else:

    class LegacyProduct(Base, AggregateMixin):
        __tablename__ = "legacy_products"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        name: Mapped[str] = mapped_column(String)


# -- simple specification --------------------------------------------------


class SimpleSpecification:
    """Minimal ISpecification implementation for tests."""

    def __init__(self, spec_dict: dict[str, Any]) -> None:
        self._data = spec_dict

    def to_dict(self) -> dict[str, Any]:
        return self._data

    def is_satisfied_by(self, candidate: Any) -> bool:
        """Basic in-memory check for leaf equality specs."""
        attr = self._data.get("attr")
        val = self._data.get("val")
        if attr and val is not None:
            return getattr(candidate, attr, None) == val
        return True


class AlwaysTrueSpec:
    """Spec that matches everything (empty dict)."""

    def to_dict(self) -> dict[str, Any]:
        return {}

    def is_satisfied_by(self, candidate: Any) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
def uow_factory(session):
    return lambda: SQLAlchemyUnitOfWork(session=session)


def _seed_items(session: AsyncSession):
    """Seed 5 items into the database."""
    items = [
        ItemModel(
            id=f"i{i}",
            name=f"Item {i}",
            price=i * 10,
            status="active" if i % 2 == 0 else "archived",
        )
        for i in range(1, 6)
    ]
    session.add_all(items)


# ---------------------------------------------------------------------------
# Tests: separate entity_cls / db_model_cls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_class_to_model_from_model(session, uow_factory):
    """to_model creates DB model; from_model creates domain entity."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    entity = Item(id="x1", name="Widget", price=42, status="active")
    db_model = repo.to_model(entity)

    assert isinstance(db_model, ItemModel)
    assert db_model.id == "x1"
    assert db_model.name == "Widget"
    assert db_model.price == 42

    domain = repo.from_model(db_model)
    assert isinstance(domain, Item)
    assert domain.name == "Widget"


@pytest.mark.asyncio
async def test_two_class_crud(session, uow_factory):
    """Full CRUD cycle with separate entity/DB model."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    entity = Item(id="c1", name="CRUD Test", price=100, status="active")

    # Add
    async with uow_factory() as uow:
        result_id = await repo.add(entity, uow=uow)
        await uow.commit()
    assert result_id == "c1"

    # Get
    found = await repo.get("c1")
    assert found is not None
    assert found.name == "CRUD Test"

    # List
    items = await repo.list_all()
    assert len(items) == 1

    # Delete
    await repo.delete("c1")
    await session.commit()
    assert await repo.get("c1") is None


# ---------------------------------------------------------------------------
# Tests: single-model mode (entity IS the DB model)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_model_mode(session, uow_factory):
    """Single-class mode works when entity_cls is also the DB model."""
    repo = SQLAlchemyRepository(LegacyProduct, uow_factory=uow_factory)

    p = LegacyProduct(id="lp1", name="Legacy")
    session.add(p)
    await session.commit()

    found = await repo.get("lp1")
    assert found is not None
    assert found.name == "Legacy"


def test_db_model_cls_defaults_to_entity_cls():
    """When db_model_cls is omitted, it defaults to entity_cls."""
    repo = SQLAlchemyRepository(ItemModel)
    assert repo.db_model_cls is ItemModel
    assert repo.entity_cls is ItemModel


# ---------------------------------------------------------------------------
# Tests: search with specification compiler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_with_spec(session, uow_factory):
    """search() uses build_sqla_filter to compile specification AST."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    spec = SimpleSpecification({"op": "=", "attr": "status", "val": "active"})
    results = await (await repo.search(spec))

    # Items 2, 4 are active (i%2==0)
    assert len(results) == 2
    assert all(r.status == "active" for r in results)


@pytest.mark.asyncio
async def test_search_empty_spec(session, uow_factory):
    """Empty specification dict returns all items."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    results = await (await repo.search(AlwaysTrueSpec()))
    assert len(results) == 5


# ---------------------------------------------------------------------------
# Tests: search with QueryOptions (unified API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_query_options_pagination(session, uow_factory):
    """QueryOptions limit/offset via unified search()."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    opts = QueryOptions(limit=2, offset=1)
    results = await (await repo.search(opts))
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_query_options_ordering(session, uow_factory):
    """QueryOptions order_by via unified search()."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    opts = QueryOptions(order_by=["-price"])
    results = await (await repo.search(opts))
    prices = [r.price for r in results]
    assert prices == sorted(prices, reverse=True)


@pytest.mark.asyncio
async def test_search_query_options_spec_and_pagination(session, uow_factory):
    """Combine specification filter with pagination via unified search()."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    spec = SimpleSpecification({"op": "=", "attr": "status", "val": "active"})
    opts = QueryOptions(specification=spec, limit=1)
    results = await (await repo.search(opts))
    assert len(results) == 1
    assert results[0].status == "active"


# ---------------------------------------------------------------------------
# Tests: streaming via search(...).stream()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_returns_async_iterator(session, uow_factory):
    """search(...).stream() yields entities matching the specification."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    spec = SimpleSpecification({"op": "=", "attr": "status", "val": "archived"})
    collected = []
    async for entity in (await repo.search(spec)).stream(batch_size=2):
        collected.append(entity)

    # Items 1, 3, 5 are archived
    assert len(collected) == 3
    assert all(e.status == "archived" for e in collected)


@pytest.mark.asyncio
async def test_stream_all(session, uow_factory):
    """search(...).stream() with AlwaysTrueSpec returns all."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    count = 0
    async for _ in (await repo.search(AlwaysTrueSpec())).stream():
        count += 1
    assert count == 5


@pytest.mark.asyncio
async def test_stream_with_query_options(session, uow_factory):
    """search(QueryOptions).stream() applies options and streams."""
    repo = SQLAlchemyRepository(Item, ItemModel, uow_factory=uow_factory)

    _seed_items(session)
    await session.commit()

    spec = SimpleSpecification({"op": "=", "attr": "status", "val": "active"})
    opts = QueryOptions(specification=spec, order_by=["-price"])
    collected = []
    async for entity in (await repo.search(opts)).stream():
        collected.append(entity)

    assert len(collected) == 2
    assert all(e.status == "active" for e in collected)


# ---------------------------------------------------------------------------
# Tests: hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hooks_intercept_field_resolution(session, uow_factory):
    """A hook can override field resolution during spec compilation."""

    def price_hook(ctx: ResolutionContext) -> HookResult[Any]:
        if ctx.field_path == "computed_price":
            # Redirect to the real 'price' column on the model
            return HookResult(value=ItemModel.price, handled=True)
        return HookResult.skip()

    repo = SQLAlchemyRepository(
        Item, ItemModel, uow_factory=uow_factory, hooks=[price_hook]
    )

    _seed_items(session)
    await session.commit()

    # Use the virtual "computed_price" field
    spec = SimpleSpecification({"op": ">", "attr": "computed_price", "val": 30})
    # Need full is_satisfied_by override for this spec
    spec.is_satisfied_by = lambda candidate: candidate.price > 30  # type: ignore

    results = await (await repo.search(spec))
    # Items 4 (price=40), 5 (price=50)
    assert len(results) == 2
    assert all(r.price > 30 for r in results)


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_uow_raises():
    """Operations without UoW raise ValueError."""
    repo = SQLAlchemyRepository(Item, ItemModel)

    with pytest.raises(ValueError, match="No UnitOfWork"):
        await repo.get("x")


def test_protocol_compliance():
    """SQLAlchemyRepository is a valid IRepository."""
    from cqrs_ddd_core.ports.repository import IRepository

    assert issubclass(SQLAlchemyRepository, IRepository)
