"""Unit tests for MongoConnectionManager (without real MongoDB)."""

from __future__ import annotations

import pytest
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_persistence_mongo.exceptions import MongoConnectionError


def test_client_raises_before_connect() -> None:
    mgr = MongoConnectionManager(url="mongodb://localhost:27017")
    with pytest.raises(MongoConnectionError, match="Not connected"):
        _ = mgr.client


def test_close_idempotent() -> None:
    mgr = MongoConnectionManager()
    mgr.close()  # sync; idempotent when not connected
    mgr.close()
