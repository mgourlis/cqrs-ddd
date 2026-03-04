"""Tests for Phase 13: Projections Engine Multitenancy Integration.

Tests cover:
- MultitenantProjectionHandler: tenant context from events
- TenantAwareProjectionRegistry: automatic handler wrapping
- MultitenantReplayMixin: tenant context per event during replay
- MultitenantWorkerMixin: tenant context per event during worker polling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_multitenancy.context import (
    SYSTEM_TENANT,
    clear_tenant,
    get_current_tenant_or_none,
    set_tenant,
)
from cqrs_ddd_multitenancy.projections.handler import (
    MultitenantProjectionHandler,
    extract_tenant_from_event,
)
from cqrs_ddd_multitenancy.projections.registry import TenantAwareProjectionRegistry
from cqrs_ddd_multitenancy.projections.replay import MultitenantReplayMixin
from cqrs_ddd_multitenancy.projections.worker import MultitenantWorkerMixin

# ── Test helpers ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FakeStoredEvent:
    """Mimics StoredEvent for testing."""

    event_id: str = "evt-1"
    event_type: str = "OrderCreated"
    aggregate_id: str = "agg-1"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    position: int | None = 1
    tenant_id: str | None = None


@dataclass(frozen=True)
class FakeDomainEvent:
    """Mimics DomainEvent for testing."""

    event_id: str = "evt-1"
    aggregate_id: str | None = "agg-1"
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeProjectionHandler:
    """Fake IProjectionHandler that records calls and captures tenant context."""

    def __init__(self) -> None:
        self.handled_events: list[tuple[Any, str | None]] = []
        self._handles: set[type] = {FakeDomainEvent}

    @property
    def handles(self) -> set[type]:
        return self._handles

    async def handle(self, event: Any) -> None:
        tenant = get_current_tenant_or_none()
        self.handled_events.append((event, tenant))


class FakeProjectionRegistry:
    """Fake IProjectionRegistry for testing."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Any]] = {}

    def register(self, handler: Any) -> None:
        for event_cls in handler.handles:
            name = getattr(event_cls, "__name__", str(event_cls))
            self._handlers.setdefault(name, []).append(handler)

    def get_handlers(self, event_type: str) -> list[Any]:
        return list(self._handlers.get(event_type, []))


# ── extract_tenant_from_event ─────────────────────────────────────────


class TestExtractTenantFromEvent:
    """Test tenant extraction from events."""

    def test_extract_from_dedicated_attribute(self):
        event = FakeStoredEvent(tenant_id="tenant-a")
        assert extract_tenant_from_event(event) == "tenant-a"

    def test_extract_from_metadata(self):
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-b"})
        assert extract_tenant_from_event(event) == "tenant-b"

    def test_dedicated_attribute_takes_priority(self):
        event = FakeStoredEvent(
            tenant_id="from-attr", metadata={"tenant_id": "from-meta"}
        )
        assert extract_tenant_from_event(event) == "from-attr"

    def test_returns_none_when_no_tenant(self):
        event = FakeDomainEvent()
        assert extract_tenant_from_event(event) is None

    def test_returns_none_for_plain_object(self):
        assert extract_tenant_from_event(object()) is None

    def test_converts_to_string(self):
        """Non-string tenant_id should be converted to str."""

        @dataclass
        class EventWithIntTenant:
            tenant_id: int = 42

        assert extract_tenant_from_event(EventWithIntTenant()) == "42"


# ── MultitenantProjectionHandler ──────────────────────────────────────


class TestMultitenantProjectionHandler:
    """Test the tenant-aware projection handler wrapper."""

    async def test_sets_tenant_context_from_event(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-x"})

        await handler.handle(event)

        assert len(inner.handled_events) == 1
        assert inner.handled_events[0][1] == "tenant-x"

    async def test_restores_previous_tenant_context(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)

        set_tenant("original")
        try:
            event = FakeDomainEvent(metadata={"tenant_id": "tenant-x"})
            await handler.handle(event)

            # Inner handler saw tenant-x
            assert inner.handled_events[0][1] == "tenant-x"
            # Original context restored
            assert get_current_tenant_or_none() == "original"
        finally:
            clear_tenant()

    async def test_clears_context_when_no_previous(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-x"})

        await handler.handle(event)

        assert get_current_tenant_or_none() is None

    async def test_no_tenant_in_event_preserves_context(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)
        event = FakeDomainEvent()  # No tenant_id

        set_tenant("existing")
        try:
            await handler.handle(event)

            # Inner handler saw the existing context
            assert inner.handled_events[0][1] == "existing"
            assert get_current_tenant_or_none() == "existing"
        finally:
            clear_tenant()

    async def test_system_tenant_skipped_by_default(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)
        event = FakeDomainEvent(metadata={"tenant_id": SYSTEM_TENANT})

        await handler.handle(event)

        # Inner handler was called without setting system tenant
        assert inner.handled_events[0][1] is None

    async def test_system_tenant_not_skipped_when_disabled(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner, skip_system_events=False)
        event = FakeDomainEvent(metadata={"tenant_id": SYSTEM_TENANT})

        await handler.handle(event)

        assert inner.handled_events[0][1] == SYSTEM_TENANT

    async def test_delegates_handles_property(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner)

        assert handler.handles == {FakeDomainEvent}

    async def test_custom_tenant_column(self):
        inner = FakeProjectionHandler()
        handler = MultitenantProjectionHandler(inner, tenant_column="org_id")
        event = FakeDomainEvent(metadata={"org_id": "org-1"})

        await handler.handle(event)

        assert inner.handled_events[0][1] == "org-1"

    async def test_restores_context_on_handler_error(self):
        """Tenant context must be restored even if inner handler raises."""

        class FailingHandler:
            handles = {FakeDomainEvent}

            async def handle(self, event: Any) -> None:
                raise RuntimeError("boom")

        handler = MultitenantProjectionHandler(FailingHandler())
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-x"})

        set_tenant("original")
        try:
            with pytest.raises(RuntimeError, match="boom"):
                await handler.handle(event)
            assert get_current_tenant_or_none() == "original"
        finally:
            clear_tenant()


# ── TenantAwareProjectionRegistry ────────────────────────────────────


class TestTenantAwareProjectionRegistry:
    """Test the registry wrapper that auto-wraps handlers."""

    def test_register_delegates_to_inner(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner)
        handler = FakeProjectionHandler()

        registry.register(handler)

        # Inner registry has the handler
        assert len(inner.get_handlers("FakeDomainEvent")) == 1

    def test_get_handlers_returns_wrapped_handlers(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner)
        handler = FakeProjectionHandler()
        registry.register(handler)

        wrapped = registry.get_handlers("FakeDomainEvent")

        assert len(wrapped) == 1
        assert isinstance(wrapped[0], MultitenantProjectionHandler)

    def test_wrapped_handlers_are_cached(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner)
        handler = FakeProjectionHandler()
        registry.register(handler)

        wrapped1 = registry.get_handlers("FakeDomainEvent")
        wrapped2 = registry.get_handlers("FakeDomainEvent")

        assert wrapped1[0] is wrapped2[0]

    async def test_wrapped_handler_sets_tenant_context(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner)
        handler = FakeProjectionHandler()
        registry.register(handler)

        wrapped = registry.get_handlers("FakeDomainEvent")[0]
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-z"})
        await wrapped.handle(event)

        assert handler.handled_events[0][1] == "tenant-z"

    def test_empty_handlers(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner)

        assert registry.get_handlers("NonExistentEvent") == []

    def test_custom_tenant_column(self):
        inner = FakeProjectionRegistry()
        registry = TenantAwareProjectionRegistry(inner, tenant_column="org_id")
        handler = FakeProjectionHandler()
        registry.register(handler)

        wrapped = registry.get_handlers("FakeDomainEvent")

        assert isinstance(wrapped[0], MultitenantProjectionHandler)
        assert wrapped[0]._tenant_column == "org_id"


# ── MultitenantReplayMixin ────────────────────────────────────────────


class TestMultitenantReplayMixin:
    """Test the replay engine mixin with tenant context per event."""

    async def test_sets_tenant_from_stored_event(self):
        """The mixin should extract tenant from stored event."""
        captured_tenants: list[str | None] = []

        class MockReplayEngine:
            async def _dispatch_to_handlers(
                self, stored: Any, domain_event: Any
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantReplay(MultitenantReplayMixin, MockReplayEngine):
            pass

        engine = TenantReplay()
        stored = FakeStoredEvent(tenant_id="tenant-replay")
        domain = FakeDomainEvent()

        await engine._dispatch_to_handlers(stored, domain)

        assert captured_tenants == ["tenant-replay"]
        assert get_current_tenant_or_none() is None

    async def test_falls_back_to_domain_event_metadata(self):
        captured_tenants: list[str | None] = []

        class MockReplayEngine:
            async def _dispatch_to_handlers(
                self, stored: Any, domain_event: Any
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantReplay(MultitenantReplayMixin, MockReplayEngine):
            pass

        engine = TenantReplay()
        stored = FakeStoredEvent(tenant_id=None)  # No tenant on stored event
        domain = FakeDomainEvent(metadata={"tenant_id": "tenant-from-domain"})

        await engine._dispatch_to_handlers(stored, domain)

        assert captured_tenants == ["tenant-from-domain"]

    async def test_no_tenant_delegates_without_context(self):
        captured_tenants: list[str | None] = []

        class MockReplayEngine:
            async def _dispatch_to_handlers(
                self, stored: Any, domain_event: Any
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantReplay(MultitenantReplayMixin, MockReplayEngine):
            pass

        engine = TenantReplay()
        stored = FakeStoredEvent(tenant_id=None)
        domain = FakeDomainEvent()

        await engine._dispatch_to_handlers(stored, domain)

        assert captured_tenants == [None]

    async def test_restores_context_after_dispatch(self):
        class MockReplayEngine:
            async def _dispatch_to_handlers(
                self, stored: Any, domain_event: Any
            ) -> None:
                pass

        class TenantReplay(MultitenantReplayMixin, MockReplayEngine):
            pass

        engine = TenantReplay()

        set_tenant("outer")
        try:
            stored = FakeStoredEvent(tenant_id="inner")
            await engine._dispatch_to_handlers(stored, FakeDomainEvent())
            assert get_current_tenant_or_none() == "outer"
        finally:
            clear_tenant()

    async def test_restores_context_on_error(self):
        class MockReplayEngine:
            async def _dispatch_to_handlers(
                self, stored: Any, domain_event: Any
            ) -> None:
                raise RuntimeError("dispatch error")

        class TenantReplay(MultitenantReplayMixin, MockReplayEngine):
            pass

        engine = TenantReplay()

        set_tenant("safe")
        try:
            stored = FakeStoredEvent(tenant_id="inner")
            with pytest.raises(RuntimeError, match="dispatch error"):
                await engine._dispatch_to_handlers(stored, FakeDomainEvent())
            assert get_current_tenant_or_none() == "safe"
        finally:
            clear_tenant()


# ── MultitenantWorkerMixin ────────────────────────────────────────────


class TestMultitenantWorkerMixin:
    """Test the worker mixin with tenant context per event."""

    async def test_sets_tenant_from_stored_event(self):
        captured_tenants: list[str | None] = []

        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()
        stored = FakeStoredEvent(tenant_id="tenant-w")
        event = FakeDomainEvent()

        await worker._dispatch(event, stored, 1, 0)

        assert captured_tenants == ["tenant-w"]
        assert get_current_tenant_or_none() is None

    async def test_falls_back_to_domain_event(self):
        captured_tenants: list[str | None] = []

        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()
        stored = FakeStoredEvent(tenant_id=None)
        event = FakeDomainEvent(metadata={"tenant_id": "tenant-from-event"})

        await worker._dispatch(event, stored, 1, 0)

        assert captured_tenants == ["tenant-from-event"]

    async def test_no_tenant_delegates_transparently(self):
        captured_tenants: list[str | None] = []

        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()
        stored = FakeStoredEvent(tenant_id=None)
        event = FakeDomainEvent()

        await worker._dispatch(event, stored, 1, 0)

        assert captured_tenants == [None]

    async def test_restores_context_after_dispatch(self):
        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                pass

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()
        set_tenant("outer-w")
        try:
            stored = FakeStoredEvent(tenant_id="inner-w")
            await worker._dispatch(FakeDomainEvent(), stored, 1, 0)
            assert get_current_tenant_or_none() == "outer-w"
        finally:
            clear_tenant()

    async def test_restores_context_on_error(self):
        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                raise RuntimeError("worker error")

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()
        set_tenant("safe-w")
        try:
            stored = FakeStoredEvent(tenant_id="inner-w")
            with pytest.raises(RuntimeError, match="worker error"):
                await worker._dispatch(FakeDomainEvent(), stored, 1, 0)
            assert get_current_tenant_or_none() == "safe-w"
        finally:
            clear_tenant()

    async def test_multiple_events_different_tenants(self):
        """Process events from different tenants sequentially."""
        captured_tenants: list[str | None] = []

        class MockProjectionWorker:
            async def _dispatch(
                self, event: Any, stored: Any, event_position: int, retry_count: int
            ) -> None:
                captured_tenants.append(get_current_tenant_or_none())

        class TenantWorker(MultitenantWorkerMixin, MockProjectionWorker):
            pass

        worker = TenantWorker()

        for tid in ["tenant-1", "tenant-2", "tenant-3"]:
            stored = FakeStoredEvent(tenant_id=tid)
            await worker._dispatch(FakeDomainEvent(), stored, 1, 0)

        assert captured_tenants == ["tenant-1", "tenant-2", "tenant-3"]
        assert get_current_tenant_or_none() is None
