"""Tests for ProjectionSchema and ProjectionSchemaRegistry."""

from __future__ import annotations

import json
import tempfile

from sqlalchemy import Column, Integer, String

from cqrs_ddd_advanced_core.projections.schema import (
    PROJECTION_VERSION_COLUMNS,
    ProjectionRelationship,
    ProjectionSchema,
    ProjectionSchemaRegistry,
    RelationshipType,
    create_schema,
)


def test_create_schema_adds_version_columns():
    schema = create_schema(
        "order_summaries",
        columns=[
            Column("id", String(255), primary_key=True),
            Column("total", Integer(), nullable=False),
        ],
    )
    assert schema.name == "order_summaries"
    col_names = [c.name for c in schema.columns]
    assert "id" in col_names
    assert "total" in col_names
    assert "_version" in col_names
    assert "_last_event_id" in col_names
    assert "_last_event_position" in col_names


def test_schema_to_json_round_trip():
    schema = create_schema(
        "test_table",
        columns=[
            Column("id", String(255), primary_key=True),
            Column("name", String(255)),
        ],
    )
    data = schema.to_json()
    assert data["name"] == "test_table"
    loaded = ProjectionSchema.from_json(data)
    assert loaded.name == schema.name
    assert len(loaded.columns) == len(schema.columns)


def test_registry_register_and_get():
    registry = ProjectionSchemaRegistry()
    schema = ProjectionSchema(
        name="orders", columns=[Column("id", String(255), primary_key=True)]
    )
    registry.register(schema)
    assert registry.get("orders") is schema
    assert registry.get("missing") is None


def test_registry_initialization_order():
    registry = ProjectionSchemaRegistry()
    registry.register(
        ProjectionSchema(
            name="orders",
            columns=[Column("id", String(255), primary_key=True)],
            relationships=[],
        )
    )
    registry.register(
        ProjectionSchema(
            name="items",
            columns=[Column("id", String(255), primary_key=True)],
            relationships=[
                ProjectionRelationship(
                    name="order",
                    type=RelationshipType.MANY_TO_ONE,
                    target_schema="orders",
                    foreign_key="order_id",
                )
            ],
        )
    )
    order = registry.get_initialization_order()
    # orders should come before items (dependency)
    assert order.index("orders") < order.index("items")


def test_projection_version_columns_defined():
    assert len(PROJECTION_VERSION_COLUMNS) >= 3
    names = [c.name for c in PROJECTION_VERSION_COLUMNS]
    assert "_version" in names
    assert "_last_event_id" in names


def test_schema_save_and_load_file():
    registry = ProjectionSchemaRegistry()
    schema = create_schema(
        "file_test", columns=[Column("id", String(255), primary_key=True)]
    )
    registry.register(schema)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        registry.save_to_file(path)
        with open(path) as fp:
            data = json.load(fp)
        assert "schemas" in data
        assert "initialization_order" in data
        loaded = ProjectionSchemaRegistry.load_from_file(path)
        assert loaded.get("file_test") is not None
    finally:
        import os

        os.unlink(path)
