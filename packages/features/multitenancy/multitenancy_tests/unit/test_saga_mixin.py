"""Unit tests for MultitenantSagaMixin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_advanced_core.sagas.state import (
    SagaState,
    SagaStatus,
)
from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
)
from cqrs_ddd_multitenancy.mixins.saga import MultitenantSagaMixin

# ── Test Doubles ───────────────────────────────────────────────────────


class MockSagaRepository:
    """Mock base saga repository for testing."""

    def __init__(self) -> None:
        self.added_sagas: list[SagaState] = []
        self.updated_sagas: list[SagaState] = []
        self.deleted_sagas: list[SagaState] = []
        self.sagas: dict[str, SagaState] = {}

    async def add(self, saga_state: SagaState) -> None:
        self.added_sagas.append(saga_state)
        self.sagas[saga_state.id] = saga_state

    async def get(self, saga_id: str) -> SagaState | None:
        return self.sagas.get(saga_id)

    async def update(self, saga_state: SagaState) -> None:
        self.updated_sagas.append(saga_state)
        self.sagas[saga_state.id] = saga_state

    async def delete(self, saga_state: SagaState) -> None:
        self.deleted_sagas.append(saga_state)
        self.sagas.pop(saga_state.id, None)

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[SagaState]:
        sagas = list(self.sagas.values())
        if entity_ids is not None:
            sagas = [s for s in sagas if s.id in entity_ids]
        if specification is not None:
            sagas = [s for s in sagas if specification.is_satisfied_by(s)]
        return sagas

    async def search(
        self, specification: Any, limit: int | None = None, offset: int | None = None
    ):
        """Mock search that returns SearchResult."""
        from cqrs_ddd_core.ports.search_result import SearchResult

        # Simple filtering for mock
        all_sagas = list(self.sagas.values())

        # For testing, we'll just return filtered by tenant_id
        if hasattr(specification, "right") and hasattr(specification.right, "val"):
            tenant_id = specification.right.val
            filtered = [
                s for s in all_sagas if getattr(s, "tenant_id", None) == tenant_id
            ]
        else:
            filtered = all_sagas

        if offset:
            filtered = filtered[offset:]
        if limit:
            filtered = filtered[:limit]

        result = MagicMock(spec=SearchResult)
        result.list = AsyncMock(return_value=filtered)
        return result

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        for saga in self.sagas.values():
            if saga.correlation_id == correlation_id and saga.saga_type == saga_type:
                return saga
        return None

    async def find_stalled_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        result = [s for s in self.sagas.values() if s.status == SagaStatus.RUNNING]
        if specification is not None:
            result = [s for s in result if specification.is_satisfied_by(s)]
        return result[:limit]

    async def find_suspended_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        result = [s for s in self.sagas.values() if s.status == SagaStatus.SUSPENDED]
        if specification is not None:
            result = [s for s in result if specification.is_satisfied_by(s)]
        return result[:limit]

    async def find_expired_suspended_sagas(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        now = datetime.now(timezone.utc)
        result = [
            s
            for s in self.sagas.values()
            if s.status == SagaStatus.SUSPENDED and s.timeout_at and s.timeout_at < now
        ]
        if specification is not None:
            result = [s for s in result if specification.is_satisfied_by(s)]
        return result[:limit]

    async def find_running_sagas_with_tcc_steps(
        self, limit: int = 10, *, specification: Any | None = None
    ) -> list[SagaState]:
        result = [
            s
            for s in self.sagas.values()
            if s.status == SagaStatus.RUNNING and s.tcc_steps
        ]
        if specification is not None:
            result = [s for s in result if specification.is_satisfied_by(s)]
        return result[:limit]


class TestMultitenantSagaRepository(MultitenantSagaMixin, MockSagaRepository):
    """Test implementation combining mixin with mock base."""


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def saga_repo() -> TestMultitenantSagaRepository:
    """Create test saga repository."""
    return TestMultitenantSagaRepository()


@pytest.fixture
def tenant_a() -> str:
    """Tenant A ID."""
    return "tenant-a"


@pytest.fixture
def tenant_b() -> str:
    """Tenant B ID."""
    return "tenant-b"


@pytest.fixture
def saga_state_a(tenant_a: str) -> SagaState:
    """Create saga state for tenant A."""
    return SagaState(
        id="saga-1",
        saga_type="OrderSaga",
        status=SagaStatus.RUNNING,
        correlation_id="corr-1",
        metadata={"tenant_id": tenant_a},
    )


@pytest.fixture
def saga_state_b(tenant_b: str) -> SagaState:
    """Create saga state for tenant B."""
    return SagaState(
        id="saga-2",
        saga_type="OrderSaga",
        status=SagaStatus.RUNNING,
        correlation_id="corr-2",
        metadata={"tenant_id": tenant_b},
    )


# ── Test Cases ──────────────────────────────────────────────────────────


class TestMultitenantSagaMixinAdd:
    """Tests for add() method."""

    @pytest.mark.asyncio
    async def test_add_injects_tenant_id(
        self, saga_repo: TestMultitenantSagaRepository, tenant_a: str
    ) -> None:
        """Should inject tenant_id into saga state metadata."""
        token = set_tenant(tenant_a)
        try:
            saga_state = SagaState(
                id="saga-new",
                saga_type="OrderSaga",
                status=SagaStatus.PENDING,
                correlation_id="corr-new",
            )

            await saga_repo.add(saga_state)

            assert len(saga_repo.added_sagas) == 1
            assert saga_repo.added_sagas[0].metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_preserves_existing_tenant_id(
        self, saga_repo: TestMultitenantSagaRepository, tenant_a: str
    ) -> None:
        """Should preserve tenant_id if already set in metadata."""
        token = set_tenant(tenant_a)
        try:
            saga_state = SagaState(
                id="saga-new",
                saga_type="OrderSaga",
                status=SagaStatus.PENDING,
                correlation_id="corr-new",
                metadata={"tenant_id": tenant_a},
            )

            await saga_repo.add(saga_state)

            assert saga_repo.added_sagas[0].metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_rejects_cross_tenant(
        self, saga_repo: TestMultitenantSagaRepository, tenant_a: str, tenant_b: str
    ) -> None:
        """Should reject saga belonging to different tenant."""
        token = set_tenant(tenant_a)
        try:
            saga_state = SagaState(
                id="saga-new",
                saga_type="OrderSaga",
                status=SagaStatus.PENDING,
                correlation_id="corr-new",
                metadata={"tenant_id": tenant_b},
            )

            with pytest.raises(CrossTenantAccessError):
                await saga_repo.add(saga_state)

            assert len(saga_repo.added_sagas) == 0
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_requires_tenant_context(
        self, saga_repo: TestMultitenantSagaRepository
    ) -> None:
        """Should require tenant context."""
        saga_state = SagaState(
            id="saga-new",
            saga_type="OrderSaga",
            status=SagaStatus.PENDING,
            correlation_id="corr-new",
        )

        with pytest.raises(TenantContextMissingError):
            await saga_repo.add(saga_state)


class TestMultitenantSagaMixinGet:
    """Tests for get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_saga_for_same_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_a: SagaState,
        tenant_a: str,
    ) -> None:
        """Should return saga belonging to current tenant."""
        token = set_tenant(tenant_a)
        try:
            await saga_repo.add(saga_state_a)
            result = await saga_repo.get(saga_state_a.id)

            assert result is not None
            assert result.id == saga_state_a.id
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_returns_none_for_cross_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_b: SagaState,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should return None for cross-tenant access (silent denial)."""
        # Add saga in tenant_b's context
        token_b = set_tenant(tenant_b)
        await saga_repo.add(saga_state_b)
        reset_tenant(token_b)

        # Try to access from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await saga_repo.get(saga_state_b.id)

            assert result is None
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_get_returns_none_for_not_found(
        self, saga_repo: TestMultitenantSagaRepository, tenant_a: str
    ) -> None:
        """Should return None if saga not found."""
        token = set_tenant(tenant_a)
        try:
            result = await saga_repo.get("nonexistent")
            assert result is None
        finally:
            reset_tenant(token)


class TestMultitenantSagaMixinUpdate:
    """Tests for update() method."""

    @pytest.mark.asyncio
    async def test_update_allows_same_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_a: SagaState,
        tenant_a: str,
    ) -> None:
        """Should allow updating saga in same tenant."""
        token = set_tenant(tenant_a)
        try:
            await saga_repo.add(saga_state_a)
            saga_state_a.status = SagaStatus.COMPLETED
            await saga_repo.update(saga_state_a)

            assert len(saga_repo.updated_sagas) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_update_rejects_cross_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_b: SagaState,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should reject updating saga from different tenant."""
        # Add saga in tenant_b's context
        token_b = set_tenant(tenant_b)
        await saga_repo.add(saga_state_b)
        reset_tenant(token_b)

        # Try to update from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            with pytest.raises(CrossTenantAccessError):
                await saga_repo.update(saga_state_b)

            assert len(saga_repo.updated_sagas) == 0
        finally:
            reset_tenant(token_a)


class TestMultitenantSagaMixinDelete:
    """Tests for delete() method."""

    @pytest.mark.asyncio
    async def test_delete_allows_same_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_a: SagaState,
        tenant_a: str,
    ) -> None:
        """Should allow deleting saga in same tenant."""
        token = set_tenant(tenant_a)
        try:
            await saga_repo.add(saga_state_a)
            await saga_repo.delete(saga_state_a)

            assert len(saga_repo.deleted_sagas) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_delete_rejects_cross_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_b: SagaState,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should reject deleting saga from different tenant."""
        # Add saga in tenant_b's context
        token_b = set_tenant(tenant_b)
        await saga_repo.add(saga_state_b)
        reset_tenant(token_b)

        # Try to delete from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            with pytest.raises(CrossTenantAccessError):
                await saga_repo.delete(saga_state_b)

            assert len(saga_repo.deleted_sagas) == 0
        finally:
            reset_tenant(token_a)


class TestMultitenantSagaMixinFindByCorrelationId:
    """Tests for find_by_correlation_id() method."""

    @pytest.mark.asyncio
    async def test_find_by_correlation_id_filters_by_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_a: SagaState,
        tenant_a: str,
    ) -> None:
        """Should find saga by correlation ID in same tenant."""
        token = set_tenant(tenant_a)
        try:
            await saga_repo.add(saga_state_a)
            result = await saga_repo.find_by_correlation_id(
                saga_state_a.correlation_id, saga_state_a.saga_type
            )

            assert result is not None
            assert result.id == saga_state_a.id
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_find_by_correlation_id_returns_none_for_cross_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_b: SagaState,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should return None for cross-tenant correlation ID lookup."""
        # Add saga in tenant_b's context
        token_b = set_tenant(tenant_b)
        await saga_repo.add(saga_state_b)
        reset_tenant(token_b)

        # Try to access from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await saga_repo.find_by_correlation_id(
                saga_state_b.correlation_id, saga_state_b.saga_type
            )

            assert result is None
        finally:
            reset_tenant(token_a)


class TestMultitenantSagaMixinQueryMethods:
    """Tests for query methods (find_stalled, find_suspended, etc.)."""

    @pytest.mark.asyncio
    async def test_find_stalled_sagas_filters_by_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        saga_state_a: SagaState,
        saga_state_b: SagaState,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should filter stalled sagas by tenant."""
        # Add saga for tenant_a
        token_a = set_tenant(tenant_a)
        await saga_repo.add(saga_state_a)
        reset_tenant(token_a)

        # Add saga for tenant_b
        token_b = set_tenant(tenant_b)
        await saga_repo.add(saga_state_b)
        reset_tenant(token_b)

        # Query from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await saga_repo.find_stalled_sagas()

            # Should only return sagas for tenant_a
            assert all(s.metadata.get("tenant_id") == tenant_a for s in result)
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_find_suspended_sagas_filters_by_tenant(
        self,
        saga_repo: TestMultitenantSagaRepository,
        tenant_a: str,
    ) -> None:
        """Should filter suspended sagas by tenant."""
        token = set_tenant(tenant_a)
        try:
            # Add suspended saga for tenant_a
            saga_a = SagaState(
                id="saga-suspended-a",
                saga_type="OrderSaga",
                status=SagaStatus.SUSPENDED,
                correlation_id="corr-suspended-a",
                metadata={"tenant_id": tenant_a},
            )
            await saga_repo.add(saga_a)

            result = await saga_repo.find_suspended_sagas()

            assert len(result) == 1
            assert result[0].metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)
