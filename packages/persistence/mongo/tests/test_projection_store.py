"""Unit tests for MongoProjectionStore."""

from __future__ import annotations

import pytest
from cqrs_ddd_persistence_mongo.exceptions import MongoPersistenceError
from cqrs_ddd_persistence_mongo.projection_store import MongoProjectionStore


@pytest.mark.asyncio
async def test_upsert_batch_requires_id() -> None:
    """Documents in upsert_batch must have an id field."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    store = MongoProjectionStore(conn)
    with pytest.raises(MongoPersistenceError, match="must have an id"):
        await store.upsert_batch("coll", [{"name": "no-id"}])
