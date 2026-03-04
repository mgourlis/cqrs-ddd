"""Tests for command handlers (GrantACL, RevokeACL, SetResourcePublic, GrantOwnershipACL)."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.commands import (
    GrantACL,
    GrantOwnershipACL,
    RevokeACL,
    SetResourcePublic,
)
from cqrs_ddd_access_control.events import (
    ACLGrantRequested,
    ACLRevokeRequested,
    ResourceTypePublicSetRequested,
)
from cqrs_ddd_access_control.handlers import (
    GrantACLHandler,
    GrantOwnershipACLHandler,
    RevokeACLHandler,
    SetResourcePublicHandler,
)
from cqrs_ddd_access_control.models import AccessRule
from cqrs_ddd_identity import Principal, set_access_token, set_principal
from cqrs_ddd_identity.context import _access_token_context, _principal_context

# ---------------------------------------------------------------------------
# Auto-clean identity context
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    _principal_context.set(None)
    _access_token_context.set(None)


# ---------------------------------------------------------------------------
# GrantACLHandler
# ---------------------------------------------------------------------------


class TestGrantACLHandler:
    @pytest.mark.asyncio
    async def test_emits_grant_requested_event(self) -> None:
        handler = GrantACLHandler()
        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        resp = await handler.handle(cmd)
        assert resp.result == {"status": "requested"}
        assert len(resp.events) == 1
        event = resp.events[0]
        assert isinstance(event, ACLGrantRequested)
        assert event.resource_type == "order"
        assert event.resource_id == "o-1"
        assert len(event.access_rules) == 1
        rule = event.access_rules[0]
        assert rule.principal_name == "alice"
        assert rule.action == "read"

    @pytest.mark.asyncio
    async def test_with_role_name(self) -> None:
        handler = GrantACLHandler()
        cmd = GrantACL(
            resource_type="doc",
            action="write",
            role_name="editor",
        )
        resp = await handler.handle(cmd)
        event = resp.events[0]
        assert isinstance(event, ACLGrantRequested)
        assert event.access_rules[0].role_name == "editor"
        assert event.access_rules[0].principal_name is None

    @pytest.mark.asyncio
    async def test_with_conditions(self) -> None:
        handler = GrantACLHandler()
        cond = {"op": "=", "attr": "status", "val": "active"}
        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            conditions=cond,
        )
        resp = await handler.handle(cmd)
        rule = resp.events[0].access_rules[0]
        assert rule.conditions == cond

    @pytest.mark.asyncio
    async def test_with_specification_dsl(self) -> None:
        handler = GrantACLHandler()
        spec_dsl = {"type": "eq", "field": "status", "value": "open"}
        cmd = GrantACL(
            resource_type="ticket",
            action="read",
            principal_name="bob",
            specification_dsl=spec_dsl,
        )
        resp = await handler.handle(cmd)
        rule = resp.events[0].access_rules[0]
        assert rule.specification_dsl == spec_dsl

    @pytest.mark.asyncio
    async def test_correlation_and_causation(self) -> None:
        handler = GrantACLHandler()
        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            correlation_id="corr-1",
        )
        resp = await handler.handle(cmd)
        assert resp.correlation_id == "corr-1"
        assert resp.causation_id == cmd.command_id
        assert resp.events[0].correlation_id == "corr-1"
        assert resp.events[0].causation_id == cmd.command_id


# ---------------------------------------------------------------------------
# RevokeACLHandler
# ---------------------------------------------------------------------------


class TestRevokeACLHandler:
    @pytest.mark.asyncio
    async def test_emits_revoke_requested_event(self) -> None:
        handler = RevokeACLHandler()
        cmd = RevokeACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        resp = await handler.handle(cmd)
        assert resp.result == {"status": "requested"}
        assert len(resp.events) == 1
        event = resp.events[0]
        assert isinstance(event, ACLRevokeRequested)
        assert event.resource_type == "order"
        assert event.action == "read"
        assert event.principal_name == "alice"
        assert event.resource_id == "o-1"

    @pytest.mark.asyncio
    async def test_with_role_name(self) -> None:
        handler = RevokeACLHandler()
        cmd = RevokeACL(
            resource_type="doc",
            action="write",
            role_name="editor",
        )
        resp = await handler.handle(cmd)
        event = resp.events[0]
        assert isinstance(event, ACLRevokeRequested)
        assert event.role_name == "editor"
        assert event.principal_name is None


# ---------------------------------------------------------------------------
# SetResourcePublicHandler
# ---------------------------------------------------------------------------


class TestSetResourcePublicHandler:
    @pytest.mark.asyncio
    async def test_emits_public_set_requested_event(self) -> None:
        handler = SetResourcePublicHandler()
        cmd = SetResourcePublic(resource_type="page", is_public=True)
        resp = await handler.handle(cmd)
        assert resp.result == {"status": "requested"}
        assert len(resp.events) == 1
        event = resp.events[0]
        assert isinstance(event, ResourceTypePublicSetRequested)
        assert event.resource_type == "page"
        assert event.is_public is True

    @pytest.mark.asyncio
    async def test_set_private(self) -> None:
        handler = SetResourcePublicHandler()
        cmd = SetResourcePublic(resource_type="page", is_public=False)
        resp = await handler.handle(cmd)
        assert resp.events[0].is_public is False


# ---------------------------------------------------------------------------
# GrantOwnershipACLHandler
# ---------------------------------------------------------------------------


class TestGrantOwnershipACLHandler:
    @pytest.mark.asyncio
    async def test_emits_grant_for_current_principal(
        self, principal: Principal
    ) -> None:
        set_principal(principal)
        handler = GrantOwnershipACLHandler()
        cmd = GrantOwnershipACL(
            resource_type="order",
            resource_id="o-42",
            actions=["read", "write", "delete"],
        )
        resp = await handler.handle(cmd)
        assert resp.result["status"] == "requested"
        assert resp.result["principal"] == "testuser"
        event = resp.events[0]
        assert isinstance(event, ACLGrantRequested)
        assert event.resource_type == "order"
        assert event.resource_id == "o-42"
        assert len(event.access_rules) == 3
        for rule in event.access_rules:
            assert rule.principal_name == "testuser"

    @pytest.mark.asyncio
    async def test_default_actions(self, principal: Principal) -> None:
        set_principal(principal)
        handler = GrantOwnershipACLHandler()
        cmd = GrantOwnershipACL(
            resource_type="doc",
            resource_id="d-1",
        )
        resp = await handler.handle(cmd)
        event = resp.events[0]
        actions = {r.action for r in event.access_rules}
        assert actions == {"read", "write", "delete", "admin"}

    @pytest.mark.asyncio
    async def test_no_principal_raises(self) -> None:
        _principal_context.set(None)
        handler = GrantOwnershipACLHandler()
        cmd = GrantOwnershipACL(
            resource_type="order",
            resource_id="o-1",
        )
        with pytest.raises(Exception):
            await handler.handle(cmd)
