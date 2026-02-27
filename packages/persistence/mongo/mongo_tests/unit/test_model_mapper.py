"""Unit tests for MongoDBModelMapper — BSON preservation, round-trip, field mapping."""

from decimal import Decimal

import pytest
from pydantic import BaseModel

from cqrs_ddd_persistence_mongo.core.model_mapper import MongoDBModelMapper


class SimpleModel(BaseModel):
    id: str = ""
    name: str = ""
    value: int = 0


class ModelWithDecimal(BaseModel):
    id: str = ""
    amount: Decimal = Decimal("0")


class ModelWithNested(BaseModel):
    id: str = ""
    nested: dict | None = None


@pytest.fixture
def simple_mapper():
    return MongoDBModelMapper(SimpleModel)


@pytest.fixture
def decimal_mapper():
    return MongoDBModelMapper(ModelWithDecimal)


def test_to_doc_maps_id_to_underscore(simple_mapper):
    entity = SimpleModel(id="e1", name="x", value=1)
    doc = simple_mapper.to_doc(entity)
    assert doc["_id"] == "e1"
    assert "id" not in doc
    assert doc["name"] == "x"
    assert doc["value"] == 1


def test_from_doc_maps_underscore_to_id(simple_mapper):
    doc = {"_id": "e1", "name": "x", "value": 1}
    entity = simple_mapper.from_doc(doc)
    assert entity.id == "e1"
    assert entity.name == "x"
    assert entity.value == 1


def test_round_trip_simple(simple_mapper):
    entity = SimpleModel(id="e1", name="test", value=42)
    doc = simple_mapper.to_doc(entity)
    back = simple_mapper.from_doc(doc)
    assert back.id == entity.id
    assert back.name == entity.name
    assert back.value == entity.value


def test_decimal_serializes_to_decimal128(decimal_mapper):
    from bson.decimal128 import Decimal128

    entity = ModelWithDecimal(id="e1", amount=Decimal("123.45"))
    doc = decimal_mapper.to_doc(entity)
    assert isinstance(doc["amount"], Decimal128)
    assert str(doc["amount"]) == "123.45"


def test_decimal128_deserializes_to_decimal(decimal_mapper):
    from bson.decimal128 import Decimal128

    doc = {"_id": "e1", "amount": Decimal128("99.99")}
    entity = decimal_mapper.from_doc(doc)
    assert entity.amount == Decimal("99.99")


def test_round_trip_decimal(decimal_mapper):
    entity = ModelWithDecimal(id="e1", amount=Decimal("3.14"))
    doc = decimal_mapper.to_doc(entity)
    back = decimal_mapper.from_doc(doc)
    assert back.amount == entity.amount


def test_field_map_forward(simple_mapper):
    mapper = MongoDBModelMapper(SimpleModel, field_map={"name": "title"})
    entity = SimpleModel(id="e1", name="mapped", value=1)
    doc = mapper.to_doc(entity)
    assert doc.get("title") == "mapped"
    assert "name" not in doc


def test_field_map_reverse(simple_mapper):
    mapper = MongoDBModelMapper(SimpleModel, field_map={"name": "title"})
    doc = {"_id": "e1", "title": "mapped", "value": 1}
    entity = mapper.from_doc(doc)
    assert entity.name == "mapped"


def test_exclude_fields(simple_mapper):
    mapper = MongoDBModelMapper(SimpleModel, exclude_fields={"value"})
    entity = SimpleModel(id="e1", name="x", value=999)
    doc = mapper.to_doc(entity)
    assert "value" not in doc
    assert doc["_id"] == "e1"
    assert doc["name"] == "x"


class ModelWithPk(BaseModel):
    pk: str = ""
    name: str = ""


def test_custom_id_field():
    mapper = MongoDBModelMapper(ModelWithPk, id_field="pk")
    entity = ModelWithPk(pk="e1", name="x")
    doc = mapper.to_doc(entity)
    assert doc["_id"] == "e1"
    assert "pk" not in doc
    back = mapper.from_doc(doc)
    assert back.pk == "e1"
