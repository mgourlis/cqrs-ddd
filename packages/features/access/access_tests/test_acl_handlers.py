"""Tests for priority ACL event handlers."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.acl_handlers import (
    ACLGrantRequestedHandler,
    ACLRevokeRequestedHandler,
    ResourceTypePublicSetHandler,
    register_priority_acl_handlers,
)
from cqrs_ddd_access_control.events import (
    ACLGranted,
    ACLGrantRequested,
    ACLRevoked,
    ACLRevokeRequested,
    ResourceTypePublicSet,
    ResourceTypePublicSetRequested,
)
from cqrs_ddd_access_control.exceptions import ACLError
from cqrs_ddd_access_control.models import AccessRule

# ---------------------------------------------------------------------------
# Stub event store
# ---------------------------------------------------------------------------


class _StubEventStore:
    """Minimal event store that collects appended events."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def append(self, event: Any) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Failing admin port
# ---------------------------------------------------------------------------


class _FailingAdminPort:
    """Admin port that raises on every operation."""

    async def create_acl(self, *a: Any, **kw: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def create_acl_from_specification(self, *a: Any, **kw: Any) -> dict[str, Any]:
        raise RuntimeError("spec boom")

    async def delete_acl_by_key(self, *a: Any, **kw: Any) -> dict[str, Any]:
        raise RuntimeError("revoke boom")

    async def set_resource_type_public(self, *a: Any, **kw: Any) -> dict[str, Any]:
        raise RuntimeError("public boom")


# ---------------------------------------------------------------------------
# Stub event dispatcher
# ---------------------------------------------------------------------------


class _StubEventDispatcher:
    """Records registrations for verifying ``register_priority_acl_handlers``."""

    def __init__(self) -> None:
        self.registrations: list[tuple[type, Any]] = []

    def register(self, event_type: type, handler: Any) -> None:
        self.registrations.append((event_type, handler))


# ---------------------------------------------------------------------------
# Tests — ACLGrantRequestedHandler
# ---------------------------------------------------------------------------


class TestACLGrantRequestedHandler:
    @pytest.mark.asyncio
    async def test_creates_acl_and_persists_completion(
        self, stub_admin_port: Any
    ) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(principal_name="alice", action="read"),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)

        # ACL created in admin port
        assert len(stub_admin_port.acls) == 1
        acl = stub_admin_port.acls[0]
        assert acl["resource_type"] == "order"
        assert acl["action"] == "read"
        assert acl["principal_name"] == "alice"

        # Completion event persisted
        assert len(event_store.events) == 1
        completion = event_store.events[0]
        assert isinstance(completion, ACLGranted)
        assert completion.resource_type == "order"
        assert completion.action == "read"
        assert completion.principal_name == "alice"
        assert completion.resource_id == "o-1"

    @pytest.mark.asyncio
    async def test_multiple_rules(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(principal_name="alice", action="read"),
                AccessRule(principal_name="alice", action="write"),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)
        assert len(stub_admin_port.acls) == 2
        assert len(event_store.events) == 2

    @pytest.mark.asyncio
    async def test_with_specification_dsl(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        spec_dsl = {"type": "eq", "field": "status", "value": "open"}
        event = ACLGrantRequested(
            resource_type="ticket",
            resource_id="t-1",
            access_rules=[
                AccessRule(
                    principal_name="bob",
                    action="read",
                    specification_dsl=spec_dsl,
                ),
            ],
            aggregate_id="t-1",
            aggregate_type="ticket",
        )
        await handler(event)
        assert len(stub_admin_port.acls) == 1
        completion = event_store.events[0]
        assert completion.specification_dsl == spec_dsl

    @pytest.mark.asyncio
    async def test_with_conditions(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        cond = {"op": "=", "attr": "status", "val": "active"}
        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(
                    principal_name="alice",
                    action="read",
                    conditions=cond,
                ),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)
        acl = stub_admin_port.acls[0]
        assert acl["conditions"] == cond
        completion = event_store.events[0]
        assert completion.conditions == cond

    @pytest.mark.asyncio
    async def test_tenant_isolation_injected(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(
            stub_admin_port,
            event_store,
            enforce_tenant_isolation=True,
        )

        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(principal_name="alice", action="read"),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)
        acl = stub_admin_port.acls[0]
        # When no existing conditions, tenant condition is applied directly
        assert acl["conditions"]["op"] == "="
        assert acl["conditions"]["attr"] == "tenant_id"

    @pytest.mark.asyncio
    async def test_tenant_isolation_merged_with_existing_conditions(
        self,
        stub_admin_port: Any,
    ) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(
            stub_admin_port,
            event_store,
            enforce_tenant_isolation=True,
        )

        existing_cond = {"op": "=", "attr": "status", "val": "open"}
        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(
                    principal_name="alice",
                    action="read",
                    conditions=existing_cond,
                ),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)
        acl = stub_admin_port.acls[0]
        # Conditions should be AND-combined
        assert acl["conditions"]["op"] == "and"
        assert len(acl["conditions"]["conditions"]) == 2

    @pytest.mark.asyncio
    async def test_no_event_store(self, stub_admin_port: Any) -> None:
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store=None)

        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[AccessRule(principal_name="alice", action="read")],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)  # no error even without event store
        assert len(stub_admin_port.acls) == 1

    @pytest.mark.asyncio
    async def test_rule_resource_id_fallback_to_event(
        self,
        stub_admin_port: Any,
    ) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        # Rule has no resource_id → falls back to event.resource_id
        event = ACLGrantRequested(
            resource_type="order",
            resource_id="fallback-id",
            access_rules=[AccessRule(principal_name="alice", action="read")],
            aggregate_id="fallback-id",
            aggregate_type="order",
        )
        await handler(event)
        acl = stub_admin_port.acls[0]
        assert acl["resource_external_id"] == "fallback-id"
        completion = event_store.events[0]
        assert completion.resource_id == "fallback-id"

    @pytest.mark.asyncio
    async def test_admin_port_error_raises_acl_error(self) -> None:
        handler = ACLGrantRequestedHandler(_FailingAdminPort())
        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[AccessRule(principal_name="alice", action="read")],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        with pytest.raises(ACLError, match="ACL grant failed"):
            await handler(event)

    @pytest.mark.asyncio
    async def test_spec_admin_port_error_raises_acl_error(self) -> None:
        handler = ACLGrantRequestedHandler(_FailingAdminPort())
        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(
                    principal_name="alice",
                    action="read",
                    specification_dsl={"type": "eq"},
                ),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        with pytest.raises(ACLError):
            await handler(event)

    @pytest.mark.asyncio
    async def test_with_role_name(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLGrantRequestedHandler(stub_admin_port, event_store)

        event = ACLGrantRequested(
            resource_type="order",
            resource_id="o-1",
            access_rules=[
                AccessRule(role_name="editor", action="write"),
            ],
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)
        acl = stub_admin_port.acls[0]
        assert acl["role_name"] == "editor"
        assert acl["principal_name"] is None


# ---------------------------------------------------------------------------
# Tests — ACLRevokeRequestedHandler
# ---------------------------------------------------------------------------


class TestACLRevokeRequestedHandler:
    @pytest.mark.asyncio
    async def test_deletes_acl_and_persists_completion(
        self,
        stub_admin_port: Any,
    ) -> None:
        event_store = _StubEventStore()
        handler = ACLRevokeRequestedHandler(stub_admin_port, event_store)

        # Pre-create an ACL
        await stub_admin_port.create_acl(
            "order",
            "read",
            principal_name="alice",
        )
        assert len(stub_admin_port.acls) == 1

        event = ACLRevokeRequested(
            resource_type="order",
            action="read",
            principal_name="alice",
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)

        # ACL should be deleted
        assert len(stub_admin_port.acls) == 0

        # Completion event persisted
        assert len(event_store.events) == 1
        completion = event_store.events[0]
        assert isinstance(completion, ACLRevoked)
        assert completion.resource_type == "order"
        assert completion.action == "read"
        assert completion.principal_name == "alice"

    @pytest.mark.asyncio
    async def test_no_event_store(self, stub_admin_port: Any) -> None:
        handler = ACLRevokeRequestedHandler(stub_admin_port, event_store=None)
        event = ACLRevokeRequested(
            resource_type="order",
            action="read",
            principal_name="alice",
            aggregate_id="o-1",
            aggregate_type="order",
        )
        await handler(event)  # should not raise

    @pytest.mark.asyncio
    async def test_admin_port_error_raises_acl_error(self) -> None:
        handler = ACLRevokeRequestedHandler(_FailingAdminPort())
        event = ACLRevokeRequested(
            resource_type="order",
            action="read",
            principal_name="alice",
            aggregate_id="o-1",
            aggregate_type="order",
        )
        with pytest.raises(ACLError, match="ACL revoke failed"):
            await handler(event)

    @pytest.mark.asyncio
    async def test_with_role_name(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        handler = ACLRevokeRequestedHandler(stub_admin_port, event_store)

        event = ACLRevokeRequested(
            resource_type="doc",
            action="write",
            role_name="editor",
            aggregate_id="d-1",
            aggregate_type="doc",
        )
        await handler(event)
        completion = event_store.events[0]
        assert completion.role_name == "editor"


# ---------------------------------------------------------------------------
# Tests — ResourceTypePublicSetHandler
# ---------------------------------------------------------------------------


class TestResourceTypePublicSetHandler:
    @pytest.mark.asyncio
    async def test_sets_public_and_persists_completion(
        self,
        stub_admin_port: Any,
    ) -> None:
        event_store = _StubEventStore()
        handler = ResourceTypePublicSetHandler(stub_admin_port, event_store)

        # Pre-create resource type
        await stub_admin_port.create_resource_type("page", is_public=False)

        event = ResourceTypePublicSetRequested(
            resource_type="page",
            is_public=True,
            aggregate_type="page",
        )
        await handler(event)

        # Resource type should be public now
        assert stub_admin_port.resource_types["page"]["is_public"] is True

        # Completion event persisted
        assert len(event_store.events) == 1
        completion = event_store.events[0]
        assert isinstance(completion, ResourceTypePublicSet)
        assert completion.resource_type == "page"
        assert completion.is_public is True
        assert completion.previous_public is False

    @pytest.mark.asyncio
    async def test_no_event_store(self, stub_admin_port: Any) -> None:
        handler = ResourceTypePublicSetHandler(stub_admin_port, event_store=None)
        event = ResourceTypePublicSetRequested(
            resource_type="page",
            is_public=True,
            aggregate_type="page",
        )
        await handler(event)  # should not raise

    @pytest.mark.asyncio
    async def test_admin_port_error_raises_acl_error(self) -> None:
        handler = ResourceTypePublicSetHandler(_FailingAdminPort())
        event = ResourceTypePublicSetRequested(
            resource_type="page",
            is_public=True,
            aggregate_type="page",
        )
        with pytest.raises(ACLError, match="Set public failed"):
            await handler(event)


# ---------------------------------------------------------------------------
# Tests — register_priority_acl_handlers
# ---------------------------------------------------------------------------


class TestRegisterPriorityACLHandlers:
    def test_registers_all_three_handlers(self, stub_admin_port: Any) -> None:
        dispatcher = _StubEventDispatcher()
        register_priority_acl_handlers(dispatcher, stub_admin_port)  # type: ignore[arg-type]

        registered_types = [t for t, _ in dispatcher.registrations]
        assert ACLGrantRequested in registered_types
        assert ACLRevokeRequested in registered_types
        assert ResourceTypePublicSetRequested in registered_types
        assert len(dispatcher.registrations) == 3

    def test_passes_event_store(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        dispatcher = _StubEventDispatcher()
        register_priority_acl_handlers(
            dispatcher,
            stub_admin_port,
            event_store=event_store,  # type: ignore[arg-type]
        )
        # Verify handlers got the event store
        for _, handler in dispatcher.registrations:
            assert handler._event_store is event_store

    def test_enforce_tenant_isolation(self, stub_admin_port: Any) -> None:
        dispatcher = _StubEventDispatcher()
        register_priority_acl_handlers(
            dispatcher,
            stub_admin_port,
            enforce_tenant_isolation=True,  # type: ignore[arg-type]
        )
        # Only the grant handler gets the flag
        for event_type, handler in dispatcher.registrations:
            if event_type is ACLGrantRequested:
                assert handler._enforce_tenant_isolation is True
