"""SecurityConstraintInjector — append tenant, auth, soft-filter constraints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_specifications.ast import AttributeSpecification
from cqrs_ddd_specifications.base import AndSpecification
from cqrs_ddd_specifications.evaluator import MemoryOperatorRegistry
from cqrs_ddd_specifications.operators import SpecificationOperator

from .exceptions import SecurityConstraintError

if TYPE_CHECKING:
    from collections.abc import Callable


class SecurityConstraintInjector:
    """Appends mandatory constraints before query execution."""

    def __init__(
        self,
        registry: MemoryOperatorRegistry,
        *,
        get_tenant_id: Callable[[], str | None] | None = None,
        get_owner_id: Callable[[], str | None] | None = None,
        tenant_field: str = "tenant_id",
        owner_field: str = "owner_id",
        require_tenant: bool = True,
    ) -> None:
        """
        Initialize SecurityConstraintInjector.
        
        Args:
            registry: MemoryOperatorRegistry for creating specifications.
            get_tenant_id: Callable that returns current tenant ID.
            get_owner_id: Callable that returns current owner ID.
            tenant_field: Field name for tenant constraint.
            owner_field: Field name for owner constraint.
            require_tenant: Raise error if tenant_id is None.
        """
        if registry is None:
            raise ValueError(
                "registry parameter is required. "
                "Use build_default_registry() from cqrs_ddd_specifications.operators_memory "
                "to create one."
            )
        self._registry = registry
        self._get_tenant_id = get_tenant_id
        self._get_owner_id = get_owner_id
        self._tenant_field = tenant_field
        self._owner_field = owner_field
        self._require_tenant = require_tenant

    def inject(self, spec: Any) -> Any:
        """Return spec AND tenant constraint (and optionally owner)."""
        constraints: list[Any] = []
        if self._get_tenant_id:
            tenant = self._get_tenant_id()
            if tenant is not None:
                constraints.append(
                    AttributeSpecification(
                        self._tenant_field,
                        SpecificationOperator.EQ,
                        tenant,
                        registry=self._registry,
                    )
                )
            elif self._require_tenant:
                raise SecurityConstraintError("Tenant context is required")
        if self._get_owner_id:
            owner = self._get_owner_id()
            if owner is not None:
                constraints.append(
                    AttributeSpecification(
                        self._owner_field,
                        SpecificationOperator.EQ,
                        owner,
                        registry=self._registry,
                    )
                )
        if not constraints:
            return spec
        result = spec
        for c in constraints:
            result = AndSpecification(result, c) if result is not None else c
        return result
