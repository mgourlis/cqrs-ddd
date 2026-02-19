"""DeadLetterHandler — route failed messages after max retries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import DeadLetterError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from .envelope import MessageEnvelope


class DeadLetterHandler:
    """Routes messages that fail after max retries to a dead-letter destination.

    Caller provides an async handler that receives the envelope and failure reason;
    typically it publishes to a DLQ topic or stores for inspection.
    """

    def __init__(
        self,
        on_dead_letter: (
            Callable[
                [MessageEnvelope, str, BaseException | None], Coroutine[Any, Any, None]
            ]
            | None
        ) = None,
    ) -> None:
        """Configure dead-letter handling.

        Args:
            on_dead_letter: Async callable (envelope, reason, exception) -> None.
                If None, raising DeadLetterError
                is the only effect when route() is used.
        """
        self._on_dead_letter = on_dead_letter

    async def route(
        self,
        envelope: MessageEnvelope,
        reason: str,
        exception: BaseException | None = None,
    ) -> None:
        """Send the message to dead-letter:
        call on_dead_letter if set, then raise DeadLetterError."""
        if self._on_dead_letter is not None:
            await self._on_dead_letter(envelope, reason, exception)
        raise DeadLetterError(
            reason or "Message failed after max retries",
            message_id=envelope.message_id,
        )
