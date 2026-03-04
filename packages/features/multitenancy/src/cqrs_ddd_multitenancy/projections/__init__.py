"""Multitenancy projections engine integration.

Provides tenant-aware wrappers for projection handlers, registries,
and replay engines. These components extract tenant context from events
and ensure handlers execute within the correct tenant scope.

Components:
    - ``MultitenantProjectionHandler``  — wraps any ``IProjectionHandler`` to
      set tenant context from the event before dispatching.
    - ``TenantAwareProjectionRegistry`` — wraps any ``IProjectionRegistry`` so
      every returned handler is automatically tenant-context-aware.
    - ``MultitenantReplayMixin``  — mixin for ``ReplayEngine`` that sets tenant
      context per event during replay.
    - ``MultitenantWorkerMixin``  — mixin for ``ProjectionWorker`` that sets
      tenant context per event during polling.

Usage::

    from cqrs_ddd_multitenancy.projections import (
        TenantAwareProjectionRegistry,
        MultitenantReplayMixin,
        MultitenantWorkerMixin,
    )

    # Wrap existing registry
    registry = TenantAwareProjectionRegistry(ProjectionRegistry())

    # Tenant-aware replay engine (MRO composition)
    class TenantReplayEngine(MultitenantReplayMixin, ReplayEngine):
        pass

    # Tenant-aware worker (MRO composition)
    class TenantProjectionWorker(MultitenantWorkerMixin, ProjectionWorker):
        pass
"""

from __future__ import annotations

from .handler import MultitenantProjectionHandler
from .registry import TenantAwareProjectionRegistry
from .replay import MultitenantReplayMixin
from .worker import MultitenantWorkerMixin

__all__ = [
    "MultitenantProjectionHandler",
    "MultitenantReplayMixin",
    "MultitenantWorkerMixin",
    "TenantAwareProjectionRegistry",
]
