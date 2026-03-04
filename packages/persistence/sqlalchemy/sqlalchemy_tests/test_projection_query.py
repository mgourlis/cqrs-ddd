"""Tests for SQLAlchemy projection query persistence adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyProjectionStore
from cqrs_ddd_persistence_sqlalchemy.advanced.projection_query import (
    SQLAlchemyProjectionDualPersistence,
    SQLAlchemyProjectionQueryPersistence,
    SQLAlchemyProjectionSpecPersistence,
)
from cqrs_ddd_persistence_sqlalchemy.core.models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS query_test (id TEXT PRIMARY KEY, name TEXT)"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_projection_query_persistence_get_reader(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionStore(session_factory)

    class DTO:
        def __init__(self, id: str, name: str) -> None:
            self.id = id
            self.name = name

    class QueryPersistence(SQLAlchemyProjectionQueryPersistence[DTO, str]):
        collection = "query_test"

        def to_dto(self, doc: dict) -> DTO:
            return DTO(doc["id"], doc["name"])

    persistence = QueryPersistence(store)
    reader = persistence.get_reader()
    assert reader is store


@pytest.mark.asyncio
async def test_projection_spec_persistence_build_filter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionStore(session_factory)

    class SpecWithDict:
        def to_filter_dict(self) -> dict:
            return {"name": "Alice"}

    class DTO:
        pass

    class SpecPersistence(SQLAlchemyProjectionSpecPersistence[DTO]):
        collection = "query_test"

        def to_dto(self, doc: dict) -> DTO:
            return DTO()

    persistence = SpecPersistence(store)
    assert persistence.get_reader() is store
    filt = persistence.build_filter(SpecWithDict())
    assert filt == {"name": "Alice"}


@pytest.mark.asyncio
async def test_projection_spec_persistence_build_filter_no_attr_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionStore(session_factory)

    class DTO:
        pass

    class SpecPersistence(SQLAlchemyProjectionSpecPersistence[DTO]):
        collection = "query_test"

        def to_dto(self, doc: dict) -> DTO:
            return DTO()

    persistence = SpecPersistence(store)
    with pytest.raises(NotImplementedError):
        persistence.build_filter(object())


@pytest.mark.asyncio
async def test_projection_dual_persistence_get_reader_writer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionStore(session_factory)

    class DTO:
        def __init__(self, id: str, name: str) -> None:
            self.id = id
            self.name = name

    class DualPersistence(SQLAlchemyProjectionDualPersistence[DTO, str]):
        collection = "query_test"

        def to_dto(self, doc: dict) -> DTO:
            return DTO(doc["id"], doc["name"])

        def build_filter(self, criteria) -> dict:
            return getattr(criteria, "to_filter_dict", dict)()

    persistence = DualPersistence(store)
    assert persistence.get_reader() is store
    assert persistence.get_writer() is store

    class SpecWithDict:
        def to_filter_dict(self) -> dict:
            return {"status": "active"}

    assert persistence.build_filter(SpecWithDict()) == {"status": "active"}
