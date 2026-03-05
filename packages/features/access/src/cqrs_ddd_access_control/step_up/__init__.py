"""Step-up authentication — commands, handlers, events, and saga.

Provides the orchestration side of step-up (re-authentication) flows.
The enforcement side is :func:`~cqrs_ddd_access_control.verify_elevation`.

Typical usage::

    # 1. Emit SensitiveOperationRequested from your command handler
    #    (include original_command_data for auto-replay after MFA)
    event = SensitiveOperationRequested(
        user_id=user_id,
        operation_id=str(uuid.uuid4()),
        action="delete_tenant",
        original_command_data=serialize_command(original_cmd),
    )

    # 2. A separate event handler (in the auth layer) listens
    #    to SensitiveOperationRequested and sends an MFA challenge.

    # 3. After successful MFA, emit MFAChallengeVerified.
    #    StepUpAuthenticationSaga resumes and grants elevation.

    # 4. Enforcement: verify_elevation() checks the ACL in the ABAC engine.
"""

from __future__ import annotations

from .commands import GrantTemporaryElevation, ResumeSensitiveOperation, RevokeElevation
from .events import (
    MFAChallengeVerified,
    SensitiveOperationCompleted,
    SensitiveOperationRequested,
    TemporaryElevationGranted,
    TemporaryElevationRevoked,
)
from .handlers import (
    GrantTemporaryElevationHandler,
    ResumeSensitiveOperationHandler,
    RevokeElevationHandler,
)
from .results import (
    GrantTemporaryElevationResult,
    ResumeSensitiveOperationResult,
    RevokeElevationResult,
)
from .utils import serialize_command

__all__ = [
    # Commands
    "GrantTemporaryElevation",
    "RevokeElevation",
    "ResumeSensitiveOperation",
    # Results
    "GrantTemporaryElevationResult",
    "RevokeElevationResult",
    "ResumeSensitiveOperationResult",
    # Events
    "SensitiveOperationRequested",
    "MFAChallengeVerified",
    "SensitiveOperationCompleted",
    "TemporaryElevationGranted",
    "TemporaryElevationRevoked",
    # Handlers
    "GrantTemporaryElevationHandler",
    "RevokeElevationHandler",
    "ResumeSensitiveOperationHandler",
    # Utilities
    "serialize_command",
]

# Saga is optional — requires cqrs-ddd-advanced-core
try:
    from .saga import StepUpAuthenticationSaga, StepUpState

    __all__ += ["StepUpAuthenticationSaga", "StepUpState"]
except ImportError:
    pass
