from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyRepository


class Base(DeclarativeBase):
    pass


class AggregateMixin:
    def __init__(self, **kwargs: Any) -> None:
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

    def collect_events(self) -> list[Any]:
        return []


if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot

    class Product(AggregateRoot, Base):
        __tablename__ = "products"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        name: Mapped[str] = mapped_column(String)
else:

    class Product(Base, AggregateMixin):
        __tablename__ = "products"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        name: Mapped[str] = mapped_column(String)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_get_delete_list(session: AsyncSession) -> None:
    from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyUnitOfWork

    def uow_factory():
        return SQLAlchemyUnitOfWork(session=session)

    repo = SQLAlchemyRepository(Product, uow_factory=uow_factory)

    p1 = Product(id="p1", name="Product 1")
    p2 = Product(id="p2", name="Product 2")

    session.add_all([p1, p2])
    await session.commit()

    # Test list
    products = await repo.list_all()
    assert len(products) == 2

    # Test get
    found = await repo.get("p1")
    assert found is not None
    assert found.name == "Product 1"

    # Test delete
    await repo.delete("p1")
    await session.commit()

    found = await repo.get("p1")
    assert found is None

    products = await repo.list_all()
    assert len(products) == 1


@pytest.mark.asyncio
async def test_repository_not_found(session: AsyncSession) -> None:
    from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyUnitOfWork

    def uow_factory():
        return SQLAlchemyUnitOfWork(session=session)

    repo = SQLAlchemyRepository(Product, uow_factory=uow_factory)
    found = await repo.get("non-existent")
    assert found is None


def test_repository_protocol_compliance() -> None:
    from cqrs_ddd_core.ports.repository import IRepository

    assert issubclass(SQLAlchemyRepository, IRepository)
