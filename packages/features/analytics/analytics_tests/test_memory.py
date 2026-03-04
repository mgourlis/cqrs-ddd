"""Tests for InMemorySink."""

from __future__ import annotations

import pytest

from cqrs_ddd_analytics.memory import InMemorySink
from cqrs_ddd_analytics.schema import AnalyticsSchema, ColumnDef, ColumnType


class TestInMemorySink:
    """Tests for InMemorySink."""

    @pytest.mark.asyncio
    async def test_push_batch(self) -> None:
        sink = InMemorySink()
        count = await sink.push_batch("orders", [{"id": "1"}, {"id": "2"}])
        assert count == 2
        assert sink.row_count("orders") == 2

    @pytest.mark.asyncio
    async def test_get_rows(self) -> None:
        sink = InMemorySink()
        await sink.push_batch("orders", [{"id": "1"}, {"id": "2"}])
        rows = sink.get_rows("orders")
        assert len(rows) == 2
        assert rows[0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_get_rows_empty(self) -> None:
        sink = InMemorySink()
        assert sink.get_rows("nonexistent") == []

    @pytest.mark.asyncio
    async def test_initialize_dataset(self) -> None:
        sink = InMemorySink()
        schema = AnalyticsSchema(
            table_name="metrics",
            columns=[ColumnDef(name="val", type=ColumnType.FLOAT)],
        )
        await sink.initialize_dataset(schema)
        assert sink.get_schema("metrics") is schema
        assert "metrics" in sink.tables

    @pytest.mark.asyncio
    async def test_clear_table(self) -> None:
        sink = InMemorySink()
        await sink.push_batch("t1", [{"a": 1}])
        await sink.push_batch("t2", [{"b": 2}])
        sink.clear("t1")
        assert sink.row_count("t1") == 0
        assert sink.row_count("t2") == 1

    @pytest.mark.asyncio
    async def test_clear_all(self) -> None:
        sink = InMemorySink()
        await sink.push_batch("t1", [{"a": 1}])
        await sink.push_batch("t2", [{"b": 2}])
        sink.clear()
        assert sink.row_count("t1") == 0
        assert sink.row_count("t2") == 0

    @pytest.mark.asyncio
    async def test_tables_property(self) -> None:
        sink = InMemorySink()
        await sink.push_batch("alpha", [{"x": 1}])
        await sink.push_batch("beta", [{"y": 2}])
        assert set(sink.tables) == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_multiple_batches_append(self) -> None:
        sink = InMemorySink()
        await sink.push_batch("t", [{"a": 1}])
        await sink.push_batch("t", [{"a": 2}])
        assert sink.row_count("t") == 2
