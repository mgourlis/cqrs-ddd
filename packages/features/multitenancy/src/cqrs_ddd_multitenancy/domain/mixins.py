"""Multitenant domain mixins for aggregates and entities.

These mixins add tenant context to domain models following the same
pattern as core mixins (AuditableMixin, ArchivableMixin).

Usage:
    from cqrs_ddd_core import AggregateRoot
    from cqrs_ddd_multitenancy.domain import MultitenantMixin

    class Order(MultitenantMixin, AggregateRoot[str]):
        customer_id: str
        status: str = "pending"
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "MultitenantMixin",
]


class MultitenantMixin(BaseModel):
    """Mixin that adds tenant_id to aggregates and entities.

    This mixin provides first-class tenant_id field support for multitenant
    applications. Use it together with AggregateRoot:

        class Order(MultitenantMixin, AggregateRoot[str]):
            customer_id: str
            status: str = "pending"

    The tenant_id field will be:
    - Validated by Pydantic
    - Serialized to database as a regular column
    - Automatically indexed for efficient filtering
    - Enforced by multitenancy repository mixins

    Attributes:
        tenant_id: The tenant identifier this entity belongs to

    Example:
        >>> order = Order(
        ...     id="order-123",
        ...     tenant_id="tenant-456",
        ...     customer_id="customer-789"
        ... )
        >>> order.tenant_id
        'tenant-456'
    """

    tenant_id: str = Field(
        ...,
        description="Tenant identifier for multitenant isolation",
        min_length=1,
        max_length=128,
        examples=["tenant-123", "acme-corp"],
    )

    def validate_tenant(self, expected_tenant: str) -> None:
        """Validate that this entity belongs to the expected tenant.

        Args:
            expected_tenant: The expected tenant ID

        Raises:
            ValueError: If tenant_id doesn't match
        """
        if self.tenant_id != expected_tenant:
            raise ValueError(
                f"Entity tenant_id '{self.tenant_id}' does not match "
                f"expected tenant '{expected_tenant}'"
            )
