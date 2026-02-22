# MongoDB Specification Operators

**Compile domain specifications to MongoDB query operators.**

---

## Overview

The `operators` package provides **MongoDB-specific operator compilers** for the `cqrs-ddd-specifications` package, translating specification operators to MongoDB query operators.

**Key Features:**
- ✅ **Strategy Pattern** - Each operator category is an isolated compiler module
- ✅ **MongoDB Native Operators** - Maps to MongoDB operators ($eq, $gt, $in, $regex, etc.)
- ✅ **Geometry Operators** - GeoJSON support with $geoIntersects, $near, etc.
- ✅ **JSONB Operators** - MongoDB document path queries ($elemMatch, dot notation)
- ✅ **Null Handling** - MongoDB-specific null/missing field handling

**Dependencies:**
- `cqrs-ddd-specifications` - Specification operators and AST

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  MongoQueryBuilder.build_match(spec)                        │
│       ↓                                                      │
│  spec_dict = spec.to_dict()                                 │
│  filter = _compile_node(spec_dict)                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  OPERATOR COMPILERS                          │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  STANDARD    │  │   STRING     │  │     SET      │     │
│  │              │  │              │  │              │     │
│  │  eq → $eq    │  │  like→ $regex│  │  in  → $in   │     │
│  │  gt  → $gt   │  │  ilike→ $regex│  │  nin → $nin  │     │
│  │  gte → $gte  │  │  contains    │  │              │     │
│  │  lt  → $lt   │  │  startswith  │  │              │     │
│  │  lte → $lte  │  │  endswith    │  │              │     │
│  │  ne  → $ne   │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │    NULL      │  │    JSONB     │  │   GEOMETRY   │     │
│  │              │  │              │  │              │     │
│  │  is_null     │  │  @> → $all   │  │  st_within   │     │
│  │  is_not_null │  │  ?  → $exists│  │  st_intersects│    │
│  │              │  │  Dot notation│  │  st_near     │     │
│  │              │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MONGODB QUERY                             │
│                                                              │
│  {                                                           │
│    "status": {"$eq": "active"},                              │
│    "total": {"$gte": 100},                                   │
│    "tags": {"$in": ["premium", "featured"]},                 │
│    "email": {"$regex": ".*@example.com", "$options": "i"}   │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Operator Compilers

### 1. `compile_standard` - Basic Comparisons

**Purpose:** Maps standard comparison operators to MongoDB operators.

**Operators:**
- `eq` → `$eq` (equal)
- `ne` → `$ne` (not equal)
- `gt` → `$gt` (greater than)
- `gte` → `$gte` (greater than or equal)
- `lt` → `$lt` (less than)
- `lte` → `$lte` (less than or equal)

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_standard
from cqrs_ddd_specifications.operators import SpecificationOperator

# Equal
result = compile_standard("status", SpecificationOperator.EQ, "active")
# {"status": {"$eq": "active"}}

# Greater than or equal
result = compile_standard("total", SpecificationOperator.GTE, 100)
# {"total": {"$gte": 100}}

# Not equal
result = compile_standard("status", SpecificationOperator.NE, "deleted")
# {"status": {"$ne": "deleted"}}
```

**MongoDB Query Examples:**

```python
# Specification
spec = builder.where("status", "eq", "active").and_where("total", "gt", 100).build()

# Generated MongoDB query
{
    "$and": [
        {"status": {"$eq": "active"}},
        {"total": {"$gt": 100}},
    ]
}

# SQL equivalent (for comparison)
# WHERE status = 'active' AND total > 100
```

---

### 2. `compile_string` - String Matching

**Purpose:** Maps string operators to MongoDB `$regex` operator.

**Operators:**
- `like` → `$regex` (case-sensitive pattern matching)
- `ilike` → `$regex` with `$options: "i"` (case-insensitive)
- `contains` → `$regex` (substring match)
- `startswith` → `$regex` (prefix match)
- `endswith` → `$regex` (suffix match)

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_string

# Case-sensitive like
result = compile_string("name", "like", "John%")
# {"name": {"$regex": "^John.*$"}}

# Case-insensitive like
result = compile_string("email", "ilike", "%@EXAMPLE.COM")
# {"email": {"$regex": ".*@EXAMPLE\\.COM$", "$options": "i"}}

# Contains
result = compile_string("description", "contains", "python")
# {"description": {"$regex": "python"}}

# Starts with
result = compile_string("code", "startswith", "ORD-")
# {"code": {"$regex": "^ORD-"}}

# Ends with
result = compile_string("email", "endswith", "@example.com")
# {"email": {"$regex": "@example\\.com$"}}
```

**MongoDB Query Examples:**

```python
# Specification
spec = (
    builder
    .where("name", "ilike", "john%")
    .and_where("email", "contains", "@company")
    .build()
)

# Generated MongoDB query
{
    "$and": [
        {"name": {"$regex": "^john.*$", "$options": "i"}},
        {"email": {"$regex": "@company"}},
    ]
}

# SQL equivalent (for comparison)
# WHERE name ILIKE 'john%' AND email LIKE '%@company%'
```

**Special Character Escaping:**

```python
# Automatically escapes regex special characters
result = compile_string("email", "contains", "user+test@example.com")
# {"email": {"$regex": "user\\+test@example\\.com"}}
```

---

### 3. `compile_set` - Set Membership

**Purpose:** Maps set operators to MongoDB `$in` and `$nin`.

**Operators:**
- `in` → `$in` (value in array)
- `not_in` → `$nin` (value not in array)

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_set

# In array
result = compile_set("status", "in", ["pending", "processing", "shipped"])
# {"status": {"$in": ["pending", "processing", "shipped"]}}

# Not in array
result = compile_set("status", "not_in", ["deleted", "cancelled"])
# {"status": {"$nin": ["deleted", "cancelled"]}}
```

**MongoDB Query Examples:**

```python
# Specification
spec = (
    builder
    .where("status", "in", ["active", "pending"])
    .and_where("priority", "not_in", ["low", "normal"])
    .build()
)

# Generated MongoDB query
{
    "$and": [
        {"status": {"$in": ["active", "pending"]}},
        {"priority": {"$nin": ["low", "normal"]}},
    ]
}

# SQL equivalent (for comparison)
# WHERE status IN ('active', 'pending') AND priority NOT IN ('low', 'normal')
```

---

### 4. `compile_null` - Null/Existence Checks

**Purpose:** Maps null operators to MongoDB `$exists` and type checks.

**Operators:**
- `is_null` → `{$exists: false}` or `{$eq: null}`
- `is_not_null` → `{$exists: true, $ne: null}`

**MongoDB-Specific Behavior:**
- MongoDB distinguishes between **missing field** and **null value**
- `is_null` matches both missing fields and explicit `null` values
- `is_not_null` matches only present, non-null values

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_null

# Is null (missing or null)
result = compile_null("deleted_at", "is_null", True)
# {"deleted_at": {"$eq": null}}

# Is not null (present and not null)
result = compile_null("email", "is_not_null", True)
# {"email": {"$exists": true, "$ne": null}}
```

**MongoDB Query Examples:**

```python
# Specification
spec = (
    builder
    .where("deleted_at", "is_null", True)
    .and_where("email", "is_not_null", True)
    .build()
)

# Generated MongoDB query
{
    "$and": [
        {"deleted_at": {"$eq": null}},
        {"email": {"$exists": True, "$ne": None}},
    ]
}

# SQL equivalent (for comparison)
# WHERE deleted_at IS NULL AND email IS NOT NULL
```

**MongoDB Document Examples:**

```python
# Document with null value
{"name": "John", "email": null}
# Matches: email is_null → YES, email is_not_null → NO

# Document with missing field
{"name": "Jane"}
# Matches: email is_null → YES (missing), email is_not_null → NO

# Document with value
{"name": "Bob", "email": "bob@example.com"}
# Matches: email is_null → NO, email is_not_null → YES
```

---

### 5. `compile_jsonb` - Document/Array Queries

**Purpose:** Maps JSONB operators to MongoDB document and array queries.

**Operators:**
- `@>` (contains) → `$all` (array contains all elements)
- `?` (key exists) → `$exists` (field exists)
- Dot notation for nested fields

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_jsonb

# Array contains all elements
result = compile_jsonb("tags", "@>", ["premium", "featured"])
# {"tags": {"$all": ["premium", "featured"]}}

# Field exists in document
result = compile_jsonb("metadata.customer_tier", "?", True)
# {"metadata.customer_tier": {"$exists": True}}

# Dot notation (handled automatically by MongoDB)
# metadata.customer_tier automatically queries nested field
```

**MongoDB Query Examples:**

```python
# Specification
spec = (
    builder
    .where("tags", "@>", ["premium", "active"])
    .and_where("metadata.verified", "?", True)
    .build()
)

# Generated MongoDB query
{
    "$and": [
        {"tags": {"$all": ["premium", "active"]}},
        {"metadata.verified": {"$exists": True}},
    ]
}

# SQL equivalent (PostgreSQL JSONB)
# WHERE tags @> '["premium", "active"]' AND metadata ? 'verified'
```

**Nested Document Queries:**

```python
# Document structure
{
    "id": "order-123",
    "customer": {
        "name": "John Doe",
        "address": {
            "city": "New York",
            "country": "USA",
        },
    },
}

# Query nested field (dot notation)
spec = builder.where("customer.address.city", "eq", "New York").build()

# MongoDB query
{"customer.address.city": {"$eq": "New York"}}
```

---

### 6. `compile_geometry` - Spatial Queries

**Purpose:** Maps geometry operators to MongoDB GeoJSON operators.

**Operators:**
- `st_within` → `$geoWithin` (within geometry)
- `st_intersects` → `$geoIntersects` (intersects geometry)
- `st_near` → `$near` / `$nearSphere` (near point)

**Usage:**

```python
from cqrs_ddd_persistence_mongo.operators import compile_geometry

# Within polygon
polygon = {
    "type": "Polygon",
    "coordinates": [[
        [-74.1, 40.6],
        [-73.9, 40.6],
        [-73.9, 40.8],
        [-74.1, 40.8],
        [-74.1, 40.6],
    ]],
}
result = compile_geometry("location", "st_within", polygon)
# {
#     "location": {
#         "$geoWithin": {
#             "$geometry": polygon
#         }
#     }
# }

# Near point
point = {"type": "Point", "coordinates": [-73.97, 40.77]}
result = compile_geometry("location", "st_near", {
    "geometry": point,
    "max_distance": 1000,  # meters
})
# {
#     "location": {
#         "$near": {
#             "$geometry": point,
#             "$maxDistance": 1000
#         }
#     }
# }
```

**GeoJSON Document Structure:**

```python
# MongoDB document with GeoJSON
{
    "id": "store-123",
    "name": "Downtown Store",
    "location": {
        "type": "Point",
        "coordinates": [-73.97, 40.77],  # [longitude, latitude]
    },
}

// Index for geo queries
{
    "location": "2dsphere"
}
```

**MongoDB Query Examples:**

```python
# Specification
spec = builder.where(
    "location",
    "st_within",
    {
        "type": "Polygon",
        "coordinates": [[
            [-74.1, 40.6],
            [-73.9, 40.6],
            [-73.9, 40.8],
            [-74.1, 40.8],
            [-74.1, 40.6],
        ]],
    },
).build()

# Generated MongoDB query
{
    "location": {
        "$geoWithin": {
            "$geometry": {
                "type": "Polygon",
                "coordinates": [[...]]
            }
        }
    }
}

# SQL equivalent (PostGIS)
# WHERE ST_Within(location, ST_GeomFromGeoJSON('{"type":"Polygon",...}'))
```

---

## Query Builder Integration

### `MongoQueryBuilder` - Main Compiler

**Purpose:** Orchestrates operator compilation for complete specifications.

**Usage:**

```python
from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder
from cqrs_ddd_specifications import SpecificationBuilder

builder = SpecificationBuilder()
query_builder = MongoQueryBuilder()

# Build specification
spec = (
    builder
    .where("status", "eq", "active")
    .and_where("total", "gte", 100)
    .and_where("tags", "in", ["premium", "featured"])
    .build()
)

# Compile to MongoDB query
filter_dict = query_builder.build_match(spec)
# {
#     "$and": [
#         {"status": {"$eq": "active"}},
#         {"total": {"$gte": 100}},
#         {"tags": {"$in": ["premium", "featured"]}},
#     ]
# }

# Build sort
sort = query_builder.build_sort(["-created_at", "status"])
# [("created_at", -1), ("status", 1)]

# Use in MongoDB query
collection = db["orders"]
cursor = collection.find(filter_dict).sort(sort)
```

**Complex Query Example:**

```python
spec = (
    builder
    .where("status", "in", ["pending", "processing"])
    .and_where("customer.email", "ilike", "%@example.com")
    .and_where(
        builder.or_group()
        .where("priority", "eq", "high")
        .where("created_at", "gte", datetime.now() - timedelta(days=7))
        .build()
    )
    .build()
)

filter_dict = query_builder.build_match(spec)
# {
#     "$and": [
#         {"status": {"$in": ["pending", "processing"]}},
#         {"customer.email": {"$regex": ".*@example\\.com$", "$options": "i"}},
#         {
#             "$or": [
#                 {"priority": {"$eq": "high"}},
#                 {"created_at": {"$gte": ISODate("2024-01-01")}},
#             ]
#         },
#     ]
# }
```

---

## MongoDB vs PostgreSQL Operators

| Feature | PostgreSQL | MongoDB |
|---------|------------|---------|
| **Equality** | `=` | `$eq` |
| **Inequality** | `!=` / `<>` | `$ne` |
| **Comparison** | `>`, `>=`, `<`, `<=` | `$gt`, `$gte`, `$lt`, `$lte` |
| **Set Membership** | `IN` | `$in` |
| **Pattern Matching** | `LIKE` / `ILIKE` | `$regex` with `$options` |
| **Null Check** | `IS NULL` | `{$eq: null}` or `{$exists: false}` |
| **Array Contains** | `@>` | `$all` / `$elemMatch` |
| **Full-Text Search** | `to_tsvector @@ to_tsquery` | `$text` / `$search` |
| **JSONB Path** | `->` / `->>` | Dot notation |
| **Geometry** | `ST_Within`, `ST_Intersects` | `$geoWithin`, `$geoIntersects` |

---

## Performance Considerations

### 1. Index Usage

```python
# ✅ GOOD: Uses index on status
spec = builder.where("status", "eq", "active").build()

# ✅ GOOD: Compound index on (status, created_at)
spec = (
    builder
    .where("status", "eq", "active")
    .and_where("created_at", "gte", datetime.now() - timedelta(days=7))
    .build()
)

# ❌ BAD: Case-insensitive regex can't use index efficiently
spec = builder.where("email", "ilike", "%@example.com").build()

# ✅ BETTER: Use anchored regex or full-text search
spec = builder.where("email", "endswith", "@example.com").build()
```

### 2. MongoDB-Specific Optimizations

```python
# ✅ GOOD: Use $in for multiple values
spec = builder.where("status", "in", ["pending", "processing"]).build()
# {"status": {"$in": ["pending", "processing"]}}

# ❌ BAD: Multiple OR conditions
spec = (
    builder
    .or_group()
    .where("status", "eq", "pending")
    .where("status", "eq", "processing")
    .build()
)
# {"$or": [{"status": "pending"}, {"status": "processing"}]}
```

### 3. Dot Notation vs $elemMatch

```python
# ✅ GOOD: Simple nested field query
spec = builder.where("customer.email", "eq", "user@example.com").build()
# Uses index on "customer.email"

# ⚠️ COMPLEX: Array element matching
spec = builder.where("items", "@>", [{"product_id": "prod-123"}]).build()
# {"items": {"$elemMatch": {"product_id": "prod-123"}}}
# May require compound index
```

---

## Error Handling

### Invalid Operator

```python
from cqrs_ddd_persistence_mongo.exceptions import MongoQueryError

try:
    # Unsupported operator
    spec = builder.where("field", "unsupported_op", "value").build()
    filter_dict = query_builder.build_match(spec)
except MongoQueryError as e:
    logger.error(f"Invalid operator: {e}")
```

### Invalid Field Name

```python
# MongoDB doesn't allow certain field names
spec = builder.where("$invalid", "eq", "value").build()
filter_dict = query_builder.build_match(spec)
# MongoDB will raise error during query execution
```

---

## Summary

| Compiler | Operators | MongoDB Operator |
|----------|-----------|------------------|
| `compile_standard` | `eq`, `ne`, `gt`, `gte`, `lt`, `lte` | `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte` |
| `compile_string` | `like`, `ilike`, `contains`, `startswith`, `endswith` | `$regex` with `$options` |
| `compile_set` | `in`, `not_in` | `$in`, `$nin` |
| `compile_null` | `is_null`, `is_not_null` | `$exists`, `$eq` |
| `compile_jsonb` | `@>`, `?` | `$all`, `$exists`, dot notation |
| `compile_geometry` | `st_within`, `st_intersects`, `st_near` | `$geoWithin`, `$geoIntersects`, `$near` |

**Total Lines:** ~400  
**Dependencies:** cqrs-ddd-specifications, pymongo 4.0+  
**Python Version:** 3.11+  
**MongoDB Version:** 4.0+
