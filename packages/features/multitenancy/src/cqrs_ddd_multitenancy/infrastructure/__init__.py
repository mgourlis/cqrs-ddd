"""Infrastructure multitenancy support package.

Provides multitenancy mixins and utilities for infrastructure components:
- Redis cache with tenant namespacing
- Redis locks with tenant isolation
- Health checks for tenant-specific resources
- Message broker context propagation
"""

from __future__ import annotations

__all__ = [
    # Redis
    "MultitenantRedisCacheMixin",
    "MultitenantRedisLockMixin",
    # Health Checks
    "HealthStatus",
    "TenantHealthCheckResult",
    "TenantHealthChecker",
    "CompositeTenantHealthChecker",
    # Messaging
    "TenantMessagePropagator",
    "inject_tenant_to_message",
    "extract_tenant_from_message",
    "with_tenant_from_message",
]

from .health import (
    CompositeTenantHealthChecker,
    HealthStatus,
    TenantHealthChecker,
    TenantHealthCheckResult,
)
from .messaging import (
    TenantMessagePropagator,
    extract_tenant_from_message,
    inject_tenant_to_message,
    with_tenant_from_message,
)
from .redis.cache import MultitenantRedisCacheMixin
from .redis.locks import MultitenantRedisLockMixin
