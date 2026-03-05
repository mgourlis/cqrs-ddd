"""Command handlers for step-up authentication."""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.handler import CommandHandler
from cqrs_ddd_core.cqrs.response import CommandResponse

from ..events import ACLGrantRequested
from ..models import AccessRule
from .commands import GrantTemporaryElevation, ResumeSensitiveOperation, RevokeElevation
from .events import (
    SensitiveOperationCompleted,
    TemporaryElevationGranted,
    TemporaryElevationRevoked,
)
from .results import (
    GrantTemporaryElevationResult,
    ResumeSensitiveOperationResult,
    RevokeElevationResult,
)

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.mediator import Mediator

logger = logging.getLogger("cqrs_ddd.access.step_up")


class GrantTemporaryElevationHandler(CommandHandler[GrantTemporaryElevationResult]):
    """Handle :class:`~.commands.GrantTemporaryElevation`.

    Emits two events:

    * :class:`~cqrs_ddd_access_control.events.ACLGrantRequested` — processed
      by the priority ACL handler to create a type-level ``"elevation"`` entry
      in the ABAC engine for the user/action pair.
    * :class:`~.events.TemporaryElevationGranted` — audit / saga correlation.

    The correlation chain (``correlation_id`` → ``causation_id``) is
    preserved so that :class:`~.handlers.RevokeElevationHandler` can undo all
    ACLs created during the elevated session via the undo service.

    Typically dispatched by :class:`~.saga.StepUpAuthenticationSaga` after
    :class:`~.events.MFAChallengeVerified`.
    """

    async def handle(
        self, command: Command[GrantTemporaryElevationResult]
    ) -> CommandResponse[GrantTemporaryElevationResult]:
        # Type narrowing: we know this is GrantTemporaryElevation at runtime
        if not isinstance(command, GrantTemporaryElevation):
            raise TypeError(f"Expected GrantTemporaryElevation, got {type(command)}")
        cmd = command
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=cmd.ttl_seconds)

        acl_event = ACLGrantRequested(
            resource_type="elevation",
            resource_id=None,
            access_rules=[
                AccessRule(
                    principal_name=cmd.user_id,
                    action=cmd.action,
                )
            ],
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )
        elevation_event = TemporaryElevationGranted(
            user_id=cmd.user_id,
            action=cmd.action,
            ttl_seconds=cmd.ttl_seconds,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )
        return CommandResponse(
            result=GrantTemporaryElevationResult(
                success=True,
                user_id=cmd.user_id,
                action=cmd.action,
                ttl_seconds=cmd.ttl_seconds,
                expires_at=expires_at,
                message=f"Temporary elevation granted for action '{cmd.action}'",
            ),
            events=[acl_event, elevation_event],
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )


class RevokeElevationHandler(CommandHandler[RevokeElevationResult]):
    """Handle :class:`~.commands.RevokeElevation`.

    Optionally uses an *undo_service* to replay-revoke all ACL entries created
    during the elevated session (matched by ``correlation_id``).  This keeps
    the undo bus the single source of truth for ACL removal.

    Args:
        undo_service: Optional service with an async ``undo(correlation_id)``
            method.  When omitted the handler still emits
            :class:`~.events.TemporaryElevationRevoked` for audit purposes.
    """

    def __init__(self, undo_service: Any | None = None) -> None:
        self.undo_service = undo_service

    async def handle(
        self, command: Command[RevokeElevationResult]
    ) -> CommandResponse[RevokeElevationResult]:
        # Type narrowing: we know this is RevokeElevation at runtime
        if not isinstance(command, RevokeElevation):
            raise TypeError(f"Expected RevokeElevation, got {type(command)}")
        cmd = command
        undo_performed = False
        if self.undo_service and cmd.correlation_id:
            try:
                await self.undo_service.undo(correlation_id=cmd.correlation_id)
                undo_performed = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to undo ACLs on elevation revoke: %s", exc)

        event = TemporaryElevationRevoked(
            user_id=cmd.user_id,
            reason=cmd.reason,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )
        return CommandResponse(
            result=RevokeElevationResult(
                success=True,
                user_id=cmd.user_id,
                reason=cmd.reason,
                message=(
                    "Temporary elevation revoked (ACLs undone)"
                    if undo_performed
                    else "Temporary elevation revoked"
                ),
            ),
            events=[event],
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )


class ResumeSensitiveOperationHandler(CommandHandler[ResumeSensitiveOperationResult]):
    """Handle :class:`~.commands.ResumeSensitiveOperation`.

    If *original_command_data* is present and a *mediator* is configured,
    deserialises the original command and dispatches it through the mediator.
    On success emits :class:`~.events.SensitiveOperationCompleted` so the
    saga can revoke the temporary elevation.

    Args:
        mediator: CQRS mediator used to dispatch the deserialised command.
        operation_store: Legacy operation store (fallback; sets ``resumed=True``
            in the result when the store is configured, even if no command
            data is provided).
    """

    def __init__(
        self,
        mediator: Mediator | None = None,
        operation_store: Any | None = None,
    ) -> None:
        self.mediator = mediator
        self.operation_store = operation_store

    async def handle(
        self, command: Command[ResumeSensitiveOperationResult]
    ) -> CommandResponse[ResumeSensitiveOperationResult]:
        # Type narrowing: we know this is ResumeSensitiveOperation at runtime
        if not isinstance(command, ResumeSensitiveOperation):
            raise TypeError(f"Expected ResumeSensitiveOperation, got {type(command)}")
        cmd = command
        if cmd.original_command_data and self.mediator:
            try:
                original_cmd = self._deserialize_command(cmd.original_command_data)
                if original_cmd is not None:
                    # Propagate correlation_id into the replayed command.
                    if hasattr(original_cmd, "correlation_id") and cmd.correlation_id:
                        original_cmd = original_cmd.model_copy(
                            update={"correlation_id": cmd.correlation_id}
                        )
                    await self.mediator.send(original_cmd)

                    completed = SensitiveOperationCompleted(
                        user_id=getattr(original_cmd, "user_id", "") or "",
                        operation_id=cmd.operation_id,
                        correlation_id=cmd.correlation_id,
                        causation_id=cmd.command_id,
                    )
                    return CommandResponse(
                        result=ResumeSensitiveOperationResult(
                            success=True,
                            operation_id=cmd.operation_id,
                            resumed=True,
                            message="Original command dispatched successfully",
                        ),
                        events=[completed],
                        correlation_id=cmd.correlation_id,
                        causation_id=cmd.command_id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to dispatch original command: %s", exc)
                return CommandResponse(
                    result=ResumeSensitiveOperationResult(
                        success=False,
                        operation_id=cmd.operation_id,
                        resumed=False,
                        message=f"Failed to dispatch original command: {exc}",
                    ),
                    events=[],
                    correlation_id=cmd.correlation_id,
                    causation_id=cmd.command_id,
                )

        # Fallback: operation_store-based or no-op signal.
        return CommandResponse(
            result=ResumeSensitiveOperationResult(
                success=True,
                operation_id=cmd.operation_id,
                resumed=bool(self.operation_store),
                message=(
                    "Operation resume signal sent"
                    if self.operation_store
                    else "No command data or mediator configured"
                ),
            ),
            events=[],
            correlation_id=cmd.correlation_id,
            causation_id=cmd.command_id,
        )

    @staticmethod
    def _deserialize_command(command_data: dict[str, Any]) -> Any | None:
        """Deserialise a command from the format produced by :
        func:`~.utils.serialize_command`."""
        module_name = command_data.get("module_name")
        type_name = command_data.get("type_name")
        data = command_data.get("data", {})

        if not module_name or not type_name:
            logger.warning(
                "Cannot deserialize command: missing module_name or type_name"
            )
            return None
        try:
            module = importlib.import_module(module_name)
            command_class = getattr(module, type_name)
            return command_class(**data)
        except (ImportError, AttributeError) as exc:
            logger.error(
                "Failed to deserialize command %s.%s: %s", module_name, type_name, exc
            )
            return None
