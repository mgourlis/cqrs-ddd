"""Tests for ParquetFileSink."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from cqrs_ddd_analytics.parquet import ParquetFileSink
from cqrs_ddd_analytics.schema import AnalyticsSchema, ColumnDef, ColumnType


@pytest.fixture
def parquet_dir(tmp_path: Path) -> Path:
    return tmp_path / "analytics_data"


@pytest.fixture
def sink(parquet_dir: Path) -> ParquetFileSink:
    return ParquetFileSink(parquet_dir)


@pytest.fixture
def orders_schema() -> AnalyticsSchema:
    return AnalyticsSchema(
        table_name="orders",
        columns=[
            ColumnDef(name="event_date", type=ColumnType.STRING),
            ColumnDef(name="order_id", type=ColumnType.STRING),
            ColumnDef(name="total_amount", type=ColumnType.FLOAT),
        ],
        partition_key="event_date",
    )


@pytest.fixture
def flat_schema() -> AnalyticsSchema:
    return AnalyticsSchema(
        table_name="metrics",
        columns=[
            ColumnDef(name="name", type=ColumnType.STRING),
            ColumnDef(name="value", type=ColumnType.FLOAT),
        ],
    )


class TestParquetFileSink:
    """Tests for ParquetFileSink."""

    @pytest.mark.asyncio
    async def test_initialize_creates_directory(
        self, sink: ParquetFileSink, orders_schema: AnalyticsSchema, parquet_dir: Path
    ) -> None:
        await sink.initialize_dataset(orders_schema)
        assert (parquet_dir / "orders").is_dir()

    @pytest.mark.asyncio
    async def test_push_batch_writes_parquet(
        self, sink: ParquetFileSink, flat_schema: AnalyticsSchema, parquet_dir: Path
    ) -> None:
        await sink.initialize_dataset(flat_schema)
        rows: list[dict[str, object]] = [
            {"name": "cpu", "value": 85.0},
            {"name": "mem", "value": 72.5},
        ]
        count = await sink.push_batch("metrics", rows)
        assert count == 2

        # Verify parquet file exists
        parquet_files = list((parquet_dir / "metrics").glob("*.parquet"))
        assert len(parquet_files) == 1

        # Verify content
        table = pq.read_table(parquet_files[0])
        assert table.num_rows == 2
        assert set(table.column_names) == {"name", "value"}

    @pytest.mark.asyncio
    async def test_push_batch_partitioned(
        self,
        sink: ParquetFileSink,
        orders_schema: AnalyticsSchema,
        parquet_dir: Path,
    ) -> None:
        await sink.initialize_dataset(orders_schema)
        rows: list[dict[str, object]] = [
            {"event_date": "2024-01-01", "order_id": "o1", "total_amount": 10.0},
            {"event_date": "2024-01-01", "order_id": "o2", "total_amount": 20.0},
            {"event_date": "2024-01-02", "order_id": "o3", "total_amount": 30.0},
        ]
        count = await sink.push_batch("orders", rows)
        assert count == 3

        # Verify partition directories
        orders_dir = parquet_dir / "orders"
        partition_dirs = sorted(d.name for d in orders_dir.iterdir() if d.is_dir())
        assert "event_date=2024-01-01" in partition_dirs
        assert "event_date=2024-01-02" in partition_dirs

        # Check row counts per partition
        p1_files = list((orders_dir / "event_date=2024-01-01").glob("*.parquet"))
        p2_files = list((orders_dir / "event_date=2024-01-02").glob("*.parquet"))
        assert len(p1_files) == 1
        assert len(p2_files) == 1

        # Check the file's internal schema (not reconstructed partitions)
        p1_meta = pq.read_metadata(p1_files[0])
        assert p1_meta.num_rows == 2
        file_schema_names = pq.read_schema(p1_files[0]).names
        # Partition column should be excluded from the physical file
        assert "event_date" not in file_schema_names
        assert "order_id" in file_schema_names

        p2_meta = pq.read_metadata(p2_files[0])
        assert p2_meta.num_rows == 1

    @pytest.mark.asyncio
    async def test_push_empty_batch(
        self, sink: ParquetFileSink, flat_schema: AnalyticsSchema
    ) -> None:
        await sink.initialize_dataset(flat_schema)
        count = await sink.push_batch("metrics", [])
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_temp_files_remain(
        self, sink: ParquetFileSink, flat_schema: AnalyticsSchema, parquet_dir: Path
    ) -> None:
        await sink.initialize_dataset(flat_schema)
        await sink.push_batch("metrics", [{"name": "x", "value": 1.0}])
        tmp_files = list((parquet_dir / "metrics").glob("*.tmp"))
        assert len(tmp_files) == 0

    @pytest.mark.asyncio
    async def test_multiple_batches_create_separate_files(
        self, sink: ParquetFileSink, flat_schema: AnalyticsSchema, parquet_dir: Path
    ) -> None:
        await sink.initialize_dataset(flat_schema)
        await sink.push_batch("metrics", [{"name": "a", "value": 1.0}])
        await sink.push_batch("metrics", [{"name": "b", "value": 2.0}])
        parquet_files = list((parquet_dir / "metrics").glob("*.parquet"))
        assert len(parquet_files) == 2

    @pytest.mark.asyncio
    async def test_push_without_schema(
        self, sink: ParquetFileSink, parquet_dir: Path
    ) -> None:
        """Pushing to a table without prior initialize_dataset still writes."""
        (parquet_dir / "adhoc").mkdir(parents=True, exist_ok=True)
        # No schema registered — inferred from data
        count = await sink.push_batch("adhoc", [{"key": "val", "num": 42}])
        assert count == 1

    @pytest.mark.asyncio
    async def test_atomic_write_no_partial_reads(
        self, sink: ParquetFileSink, flat_schema: AnalyticsSchema, parquet_dir: Path
    ) -> None:
        """Verify that only .parquet files exist (no hidden .tmp)."""
        await sink.initialize_dataset(flat_schema)
        for i in range(5):
            await sink.push_batch("metrics", [{"name": f"m{i}", "value": float(i)}])
        all_files = list((parquet_dir / "metrics").iterdir())
        for f in all_files:
            assert f.suffix == ".parquet"
            assert not f.name.startswith(".")
