"""Tests for ACL undo executors."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.events import (
    ACLGranted,
    ACLGrantRequested,
    ACLRevoked,
    ACLRevokeRequested,
    ResourceTypePublicSet,
    ResourceTypePublicSetRequested,
)
from cqrs_ddd_access_control.undo import (
    ACLGrantedUndoExecutor,
    ACLRevokedUndoExecutor,
    ResourceTypePublicSetUndoExecutor,
    register_acl_undo_executors,
)
from cqrs_ddd_core import DomainEvent
from cqrs_ddd_core.cqrs.response import CommandResponse

# ---------------------------------------------------------------------------
# Stub mediator
# ---------------------------------------------------------------------------


class _StubMediator:
    """Records commands sent through it and returns a CommandResponse."""

    def __init__(self, response_events: list[DomainEvent] | None = None) -> None:
        self.sent: list[Any] = []
        self._events = response_events or []

    async def send(self, command: Any) -> CommandResponse[Any]:
        self.sent.append(command)
        return CommandResponse(
            result={"status": "ok"},
            events=self._events,
        )


# ---------------------------------------------------------------------------
# Stub undo registry
# ---------------------------------------------------------------------------


class _StubUndoRegistry:
    """Collects registered executors."""

    def __init__(self) -> None:
        self.executors: list[Any] = []

    def register(self, executor: Any) -> None:
        self.executors.append(executor)


# ---------------------------------------------------------------------------
# Tests — ACLGrantedUndoExecutor
# ---------------------------------------------------------------------------


class TestACLGrantedUndoExecutor:
    def test_event_type(self) -> None:
        mediator = _StubMediator()
        executor = ACLGrantedUndoExecutor(mediator)  # type: ignore[arg-type]
        assert executor.event_type == "ACLGranted"

    @pytest.mark.asyncio
    async def test_can_undo(self) -> None:
        mediator = _StubMediator()
        executor = ACLGrantedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLGranted(
            resource_type="order",
            action="read",
            principal_name="alice",
        )
        assert await executor.can_undo(event) is True

    @pytest.mark.asyncio
    async def test_can_undo_true_for_valid_event(self) -> None:
        mediator = _StubMediator()
        executor = ACLGrantedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLGranted(
            resource_type="order",
            action="read",
            principal_name="alice",
        )
        # Both resource_type and action are set → can undo
        assert await executor.can_undo(event) is True

    @pytest.mark.asyncio
    async def test_undo_sends_revoke(self) -> None:
        mediator = _StubMediator()
        executor = ACLGrantedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLGranted(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        events = await executor.undo(event)
        assert len(mediator.sent) == 1
        cmd = mediator.sent[0]
        assert cmd.resource_type == "order"
        assert cmd.action == "read"
        assert cmd.principal_name == "alice"
        assert cmd.resource_id == "o-1"
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_redo_sends_grant(self) -> None:
        mediator = _StubMediator()
        executor = ACLGrantedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLGranted(
            resource_type="order",
            action="read",
            principal_name="alice",
            conditions={"op": "=", "attr": "status", "val": "open"},
            specification_dsl={"type": "eq", "field": "status", "value": "open"},
        )
        undo_event = DomainEvent()
        events = await executor.redo(event, undo_event)

        cmd = mediator.sent[0]
        assert cmd.resource_type == "order"
        assert cmd.action == "read"
        assert cmd.conditions == {"op": "=", "attr": "status", "val": "open"}
        assert cmd.specification_dsl == {
            "type": "eq",
            "field": "status",
            "value": "open",
        }
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# Tests — ACLRevokedUndoExecutor
# ---------------------------------------------------------------------------


class TestACLRevokedUndoExecutor:
    def test_event_type(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]
        assert executor.event_type == "ACLRevoked"

    @pytest.mark.asyncio
    async def test_can_undo_with_previous_state(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLRevoked(
            resource_type="order",
            action="read",
            previous_state={"conditions": {"op": "="}},
        )
        assert await executor.can_undo(event) is True

    @pytest.mark.asyncio
    async def test_can_undo_without_previous_state(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLRevoked(
            resource_type="order",
            action="read",
            previous_state=None,
        )
        assert await executor.can_undo(event) is False

    @pytest.mark.asyncio
    async def test_undo_sends_grant_with_previous_conditions(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLRevoked(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
            previous_state={
                "conditions": {"op": "=", "attr": "status", "val": "open"},
                "specification_dsl": {"type": "eq"},
            },
        )
        events = await executor.undo(event)

        cmd = mediator.sent[0]
        assert cmd.resource_type == "order"
        assert cmd.action == "read"
        assert cmd.principal_name == "alice"
        assert cmd.conditions == {"op": "=", "attr": "status", "val": "open"}
        assert cmd.specification_dsl == {"type": "eq"}
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_undo_no_previous_state(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLRevoked(
            resource_type="order",
            action="read",
            principal_name="alice",
            previous_state=None,
        )
        await executor.undo(event)
        cmd = mediator.sent[0]
        # Should still send grant but conditions/spec_dsl extracted from empty dict
        assert cmd.conditions is None
        assert cmd.specification_dsl is None

    @pytest.mark.asyncio
    async def test_redo_sends_revoke(self) -> None:
        mediator = _StubMediator()
        executor = ACLRevokedUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ACLRevoked(
            resource_type="order",
            action="read",
            principal_name="alice",
            role_name="editor",
            resource_id="o-1",
        )
        undo_event = DomainEvent()
        events = await executor.redo(event, undo_event)

        cmd = mediator.sent[0]
        assert cmd.resource_type == "order"
        assert cmd.action == "read"
        assert cmd.principal_name == "alice"
        assert cmd.role_name == "editor"
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# Tests — ResourceTypePublicSetUndoExecutor
# ---------------------------------------------------------------------------


class TestResourceTypePublicSetUndoExecutor:
    def test_event_type(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]
        assert executor.event_type == "ResourceTypePublicSet"

    @pytest.mark.asyncio
    async def test_can_undo_with_previous(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ResourceTypePublicSet(
            resource_type="page",
            is_public=True,
            previous_public=False,
        )
        assert await executor.can_undo(event) is True

    @pytest.mark.asyncio
    async def test_can_undo_without_previous(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ResourceTypePublicSet(
            resource_type="page",
            is_public=True,
            previous_public=None,
        )
        assert await executor.can_undo(event) is False

    @pytest.mark.asyncio
    async def test_undo_sends_set_with_previous_value(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ResourceTypePublicSet(
            resource_type="page",
            is_public=True,
            previous_public=False,
        )
        events = await executor.undo(event)

        cmd = mediator.sent[0]
        assert cmd.resource_type == "page"
        assert cmd.is_public is False
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_undo_without_previous_inverts(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ResourceTypePublicSet(
            resource_type="page",
            is_public=True,
            previous_public=None,
        )
        await executor.undo(event)

        cmd = mediator.sent[0]
        # When previous_public is None, inverts is_public
        assert cmd.is_public is False

    @pytest.mark.asyncio
    async def test_redo_sends_original(self) -> None:
        mediator = _StubMediator()
        executor = ResourceTypePublicSetUndoExecutor(mediator)  # type: ignore[arg-type]

        event = ResourceTypePublicSet(
            resource_type="page",
            is_public=True,
            previous_public=False,
        )
        undo_event = DomainEvent()
        events = await executor.redo(event, undo_event)

        cmd = mediator.sent[0]
        assert cmd.resource_type == "page"
        assert cmd.is_public is True
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# Tests — register_acl_undo_executors
# ---------------------------------------------------------------------------


class TestRegisterACLUndoExecutors:
    def test_registers_all_three(self) -> None:
        registry = _StubUndoRegistry()
        mediator = _StubMediator()
        register_acl_undo_executors(registry, mediator)  # type: ignore[arg-type]

        assert len(registry.executors) == 3
        types = {e.event_type for e in registry.executors}
        assert types == {"ACLGranted", "ACLRevoked", "ResourceTypePublicSet"}
