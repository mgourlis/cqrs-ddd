"""CompositeValidator — chains multiple validators, collects all errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .result import ValidationResult

if TYPE_CHECKING:
    from ..cqrs.command import Command
    from ..ports.validation import IValidator


class CompositeValidator:
    """Runs a list of validators and merges their results.

    Unlike fail-fast validation, this collects **all** errors across
    all validators before returning.

    Usage::

        validator = CompositeValidator([NameValidator(), PriceValidator()])
        result = await validator.validate(command)
    """

    def __init__(self, validators: list[IValidator] | None = None) -> None:
        self._validators: list[IValidator] = list(validators or [])

    def add(self, validator: IValidator) -> None:
        """Append a validator to the chain."""
        self._validators.append(validator)

    async def validate(self, command: Command[Any]) -> ValidationResult:
        """Run all validators and merge errors."""
        combined = ValidationResult.success()
        for validator in self._validators:
            result = await validator.validate(command)
            combined = combined.merge(result)
        return combined
