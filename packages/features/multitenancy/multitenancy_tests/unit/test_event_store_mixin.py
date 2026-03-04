"""Unit tests for MultitenantEventStoreMixin."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.mixins.event_store import MultitenantEventStoreMixin

# ── Helpers ────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class FakeStoredEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    version: int
    schema_version: int = 1
    payload: dict = dataclasses.field(default_factory=dict)
    metadata: dict = dataclasses.field(default_factory=dict)
    occurred_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    correlation_id: str | None = None
    causation_id: str | None = None
    position: int | None = None
    tenant_id: str | None = None


def make_event(
    aggregate_id: str = "agg-1",
    tenant_id: str | None = None,
    version: int = 1,
) -> FakeStoredEvent:
    return FakeStoredEvent(
        event_id=str(uuid4()),
        event_type="OrderPlaced",
        aggregate_id=aggregate_id,
        aggregate_type="Order",
        version=version,
        tenant_id=tenant_id,
    )


class MockEventStore:
    """Mock base event store for MRO composition."""

    def __init__(self) -> None:
        self.appended: list[FakeStoredEvent] = []
        self.events: list[FakeStoredEvent] = []

    async def append(self, stored_event: FakeStoredEvent) -> None:
        self.appended.append(stored_event)
        self.events.append(stored_event)

    async def append_batch(self, events: list[FakeStoredEvent]) -> None:
        self.appended.extend(events)
        self.events.extend(events)

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
        specification: Any | None = None,
    ) -> list[FakeStoredEvent]:
        result = [
            e
            for e in self.events
            if e.aggregate_id == aggregate_id and e.version > after_version
        ]
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        return result

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
        *,
        specification: Any | None = None,
    ) -> list[FakeStoredEvent]:
        result = [e for e in self.events if e.aggregate_id == aggregate_id]
        if aggregate_type is not None:
            result = [e for e in result if e.aggregate_type == aggregate_type]
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        return result

    async def get_all(
        self, *, specification: Any | None = None
    ) -> list[FakeStoredEvent]:
        result = list(self.events)
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        return result

    async def get_events_after(
        self,
        position: int,
        limit: int = 1000,
        *,
        specification: Any | None = None,
    ) -> list[FakeStoredEvent]:
        result = [e for e in self.events if (e.position or 0) > position]
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        return result[:limit]

    async def stream_all(
        self, batch_size: int = 1000, *, specification: Any | None = None
    ) -> AsyncIterator[FakeStoredEvent]:
        result = list(self.events)
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        for event in result:
            yield event

    def get_events_from_position(
        self,
        position: int,
        *,
        limit: int | None = None,
        specification: Any | None = None,
    ) -> AsyncIterator[FakeStoredEvent]:
        async def _gen():
            result = [e for e in self.events if (e.position or 0) > position]
            if specification is not None:
                result = [e for e in result if specification.is_satisfied_by(e)]
            for event in result:
                yield event

        return _gen()

    def get_all_streaming(
        self, batch_size: int = 1000, *, specification: Any | None = None
    ) -> AsyncIterator[list[FakeStoredEvent]]:
        async def _gen():
            result = list(self.events)
            if specification is not None:
                result = [e for e in result if specification.is_satisfied_by(e)]
            yield result[:batch_size]

        return _gen()

    async def get_latest_position(
        self, *, specification: Any | None = None
    ) -> int | None:
        result = list(self.events)
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        if not result:
            return None
        return max(e.position or 0 for e in result)


class TestEventStore(MultitenantEventStoreMixin, MockEventStore):
    pass


@pytest.fixture
def store() -> TestEventStore:
    return TestEventStore()


# ── Tests: append ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_injects_tenant_id(store: TestEventStore):
    token = set_tenant("tenant-A")
    try:
        event = make_event()
        await store.append(event)
        assert len(store.appended) == 1
        assert store.appended[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_append_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.append(make_event())


@pytest.mark.asyncio
async def test_append_system_bypasses(store: TestEventStore):
    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_append():
        await store.append(make_event())

    await do_append()
    assert len(store.appended) == 1
    # Tenant ID not injected for system operations
    assert store.appended[0].tenant_id is None


# ── Tests: append_batch ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_batch_injects_tenant_id(store: TestEventStore):
    token = set_tenant("tenant-A")
    try:
        events = [make_event(version=i) for i in range(3)]
        await store.append_batch(events)
        assert all(e.tenant_id == "tenant-A" for e in store.appended)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_append_batch_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.append_batch([make_event()])


@pytest.mark.asyncio
async def test_append_batch_system_bypasses(store: TestEventStore):
    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_append():
        await store.append_batch([make_event(), make_event(version=2)])

    await do_append()
    assert len(store.appended) == 2


# ── Tests: get_events ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_events_filters_by_tenant(store: TestEventStore):
    store.events = [
        make_event("agg-1", "tenant-A"),
        make_event("agg-1", "tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = await store.get_events("agg-1")
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_events_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.get_events("agg-1")


@pytest.mark.asyncio
async def test_get_events_system_bypasses(store: TestEventStore):
    store.events = [
        make_event("agg-1", "tenant-A"),
        make_event("agg-1", "tenant-B"),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_get():
        return await store.get_events("agg-1")

    results = await do_get()
    assert len(results) == 2


# ── Tests: get_by_aggregate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_aggregate_filters_by_tenant(store: TestEventStore):
    store.events = [
        make_event("agg-1", "tenant-A"),
        make_event("agg-1", "tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = await store.get_by_aggregate("agg-1")
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_by_aggregate_with_aggregate_type(store: TestEventStore):
    store.events = [make_event("agg-1", "tenant-A")]
    token = set_tenant("tenant-A")
    try:
        results = await store.get_by_aggregate("agg-1", "Order")
        assert len(results) == 1
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_by_aggregate_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.get_by_aggregate("agg-1")


# ── Tests: get_all ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_filters_by_tenant(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = await store.get_all()
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_all_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.get_all()


@pytest.mark.asyncio
async def test_get_all_system_bypasses(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_get():
        return await store.get_all()

    results = await do_get()
    assert len(results) == 2


# ── Tests: get_events_after ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_events_after_filters_by_tenant(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=5),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=6),
    ]
    token = set_tenant("tenant-A")
    try:
        results = await store.get_events_after(0)
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_events_after_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.get_events_after(0)


@pytest.mark.asyncio
async def test_get_events_after_system_bypasses(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=1),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=2),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_get():
        return await store.get_events_after(0)

    results = await do_get()
    assert len(results) == 2


# ── Tests: stream_all ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_all_filters_by_tenant(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = []
        async for event in store.stream_all():
            results.append(event)
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_stream_all_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        async for _ in store.stream_all():
            pass


@pytest.mark.asyncio
async def test_stream_all_system_bypasses(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_stream():
        results = []
        async for event in store.stream_all():
            results.append(event)
        return results

    results = await do_stream()
    assert len(results) == 2


# ── Tests: get_events_from_position ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_events_from_position_filters_by_tenant(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=1),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=2),
    ]
    token = set_tenant("tenant-A")
    try:
        results = []
        async for event in store.get_events_from_position(0):
            results.append(event)
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_events_from_position_system_bypasses(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=1),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=2),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_stream():
        results = []
        async for event in store.get_events_from_position(0):
            results.append(event)
        return results

    results = await do_stream()
    assert len(results) == 2


# ── Tests: get_all_streaming ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_streaming_filters_by_tenant(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = []
        async for batch in store.get_all_streaming():
            results.extend(batch)
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_all_streaming_system_bypasses(store: TestEventStore):
    store.events = [
        make_event(tenant_id="tenant-A"),
        make_event(tenant_id="tenant-B"),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_stream():
        results = []
        async for batch in store.get_all_streaming():
            results.extend(batch)
        return results

    results = await do_stream()
    assert len(results) == 2


# ── Tests: get_latest_position ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_latest_position_filters_by_tenant(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=5),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=10),
    ]
    token = set_tenant("tenant-A")
    try:
        pos = await store.get_latest_position()
        assert pos == 5
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_latest_position_returns_none_when_empty(store: TestEventStore):
    token = set_tenant("tenant-A")
    try:
        pos = await store.get_latest_position()
        assert pos is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_latest_position_system_bypasses(store: TestEventStore):
    store.events = [
        dataclasses.replace(make_event(tenant_id="tenant-A"), position=5),
        dataclasses.replace(make_event(tenant_id="tenant-B"), position=10),
    ]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_get():
        return await store.get_latest_position()

    pos = await do_get()
    assert pos == 10


@pytest.mark.asyncio
async def test_get_latest_position_raises_when_no_tenant(store: TestEventStore):
    with pytest.raises(TenantContextMissingError):
        await store.get_latest_position()


# ── Tests: _inject_tenant_into_event ──────────────────────────────────


def test_inject_tenant_into_event():
    store = TestEventStore()
    event = make_event()
    result = store._inject_tenant_into_event(event, "tenant-X")
    assert result.tenant_id == "tenant-X"
    # Original event unchanged (frozen dataclass)
    assert event.tenant_id is None


# ── Tests: _build_tenant_specification / _compose_specs ───────────────


def test_build_tenant_specification_creates_spec():
    store = TestEventStore()
    spec = store._build_tenant_specification("tenant-X")
    assert spec is not None


def test_compose_specs_with_none_returns_tenant_spec():
    store = TestEventStore()
    spec = store._build_tenant_specification("tenant-X")
    result = store._compose_specs(spec, None)
    assert result is spec


def test_compose_specs_composes_two_specs():
    store = TestEventStore()
    tenant_spec = store._build_tenant_specification("tenant-X")

    class OtherSpec:
        def is_satisfied_by(self, x):
            return True

        def __and__(self, other):
            return other

    result = store._compose_specs(OtherSpec(), tenant_spec)
    # Since OtherSpec is the first arg to _compose_specs(tenant_spec, other)
    # and tenant_spec.__and__ is called, result should be composed
    assert result is not None
