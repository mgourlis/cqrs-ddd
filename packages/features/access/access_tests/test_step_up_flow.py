"""End-to-end flow tests for step-up authentication.

Tests the complete lifecycle:
  SensitiveOperationRequested
    → StepUpAuthenticationSaga suspends
  MFAChallengeVerified
    → Saga resumes → dispatches GrantTemporaryElevation + ResumeSensitiveOperation
  GrantTemporaryElevationHandler
    → ACLGrantRequested emitted
  ACLGrantRequestedHandler (priority)
    → ACL created in admin port, ACLGranted stored in event store
  ResumeSensitiveOperationHandler
    → original command replayed, SensitiveOperationCompleted emitted
  SensitiveOperationCompleted
    → Saga dispatches RevokeElevation, marks COMPLETED
  RevokeElevationHandler
    → undo_service called, TemporaryElevationRevoked emitted
  verify_elevation()
    → returns False (elevation has been revoked)

Also covers: MFA timeout → compensation → saga FAILED.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_access_control.acl_handlers import ACLGrantRequestedHandler
from cqrs_ddd_access_control.elevation import verify_elevation
from cqrs_ddd_access_control.events import ACLGrantRequested
from cqrs_ddd_access_control.exceptions import ElevationRequiredError
from cqrs_ddd_access_control.step_up import (
    GrantTemporaryElevation,
    GrantTemporaryElevationHandler,
    MFAChallengeVerified,
    ResumeSensitiveOperation,
    ResumeSensitiveOperationHandler,
    RevokeElevation,
    RevokeElevationHandler,
    SensitiveOperationCompleted,
    SensitiveOperationRequested,
    serialize_command,
)
from cqrs_ddd_access_control.step_up.events import (
    TemporaryElevationGranted,
    TemporaryElevationRevoked,
)
from cqrs_ddd_access_control.step_up.saga import StepUpAuthenticationSaga, StepUpState
from cqrs_ddd_advanced_core.sagas import SagaStatus

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _EventStore:
    """Minimal in-memory event store that tracks appended events."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def append(self, event: Any) -> None:
        self.events.append(event)

    def by_type(self, cls: type) -> list[Any]:
        return [e for e in self.events if isinstance(e, cls)]


class _InMemoryAuthPort:
    """Minimal authorization port that mirrors elevations granted via the admin port."""

    def __init__(self, admin_port: Any) -> None:
        self._admin = admin_port

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        **_: Any,
    ) -> list[str]:
        """Return non-empty list when the admin port has a matching ACL."""
        matching = [
            a
            for a in self._admin.acls
            if a.get("resource_type") == resource_type and a.get("action") == action
        ]
        # For elevation checks resource_ids is None — return a sentinel if found
        if matching:
            return ["elevated"]
        return []


def _make_saga(correlation_id: str = "corr-test") -> StepUpAuthenticationSaga:
    state = StepUpState(id=correlation_id, saga_type="StepUpAuthenticationSaga")
    # Set state's correlation_id so handlers can propagate it
    object.__setattr__(state, "correlation_id", correlation_id)
    return StepUpAuthenticationSaga(state)


# ---------------------------------------------------------------------------
# Helper: run a saga step and collect commands
# ---------------------------------------------------------------------------


async def _drive(saga: StepUpAuthenticationSaga, event: Any) -> list[Any]:
    await saga.handle(event)
    return saga.collect_commands()


# ---------------------------------------------------------------------------
# Test: full happy path
# ---------------------------------------------------------------------------


class TestStepUpFullFlow:
    """Complete happy-path step-up flow."""

    @pytest.mark.asyncio
    async def test_full_flow(self, stub_admin_port: Any) -> None:
        """
        Full flow:
          1. SensitiveOperationRequested → saga suspends
          2. MFAChallengeVerified → saga resumes, produces Grant + Resume commands
          3. GrantTemporaryElevationHandler → ACLGrantRequested + audit event
          4. ACLGrantRequestedHandler → ACL created, ACLGranted stored
          5. verify_elevation → True (ACL present)
          6. ResumeSensitiveOperationHandler → operation_store resume signal
          7. SensitiveOperationCompleted → saga dispatches RevokeElevation, completes
          8. RevokeElevationHandler → undo called, TemporaryElevationRevoked emitted
          9. verify_elevation → False (ElevationRequiredError)
        """
        event_store = _EventStore()
        undo_service = AsyncMock()
        auth_port = _InMemoryAuthPort(stub_admin_port)
        correlation_id = "corr-happy"

        # --- Step 1: sensitive operation requested -----------------------
        saga = _make_saga(correlation_id)
        op_event = SensitiveOperationRequested(
            user_id="u1",
            operation_id="op-42",
            action="delete_resource",
            correlation_id=correlation_id,
        )
        cmds = await _drive(saga, op_event)
        assert saga.state.status == SagaStatus.SUSPENDED
        assert saga.state.current_step == "waiting_for_mfa"
        assert cmds == []  # MFA challenge delivered externally

        # --- Step 2: MFA verified ----------------------------------------
        mfa_event = MFAChallengeVerified(
            user_id="u1",
            method="email",
            correlation_id=correlation_id,
        )
        cmds = await _drive(saga, mfa_event)
        assert saga.state.status == SagaStatus.RUNNING
        assert len(cmds) == 2
        grant_cmd, resume_cmd = cmds
        assert isinstance(grant_cmd, GrantTemporaryElevation)
        assert grant_cmd.user_id == "u1"
        assert grant_cmd.action == "delete_resource"
        assert isinstance(resume_cmd, ResumeSensitiveOperation)
        assert resume_cmd.operation_id == "op-42"

        # --- Step 3: GrantTemporaryElevationHandler ----------------------
        grant_handler = GrantTemporaryElevationHandler()
        grant_resp = await grant_handler.handle(grant_cmd)

        assert grant_resp.result.success
        assert grant_resp.result.expires_at is not None
        assert len(grant_resp.events) == 2
        acl_req, teg = grant_resp.events
        assert isinstance(acl_req, ACLGrantRequested)
        assert acl_req.resource_type == "elevation"
        assert acl_req.access_rules[0].principal_name == "u1"
        assert isinstance(teg, TemporaryElevationGranted)

        # --- Step 4: priority ACL handler --------------------------------
        acl_priority = ACLGrantRequestedHandler(stub_admin_port, event_store)
        await acl_priority(acl_req)

        elevation_acls = [
            a for a in stub_admin_port.acls if a.get("resource_type") == "elevation"
        ]
        assert len(elevation_acls) == 1
        assert elevation_acls[0]["action"] == "delete_resource"
        assert elevation_acls[0]["principal_name"] == "u1"

        # ACLGranted stored for undo tracking
        from cqrs_ddd_access_control.events import ACLGranted

        assert len(event_store.by_type(ACLGranted)) == 1

        # --- Step 5: verify_elevation → True -----------------------------
        from cqrs_ddd_identity import set_access_token
        from cqrs_ddd_identity.context import _access_token_context

        _access_token_context.set("tok-u1")
        elevated = await verify_elevation(
            auth_port, "delete_resource", on_fail="return"
        )
        assert elevated is True

        # --- Step 6: ResumeSensitiveOperationHandler ---------------------
        operation_store = AsyncMock()
        resume_handler = ResumeSensitiveOperationHandler(
            operation_store=operation_store
        )
        resume_resp = await resume_handler.handle(resume_cmd)
        assert resume_resp.result.success
        assert resume_resp.result.resumed is True

        # --- Step 7: SensitiveOperationCompleted → saga finishes ---------
        completed_event = SensitiveOperationCompleted(
            user_id="u1",
            operation_id="op-42",
            correlation_id=correlation_id,
        )
        cmds = await _drive(saga, completed_event)
        assert saga.state.status == SagaStatus.COMPLETED
        assert len(cmds) == 1
        revoke_cmd = cmds[0]
        assert isinstance(revoke_cmd, RevokeElevation)
        assert revoke_cmd.user_id == "u1"
        assert revoke_cmd.reason == "completed"

        # --- Step 8: RevokeElevationHandler ------------------------------
        revoke_handler = RevokeElevationHandler(undo_service=undo_service)
        revoke_resp = await revoke_handler.handle(revoke_cmd)
        assert revoke_resp.result.success
        assert len(revoke_resp.events) == 1
        assert isinstance(revoke_resp.events[0], TemporaryElevationRevoked)

        # Undo service was invoked (would remove the ACL from admin port in prod)
        undo_service.undo.assert_awaited_once()

        # --- Step 9: verify_elevation → False (elevation revoked) --------
        # Simulate undo by removing the elevation ACL from stub admin port
        stub_admin_port.acls = [
            a for a in stub_admin_port.acls if a.get("resource_type") != "elevation"
        ]
        with pytest.raises(ElevationRequiredError):
            await verify_elevation(auth_port, "delete_resource")

        _access_token_context.set(None)


# ---------------------------------------------------------------------------
# Test: MFA timeout path
# ---------------------------------------------------------------------------


class TestStepUpTimeoutFlow:
    """Saga timeout → compensation dispatched, saga FAILED."""

    @pytest.mark.asyncio
    async def test_timeout_dispatches_revoke_and_fails(self) -> None:
        saga = _make_saga("corr-timeout")

        op_event = SensitiveOperationRequested(
            user_id="u2",
            operation_id="op-99",
            action="export_data",
            correlation_id="corr-timeout",
        )
        await _drive(saga, op_event)
        assert saga.state.status == SagaStatus.SUSPENDED

        # Simulate timeout
        await saga.on_timeout()

        cmds = saga.collect_commands()
        assert saga.state.status == SagaStatus.FAILED
        # RevokeElevation was dispatched as the cleanup command
        revoke_cmds = [c for c in cmds if isinstance(c, RevokeElevation)]
        assert len(revoke_cmds) == 1
        assert revoke_cmds[0].user_id == "u2"
        assert revoke_cmds[0].reason == "timeout"


# ---------------------------------------------------------------------------
# Test: wrong user MFA verification is ignored
# ---------------------------------------------------------------------------


class TestStepUpWrongUser:
    """MFAChallengeVerified for a different user is silently ignored."""

    @pytest.mark.asyncio
    async def test_wrong_user_mfa_ignored(self) -> None:
        saga = _make_saga("corr-wrong")

        op_event = SensitiveOperationRequested(
            user_id="u1",
            operation_id="op-1",
            action="delete",
            correlation_id="corr-wrong",
        )
        await _drive(saga, op_event)
        assert saga.state.status == SagaStatus.SUSPENDED

        # A different user verifies MFA
        mfa_event = MFAChallengeVerified(
            user_id="u-other",
            method="totp",
            correlation_id="corr-wrong",
        )
        cmds = await _drive(saga, mfa_event)

        # Saga resumed but produced no commands (guard tripped)
        assert cmds == []


# ---------------------------------------------------------------------------
# Test: auto-replay of original command via mediator
# ---------------------------------------------------------------------------


class TestStepUpAutoReplay:
    """When original_command_data is set, the handler replays the command."""

    @pytest.mark.asyncio
    async def test_auto_replay_dispatches_original_command(self) -> None:
        mediator = AsyncMock()
        mediator.send = AsyncMock()
        handler = ResumeSensitiveOperationHandler(mediator=mediator)

        # Serialise a GrantTemporaryElevation as a stand-in "original" command
        original = GrantTemporaryElevation(user_id="u3", action="archive")
        cmd_data = serialize_command(original)

        saga = _make_saga("corr-replay")
        op_event = SensitiveOperationRequested(
            user_id="u3",
            operation_id="op-replay",
            action="archive",
            original_command_data=cmd_data,
            correlation_id="corr-replay",
        )
        await _drive(saga, op_event)

        mfa_event = MFAChallengeVerified(
            user_id="u3", method="sms", correlation_id="corr-replay"
        )
        cmds = await _drive(saga, mfa_event)
        _, resume_cmd = cmds  # GrantTemporaryElevation, ResumeSensitiveOperation

        assert isinstance(resume_cmd, ResumeSensitiveOperation)
        assert resume_cmd.original_command_data is not None

        result = await handler.handle(resume_cmd)

        assert result.result.success
        assert result.result.resumed is True
        mediator.send.assert_awaited_once()
        # SensitiveOperationCompleted emitted to drive saga forward
        from cqrs_ddd_access_control.step_up.events import (
            SensitiveOperationCompleted as Completed,
        )

        assert any(isinstance(e, Completed) for e in result.events)
