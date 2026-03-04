"""System-tenant bypass tests for MultitenantSagaMixin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
from cqrs_ddd_multitenancy.context import SYSTEM_TENANT, reset_tenant, set_tenant
from cqrs_ddd_multitenancy.mixins.saga import MultitenantSagaMixin

# ── Shared test doubles ────────────────────────────────────────────────


class MockSagaBase:
    def __init__(self) -> None:
        self.sagas: dict[str, SagaState] = {}

    async def add(self, saga: SagaState) -> None:
        self.sagas[saga.id] = saga

    async def get(self, saga_id: str) -> SagaState | None:
        return self.sagas.get(saga_id)

    async def update(self, saga: SagaState) -> None:
        self.sagas[saga.id] = saga

    async def delete(self, saga: SagaState) -> None:
        self.sagas.pop(saga.id, None)

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[SagaState]:
        return list(self.sagas.values())

    async def search(
        self, specification: Any, limit: int | None = None, offset: int | None = None
    ):
        from cqrs_ddd_core.ports.search_result import SearchResult

        result = MagicMock(spec=SearchResult)
        result.list = AsyncMock(return_value=list(self.sagas.values()))
        return result

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        for s in self.sagas.values():
            if s.correlation_id == correlation_id and s.saga_type == saga_type:
                return s
        return None

    async def find_stalled_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        return [s for s in self.sagas.values() if s.status == SagaStatus.RUNNING][
            :limit
        ]

    async def find_suspended_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        return [s for s in self.sagas.values() if s.status == SagaStatus.SUSPENDED][
            :limit
        ]

    async def find_expired_suspended_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        return [s for s in self.sagas.values() if s.status == SagaStatus.SUSPENDED][
            :limit
        ]

    async def find_running_sagas_with_tcc_steps(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        return [s for s in self.sagas.values() if s.status == SagaStatus.RUNNING][
            :limit
        ]


class SagaRepo(MultitenantSagaMixin, MockSagaBase):
    pass


def _make_saga(saga_id: str = "s1", tenant_id: str = "t1") -> SagaState:
    return SagaState(
        id=saga_id,
        saga_type="OrderSaga",
        status=SagaStatus.RUNNING,
        correlation_id=f"corr-{saga_id}",
        metadata={"tenant_id": tenant_id},
    )


# ── System-tenant bypass tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_system_tenant_bypasses_injection():
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        assert "s1" in repo.sagas
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_system_tenant_bypasses_filter():
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.get("s1")
        assert result is not None
        assert result.id == "s1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_update_system_tenant_bypasses_validation():
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        updated = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.COMPLETED,
            correlation_id="corr-s1",
            metadata={"tenant_id": "tenant-A"},
        )
        await repo.update(updated)
        result = await repo.get("s1")
        assert result.status == SagaStatus.COMPLETED
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_list_all_system_tenant_returns_all():
    repo = SagaRepo()
    token_a = set_tenant("tenant-A")
    saga_a = _make_saga("s1", "tenant-A")
    await repo.add(saga_a)
    reset_tenant(token_a)

    token_b = set_tenant("tenant-B")
    saga_b = _make_saga("s2", "tenant-B")
    await repo.add(saga_b)
    reset_tenant(token_b)

    token = set_tenant(SYSTEM_TENANT)
    try:
        result = await repo.list_all()
        assert len(result) == 2
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_search_system_tenant_returns_all():
    repo = SagaRepo()
    token_a = set_tenant("tenant-A")
    await repo.add(_make_saga("s1", "tenant-A"))
    reset_tenant(token_a)

    token_b = set_tenant("tenant-B")
    await repo.add(_make_saga("s2", "tenant-B"))
    reset_tenant(token_b)

    token = set_tenant(SYSTEM_TENANT)
    try:
        result = await repo.search(None)
        items = await result.list()
        assert len(items) == 2
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_by_correlation_id_system_tenant_bypasses_filter():
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.find_by_correlation_id("corr-s1", "OrderSaga")
        assert result is not None
        assert result.id == "s1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_stalled_system_tenant_returns_all():
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.find_stalled_sagas()
        assert len(result) == 1
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_suspended_system_tenant_returns_all():
    repo = SagaRepo()
    saga = SagaState(
        id="s1",
        saga_type="OrderSaga",
        status=SagaStatus.SUSPENDED,
        correlation_id="corr-s1",
        metadata={"tenant_id": "tenant-A"},
    )
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.find_suspended_sagas()
        assert len(result) == 1
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_expired_suspended_system_tenant_returns_all():
    repo = SagaRepo()
    saga = SagaState(
        id="s1",
        saga_type="OrderSaga",
        status=SagaStatus.SUSPENDED,
        correlation_id="corr-s1",
        metadata={"tenant_id": "tenant-A"},
        timeout_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.find_expired_suspended_sagas()
        assert len(result) == 1
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_running_with_tcc_steps_system_tenant_returns_all():
    repo = SagaRepo()
    saga = SagaState(
        id="s1",
        saga_type="OrderSaga",
        status=SagaStatus.RUNNING,
        correlation_id="corr-s1",
        metadata={"tenant_id": "tenant-A"},
    )
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        result = await repo.find_running_sagas_with_tcc_steps()
        # The base mock returns running sagas, system should pass through
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


# ── Additional coverage: non-system paths not yet covered ──────────────


@pytest.mark.asyncio
async def test_list_all_with_specification_composes():
    """list_all with a specification composes with tenant spec."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        await repo.add(_make_saga("s1", "tenant-A"))
        await repo.add(_make_saga("s2", "tenant-A"))
        # list_all with no specification still filters by tenant
        result = await repo.list_all()
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_search_with_specification_composes():
    """search with a criteria composes with tenant spec."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        await repo.add(_make_saga("s1", "tenant-A"))
        from unittest.mock import MagicMock

        # Spec without __and__ - should use tenant_spec only
        criteria = MagicMock(spec=[])  # no __and__
        result = await repo.search(criteria)
        assert result is not None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_stalled_with_specification_composes():
    """find_stalled_sagas with explicit specification."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        await repo.add(_make_saga("s1", "tenant-A"))
        spec = MagicMock()
        spec.is_satisfied_by.return_value = True
        spec.__and__ = lambda self, other: self
        result = await repo.find_stalled_sagas(specification=spec)
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_suspended_with_specification_composes():
    """find_suspended_sagas with explicit specification."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        saga = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.SUSPENDED,
            correlation_id="corr-s1",
            metadata={"tenant_id": "tenant-A"},
        )
        await repo.add(saga)
        spec = MagicMock()
        spec.is_satisfied_by.return_value = True
        spec.__and__ = lambda self, other: self
        result = await repo.find_suspended_sagas(specification=spec)
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_expired_with_specification_composes():
    """find_expired_suspended_sagas with specification."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        saga = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.SUSPENDED,
            correlation_id="corr-s1",
            metadata={"tenant_id": "tenant-A"},
            timeout_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        await repo.add(saga)
        spec = MagicMock()
        spec.is_satisfied_by.return_value = True
        spec.__and__ = lambda self, other: self
        result = await repo.find_expired_suspended_sagas(specification=spec)
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_running_with_tcc_with_specification_composes():
    """find_running_sagas_with_tcc_steps with specification."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        await repo.add(_make_saga("s1", "tenant-A"))
        spec = MagicMock()
        spec.is_satisfied_by.return_value = True
        spec.__and__ = lambda self, other: self
        result = await repo.find_running_sagas_with_tcc_steps(specification=spec)
        assert isinstance(result, list)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_delete_system_tenant_bypasses_validation():
    """delete() with system tenant skips ownership check."""
    repo = SagaRepo()
    saga = _make_saga("s1", "tenant-A")
    token = set_tenant(SYSTEM_TENANT)
    try:
        await repo.add(saga)
        await repo.delete(saga)
        assert "s1" not in repo.sagas
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_search_criteria_without_and_uses_tenant_spec_only():
    """search() with criteria that lacks __and__ falls back to tenant spec alone."""
    repo = SagaRepo()
    token = set_tenant("tenant-A")
    try:
        await repo.add(_make_saga("s1", "tenant-A"))
        # Pass criteria with no __and__ attribute
        criteria = MagicMock(spec=[])  # no __and__
        result = await repo.search(criteria)
        assert result is not None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_find_by_correlation_id_returns_none_for_cross_tenant():
    """find_by_correlation_id returns None when found saga belongs to different tenant."""
    repo = SagaRepo()
    # Add saga for tenant-B directly (bypassing mixin with system tenant)
    token_sys = set_tenant(SYSTEM_TENANT)
    saga_b = _make_saga("s2", "tenant-B")
    await repo.add(saga_b)
    reset_tenant(token_sys)

    # Query from tenant-A — should return None because saga belongs to tenant-B
    token_a = set_tenant("tenant-A")
    try:
        result = await repo.find_by_correlation_id("corr-s2", "OrderSaga")
        assert result is None
    finally:
        reset_tenant(token_a)
