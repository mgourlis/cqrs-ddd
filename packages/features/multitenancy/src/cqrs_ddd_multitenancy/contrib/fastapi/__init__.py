"""FastAPI integration for multitenancy."""

from __future__ import annotations

__all__ = [
    "TenantMiddleware",
    "TenantContextMiddleware",
    "get_current_tenant_dep",
    "require_tenant_dep",
    "get_tenant_or_none_dep",
]

from .middleware import (
    TenantContextMiddleware,
    TenantMiddleware,
    get_current_tenant_dep,
    get_tenant_or_none_dep,
    require_tenant_dep,
)
