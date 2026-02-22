"""Unit tests for serialization edge cases."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from bson import Decimal128
from pydantic import BaseModel, Field, field_validator

from cqrs_ddd_persistence_mongo.exceptions import MongoPersistenceError
from cqrs_ddd_persistence_mongo.serialization import (
    _deserialize_value,
    _serialize_value,
    model_from_doc,
    model_to_doc,
)


# Test Models
class SimpleModel(BaseModel):
    """Simple model for serialization tests."""

    id: str
    name: str
    value: int = 0


class ModelWithNone(BaseModel):
    """Model with optional None values."""

    id: str
    name: str | None = None
    value: int | None = None


class NestedModel(BaseModel):
    """Model with nested structures."""

    id: str
    data: dict[str, int]
    items: list[str]


class CustomTypeModel(BaseModel):
    """Model with custom types."""

    id: str
    timestamp: datetime
    decimal_val: Decimal
    uuid_val: str | None = None


class ModelWithValidation(BaseModel):
    """Model with validation."""

    id: str
    value: int

    @field_validator("value")
    @classmethod
    def validate_value(cls, v):
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v


# Phase 3, Step 11: Serialization Edge Cases Tests (6 tests)


class TestSerializationNoneValues:
    """Tests for handling None values in serialization."""

    def test_model_to_doc_with_none_values(self):
        """Test model_to_doc with None field values."""
        model = ModelWithNone(id="test-id", name=None, value=None)

        doc = model_to_doc(model)

        assert doc["_id"] == "test-id"
        assert "name" in doc
        assert "value" in doc
        # None values should be preserved
        assert doc.get("name") is None
        assert doc.get("value") is None

    def test_model_from_doc_with_none_values(self):
        """Test model_from_doc with None field values."""
        doc = {"_id": "test-id", "name": None, "value": None}

        model = model_from_doc(ModelWithNone, doc)

        assert model.id == "test-id"
        assert model.name is None
        assert model.value is None


class TestSerializationNestedModels:
    """Tests for handling nested structures in serialization."""

    def test_model_to_doc_with_nested_models(self):
        """Test model_to_doc with nested dict structures."""
        model = NestedModel(
            id="test-id",
            data={"key1": 1, "key2": 2},
            items=["item1", "item2"],
        )

        doc = model_to_doc(model)

        assert doc["_id"] == "test-id"
        assert "data" in doc
        assert "items" in doc
        assert doc["data"] == {"key1": 1, "key2": 2}
        assert doc["items"] == ["item1", "item2"]

    def test_model_from_doc_with_nested_structures(self):
        """Test model_from_doc with nested structures."""
        doc = {
            "_id": "test-id",
            "data": {"key1": 1, "key2": 2},
            "items": ["item1", "item2"],
        }

        model = model_from_doc(NestedModel, doc)

        assert model.id == "test-id"
        assert model.data == {"key1": 1, "key2": 2}
        assert model.items == ["item1", "item2"]


class TestSerializationMissingFields:
    """Tests for handling missing fields in deserialization."""

    def test_model_from_doc_with_missing_fields(self):
        """Test model_from_doc with missing optional fields."""
        # Document missing optional fields
        doc = {"_id": "test-id", "name": "Test"}

        model = model_from_doc(ModelWithNone, doc)

        assert model.id == "test-id"
        assert model.name == "Test"
        # value is optional with default None
        assert model.value is None


class TestSerializationInvalidTypes:
    """Tests for handling invalid types in serialization."""

    def test_model_from_doc_with_invalid_types(self):
        """Test model_from_doc with invalid types that fail validation."""
        # Invalid type for value (should be int)
        doc = {"_id": "test-id", "name": "Test", "value": "not-an-int"}

        with pytest.raises(MongoPersistenceError):
            model_from_doc(SimpleModel, doc)


class TestSerializationEmptyCollections:
    """Tests for handling empty collections in serialization."""

    def test_serialization_empty_collections(self):
        """Test serialization of empty lists and dicts."""
        model = NestedModel(id="test-id", data={}, items=[])

        # Test to_doc
        doc = model_to_doc(model)
        assert doc["data"] == {}
        assert doc["items"] == []

        # Test from_doc
        round_trip = model_from_doc(NestedModel, doc)
        assert round_trip.id == "test-id"
        assert round_trip.data == {}
        assert round_trip.items == []


class TestSerializationCustomTypes:
    """Tests for handling custom types in serialization."""

    def test_serialization_custom_types(self):
        """Test serialization of datetime, Decimal, and UUID types."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        decimal_val = Decimal("123.45")
        uuid_val = str(uuid4())

        model = CustomTypeModel(
            id="test-id",
            timestamp=timestamp,
            decimal_val=decimal_val,
            uuid_val=uuid_val,
        )

        # Test to_doc (Decimal must be stored as BSON Decimal128)
        doc = model_to_doc(model)
        assert doc["_id"] == "test-id"
        assert "timestamp" in doc
        assert "decimal_val" in doc
        assert isinstance(doc["decimal_val"], Decimal128)
        assert doc["uuid_val"] == uuid_val

        # Test from_doc (round trip)
        round_trip = model_from_doc(CustomTypeModel, doc)
        assert round_trip.id == "test-id"
        assert round_trip.timestamp == timestamp
        assert round_trip.decimal_val == decimal_val
        assert round_trip.uuid_val == uuid_val


class TestSerializationValueHelpers:
    """Tests for _serialize_value and _deserialize_value helpers."""

    def test_serialize_value_with_none(self):
        """Test _serialize_value with None."""
        result = _serialize_value(None)
        assert result is None

    def test_deserialize_value_with_none(self):
        """Test _deserialize_value with None."""
        result = _deserialize_value(None)
        assert result is None

    def test_serialize_value_with_list(self):
        """Test _serialize_value with list containing various types."""
        input_list = ["string", 123, None, {"key": "value"}]
        result = _serialize_value(input_list)

        assert isinstance(result, list)
        assert result[0] == "string"
        assert result[1] == 123
        assert result[2] is None
        assert result[3] == {"key": "value"}

    def test_deserialize_value_with_list(self):
        """Test _deserialize_value with list."""
        input_list = ["string", 123, None, {"key": "value"}]
        result = _deserialize_value(input_list)

        assert isinstance(result, list)
        assert result == input_list
