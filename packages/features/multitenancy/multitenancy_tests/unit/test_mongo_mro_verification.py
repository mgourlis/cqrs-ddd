"""Phase 12 – Verify existing multitenancy mixins work with MongoDB adapters via MRO.

These tests confirm that MRO composition of MultitenantXxxMixin + MongoXxx
produces concrete classes whose methods resolve correctly and execute tenant
filtering using the specification parameter path already supported by
MongoRepository / MongoEventStore / etc.

**Key verification:** All generic mixins (not Mongo-specific workarounds) work
directly with MongoDB adapters via MRO, because MongoDB adapters now accept
``specification`` keyword-only parameters.

Uses mongomock-motor for functional verification without a real MongoDB instance.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import BaseModel

from cqrs_ddd_advanced_core.background_jobs.entity import (
    BackgroundJobStatus,
    BaseBackgroundJob,
)

# ── Domain models ────────────────────────────────────────────────────────
from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
from cqrs_ddd_core.ports.event_store import StoredEvent
from cqrs_ddd_core.ports.outbox import OutboxMessage

# ── Multitenancy mixins (GENERIC — no Mongo-specific workarounds) ────────
from cqrs_ddd_multitenancy import clear_tenant, set_tenant
from cqrs_ddd_multitenancy.context import system_operation
from cqrs_ddd_multitenancy.mixins import (
    MultitenantBackgroundJobMixin,
    MultitenantEventStoreMixin,
    MultitenantOutboxMixin,
    MultitenantProjectionMixin,
    MultitenantProjectionPositionMixin,
    MultitenantRepositoryMixin,
    MultitenantSagaMixin,
    MultitenantSnapshotMixin,
)

# ── Advanced MongoDB adapters ────────────────────────────────────────────
from cqrs_ddd_persistence_mongo.advanced.jobs import MongoBackgroundJobRepository
from cqrs_ddd_persistence_mongo.advanced.position_store import (
    MongoProjectionPositionStore,
)
from cqrs_ddd_persistence_mongo.advanced.projection_store import MongoProjectionStore
from cqrs_ddd_persistence_mongo.advanced.saga import MongoSagaRepository
from cqrs_ddd_persistence_mongo.advanced.snapshots import MongoSnapshotStore

# ── MongoDB imports ──────────────────────────────────────────────────────
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_persistence_mongo.core.event_store import MongoEventStore
from cqrs_ddd_persistence_mongo.core.outbox import MongoOutboxStorage
from cqrs_ddd_persistence_mongo.core.repository import MongoRepository


# ---------------------------------------------------------------------------
# Test Domain Model
# ---------------------------------------------------------------------------
class Order(BaseModel):
    id: str
    name: str
    tenant_id: str | None = None


# ---------------------------------------------------------------------------
# MRO Composed Classes — ALL use generic mixins (no Mongo-specific workarounds)
# ---------------------------------------------------------------------------
class TenantMongoRepo(MultitenantRepositoryMixin, MongoRepository[Order]):
    """Multitenant MongoDB repository via MRO."""


class TenantMongoEventStore(MultitenantEventStoreMixin, MongoEventStore):
    """Multitenant MongoDB event store via MRO."""


class TenantMongoOutbox(MultitenantOutboxMixin, MongoOutboxStorage):
    """Multitenant MongoDB outbox via generic MRO (specification path)."""


class TenantMongoSagaRepo(MultitenantSagaMixin, MongoSagaRepository):
    """Multitenant MongoDB saga repository via MRO."""


class TenantMongoJobRepo(MultitenantBackgroundJobMixin, MongoBackgroundJobRepository):
    """Multitenant MongoDB background job repository via MRO."""


class TenantMongoProjectionStore(MultitenantProjectionMixin, MongoProjectionStore):
    """Multitenant MongoDB projection store via MRO."""


class TenantMongoPositionStore(
    MultitenantProjectionPositionMixin, MongoProjectionPositionStore
):
    """Multitenant MongoDB projection position store via MRO."""


class TenantMongoSnapshotStore(MultitenantSnapshotMixin, MongoSnapshotStore):
    """Multitenant MongoDB snapshot store via generic MRO (specification path)."""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _clear_tenant():
    """Auto-clear tenant context after each test."""
    yield
    clear_tenant()


@pytest.fixture
def mongo_connection():
    """Create a mongomock-motor connection for testing."""
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    mgr = MongoConnectionManager.__new__(MongoConnectionManager)
    mgr._client = client
    mgr._url = "mongodb://mock"
    mgr._database = "test_db"
    return mgr


@pytest.fixture
def tenant_repo(mongo_connection: MongoConnectionManager) -> TenantMongoRepo:
    return TenantMongoRepo(
        connection=mongo_connection,
        collection="orders",
        model_cls=Order,
        database="test_db",
    )


@pytest.fixture
def tenant_event_store(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoEventStore:
    return TenantMongoEventStore(
        connection=mongo_connection,
        database="test_db",
    )


@pytest.fixture
def tenant_outbox(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoOutbox:
    return TenantMongoOutbox(
        connection=mongo_connection,
        database="test_db",
    )


@pytest.fixture
def tenant_saga_repo(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoSagaRepo:
    return TenantMongoSagaRepo(
        connection=mongo_connection,
        collection="sagas",
        database="test_db",
    )


@pytest.fixture
def tenant_job_repo(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoJobRepo:
    return TenantMongoJobRepo(
        connection=mongo_connection,
        collection="background_jobs",
        database="test_db",
    )


@pytest.fixture
def tenant_projection_store(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoProjectionStore:
    return TenantMongoProjectionStore(
        connection=mongo_connection,
        database="test_db",
    )


@pytest.fixture
def tenant_position_store(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoPositionStore:
    return TenantMongoPositionStore(
        connection=mongo_connection,
        database="test_db",
    )


@pytest.fixture
def tenant_snapshot_store(
    mongo_connection: MongoConnectionManager,
) -> TenantMongoSnapshotStore:
    return TenantMongoSnapshotStore(
        connection=mongo_connection,
        database="test_db",
    )


# =========================================================================
# Tests: MRO Resolution Verification
# =========================================================================


class TestMROClassComposition:
    """Verify that MRO composed classes resolve methods correctly.

    All compositions use GENERIC mixins — no Mongo-specific workarounds needed.
    """

    def test_repository_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoRepo.__mro__]
        repo_idx = mro.index("MultitenantRepositoryMixin")
        mongo_idx = mro.index("MongoRepository")
        assert repo_idx < mongo_idx, "Mixin must precede MongoRepository in MRO"

    def test_event_store_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoEventStore.__mro__]
        mixin_idx = mro.index("MultitenantEventStoreMixin")
        mongo_idx = mro.index("MongoEventStore")
        assert mixin_idx < mongo_idx

    def test_saga_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoSagaRepo.__mro__]
        mixin_idx = mro.index("MultitenantSagaMixin")
        mongo_idx = mro.index("MongoSagaRepository")
        assert mixin_idx < mongo_idx

    def test_job_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoJobRepo.__mro__]
        mixin_idx = mro.index("MultitenantBackgroundJobMixin")
        mongo_idx = mro.index("MongoBackgroundJobRepository")
        assert mixin_idx < mongo_idx

    def test_outbox_mro_order(self):
        """Generic MultitenantOutboxMixin precedes MongoOutboxStorage."""
        mro = [cls.__name__ for cls in TenantMongoOutbox.__mro__]
        mixin_idx = mro.index("MultitenantOutboxMixin")
        mongo_idx = mro.index("MongoOutboxStorage")
        assert mixin_idx < mongo_idx

    def test_projection_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoProjectionStore.__mro__]
        mixin_idx = mro.index("MultitenantProjectionMixin")
        mongo_idx = mro.index("MongoProjectionStore")
        assert mixin_idx < mongo_idx

    def test_position_store_mro_order(self):
        mro = [cls.__name__ for cls in TenantMongoPositionStore.__mro__]
        mixin_idx = mro.index("MultitenantProjectionPositionMixin")
        mongo_idx = mro.index("MongoProjectionPositionStore")
        assert mixin_idx < mongo_idx

    def test_snapshot_mro_order(self):
        """Generic MultitenantSnapshotMixin precedes MongoSnapshotStore."""
        mro = [cls.__name__ for cls in TenantMongoSnapshotStore.__mro__]
        mixin_idx = mro.index("MultitenantSnapshotMixin")
        mongo_idx = mro.index("MongoSnapshotStore")
        assert mixin_idx < mongo_idx


# =========================================================================
# Tests: Repository Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoRepository:
    """Verify MultitenantRepositoryMixin + MongoRepository works end-to-end."""

    async def test_add_injects_tenant(self, tenant_repo: TenantMongoRepo):
        set_tenant("tenant-a")
        order = Order(id="o1", name="Widget")
        await tenant_repo.add(order)
        result = await tenant_repo.get("o1")
        assert result is not None
        assert result.tenant_id == "tenant-a"

    async def test_get_filters_by_tenant(self, tenant_repo: TenantMongoRepo):
        set_tenant("tenant-a")
        await tenant_repo.add(Order(id="o1", name="A-Widget"))
        set_tenant("tenant-b")
        # Tenant B should not see Tenant A's order
        result = await tenant_repo.get("o1")
        assert result is None

    async def test_list_all_filters_by_tenant(self, tenant_repo: TenantMongoRepo):
        set_tenant("tenant-a")
        await tenant_repo.add(Order(id="o1", name="A1"))
        await tenant_repo.add(Order(id="o2", name="A2"))
        set_tenant("tenant-b")
        await tenant_repo.add(Order(id="o3", name="B1"))

        # Should only see tenant-b's order
        results = await tenant_repo.list_all()
        assert len(results) == 1
        assert results[0].id == "o3"

    async def test_delete_scoped_to_tenant(self, tenant_repo: TenantMongoRepo):
        set_tenant("tenant-a")
        await tenant_repo.add(Order(id="o1", name="Widget"))
        set_tenant("tenant-b")
        # Cross-tenant delete should fail silently (no match)
        await tenant_repo.delete("o1")
        set_tenant("tenant-a")
        # Order should still exist for tenant-a
        result = await tenant_repo.get("o1")
        assert result is not None

    async def test_system_tenant_bypass(self, tenant_repo: TenantMongoRepo):
        """System tenant can access all entities without filtering."""
        set_tenant("tenant-a")
        await tenant_repo.add(Order(id="o1", name="A"))
        set_tenant("tenant-b")
        await tenant_repo.add(Order(id="o2", name="B"))

        @system_operation
        async def list_all():
            return await tenant_repo.list_all()

        results = await list_all()
        assert len(results) == 2


# =========================================================================
# Tests: Event Store Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoEventStore:
    """Verify MultitenantEventStoreMixin + MongoEventStore works end-to-end."""

    async def test_append_injects_tenant(
        self, tenant_event_store: TenantMongoEventStore
    ):
        set_tenant("tenant-a")
        event = StoredEvent(
            event_id=str(uuid.uuid4()),
            event_type="OrderCreated",
            aggregate_id="agg-1",
            aggregate_type="Order",
            version=1,
            payload={"name": "test"},
        )
        await tenant_event_store.append(event)
        events = await tenant_event_store.get_events("agg-1")
        assert len(events) == 1
        assert events[0].tenant_id == "tenant-a"

    async def test_get_events_filters_by_tenant(
        self, tenant_event_store: TenantMongoEventStore
    ):
        set_tenant("tenant-a")
        await tenant_event_store.append(
            StoredEvent(
                event_type="OrderCreated",
                aggregate_id="agg-1",
                aggregate_type="Order",
                version=1,
            )
        )
        set_tenant("tenant-b")
        events = await tenant_event_store.get_events("agg-1")
        assert len(events) == 0

    async def test_get_all_filters_by_tenant(
        self, tenant_event_store: TenantMongoEventStore
    ):
        set_tenant("tenant-a")
        await tenant_event_store.append(
            StoredEvent(
                event_type="OrderCreated",
                aggregate_id="agg-1",
                aggregate_type="Order",
                version=1,
            )
        )
        set_tenant("tenant-b")
        await tenant_event_store.append(
            StoredEvent(
                event_type="OrderUpdated",
                aggregate_id="agg-2",
                aggregate_type="Order",
                version=1,
            )
        )
        # tenant-b should only see its own events
        events = await tenant_event_store.get_all()
        assert len(events) == 1
        assert events[0].aggregate_id == "agg-2"


# =========================================================================
# Tests: Outbox Functional Verification (GENERIC mixin, not workaround)
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoOutbox:
    """Verify generic MultitenantOutboxMixin + MongoOutboxStorage works end-to-end.

    Uses specification-based DB-level filtering (not in-memory post-filtering).
    """

    async def test_save_injects_tenant(self, tenant_outbox: TenantMongoOutbox):
        set_tenant("tenant-a")
        msg = OutboxMessage(
            message_id="m1",
            event_type="OrderCreated",
            payload={"id": "o1"},
            correlation_id="corr-1",
        )
        await tenant_outbox.save_messages([msg])
        pending = await tenant_outbox.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].tenant_id == "tenant-a"

    async def test_get_pending_filters_by_tenant(
        self, tenant_outbox: TenantMongoOutbox
    ):
        set_tenant("tenant-a")
        await tenant_outbox.save_messages(
            [
                OutboxMessage(
                    message_id="m1",
                    event_type="E1",
                    payload={},
                    correlation_id="c1",
                )
            ]
        )
        set_tenant("tenant-b")
        await tenant_outbox.save_messages(
            [
                OutboxMessage(
                    message_id="m2",
                    event_type="E2",
                    payload={},
                    correlation_id="c2",
                )
            ]
        )
        # Tenant-b should only see its own message
        pending = await tenant_outbox.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].message_id == "m2"

    async def test_mark_published_with_tenant(self, tenant_outbox: TenantMongoOutbox):
        set_tenant("tenant-a")
        await tenant_outbox.save_messages(
            [
                OutboxMessage(
                    message_id="m1",
                    event_type="E1",
                    payload={},
                    correlation_id="c1",
                )
            ]
        )
        await tenant_outbox.mark_published(["m1"])
        pending = await tenant_outbox.get_pending(limit=10)
        assert len(pending) == 0


# =========================================================================
# Tests: Projection Store Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoProjectionStore:
    """Verify MultitenantProjectionMixin + MongoProjectionStore works end-to-end."""

    async def test_upsert_and_get_with_tenant(
        self, tenant_projection_store: TenantMongoProjectionStore
    ):
        set_tenant("tenant-a")
        data = {"name": "Order Summary", "total": 100}
        await tenant_projection_store.upsert("order_summaries", "os-1", data)
        result = await tenant_projection_store.get("order_summaries", "os-1")
        assert result is not None
        assert result.get("tenant_id") == "tenant-a"

    async def test_get_filters_by_tenant(
        self, tenant_projection_store: TenantMongoProjectionStore
    ):
        set_tenant("tenant-a")
        await tenant_projection_store.upsert("order_summaries", "os-1", {"name": "A"})
        set_tenant("tenant-b")
        result = await tenant_projection_store.get("order_summaries", "os-1")
        assert result is None

    async def test_delete_scoped_to_tenant(
        self, tenant_projection_store: TenantMongoProjectionStore
    ):
        set_tenant("tenant-a")
        await tenant_projection_store.upsert("order_summaries", "os-1", {"name": "A"})
        set_tenant("tenant-b")
        # Cross-tenant delete should not affect tenant-a's data
        await tenant_projection_store.delete("order_summaries", "os-1")
        set_tenant("tenant-a")
        result = await tenant_projection_store.get("order_summaries", "os-1")
        assert result is not None


# =========================================================================
# Tests: Position Store Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoPositionStore:
    """Verify MultitenantProjectionPositionMixin + MongoProjectionPositionStore."""

    async def test_save_and_get_position(
        self, tenant_position_store: TenantMongoPositionStore
    ):
        set_tenant("tenant-a")
        await tenant_position_store.save_position("my_projection", 42)
        pos = await tenant_position_store.get_position("my_projection")
        assert pos == 42

    async def test_positions_isolated_by_tenant(
        self, tenant_position_store: TenantMongoPositionStore
    ):
        set_tenant("tenant-a")
        await tenant_position_store.save_position("proj", 10)
        set_tenant("tenant-b")
        await tenant_position_store.save_position("proj", 20)
        # Each tenant sees its own position
        set_tenant("tenant-a")
        assert await tenant_position_store.get_position("proj") == 10
        set_tenant("tenant-b")
        assert await tenant_position_store.get_position("proj") == 20


# =========================================================================
# Tests: Snapshot Store Functional Verification (GENERIC mixin)
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoSnapshotStore:
    """Verify generic MultitenantSnapshotMixin + MongoSnapshotStore works.

    Uses specification-based DB-level filtering (not key-namespacing workaround).
    """

    async def test_save_and_get_snapshot(
        self, tenant_snapshot_store: TenantMongoSnapshotStore
    ):
        set_tenant("tenant-a")
        await tenant_snapshot_store.save_snapshot(
            "Order", "agg-1", {"name": "test"}, version=5
        )
        result = await tenant_snapshot_store.get_latest_snapshot("Order", "agg-1")
        assert result is not None
        assert result["version"] == 5

    async def test_snapshots_isolated_by_tenant(
        self, tenant_snapshot_store: TenantMongoSnapshotStore
    ):
        """Snapshot isolation via specification-based filtering."""
        set_tenant("tenant-a")
        await tenant_snapshot_store.save_snapshot(
            "Order", "agg-1", {"name": "A"}, version=1
        )
        set_tenant("tenant-b")
        # tenant-b should NOT see tenant-a's snapshot via spec filtering
        result = await tenant_snapshot_store.get_latest_snapshot("Order", "agg-1")
        assert result is None

    async def test_delete_snapshot_scoped_to_tenant(
        self, tenant_snapshot_store: TenantMongoSnapshotStore
    ):
        set_tenant("tenant-a")
        await tenant_snapshot_store.save_snapshot(
            "Order", "agg-1", {"name": "A"}, version=1
        )
        set_tenant("tenant-b")
        # Cross-tenant delete should not affect tenant-a's snapshot
        await tenant_snapshot_store.delete_snapshot("Order", "agg-1")
        set_tenant("tenant-a")
        result = await tenant_snapshot_store.get_latest_snapshot("Order", "agg-1")
        assert result is not None


# =========================================================================
# Tests: Saga Repository Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoSagaRepo:
    """Verify MultitenantSagaMixin + MongoSagaRepository works end-to-end."""

    async def test_add_injects_tenant(self, tenant_saga_repo: TenantMongoSagaRepo):
        set_tenant("tenant-a")
        saga = SagaState(
            id="saga-1",
            saga_type="OrderSaga",
            correlation_id="corr-1",
            status=SagaStatus.RUNNING,
        )
        await tenant_saga_repo.add(saga)
        result = await tenant_saga_repo.get("saga-1")
        assert result is not None
        assert result.tenant_id == "tenant-a"

    async def test_get_filters_by_tenant(self, tenant_saga_repo: TenantMongoSagaRepo):
        set_tenant("tenant-a")
        await tenant_saga_repo.add(
            SagaState(
                id="saga-1",
                saga_type="OrderSaga",
                correlation_id="corr-1",
                status=SagaStatus.RUNNING,
            )
        )
        set_tenant("tenant-b")
        result = await tenant_saga_repo.get("saga-1")
        assert result is None

    async def test_list_all_filters_by_tenant(
        self, tenant_saga_repo: TenantMongoSagaRepo
    ):
        set_tenant("tenant-a")
        await tenant_saga_repo.add(
            SagaState(
                id="saga-1",
                saga_type="OrderSaga",
                correlation_id="c1",
                status=SagaStatus.RUNNING,
            )
        )
        set_tenant("tenant-b")
        await tenant_saga_repo.add(
            SagaState(
                id="saga-2",
                saga_type="OrderSaga",
                correlation_id="c2",
                status=SagaStatus.RUNNING,
            )
        )
        results = await tenant_saga_repo.list_all()
        assert len(results) == 1
        assert results[0].id == "saga-2"

    async def test_find_stalled_sagas_filtered_by_tenant(
        self, tenant_saga_repo: TenantMongoSagaRepo
    ):
        """find_stalled_sagas passes tenant specification to Mongo adapter."""
        set_tenant("tenant-a")
        stalled_a = SagaState(
            id="saga-stalled-a",
            saga_type="OrderSaga",
            correlation_id="c1",
            status=SagaStatus.RUNNING,
        )
        # Simulate stalled by setting updated_at far in the past
        object.__setattr__(
            stalled_a, "updated_at", datetime.now(timezone.utc) - timedelta(hours=2)
        )
        await tenant_saga_repo.add(stalled_a)

        set_tenant("tenant-b")
        stalled_b = SagaState(
            id="saga-stalled-b",
            saga_type="OrderSaga",
            correlation_id="c2",
            status=SagaStatus.RUNNING,
        )
        object.__setattr__(
            stalled_b, "updated_at", datetime.now(timezone.utc) - timedelta(hours=2)
        )
        await tenant_saga_repo.add(stalled_b)

        # tenant-b should only see its own stalled sagas
        results = await tenant_saga_repo.find_stalled_sagas(limit=10)
        assert all(r.tenant_id == "tenant-b" for r in results)


# =========================================================================
# Tests: Background Job Repository Functional Verification
# =========================================================================


@pytest.mark.usefixtures("_clear_tenant")
class TestMultitenantMongoJobRepo:
    """Verify MultitenantBackgroundJobMixin + MongoBackgroundJobRepository."""

    async def test_add_injects_tenant(self, tenant_job_repo: TenantMongoJobRepo):
        set_tenant("tenant-a")
        job = BaseBackgroundJob(
            id="job-1",
            job_type="ProcessOrder",
            payload={"order_id": "o1"},
        )
        await tenant_job_repo.add(job)
        result = await tenant_job_repo.get("job-1")
        assert result is not None
        assert result.tenant_id == "tenant-a"

    async def test_get_filters_by_tenant(self, tenant_job_repo: TenantMongoJobRepo):
        set_tenant("tenant-a")
        await tenant_job_repo.add(
            BaseBackgroundJob(
                id="job-1",
                job_type="ProcessOrder",
                payload={},
            )
        )
        set_tenant("tenant-b")
        result = await tenant_job_repo.get("job-1")
        assert result is None

    async def test_find_by_status_filtered_by_tenant(
        self, tenant_job_repo: TenantMongoJobRepo
    ):
        """find_by_status passes tenant specification to Mongo adapter."""
        set_tenant("tenant-a")
        await tenant_job_repo.add(
            BaseBackgroundJob(
                id="job-a",
                job_type="ProcessOrder",
                payload={},
            )
        )
        set_tenant("tenant-b")
        await tenant_job_repo.add(
            BaseBackgroundJob(
                id="job-b",
                job_type="ProcessOrder",
                payload={},
            )
        )
        # tenant-b should find only its own pending jobs
        results = await tenant_job_repo.find_by_status(
            [BackgroundJobStatus.PENDING], limit=50
        )
        assert len(results) == 1
        assert results[0].id == "job-b"

    async def test_count_by_status_filtered_by_tenant(
        self, tenant_job_repo: TenantMongoJobRepo
    ):
        """count_by_status passes tenant specification to Mongo adapter."""
        set_tenant("tenant-a")
        await tenant_job_repo.add(BaseBackgroundJob(id="j1", job_type="T", payload={}))
        await tenant_job_repo.add(BaseBackgroundJob(id="j2", job_type="T", payload={}))
        set_tenant("tenant-b")
        await tenant_job_repo.add(BaseBackgroundJob(id="j3", job_type="T", payload={}))
        counts = await tenant_job_repo.count_by_status()
        # tenant-b should see only 1 pending job
        assert counts.get(BackgroundJobStatus.PENDING.value, 0) == 1
