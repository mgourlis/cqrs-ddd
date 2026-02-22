"""Integration tests for MongoDB (require testcontainers)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")

from pydantic import BaseModel

from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_persistence_mongo.core.repository import MongoRepository


class ReadModel(BaseModel):
    id: str
    name: str
    value: int


@pytest.fixture(scope="module")
def mongo_url() -> str:
    from testcontainers.mongodb import MongoDbContainer

    with MongoDbContainer("mongo:6") as mongo:
        yield mongo.get_connection_url()


@pytest.mark.asyncio
async def test_connection_health(mongo_url: str) -> None:
    mgr = MongoConnectionManager(url=mongo_url)
    await mgr.connect()
    assert await mgr.health_check() is True
    mgr.close()


@pytest.mark.asyncio
async def test_repository_crud(mongo_url: str) -> None:
    mgr = MongoConnectionManager(url=mongo_url)
    await mgr.connect()
    repo = MongoRepository(mgr, "test_coll", ReadModel, database="test_db")
    try:
        e = ReadModel(id="1", name="a", value=10)
        out_id = await repo.add(e)
        assert out_id == "1"
        got = await repo.get("1")
        assert got is not None
        assert got.name == "a"
        await repo.delete("1")
        assert await repo.get("1") is None
    finally:
        mgr.close()
