# SQLAlchemy Specifications Compiler

**Compile domain specifications into efficient SQLAlchemy queries.**

---

## Overview

The `specifications` package provides a **SQLAlchemy backend** for the `cqrs-ddd-specifications` package, translating domain specification ASTs into optimized SQLAlchemy filter expressions.

**Key Features:**
- ✅ **Strategy Pattern** - Each operator (eq, like, @>, etc.) is an isolated strategy class
- ✅ **Resolution Hooks** - Intercept field resolution for computed columns, JSON, relationships
- ✅ **Query Options** - Automatic ordering, pagination, distinct, group_by
- ✅ **PostgreSQL-Specific Operators** - Full-text search, JSONB containment, geometry ops
- ✅ **JOIN Optimization** - Alias cache prevents duplicate joins for relationships

**Dependencies:**
- `cqrs-ddd-specifications` - Specification AST and operators
- `sqlalchemy>=2.0` - ORM framework

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  Service / Repository                                        │
│       ↓                                                      │
│  spec = builder.where("status", "eq", "active").build()     │
│  stmt = build_sqla_filter(OrderModel, spec.to_dict())       │
│  result = await session.execute(stmt)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  SPECIFICATIONS COMPILER                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  build_sqla_filter(model, spec_dict)                 │  │
│  │  - Walks AST tree (AND/OR/NOT/LEAF)                  │  │
│  │  - Delegates to operator registry                     │  │
│  │  - Applies resolution hooks                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyOperatorRegistry                           │  │
│  │  - Strategy pattern for operators                     │  │
│  │  - register(eq_op), register(like_op), ...            │  │
│  │  - apply(op, column, value) → BooleanClause          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Resolution Hooks                                     │  │
│  │  - Field resolution intercept                         │  │
│  │  - Computed columns, JSON lookups                     │  │
│  │  - Relationship aliasing                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  apply_query_options(stmt, model, options)            │  │
│  │  - Ordering, pagination                               │  │
│  │  - Distinct, group_by                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    SQL QUERY                                 │
│                                                              │
│  SELECT * FROM orders                                        │
│  WHERE status = 'active'                                     │
│  ORDER BY created_at DESC                                    │
│  LIMIT 20 OFFSET 0                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `build_sqla_filter()` - Main Compiler

**Purpose:** Transforms specification dictionary into SQLAlchemy filter expression.

**How It Works:**
1. Walks the AST tree (AND/OR/NOT/LEAF nodes)
2. For LEAF nodes, delegates to operator registry
3. Applies resolution hooks for custom field handling
4. Combines results with `and_()`, `or_()`, `not_()`

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications import build_sqla_filter
from cqrs_ddd_specifications import SpecificationBuilder, build_default_registry

# Build specification
registry = build_default_registry()
builder = SpecificationBuilder()
spec = (
    builder
    .where("status", "eq", "active")
    .and_where("total", "gt", 100)
    .build()
)

# Compile to SQLAlchemy
stmt = select(OrderModel)
filter_expr = build_sqla_filter(OrderModel, spec.to_dict(), registry=registry)
stmt = stmt.where(filter_expr)

# Execute
result = await session.execute(stmt)
orders = result.scalars().all()
```

**Generated SQL:**
```sql
SELECT * FROM orders
WHERE status = 'active' AND total > 100
```

**Complex Example:**

```python
spec = (
    builder
    .where("status", "in", ["pending", "processing"])
    .and_where("customer.email", "like", "%@example.com")
    .and_where(
        builder.or_group()
        .where("priority", "eq", "high")
        .where("created_at", "gte", datetime.now() - timedelta(days=7))
        .build()
    )
    .build()
)

filter_expr = build_sqla_filter(OrderModel, spec.to_dict(), registry=registry)
```

**Generated SQL:**
```sql
SELECT * FROM orders
WHERE status IN ('pending', 'processing')
  AND customer.email LIKE '%@example.com'
  AND (priority = 'high' OR created_at >= '2024-01-01')
```

---

### 2. `SQLAlchemyOperatorRegistry` - Strategy Registry

**Purpose:** Registry of operator strategies, each handling a specific comparison.

**Built-in Operators:**

| Category | Operators | Description |
|----------|-----------|-------------|
| **Standard** | `eq`, `ne`, `gt`, `gte`, `lt`, `lte` | Basic comparisons |
| **Null** | `is_null`, `is_not_null` | NULL checks |
| **Set** | `in`, `not_in` | Set membership |
| **String** | `like`, `ilike`, `contains`, `startswith`, `endswith` | String matching |
| **PostgreSQL FTS** | `fts`, `plainto_tsquery` | Full-text search |
| **PostgreSQL JSONB** | `@>`, `?`, `?&`, `?\|` | JSON containment/existence |
| **PostgreSQL Geometry** | `st_contains`, `st_within`, `st_dwithin` | Spatial operations |

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications import SQLAlchemyOperatorRegistry
from cqrs_ddd_persistence_sqlalchemy.specifications.operators.standard import (
    EqualOperator,
    GreaterThanOperator,
)

# Create custom registry
registry = SQLAlchemyOperatorRegistry()
registry.register_all(
    EqualOperator(),
    GreaterThanOperator(),
    # ... add more operators
)

# Apply operator
from cqrs_ddd_specifications.operators import SpecificationOperator

filter_expr = registry.apply(
    SpecificationOperator.EQ,
    OrderModel.status,
    "active",
)
# filter_expr = (OrderModel.status == 'active')
```

**Custom Operator:**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.strategy import SQLAlchemyOperator
from cqrs_ddd_specifications.operators import SpecificationOperator

class ModuloOperator(SQLAlchemyOperator):
    """Custom operator: field % divisor = remainder."""
    
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator("modulo")  # Custom operator
    
    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        # value = {"divisor": 10, "remainder": 0}
        divisor = value["divisor"]
        remainder = value["remainder"]
        return (column % divisor) == remainder

# Register
registry.register(ModuloOperator())
```

---

### 3. Resolution Hooks - Custom Field Handling

**Purpose:** Intercept field resolution for computed columns, JSON paths, relationships.

**Hook Protocol:**
```python
from cqrs_ddd_specifications.hooks import ResolutionHook

def my_hook(context: ResolutionContext) -> HookResult | None:
    """Return HookResult to handle, or None to continue."""
    if context.field_path == "computed_field":
        return HookResult(
            value=func.lower(context.model.name),
            handled=True,
        )
    return None
```

**SQLAlchemy Context:**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.hooks import (
    SQLAlchemyResolutionContext,
    SQLAlchemyHookResult,
)

def json_field_hook(context: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult | None:
    """Resolve JSON field paths like 'metadata.customer_id'."""
    if "." in context.field_path and context.field_path.startswith("metadata."):
        # Extract JSON path
        path_parts = context.field_path.split(".")[1:]  # Skip 'metadata'
        
        # Build JSON path expression
        json_col = context.get_column("metadata")
        expr = json_col[path_parts[0]]
        
        for part in path_parts[1:]:
            expr = expr[part]
        
        return SQLAlchemyHookResult(
            value=expr,
            handled=True,
            resolved_field=expr,
        )
    
    return None

# Usage
filter_expr = build_sqla_filter(
    OrderModel,
    spec.to_dict(),
    hooks=[json_field_hook],
)
```

**Relationship Hook:**

```python
def relationship_join_hook(context: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult | None:
    """Auto-join relationships like 'customer.email'."""
    if "." not in context.field_path:
        return None
    
    parts = context.field_path.split(".")
    if parts[0] == "customer":
        # Check alias cache to avoid duplicate joins
        alias_key = "customer"
        if alias_key in context.alias_cache:
            customer_alias = context.alias_cache[alias_key]
        else:
            # Create join
            customer_alias = aliased(CustomerModel)
            context.stmt = context.stmt.join(
                customer_alias,
                OrderModel.customer_id == customer_alias.id,
            )
            context.alias_cache[alias_key] = customer_alias
        
        # Resolve field on aliased model
        field_name = parts[1]
        resolved = getattr(customer_alias, field_name)
        
        return SQLAlchemyHookResult(
            value=resolved,
            handled=True,
            resolved_field=resolved,
            new_statement=context.stmt,
            new_model=customer_alias,
        )
    
    return None

# Usage with statement modification
from sqlalchemy import select

stmt = select(OrderModel)
filter_expr = build_sqla_filter(
    OrderModel,
    spec.to_dict(),
    hooks=[relationship_join_hook],
)
stmt = stmt.where(filter_expr)

# Generated SQL:
# SELECT orders.* FROM orders
# JOIN customers ON orders.customer_id = customers.id
# WHERE customers.email = 'user@example.com'
```

---

### 4. `apply_query_options()` - Query Modifiers

**Purpose:** Apply ordering, pagination, distinct, group_by to query.

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications import apply_query_options
from cqrs_ddd_specifications import QueryOptions

# Build query options
options = (
    QueryOptions()
    .with_ordering("-created_at", "status")  # DESC created_at, ASC status
    .with_pagination(limit=20, offset=0)
    .with_distinct(True)
)

# Apply to statement
stmt = select(OrderModel)
stmt = apply_query_options(stmt, OrderModel, options)

# Generated SQL:
# SELECT DISTINCT * FROM orders
# ORDER BY created_at DESC, status ASC
# LIMIT 20 OFFSET 0
```

**Integration with Repository:**

```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyRepository

async def search_orders(spec: ISpecification, options: QueryOptions):
    """Search with specifications and options."""
    # Build filter
    filter_expr = build_sqla_filter(OrderModel, spec.to_dict())
    
    # Build statement
    stmt = select(OrderModel).where(filter_expr)
    stmt = apply_query_options(stmt, OrderModel, options)
    
    # Execute
    result = await session.execute(stmt)
    return result.scalars().all()
```

---

## PostgreSQL-Specific Operators

### Full-Text Search (FTS)

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.operators.fts import (
    FtsOperator,
    PlainToTsqueryOperator,
)

# Register FTS operators
registry.register_all(
    FtsOperator(),  # to_tsvector(field) @@ to_tsquery(value)
    PlainToTsqueryOperator(),  # plainto_tsquery
)

# Usage
spec = builder.where("description", "fts", "python programming").build()

# Generated SQL:
# WHERE to_tsvector('english', description) @@ to_tsquery('english', 'python & programming')
```

### JSONB Operators

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.operators.jsonb import (
    JsonContainsOperator,  # @>
    JsonExistsOperator,    # ?
    JsonAllExistsOperator, # ?&
    JsonAnyExistsOperator, # ?|
)

# Register JSONB operators
registry.register_all(
    JsonContainsOperator(),
    JsonExistsOperator(),
)

# Usage: JSON containment
spec = builder.where(
    "metadata",
    "@>",
    {"tags": ["premium", "featured"]},
).build()

# Generated SQL:
# WHERE metadata @> '{"tags": ["premium", "featured"]}'::jsonb

# Usage: JSON key exists
spec = builder.where("metadata->tags", "?", "premium").build()

# Generated SQL:
# WHERE metadata ? 'premium'
```

### Geometry Operators

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.operators.geometry import (
    STContainsOperator,
    STWithinOperator,
    STDWithinOperator,
)

# Register geometry operators
registry.register_all(
    STContainsOperator(),
    STWithinOperator(),
    STDWithinOperator(),
)

# Usage: Find points within polygon
spec = builder.where(
    "location",
    "st_within",
    "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))",
).build()

# Generated SQL:
# WHERE ST_Within(location, ST_GeomFromText('POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))'))
```

---

## Integration Patterns

### Pattern 1: Repository Integration

```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyRepository
from cqrs_ddd_persistence_sqlalchemy.specifications import (
    build_sqla_filter,
    apply_query_options,
)

class OrderRepository(SQLAlchemyRepository[Order, str]):
    """Repository with specification support."""
    
    async def search(
        self,
        spec: ISpecification | None = None,
        options: QueryOptions | None = None,
        uow: SQLAlchemyUnitOfWork | None = None,
    ) -> list[Order]:
        """Search orders by specification."""
        active_uow = self._get_active_uow(uow)
        
        # Build statement
        stmt = select(OrderModel)
        
        # Apply specification
        if spec:
            filter_expr = build_sqla_filter(
                OrderModel,
                spec.to_dict(),
                registry=self._registry,
                hooks=self._hooks,
            )
            stmt = stmt.where(filter_expr)
        
        # Apply query options
        if options:
            stmt = apply_query_options(stmt, OrderModel, options)
        
        # Execute
        result = await active_uow.session.execute(stmt)
        models = result.scalars().all()
        
        return [self.from_model(m) for m in models]
```

### Pattern 2: Dynamic Filtering with Hooks

```python
from cqrs_ddd_persistence_sqlalchemy.specifications import build_sqla_filter

def computed_field_hook(context: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult | None:
    """Resolve computed fields."""
    if context.field_path == "full_name":
        # Computed column: first_name || ' ' || last_name
        expr = func.concat(context.model.first_name, " ", context.model.last_name)
        return SQLAlchemyHookResult(value=expr, handled=True)
    
    return None

# Usage
spec = builder.where("full_name", "like", "John%").build()
filter_expr = build_sqla_filter(
    CustomerModel,
    spec.to_dict(),
    hooks=[computed_field_hook],
)

# Generated SQL:
# WHERE CONCAT(first_name, ' ', last_name) LIKE 'John%'
```

### Pattern 3: Multi-Tenant with Hooks

```python
def tenant_filter_hook(context: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult | None:
    """Inject tenant_id filter for all queries."""
    tenant_id = get_current_tenant_id()
    
    if tenant_id:
        return SQLAlchemyHookResult(
            value=and_(
                context.model.tenant_id == tenant_id,
                context.value,  # Original condition
            ),
            handled=True,
        )
    
    return None

# Usage
spec = builder.where("status", "eq", "active").build()
filter_expr = build_sqla_filter(
    OrderModel,
    spec.to_dict(),
    hooks=[tenant_filter_hook],
)

# Generated SQL:
# WHERE tenant_id = 'tenant-123' AND status = 'active'
```

---

## Performance Considerations

### 1. Index Usage

```python
# ✅ GOOD: Uses index on status
spec = builder.where("status", "eq", "active").build()

# ✅ GOOD: Composite index on (status, created_at)
spec = (
    builder
    .where("status", "eq", "active")
    .where("created_at", "gte", datetime.now() - timedelta(days=7))
    .build()
)

# ❌ BAD: Can't use index with leading wildcard
spec = builder.where("email", "like", "%@example.com").build()

# ✅ BETTER: Use trigram index or full-text search
spec = builder.where("email", "contains", "@example").build()
```

### 2. JOIN Optimization

```python
# ❌ SLOW: Multiple joins without alias cache
for field in ["customer.email", "customer.address.city"]:
    spec = builder.where(field, "eq", "value").build()
    # Creates duplicate join

# ✅ FAST: Alias cache prevents duplicate joins
def relationship_hook(context: SQLAlchemyResolutionContext):
    alias_key = "customer"
    if alias_key not in context.alias_cache:
        # Create join once
        context.alias_cache[alias_key] = aliased(CustomerModel)
    # Reuse alias
    ...

filter_expr = build_sqla_filter(OrderModel, spec.to_dict(), hooks=[relationship_hook])
```

### 3. Batch Operations

```python
# ❌ SLOW: Individual queries
for order_id in order_ids:
    spec = builder.where("id", "eq", order_id).build()
    order = await repo.search(spec)

# ✅ FAST: Single query with IN operator
spec = builder.where("id", "in", order_ids).build()
orders = await repo.search(spec)
```

---

## Error Handling

### Invalid Field

```python
try:
    spec = builder.where("nonexistent_field", "eq", "value").build()
    filter_expr = build_sqla_filter(OrderModel, spec.to_dict())
except AttributeError as e:
    logger.error(f"Field not found: {e}")
```

### Unsupported Operator

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.strategy import SQLAlchemyOperatorRegistry

# Create minimal registry (missing operators)
registry = SQLAlchemyOperatorRegistry()
registry.register(EqualOperator())

try:
    filter_expr = build_sqla_filter(
        OrderModel,
        spec.to_dict(),
        registry=registry,  # Missing 'like' operator
    )
except ValueError as e:
    logger.error(f"Unsupported operator: {e}")
```

### Hook Errors

```python
def safe_hook(context: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult | None:
    """Hook with error handling."""
    try:
        if context.field_path == "risky_field":
            expr = complex_computation(context)
            return SQLAlchemyHookResult(value=expr, handled=True)
    except Exception as e:
        logger.warning(f"Hook failed for {context.field_path}: {e}")
        # Return None to fall back to default resolution
        return None
    
    return None
```

---

## Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `build_sqla_filter()` | Compile specification to SQL | AST walking, hook support |
| `SQLAlchemyOperatorRegistry` | Operator strategies | Strategy pattern, extensible |
| `Resolution Hooks` | Custom field resolution | Computed columns, JSON, relationships |
| `apply_query_options()` | Query modifiers | Ordering, pagination, distinct, group_by |
| `PostgreSQL Operators` | Advanced SQL features | FTS, JSONB, Geometry |

**Total Lines:** ~800  
**Dependencies:** SQLAlchemy 2.0+, cqrs-ddd-specifications  
**Python Version:** 3.11+

**Supported Databases:**
- PostgreSQL (recommended) - Full operator support
- SQLite - Standard operators only (no FTS/JSONB/Geometry)
