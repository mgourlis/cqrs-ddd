# cqrs-ddd-analytics

**OLAP connector** — flattens domain events to tabular rows and writes them to local or networked Parquet files, optimized for downstream querying via **DuckDB** and visualization in **Apache Superset**.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)

---

## Overview

`cqrs-ddd-analytics` is the ingestion layer for a lightweight, high-performance BI pipeline built on top of the CQRS/DDD toolkit. It consumes domain events (in real-time via `EventDispatcher` or in batch via event store replay), converts them to flat tabular rows through configurable mappers, batches them in memory, and writes them as partitioned Apache Parquet files.

### Target Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Domain Events   │────▶│  cqrs-ddd-       │────▶│  Partitioned    │
│  (EventDispatcher│     │  analytics       │     │  Parquet Files  │
│   / Event Store) │     │                  │     │  (GeoParquet)   │
└──────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                          ┌────────────────────────────────┘
                          ▼
                    ┌──────────┐        ┌──────────────────┐
                    │  DuckDB  │───────▶│  Apache Superset │
                    │ (columnar│        │  (dashboards,    │
                    │  SQL)    │        │   deck.gl maps)  │
                    └──────────┘        └──────────────────┘
```

1. **Storage:** `ParquetFileSink` writes partitioned `.parquet` files (including GeoParquet for spatial data) using an atomic rename pattern to prevent read contention.
2. **Compute:** **DuckDB** mounts the Parquet directory as a virtual database, providing zero-copy columnar reads and fast SQL aggregations.
3. **Visualization:** **Apache Superset** connects to DuckDB via SQLAlchemy (`duckdb-engine`), utilizing its native `deck.gl` integration to render standard dashboards and complex geospatial polygons/points.

## Installation

```bash
pip install cqrs-ddd-analytics
```

### Optional extras

```bash
# With geospatial support (shapely + geopandas for WKB conversion & GeoParquet metadata)
pip install cqrs-ddd-analytics[geo]
```

## Package Structure

```
cqrs_ddd_analytics/
├── __init__.py        # Public API exports
├── ports.py           # IAnalyticsSink, IRowMapper (Protocol definitions)
├── schema.py          # AnalyticsSchema, ColumnDef, ColumnType
├── mapper.py          # EventToRowMapper — configurable event-to-row flattening
├── buffer.py          # AnalyticsBuffer — batches rows before push (size/time threshold)
├── handler.py         # AnalyticsEventHandler — EventHandler that maps + buffers + pushes
├── parquet.py         # ParquetFileSink — IAnalyticsSink impl (atomic Parquet writes)
├── memory.py          # InMemorySink — testing fake with get_rows() assertion helper
└── exceptions.py      # AnalyticsError, SchemaError, SinkConnectionError, BufferFlushError
```

## Dependencies

| Dependency | Purpose | Required? |
|---|---|---|
| `cqrs-ddd-core` | Domain events, `EventHandler`, `IBackgroundWorker` | **Mandatory** |
| `pyarrow` | Parquet file I/O, columnar in-memory tables | **Mandatory** |
| `shapely` | Coordinate → WKB conversion for GeoParquet | Optional (`[geo]`) |
| `geopandas` | GeoParquet metadata utilities | Optional (`[geo]`) |

---

## Core Concepts

### Ports (Protocols)

All integrations are defined as `@runtime_checkable` Protocols in `ports.py`:

#### `IRowMapper`

Maps a domain event to one or more row dictionaries, or `None` to skip.

```python
class IRowMapper(Protocol):
    def map(self, event: DomainEvent) -> dict[str, object] | list[dict[str, object]] | None: ...
```

#### `IAnalyticsSink`

Receives batches of pre-mapped rows and persists them.

```python
class IAnalyticsSink(Protocol):
    async def push_batch(self, table: str, rows: list[dict[str, object]]) -> int: ...
    async def initialize_dataset(self, schema: AnalyticsSchema) -> None: ...
```

### Schema Definition

`AnalyticsSchema` defines the structure of an analytics dataset: table name, column definitions, and an optional partition key.

```python
from cqrs_ddd_analytics import AnalyticsSchema, ColumnDef, ColumnType

order_schema = AnalyticsSchema(
    table_name="order_events",
    columns=[
        ColumnDef(name="event_date", type=ColumnType.STRING),
        ColumnDef(name="event_type", type=ColumnType.STRING),
        ColumnDef(name="event_id", type=ColumnType.STRING),
        ColumnDef(name="occurred_at", type=ColumnType.DATETIME),
        ColumnDef(name="order_id", type=ColumnType.STRING),
        ColumnDef(name="total_amount", type=ColumnType.FLOAT, nullable=True),
    ],
    partition_key="event_date",
)
```

**Supported column types:**

| `ColumnType` | PyArrow type | Notes |
|---|---|---|
| `STRING` | `pa.string()` | |
| `INT` | `pa.int64()` | |
| `FLOAT` | `pa.float64()` | |
| `DATETIME` | `pa.timestamp("us", tz="UTC")` | Microsecond precision, UTC |
| `JSON` | `pa.string()` | Stored as JSON-encoded string |
| `BOOL` | `pa.bool_()` | |
| `GEOMETRY` | `pa.binary()` | WKB-encoded; GeoParquet metadata auto-injected |

**Validation:** The schema validates at construction time that:
- `table_name` is non-empty
- `partition_key` (if set) references an existing column

---

## Usage

### 1. Define Event-to-Row Mappers

Use `EventToRowMapper` to register mapping functions for specific event types. It implements `IRowMapper` and can be used as a decorator or called directly.

```python
from cqrs_ddd_analytics import EventToRowMapper

mapper = EventToRowMapper()


@mapper.register(OrderCreated)
def map_order_created(event: OrderCreated) -> dict:
    return {
        "event_date": event.occurred_at.strftime("%Y-%m-%d"),
        "event_type": "OrderCreated",
        "event_id": event.event_id,
        "occurred_at": event.occurred_at,
        "order_id": str(event.aggregate_id),
        "total_amount": float(event.total),
    }


@mapper.register(OrderCancelled)
def map_order_cancelled(event: OrderCancelled) -> dict:
    return {
        "event_date": event.occurred_at.strftime("%Y-%m-%d"),
        "event_type": "OrderCancelled",
        "event_id": event.event_id,
        "occurred_at": event.occurred_at,
        "order_id": str(event.aggregate_id),
        "reason": event.reason,
    }

# Events without a registered mapper are silently skipped
```

#### Geospatial Mapping

When working with geospatial data, convert coordinates to WKB (Well-Known Binary) in the mapper function. The `GEOMETRY` column type stores WKB bytes and automatically injects GeoParquet metadata into the Parquet file schema.

```python
from shapely.geometry import Point

@mapper.register(DeliveryLocationUpdated)
def map_delivery(event: DeliveryLocationUpdated) -> dict:
    point = Point(event.longitude, event.latitude)
    return {
        "event_type": "DeliveryLocationUpdated",
        "event_id": event.event_id,
        "delivery_id": event.delivery_id,
        "location": point.wkb,  # Raw WKB byte string
    }
```

#### Multi-Row Mapping

A mapper can return a list of dicts to produce multiple rows from a single event:

```python
@mapper.register(OrderItemsAdded)
def map_items(event: OrderItemsAdded) -> list[dict]:
    return [
        {
            "order_id": event.order_id,
            "item_sku": item.sku,
            "quantity": item.quantity,
            "price": item.price,
        }
        for item in event.items
    ]
```

### 2. Configure the Sink

#### ParquetFileSink (Production)

Writes partitioned Parquet files to disk using atomic renames to prevent partial reads.

```python
from cqrs_ddd_analytics import ParquetFileSink, AnalyticsSchema, ColumnDef, ColumnType

sink = ParquetFileSink(base_path="/data/analytics")

schema = AnalyticsSchema(
    table_name="order_events",
    columns=[
        ColumnDef(name="event_date", type=ColumnType.STRING),
        ColumnDef(name="order_id", type=ColumnType.STRING),
        ColumnDef(name="total_amount", type=ColumnType.FLOAT),
    ],
    partition_key="event_date",
)

await sink.initialize_dataset(schema)
```

**File layout on disk after writes:**

```
/data/analytics/
└── order_events/
    ├── event_date=2024-01-15/
    │   ├── batch_a1b2c3d4e5f6.parquet
    │   └── batch_f6e5d4c3b2a1.parquet
    └── event_date=2024-01-16/
        └── batch_1a2b3c4d5e6f.parquet
```

**Atomic write protocol:**
1. Data is serialized to a PyArrow Table
2. Written to a hidden temporary file: `.batch_<id>.tmp`
3. Atomically renamed via `os.replace()` to `batch_<id>.parquet`
4. DuckDB queries target only `*.parquet` — never sees partial writes

#### InMemorySink (Testing)

For unit tests, use the `InMemorySink` which stores rows in memory with assertion helpers:

```python
from cqrs_ddd_analytics import InMemorySink

sink = InMemorySink()

# After running your pipeline...
rows = sink.get_rows("order_events")
assert len(rows) == 5
assert rows[0]["order_id"] == "ord-123"

# Utility methods
sink.row_count("order_events")  # int
sink.tables                     # list[str]
sink.clear("order_events")      # clear one table
sink.clear()                    # clear all
```

### 3. Set Up the Buffer

`AnalyticsBuffer` accumulates rows in memory and flushes to the sink when either threshold is reached:
- **`batch_size`** — number of rows (default: 1000)
- **`flush_interval`** — seconds since last flush (default: 30.0)

It implements `IBackgroundWorker` so the periodic flush timer integrates with the toolkit's worker lifecycle.

```python
from cqrs_ddd_analytics import AnalyticsBuffer

buffer = AnalyticsBuffer(
    sink,
    batch_size=1000,       # Flush every 1000 rows
    flush_interval=30.0,   # Or every 30 seconds, whichever comes first
)

# Start the periodic flush timer (background asyncio task)
await buffer.start()

# Add rows (auto-flushes at batch_size)
await buffer.add("order_events", {"order_id": "o1", "total": 99.99})

# Manually flush all pending rows
await buffer.flush_all()

# Stop the timer and flush remaining rows
await buffer.stop()
```

**Data flow:**

```
event → mapper.map(event) → row (dict)
  → AnalyticsBuffer.add(table, row)
    → when batch_size reached OR flush_interval elapsed:
      → IAnalyticsSink.push_batch(table, rows)
        → ParquetFileSink converts rows to PyArrow Table
        → Writes to temporary file: /table/date=2024-01-15/.batch_abc123.tmp
        → OS atomic rename: /table/date=2024-01-15/batch_abc123.parquet
      → clear buffer
```

**Error handling:** If `push_batch` fails, rows are re-inserted at the front of the buffer (preserving order) and a `BufferFlushError` is raised. Buffer data loss on crash is acceptable — events are replayable from the event store.

### 4. Wire Up the Event Handler

`AnalyticsEventHandler` is a standard `EventHandler[DomainEvent]` that bridges the event dispatcher to the analytics pipeline. Register it with the `EventDispatcher` for each event type you want to track.

```python
from cqrs_ddd_core import EventDispatcher
from cqrs_ddd_analytics import (
    AnalyticsEventHandler,
    AnalyticsBuffer,
    EventToRowMapper,
    ParquetFileSink,
)

# 1. Create components
sink = ParquetFileSink("/data/analytics")
mapper = EventToRowMapper()
buffer = AnalyticsBuffer(sink, batch_size=500, flush_interval=15.0)
handler = AnalyticsEventHandler(mapper, buffer, table="order_events")

# 2. Register mappers (see section above)
@mapper.register(OrderCreated)
def map_order(event: OrderCreated) -> dict:
    return {"order_id": event.order_id, "total": event.total_amount}

# 3. Register handler with the event dispatcher
dispatcher = EventDispatcher()
dispatcher.register(OrderCreated, handler)
dispatcher.register(OrderCancelled, handler)

# 4. Start the buffer's flush timer
await buffer.start()

# ... application runs, events flow through the dispatcher ...

# 5. On shutdown
await buffer.stop()
```

### 5. Backfill / Replay Historical Events

For historical data population, read events from the event store and push them through the mapper in batch:

```python
from cqrs_ddd_analytics import EventToRowMapper, ParquetFileSink, AnalyticsSchema

sink = ParquetFileSink("/data/analytics")
await sink.initialize_dataset(order_schema)

# Read all historical events
events = await event_store.get_all()

# Map and batch
batch: list[dict] = []
for event in events:
    result = mapper.map(event)
    if result is None:
        continue
    if isinstance(result, dict):
        batch.append(result)
    else:
        batch.extend(result)

    # Push in chunks
    if len(batch) >= 5000:
        await sink.push_batch("order_events", batch)
        batch.clear()

# Final flush
if batch:
    await sink.push_batch("order_events", batch)
```

The sink automatically partitions the resulting files based on the `partition_key` value in each row.

---

## Querying with DuckDB

Once Parquet files are written, DuckDB can query them directly with zero setup:

```sql
-- Point DuckDB at the analytics directory
SELECT * FROM read_parquet('/data/analytics/order_events/**/*.parquet', hive_partitioning=true);

-- Aggregate by partition
SELECT event_date, COUNT(*) as total_orders, SUM(total_amount) as revenue
FROM read_parquet('/data/analytics/order_events/**/*.parquet', hive_partitioning=true)
GROUP BY event_date
ORDER BY event_date DESC;
```

### Geospatial Queries (with DuckDB spatial extension)

```sql
INSTALL spatial;
LOAD spatial;

SELECT delivery_id, ST_AsText(ST_GeomFromWKB(location)) as location_wkt
FROM read_parquet('/data/analytics/deliveries/**/*.parquet', hive_partitioning=true)
WHERE ST_Within(
    ST_GeomFromWKB(location),
    ST_GeomFromText('POLYGON((-73.0 40.0, -73.0 41.0, -74.0 41.0, -74.0 40.0, -73.0 40.0))')
);
```

### Apache Superset Integration

Connect Superset to DuckDB using the `duckdb-engine` SQLAlchemy dialect:

```
duckdb:///data/analytics/my_analytics.duckdb
```

Create views in DuckDB that reference the Parquet directories, then build dashboards and deck.gl map visualizations on top of them.

---

## Exceptions

All exceptions inherit from `CQRSDDDError` from the core package:

| Exception | Parent | When raised |
|---|---|---|
| `AnalyticsError` | `CQRSDDDError` | Base for all analytics errors |
| `SchemaError` | `AnalyticsError` | Invalid schema definition, PyArrow conversion failure |
| `SinkConnectionError` | `AnalyticsError`, `InfrastructureError` | Cannot create directory or write Parquet file |
| `BufferFlushError` | `AnalyticsError` | Buffer failed to flush rows to sink |

---

## Implementation Constraints

1. **Explicit mapping required** — Domain objects are never directly serialized. Every event type needs a registered mapper function.
2. **Event consumption** — Consumes domain events via `EventDispatcher` (real-time) or event store replay (backfill).
3. **Acceptable data loss** — Buffer data loss on crash is acceptable since events can be replayed from the event store.
4. **Append-only & atomic** — The sink never mutates existing Parquet files. Each `push_batch` creates a new file using the `.tmp` → `.parquet` atomic rename pattern.
5. **Geospatial constraint** — Geometry data must be mapped to WKB in the `EventToRowMapper`. The `GEOMETRY` column type stores `pa.binary()` with GeoParquet metadata auto-injected.
6. **No infrastructure in domain** — This package depends only on `cqrs-ddd-core` and `pyarrow`. No database drivers, no network I/O.

---

## Testing

The package ships with `InMemorySink` for test assertions. Combine it with the mapper and buffer for full pipeline testing without touching the filesystem:

```python
import pytest
from cqrs_ddd_analytics import (
    AnalyticsBuffer,
    AnalyticsEventHandler,
    EventToRowMapper,
    InMemorySink,
)


@pytest.fixture
def analytics_pipeline():
    sink = InMemorySink()
    mapper = EventToRowMapper()

    @mapper.register(OrderCreated)
    def map_order(event):
        return {"order_id": event.order_id, "total": event.total_amount}

    buffer = AnalyticsBuffer(sink, batch_size=100)
    handler = AnalyticsEventHandler(mapper, buffer, table="orders")
    return handler, buffer, sink


async def test_order_event_captured(analytics_pipeline):
    handler, buffer, sink = analytics_pipeline
    await handler.handle(OrderCreated(order_id="o1", total_amount=42.0))
    await buffer.flush_all()

    rows = sink.get_rows("orders")
    assert len(rows) == 1
    assert rows[0]["total"] == 42.0
```

Run tests:

```bash
pytest packages/features/analytics/tests/
```

---

## API Reference

### `EventToRowMapper`

| Method | Description |
|---|---|
| `register(event_type, func=None)` | Register a mapping function; usable as decorator or direct call |
| `map(event) → dict \| list[dict] \| None` | Map an event using the registered function; returns `None` for unmapped types |
| `registered_types → frozenset[type]` | Set of event types with registered mappers |

### `AnalyticsBuffer`

| Method | Description |
|---|---|
| `add(table, row)` | Add a row; auto-flushes if `batch_size` reached |
| `flush_all()` | Flush all buffered rows across all tables |
| `start()` | Start periodic flush timer (`IBackgroundWorker`) |
| `stop()` | Stop timer and flush remaining rows |
| `pending_count → int` | Total rows currently buffered |

### `ParquetFileSink`

| Method | Description |
|---|---|
| `initialize_dataset(schema)` | Create dataset directory and store schema |
| `push_batch(table, rows) → int` | Write rows as atomic Parquet file; returns count |

### `InMemorySink`

| Method | Description |
|---|---|
| `initialize_dataset(schema)` | Store schema and prepare empty row list |
| `push_batch(table, rows) → int` | Append rows to in-memory store; returns count |
| `get_rows(table) → list[dict]` | Get all stored rows for assertions |
| `row_count(table) → int` | Count stored rows |
| `get_schema(table) → AnalyticsSchema \| None` | Retrieve stored schema |
| `clear(table=None)` | Clear one or all tables |
| `tables → list[str]` | List tables with stored data |

### `AnalyticsEventHandler`

| Method | Description |
|---|---|
| `handle(event)` | Map event → rows → buffer (standard `EventHandler` interface) |
