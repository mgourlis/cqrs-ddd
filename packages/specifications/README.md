# CQRS/DDD Specifications

**Production-ready Specification Pattern** with fluent builder, composite operators, and QueryOptions for result shaping.

---

## Overview

The **specifications** package provides a powerful, type-safe implementation of the **Specification Pattern** for building complex query criteria in domain-driven design.

**Key Features:**
- ✅ **Fluent Builder API** — Chain `.where()` calls for readable queries
- ✅ **Composite Operators** — AND, OR, NOT with Python operators (`&`, `|`, `~`)
- ✅ **QueryOptions** — Pagination, ordering, grouping, field projection
- ✅ **Infrastructure-Agnostic** — Works with SQLAlchemy, MongoDB, Memory
- ✅ **Serializable** — Convert to/from dict for API transport
- ✅ **Type-Safe** — Full type hints with Pydantic compatibility

---

## Installation

```bash
pip install cqrs-ddd-specifications
```

---

## Quick Start

### Basic Specification

```python
from cqrs_ddd_specifications import SpecificationBuilder

# Build a specification
spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("age", ">=", 18)
    .where("role", "in", ["admin", "moderator"])
    .build()
)

# Use with repository
result = await repository.search(spec)
items = await result  # Get list

# Or stream
async for item in result.stream(batch_size=100):
    process(item)
```

### With QueryOptions (Pagination + Ordering)

```python
from cqrs_ddd_specifications import QueryOptions

# Wrap specification with result-shaping options
options = (
    QueryOptions()
    .with_specification(spec)
    .with_pagination(limit=20, offset=40)  # Page 3
    .with_ordering("-created_at", "name")   # DESC created_at, ASC name
)

# Repository accepts QueryOptions
result = await repository.search(options)
items = await result  # List of 20 items
```

---

## Core Concepts

### 1. Specification Pattern

**Purpose:** Encapsulate business rules for filtering domain objects in a reusable, composable way.

**Three Parts:**
1. **Specification** — The filter logic (WHAT to match)
2. **QueryOptions** — Result shaping (HOW to return)
3. **Evaluator/Compiler** — Infrastructure-specific execution

```
┌────────────────────────────────────────────────────────────────┐
│                    SPECIFICATION LAYER                         │
│                                                                │
│  SpecificationBuilder                                          │
│       .where("status", "==", "active")                         │
│       .where("total", ">", 100)                                │
│       .build()                                                 │
│           ↓                                                    │
│      ISpecification (Domain Logic)                             │
│           ↓                                                    │
│      QueryOptions (Pagination, Ordering)                       │
│           ↓                                                    │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                        │
│                                                                │
│  SQLAlchemyCompiler → WHERE clause                             │
│  MongoQueryBuilder → $match stage                              │
│  MemoryEvaluator → Python filter()                             │
└────────────────────────────────────────────────────────────────┘
```

### 2. SpecificationBuilder

**Fluent API** for constructing specification trees without manual composition.

```python
from cqrs_ddd_specifications import SpecificationBuilder

# Simple AND chain
spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("age", ">=", 21)
    .build()
)
# → AND(status == "active", age >= 21)

# Complex nested logic
spec = (
    SpecificationBuilder()
    .or_group()
        .where("role", "==", "admin")
        .where("role", "==", "superuser")
    .end_group()
    .where("active", "==", True)
    .where("deleted_at", "==", None)
    .build()
)
# → AND(
#      OR(role == "admin", role == "superuser"),
#      active == True,
#      deleted_at IS NULL
#    )
```

### 3. Composite Specifications

**Python operators** for composing specifications:

```python
from cqrs_ddd_specifications import AttributeSpecification

# Create leaf specifications
active = AttributeSpecification("status", "==", "active")
premium = AttributeSpecification("tier", "==", "premium")
recent = AttributeSpecification("created_at", ">=", "2024-01-01")

# Compose with operators
spec = (active & premium) | (recent & ~premium)

# Equivalent to:
# (status == "active" AND tier == "premium")
# OR
# (created_at >= "2024-01-01" AND NOT tier == "premium")
```

### 4. QueryOptions

**Result-shaping wrapper** that separates filtering from pagination/ordering.

```python
from cqrs_ddd_specifications import QueryOptions

options = (
    QueryOptions()
    .with_specification(spec)              # Filter logic
    .with_pagination(limit=50, offset=100) # Page 3, 50 per page
    .with_ordering("-created_at", "name")  # Sort by created_at DESC, name ASC
)

# Merge multiple QueryOptions
base_options = QueryOptions().with_ordering("name")
page_options = QueryOptions().with_pagination(limit=20, offset=0)
final_options = base_options.merge(page_options)
```

**QueryOptions Fields:**
- `specification: ISpecification | None` — Filter criteria
- `limit: int | None` — Max results
- `offset: int | None` — Skip first N results
- `order_by: list[str]` — Ordering (prefix with `-` for DESC)
- `distinct: bool` — Return only distinct rows
- `group_by: list[str]` — Group results by field(s)
- `select_fields: list[str]` — Project specific fields

---

## Architecture

### Package Structure

```
cqrs_ddd_specifications/
├── __init__.py              # Public API exports
├── builder.py               # SpecificationBuilder (fluent API)
├── base.py                  # BaseSpecification, And/Or/Not composites
├── ast.py                   # AttributeSpecification (leaf nodes)
├── operators.py             # Operator registry (==, >, in, like, etc.)
├── query_options.py         # QueryOptions (pagination, ordering)
├── evaluator.py             # In-memory specification evaluator
├── exceptions.py            # Custom exceptions
├── hooks.py                 # Hooks for custom operator behavior
├── utils.py                 # Utility functions
│
└── operators_memory/        # Memory backend operators
    ├── standard.py          # ==, !=, <, >, <=, >=
    ├── string.py            # like, ilike, startswith, endswith
    ├── set.py               # in, not_in, contains_any
    ├── null.py              # is_null, is_not_null
    ├── jsonb.py             # jsonb_contains, jsonb_path
    ├── geometry.py          # geo_within, geo_near
    └── fts.py               # full_text_search
```

### Specification Types

#### 1. AttributeSpecification (Leaf)

**Single field condition:**

```python
from cqrs_ddd_specifications import AttributeSpecification

spec = AttributeSpecification("status", "==", "active")
# {field: "status", operator: "==", value: "active"}
```

#### 2. Composite Specifications

**Logical combinations:**

```python
from cqrs_ddd_specifications import AndSpecification, OrSpecification, NotSpecification

# AND
spec = AndSpecification(spec1, spec2, spec3)

# OR
spec = OrSpecification(spec1, spec2)

# NOT
spec = NotSpecification(spec1)
```

#### 3. SpecificationBuilder (Convenience)

**Fluent construction:**

```python
spec = (
    SpecificationBuilder()
    .where("field1", "op1", value1)
    .where("field2", "op2", value2)
    .or_group()
        .where("field3", "op3", value3)
        .where("field4", "op4", value4)
    .end_group()
    .build()
)
```

---

## Operators

### Standard Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `==` | Equal | `.where("status", "==", "active")` |
| `!=` | Not equal | `.where("status", "!=", "deleted")` |
| `>` | Greater than | `.where("age", ">", 18)` |
| `>=` | Greater or equal | `.where("price", ">=", 100)` |
| `<` | Less than | `.where("stock", "<", 10)` |
| `<=` | Less or equal | `.where("discount", "<=", 0.5)` |

### Set Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `in` | Value in list | `.where("status", "in", ["pending", "confirmed"])` |
| `not_in` | Value not in list | `.where("role", "not_in", ["banned", "spam"])` |
| `contains` | Array contains value | `.where("tags", "contains", "python")` |
| `contains_any` | Array contains any | `.where("tags", "contains_any", ["python", "go"])` |
| `contains_all` | Array contains all | `.where("tags", "contains_all", ["python", "ddd"])` |

### String Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `like` | SQL LIKE pattern | `.where("name", "like", "John%")` |
| `ilike` | Case-insensitive LIKE | `.where("email", "ilike", "%@gmail.com")` |
| `startswith` | Prefix match | `.where("code", "startswith", "ORD-")` |
| `endswith` | Suffix match | `.where("file", "endswith", ".pdf")` |
| `regex` | Regular expression | `.where("phone", "regex", r"^\d{3}-\d{4}$")` |

### Null Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `is_null` | Field is NULL | `.where("deleted_at", "is_null", True)` |
| `is_not_null` | Field is NOT NULL | `.where("email", "is_not_null", True)` |

### JSON Operators (PostgreSQL/MongoDB)

| Operator | Description | Example |
|----------|-------------|---------|
| `json_contains` | JSON contains key/path | `.where("metadata", "json_contains", {"verified": True})` |
| `json_path` | JSONPath query | `.where("data", "json_path", "$.items[*].price")` |

### Geometry Operators (PostGIS/MongoDB)

| Operator | Description | Example |
|----------|-------------|---------|
| `geo_within` | Point within polygon | `.where("location", "geo_within", polygon)` |
| `geo_near` | Near point (distance) | `.where("location", "geo_near", {"point": point, "max_distance": 1000})` |

### Full-Text Search

| Operator | Description | Example |
|----------|-------------|---------|
| `full_text_search` | Full-text search | `.where("content", "full_text_search", "python ddd")` |

---

## Usage Patterns

### Pattern 1: Simple Filtering

```python
from cqrs_ddd_specifications import SpecificationBuilder

spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("balance", ">", 0)
    .build()
)

result = await customer_repo.search(spec)
customers = await result
```

### Pattern 2: Pagination + Ordering

```python
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions

spec = (
    SpecificationBuilder()
    .where("category", "==", "electronics")
    .where("price", "<=", 1000)
    .build()
)

options = (
    QueryOptions()
    .with_specification(spec)
    .with_pagination(limit=20, offset=40)  # Page 3
    .with_ordering("-price", "name")        # Cheapest first, then name
)

result = await product_repo.search(options)
products = await result
```

### Pattern 3: Complex Nested Logic

```python
spec = (
    SpecificationBuilder()
    # (Admin OR Moderator)
    .or_group()
        .where("role", "==", "admin")
        .where("role", "==", "moderator")
    .end_group()
    # AND active
    .where("active", "==", True)
    # AND (NOT banned OR verified)
    .and_group()
        .not_group()
            .where("status", "==", "banned")
        .end_group()
        .or_group()
            .where("verified", "==", True)
        .end_group()
    .end_group()
    .build()
)
```

### Pattern 4: Reusable Specifications

```python
from cqrs_ddd_specifications import AttributeSpecification

# Define reusable business rules
class CustomerSpecs:
    @staticmethod
    def active():
        return AttributeSpecification("status", "==", "active")
    
    @staticmethod
    def premium():
        return AttributeSpecification("tier", "==", "premium")
    
    @staticmethod
    def from_country(country_code: str):
        return AttributeSpecification("country", "==", country_code)

# Compose reusable specs
active_premium_us = (
    CustomerSpecs.active() 
    & CustomerSpecs.premium() 
    & CustomerSpecs.from_country("US")
)

result = await customer_repo.search(active_premium_us)
```

### Pattern 5: Dynamic Specification Construction

```python
def build_search_spec(filters: dict) -> ISpecification:
    """Build specification from API query params."""
    builder = SpecificationBuilder()
    
    if "status" in filters:
        builder.where("status", "==", filters["status"])
    
    if "min_price" in filters:
        builder.where("price", ">=", filters["min_price"])
    
    if "max_price" in filters:
        builder.where("price", "<=", filters["max_price"])
    
    if "tags" in filters:
        builder.where("tags", "contains_any", filters["tags"])
    
    return builder.build()

# Usage in FastAPI endpoint
@app.get("/products")
async def search_products(
    status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    tags: list[str] | None = Query(None),
):
    filters = {
        k: v for k, v in {
            "status": status,
            "min_price": min_price,
            "max_price": max_price,
            "tags": tags,
        }.items() if v is not None
    }
    
    spec = build_search_spec(filters)
    return await product_repo.search(spec)
```

### Pattern 6: Streaming Large Results

```python
from cqrs_ddd_specifications import QueryOptions

options = (
    QueryOptions()
    .with_specification(spec)
    .with_ordering("created_at")
)

result = await order_repo.search(options)

# Stream in batches of 1000
async for order in result.stream(batch_size=1000):
    await process_order(order)
    await update_analytics(order)
```

### Pattern 7: Field Projection (Select Specific Fields)

```python
options = (
    QueryOptions()
    .with_specification(spec)
    .with_select_fields("id", "name", "email")  # Only fetch these fields
)

result = await user_repo.search(options)
users = await result  # Each user dict has only id, name, email
```

### Pattern 8: Distinct + Group By

```python
options = (
    QueryOptions()
    .with_specification(spec)
    .with_distinct()  # or .with_distinct(True)
    .with_group_by("category", "brand")
)

result = await product_repo.search(options)
unique_combinations = await result
```

---

## Integration with Repositories

### IRepository Interface

**Core repository accepts specifications or QueryOptions:**

```python
from cqrs_ddd_core.ports.repository import IRepository

class IRepository(Protocol[T, ID]):
    async def search(
        self,
        criteria: ISpecification[T] | Any,  # ISpecification | QueryOptions
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]: ...
```

**Usage:**

```python
# Bare specification
result = await repo.search(spec)
items = await result

# With QueryOptions
options = QueryOptions().with_specification(spec).with_pagination(limit=20)
result = await repo.search(options)
items = await result
```

### How It Works Internally

**Repository normalizes criteria:**

```python
def _normalise_criteria(criteria):
    if hasattr(criteria, "specification"):
        # It's QueryOptions
        return criteria.specification, criteria
    else:
        # It's bare ISpecification
        return criteria, None
```

**Then applies:**
- Specification → WHERE clause (SQL) or $match stage (Mongo)
- QueryOptions → LIMIT/OFFSET/ORDER BY (SQL) or $limit/$skip/$sort (Mongo)

---

## Integration with Projections

### IProjectionReader Interface

**Low-level projection reader** does NOT accept QueryOptions directly:

```python
class IProjectionReader(Protocol):
    async def find(
        self,
        collection: str,
        filter: dict[str, Any],  # Simple dict, NOT ISpecification
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]: ...
```

### ProjectionBackedSpecPersistence Adapter

**Converts ISpecification → simple filter dict:**

```python
class OrderSummaryQuery(ProjectionBackedSpecPersistence[OrderSummaryDTO]):
    collection = "order_summaries"
    
    def to_dto(self, doc: dict) -> OrderSummaryDTO:
        return OrderSummaryDTO(**doc)
    
    def build_filter(self, spec: ISpecification) -> dict[str, Any]:
        """Convert specification to simple filter dict."""
        spec_dict = spec.to_dict()
        
        # Example: {"field": "status", "op": "==", "value": "active"}
        # Convert to: {"status": "active"}
        if spec_dict.get("op") == "==":
            return {spec_dict["field"]: spec_dict["value"]}
        
        # More complex logic for ranges, sets, etc.
        return self._compile_spec_to_filter(spec_dict)
    
    async def fetch(self, criteria, uow=None):
        # Extract pagination from QueryOptions
        if hasattr(criteria, "specification"):
            spec = criteria.specification
            limit = criteria.limit or 100
            offset = criteria.offset or 0
        else:
            spec = criteria
            limit = 100
            offset = 0
        
        # Convert spec → filter dict
        filter_dict = self.build_filter(spec)
        
        # Call low-level reader
        docs = await self.reader.find(
            self.collection,
            filter_dict,
            limit=limit,
            offset=offset,
            uow=uow,
        )
        
        return [self.to_dto(doc) for doc in docs]
```

**Key Insight:**
- `IProjectionReader` stays simple (only understands dicts)
- `ProjectionBackedSpecPersistence` adapts ISpecification → dict
- QueryOptions is unwrapped at the adapter level

---

## Serialization

### To Dict (for API transport)

```python
spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("age", ">=", 18)
    .build()
)

spec_dict = spec.to_dict()
# {
#     "op": "and",
#     "conditions": [
#         {"field": "status", "op": "==", "value": "active"},
#         {"field": "age", "op": ">=", "value": 18}
#     ]
# }

# QueryOptions serialization
options = QueryOptions().with_specification(spec).with_pagination(limit=20)
options_dict = options.to_dict()
# {
#     "specification": {...},
#     "limit": 20,
#     "offset": None,
#     "order_by": [],
#     ...
# }
```

### From Dict (reconstruction)

```python
from cqrs_ddd_specifications import SpecificationBuilder

# Reconstruct from dict
def spec_from_dict(data: dict) -> ISpecification:
    builder = SpecificationBuilder()
    
    if data["op"] == "and":
        for cond in data["conditions"]:
            builder.where(cond["field"], cond["op"], cond["value"])
    
    return builder.build()
```

---

## In-Memory Evaluation

**Test specifications without database:**

```python
from cqrs_ddd_specifications import SpecificationBuilder, evaluate_specification

spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("age", ">=", 18)
    .build()
)

customers = [
    {"id": 1, "status": "active", "age": 25},
    {"id": 2, "status": "inactive", "age": 30},
    {"id": 3, "status": "active", "age": 16},
]

# Filter in-memory
matching = [c for c in customers if evaluate_specification(spec, c)]
# [{"id": 1, "status": "active", "age": 25}]
```

---

## Advanced Features

### Custom Operators

**Define domain-specific operators:**

```python
from cqrs_ddd_specifications.operators import register_operator

@register_operator("credit_approved")
def credit_approved_operator(field, value, candidate):
    """Custom operator: check if credit score meets threshold."""
    credit_score = getattr(candidate, field)
    return credit_score >= value["min_score"] and not value.get("has_bankruptcy")

# Usage
spec = (
    SpecificationBuilder()
    .where("credit", "credit_approved", {"min_score": 700, "has_bankruptcy": False})
    .build()
)
```

### Hooks for Backend-Specific Behavior

**Inject custom logic per backend:**

```python
from cqrs_ddd_specifications.hooks import register_hook

@register_hook("sqlalchemy", "jsonb_contains")
def jsonb_contains_sqlalchemy(field, value):
    """Generate SQLAlchemy JSONB contains expression."""
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB
    
    return cast(field, JSONB).contains(value)

@register_hook("mongo", "jsonb_contains")
def jsonb_contains_mongo(field, value):
    """Generate MongoDB $elemMatch expression."""
    return {field: {"$elemMatch": value}}
```

---

## Best Practices

### 1. Use Reusable Specification Factories

```python
# ✅ GOOD: Centralized business rules
class OrderSpecs:
    @staticmethod
    def pending():
        return AttributeSpecification("status", "==", "pending")
    
    @staticmethod
    def high_value(threshold=1000):
        return AttributeSpecification("total", ">=", threshold)

# ❌ BAD: Duplicated logic
spec1 = AttributeSpecification("status", "==", "pending")
spec2 = AttributeSpecification("status", "==", "pending")
```

### 2. Prefer SpecificationBuilder for Complex Queries

```python
# ✅ GOOD: Readable
spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .or_group()
        .where("role", "==", "admin")
        .where("role", "==", "superuser")
    .end_group()
    .build()
)

# ❌ BAD: Hard to read
spec = AndSpecification(
    AttributeSpecification("status", "==", "active"),
    OrSpecification(
        AttributeSpecification("role", "==", "admin"),
        AttributeSpecification("role", "==", "superuser"),
    ),
)
```

### 3. Use QueryOptions for Pagination/Ordering

```python
# ✅ GOOD: Separation of concerns
options = (
    QueryOptions()
    .with_specification(spec)
    .with_pagination(limit=20, offset=40)
    .with_ordering("-created_at")
)

# ❌ BAD: Mixing filter and pagination logic
class PaginatedSpecification(ISpecification):
    def __init__(self, spec, limit, offset):
        self.spec = spec
        self.limit = limit  # Don't do this!
```

### 4. Test with In-Memory Evaluator

```python
# ✅ GOOD: Fast unit tests
def test_order_filter():
    spec = OrderSpecs.pending()
    
    orders = [
        Order(id=1, status="pending"),
        Order(id=2, status="confirmed"),
    ]
    
    matching = [o for o in orders if evaluate_specification(spec, o)]
    assert len(matching) == 1
    assert matching[0].id == 1
```

### 5. Serialize for API Transport

```python
# ✅ GOOD: Send spec to client
@app.get("/search")
async def search_endpoint(spec_dict: dict):
    spec = spec_from_dict(spec_dict)
    return await repo.search(spec)

# Client sends:
# {"op": "and", "conditions": [{"field": "status", "op": "==", "value": "active"}]}
```

---

## Comparison with Alternatives

| Feature | Specifications | Django ORM | SQLAlchemy Core | Raw SQL |
|---------|---------------|------------|-----------------|---------|
| **Type Safety** | ✅ Full | ⚠️ Partial | ✅ Full | ❌ None |
| **Reusability** | ✅ High | ⚠️ Medium | ⚠️ Medium | ❌ Low |
| **Composability** | ✅ Excellent | ⚠️ Good | ✅ Good | ❌ Poor |
| **Backend-Agnostic** | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **Serialization** | ✅ Built-in | ❌ No | ❌ No | ❌ No |
| **In-Memory Testing** | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **Complex Queries** | ✅ Excellent | ⚠️ Medium | ✅ Excellent | ✅ Excellent |

---

## Dependencies

### Required
- `typing_extensions` — Type hints for Python 3.8+

### Optional (Infrastructure)
- `cqrs-ddd-core` — Core interfaces (ISpecification, AggregateRoot)
- `cqrs-ddd-persistence-sqlalchemy` — SQLAlchemy compiler
- `cqrs-ddd-persistence-mongo` — MongoDB query builder

### Development
- `pytest` — Testing
- `pytest-asyncio` — Async test support
- `hypothesis` — Property-based testing

---

## Testing

### Unit Tests

```bash
pytest packages/specifications/tests/unit/ -v
```

### Integration Tests

```bash
pytest packages/specifications/tests/integration/ -v
```

### With Coverage

```bash
pytest packages/specifications/tests/ --cov=cqrs_ddd_specifications --cov-report=html
```

---

## Migration Guides

### From Django Q Objects

**Before (Django):**
```python
from django.db.models import Q

query = Q(status="active") & Q(age__gte=18)
User.objects.filter(query)
```

**After (Specifications):**
```python
from cqrs_ddd_specifications import SpecificationBuilder

spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .where("age", ">=", 18)
    .build()
)
await user_repo.search(spec)
```

### From SQLAlchemy Core

**Before (SQLAlchemy):**
```python
from sqlalchemy import select, and_, or_

query = select(User).where(
    and_(
        User.status == "active",
        or_(
            User.role == "admin",
            User.role == "superuser",
        )
    )
).limit(20).offset(40)
```

**After (Specifications):**
```python
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions

spec = (
    SpecificationBuilder()
    .where("status", "==", "active")
    .or_group()
        .where("role", "==", "admin")
        .where("role", "==", "superuser")
    .end_group()
    .build()
)

options = (
    QueryOptions()
    .with_specification(spec)
    .with_pagination(limit=20, offset=40)
)

await user_repo.search(options)
```

---

## Contributing

### Code Style
- Use type hints for all functions
- Use `from __future__ import annotations`
- Follow PEP 8 naming conventions
- Prefer composition over inheritance

### Testing
- Write tests for all operators
- Test serialization/deserialization
- Use Hypothesis for complex logic
- Aim for >90% code coverage

### Adding New Operators
1. Define operator in `operators.py`
2. Implement in `operators_memory/` for in-memory evaluation
3. Add backend-specific hooks (SQLAlchemy, Mongo)
4. Write tests and documentation

---

## Summary

| Feature | Status | Tests | Documentation |
|---------|--------|-------|---------------|
| SpecificationBuilder | ✅ Complete | ✅ Passing | ✅ Complete |
| Composite Operators (AND/OR/NOT) | ✅ Complete | ✅ Passing | ✅ Complete |
| QueryOptions | ✅ Complete | ✅ Passing | ✅ Complete |
| Standard Operators | ✅ Complete | ✅ Passing | ✅ Complete |
| Set Operators | ✅ Complete | ✅ Passing | ✅ Complete |
| String Operators | ✅ Complete | ✅ Passing | ✅ Complete |
| JSONB Operators | ✅ Complete | ✅ Passing | ✅ Complete |
| Geometry Operators | ✅ Complete | ✅ Passing | ✅ Complete |
| In-Memory Evaluator | ✅ Complete | ✅ Passing | ✅ Complete |
| Serialization | ✅ Complete | ✅ Passing | ✅ Complete |

---

**Last Updated:** February 21, 2026  
**Status:** Production Ready ✅  
**Version:** 1.0.0
