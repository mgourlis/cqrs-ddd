"""CQRS-DDD Multitenancy Module.

Provides tenant isolation for CQRS-DDD applications with:
- ContextVar-based tenant resolution
- Automatic query filtering via repository/store mixins
- Multiple isolation strategies (discriminator, schema, database)
- CQRS and FastAPI middleware integration
- Domain mixins for multitenant aggregates
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import (
    SYSTEM_TENANT,
    clear_tenant,
    get_current_tenant,
    get_current_tenant_or_none,
    is_system_tenant,
    require_tenant,
    reset_tenant,
    set_tenant,
    system_operation,
    with_tenant_context,
)

# Domain Mixins (RECOMMENDED for new projects)
from .domain import MultitenantMixin
from .exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
    TenantDeactivatedError,
    TenantError,
    TenantIsolationError,
    TenantNotFoundError,
    TenantProvisioningError,
)

# Phase 11: Infrastructure
from .infrastructure import (
    CompositeTenantHealthChecker,
    HealthStatus,
    MultitenantRedisCacheMixin,
    MultitenantRedisLockMixin,
    TenantHealthChecker,
    TenantHealthCheckResult,
    TenantMessagePropagator,
    extract_tenant_from_message,
    inject_tenant_to_message,
    with_tenant_from_message,
)
from .isolation import IsolationConfig, TenantIsolationStrategy

# CQRS Middleware
from .middleware import TenantMiddleware as CQRSTenantMiddleware

# Core Persistence Mixins
from .mixins import (
    MultitenantEventStoreMixin,
    MultitenantOutboxMixin,
    MultitenantRepositoryMixin,
    StrictMultitenantOutboxMixin,
    StrictMultitenantRepositoryMixin,
)

# Phase 10: Background Jobs
from .mixins.background_jobs import MultitenantBackgroundJobMixin

# Phase 9.5: Dispatcher & Persistence Mixins
from .mixins.dispatcher import MultitenantDispatcherMixin
from .mixins.persistence import (
    MultitenantOperationPersistenceMixin,
    MultitenantQueryPersistenceMixin,
    MultitenantQuerySpecificationPersistenceMixin,
    MultitenantRetrievalPersistenceMixin,
)

# Phase 9.5: Projection Mixins
from .mixins.projections import (
    MultitenantProjectionMixin,
    MultitenantProjectionPositionMixin,
)

# Phase 9: Advanced Persistence Mixins
from .mixins.saga import MultitenantSagaMixin
from .mixins.scheduling import MultitenantCommandSchedulerMixin
from .mixins.snapshots import MultitenantSnapshotMixin
from .mixins.upcasting import MultitenantUpcasterMixin

# Phase 13: Projections Engine Integration
from .projections import (
    MultitenantProjectionHandler,
    MultitenantReplayMixin,
    MultitenantWorkerMixin,
    TenantAwareProjectionRegistry,
)

# Resolvers
from .resolver import (
    CallableResolver,
    CompositeResolver,
    HeaderResolver,
    ITenantResolver,
    JwtClaimResolver,
    PathResolver,
    StaticResolver,
    SubdomainResolver,
)
from .workers.context import TenantAwareJobWorker, with_tenant_context_from_job

if TYPE_CHECKING:
    from .resolver import ITenantResolver

__all__ = [
    # Context
    "SYSTEM_TENANT",
    "get_current_tenant",
    "get_current_tenant_or_none",
    "set_tenant",
    "reset_tenant",
    "clear_tenant",
    "require_tenant",
    "is_system_tenant",
    "system_operation",
    "with_tenant_context",
    # Exceptions
    "TenantError",
    "TenantContextMissingError",
    "TenantNotFoundError",
    "TenantDeactivatedError",
    "CrossTenantAccessError",
    "TenantIsolationError",
    "TenantProvisioningError",
    # Isolation
    "TenantIsolationStrategy",
    "IsolationConfig",
    # Resolvers
    "CallableResolver",
    "CompositeResolver",
    "HeaderResolver",
    "ITenantResolver",
    "JwtClaimResolver",
    "PathResolver",
    "StaticResolver",
    "SubdomainResolver",
    # Domain Mixins (RECOMMENDED)
    "MultitenantMixin",
    # Phase 9: Advanced Persistence Mixins
    "MultitenantSagaMixin",
    "MultitenantSnapshotMixin",
    "MultitenantCommandSchedulerMixin",
    "MultitenantUpcasterMixin",
    # Phase 9.5: Dispatcher & Persistence Mixins
    "MultitenantDispatcherMixin",
    "MultitenantOperationPersistenceMixin",
    "MultitenantRetrievalPersistenceMixin",
    "MultitenantQueryPersistenceMixin",
    "MultitenantQuerySpecificationPersistenceMixin",
    # Phase 9.5: Projection Mixins
    "MultitenantProjectionMixin",
    "MultitenantProjectionPositionMixin",
    # Phase 10: Background Jobs
    "MultitenantBackgroundJobMixin",
    "TenantAwareJobWorker",
    "with_tenant_context_from_job",
    # Phase 11: Infrastructure
    "MultitenantRedisCacheMixin",
    "MultitenantRedisLockMixin",
    "HealthStatus",
    "TenantHealthCheckResult",
    "TenantHealthChecker",
    "CompositeTenantHealthChecker",
    "TenantMessagePropagator",
    "inject_tenant_to_message",
    "extract_tenant_from_message",
    "with_tenant_from_message",
    # Phase 13: Projections Engine Integration
    "MultitenantProjectionHandler",
    "MultitenantReplayMixin",
    "MultitenantWorkerMixin",
    "TenantAwareProjectionRegistry",
    # Core Persistence Mixins
    "MultitenantRepositoryMixin",
    "StrictMultitenantRepositoryMixin",
    "MultitenantEventStoreMixin",
    "MultitenantOutboxMixin",
    "StrictMultitenantOutboxMixin",
    # CQRS Middleware
    "CQRSTenantMiddleware",
    # Protocols (for typing)
    "ITenantResolver",
]

__version__ = "0.1.0"
