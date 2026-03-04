"""AnalyticsSchema — dataset definition with PyArrow type translation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .exceptions import SchemaError

if TYPE_CHECKING:
    import pyarrow as pa


class ColumnType(Enum):
    """Supported column types for analytics datasets."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    DATETIME = "datetime"
    JSON = "json"
    BOOL = "bool"
    GEOMETRY = "geometry"


@dataclass(frozen=True)
class ColumnDef:
    """Definition of a single column in an analytics dataset."""

    name: str
    type: ColumnType
    nullable: bool = True

    def to_pyarrow_field(self) -> pa.Field:
        """Convert this column definition to a PyArrow field."""
        import pyarrow as pa

        type_map: dict[ColumnType, pa.DataType] = {
            ColumnType.STRING: pa.string(),
            ColumnType.INT: pa.int64(),
            ColumnType.FLOAT: pa.float64(),
            ColumnType.DATETIME: pa.timestamp("us", tz="UTC"),
            ColumnType.JSON: pa.string(),
            ColumnType.BOOL: pa.bool_(),
            ColumnType.GEOMETRY: pa.binary(),
        }
        pa_type = type_map[self.type]
        return pa.field(self.name, pa_type, nullable=self.nullable)


@dataclass(frozen=True)
class AnalyticsSchema:
    """Dataset definition: table name, columns, and partition key.

    The ``partition_key`` must reference a column defined in ``columns``.
    It is used by sinks to organise output files into subdirectories
    (e.g. ``event_date=2024-01-15/``).
    """

    table_name: str
    columns: list[ColumnDef] = field(default_factory=list)
    partition_key: str | None = None

    def __post_init__(self) -> None:
        if not self.table_name:
            raise SchemaError("table_name must not be empty")
        if self.partition_key is not None:
            col_names = {c.name for c in self.columns}
            if self.partition_key not in col_names:
                raise SchemaError(
                    f"partition_key '{self.partition_key}' is not defined in columns: "
                    f"{sorted(col_names)}"
                )

    def to_pyarrow_schema(self) -> pa.Schema:
        """Convert the analytics schema to a PyArrow schema."""
        import pyarrow as pa

        fields = [col.to_pyarrow_field() for col in self.columns]
        metadata: dict[bytes, bytes] = {}

        # Inject GeoParquet metadata if geometry columns exist and geo libs available
        geo_columns = [c for c in self.columns if c.type is ColumnType.GEOMETRY]
        if geo_columns:
            try:
                import json

                geo_meta: dict[str, object] = {
                    "version": "1.0.0",
                    "primary_column": geo_columns[0].name,
                    "columns": {
                        c.name: {
                            "encoding": "WKB",
                            "geometry_types": [],
                        }
                        for c in geo_columns
                    },
                }
                metadata[b"geo"] = json.dumps(geo_meta).encode()
            except Exception:  # noqa: BLE001
                pass

        return pa.schema(fields, metadata=metadata)

    @property
    def column_names(self) -> list[str]:
        """Return ordered list of column names."""
        return [c.name for c in self.columns]
