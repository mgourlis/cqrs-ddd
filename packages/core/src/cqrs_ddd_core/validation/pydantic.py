"""PydanticValidator — leverages Pydantic model validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PydanticValidationError

from .result import ValidationResult

if TYPE_CHECKING:
    from ..cqrs.command import Command


class PydanticValidator:
    """Validates commands using Pydantic model validation.

    Re-validates the command data through its model class and converts
    any ``ValidationError`` into a
    :class:`~cqrs_ddd_core.validation.result.ValidationResult`.
    """

    async def validate(self, command: Command[Any]) -> ValidationResult:
        if not hasattr(command, "model_validate"):
            return ValidationResult.success()

        try:
            type(command).model_validate(command.model_dump())
            return ValidationResult.success()
        except PydanticValidationError as exc:
            errors: dict[str, list[str]] = {}
            for error in exc.errors():
                loc = ".".join(str(p) for p in error.get("loc", ("__root__",)))
                msg = error.get("msg", "validation error")
                errors.setdefault(loc, []).append(msg)
            return ValidationResult.failure(errors)
