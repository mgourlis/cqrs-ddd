"""IValidator — composable command-validation protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..cqrs.command import Command
    from ..validation.result import ValidationResult


@runtime_checkable
class IValidator(Protocol):
    """Protocol for command validators.

    Validators are composable via
    :class:`~cqrs_ddd_core.validation.composite.CompositeValidator`.
    """

    async def validate(self, command: Command[Any]) -> ValidationResult:
        """Validate *command* and return a
        :class:`~cqrs_ddd_core.validation.result.ValidationResult`.

        Must return :meth:`ValidationResult.success()` or
        :meth:`ValidationResult.failure(errors)`.
        """
        ...
