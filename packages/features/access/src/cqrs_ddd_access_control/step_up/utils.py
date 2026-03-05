"""Utility helpers for step-up authentication flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cqrs_ddd_core import Command


def serialize_command(command: Command[Any]) -> dict[str, Any]:
    """Serialise a command so it can be stored and replayed later.

    Use this when emitting :class:`~.events.SensitiveOperationRequested` to
    include the original command for automatic replay after the user passes
    the MFA challenge.

    Expected format consumed by
    :class:`~.handlers.ResumeSensitiveOperationHandler`::

        {
            "module_name": "myapp.application.commands",
            "type_name": "DeleteFile",
            "data": {"file_id": "123", ...},
        }

    Example::

        event = SensitiveOperationRequested(
            user_id=command.user_id,
            operation_id=str(uuid.uuid4()),
            action="delete_tenant",
            original_command_data=serialize_command(command),
        )

    Args:
        command: A Pydantic-based :class:`cqrs_ddd_core.Command` instance.

    Returns:
        A JSON-serialisable dict with ``module_name``, ``type_name``, and
        ``data`` keys.
    """
    cls = type(command)
    return {
        "module_name": cls.__module__,
        "type_name": cls.__qualname__,
        "data": command.model_dump(exclude={"command_id", "correlation_id"}),
    }
