"""Unit tests for BSON serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from cqrs_ddd_persistence_mongo.serialization import model_from_doc, model_to_doc
from pydantic import BaseModel


class SampleModel(BaseModel):
    id: str
    name: str
    amount: Decimal
    created_at: datetime


def test_model_to_doc_id_mapping() -> None:
    m = SampleModel(
        id="x-1",
        name="test",
        amount=Decimal("10.5"),
        created_at=datetime.now(timezone.utc),
    )
    doc = model_to_doc(m, use_id_field="id")
    assert doc["_id"] == "x-1"
    assert "id" not in doc


def test_model_from_doc_id_mapping() -> None:
    doc = {
        "_id": "x-1",
        "name": "test",
        "amount": "10.5",
        "created_at": "2025-01-01T12:00:00Z",
    }
    m = model_from_doc(SampleModel, doc, id_field="id")
    assert m.id == "x-1"
    assert m.name == "test"


def test_roundtrip() -> None:
    m = SampleModel(
        id="r-1",
        name="round",
        amount=Decimal("99.99"),
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    doc = model_to_doc(m, use_id_field="id")
    m2 = model_from_doc(SampleModel, doc, id_field="id")
    assert m2.id == m.id
    assert m2.name == m.name
    assert m2.amount == m.amount
    assert m2.created_at == m.created_at
