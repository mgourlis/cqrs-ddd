"""Unit tests for step-up authentication handlers and utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_access_control.events import ACLGrantRequested
from cqrs_ddd_access_control.step_up import (
    GrantTemporaryElevation,
    GrantTemporaryElevationHandler,
    ResumeSensitiveOperation,
    ResumeSensitiveOperationHandler,
    RevokeElevation,
    RevokeElevationHandler,
    serialize_command,
)
from cqrs_ddd_access_control.step_up.events import (
    TemporaryElevationGranted,
    TemporaryElevationRevoked,
)

# ---------------------------------------------------------------------------
# GrantTemporaryElevationHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_elevation_emits_acl_and_audit_events() -> None:
    handler = GrantTemporaryElevationHandler()
    cmd = GrantTemporaryElevation(
        user_id="u1", action="delete_resource", ttl_seconds=300
    )

    resp = await handler.handle(cmd)

    assert resp.result.success
    assert resp.result.user_id == "u1"
    assert resp.result.action == "delete_resource"
    assert resp.result.ttl_seconds == 300
    assert resp.result.expires_at is not None

    assert len(resp.events) == 2
    acl_evt, elevation_evt = resp.events
    assert isinstance(acl_evt, ACLGrantRequested)
    assert acl_evt.resource_type == "elevation"
    assert acl_evt.access_rules[0].principal_name == "u1"
    assert acl_evt.access_rules[0].action == "delete_resource"

    assert isinstance(elevation_evt, TemporaryElevationGranted)
    assert elevation_evt.user_id == "u1"
    assert elevation_evt.action == "delete_resource"


@pytest.mark.asyncio
async def test_grant_elevation_propagates_correlation_id() -> None:
    handler = GrantTemporaryElevationHandler()
    cmd = GrantTemporaryElevation(
        user_id="u1",
        action="export_data",
        ttl_seconds=60,
        correlation_id="corr-123",
    )
    resp = await handler.handle(cmd)

    assert resp.correlation_id == "corr-123"
    assert resp.events[0].correlation_id == "corr-123"
    assert resp.events[1].correlation_id == "corr-123"


# ---------------------------------------------------------------------------
# RevokeElevationHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_elevation_calls_undo_service() -> None:
    undo_service = AsyncMock()
    handler = RevokeElevationHandler(undo_service=undo_service)
    cmd = RevokeElevation(user_id="u1", reason="completed", correlation_id="corr-abc")

    resp = await handler.handle(cmd)

    assert resp.result.success
    undo_service.undo.assert_awaited_once_with(correlation_id="corr-abc")
    assert "ACLs undone" in resp.result.message


@pytest.mark.asyncio
async def test_revoke_elevation_without_undo_service() -> None:
    handler = RevokeElevationHandler()
    cmd = RevokeElevation(user_id="u2", reason="timeout")

    resp = await handler.handle(cmd)

    assert resp.result.success
    assert resp.result.user_id == "u2"
    assert len(resp.events) == 1
    assert isinstance(resp.events[0], TemporaryElevationRevoked)


@pytest.mark.asyncio
async def test_revoke_elevation_undo_failure_is_logged_not_raised(caplog) -> None:
    undo_service = AsyncMock()
    undo_service.undo.side_effect = RuntimeError("store unavailable")
    handler = RevokeElevationHandler(undo_service=undo_service)
    cmd = RevokeElevation(user_id="u1", correlation_id="corr-x")

    resp = await handler.handle(cmd)

    # Handler should still succeed even if undo fails.
    assert resp.result.success
    assert "ACLs undone" not in resp.result.message


# ---------------------------------------------------------------------------
# ResumeSensitiveOperationHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_operation_with_store_sets_resumed() -> None:
    operation_store = AsyncMock()
    handler = ResumeSensitiveOperationHandler(operation_store=operation_store)
    cmd = ResumeSensitiveOperation(operation_id="op-1")

    resp = await handler.handle(cmd)

    assert resp.result.success
    assert resp.result.operation_id == "op-1"
    assert resp.result.resumed is True


@pytest.mark.asyncio
async def test_resume_operation_no_config_not_resumed() -> None:
    handler = ResumeSensitiveOperationHandler()
    cmd = ResumeSensitiveOperation(operation_id="op-2")

    resp = await handler.handle(cmd)

    assert resp.result.success
    assert resp.result.resumed is False


@pytest.mark.asyncio
async def test_resume_operation_dispatches_original_command() -> None:
    """When original_command_data is provided, the handler dispatches it via mediator."""
    mediator = AsyncMock()
    mediator.send = AsyncMock()
    handler = ResumeSensitiveOperationHandler(mediator=mediator)

    # Use GrantTemporaryElevation itself as the "original command" to avoid
    # importing an external module.
    original = GrantTemporaryElevation(user_id="u1", action="delete_resource")
    cmd_data = serialize_command(original)

    cmd = ResumeSensitiveOperation(
        operation_id="op-3",
        original_command_data=cmd_data,
        correlation_id="corr-replay",
    )
    resp = await handler.handle(cmd)

    assert resp.result.success
    assert resp.result.resumed is True
    mediator.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_operation_mediator_failure_returns_failure() -> None:
    mediator = AsyncMock()
    mediator.send.side_effect = RuntimeError("downstream down")
    handler = ResumeSensitiveOperationHandler(mediator=mediator)

    original = GrantTemporaryElevation(user_id="u1", action="act")
    cmd_data = serialize_command(original)
    cmd = ResumeSensitiveOperation(operation_id="op-4", original_command_data=cmd_data)

    resp = await handler.handle(cmd)

    assert not resp.result.success
    assert resp.result.resumed is False


# ---------------------------------------------------------------------------
# serialize_command utility
# ---------------------------------------------------------------------------


def test_serialize_command_round_trip() -> None:
    cmd = GrantTemporaryElevation(user_id="u1", action="delete", ttl_seconds=120)
    data = serialize_command(cmd)

    assert data["module_name"] == GrantTemporaryElevation.__module__
    assert data["type_name"] == "GrantTemporaryElevation"
    assert data["data"]["user_id"] == "u1"
    assert data["data"]["action"] == "delete"
    assert data["data"]["ttl_seconds"] == 120
    # command_id and correlation_id are excluded
    assert "command_id" not in data["data"]
    assert "correlation_id" not in data["data"]


def test_deserialize_command_unknown_module() -> None:
    handler = ResumeSensitiveOperationHandler()
    result = handler._deserialize_command(
        {"module_name": "no.such.module", "type_name": "FakeCmd", "data": {}}
    )
    assert result is None


def test_deserialize_command_missing_keys() -> None:
    handler = ResumeSensitiveOperationHandler()
    result = handler._deserialize_command({})
    assert result is None
