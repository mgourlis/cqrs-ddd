"""Tests for AnalyticsSchema and ColumnDef."""

from __future__ import annotations

import pyarrow as pa
import pytest

from cqrs_ddd_analytics.exceptions import SchemaError
from cqrs_ddd_analytics.schema import AnalyticsSchema, ColumnDef, ColumnType


class TestColumnDef:
    """Tests for ColumnDef."""

    def test_to_pyarrow_field_string(self) -> None:
        col = ColumnDef(name="name", type=ColumnType.STRING)
        field = col.to_pyarrow_field()
        assert field.name == "name"
        assert field.type == pa.string()
        assert field.nullable is True

    def test_to_pyarrow_field_int(self) -> None:
        col = ColumnDef(name="count", type=ColumnType.INT, nullable=False)
        field = col.to_pyarrow_field()
        assert field.type == pa.int64()
        assert field.nullable is False

    def test_to_pyarrow_field_float(self) -> None:
        col = ColumnDef(name="amount", type=ColumnType.FLOAT)
        assert col.to_pyarrow_field().type == pa.float64()

    def test_to_pyarrow_field_datetime(self) -> None:
        col = ColumnDef(name="ts", type=ColumnType.DATETIME)
        assert col.to_pyarrow_field().type == pa.timestamp("us", tz="UTC")

    def test_to_pyarrow_field_bool(self) -> None:
        col = ColumnDef(name="active", type=ColumnType.BOOL)
        assert col.to_pyarrow_field().type == pa.bool_()

    def test_to_pyarrow_field_json(self) -> None:
        col = ColumnDef(name="meta", type=ColumnType.JSON)
        assert col.to_pyarrow_field().type == pa.string()

    def test_to_pyarrow_field_geometry(self) -> None:
        col = ColumnDef(name="location", type=ColumnType.GEOMETRY)
        assert col.to_pyarrow_field().type == pa.binary()


class TestAnalyticsSchema:
    """Tests for AnalyticsSchema."""

    def test_empty_table_name_raises(self) -> None:
        with pytest.raises(SchemaError, match="table_name must not be empty"):
            AnalyticsSchema(table_name="")

    def test_partition_key_not_in_columns_raises(self) -> None:
        with pytest.raises(SchemaError, match="partition_key 'missing_col'"):
            AnalyticsSchema(
                table_name="orders",
                columns=[ColumnDef(name="id", type=ColumnType.STRING)],
                partition_key="missing_col",
            )

    def test_valid_schema_with_partition(self) -> None:
        schema = AnalyticsSchema(
            table_name="orders",
            columns=[
                ColumnDef(name="event_date", type=ColumnType.STRING),
                ColumnDef(name="order_id", type=ColumnType.STRING),
            ],
            partition_key="event_date",
        )
        assert schema.table_name == "orders"
        assert schema.partition_key == "event_date"
        assert schema.column_names == ["event_date", "order_id"]

    def test_to_pyarrow_schema(self) -> None:
        schema = AnalyticsSchema(
            table_name="metrics",
            columns=[
                ColumnDef(name="name", type=ColumnType.STRING),
                ColumnDef(name="value", type=ColumnType.FLOAT),
            ],
        )
        pa_schema = schema.to_pyarrow_schema()
        assert len(pa_schema) == 2
        assert pa_schema.field("name").type == pa.string()
        assert pa_schema.field("value").type == pa.float64()

    def test_to_pyarrow_schema_with_geometry_metadata(self) -> None:
        import json

        schema = AnalyticsSchema(
            table_name="geo",
            columns=[
                ColumnDef(name="id", type=ColumnType.STRING),
                ColumnDef(name="location", type=ColumnType.GEOMETRY),
            ],
        )
        pa_schema = schema.to_pyarrow_schema()
        assert pa_schema.metadata is not None
        geo_meta = json.loads(pa_schema.metadata[b"geo"])
        assert geo_meta["primary_column"] == "location"
        assert geo_meta["columns"]["location"]["encoding"] == "WKB"

    def test_schema_without_partition_key(self) -> None:
        schema = AnalyticsSchema(
            table_name="events",
            columns=[ColumnDef(name="id", type=ColumnType.STRING)],
        )
        assert schema.partition_key is None
