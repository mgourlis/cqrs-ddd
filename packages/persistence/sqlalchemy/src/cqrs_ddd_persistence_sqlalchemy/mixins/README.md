# SQLAlchemy Column Mixins

**Reusable column mixins for building domain-driven SQLAlchemy models.**

---

## Overview

The `mixins` package provides **declarative column mixins** that mirror domain-level mixins, enabling rapid model definition while maintaining separation between domain and persistence concerns.

**Key Features:**
- ✅ **Declarative Syntax** - Add columns via inheritance
- ✅ **Domain Alignment** - Mirrors domain mixins (Auditable, Archivable, Versioned)
- ✅ **Smart Indexing** - Automatic partial indexes for performance
- ✅ **Spatial Support** - GeoAlchemy2 integration for geometry columns
- ✅ **OCC Support** - Optimistic concurrency control via version column

---

## Available Mixins

### 1. `VersionMixin` - Optimistic Concurrency Control

**Purpose:** Adds version tracking for optimistic concurrency control.

**Columns Added:**
- `version: int` - Auto-incremented on each update (managed by SQLAlchemy)

**Behavior:**
- SQLAlchemy automatically checks version on `merge()` operations
- Raises `StaleDataError` if concurrent modification detected
- Version incremented automatically on successful updates

**Usage:**
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from cqrs_ddd_persistence_sqlalchemy.mixins import VersionMixin

class Base(DeclarativeBase):
    pass

class Product(VersionMixin, Base):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(10, 2))
```

**Generated SQL:**
```sql
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100),
    price NUMERIC(10, 2),
    version INTEGER DEFAULT 0
);
```

**How OCC Works:**
```python
# Thread 1: Loads product with version=5
product1 = await repo.get(product_id, uow=uow1)

# Thread 2: Loads same product with version=5
product2 = await repo.get(product_id, uow=uow2)

# Thread 1: Updates successfully (version → 6)
product1.price = 99.99
await repo.add(product1, uow=uow1)  # ✅ SUCCESS

# Thread 2: Tries to update (stale version=5)
product2.price = 89.99
await repo.add(product2, uow=uow2)  # ❌ StaleDataError!
```

---

### 2. `AuditableModelMixin` - Created/Updated Timestamps

**Purpose:** Automatically tracks creation and modification timestamps.

**Columns Added:**
- `created_at: datetime` - Set on insert (UTC timezone-aware)
- `updated_at: datetime` - Updated on every modification (UTC, indexed)

**Behavior:**
- Both default to `datetime.now(timezone.utc)` 
- `updated_at` automatically updates on `UPDATE` operations
- `updated_at` indexed for efficient "recently modified" queries

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.mixins import AuditableModelMixin

class Order(AuditableModelMixin, Base):
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[float] = mapped_column(Numeric(10, 2))
```

**Query Examples:**
```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

# Find orders created in last 7 days
cutoff = datetime.now(timezone.utc) - timedelta(days=7)
recent_orders = await session.execute(
    select(Order).where(Order.created_at >= cutoff)
)

# Find orders updated in last hour
recently_updated = await session.execute(
    select(Order).where(Order.updated_at >= datetime.now(timezone.utc) - timedelta(hours=1))
)
```

**Generated SQL:**
```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    total NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP),
    updated_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX ix_orders_updated_at ON orders(updated_at);
```

---

### 3. `ArchivableModelMixin` - Soft Delete with Partial Indexes

**Purpose:** Enables soft-delete (archive) pattern with smart partial indexes.

**Columns Added:**
- `archived_at: datetime | None` - NULL for active, timestamp when archived
- `archived_by: str | None` - User/system that archived the record

**Partial Indexes Created:**
1. `ix_{table}_archivable_active` - WHERE `archived_at IS NULL` (active rows)
2. `ix_{table}_archivable_archived` - WHERE `archived_at IS NOT NULL` (archived rows)
3. `uq_{table}_archivable_{cols}` - UNIQUE constraint on active rows only (if configured)

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.mixins import ArchivableModelMixin

class Document(ArchivableModelMixin, Base):
    __tablename__ = "documents"
    
    __archivable_unique_columns__ = ["slug"]  # Unique slug among active docs
    
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
```

**Generated SQL (PostgreSQL):**
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    slug VARCHAR(200),
    title VARCHAR(500),
    content TEXT,
    archived_at TIMESTAMP,
    archived_by VARCHAR
);

-- Partial index: Active rows only
CREATE INDEX ix_documents_archivable_active 
ON documents(archived_at) 
WHERE archived_at IS NULL;

-- Partial index: Archived rows only
CREATE INDEX ix_documents_archivable_archived 
ON documents(archived_at) 
WHERE archived_at IS NOT NULL;

-- Partial unique constraint: Unique slug among active documents
CREATE UNIQUE INDEX uq_documents_archivable_slug
ON documents(slug)
WHERE archived_at IS NULL;
```

**Query Examples:**
```python
from sqlalchemy import select

# List active documents (uses partial index)
active_docs = await session.execute(
    select(Document).where(Document.archived_at.is_(None))
)

# List archived documents (uses partial index)
archived_docs = await session.execute(
    select(Document).where(Document.archived_at.is_not(None))
)

# Archive a document
doc.archived_at = datetime.now(timezone.utc)
doc.archived_by = current_user.id
await session.commit()

# This now allows a new document with same slug (old one is archived)
new_doc = Document(slug="same-slug", title="New Version")
session.add(new_doc)
await session.commit()  # ✅ SUCCESS - unique constraint only applies to active docs
```

**Multiple Unique Constraints:**
```python
class Ticket(ArchivableModelMixin, Base):
    __tablename__ = "tickets"
    
    # Both code and (event_id, seat_number) must be unique among active tickets
    __archivable_unique_columns__ = [
        ["code"],                     # Unique code
        ["event_id", "seat_number"],  # Unique (event_id, seat_number) combination
    ]
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    seat_number: Mapped[str] = mapped_column(String(20))
```

**Overriding `__table_args__`:**
```python
class MyModel(ArchivableModelMixin, Base):
    __tablename__ = "my_table"
    __archivable_unique_columns__ = ["code"]
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100))
    
    @declared_attr.directive
    def __table_args__(cls):
        # Merge mixin indexes with local constraints
        return ArchivableModelMixin.__table_args__(cls) + (
            UniqueConstraint("other_col"),
            {"comment": "My table comment"},
        )
```

---

### 4. `SpatialModelMixin` - Geometry Columns

**Purpose:** Adds a geometry column using GeoAlchemy2 for spatial data.

**Configuration Attributes:**
- `__geometry_type__: str` - Geometry type (default: "GEOMETRY")
- `__geometry_srid__: int` - Spatial reference ID (default: 4326)

**Columns Added:**
- `geom: Geometry` - GeoAlchemy2 geometry column with spatial index

**Supported Geometry Types:**
- `POINT` - Single point
- `LINESTRING` - Line
- `POLYGON` - Polygon
- `MULTIPOINT` - Multiple points
- `MULTILINESTRING` - Multiple lines
- `MULTIPOLYGON` - Multiple polygons
- `GEOMETRYCOLLECTION` - Mixed geometry types
- `GEOMETRY` - Any geometry type

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.mixins import SpatialModelMixin

class Store(SpatialModelMixin, Base):
    __tablename__ = "stores"
    __geometry_type__ = "POINT"
    __geometry_srid__ = 4326  # WGS84 (GPS coordinates)
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # geom column added automatically
```

**Generated SQL (PostGIS):**
```sql
CREATE TABLE stores (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200),
    geom GEOMETRY(POINT, 4326)
);

CREATE INDEX ix_stores_geom ON stores USING GIST(geom);
```

**Spatial Queries:**
```python
from geoalchemy2 import functions as func
from sqlalchemy import select
from shapely.geometry import Point

# Find stores within 5km of a point
user_location = Point(-73.9857, 40.7484)  # NYC coordinates
wkb_element = from_shape(user_location, srid=4326)

nearby_stores = await session.execute(
    select(Store).where(
        func.ST_DWithin(Store.geom, wkb_element, 5000)  # 5km radius
    )
)

# Find stores in a bounding box
from geoalchemy2.elements import WKTElement
bbox = WKTElement(
    "POLYGON((-74.0 40.7, -73.9 40.7, -73.9 40.8, -74.0 40.8, -74.0 40.7))",
    srid=4326
)

stores_in_bbox = await session.execute(
    select(Store).where(func.ST_Within(Store.geom, bbox))
)

# Insert store with location
from geoalchemy2.elements import WKTElement

new_store = Store(
    name="Downtown Store",
    geom=WKTElement("POINT(-73.9857 40.7484)", srid=4326)
)
session.add(new_store)
await session.commit()
```

**GeoPackage/SQLite Setup:**
```python
from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
    setup_spatialite_engine,
    register_spatialite_mappings,
)

# Register SpatiaLite function mappings (call once)
register_spatialite_mappings()

# Setup engine to load SpatiaLite extension
engine = create_async_engine("sqlite+aiosqlite:///mydb.sqlite")
setup_spatialite_engine(engine.sync_engine)
```

---

## Combining Mixins

You can combine multiple mixins:

```python
from cqrs_ddd_persistence_sqlalchemy.mixins import (
    VersionMixin,
    AuditableModelMixin,
    ArchivableModelMixin,
    SpatialModelMixin,
)

class Location(
    VersionMixin,
    AuditableModelMixin,
    ArchivableModelMixin,
    SpatialModelMixin,
    Base,
):
    __tablename__ = "locations"
    __archivable_unique_columns__ = ["code"]
    __geometry_type__ = "POINT"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    
    # Columns added by mixins:
    # - version (VersionMixin)
    # - created_at, updated_at (AuditableModelMixin)
    # - archived_at, archived_by (ArchivableModelMixin)
    # - geom (SpatialModelMixin)
```

**Generated SQL:**
```sql
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    code VARCHAR(50),
    name VARCHAR(200),
    version INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP),
    updated_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP),
    archived_at TIMESTAMP,
    archived_by VARCHAR,
    geom GEOMETRY(POINT, 4326)
);

-- Indexes
CREATE INDEX ix_locations_updated_at ON locations(updated_at);
CREATE INDEX ix_locations_archived_at ON locations(archived_at);
CREATE INDEX ix_locations_geom ON locations USING GIST(geom);

-- Partial indexes for archivable
CREATE INDEX ix_locations_archivable_active ON locations(archived_at) WHERE archived_at IS NULL;
CREATE INDEX ix_locations_archivable_archived ON locations(archived_at) WHERE archived_at IS NOT NULL;

-- Partial unique constraint
CREATE UNIQUE INDEX uq_locations_archivable_code ON locations(code) WHERE archived_at IS NULL;
```

---

## Best Practices

### 1. Use VersionMixin for Concurrent Updates

```python
# ✅ GOOD: Protect against concurrent modifications
class Product(VersionMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock: Mapped[int] = mapped_column(Integer)

# ❌ BAD: Lost updates possible
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock: Mapped[int] = mapped_column(Integer)
```

### 2. Use ArchivableModelMixin for Soft Deletes

```python
# ✅ GOOD: Preserve historical data
class Order(ArchivableModelMixin, Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)

# Archive instead of delete
order.archived_at = datetime.now(timezone.utc)
await session.commit()

# ❌ BAD: Permanent data loss
await session.delete(order)
await session.commit()
```

### 3. Use Spatial Indexes for Location Queries

```python
# ✅ GOOD: Spatial index automatically created
class Store(SpatialModelMixin, Base):
    __tablename__ = "stores"
    __geometry_type__ = "POINT"

# Query uses spatial index
stores = await session.execute(
    select(Store).where(func.ST_DWithin(Store.geom, point, 1000))
)

# ❌ BAD: No spatial index, full table scan
class Store(Base):
    __tablename__ = "stores"
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
```

### 4. Configure Partial Unique Constraints

```python
# ✅ GOOD: Unique among active records
class Document(ArchivableModelMixin, Base):
    __archivable_unique_columns__ = ["slug"]

# Allows:
# 1. Active document with slug="report"
# 2. Archive it
# 3. Create new active document with slug="report"

# ❌ BAD: Unique across all records (including archived)
class Document(Base):
    slug: Mapped[str] = mapped_column(String(200), unique=True)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DOMAIN MODELS                             │
│                                                              │
│  class Product(AggregateRoot):                              │
│      - Uses domain mixins (AuditableMixin, etc.)            │
│      - Business logic                                        │
│      - Validation                                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
                      ModelMapper converts
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 SQLALCHEMY MODELS                            │
│                                                              │
│  class ProductModel(                                        │
│      VersionMixin,          # ← OCC support                 │
│      AuditableModelMixin,   # ← created_at, updated_at      │
│      ArchivableModelMixin,  # ← archived_at, partial idxs   │
│      SpatialModelMixin,     # ← geom column (if needed)     │
│      Base                                                   │
│  ):                                                         │
│      __tablename__ = "products"                             │
│      # Columns defined here                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
                      SQLAlchemy generates
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE SCHEMA                           │
│                                                              │
│  CREATE TABLE products (                                    │
│      id INTEGER PRIMARY KEY,                                │
│      version INTEGER DEFAULT 0,        ← VersionMixin       │
│      created_at TIMESTAMP,             ← AuditableMixin     │
│      updated_at TIMESTAMP,             ← AuditableMixin     │
│      archived_at TIMESTAMP,            ← ArchivableMixin    │
│      archived_by VARCHAR,              ← ArchivableMixin    │
│      geom GEOMETRY(POINT, 4326)        ← SpatialMixin       │
│  );                                                          │
│                                                              │
│  -- Indexes automatically created                           │
│  CREATE INDEX ix_products_updated_at ...                    │
│  CREATE INDEX ix_products_archivable_active WHERE ...       │
│  CREATE INDEX ix_products_geom USING GIST ...               │
└─────────────────────────────────────────────────────────────┘
```

---

## Performance Considerations

### Partial Indexes

Partial indexes (used by `ArchivableModelMixin`) significantly improve query performance:

```sql
-- Query: Find active documents
SELECT * FROM documents WHERE archived_at IS NULL;

-- Without partial index: Scans ALL rows (including archived)
-- With partial index: Scans only active rows
CREATE INDEX ix_documents_archivable_active 
ON documents(archived_at) 
WHERE archived_at IS NULL;  -- Only indexes active rows
```

**Size Comparison:**
- Full index on `archived_at`: 1,000,000 entries (all rows)
- Partial index on `archived_at IS NULL`: 100,000 entries (only active rows)
- **Result:** 10x smaller index, 10x faster queries

### Spatial Indexes

Spatial indexes (created by `SpatialModelMixin`) are essential for location queries:

```sql
-- Without spatial index: Full table scan + geometry calculation per row
SELECT * FROM stores WHERE ST_DWithin(geom, point, 5000);
-- Time: ~500ms (1M rows)

-- With GIST spatial index: Index scan
CREATE INDEX ix_stores_geom ON stores USING GIST(geom);
-- Time: ~5ms (1M rows)
```

---

## Dependencies

- `sqlalchemy>=2.0` - ORM framework
- `geoalchemy2` - Spatial extensions (optional, only for `SpatialModelMixin`)
- `shapely` - Geometry operations (optional, for spatial queries)

---

## Testing

Mixins can be tested independently:

```python
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

def test_version_mixin_detects_concurrent_modification():
    """Test that VersionMixin raises error on concurrent update."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    # Create initial product
    with Session(engine) as session:
        product = Product(name="Widget", price=10.0)
        session.add(product)
        session.commit()
        product_id = product.id
        version_1 = product.version
    
    # Simulate concurrent modifications
    with Session(engine) as session1, Session(engine) as session2:
        # Both load same version
        p1 = session1.get(Product, product_id)
        p2 = session2.get(Product, product_id)
        
        # First update succeeds
        p1.price = 15.0
        session1.commit()  # version → 2
        
        # Second update fails
        p2.price = 20.0
        with pytest.raises(StaleDataError):
            session2.commit()  # ❌ Version mismatch!
```

---

## Migration Guide

### Adding Mixins to Existing Tables

```python
# Before
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)

# After (add version tracking)
class Product(VersionMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)

# Migration (Alembic)
def upgrade():
    op.add_column('products', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
```

---

## Summary

| Mixin | Purpose | Columns | Indexes |
|-------|---------|---------|---------|
| `VersionMixin` | Optimistic concurrency | `version` | - |
| `AuditableModelMixin` | Timestamps | `created_at`, `updated_at` | `updated_at` |
| `ArchivableModelMixin` | Soft delete | `archived_at`, `archived_by` | Partial (active/archived) + optional unique |
| `SpatialModelMixin` | Geometry data | `geom` | Spatial GIST |

**Total Lines:** ~250  
**Dependencies:** SQLAlchemy 2.0+, GeoAlchemy2 (optional)  
**Python Version:** 3.11+
