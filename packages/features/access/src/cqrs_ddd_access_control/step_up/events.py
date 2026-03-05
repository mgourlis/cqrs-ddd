"""Step-up authentication domain events.

These events form the vocabulary of the step-up MFA flow:

* :class:`SensitiveOperationRequested` — emitted by a command handler when an
  action requires re-authentication before it may proceed.
* :class:`MFAChallengeVerified` — emitted by the identity / auth layer after
  the user successfully passes an MFA challenge.  The saga listens to this.
* :class:`SensitiveOperationCompleted` — emitted after the resumed operation
  finishes, signalling the saga to revoke the temporary elevation.
* :class:`TemporaryElevationGranted` — audit event: elevation was granted.
* :class:`TemporaryElevationRevoked` — audit event: elevation was revoked.
"""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core import DomainEvent


class SensitiveOperationRequested(DomainEvent):
    """Raised when an action requires step-up authentication.

    Triggers :class:`~.saga.StepUpAuthenticationSaga`.  A separate event
    handler (typically in the auth / identity layer) should listen to this
    event and deliver an MFA challenge to the user.

    Attributes:
        user_id: The user who must re-authenticate.
        operation_id: Unique identifier for this operation attempt.
        action: The ABAC action requiring elevation (e.g. ``"delete_tenant"``).
        original_command_data: Serialised original command for auto-replay
            after successful MFA.  Use :func:`~.utils.serialize_command` to
            produce this dict.
    """

    user_id: str
    operation_id: str
    action: str
    original_command_data: dict[str, Any] | None = None


class MFAChallengeVerified(DomainEvent):
    """Raised after a user successfully verifies an MFA challenge.

    The identity / auth layer should emit this event once it confirms the
    user's OTP, TOTP code, or other factor.
    :class:`~.saga.StepUpAuthenticationSaga` listens for this to resume the
    suspended operation and grant temporary elevated access.

    Attributes:
        user_id: The user who completed the MFA challenge.
        method: The MFA method used (e.g. ``"email"``, ``"sms"``, ``"totp"``).
    """

    user_id: str
    method: str = ""


class SensitiveOperationCompleted(DomainEvent):
    """Raised when a sensitive operation has completed successfully.

    Signals :class:`~.saga.StepUpAuthenticationSaga` to revoke the temporary
    elevation and mark itself as completed.

    Attributes:
        user_id: The user who performed the operation.
        operation_id: The operation identifier
        from :class:`SensitiveOperationRequested`.
    """

    user_id: str
    operation_id: str


class TemporaryElevationGranted(DomainEvent):
    """Audit event: temporary elevated privileges were granted to a user.

    Attributes:
        user_id: The user who received the elevation.
        action: The ABAC action the user is elevated for.
        ttl_seconds: How long the elevation lasts.
    """

    user_id: str
    action: str
    ttl_seconds: int = 300


class TemporaryElevationRevoked(DomainEvent):
    """Audit event: temporary elevated privileges were revoked from a user.

    Attributes:
        user_id: The user whose elevation was revoked.
        reason: Why the elevation was revoked (e.g. ``"completed"``, ``"timeout"``).
    """

    user_id: str
    reason: str = "completed"
