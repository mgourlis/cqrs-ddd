"""Multitenancy mixins package.

Provides mixins for tenant-aware repository, event store, outbox, and advanced
persistence implementations (sagas, snapshots, scheduling, upcasting, background jobs,
dispatcher, persistence interfaces, and projections).
"""

from __future__ import annotations

__all__ = [
    # Core Mixins (Phases 1-8)
    "MultitenantRepositoryMixin",
    "StrictMultitenantRepositoryMixin",
    "MultitenantEventStoreMixin",
    "MultitenantOutboxMixin",
    "StrictMultitenantOutboxMixin",
    # Advanced Persistence Mixins (Phase 9)
    "MultitenantSagaMixin",
    "MultitenantSnapshotMixin",
    "MultitenantCommandSchedulerMixin",
    "MultitenantUpcasterMixin",
    # Background Jobs Mixins (Phase 10)
    "MultitenantBackgroundJobMixin",
    # Dispatcher & Persistence Mixins (Phase 9.5)
    "MultitenantDispatcherMixin",
    "MultitenantOperationPersistenceMixin",
    "MultitenantRetrievalPersistenceMixin",
    "MultitenantQueryPersistenceMixin",
    "MultitenantQuerySpecificationPersistenceMixin",
    # Projection Mixins (Phase 9.5)
    "MultitenantProjectionMixin",
    "MultitenantProjectionPositionMixin",
]

from .background_jobs import MultitenantBackgroundJobMixin
from .dispatcher import MultitenantDispatcherMixin
from .event_store import MultitenantEventStoreMixin
from .outbox import MultitenantOutboxMixin, StrictMultitenantOutboxMixin
from .persistence import (
    MultitenantOperationPersistenceMixin,
    MultitenantQueryPersistenceMixin,
    MultitenantQuerySpecificationPersistenceMixin,
    MultitenantRetrievalPersistenceMixin,
)
from .projections import MultitenantProjectionMixin, MultitenantProjectionPositionMixin
from .repository import MultitenantRepositoryMixin, StrictMultitenantRepositoryMixin
from .saga import MultitenantSagaMixin
from .scheduling import MultitenantCommandSchedulerMixin
from .snapshots import MultitenantSnapshotMixin
from .upcasting import MultitenantUpcasterMixin
