"""Unit tests for multitenant dispatcher and persistence mixins.

Tests cover:
- MultitenantDispatcherMixin
- MultitenantOperationPersistenceMixin
- MultitenantRetrievalPersistenceMixin
- MultitenantQueryPersistenceMixin
- MultitenantQuerySpecificationPersistenceMixin
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_multitenancy import (
    MultitenantDispatcherMixin,
    MultitenantOperationPersistenceMixin,
    MultitenantQueryPersistenceMixin,
    MultitenantQuerySpecificationPersistenceMixin,
    MultitenantRetrievalPersistenceMixin,
    reset_tenant,
    set_tenant,
)
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError

# ============================================================================
# Test Fixtures
# ============================================================================


class MockEntity:
    """Mock aggregate root for testing with dedicated tenant_id field.

    Simulates an aggregate using MultitenantMixin from cqrs_ddd_multitenancy.domain.
    The tenant_id field always exists (may be None initially).
    """

    def __init__(
        self,
        entity_id: str,
        tenant_id: str | None = None,
    ):
        self.id = entity_id
        self.tenant_id = tenant_id  # Always has the field, even if None


class MockEvent:
    """Mock domain event for testing."""

    def __init__(self, event_id: str, metadata: dict[str, Any] | None = None):
        self.event_id = event_id
        self.metadata = metadata if metadata is not None else {}


class MockResultDTO:
    """Mock result DTO for testing."""

    def __init__(self, result_id: str, tenant_id: str | None = None):
        self.id = result_id
        self.tenant_id = tenant_id


class MockSearchResult:
    """Mock search result for testing."""

    def __init__(self, results: list[Any]):
        self._results = results

    def __await__(self):
        async def _await():
            return self._results

        return _await().__await__()


# ============================================================================
# Base Parent Classes (simulate underlying implementation)
# ============================================================================


class BaseDispatcher:
    """Base dispatcher that the mixin wraps."""

    async def apply(self, entity, uow=None, events=None):
        """Base implementation just returns entity ID."""
        return entity.id

    async def fetch_domain(self, entity_type, ids, uow=None, *, specification=None):
        """Base implementation returns empty list."""
        return []

    async def fetch(self, result_type, criteria, uow=None, *, specification=None):
        """Base implementation returns empty result."""
        return MockSearchResult([])


class BaseOperationPersistence:
    """Base operation persistence that the mixin wraps."""

    async def persist(self, entity, uow, events=None):
        """Base implementation just returns entity ID."""
        return entity.id


class BaseRetrievalPersistence:
    """Base retrieval persistence that the mixin wraps."""

    async def retrieve(self, ids, uow, *, specification=None):
        """Base implementation returns empty list."""
        return []


class BaseQueryPersistence:
    """Base query persistence that the mixin wraps."""

    async def fetch(self, ids, uow, *, specification=None):
        """Base implementation returns empty list."""
        return []


class BaseQuerySpecPersistence:
    """Base query specification persistence that the mixin wraps."""

    def fetch(self, criteria, uow):
        """Base implementation returns empty result."""
        return MockSearchResult([])


# ============================================================================
# MultitenantDispatcherMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantDispatcherMixin:
    """Test suite for MultitenantDispatcherMixin."""

    async def test_apply_injects_tenant_metadata(self):
        """Test that apply() injects tenant_id into entity and events."""

        # Create test dispatcher with proper MRO composition
        class TestDispatcher(MultitenantDispatcherMixin, BaseDispatcher):
            pass

        dispatcher = TestDispatcher()
        entity = MockEntity("entity-1")
        events = [MockEvent("event-1"), MockEvent("event-2")]

        token = set_tenant("tenant-123")
        try:
            result = await dispatcher.apply(entity, events=events)
            # Verify tenant_id was injected into entity
            assert entity.tenant_id == "tenant-123"
            # Verify tenant_id was injected into events
            for event in events:
                assert event.metadata.get("tenant_id") == "tenant-123"
            assert result == "entity-1"
        finally:
            reset_tenant(token)

    async def test_apply_requires_tenant_context(self):
        """Test that apply() raises error without tenant context."""

        class TestDispatcher(MultitenantDispatcherMixin, BaseDispatcher):
            pass

        dispatcher = TestDispatcher()
        entity = MockEntity("entity-1")

        with pytest.raises(TenantContextMissingError):
            await dispatcher.apply(entity)

    async def test_fetch_domain_filters_by_tenant(self):
        """Test that fetch_domain() requires tenant context and delegates to base."""

        # Create base class that simulates DB-level filtering
        class TestBaseDispatcher(BaseDispatcher):
            async def fetch_domain(
                self, entity_type, ids, uow=None, *, specification=None
            ):
                # Simulates database-level filtering: WHERE tenant_id = :tenant_id
                # Returns only entities for the current tenant
                return [
                    MockEntity("entity-1", tenant_id="tenant-123"),
                    MockEntity("entity-3", tenant_id="tenant-123"),
                ]

        class TestDispatcher(MultitenantDispatcherMixin, TestBaseDispatcher):
            pass

        dispatcher = TestDispatcher()

        token = set_tenant("tenant-123")
        try:
            results = await dispatcher.fetch_domain(
                MockEntity, ["entity-1", "entity-2", "entity-3"]
            )

            # Base implementation already filtered by tenant (DB-level)
            assert len(results) == 2
            assert all(e.tenant_id == "tenant-123" for e in results)
        finally:
            reset_tenant(token)

    async def test_fetch_with_tenant_context(self):
        """Test that fetch() executes with tenant context."""

        class TestBaseDispatcher(BaseDispatcher):
            async def fetch(
                self, result_type, criteria, uow=None, *, specification=None
            ):
                return MockSearchResult([MockResultDTO("result-1", "tenant-123")])

        class TestDispatcher(MultitenantDispatcherMixin, TestBaseDispatcher):
            pass

        dispatcher = TestDispatcher()

        token = set_tenant("tenant-123")
        try:
            results = await dispatcher.fetch(MockResultDTO, {"id": "result-1"})
            result_list = await results
            assert len(result_list) == 1
        finally:
            reset_tenant(token)


# ============================================================================
# MultitenantOperationPersistenceMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantOperationPersistenceMixin:
    """Test suite for MultitenantOperationPersistenceMixin."""

    async def test_persist_injects_tenant_metadata(self):
        """Test that persist() injects tenant_id into entity and events."""

        class TestPersistence(
            MultitenantOperationPersistenceMixin, BaseOperationPersistence
        ):
            pass

        persistence = TestPersistence()
        entity = MockEntity("entity-1")
        events = [MockEvent("event-1")]
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            result = await persistence.persist(entity, uow, events)
            # Verify tenant_id was injected into entity
            assert entity.tenant_id == "tenant-123"
            # Verify tenant_id was injected into events
            for event in events:
                assert event.metadata.get("tenant_id") == "tenant-123"
            assert result == "entity-1"
        finally:
            reset_tenant(token)

    async def test_persist_requires_tenant_context(self):
        """Test that persist() raises error without tenant context."""

        class TestPersistence(
            MultitenantOperationPersistenceMixin, BaseOperationPersistence
        ):
            pass

        persistence = TestPersistence()
        entity = MockEntity("entity-1")
        uow = MagicMock()

        with pytest.raises(TenantContextMissingError):
            await persistence.persist(entity, uow)


# ============================================================================
# MultitenantRetrievalPersistenceMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantRetrievalPersistenceMixin:
    """Test suite for MultitenantRetrievalPersistenceMixin."""

    async def test_retrieve_filters_by_tenant(self):
        """Test that retrieve() passes tenant specification to base."""

        received_spec = {}

        class TestBasePersistence(BaseRetrievalPersistence):
            async def retrieve(self, ids, uow, *, specification=None):
                received_spec["spec"] = specification
                # In real implementation, DB would filter by specification
                return [
                    MockEntity("entity-1", tenant_id="tenant-123"),
                    MockEntity("entity-3", tenant_id="tenant-123"),
                ]

        class TestPersistence(
            MultitenantRetrievalPersistenceMixin, TestBasePersistence
        ):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            results = await persistence.retrieve(
                ["entity-1", "entity-2", "entity-3"], uow
            )

            # Verify specification was passed to base
            assert received_spec["spec"] is not None
            spec = received_spec["spec"]
            spec_dict = spec.to_dict()
            assert spec_dict["attr"] == "tenant_id"
            assert spec_dict["val"] == "tenant-123"
            # Results come from base (DB-level filtering)
            assert len(results) == 2
        finally:
            reset_tenant(token)

    async def test_retrieve_requires_tenant_context(self):
        """Test that retrieve() raises error without tenant context."""

        class TestPersistence(
            MultitenantRetrievalPersistenceMixin, BaseRetrievalPersistence
        ):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        with pytest.raises(TenantContextMissingError):
            await persistence.retrieve(["entity-1"], uow)


# ============================================================================
# MultitenantQueryPersistenceMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantQueryPersistenceMixin:
    """Test suite for MultitenantQueryPersistenceMixin."""

    async def test_fetch_filters_by_tenant(self):
        """Test that fetch() passes tenant specification to base."""

        received_spec = {}

        class TestBasePersistence(BaseQueryPersistence):
            async def fetch(self, ids, uow, *, specification=None):
                received_spec["spec"] = specification
                # In real implementation, DB would filter by specification
                return [
                    MockResultDTO("result-1", "tenant-123"),
                    MockResultDTO("result-3", "tenant-123"),
                ]

        class TestPersistence(MultitenantQueryPersistenceMixin, TestBasePersistence):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            results = await persistence.fetch(["result-1", "result-2", "result-3"], uow)

            # Verify specification was passed to base
            assert received_spec["spec"] is not None
            spec = received_spec["spec"]
            spec_dict = spec.to_dict()
            assert spec_dict["attr"] == "tenant_id"
            assert spec_dict["val"] == "tenant-123"
            # Results come from base (DB-level filtering)
            assert len(results) == 2
        finally:
            reset_tenant(token)

    async def test_fetch_allows_results_without_tenant_field(self):
        """Test that fetch() still passes specification even for tenant-agnostic DTOs."""

        received_spec = {}

        class TestBasePersistence(BaseQueryPersistence):
            async def fetch(self, ids, uow, *, specification=None):
                received_spec["spec"] = specification
                # Return DTOs without tenant_id
                return [
                    MockResultDTO("result-1", None),
                    MockResultDTO("result-2", None),
                ]

        class TestPersistence(MultitenantQueryPersistenceMixin, TestBasePersistence):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            results = await persistence.fetch(["result-1", "result-2"], uow)

            # Specification is still passed (DB decides how to handle it)
            assert received_spec["spec"] is not None
            # All results returned
            assert len(results) == 2
        finally:
            reset_tenant(token)

    async def test_fetch_requires_tenant_context(self):
        """Test that fetch() raises error without tenant context."""

        class TestPersistence(MultitenantQueryPersistenceMixin, BaseQueryPersistence):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        with pytest.raises(TenantContextMissingError):
            await persistence.fetch(["result-1"], uow)


# ============================================================================
# MultitenantQuerySpecificationPersistenceMixin Tests
# ============================================================================


@pytest.mark.asyncio
class TestMultitenantQuerySpecificationPersistenceMixin:
    """Test suite for MultitenantQuerySpecificationPersistenceMixin."""

    async def test_fetch_with_tenant_context(self):
        """Test that fetch() executes with tenant context."""

        class TestBasePersistence(BaseQuerySpecPersistence):
            def fetch(self, criteria, uow):
                return MockSearchResult([MockResultDTO("result-1", "tenant-123")])

        class TestPersistence(
            MultitenantQuerySpecificationPersistenceMixin, TestBasePersistence
        ):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            results = persistence.fetch({"status": "active"}, uow)
            result_list = await results
            assert len(result_list) == 1
        finally:
            reset_tenant(token)

    async def test_fetch_requires_tenant_context(self):
        """Test that fetch() raises error without tenant context."""

        class TestPersistence(
            MultitenantQuerySpecificationPersistenceMixin, BaseQuerySpecPersistence
        ):
            pass

        persistence = TestPersistence()
        uow = MagicMock()

        with pytest.raises(TenantContextMissingError):
            persistence.fetch({"status": "active"}, uow)


# ============================================================================
# Integration Tests (MRO Pattern)
# ============================================================================


@pytest.mark.asyncio
class TestMROPattern:
    """Test that MRO composition pattern works correctly."""

    async def test_dispatcher_mro_composition(self):
        """Test that MultitenantDispatcherMixin works in MRO chain."""

        class BaseDispatcher:
            async def apply(self, entity, uow=None, events=None):
                return entity.id

            async def fetch_domain(
                self, entity_type, ids, uow=None, *, specification=None
            ):
                return []

            async def fetch(
                self, result_type, criteria, uow=None, *, specification=None
            ):
                return MockSearchResult([])

        class TenantAwareDispatcher(MultitenantDispatcherMixin, BaseDispatcher):
            pass

        dispatcher = TenantAwareDispatcher()
        entity = MockEntity("entity-1")

        token = set_tenant("tenant-123")
        try:
            # Should inject tenant_id field
            result = await dispatcher.apply(entity)
            assert result == "entity-1"
            assert entity.tenant_id == "tenant-123"
        finally:
            reset_tenant(token)

    async def test_persistence_mro_composition(self):
        """Test that persistence mixins work in MRO chain."""

        class BaseOperationPersistence:
            async def persist(self, entity, uow, events=None):
                return entity.id

        class TenantAwareOperationPersistence(
            MultitenantOperationPersistenceMixin, BaseOperationPersistence
        ):
            pass

        persistence = TenantAwareOperationPersistence()
        entity = MockEntity("entity-1")
        uow = MagicMock()

        token = set_tenant("tenant-123")
        try:
            result = await persistence.persist(entity, uow)
            assert result == "entity-1"
            assert entity.tenant_id == "tenant-123"
        finally:
            reset_tenant(token)
