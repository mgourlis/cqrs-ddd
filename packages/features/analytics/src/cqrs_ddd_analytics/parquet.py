"""ParquetFileSink — IAnalyticsSink writing partitioned Parquet with atomic renames."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa

from .exceptions import SchemaError, SinkConnectionError
from .ports import IAnalyticsSink

if TYPE_CHECKING:
    from .schema import AnalyticsSchema

logger = logging.getLogger(__name__)


class ParquetFileSink(IAnalyticsSink):
    """Write analytics rows to partitioned Parquet files on disk.

    Each ``push_batch`` call creates a new ``.parquet`` file in the target
    dataset directory.  Files are written atomically: data is first flushed
    to a hidden ``.tmp`` file, then renamed via :func:`os.replace` to prevent
    downstream readers (e.g. DuckDB) from seeing partial writes.

    If a ``partition_key`` is configured in the schema, rows are grouped
    by partition value and written to subdirectories named
    ``<partition_key>=<value>/``.

    Args:
        base_path: Root directory where Parquet datasets are stored.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)
        self._schemas: dict[str, AnalyticsSchema] = {}

    # ── IAnalyticsSink ───────────────────────────────────────────

    async def initialize_dataset(self, schema: AnalyticsSchema) -> None:
        """Ensure the dataset directory exists.

        Stores the schema for later use during ``push_batch``.
        """
        dataset_dir = self._base_path / schema.table_name
        try:
            dataset_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SinkConnectionError(
                f"Cannot create dataset directory '{dataset_dir}': {exc}"
            ) from exc
        self._schemas[schema.table_name] = schema
        logger.info("Initialized dataset '%s' at %s", schema.table_name, dataset_dir)

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _group_by_partition(
        rows: list[dict[str, object]], partition_key: str | None
    ) -> dict[str | None, list[dict[str, object]]]:
        """Group rows by partition value (or None for un-partitioned)."""
        partitions: dict[str | None, list[dict[str, object]]] = {}
        for row in rows:
            pval = (
                str(row[partition_key])
                if (partition_key and partition_key in row)
                else None
            )
            partitions.setdefault(pval, []).append(row)
        return partitions

    def _build_pa_table(
        self,
        rows: list[dict[str, object]],
        schema: AnalyticsSchema | None,
        partition_key: str | None,
        partition_value: str | None,
    ) -> pa.Table:
        if schema is None:
            return pa.Table.from_pylist(rows)

        pa_schema = schema.to_pyarrow_schema()
        strip_partition = partition_key and partition_value is not None
        if strip_partition:
            field_idx = pa_schema.get_field_index(partition_key)
            if field_idx >= 0:
                pa_schema = pa_schema.remove(field_idx)
                rows = [
                    {k: v for k, v in r.items() if k != partition_key} for r in rows
                ]

        try:
            return pa.Table.from_pylist(rows, schema=pa_schema)
        except Exception as exc:
            raise SchemaError(
                f"Failed to convert rows to PyArrow table for "
                f"'{schema.table_name}': {exc}"
            ) from exc

    @staticmethod
    def _atomic_write(pa_table: pa.Table, target_dir: Path, batch_id: str) -> Path:
        import pyarrow.parquet as pq

        tmp_file = target_dir / f".batch_{batch_id}.tmp"
        final_file = target_dir / f"batch_{batch_id}.parquet"
        try:
            pq.write_table(pa_table, str(tmp_file))
            tmp_file.replace(final_file)
        except OSError as exc:
            tmp_file.unlink(missing_ok=True)
            raise SinkConnectionError(
                f"Failed to write Parquet file '{final_file}': {exc}"
            ) from exc
        return final_file

    def _write_partition(
        self,
        _table: str,
        partition_key: str | None,
        partition_value: str | None,
        partition_rows: list[dict[str, object]],
        dataset_dir: Path,
        schema: AnalyticsSchema | None,
    ) -> int:
        """Write one partition batch; return the number of rows written."""
        target_dir = (
            dataset_dir / f"{partition_key}={partition_value}"
            if (partition_value is not None and partition_key is not None)
            else dataset_dir
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        pa_table = self._build_pa_table(
            partition_rows, schema, partition_key, partition_value
        )
        batch_id = uuid.uuid4().hex[:12]
        final_file = self._atomic_write(pa_table, target_dir, batch_id)
        logger.debug("Wrote %d rows to %s", len(partition_rows), final_file)
        return len(partition_rows)

    # ── IAnalyticsSink ───────────────────────────────────────────

    async def push_batch(self, table: str, rows: list[dict[str, object]]) -> int:
        """Write rows as a new Parquet file using atomic rename.

        Returns the number of rows written.
        """
        if not rows:
            return 0

        schema = self._schemas.get(table)
        partition_key = schema.partition_key if schema else None
        dataset_dir = self._base_path / table
        partitions = self._group_by_partition(rows, partition_key)

        return sum(
            self._write_partition(
                table, partition_key, pval, prows, dataset_dir, schema
            )
            for pval, prows in partitions.items()
        )
