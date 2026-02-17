"""ValidatorMiddleware — validates commands before execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..ports.middleware import IMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..ports.validation import IValidator


class ValidatorMiddleware(IMiddleware):
    """Runs ``IValidator.validate()`` before the handler.

    If validation fails, raises ValidationError.
    """

    def __init__(self, validator: IValidator) -> None:
        self._validator = validator

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Validate the message before passing to next handler."""
        result = await self._validator.validate(message)
        if hasattr(result, "is_valid") and not result.is_valid:
            from ..primitives.exceptions import ValidationError

            raise ValidationError(result.errors)
        return await next_handler(message)
