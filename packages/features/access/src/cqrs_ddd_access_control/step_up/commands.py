"""Step-up authentication commands."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core import Command


class GrantTemporaryElevation(Command[dict[str, Any]]):
    """Grant temporary elevated privileges for a specific action.

    Handled by :class:`GrantTemporaryElevationHandler`, which emits
    :class:`~cqrs_ddd_access_control.events.ACLGrantRequested` (processed
    by the priority ACL handler to create the elevation entry in the ABAC
    engine) and :class:`~.events.TemporaryElevationGranted` for audit /
    saga correlation.

    Typically dispatched by :class:`~.StepUpAuthenticationSaga` after
    successful MFA verification.
    """

    user_id: str
    action: str
    ttl_seconds: int = 300


class RevokeElevation(Command[dict[str, Any]]):
    """Revoke temporary elevated privileges for a user.

    If *action* is set, only that specific action's elevation is revoked.
    If *action* is ``None``, the undo service revokes all ACLs created during
    the elevated session (matched by ``correlation_id``).

    Handled by :class:`RevokeElevationHandler`.
    """

    user_id: str
    action: str | None = None  # None → revoke all elevations for user
    reason: str = "completed"


class ResumeSensitiveOperation(Command[dict[str, Any]]):
    """Signal that a suspended sensitive operation may now be resumed.

    If *original_command_data* is provided and a mediator is configured,
    the handler deserializes and dispatches the original command, then
    emits :class:`~.events.SensitiveOperationCompleted`.

    Expected *original_command_data* format (produced by
    :func:`~.utils.serialize_command`)::

        {
            "module_name": "myapp.application.commands",
            "type_name": "DeleteFile",
            "data": {"file_id": "123", ...},
        }

    Handled by :class:`ResumeSensitiveOperationHandler`.
    """

    operation_id: str
    original_command_data: dict[str, Any] | None = None
