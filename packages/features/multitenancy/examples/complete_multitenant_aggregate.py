"""Complete example of multitenant aggregate with dedicated tenant_id column.

This example demonstrates the recommended approach for multitenant entities:
1. Use MultitenantMixin for first-class tenant_id field
2. Dedicated tenant_id column in database
3. Automatic filtering via repository mixins
"""
# mypy: ignore-errors

from pydantic import Field

from cqrs_ddd_core import AggregateRoot, DomainEvent
from cqrs_ddd_multitenancy import (
    MultitenantMixin,
    MultitenantRepositoryMixin,
    reset_tenant,
    set_tenant,
)

# ============================================================================
# Domain Model (Recommended Approach)
# ============================================================================


class OrderCreated(DomainEvent):
    """Order created event."""

    order_id: str
    customer_id: str
    aggregate_type: str | None = "Order"


class OrderStatusChanged(DomainEvent):
    """Order status changed event."""

    order_id: str
    old_status: str
    new_status: str
    aggregate_type: str | None = "Order"


class Order(MultitenantMixin, AggregateRoot[str]):
    """Multitenant order aggregate.

    Uses MultitenantMixin to add first-class tenant_id field.
    This is the RECOMMENDED approach for all multitenant entities.
    """

    customer_id: str = Field(..., description="Customer ID")
    status: str = Field(default="pending", description="Order status")
    total: float = Field(default=0.0, description="Order total")

    def create(self, customer_id: str) -> None:
        """Create the order."""
        self.customer_id = customer_id
        self.status = "pending"

        self.add_event(
            OrderCreated(
                order_id=str(self.id),
                customer_id=customer_id,
                aggregate_id=str(self.id),
            )
        )

    def change_status(self, new_status: str) -> None:
        """Change order status."""
        old_status = self.status
        self.status = new_status

        self.add_event(
            OrderStatusChanged(
                order_id=str(self.id),
                old_status=old_status,
                new_status=new_status,
                aggregate_id=str(self.id),
            )
        )


# ============================================================================
# Database Schema (SQLAlchemy)
# ============================================================================


"""
CREATE TABLE orders (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,  -- ✅ Dedicated column
    customer_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    total DECIMAL(10, 2) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,

    -- Enforce tenant_id is always set
    CONSTRAINT orders_tenant_id_not_null CHECK (tenant_id IS NOT NULL)
);

-- Index for tenant filtering (CRITICAL)
CREATE INDEX idx_orders_tenant ON orders (tenant_id);

-- Composite indexes for common queries
CREATE INDEX idx_orders_tenant_status ON orders (tenant_id, status);
CREATE INDEX idx_orders_tenant_created ON orders (tenant_id, created_at DESC);
"""


# ============================================================================
# SQLAlchemy Model (Optional - if using separate model)
# ============================================================================


from datetime import datetime, timezone

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# Option 1: Use Pydantic model directly (recommended for simple cases)
# The ModelMapper in cqrs_ddd_persistence_sqlalchemy handles conversion


# Option 2: Separate SQLAlchemy model (for complex mappings)
class OrderModel:  # Inherit from your declarative base
    """SQLAlchemy model for Order aggregate."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,  # ✅ Indexed for performance
    )
    customer_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# Repository with Multitenancy
# ============================================================================


class MultitenantOrderRepository(
    MultitenantRepositoryMixin,  # ✅ Mixin first
    SQLAlchemyRepository,  # Base repository second
):
    """Multitenant order repository.

    The MultitenantRepositoryMixin automatically:
    1. Injects tenant_id into entities on add()
    2. Filters by tenant_id on get/search()
    3. Validates tenant ownership on all operations
    """

    def __init__(self, uow_factory):
        super().__init__(
            entity_cls=Order,
            db_model_cls=OrderModel,  # Or Order if using Pydantic directly
            uow_factory=uow_factory,
        )


# ============================================================================
# Usage Example
# ============================================================================


async def example_usage():
    """Demonstrate multitenant aggregate usage."""

    # Set tenant context
    token = set_tenant("tenant-acme-corp")

    try:
        # Create order (tenant_id automatically set from context)
        order = Order(
            id="order-123",
            tenant_id="tenant-acme-corp",  # Explicit, or auto-filled by repository
            customer_id="customer-456",
        )
        order.create(customer_id="customer-456")

        # Add to repository (mixin injects tenant_id)
        await repo.add(order, uow=uow)

        # Retrieve order (mixin filters by tenant_id)
        retrieved = await repo.get("order-123", uow=uow)

        # Search orders (mixin adds tenant filter to query)
        results = await repo.search(
            {"status": "pending"},  # Your query criteria
            uow=uow,
        )

        # All results are automatically scoped to tenant-acme-corp
        for result in await results:
            assert result.tenant_id == "tenant-acme-corp"

    finally:
        # Reset tenant context
        reset_tenant(token)


# ============================================================================
# Key Benefits of This Approach
# ============================================================================


"""
✅ PERFORMANCE: Dedicated tenant_id column enables efficient B-tree indexes
✅ SECURITY: Row-Level Security (RLS) policies work naturally
✅ SCALABILITY: Partitioning by tenant_id is straightforward
✅ INTEGRITY: Foreign key constraints can reference tenant_id
✅ TOOLING: ORM middleware can automatically inject tenant filters
✅ CLARITY: tenant_id is a first-class citizen, not hidden in JSONB
✅ VALIDATION: Pydantic validates tenant_id just like any other field
✅ TESTING: Easy to mock/verify tenant_id in unit tests

❌ AVOID: Hiding tenant_id in JSONB metadata
   - Slow queries (GIN indexes have more overhead)
   - Can't partition by tenant
   - Can't use foreign keys
   - RLS policies are complex
   - ORM tooling struggles
"""
