"""Unit tests for MultitenantSnapshotMixin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.mixins.snapshots import MultitenantSnapshotMixin

# ── Test Doubles ───────────────────────────────────────────────────────


class MockSnapshotStore:
    """Mock base snapshot store for testing.

    Stores snapshots by (aggregate_type, aggregate_id) key.
    Supports basic tenant_id-based filtering when specification is provided.
    """

    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, Any], dict[str, Any]] = {}

    def _extract_tenant_from_spec(self, specification: Any | None) -> str | None:
        """Extract tenant_id from specification for filtering."""
        if specification is None:
            return None
        # Check AttributeSpecification
        if (
            hasattr(specification, "attr")
            and getattr(specification, "attr", None) == "tenant_id"
        ):
            return getattr(specification, "val", None)
        # Check composed specifications
        if hasattr(specification, "left"):
            left_tenant = self._extract_tenant_from_spec(specification.left)
            if left_tenant:
                return left_tenant
            return self._extract_tenant_from_spec(getattr(specification, "right", None))
        # Dict-based fallback
        if isinstance(specification, dict) and specification.get("attr") == "tenant_id":
            return specification.get("value")
        return None

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
        *,
        specification: Any | None = None,
    ) -> None:
        key = (aggregate_type, aggregate_id)
        self.snapshots[key] = {
            "snapshot_data": snapshot_data,
            "version": version,
            "created_at": "2024-01-01T00:00:00Z",
        }

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: Any | None = None,
    ) -> dict[str, Any] | None:
        key = (aggregate_type, aggregate_id)
        result = self.snapshots.get(key)
        if result is None:
            return None
        # Apply specification-based tenant filtering
        tenant_id = self._extract_tenant_from_spec(specification)
        if tenant_id is not None:
            snapshot_tenant = result.get("snapshot_data", {}).get("tenant_id")
            if snapshot_tenant is not None and snapshot_tenant != tenant_id:
                return None
        return result

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: Any | None = None,
    ) -> None:
        key = (aggregate_type, aggregate_id)
        # For simplicity in mock, only delete if tenant matches
        tenant_id = self._extract_tenant_from_spec(specification)
        if tenant_id is not None:
            existing = self.snapshots.get(key)
            if existing:
                snapshot_tenant = existing.get("snapshot_data", {}).get("tenant_id")
                if snapshot_tenant is not None and snapshot_tenant != tenant_id:
                    return  # Cross-tenant — don't delete
        self.snapshots.pop(key, None)


class TestMultitenantSnapshotStore(MultitenantSnapshotMixin, MockSnapshotStore):
    """Test implementation combining mixin with mock base."""


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def snapshot_store() -> TestMultitenantSnapshotStore:
    """Create test snapshot store."""
    return TestMultitenantSnapshotStore()


@pytest.fixture
def tenant_a() -> str:
    """Tenant A ID."""
    return "tenant-a"


@pytest.fixture
def tenant_b() -> str:
    """Tenant B ID."""
    return "tenant-b"


# ── Test Cases ──────────────────────────────────────────────────────────


class TestMultitenantSnapshotMixinSave:
    """Tests for save_snapshot() method."""

    @pytest.mark.asyncio
    async def test_save_snapshot_namespaces_by_tenant(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should store snapshot with tenant_id in data (specification-based)."""
        token = set_tenant(tenant_a)
        try:
            snapshot_data = {"status": "active", "amount": 100}

            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data=snapshot_data,
                version=5,
            )

            # Check that snapshot was stored with aggregate_type key (no namespacing)
            key = ("Order", "order-1")
            assert key in snapshot_store.snapshots
            assert snapshot_store.snapshots[key]["snapshot_data"]["status"] == "active"
            assert (
                snapshot_store.snapshots[key]["snapshot_data"]["tenant_id"] == tenant_a
            )
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_save_snapshot_injects_tenant_id(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should inject tenant_id into snapshot data."""
        token = set_tenant(tenant_a)
        try:
            snapshot_data = {"status": "active", "amount": 100}

            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data=snapshot_data,
                version=5,
            )

            key = ("Order", "order-1")
            assert (
                snapshot_store.snapshots[key]["snapshot_data"]["tenant_id"] == tenant_a
            )
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_save_snapshot_preserves_existing_tenant_id(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should preserve tenant_id if already in snapshot data."""
        token = set_tenant(tenant_a)
        try:
            snapshot_data = {"status": "active", "tenant_id": tenant_a}

            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data=snapshot_data,
                version=5,
            )

            key = ("Order", "order-1")
            assert (
                snapshot_store.snapshots[key]["snapshot_data"]["tenant_id"] == tenant_a
            )
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_save_snapshot_requires_tenant_context(
        self, snapshot_store: TestMultitenantSnapshotStore
    ) -> None:
        """Should require tenant context."""
        with pytest.raises(TenantContextMissingError):
            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data={"status": "active"},
                version=5,
            )


class TestMultitenantSnapshotMixinGet:
    """Tests for get_latest_snapshot() method."""

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_for_same_tenant(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should return snapshot for same tenant."""
        token = set_tenant(tenant_a)
        try:
            snapshot_data = {"status": "active", "tenant_id": tenant_a}

            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data=snapshot_data,
                version=5,
            )

            result = await snapshot_store.get_latest_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
            )

            assert result is not None
            assert result["snapshot_data"]["status"] == "active"
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_none_for_cross_tenant(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str, tenant_b: str
    ) -> None:
        """Should return None for cross-tenant access."""
        # Save snapshot for tenant_b
        token_b = set_tenant(tenant_b)
        await snapshot_store.save_snapshot(
            aggregate_type="Order",
            aggregate_id="order-1",
            snapshot_data={"status": "active", "tenant_id": tenant_b},
            version=5,
        )
        reset_tenant(token_b)

        # Try to access from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await snapshot_store.get_latest_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
            )

            assert result is None
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_none_for_not_found(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should return None if snapshot not found."""
        token = set_tenant(tenant_a)
        try:
            result = await snapshot_store.get_latest_snapshot(
                aggregate_type="Order",
                aggregate_id="nonexistent",
            )

            assert result is None
        finally:
            reset_tenant(token)


class TestMultitenantSnapshotMixinDelete:
    """Tests for delete_snapshot() method."""

    @pytest.mark.asyncio
    async def test_delete_snapshot_removes_for_same_tenant(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str
    ) -> None:
        """Should delete snapshot for same tenant."""
        token = set_tenant(tenant_a)
        try:
            snapshot_data = {"status": "active", "tenant_id": tenant_a}

            await snapshot_store.save_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
                snapshot_data=snapshot_data,
                version=5,
            )

            # Verify it exists
            key = ("Order", "order-1")
            assert key in snapshot_store.snapshots

            # Delete it
            await snapshot_store.delete_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
            )

            # Verify it's gone
            assert key not in snapshot_store.snapshots
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_delete_snapshot_namespaces_by_tenant(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str, tenant_b: str
    ) -> None:
        """Should only delete snapshot if tenant owns it."""
        # Save snapshot for tenant_b
        token_b = set_tenant(tenant_b)
        await snapshot_store.save_snapshot(
            aggregate_type="Order",
            aggregate_id="order-1",
            snapshot_data={"status": "active", "tenant_id": tenant_b},
            version=5,
        )
        reset_tenant(token_b)

        # Try to delete from tenant_a context
        token_a = set_tenant(tenant_a)
        await snapshot_store.delete_snapshot(
            aggregate_type="Order",
            aggregate_id="order-1",
        )
        reset_tenant(token_a)

        # Verify tenant_b's snapshot still exists (delete was a no-op for wrong tenant)
        key = ("Order", "order-1")
        assert key in snapshot_store.snapshots


class TestMultitenantSnapshotMixinTenantIsolation:
    """Tests for tenant isolation."""

    @pytest.mark.asyncio
    async def test_different_tenants_cannot_access_same_aggregate(
        self, snapshot_store: TestMultitenantSnapshotStore, tenant_a: str, tenant_b: str
    ) -> None:
        """Should prevent cross-tenant access to same aggregate ID."""
        # Tenant A saves snapshot
        token_a = set_tenant(tenant_a)
        await snapshot_store.save_snapshot(
            aggregate_type="Order",
            aggregate_id="order-1",
            snapshot_data={"status": "active", "tenant_id": tenant_a},
            version=5,
        )
        reset_tenant(token_a)

        # Tenant B tries to access
        token_b = set_tenant(tenant_b)
        try:
            result = await snapshot_store.get_latest_snapshot(
                aggregate_type="Order",
                aggregate_id="order-1",
            )

            # Should return None, not tenant A's snapshot
            assert result is None
        finally:
            reset_tenant(token_b)
