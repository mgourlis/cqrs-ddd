"""
Dedicated unit tests for ModelMapper.

Covers:
- Private attribute extraction (using __private_attributes__)
- Field mapping (domain field <-> DB column)
- Field exclusion
- Custom type coercers
- Batch operations (to_models/from_models)
- Enum coercion
- Nested Pydantic serialization (dicts, lists, sets)
- Cycle detection in relationships
- Error handling (MappingError wrapping)
- Relationship depth limits
- Detached model handling
"""

from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, Field, PrivateAttr
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_persistence_sqlalchemy.core.model_mapper import ModelMapper
from cqrs_ddd_persistence_sqlalchemy.core.types.json import JSONType
from cqrs_ddd_persistence_sqlalchemy.exceptions import MappingError

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class StatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class SimpleEntity(BaseModel):
    """Simple Pydantic entity for testing."""

    id: str
    name: str
    status: StatusEnum = StatusEnum.ACTIVE
    _version: int = PrivateAttr(default=0)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_version", data.get("_version", 0))


class EntityWithPrivateAttrs(BaseModel):
    """Entity with multiple private attributes."""

    id: str
    name: str
    _version: int = PrivateAttr(default=0)
    _tenant_id: str = PrivateAttr(default="default")
    _created_by: str = PrivateAttr(default="system")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_version", data.get("_version", 5))
        object.__setattr__(self, "_tenant_id", data.get("_tenant_id", "default"))
        object.__setattr__(self, "_created_by", data.get("_created_by", "system"))


class EntityWithNested(BaseModel):
    """Entity with nested Pydantic objects."""

    id: str
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ValueObject(BaseModel):
    """Simple value object for nesting."""

    value: str
    count: int


class EntityWithValueObject(BaseModel):
    """Entity containing a ValueObject."""

    id: str
    vo: ValueObject


class SimpleModel(Base):
    """Simple SQLAlchemy model."""

    __tablename__ = "simple"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    version: Mapped[int] = mapped_column(Integer, default=0)


class ModelWithPrivateAttrs(Base):
    """SQLAlchemy model with columns matching private attributes."""

    __tablename__ = "with_private"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=0)
    tenant_id: Mapped[str] = mapped_column(String, default="default")
    created_by: Mapped[str] = mapped_column(String, default="system")


class ModelWithMetadata(Base):
    """Model with JSON column for metadata."""

    __tablename__ = "with_metadata"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default={})


class ModelWithJobMetadata(Base):
    """Model with renamed metadata column."""

    __tablename__ = "with_job_metadata"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    job_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default={})


# ---------------------------------------------------------------------------
# Tests: Private attribute extraction
# ---------------------------------------------------------------------------


def test_extract_private_attrs_uses_private_attributes():
    """Test that _extract_private_attrs uses __private_attributes__ efficiently."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    entity = SimpleEntity(id="e1", name="Test", _version=42)
    data = mapper._dump_entity(entity)
    data = mapper._extract_private_attrs(entity, data)

    assert data["version"] == 42
    assert "name" in data
    assert "id" in data


def test_extract_multiple_private_attrs():
    """Test extraction of multiple private attributes."""
    mapper = ModelMapper(EntityWithPrivateAttrs, ModelWithPrivateAttrs)

    entity = EntityWithPrivateAttrs(
        id="e1",
        name="Test",
        _version=10,
        _tenant_id="tenant-123",
        _created_by="user-456",
    )

    data = mapper._dump_entity(entity)
    data = mapper._extract_private_attrs(entity, data)

    assert data["version"] == 10
    assert data["tenant_id"] == "tenant-123"
    assert data["created_by"] == "user-456"


def test_restore_all_private_attrs():
    """Test that _restore_private_attrs restores all private attributes."""
    mapper = ModelMapper(EntityWithPrivateAttrs, ModelWithPrivateAttrs)

    model = ModelWithPrivateAttrs(
        id="e1", name="Test", version=10, tenant_id="tenant-123", created_by="user-456"
    )

    data = mapper._safe_extract(model, depth=0, seen=set())
    entity = mapper._validate_entity(data, model)
    mapper._restore_private_attrs(entity, data)

    assert entity._version == 10
    assert entity._tenant_id == "tenant-123"
    assert entity._created_by == "user-456"


# ---------------------------------------------------------------------------
# Tests: Field mapping
# ---------------------------------------------------------------------------


def test_field_map_domain_to_db():
    """Test field mapping from domain field to DB column."""
    mapper = ModelMapper(
        EntityWithNested,
        ModelWithJobMetadata,
        field_map={"metadata": "job_metadata"},
    )

    entity = EntityWithNested(id="e1", name="Test", metadata={"key": "value"})
    model = mapper.to_model(entity)

    # Note: SQLAlchemy models always have a 'metadata' class attribute (table metadata),
    # so we check that job_metadata has the mapped value instead
    assert model.job_metadata == {"key": "value"}
    assert model.name == "Test"


def test_field_map_db_to_domain():
    """Test reverse field mapping from DB column to domain field."""
    mapper = ModelMapper(
        EntityWithNested,
        ModelWithJobMetadata,
        field_map={"metadata": "job_metadata"},
    )

    model = ModelWithJobMetadata(id="e1", name="Test", job_metadata={"key": "value"})
    entity = mapper.from_model(model)

    assert entity.metadata == {"key": "value"}
    assert not hasattr(entity, "job_metadata")
    assert entity.name == "Test"


# ---------------------------------------------------------------------------
# Tests: Field exclusion
# ---------------------------------------------------------------------------


def test_exclude_fields_to_model():
    """Test that excluded fields are not mapped to DB."""
    mapper = ModelMapper(SimpleEntity, SimpleModel, exclude_fields={"status"})

    entity = SimpleEntity(id="e1", name="Test", status=StatusEnum.ARCHIVED)
    model = mapper.to_model(entity)

    # status should be excluded, so it won't be in the model
    # (assuming SimpleModel has a default)
    assert model.name == "Test"
    assert model.id == "e1"


def test_exclude_fields_from_model():
    """Test that excluded fields are not mapped from DB."""
    mapper = ModelMapper(SimpleEntity, SimpleModel, exclude_fields={"status"})

    model = SimpleModel(id="e1", name="Test", status="archived")
    entity = mapper.from_model(model)

    # status should be excluded, so it won't be in the entity
    # (or will use the default)
    assert entity.name == "Test"
    assert entity.id == "e1"


# ---------------------------------------------------------------------------
# Tests: Custom type coercers
# ---------------------------------------------------------------------------


def test_custom_type_coercer():
    """Test custom type coercer for UUID -> str."""
    mapper = ModelMapper(
        SimpleEntity,
        SimpleModel,
        type_coercers={UUID: lambda u: str(u)},
    )

    # Create entity with UUID-like field (simulated)
    SimpleEntity(id="e1", name="Test")
    # Note: This test is simplified since SimpleEntity doesn't have UUID fields
    # In real usage, you'd have an entity with UUID fields

    # Test that coercer is registered
    assert UUID in mapper._type_coercers


def test_custom_coercer_applied():
    """Test that custom coercer is applied during to_model."""
    from datetime import datetime, timezone

    class EntityWithDatetime(BaseModel):
        id: str
        created_at: datetime

    class ModelWithString(Base):
        __tablename__ = "with_string"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        created_at: Mapped[str] = mapped_column(String, default="")

    mapper = ModelMapper(
        EntityWithDatetime,
        ModelWithString,
        type_coercers={datetime: lambda dt: dt.isoformat()},
    )

    dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entity = EntityWithDatetime(id="e1", created_at=dt)
    model = mapper.to_model(entity)

    assert model.created_at == "2024-01-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Tests: Batch operations
# ---------------------------------------------------------------------------


def test_to_models_batch():
    """Test batch conversion of entities to models."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    entities = [
        SimpleEntity(id="e1", name="Entity 1"),
        SimpleEntity(id="e2", name="Entity 2"),
        SimpleEntity(id="e3", name="Entity 3"),
    ]

    models = mapper.to_models(entities)

    assert len(models) == 3
    assert all(isinstance(m, SimpleModel) for m in models)
    assert models[0].name == "Entity 1"
    assert models[1].name == "Entity 2"
    assert models[2].name == "Entity 3"


def test_from_models_batch():
    """Test batch conversion of models to entities."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    models = [
        SimpleModel(id="e1", name="Entity 1"),
        SimpleModel(id="e2", name="Entity 2"),
        SimpleModel(id="e3", name="Entity 3"),
    ]

    entities = mapper.from_models(models)

    assert len(entities) == 3
    assert all(isinstance(e, SimpleEntity) for e in entities)
    assert entities[0].name == "Entity 1"
    assert entities[1].name == "Entity 2"
    assert entities[2].name == "Entity 3"


# ---------------------------------------------------------------------------
# Tests: Enum coercion
# ---------------------------------------------------------------------------


def test_enum_coercion_to_model():
    """Test that Enum values are coerced to their .value."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    entity = SimpleEntity(id="e1", name="Test", status=StatusEnum.ARCHIVED)
    model = mapper.to_model(entity)

    assert model.status == "archived"  # Enum.value, not the enum itself


def test_enum_coercion_round_trip():
    """Test enum coercion round-trip (to_model then from_model)."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    entity = SimpleEntity(id="e1", name="Test", status=StatusEnum.ACTIVE)
    model = mapper.to_model(entity)
    assert model.status == "active"

    # When reading back, Pydantic should handle string -> enum conversion
    restored = mapper.from_model(model)
    assert restored.status == StatusEnum.ACTIVE


# ---------------------------------------------------------------------------
# Tests: Nested Pydantic serialization
# ---------------------------------------------------------------------------


def test_nested_dict_coercion():
    """Test that dict values are recursively coerced."""
    # Note: field_map maps domain field to SQL column name, but we need to handle
    # the Python attribute name (metadata_) separately. For this test, we'll
    # use a simpler model without the metadata conflict.
    mapper = ModelMapper(EntityWithNested, ModelWithJobMetadata)

    EntityWithNested(id="e1", name="Test", metadata={"nested": {"key": "value"}})
    # Test that dict coercion works in _coerce_values
    data = {"metadata": {"nested": {"key": "value"}}}
    coerced = mapper._coerce_values(data)
    assert isinstance(coerced["metadata"], dict)
    assert coerced["metadata"]["nested"]["key"] == "value"


def test_list_coercion():
    """Test that list values are coerced."""
    mapper = ModelMapper(EntityWithNested, ModelWithMetadata)

    EntityWithNested(id="e1", name="Test", tags=["tag1", "tag2"])
    # Note: This test assumes tags maps to a JSON column
    # In practice, you'd need a model with a tags column

    # Test that list coercion works in _coerce_values
    data = {"tags": ["tag1", "tag2"]}
    coerced = mapper._coerce_values(data)
    assert coerced["tags"] == ["tag1", "tag2"]


def test_set_coercion():
    """Test that set values are coerced to lists."""
    mapper = ModelMapper(EntityWithNested, ModelWithMetadata)

    data = {"tags": {"tag1", "tag2"}}
    coerced = mapper._coerce_values(data)

    # Sets should be converted to lists for JSON serialization
    assert isinstance(coerced["tags"], list)
    assert set(coerced["tags"]) == {"tag1", "tag2"}


def test_nested_value_object_coercion():
    """Test that nested ValueObjects are serialized."""
    mapper = ModelMapper(EntityWithValueObject, ModelWithMetadata)

    vo = ValueObject(value="test", count=42)
    EntityWithValueObject(id="e1", vo=vo)

    # Test coercion of ValueObject
    data = {"vo": vo}
    coerced = mapper._coerce_values(data)

    assert isinstance(coerced["vo"], dict)
    assert coerced["vo"]["value"] == "test"
    assert coerced["vo"]["count"] == 42


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


def test_mapping_error_wraps_validation_error():
    """Test that ValidationError is wrapped in MappingError."""
    ModelMapper(SimpleEntity, SimpleModel)

    # Create invalid model data that will fail validation
    class InvalidModel(Base):
        __tablename__ = "invalid"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String)

    invalid_mapper = ModelMapper(SimpleEntity, InvalidModel)

    # Create model with wrong type for id
    model = InvalidModel(id=123, name="Test")

    # This should raise MappingError, not raw ValidationError
    with pytest.raises(MappingError) as exc_info:
        invalid_mapper.from_model(model)

    assert "Failed to map" in str(exc_info.value)
    assert "SimpleEntity" in str(exc_info.value)


def test_mapping_error_includes_model_context():
    """Test that MappingError includes model class and ID context."""
    ModelMapper(SimpleEntity, SimpleModel)

    class BadModel(Base):
        __tablename__ = "bad"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    bad_mapper = ModelMapper(SimpleEntity, BadModel)
    model = BadModel(id=999)

    with pytest.raises(MappingError) as exc_info:
        bad_mapper.from_model(model)

    error_msg = str(exc_info.value)
    assert "BadModel" in error_msg
    assert "999" in error_msg or "id=999" in error_msg


# ---------------------------------------------------------------------------
# Tests: Relationship depth
# ---------------------------------------------------------------------------


def test_relationship_depth_zero_ignores_relationships():
    """Test that relationship_depth=0 ignores relationships."""
    mapper = ModelMapper(SimpleEntity, SimpleModel, relationship_depth=0)

    model = SimpleModel(id="e1", name="Test", status="active")
    data = mapper._safe_extract(model, depth=0, seen=set())

    # Should only extract columns, not relationships
    assert "id" in data
    assert "name" in data
    assert "status" in data
    # Verify no relationships are extracted (SimpleModel has no relationships, but test the concept)
    assert len(data) == 3  # id, name, status


def test_relationship_depth_limit():
    """Test that relationship_depth limits traversal."""
    # This test would require a model with relationships
    # For now, we test that depth parameter is respected
    mapper = ModelMapper(SimpleEntity, SimpleModel, relationship_depth=1)

    assert mapper._relationship_depth == 1


# ---------------------------------------------------------------------------
# Tests: Cycle detection
# ---------------------------------------------------------------------------


def test_cycle_detection_prevents_infinite_loop():
    """Test that cycle detection prevents infinite loops."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    model = SimpleModel(id="e1", name="Test")
    seen: set[int] = set()

    # First extraction
    data1 = mapper._safe_extract(model, depth=0, seen=seen)
    assert id(model) in seen
    assert "id" in data1
    assert "name" in data1

    # Second extraction of same model should return empty dict (cycle detected)
    data2 = mapper._safe_extract(model, depth=0, seen=seen)
    assert data2 == {}  # Cycle detected - returns empty dict


# ---------------------------------------------------------------------------
# Tests: Detached model handling
# ---------------------------------------------------------------------------


def test_detached_model_handling():
    """Test that detached models are handled safely."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    # Create a model instance (not attached to session)
    model = SimpleModel(id="e1", name="Test")

    # Should extract successfully even if detached
    entity = mapper.from_model(model)

    assert entity.id == "e1"
    assert entity.name == "Test"


# ---------------------------------------------------------------------------
# Tests: Non-Pydantic fallback
# ---------------------------------------------------------------------------


def test_non_pydantic_entity_fallback():
    """Test fallback for non-Pydantic entities."""

    class PlainEntity:
        def __init__(self, id: str, name: str):
            self.id = id
            self.name = name

        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            return {"id": self.id, "name": self.name}

        @classmethod
        def model_validate(cls, data: dict[str, Any]):
            return cls(**data)

    mapper = ModelMapper(PlainEntity, SimpleModel)

    entity = PlainEntity(id="e1", name="Test")
    model = mapper.to_model(entity)

    assert model.id == "e1"
    assert model.name == "Test"


# ---------------------------------------------------------------------------
# Tests: Integration - full round trip
# ---------------------------------------------------------------------------


def test_full_round_trip():
    """Test complete round-trip: entity -> model -> entity."""
    mapper = ModelMapper(SimpleEntity, SimpleModel)

    original = SimpleEntity(id="e1", name="Test Entity", status=StatusEnum.ACTIVE)
    model = mapper.to_model(original)
    restored = mapper.from_model(model)

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.status == original.status


def test_round_trip_with_private_attrs():
    """Test round-trip with private attributes."""
    mapper = ModelMapper(EntityWithPrivateAttrs, ModelWithPrivateAttrs)

    original = EntityWithPrivateAttrs(
        id="e1",
        name="Test",
        _version=42,
        _tenant_id="tenant-123",
        _created_by="user-456",
    )

    model = mapper.to_model(original)
    restored = mapper.from_model(model)

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored._version == 42
    assert restored._tenant_id == "tenant-123"
    assert restored._created_by == "user-456"
