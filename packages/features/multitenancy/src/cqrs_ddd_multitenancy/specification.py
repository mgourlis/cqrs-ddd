"""Tenant-aware specification for query filtering.

Provides specification helpers for filtering queries by tenant ID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from .context import get_current_tenant, get_current_tenant_or_none, is_system_tenant

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification

__all__ = [
    "MetadataTenantSpecification",
    "TenantSpecification",
    "with_tenant_filter",
    "create_tenant_specification",
]

T = TypeVar("T")

_SENTINEL = object()


class MetadataTenantSpecification:
    """A specification that filters by tenant_id across different entity types.

    This spec works with both SQL models (via ``to_dict()``) and in-memory
    domain objects (via ``is_satisfied_by()``).

    For SQL:
        ``to_dict()`` returns ``{"attr": "tenant_id", "op": "eq", "val": ...}``
        which ``build_sqla_filter`` translates to ``WHERE tenant_id = ?``.

    For in-memory:
        ``is_satisfied_by()`` resolves tenant_id from:
        1. Direct attribute (e.g. ``OutboxMessage.tenant_id``)
        2. Metadata dict (e.g. ``SagaState.metadata["tenant_id"]``)

    Supports specification composition via ``&`` / ``|`` / ``~`` operators
    when ``cqrs-ddd-specifications`` is installed.
    """

    def __init__(
        self,
        tenant_id: str,
        *,
        tenant_column: str = "tenant_id",
        metadata_key: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._tenant_column = tenant_column
        self._metadata_key = metadata_key or tenant_column

    def is_satisfied_by(self, candidate: Any) -> bool:
        """Check if candidate belongs to the target tenant.

        Resolution order:
        1. Direct attribute (``getattr(candidate, tenant_column)``)
        2. Metadata dict (``candidate.metadata.get(metadata_key)``)
        3. Private metadata dict (``candidate._metadata.get(metadata_key)``)
        """
        # 1. Direct attribute
        val = getattr(candidate, self._tenant_column, _SENTINEL)
        if val is not _SENTINEL and val is not None:
            return val == self._tenant_id

        # 2. Metadata dict
        metadata = getattr(candidate, "metadata", None)
        if isinstance(metadata, dict):
            mval = metadata.get(self._metadata_key)
            if mval is not None:
                return mval == self._tenant_id  # type: ignore[no-any-return]

        # 3. Private metadata dict (e.g. Command._metadata)
        private_metadata = getattr(candidate, "_metadata", None)
        if isinstance(private_metadata, dict):
            mval = private_metadata.get(self._metadata_key)
            if mval is not None:
                return mval == self._tenant_id  # type: ignore[no-any-return]

        return False

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation for SQL-level filtering."""
        return {
            "attr": self._tenant_column,
            "op": "eq",
            "val": self._tenant_id,
        }

    def __and__(self, other: Any) -> Any:
        try:
            from cqrs_ddd_specifications.base import AndSpecification

            return AndSpecification(self, other)
        except ImportError:
            return self

    def __or__(self, other: Any) -> Any:
        try:
            from cqrs_ddd_specifications.base import OrSpecification

            return OrSpecification(self, other)
        except ImportError:
            return self

    def __invert__(self) -> Any:
        try:
            from cqrs_ddd_specifications.base import NotSpecification

            return NotSpecification(self)
        except ImportError:
            return self

    def __repr__(self) -> str:
        return (
            f"MetadataTenantSpecification("
            f"tenant_id={self._tenant_id!r}, "
            f"tenant_column={self._tenant_column!r})"
        )


def create_tenant_specification(
    tenant_id: str,
    tenant_column: str = "tenant_id",
    registry: Any = None,
) -> ISpecification[T]:  # type: ignore[type-var]
    """Create a specification that filters by tenant ID.

    This function creates an AttributeSpecification for the tenant column.
    Requires cqrs-ddd-specifications package.

    Args:
        tenant_id: The tenant ID to filter by.
        tenant_column: The column name for tenant filtering.
        registry: The MemoryOperatorRegistry for evaluation.

    Returns:
        An ISpecification that filters by tenant_id.

    Raises:
        ImportError: If cqrs-ddd-specifications is not installed.
    """
    try:
        from cqrs_ddd_specifications.ast import AttributeSpecification
        from cqrs_ddd_specifications.operators import SpecificationOperator
    except ImportError as e:
        raise ImportError(
            "cqrs-ddd-specifications is required for TenantSpecification. "
            "Install with: pip install cqrs-ddd-multitenancy[specifications]"
        ) from e

    return AttributeSpecification(  # type: ignore[return-value]
        attr=tenant_column,
        op=SpecificationOperator.EQ,
        val=tenant_id,
        registry=registry,
    )


class TenantSpecification:
    """Factory for creating tenant filter specifications.

    This class provides factory methods for creating tenant-aware
    specifications that can be composed with other specifications.

    Note:
        This is a factory class, not a specification itself.
        Use the class methods to create actual specifications.

    Example:
        ```python
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()

        # Create tenant spec for current tenant
        spec = TenantSpecification.for_current_tenant(
            registry=registry,
            tenant_column="tenant_id",
        )

        # Create for specific tenant
        spec = TenantSpecification.for_tenant(
            tenant_id="tenant-123",
            registry=registry,
        )
        ```
    """

    @classmethod
    def for_current_tenant(
        cls,
        registry: Any,
        *,
        tenant_column: str = "tenant_id",
    ) -> ISpecification[T]:  # type: ignore[type-var]
        """Create a specification for the current tenant context.

        Args:
            registry: The MemoryOperatorRegistry for evaluation.
            tenant_column: The column name for tenant filtering.

        Returns:
            An ISpecification filtering by the current tenant.

        Raises:
            TenantContextMissingError: If no tenant is in context.
        """
        tenant_id = get_current_tenant()
        return create_tenant_specification(tenant_id, tenant_column, registry)

    @classmethod
    def for_tenant(
        cls,
        tenant_id: str,
        registry: Any,
        *,
        tenant_column: str = "tenant_id",
    ) -> ISpecification[T]:  # type: ignore[type-var]
        """Create a specification for a specific tenant.

        Args:
            tenant_id: The tenant ID to filter by.
            registry: The MemoryOperatorRegistry for evaluation.
            tenant_column: The column name for tenant filtering.

        Returns:
            An ISpecification filtering by the specified tenant.
        """
        return create_tenant_specification(tenant_id, tenant_column, registry)

    @classmethod
    def for_current_tenant_or_none(
        cls,
        registry: Any,
        *,
        tenant_column: str = "tenant_id",
    ) -> ISpecification[T] | None:  # type: ignore[type-var]
        """Create a specification for the current tenant, or None if not set.

        Args:
            registry: The MemoryOperatorRegistry for evaluation.
            tenant_column: The column name for tenant filtering.

        Returns:
            An ISpecification filtering by current tenant, or None.
        """
        tenant_id = get_current_tenant_or_none()
        if tenant_id is None:
            return None
        return create_tenant_specification(tenant_id, tenant_column, registry)


def with_tenant_filter(
    spec: ISpecification[T] | None,  # type: ignore[type-var]
    registry: Any,
    *,
    tenant_column: str = "tenant_id",
    tenant_id: str | None = None,
) -> ISpecification[T]:  # type: ignore[type-var]
    """Compose a specification with tenant filtering.

    If the current context is SYSTEM_TENANT, returns the original spec
    without adding tenant filtering (allows cross-tenant queries).

    Args:
        spec: The original specification (can be None).
        registry: The MemoryOperatorRegistry for evaluation.
        tenant_column: The column name for tenant filtering.
        tenant_id: Specific tenant ID (uses current context if None).

    Returns:
        A specification with tenant filtering applied, or the original
        if in system context.

    Raises:
        TenantContextMissingError: If no tenant in context and not system.

    Example:
        ```python
        # Combine business spec with tenant filter
        business_spec = AttributeSpecification("status", "eq", "active", registry=reg)
        combined = with_tenant_filter(business_spec, registry=reg)

        # Create tenant-only filter
        tenant_only = with_tenant_filter(None, registry=reg)
        ```
    """
    # System tenant bypasses filtering
    if is_system_tenant():
        if spec is None:
            # Create a pass-through spec (all records)
            from cqrs_ddd_specifications.base import BaseSpecification

            class PassthroughSpec(BaseSpecification[T]):  # type: ignore[type-var]
                def is_satisfied_by(self, candidate: T) -> bool:
                    return True

                def to_dict(self) -> dict[str, Any]:
                    return {}

            return PassthroughSpec()
        return spec

    # Get tenant ID
    effective_tenant = tenant_id if tenant_id is not None else get_current_tenant()
    tenant_spec: Any = create_tenant_specification(
        effective_tenant, tenant_column, registry
    )

    # Combine with original spec
    if spec is None:
        return tenant_spec  # type: ignore[no-any-return]

    # Use AND composition
    return tenant_spec & spec  # type: ignore[no-any-return]


def build_tenant_filter_dict(
    tenant_id: str | None = None,
    tenant_column: str = "tenant_id",
) -> dict[str, Any]:
    """Build a filter dictionary for tenant ID.

    This is useful for direct SQLAlchemy query building without
    using the specification pattern.

    Args:
        tenant_id: The tenant ID (uses current context if None).
        tenant_column: The column name for tenant filtering.

    Returns:
        A dictionary suitable for use with build_sqla_filter.

    Example:
        ```python
        filter_dict = build_tenant_filter_dict()
        # Returns: {"attr": "tenant_id", "op": "=", "val": "tenant-123"}
        ```
    """
    effective_tenant = (
        tenant_id if tenant_id is not None else get_current_tenant_or_none()
    )

    if effective_tenant is None:
        return {}

    return {
        "attr": tenant_column,
        "op": "=",
        "val": effective_tenant,
    }
