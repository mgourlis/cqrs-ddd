"""cqrs-ddd-analytics — OLAP connector for domain event analytics.

Flattens domain events to tabular rows and writes them to partitioned
Parquet files for downstream querying via DuckDB and visualization
in Apache Superset.
"""

from __future__ import annotations

from .buffer import AnalyticsBuffer
from .exceptions import (
    AnalyticsError,
    BufferFlushError,
    SchemaError,
    SinkConnectionError,
)
from .handler import AnalyticsEventHandler
from .mapper import EventToRowMapper
from .memory import InMemorySink
from .parquet import ParquetFileSink
from .ports import IAnalyticsSink, IRowMapper
from .schema import AnalyticsSchema, ColumnDef, ColumnType

__all__ = [
    # Ports
    "IAnalyticsSink",
    "IRowMapper",
    # Schema
    "AnalyticsSchema",
    "ColumnDef",
    "ColumnType",
    # Mapper
    "EventToRowMapper",
    # Buffer
    "AnalyticsBuffer",
    # Handler
    "AnalyticsEventHandler",
    # Sinks
    "ParquetFileSink",
    "InMemorySink",
    # Exceptions
    "AnalyticsError",
    "SchemaError",
    "SinkConnectionError",
    "BufferFlushError",
]
