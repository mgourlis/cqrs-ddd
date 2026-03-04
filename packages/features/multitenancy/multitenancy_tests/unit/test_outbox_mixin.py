"""Unit tests for MultitenantOutboxMixin and StrictMultitenantOutboxMixin."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
)
from cqrs_ddd_multitenancy.mixins.outbox import (
    MultitenantOutboxMixin,
    StrictMultitenantOutboxMixin,
)

# ── Helpers ────────────────────────────────────────────────────────────


@dataclasses.dataclass
class FakeOutboxMessage:
    """Minimal OutboxMessage for testing."""

    message_id: str
    event_type: str
    payload: dict
    metadata: dict = dataclasses.field(default_factory=dict)
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    published_at: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    correlation_id: str | None = None
    causation_id: str | None = None
    tenant_id: str | None = None


class MockOutboxStorage:
    """Mock base outbox storage."""

    def __init__(self) -> None:
        self.saved: list[FakeOutboxMessage] = []
        self.published: list[str] = []
        self.failed: list[str] = []

    async def save_messages(
        self, messages: list[FakeOutboxMessage], uow: Any = None
    ) -> None:
        self.saved.extend(messages)

    async def get_pending(
        self,
        limit: int = 100,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[FakeOutboxMessage]:
        result = list(self.saved)
        if specification is not None:
            result = [m for m in result if specification.is_satisfied_by(m)]
        return result[:limit]

    async def mark_published(self, message_ids: list[str], uow: Any = None) -> None:
        self.published.extend(message_ids)

    async def mark_failed(self, message_id: str, error: str, uow: Any = None) -> None:
        self.failed.append(message_id)


class UnfilteredMockOutboxStorage(MockOutboxStorage):
    """Mock where get_pending returns ALL messages regardless of spec.

    Simulates a base storage that doesn't implement spec-based filtering.
    Used to test the StrictMultitenantOutboxMixin validation logic.
    """

    async def get_pending(
        self,
        limit: int = 100,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[FakeOutboxMessage]:
        # Deliberately ignore specification to simulate unfiltered storage
        return list(self.saved)[:limit]


class TestOutbox(MultitenantOutboxMixin, MockOutboxStorage):
    pass


class StrictTestOutbox(StrictMultitenantOutboxMixin, MockOutboxStorage):
    pass


class UnfilteredStrictOutbox(StrictMultitenantOutboxMixin, UnfilteredMockOutboxStorage):
    pass


def make_message(tenant_id: str | None = None) -> FakeOutboxMessage:
    meta: dict = {}
    if tenant_id:
        meta["tenant_id"] = tenant_id
    return FakeOutboxMessage(
        message_id=str(uuid4()),
        event_type="OrderPlaced",
        payload={"order_id": "123"},
        metadata=meta,
        tenant_id=tenant_id,
    )


# ── Tests: save_messages ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_injects_tenant_id():
    outbox = TestOutbox()
    token = set_tenant("tenant-A")
    try:
        msg = make_message()
        await outbox.save_messages([msg])
        assert len(outbox.saved) == 1
        saved = outbox.saved[0]
        assert saved.metadata.get("tenant_id") == "tenant-A"
        assert saved.tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_save_raises_when_no_tenant():
    outbox = TestOutbox()
    msg = make_message()
    with pytest.raises(TenantContextMissingError):
        await outbox.save_messages([msg])


@pytest.mark.asyncio
async def test_save_multiple_messages():
    outbox = TestOutbox()
    token = set_tenant("tenant-A")
    try:
        msgs = [make_message() for _ in range(3)]
        await outbox.save_messages(msgs)
        assert len(outbox.saved) == 3
        assert all(m.tenant_id == "tenant-A" for m in outbox.saved)
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_save_system_tenant_bypasses():
    outbox = TestOutbox()
    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_save():
        msg = make_message()
        await outbox.save_messages([msg])

    await do_save()
    assert len(outbox.saved) == 1
    assert outbox.saved[0].tenant_id is None  # Not injected


# ── Tests: get_pending ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pending_filters_by_tenant():
    outbox = TestOutbox()
    outbox.saved = [
        make_message("tenant-A"),
        make_message("tenant-B"),
    ]
    token = set_tenant("tenant-A")
    try:
        results = await outbox.get_pending()
        assert len(results) == 1
        assert results[0].tenant_id == "tenant-A"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_get_pending_raises_when_no_tenant():
    outbox = TestOutbox()
    with pytest.raises(TenantContextMissingError):
        await outbox.get_pending()


@pytest.mark.asyncio
async def test_get_pending_system_bypasses():
    outbox = TestOutbox()
    outbox.saved = [make_message("tenant-A"), make_message("tenant-B")]

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_get():
        return await outbox.get_pending()

    results = await do_get()
    assert len(results) == 2


# ── Tests: mark_published ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_published_with_tenant():
    outbox = TestOutbox()
    token = set_tenant("tenant-A")
    try:
        await outbox.mark_published(["msg-1", "msg-2"])
        assert "msg-1" in outbox.published
        assert "msg-2" in outbox.published
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_mark_published_raises_when_no_tenant():
    outbox = TestOutbox()
    with pytest.raises(TenantContextMissingError):
        await outbox.mark_published(["msg-1"])


@pytest.mark.asyncio
async def test_mark_published_system_bypasses():
    outbox = TestOutbox()

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_mark():
        await outbox.mark_published(["msg-1"])

    await do_mark()
    assert "msg-1" in outbox.published


# ── Tests: mark_failed ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_with_tenant():
    outbox = TestOutbox()
    token = set_tenant("tenant-A")
    try:
        await outbox.mark_failed("msg-1", "some error")
        assert "msg-1" in outbox.failed
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_mark_failed_raises_when_no_tenant():
    outbox = TestOutbox()
    with pytest.raises(TenantContextMissingError):
        await outbox.mark_failed("msg-1", "error")


@pytest.mark.asyncio
async def test_mark_failed_system_bypasses():
    outbox = TestOutbox()

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_fail():
        await outbox.mark_failed("msg-1", "error")

    await do_fail()
    assert "msg-1" in outbox.failed


# ── Tests: StrictMultitenantOutboxMixin ────────────────────────────────


@pytest.mark.asyncio
async def test_strict_mark_published_validates_ownership():
    # Use UnfilteredStrictOutbox so that get_pending returns ALL messages,
    # allowing the strict mixin to detect cross-tenant access.
    outbox = UnfilteredStrictOutbox()
    msg = make_message("tenant-B")
    outbox.saved.append(msg)

    token = set_tenant("tenant-A")
    try:
        with pytest.raises(CrossTenantAccessError):
            await outbox.mark_published([msg.message_id])
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_strict_mark_published_allows_own_tenant():
    outbox = StrictTestOutbox()
    msg = make_message("tenant-A")
    outbox.saved.append(msg)

    token = set_tenant("tenant-A")
    try:
        await outbox.mark_published([msg.message_id])
        assert msg.message_id in outbox.published
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_strict_mark_published_system_bypasses():
    outbox = StrictTestOutbox()
    msg = make_message("tenant-B")
    outbox.saved.append(msg)

    from cqrs_ddd_multitenancy.context import system_operation

    @system_operation
    async def do_mark():
        await outbox.mark_published([msg.message_id])

    await do_mark()
    assert msg.message_id in outbox.published


# ── Tests: _inject_tenant_into_message fallback ────────────────────────


def test_inject_tenant_message_non_dataclass():
    outbox = TestOutbox()

    class NonDCMessage:
        def __init__(
            self,
            message_id="x",
            event_type="OrderPlaced",
            payload=None,
            metadata=None,
            created_at=None,
            published_at=None,
            error=None,
            retry_count=0,
            correlation_id=None,
            causation_id=None,
            tenant_id=None,
        ) -> None:
            self.message_id = message_id
            self.event_type = event_type
            self.payload = payload or {}
            self.metadata = metadata or {}
            self.created_at = created_at or datetime.now(timezone.utc)
            self.published_at = published_at
            self.error = error
            self.retry_count = retry_count
            self.correlation_id = correlation_id
            self.causation_id = causation_id
            self.tenant_id = tenant_id

    msg = NonDCMessage()
    result = outbox._inject_tenant_into_message(msg, "tenant-X")
    assert result is not None


# ── Tests: helper methods ──────────────────────────────────────────────


def test_build_tenant_specification():
    outbox = TestOutbox()
    spec = outbox._build_tenant_specification("tenant-X")
    msg_match = make_message("tenant-X")
    msg_other = make_message("tenant-Y")
    assert spec.is_satisfied_by(msg_match)
    assert not spec.is_satisfied_by(msg_other)


def test_get_tenant_from_message():
    outbox = TestOutbox()
    msg = make_message("tenant-X")
    assert outbox._get_tenant_from_message(msg) == "tenant-X"


def test_get_tenant_from_message_missing():
    outbox = TestOutbox()
    msg = make_message()
    assert outbox._get_tenant_from_message(msg) is None
