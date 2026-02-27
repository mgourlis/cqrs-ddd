"""Tests for InMemoryAuthAuditStore."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity.audit.events import (
    AuthAuditEvent,
    AuthEventType,
    login_failed_event,
    login_success_event,
)
from cqrs_ddd_identity.audit.memory import InMemoryAuthAuditStore


@pytest.fixture
def store() -> InMemoryAuthAuditStore:
    return InMemoryAuthAuditStore()


class TestInMemoryAuthAuditStoreRecord:
    @pytest.mark.asyncio
    async def test_record_and_count(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "keycloak"))
        assert store.count() == 1

    @pytest.mark.asyncio
    async def test_record_multiple(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "keycloak"))
        await store.record(login_success_event("u2", "keycloak"))
        assert store.count() == 2


class TestInMemoryAuthAuditStoreGetEvents:
    @pytest.mark.asyncio
    async def test_get_events_by_principal(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u2", "k1"))
        events = await store.get_events("u1")
        assert len(events) == 2
        assert all(e.principal_id == "u1" for e in events)

    @pytest.mark.asyncio
    async def test_get_events_empty(self, store: InMemoryAuthAuditStore) -> None:
        events = await store.get_events("nobody")
        assert events == []

    @pytest.mark.asyncio
    async def test_get_events_respects_limit(
        self, store: InMemoryAuthAuditStore
    ) -> None:
        for _ in range(5):
            await store.record(login_success_event("u1", "k1"))
        events = await store.get_events("u1", limit=2)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_events_filter_by_type(
        self, store: InMemoryAuthAuditStore
    ) -> None:
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_failed_event("k1", principal_id="u1"))
        await store.record(login_success_event("u1", "k1"))
        events = await store.get_events("u1", event_types=[AuthEventType.LOGIN_SUCCESS])
        assert len(events) == 2
        assert all(e.event_type == AuthEventType.LOGIN_SUCCESS for e in events)


class TestInMemoryAuthAuditStoreGetEventsByType:
    @pytest.mark.asyncio
    async def test_get_events_by_type(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u2", "k1"))
        await store.record(login_failed_event("k1"))
        events = await store.get_events_by_type(AuthEventType.LOGIN_SUCCESS)
        assert len(events) == 2
        assert all(e.event_type == AuthEventType.LOGIN_SUCCESS for e in events)

    @pytest.mark.asyncio
    async def test_get_events_by_type_limit(
        self, store: InMemoryAuthAuditStore
    ) -> None:
        for i in range(5):
            await store.record(
                AuthAuditEvent(
                    event_type=AuthEventType.LOGIN_SUCCESS,
                    principal_id=f"u{i}",
                )
            )
        events = await store.get_events_by_type(AuthEventType.LOGIN_SUCCESS, limit=2)
        assert len(events) == 2


class TestInMemoryAuthAuditStoreGetRecentFailures:
    @pytest.mark.asyncio
    async def test_get_recent_failures_includes_failure_types(
        self, store: InMemoryAuthAuditStore
    ) -> None:
        await store.record(login_failed_event("k1", principal_id="u1"))
        failures = await store.get_recent_failures(principal_id="u1", minutes=15)
        assert len(failures) == 1
        assert failures[0].event_type == AuthEventType.LOGIN_FAILED

    @pytest.mark.asyncio
    async def test_get_recent_failures_filter_by_principal(
        self, store: InMemoryAuthAuditStore
    ) -> None:
        await store.record(login_failed_event("k1", principal_id="u1"))
        await store.record(login_failed_event("k1", principal_id="u2"))
        failures = await store.get_recent_failures(principal_id="u1", minutes=15)
        assert len(failures) == 1
        assert failures[0].principal_id == "u1"


class TestInMemoryAuthAuditStoreClearAndCount:
    @pytest.mark.asyncio
    async def test_clear(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "k1"))
        store.clear()
        assert store.count() == 0
        events = await store.get_events("u1")
        assert events == []

    @pytest.mark.asyncio
    async def test_count_by_type(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u2", "k1"))
        await store.record(login_failed_event("k1"))
        assert store.count_by_type(AuthEventType.LOGIN_SUCCESS) == 2
        assert store.count_by_type(AuthEventType.LOGIN_FAILED) == 1

    @pytest.mark.asyncio
    async def test_count_by_principal(self, store: InMemoryAuthAuditStore) -> None:
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u1", "k1"))
        await store.record(login_success_event("u2", "k1"))
        assert store.count_by_principal("u1") == 2
        assert store.count_by_principal("u2") == 1
        assert store.count_by_principal("u3") == 0
