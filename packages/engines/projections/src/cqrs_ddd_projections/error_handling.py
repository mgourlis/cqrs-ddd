"""ProjectionErrorPolicy — skip, retry, dead-letter per event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import ProjectionHandlerError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cqrs_ddd_core.domain.events import DomainEvent


class ProjectionErrorPolicy:
    """Per-event error handling: skip, retry with backoff, or dead-letter."""

    SKIP = "skip"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"
    RETRY_THEN_DEAD_LETTER = "retry_then_dead_letter"

    def __init__(
        self,
        policy: str = "skip",
        *,
        max_retries: int = 3,
        dead_letter_callback: Callable[[DomainEvent, Exception], Any] | None = None,
    ) -> None:
        self.policy = policy
        self.max_retries = max_retries
        self.dead_letter_callback = dead_letter_callback
        self._policies: dict[
            str,
            Callable[
                [ProjectionErrorPolicy, DomainEvent, Exception, int],
                Awaitable[None],
            ],
        ] = {}
        self._register_builtin_policies()

    def register_policy(
        self,
        name: str,
        handler: Callable[
            [ProjectionErrorPolicy, DomainEvent, Exception, int],
            Awaitable[None],
        ],
    ) -> None:
        """Register or override a policy handler (OCP extension point)."""
        self._policies[name] = handler

    def _register_builtin_policies(self) -> None:
        self.register_policy(self.SKIP, ProjectionErrorPolicy._handle_skip)
        self.register_policy(self.RETRY, ProjectionErrorPolicy._handle_retry)
        self.register_policy(
            self.DEAD_LETTER,
            ProjectionErrorPolicy._handle_dead_letter,
        )
        self.register_policy(
            self.RETRY_THEN_DEAD_LETTER,
            ProjectionErrorPolicy._handle_retry_then_dead_letter,
        )

    async def _handle_skip(
        self,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        del event, error, attempt
        return

    async def _handle_retry(
        self,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        del event
        if attempt < self.max_retries:
            raise ProjectionHandlerError(str(error)) from error
        raise ProjectionHandlerError(str(error)) from error

    async def _handle_dead_letter(
        self,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        del attempt
        await self._invoke_dead_letter(event, error)
        raise ProjectionHandlerError(str(error)) from error

    async def _handle_retry_then_dead_letter(
        self,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        if attempt < self.max_retries:
            raise ProjectionHandlerError(str(error)) from error
        await self._invoke_dead_letter(event, error)
        raise ProjectionHandlerError(str(error)) from error

    async def _invoke_dead_letter(
        self,
        event: DomainEvent,
        error: Exception,
    ) -> None:
        if self.dead_letter_callback and callable(self.dead_letter_callback):
            res = self.dead_letter_callback(event, error)
            if hasattr(res, "__await__"):
                await res

    async def handle_failure(
        self,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        """Dispatch to the configured policy strategy."""
        handler = self._policies.get(self.policy)
        if handler is None:
            raise ProjectionHandlerError(
                f"Unknown projection error policy: {self.policy}"
            )

        await handler(self, event, error, attempt)
