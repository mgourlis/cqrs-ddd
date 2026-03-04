"""Unit tests for multitenant projection mixins.

Tests cover:
- MultitenantProjectionMixin
- MultitenantProjectionPositionMixin
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_multitenancy import (
    MultitenantProjectionMixin,
    MultitenantProjectionPositionMixin,
    reset_tenant,
    set_tenant,
)
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError

# ============================================================================
# Test Fixtures
# ============================================================================


class BaseMockProjectionStore:
    """Base mock projection store for testing."""

    def __init__(self):
        self.storage: dict[str, dict[str, Any]] = {}

    async def get(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        *,
        uow=None,
    ) -> dict[str, Any] | None:
        key = f"{collection}:{doc_id}"
        return self.storage.get(key)

    async def get_batch(
        self,
        collection: str,
        doc_ids: list[str | int | dict[str, Any]],
        *,
        uow=None,
    ) -> list[dict[str, Any] | None]:
        return [await self.get(collection, doc_id, uow=uow) for doc_id in doc_ids]

    async def find(
        self,
        collection: str,
        filter_dict: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow=None,
    ) -> list[dict[str, Any]]:
        results = []
        for key, doc in self.storage.items():
            if key.startswith(f"{collection}:"):
                # Simple filter matching
                match = all(doc.get(k) == v for k, v in filter_dict.items())
                if match:
                    results.append(doc)
        return results[offset : offset + limit]

    async def upsert(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        data: dict[str, Any] | Any,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow=None,
    ) -> bool:
        key = f"{collection}:{doc_id}"
        if isinstance(data, dict):
            self.storage[key] = data.copy()
        else:
            self.storage[key] = {"data": data}
        return True

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str = "id",
        uow=None,
    ) -> None:
        for doc in docs:
            doc_id = doc.get(id_field) if isinstance(doc, dict) else None
            if doc_id:
                await self.upsert(collection, doc_id, doc, uow=uow)

    async def delete(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        *,
        cascade: bool = False,
        uow=None,
    ) -> None:
        key = f"{collection}:{doc_id}"
        self.storage.pop(key, None)


class MockProjectionStore(MultitenantProjectionMixin, BaseMockProjectionStore):
    """Mock projection store with multitenant mixin.

    MRO: MultitenantProjectionMixin -> BaseMockProjectionStore
    """


class BaseMockPositionStore:
    """Base implementation for a simple in-memory position store."""

    def __init__(self):
        self.positions: dict[str, int] = {}

    async def get_position(
        self,
        projection_name: str,
        *,
        uow=None,
    ) -> int | None:
        return self.positions.get(projection_name)

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow=None,
    ) -> None:
        self.positions[projection_name] = position

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow=None,
    ) -> None:
        self.positions.pop(projection_name, None)


class MockPositionStore(MultitenantProjectionPositionMixin, BaseMockPositionStore):
    """Mock position store with tenant-namespacing.

    MRO: MultitenantProjectionPositionMixin -> BaseMockPositionStore
    """


# ============================================================================
# MultitenantProjectionMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantProjectionMixin:
    """Test suite for MultitenantProjectionMixin."""

    async def test_get_with_tenant_namespace(self):
        """Test that get() uses tenant-namespaced document ID."""
        store = MockProjectionStore()

        # Setup test data
        token = set_tenant("tenant-123")
        try:
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})

            # Verify it's stored with tenant prefix
            assert "summaries:tenant-123:order-1" in store.storage

            # Get should return the document
            result = await store.get("summaries", "order-1")
            assert result is not None
            assert result["id"] == "order-1"
            assert result["tenant_id"] == "tenant-123"
        finally:
            reset_tenant(token)

    async def test_get_blocks_cross_tenant_access(self):
        """Test that get() blocks access to other tenant's documents."""
        store = MockProjectionStore()

        # Insert document for tenant-123
        token1 = set_tenant("tenant-123")
        try:
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})
        finally:
            reset_tenant(token1)

        # Try to access from tenant-456
        token2 = set_tenant("tenant-456")
        try:
            result = await store.get("summaries", "order-1")
            # Should return None (not found for this tenant)
            assert result is None
        finally:
            reset_tenant(token2)

    async def test_get_requires_tenant_context(self):
        """Test that get() raises error without tenant context."""
        store = MockProjectionStore()

        with pytest.raises(TenantContextMissingError):
            await store.get("summaries", "order-1")

    async def test_get_batch_with_tenant_filtering(self):
        """Test that get_batch() filters by tenant."""
        store = MockProjectionStore()

        # Insert documents for multiple tenants
        token1 = set_tenant("tenant-123")
        try:
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})
            await store.upsert("summaries", "order-2", {"id": "order-2", "total": 200})
        finally:
            reset_tenant(token1)

        token2 = set_tenant("tenant-456")
        try:
            await store.upsert("summaries", "order-3", {"id": "order-3", "total": 300})
        finally:
            reset_tenant(token2)

        # Get batch for tenant-123
        token3 = set_tenant("tenant-123")
        try:
            results = await store.get_batch(
                "summaries", ["order-1", "order-2", "order-3"]
            )

            # Should only get documents for tenant-123
            assert len(results) == 3
            assert results[0] is not None
            assert results[1] is not None
            assert results[2] is None  # Different tenant
        finally:
            reset_tenant(token3)

    async def test_find_adds_tenant_filter(self):
        """Test that find() adds tenant_id to filter."""
        store = MockProjectionStore()

        # Insert documents for multiple tenants
        token1 = set_tenant("tenant-123")
        try:
            await store.upsert(
                "summaries",
                "order-1",
                {"id": "order-1", "status": "active", "total": 100},
            )
            await store.upsert(
                "summaries",
                "order-2",
                {"id": "order-2", "status": "active", "total": 200},
            )
        finally:
            reset_tenant(token1)

        token2 = set_tenant("tenant-456")
        try:
            await store.upsert(
                "summaries",
                "order-3",
                {"id": "order-3", "status": "active", "total": 300},
            )
        finally:
            reset_tenant(token2)

        # Find for tenant-123
        token3 = set_tenant("tenant-123")
        try:
            results = await store.find("summaries", {"status": "active"})

            # Should only get documents for tenant-123
            assert len(results) == 2
            assert all(r["tenant_id"] == "tenant-123" for r in results)
        finally:
            reset_tenant(token3)

    async def test_upsert_injects_tenant_id(self):
        """Test that upsert() injects tenant_id into data."""
        store = MockProjectionStore()

        token = set_tenant("tenant-123")
        try:
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})

            # Verify tenant_id was injected
            key = "summaries:tenant-123:order-1"
            assert key in store.storage
            assert store.storage[key]["tenant_id"] == "tenant-123"
        finally:
            reset_tenant(token)

    async def test_upsert_batch_injects_tenant_id(self):
        """Test that upsert_batch() injects tenant_id into all documents."""
        store = MockProjectionStore()

        token = set_tenant("tenant-123")
        try:
            docs = [
                {"id": "order-1", "total": 100},
                {"id": "order-2", "total": 200},
            ]
            await store.upsert_batch("summaries", docs)

            # Verify all documents have tenant_id
            for key, doc in store.storage.items():
                assert "tenant-123" in key
                assert doc["tenant_id"] == "tenant-123"
        finally:
            reset_tenant(token)

    async def test_delete_with_tenant_namespace(self):
        """Test that delete() uses tenant-namespaced document ID."""
        store = MockProjectionStore()

        token = set_tenant("tenant-123")
        try:
            # Insert document
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})
            assert "summaries:tenant-123:order-1" in store.storage

            # Delete document
            await store.delete("summaries", "order-1")

            # Verify it was deleted
            assert "summaries:tenant-123:order-1" not in store.storage
        finally:
            reset_tenant(token)

    async def test_composite_key_handling(self):
        """Test that composite document IDs work correctly."""
        store = MockProjectionStore()

        token = set_tenant("tenant-123")
        try:
            # Use composite key
            composite_id = {"order_id": "order-1", "item_id": "item-5"}
            await store.upsert("items", composite_id, {"quantity": 10})

            # Should have tenant_id in composite key
            assert "tenant_id" in composite_id
        finally:
            reset_tenant(token)


# ============================================================================
# MultitenantProjectionPositionMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantProjectionPositionMixin:
    """Test suite for MultitenantProjectionPositionMixin."""

    async def test_get_position_with_tenant_namespace(self):
        """Test that get_position() uses tenant-namespaced projection name."""
        store = MockPositionStore()

        token = set_tenant("tenant-123")
        try:
            # Save position
            await store.save_position("order_summary", 42)

            # Verify it's stored with tenant prefix
            assert "tenant-123:order_summary" in store.positions

            # Get should return the position
            position = await store.get_position("order_summary")
            assert position == 42
        finally:
            reset_tenant(token)

    async def test_positions_isolated_by_tenant(self):
        """Test that positions are isolated between tenants."""
        store = MockPositionStore()

        # Save position for tenant-123
        token1 = set_tenant("tenant-123")
        try:
            await store.save_position("order_summary", 42)
        finally:
            reset_tenant(token1)

        # Save position for tenant-456
        token2 = set_tenant("tenant-456")
        try:
            await store.save_position("order_summary", 99)
        finally:
            reset_tenant(token2)

        # Verify tenant-123's position is isolated
        token3 = set_tenant("tenant-123")
        try:
            position = await store.get_position("order_summary")
            assert position == 42  # Not 99
        finally:
            reset_tenant(token3)

    async def test_save_position_requires_tenant_context(self):
        """Test that save_position() raises error without tenant context."""
        store = MockPositionStore()

        with pytest.raises(TenantContextMissingError):
            await store.save_position("order_summary", 42)

    async def test_reset_position_with_tenant_namespace(self):
        """Test that reset_position() uses tenant-namespaced projection name."""
        store = MockPositionStore()

        token = set_tenant("tenant-123")
        try:
            # Save position
            await store.save_position("order_summary", 42)
            assert "tenant-123:order_summary" in store.positions

            # Reset position
            await store.reset_position("order_summary")

            # Verify it was deleted
            assert "tenant-123:order_summary" not in store.positions
        finally:
            reset_tenant(token)

    async def test_get_position_returns_none_for_missing(self):
        """Test that get_position() returns None for missing positions."""
        store = MockPositionStore()

        token = set_tenant("tenant-123")
        try:
            position = await store.get_position("nonexistent")
            assert position is None
        finally:
            reset_tenant(token)


# ============================================================================
# Integration Tests (MRO Pattern)
# ============================================================================


@pytest.mark.asyncio
class TestProjectionMROPattern:
    """Test that MRO composition pattern works correctly for projections."""

    async def test_projection_store_mro_composition(self):
        """Test that MultitenantProjectionMixin works in MRO chain."""

        class BaseProjectionStore:
            def __init__(self):
                self.storage = {}

            async def get(self, collection, doc_id, *, uow=None):
                key = f"{collection}:{doc_id}"
                return self.storage.get(key)

            async def upsert(self, collection, doc_id, data, **kwargs):
                key = f"{collection}:{doc_id}"
                self.storage[key] = data
                return True

        class TenantAwareProjectionStore(
            MultitenantProjectionMixin, BaseProjectionStore
        ):
            pass

        store = TenantAwareProjectionStore()

        token = set_tenant("tenant-123")
        try:
            # Upsert should inject tenant_id
            await store.upsert("summaries", "order-1", {"id": "order-1", "total": 100})

            # Verify tenant namespace in storage
            assert "summaries:tenant-123:order-1" in store.storage
            assert (
                store.storage["summaries:tenant-123:order-1"]["tenant_id"]
                == "tenant-123"
            )
        finally:
            reset_tenant(token)

    async def test_position_store_mro_composition(self):
        """Test that MultitenantProjectionPositionMixin works in MRO chain."""

        class BasePositionStore:
            def __init__(self):
                self.positions = {}

            async def get_position(self, projection_name, *, uow=None):
                return self.positions.get(projection_name)

            async def save_position(self, projection_name, position, *, uow=None):
                self.positions[projection_name] = position

        class TenantAwarePositionStore(
            MultitenantProjectionPositionMixin, BasePositionStore
        ):
            pass

        store = TenantAwarePositionStore()

        token = set_tenant("tenant-123")
        try:
            # Save position
            await store.save_position("order_summary", 42)

            # Verify tenant namespace
            assert "tenant-123:order_summary" in store.positions
        finally:
            reset_tenant(token)
