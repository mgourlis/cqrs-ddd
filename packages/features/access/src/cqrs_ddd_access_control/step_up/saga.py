"""Step-up authentication saga.

Requires ``cqrs-ddd-advanced-core`` (``pip install cqrs-ddd-access-control[advanced]``).

Flow
----
1. :class:`~.events.SensitiveOperationRequested` → suspend (5-minute timeout).
   A separate event handler (typically in the auth layer) should listen to
   this event and deliver an MFA challenge to the user.

2. :class:`~.events.MFAChallengeVerified` → resume, dispatch
   :class:`~.commands.GrantTemporaryElevation` and
   :class:`~.commands.ResumeSensitiveOperation`.  A compensation
   (:class:`~.commands.RevokeElevation`) is pushed onto the stack in case
   subsequent steps fail.

3. :class:`~.events.SensitiveOperationCompleted` → dispatch
   :class:`~.commands.RevokeElevation` and complete the saga.

4. Timeout → dispatch :class:`~.commands.RevokeElevation` and fail.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from cqrs_ddd_advanced_core.sagas import Saga, SagaState

from .commands import GrantTemporaryElevation, ResumeSensitiveOperation, RevokeElevation
from .events import (
    MFAChallengeVerified,
    SensitiveOperationCompleted,
    SensitiveOperationRequested,
)


class StepUpState(SagaState):
    """Persistent state for :class:`StepUpAuthenticationSaga`.

    Extends :class:`cqrs_ddd_advanced_core.sagas.SagaState` with step-up
    specific fields.  All fields are ``None`` until populated by the saga.
    """

    operation_id: str | None = None
    user_id: str | None = None
    required_action: str | None = None
    original_command_data: dict[str, Any] | None = None


class StepUpAuthenticationSaga(Saga[StepUpState]):
    """Orchestrate step-up authentication for sensitive operations.

    Register this saga with the :class:`cqrs_ddd_advanced_core.sagas.SagaRegistry`
    before starting the application::

        registry.register(StepUpAuthenticationSaga, state_factory=StepUpState)

    The identity / auth layer must emit :class:`~.events.MFAChallengeVerified`
    after the user passes the MFA challenge.  The saga will then grant
    temporary elevated access and replay the original command (if
    ``original_command_data`` was provided).

    Attributes:
        listens_to: Event types this saga reacts to.
    """

    listens_to = [
        SensitiveOperationRequested,
        MFAChallengeVerified,
        SensitiveOperationCompleted,
    ]

    state_class = StepUpState

    def __init__(
        self,
        state: StepUpState,
        message_registry: Any | None = None,
        mfa_ttl_seconds: int = 300,
    ) -> None:
        super().__init__(state, message_registry)
        self._mfa_ttl_seconds = mfa_ttl_seconds

        self.on(
            SensitiveOperationRequested,
            handler=lambda event: self._on_sensitive_op_requested(event),
        )
        self.on(
            MFAChallengeVerified, handler=lambda event: self._on_mfa_verified(event)
        )
        self.on(
            SensitiveOperationCompleted,
            handler=lambda event: self._on_operation_completed(event),
        )

    # ── Event handlers ─────────────────────────────────────────────

    async def _on_sensitive_op_requested(
        self, event: SensitiveOperationRequested
    ) -> None:
        """Persist operation context and suspend to wait for MFA."""
        self.state.operation_id = event.operation_id
        self.state.user_id = event.user_id
        self.state.required_action = event.action
        self.state.original_command_data = event.original_command_data
        self.state.current_step = "waiting_for_mfa"

        # Suspend; the auth / identity layer handles sending the MFA challenge
        # by listening to SensitiveOperationRequested independently.
        self.suspend(
            reason="waiting_for_mfa",
            timeout=timedelta(minutes=5),
        )

    async def _on_mfa_verified(self, event: MFAChallengeVerified) -> None:
        """After successful MFA: grant elevation and replay the operation."""
        # Only react if this verification belongs to our user.
        if event.user_id != self.state.user_id:
            return

        self.resume()
        self.state.current_step = "granting_elevation"

        if self.state.required_action and self.state.operation_id:
            self.dispatch(
                GrantTemporaryElevation(
                    user_id=event.user_id,
                    action=self.state.required_action,
                    ttl_seconds=self._mfa_ttl_seconds,
                    correlation_id=self.state.correlation_id,
                )
            )
            # Compensate on failure: revoke elevation automatically.
            self.add_compensation(
                RevokeElevation(
                    user_id=event.user_id,
                    correlation_id=self.state.correlation_id,
                    reason="saga_compensation",
                ),
                description="Revoke temporary elevation on saga failure",
            )
            self.dispatch(
                ResumeSensitiveOperation(
                    operation_id=self.state.operation_id,
                    original_command_data=self.state.original_command_data,
                    correlation_id=self.state.correlation_id,
                )
            )
            self.state.current_step = "resuming_operation"

    async def _on_operation_completed(
        self,
        event: SensitiveOperationCompleted,  # noqa: ARG002
    ) -> None:
        """After the operation completes: revoke elevation and finish."""
        if self.state.user_id:
            self.dispatch(
                RevokeElevation(
                    user_id=self.state.user_id,
                    correlation_id=self.state.correlation_id,
                    reason="completed",
                )
            )
        self.complete()

    async def on_timeout(self) -> None:
        """On MFA timeout: revoke any partial elevation and fail the saga."""
        if self.state.user_id:
            self.dispatch(
                RevokeElevation(
                    user_id=self.state.user_id,
                    correlation_id=self.state.correlation_id,
                    reason="timeout",
                )
            )
        await self.fail(
            f"MFA timeout for operation {self.state.operation_id}",
            compensate=True,
        )
