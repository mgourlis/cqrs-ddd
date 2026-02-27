# CQRS/DDD Filtering

**Production-ready HTTP query parameter parsing** with enhanced operator support for building API filters, sorting, and pagination.

---

## Overview

The **filtering** package provides secure, flexible parsing of HTTP query parameters into **specifications** and **query options** for API endpoints.

**Key Features:**
- ✅ **Enhanced Operator Support** — 24 operators (standard, string, null, range)
- ✅ **Two Syntax Formats** — Colon-separated (URL-friendly) and JSON (complex queries)
- ✅ **Security First** — Field whitelisting and operator validation
- ✅ **Smart Parsing** — Handles array values in URLs (e.g., `between:18,65`)
- ✅ **Backend-Agnostic** — Outputs `ISpecification` compatible with all repositories
- ✅ **Production Ready** — Comprehensive tests and validation

---

## Installation

```bash
pip install cqrs-ddd-filtering
```

**Dependencies:**
- `cqrs-ddd-specifications` — Specification pattern implementation

---

## Quick Start

### Basic Filtering

```python
from fastapi import FastAPI, Request
from cqrs_ddd_filtering import FilterParser, FieldWhitelist
from cqrs_ddd_specifications import build_default_registry

app = FastAPI()

# Create operator registry (dependency injection)
registry = build_default_registry()

# Define security whitelist
whitelist = FieldWhitelist(
    filterable_fields={
        "status": {"eq", "in", "not_in"},
        "category": {"eq", "in"},
        "price": {"gte", "lte", "between"},
        "name": {"contains", "startswith"},
        "deleted_at": {"is_null"},
    },
    sortable_fields={"created_at", "price", "name"},
    projectable_fields={"id", "name", "price", "status"},
)

@app.get("/products")
async def list_products(request: Request):
    # Parse query params (registry injected via constructor)
    parser = FilterParser(registry)
    spec, options = parser.parse(dict(request.query_params), whitelist=whitelist)

    # Execute search
    result = await product_repo.search(spec, options)
    return await result
```

**Example Request:**
```http
GET /products?filter=status:eq:active,price:between:100,500&sort=-created_at&limit=20
```

---

## Operator Support

### Tier 1: Standard Comparison (8 Operators)

| Operator | Aliases | Description | Example |
|----------|---------|-------------|---------|
| `eq` | `=` | Equal | `status:eq:active` |
| `ne` | `!=` | Not equal | `status:ne:deleted` |
| `gt` | `>` | Greater than | `price:gt:100` |
| `gte` | `>=` | Greater or equal | `price:gte:100` |
| `lt` | `<` | Less than | `stock:lt:10` |
| `lte` | `<=` | Less or equal | `stock:lte:10` |
| `in` | — | Value in list | `status:in:active,pending` |
| `not_in` | — | Value not in list | `role:not_in:banned,spam` |

### Tier 2: String Operations (6 Operators)

| Operator | Aliases | Description | Example |
|----------|---------|-------------|---------|
| `contains` | — | Contains substring | `name:contains:john` |
| `icontains` | — | Case-insensitive contains | `email:icontains:@gmail` |
| `like` | — | SQL LIKE pattern | `name:like:John%` |
| `ilike` | — | Case-insensitive LIKE | `email:ilike:%@gmail.com` |
| `startswith` | `starts_with` | Starts with | `code:startswith:ORD-` |
| `endswith` | `ends_with` | Ends with | `file:endswith:.pdf` |

### Tier 2: Null Checks (2 Operators)

| Operator | Aliases | Description | Example |
|----------|---------|-------------|---------|
| `is_null` | `null` | Field is NULL | `deleted_at:is_null:true` |
| `is_not_null` | `not_null` | Field is NOT NULL | `email:is_not_null:true` |

### Tier 2: Range Queries (2 Operators)

| Operator | Description | Example |
|----------|-------------|---------|
| `between` | Value in range (inclusive) | `age:between:18,65` |
| `not_between` | Value not in range | `price:not_between:100,200` |

---

## Syntax Formats

### 1. Colon-Separated Syntax (URL-Friendly)

**Format:** `field:operator:value`

**Single Condition:**
```http
GET /products?filter=status:eq:active
```

**Multiple Conditions (AND):**
```http
GET /products?filter=status:eq:active,price:gte:100,category:in:electronics,books
```

**Array Values:**
```http
GET /products?filter=status:in:active,pending,confirmed
GET /products?filter=age:between:18,65
GET /products?filter=price:not_between:100,500
```

**Complex Query:**
```http
GET /products?filter=status:eq:active,deleted_at:is_null:true,price:between:50,200,name:startswith:Apple&sort=-price,name&limit=20&offset=40
```

**Parsing:**
```python
from cqrs_ddd_specifications import build_default_registry

# Create registry and parser
registry = build_default_registry()
parser = FilterParser(registry)

spec, options = parser.parse({
    "filter": "status:eq:active,deleted_at:is_null:true",
    "sort": "-price,name",
    "limit": "20",
    "offset": "40",
})

# spec → ISpecification (AND composite)
# options.offset → 40
# options.limit → 20
# options.sort → [("price", "desc"), ("name", "asc")]
```

### 2. JSON Syntax (Complex Queries)

**Format:** JSON object with structured filter

**Single Condition:**
```http
POST /products/search
{
  "filter": {
    "field": "status",
    "op": "eq",
    "value": "active"
  }
}
```

**Multiple Conditions (AND/OR):**
```http
POST /products/search
{
  "filter": {
    "and": [
      {"field": "status", "op": "eq", "value": "active"},
      {"field": "price", "op": "gte", "value": 100},
      {"field": "category", "op": "in", "value": ["electronics", "books"]}
    ]
  }
}
```

**Complex Nested Logic:**
```http
POST /products/search
{
  "filter": {
    "and": [
      {
        "or": [
          {"field": "role", "op": "eq", "value": "admin"},
          {"field": "role", "op": "eq", "value": "moderator"}
        ]
      },
      {"field": "active", "op": "eq", "value": true},
      {"field": "deleted_at", "op": "is_null", "value": true}
    ]
  }
}
```

**Parsing:**
```python
from cqrs_ddd_filtering import FilterParser, JsonFilterSyntax
from cqrs_ddd_specifications import build_default_registry

# Create registry and parser with JSON syntax
registry = build_default_registry()
parser = FilterParser(registry, default_syntax=JsonFilterSyntax())

spec, options = parser.parse({
    "filter": {
        "and": [
            {"field": "status", "op": "eq", "value": "active"},
            {"field": "price", "op": "between", "value": [100, 500]}
        ]
    }
})
```

---

## Security: Field Whitelisting

### Why Whitelist?

- ✅ **Prevent unauthorized field access** (e.g., `is_admin`)
- ✅ **Limit operator usage per field** (e.g., only `eq` on status)
- ✅ **Enforce business rules** (e.g., no sorting by password)

### Define Whitelist

```python
from cqrs_ddd_filtering import FieldWhitelist

whitelist = FieldWhitelist(
    # Fields that can be filtered, with allowed operators
    filterable_fields={
        "status": {"eq", "in", "not_in"},
        "category": {"eq", "in"},
        "price": {"eq", "gte", "lte", "gt", "lt", "between"},
        "name": {"eq", "contains", "startswith", "endswith"},
        "deleted_at": {"is_null", "is_not_null"},
        "created_at": {"gte", "lte", "between"},
        "tags": {"contains", "in"},
    },

    # Fields that can be used for sorting
    sortable_fields={"created_at", "price", "name", "status"},

    # Fields that can be projected (field selection)
    projectable_fields={"id", "name", "price", "status", "category"},
)
```

### Apply Whitelist

```python
from cqrs_ddd_specifications import build_default_registry

# Create registry
registry = build_default_registry()
parser = FilterParser(registry)
spec, options = parser.parse(query_params, whitelist=whitelist)
```

**Security Errors:**
```python
# ❌ ERROR: Field "password" not in whitelist
filter=password:eq:secret123

# ❌ ERROR: Operator "like" not allowed for field "status"
filter=status:like:%active%

# ❌ ERROR: Field "is_admin" not sortable
sort=is_admin
```

---

## Parsing Options

### Pagination

**URL Parameters:**
```http
GET /products?limit=20&offset=40  # Page 3, 20 per page
```

**Parsing:**
```python
spec, options = parser.parse({"limit": "20", "offset": "40"})
assert options.limit == 20
assert options.offset == 40
```

### Sorting

**Single Field (ASC):**
```http
GET /products?sort=created_at
```

**Single Field (DESC):**
```http
GET /products?sort=-created_at
```

**Multiple Fields:**
```http
GET /products?sort=-price,name
```

**Alternative Format (Structured):**
```http
GET /products?sort[0][field]=price&sort[0][dir]=desc&sort[1][field]=name&sort[1][dir]=asc
```

**Parsing:**
```python
spec, options = parser.parse({"sort": "-price,name"})
assert options.sort == [("price", "desc"), ("name", "asc")]
```

### Field Projection

**Select Specific Fields:**
```http
GET /products?fields=id,name,price
```

**Parsing:**
```python
spec, options = parser.parse({"fields": "id,name,price"})
assert options.fields == ["id", "name", "price"]
```

---

## Integration Patterns

### Pattern 1: FastAPI with Whitelist

```python
from fastapi import FastAPI, Request, HTTPException
from cqrs_ddd_filtering import FilterParser, FieldWhitelist
from cqrs_ddd_specifications import build_default_registry

app = FastAPI()

# Create registry (singleton)
registry = build_default_registry()

# Define whitelist per resource
PRODUCT_WHITELIST = FieldWhitelist(
    filterable_fields={
        "status": {"eq", "in"},
        "category": {"eq", "in"},
        "price": {"gte", "lte", "between"},
        "name": {"contains", "startswith"},
        "deleted_at": {"is_null"},
    },
    sortable_fields={"created_at", "price", "name"},
    projectable_fields={"id", "name", "price", "status"},
)

@app.get("/products")
async def list_products(request: Request):
    try:
        parser = FilterParser(registry)  # Inject registry
        spec, options = parser.parse(
            dict(request.query_params),
            whitelist=PRODUCT_WHITELIST,
        )

        result = await product_repo.search(spec, options)
        return {
            "data": await result,
            "pagination": {
                "limit": options.limit,
                "offset": options.offset,
            }
        }
    except FieldNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### Pattern 2: Dynamic Filtering with Security

```python
from cqrs_ddd_filtering import SecurityConstraintInjector
from cqrs_ddd_specifications import build_default_registry

# Create registry
registry = build_default_registry()

# Inject mandatory security constraints (e.g., tenant_id)
injector = SecurityConstraintInjector(
    mandatory_filters={
        "tenant_id": lambda: get_current_tenant_id(),
    }
)

@app.get("/orders")
async def list_orders(request: Request):
    parser = FilterParser(registry)  # Inject registry
    user_spec, options = parser.parse(dict(request.query_params), whitelist=whitelist)

    # Inject tenant_id constraint
    secure_spec = injector.inject(user_spec)

    # secure_spec → AND(user_spec, tenant_id:eq:{current_tenant})
    return await order_repo.search(secure_spec, options)
```

### Pattern 3: POST Search with JSON Syntax

```python
from cqrs_ddd_filtering import JsonFilterSyntax
from cqrs_ddd_specifications import build_default_registry
from pydantic import BaseModel
from typing import Any

# Create registry
registry = build_default_registry()

class SearchRequest(BaseModel):
    filter: dict[str, Any] | None = None
    sort: list[dict[str, str]] | None = None
    limit: int | None = None
    offset: int | None = None
    fields: list[str] | None = None

@app.post("/products/search")
async def search_products(body: SearchRequest):
    parser = FilterParser(registry, default_syntax=JsonFilterSyntax())  # Inject registry
    spec, options = parser.parse(body.model_dump(exclude_none=True))

    result = await product_repo.search(spec, options)
    return await result
```

**Request:**
```json
{
  "filter": {
    "and": [
      {"field": "status", "op": "eq", "value": "active"},
      {"field": "price", "op": "between", "value": [100, 500]},
      {"field": "deleted_at", "op": "is_null", "value": true}
    ]
  },
  "sort": [{"field": "price", "dir": "desc"}],
  "limit": 20
}
```

---

## Complete Example

### Full FastAPI Integration

```python
from fastapi import FastAPI, Request, HTTPException, Query
from typing import Optional
from cqrs_ddd_filtering import FilterParser, FieldWhitelist, JsonFilterSyntax
from cqrs_ddd_specifications import QueryOptions as SpecQueryOptions, build_default_registry

app = FastAPI()

# Create registry (singleton for application lifetime)
registry = build_default_registry()

# Whitelist for products
PRODUCT_WHITELIST = FieldWhitelist(
    filterable_fields={
        "status": {"eq", "ne", "in", "not_in"},
        "category": {"eq", "in"},
        "price": {"eq", "ne", "gt", "gte", "lt", "lte", "between"},
        "name": {"eq", "contains", "startswith", "endswith", "like"},
        "deleted_at": {"is_null", "is_not_null"},
        "created_at": {"gte", "lte", "between"},
        "tags": {"contains", "in"},
    },
    sortable_fields={"created_at", "price", "name", "status"},
    projectable_fields={"id", "name", "price", "status", "category", "tags"},
)

@app.get("/products")
async def list_products(
    request: Request,
    filter: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    offset: Optional[int] = Query(None),
    fields: Optional[str] = Query(None),
):
    """
    List products with filtering, sorting, and pagination.

    Examples:
        # Simple filter
        GET /products?filter=status:eq:active

        # Range query
        GET /products?filter=price:between:100,500

        # Null check
        GET /products?filter=deleted_at:is_null:true

        # Complex query
        GET /products?filter=status:eq:active,price:gte:100,category:in:electronics,books
    """
    try:
        parser = FilterParser(registry)  # Inject registry
        spec, options = parser.parse(
            {
                "filter": filter,
                "sort": sort,
                "limit": limit,
                "offset": offset,
                "fields": fields,
            },
            whitelist=PRODUCT_WHITELIST,
        )

        # Convert FilterParser options to Specification QueryOptions
        query_options = (
            SpecQueryOptions()
            .with_specification(spec)
            .with_pagination(limit=options.limit, offset=options.offset)
            .with_ordering(*[f"-{f}" if d == "desc" else f for f, d in options.sort])
        )

        if options.fields:
            query_options = query_options.with_select_fields(*options.fields)

        result = await product_repo.search(query_options)
        items = await result

        return {
            "data": items,
            "pagination": {
                "limit": options.limit,
                "offset": options.offset,
                "total": len(items),
            },
            "filters_applied": filter,
            "sort_applied": sort,
        }
    except FieldNotAllowedError as e:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_filter",
            "message": str(e),
        })

@app.post("/products/search")
async def search_products(body: dict):
    """
    Advanced search with JSON syntax (supports ALL specification operators).

    Request body:
    {
      "filter": {
        "and": [
          {"field": "status", "op": "eq", "value": "active"},
          {"field": "price", "op": "between", "value": [100, 500]},
          {"field": "metadata", "op": "json_contains", "value": {"verified": true}}
        ]
      },
      "sort": [{"field": "price", "dir": "desc"}],
      "limit": 20
    }
    """
    parser = FilterParser(registry, default_syntax=JsonFilterSyntax())  # Inject registry
    spec, options = parser.parse(body, whitelist=PRODUCT_WHITELIST)

    query_options = (
        SpecQueryOptions()
        .with_specification(spec)
        .with_pagination(limit=options.limit, offset=options.offset)
    )

    result = await product_repo.search(query_options)
    return await result
```

---

## Query Examples

### Example 1: Product Search

**URL:**
```http
GET /products?filter=status:eq:active,price:between:50,200,category:in:electronics,books,deleted_at:is_null:true&sort=-price,name&limit=20&offset=40
```

**Equivalent SQL:**
```sql
SELECT * FROM products
WHERE status = 'active'
  AND price BETWEEN 50 AND 200
  AND category IN ('electronics', 'books')
  AND deleted_at IS NULL
ORDER BY price DESC, name ASC
LIMIT 20 OFFSET 40;
```

### Example 2: User Search with Null Checks

**URL:**
```http
GET /users?filter=active:eq:true,deleted_at:is_null:true,email:is_not_null:true,role:in:admin,moderator,name:startswith:John
```

**Equivalent SQL:**
```sql
SELECT * FROM users
WHERE active = true
  AND deleted_at IS NULL
  AND email IS NOT NULL
  AND role IN ('admin', 'moderator')
  AND name LIKE 'John%';
```

### Example 3: Complex JSON Query

**Request:**
```json
{
  "filter": {
    "and": [
      {"field": "status", "op": "eq", "value": "active"},
      {
        "or": [
          {"field": "price", "op": "lt", "value": 50},
          {"field": "discount", "op": "gte", "value": 0.2}
        ]
      },
      {"field": "deleted_at", "op": "is_null", "value": true},
      {"field": "tags", "op": "contains", "value": "sale"}
    ]
  },
  "sort": [{"field": "created_at", "dir": "desc"}],
  "limit": 50
}
```

---

## Operator Mapping: URL vs SQL vs MongoDB

| Filter Syntax | SQL Operator | MongoDB Operator |
|---------------|--------------|------------------|
| `eq:active` | `= 'active'` | `{"$eq": "active"}` |
| `ne:active` | `!= 'active'` | `{"$ne": "active"}` |
| `gt:100` | `> 100` | `{"$gt": 100}` |
| `gte:100` | `>= 100` | `{"$gte": 100}` |
| `lt:100` | `< 100` | `{"$lt": 100}` |
| `lte:100` | `<= 100` | `{"$lte": 100}` |
| `in:active,pending` | `IN ('active', 'pending')` | `{"$in": ["active", "pending"]}` |
| `between:18,65` | `BETWEEN 18 AND 65` | `{"$gte": 18, "$lte": 65}` |
| `startswith:John` | `LIKE 'John%'` | `{"$regex": "^John"}` |
| `endswith:.pdf` | `LIKE '%.pdf'` | `{"$regex": "\\.pdf$"}` |
| `contains:john` | `LIKE '%john%'` | `{"$regex": "john"}` |
| `is_null:true` | `IS NULL` | `{"$exists": false}` |
| `is_not_null:true` | `IS NOT NULL` | `{"$exists": true, "$ne": null}` |

---

## Architecture

### Dependency Injection Pattern

The filtering package follows **explicit dependency injection** - there is NO global state or singleton registry. All dependencies must be explicitly provided:

```
┌────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                            │
│                                                                 │
│  1. Create registry at startup (singleton)                     │
│     registry = build_default_registry()                        │
│                                                                 │
│  2. Inject registry into FilterParser                          │
│     parser = FilterParser(registry)                            │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                    API LAYER (FastAPI)                          │
│                                                                 │
│  GET /products?filter=status:eq:active,price:gte:100           │
│       ↓                                                         │
│  FilterParser(registry).parse(query_params, whitelist)        │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                    FILTERING PACKAGE                            │
│                                                                 │
│  1. Parse Syntax (Colon or JSON)                                │
│     "status:eq:active" → {"op": "eq", "attr": "status", ...}   │
│                                                                 │
│  2. Security Validation                                         │
│     - Check field in whitelist                                  │
│     - Check operator allowed for field                         │
│                                                                 │
│  3. Build Specification (with injected registry)               │
│     dict → ISpecification (using SpecificationFactory)         │
│            ↓                                                    │
│            AttributeSpecification(attr, op, val, registry=...) │
│                                                                 │
│  4. Extract QueryOptions                                        │
│     sort, limit, offset, fields → QueryOptions                 │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                    SPECIFICATIONS PACKAGE                        │
│                                                                 │
│  ISpecification + QueryOptions                                  │
│       ↓                                                         │
│  Registry.evaluate(op, actual, expected)                        │
│       ↓                                                         │
│  Repository.search(spec, options)                               │
│       ↓                                                         │
│  Backend Compiler (SQL/Mongo/In-Memory)                        │
│       ↓                                                         │
│  Database Query                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Why No Global Registry?

**Previous Design (Anti-Pattern):**
```python
# ❌ BAD: Hidden global state
from cqrs_ddd_specifications import DEFAULT_REGISTRY

class AttributeSpecification:
    def __init__(self, attr, op, val, registry=None):
        self._registry = registry or DEFAULT_REGISTRY  # Falls back to global
```

**Problems:**
- ❌ Test contamination (tests share mutable global state)
- ❌ Parallel test execution issues (pytest-xdist)
- ❌ Implicit dependencies (hard to understand)
- ❌ Concurrency issues (no thread safety)

**Current Design (Best Practice):**
```python
# ✅ GOOD: Explicit dependency injection
from cqrs_ddd_specifications import build_default_registry

# Create registry explicitly
registry = build_default_registry()

# Pass to parser
parser = FilterParser(registry)

# Registry is passed to all specifications
spec = AttributeSpecification(attr, op, val, registry=registry)
```

**Benefits:**
- ✅ Test isolation (each test gets its own registry)
- ✅ Thread-safe (no shared mutable state)
- ✅ Explicit dependencies (easy to understand)
- ✅ Works with DI containers (dependency-injector, FastAPI Depends)

---

## API Reference

### FilterParser

```python
class FilterParser:
    def __init__(self, registry: MemoryOperatorRegistry, default_syntax: FilterSyntax | None = None):
        """Initialize parser with required registry."""

    def parse(
        self,
        query_params: dict[str, Any],
        whitelist: FieldWhitelist | None = None,
        filter_key: str = "filter",
        sort_key: str = "sort",
        limit_key: str = "limit",
        offset_key: str = "offset",
        fields_key: str = "fields",
    ) -> tuple[Any, QueryOptions]:
        """Parse query params into (specification, query_options)."""
```

### FieldWhitelist

```python
@dataclass
class FieldWhitelist:
    filterable_fields: dict[str, set[str]]  # field → allowed operators
    sortable_fields: set[str]                # sortable field names
    projectable_fields: set[str]             # projectable field names

    def allow_filter(self, field: str, op: str) -> None:
        """Validate field and operator are whitelisted."""

    def allow_sort(self, field: str) -> None:
        """Validate field is sortable."""

    def allow_project(self, field: str) -> None:
        """Validate field is projectable."""
```

### FilterSyntax

```python
class FilterSyntax(Protocol):
    def parse_filter(self, raw: Any) -> dict[str, Any]:
        """Parse raw filter input to specification dict."""
```

**Implementations:**
- `ColonSeparatedSyntax` — URL-friendly `field:op:value`
- `JsonFilterSyntax` — Full JSON support with validation

---

## Best Practices

### 1. Always Use Whitelists

```python
# ✅ GOOD: Secure
parser.parse(params, whitelist=whitelist)

# ❌ BAD: No security (accepts any field/operator)
parser.parse(params)
```

### 2. Use JSON Syntax for Complex Queries

```python
# ✅ GOOD: POST with JSON for complex queries
POST /products/search
{"filter": {"and": [...]}}

# ❌ BAD: Overly long URLs
GET /products?filter=very_long_query...
```

### 3. Validate User Input

```python
# ✅ GOOD: Catch security errors
try:
    spec, options = parser.parse(params, whitelist=whitelist)
except FieldNotAllowedError as e:
    raise HTTPException(400, str(e))
```

### 4. Document Supported Operators

```python
# ✅ GOOD: Document per resource
"""
Product Search Operators:
- status: eq, in, not_in
- price: eq, gt, gte, lt, lte, between
- name: contains, startswith, endswith
- deleted_at: is_null
"""
```

### 5. Test Security

```python
# ✅ GOOD: Test that forbidden fields are rejected
def test_cannot_filter_by_password():
    with pytest.raises(FieldNotAllowedError):
        parser.parse({"filter": "password:eq:secret"}, whitelist=whitelist)
```

---

## Testing

### Unit Tests

```bash
pytest packages/features/filtering/tests/ -v
```

### Test Coverage

```bash
pytest packages/features/filtering/tests/ --cov=cqrs_ddd_filtering --cov-report=html
```

---

## Migration Guide

### From Manual Query Building

**Before:**
```python
@app.get("/products")
async def list_products(status: str | None = None, min_price: float | None = None):
    query = select(Product)
    if status:
        query = query.where(Product.status == status)
    if min_price:
        query = query.where(Product.price >= min_price)
    # ... manual query building
```

**After:**
```python
from cqrs_ddd_specifications import build_default_registry

# Create registry (application-level singleton)
registry = build_default_registry()

@app.get("/products")
async def list_products(request: Request):
    parser = FilterParser(registry)  # Inject registry
    spec, options = parser.parse(dict(request.query_params), whitelist=whitelist)
    return await product_repo.search(spec, options)
```

### Dependency Injection Best Practices

**Pattern 1: Application Singleton (Recommended)**

```python
from fastapi import FastAPI, Depends
from cqrs_ddd_specifications import build_default_registry, MemoryOperatorRegistry
from cqrs_ddd_filtering import FilterParser

app = FastAPI()

# Create registry once at application startup
registry = build_default_registry()

def get_parser() -> FilterParser:
    """Dependency injection for FilterParser."""
    return FilterParser(registry)

@app.get("/products")
async def list_products(
    request: Request,
    parser: FilterParser = Depends(get_parser)
):
    spec, options = parser.parse(dict(request.query_params), whitelist=whitelist)
    return await product_repo.search(spec, options)
```

**Pattern 2: DI Container (dependency-injector)**

```python
from dependency_injector import containers, providers
from cqrs_ddd_specifications import build_default_registry
from cqrs_ddd_filtering import FilterParser

class Container(containers.DeclarativeContainer):
    # Registry singleton
    registry = providers.Singleton(build_default_registry)

    # FilterParser factory (gets registry injected)
    filter_parser = providers.Factory(
        FilterParser,
        registry=registry,
    )

    # Service that uses filtering
    product_service = providers.Factory(
        ProductService,
        filter_parser=filter_parser,
    )

# FastAPI integration
@app.get("/products")
async def list_products(
    request: Request,
    service: ProductService = Depends(lambda: Container().product_service())
):
    return await service.search_products(dict(request.query_params))
```

**Pattern 3: Per-Request Registry (Multi-Tenant)**

```python
from contextvars import ContextVar
from cqrs_ddd_specifications import MemoryOperatorRegistry

# Thread-safe context variable for current tenant
_current_tenant_registry: ContextVar[MemoryOperatorRegistry] = ContextVar('registry')

def get_tenant_registry() -> MemoryOperatorRegistry:
    """Get or create registry for current tenant."""
    registry = _current_tenant_registry.get(None)
    if registry is None:
        # Create tenant-specific registry with custom operators
        registry = build_default_registry()
        # Add tenant-specific operators here
        _current_tenant_registry.set(registry)
    return registry

@app.get("/products")
async def list_products(request: Request):
    registry = get_tenant_registry()  # Tenant-specific registry
    parser = FilterParser(registry)
    spec, options = parser.parse(dict(request.query_params), whitelist=whitelist)
    return await product_repo.search(spec, options)
```

**Testing with DI:**

```python
import pytest
from cqrs_ddd_specifications import MemoryOperatorRegistry, build_default_registry
from cqrs_ddd_filtering import FilterParser

@pytest.fixture
def test_registry() -> MemoryOperatorRegistry:
    """Create isolated registry for testing."""
    registry = build_default_registry()
    # Add test-specific operators if needed
    return registry

@pytest.fixture
def parser(test_registry: MemoryOperatorRegistry) -> FilterParser:
    """Create parser with test registry."""
    return FilterParser(test_registry)

def test_filter_parsing(parser: FilterParser):
    """Test filtering with isolated registry."""
    spec, options = parser.parse({"filter": "status:eq:active"})
    assert spec is not None
```

---

## Dependencies

### Required
- `cqrs-ddd-specifications` — Specification pattern implementation

### Optional (Infrastructure)
- `cqrs-ddd-persistence-sqlalchemy` — SQLAlchemy backend
- `cqrs-ddd-persistence-mongo` — MongoDB backend

### Development
- `pytest` — Testing
- `pytest-asyncio` — Async test support

---

## Summary

| Feature | Status | Operators | Syntax Support |
|---------|--------|-----------|----------------|
| **Standard Comparison** | ✅ Complete | 8 | Colon + JSON |
| **String Operations** | ✅ Complete | 6 | Colon + JSON |
| **Null Checks** | ✅ Complete | 2 | Colon + JSON |
| **Range Queries** | ✅ Complete | 2 | Colon + JSON |
| **JSON Operations** | ✅ JSON Only | 6 | JSON only |
| **Geometry** | ✅ JSON Only | 5+ | JSON only |
| **Security** | ✅ Complete | — | Whitelist per field |

---

**Last Updated:** February 22, 2026
**Status:** Production Ready ✅
**Version:** 2.0.0
**Operators Supported:** 24 (Colon), 50+ (JSON)
