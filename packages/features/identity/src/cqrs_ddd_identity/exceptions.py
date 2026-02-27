"""Identity-related domain exceptions.

All identity errors inherit from IdentityError which extends DomainError
from cqrs_ddd_core, ensuring proper exception hierarchy.
"""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import DomainError

# ═══════════════════════════════════════════════════════════════
# BASE IDENTITY ERROR
# ═══════════════════════════════════════════════════════════════


class IdentityError(DomainError):
    """Base class for all identity-related domain errors.

    Identity errors represent authentication and authorization failures
    that are domain concerns, not just infrastructure issues.
    """


# ═══════════════════════════════════════════════════════════════
# AUTHENTICATION ERRORS
# ═══════════════════════════════════════════════════════════════


class AuthenticationError(IdentityError):
    """Raised when authentication fails.

    This is the base exception for all authentication failures.
    Use more specific exceptions when possible.
    """


class InvalidTokenError(AuthenticationError):
    """Raised when a token is invalid or malformed.

    Examples:
        - JWT signature verification failed
        - Token format is incorrect
        - Token claims are invalid
    """


class ExpiredTokenError(AuthenticationError):
    """Raised when a token has expired.

    The token was valid at some point but is no longer usable.
    Client should attempt to refresh the token.
    """


class InvalidCredentialsError(AuthenticationError):
    """Raised when username/password credentials are invalid.

    Used by database authentication provider.
    """


class AccountLockedError(IdentityError):
    """Raised when account is locked due to too many failed attempts.

    Attributes:
        lockout_duration: Time in seconds until the account is unlocked.
        failed_attempts: Number of failed attempts that triggered the lock.
    """

    def __init__(
        self,
        message: str = "Account is locked due to too many failed attempts",
        lockout_duration: int | None = None,
        failed_attempts: int | None = None,
    ) -> None:
        super().__init__(message)
        self.lockout_duration = lockout_duration
        self.failed_attempts = failed_attempts


class IdentityPermissionError(IdentityError):
    """Raised when the principal does not have the required role or permission.

    Used by context.require_role() and context.require_permission() so that
    identity-related authorization failures can be distinguished from other errors.
    """


# ═══════════════════════════════════════════════════════════════
# MFA ERRORS
# ═══════════════════════════════════════════════════════════════


class MfaError(IdentityError):
    """Base class for MFA-related errors."""


class MfaRequiredError(MfaError):
    """Raised when MFA verification is required but not completed.

    Carries a pending_token for the client to submit along with TOTP code
    to the "Complete MFA" endpoint.

    Attributes:
        pending_token: Reference to partial authentication state.
            Client must submit this token when completing MFA.
        available_methods: List of available MFA methods the user can use.
            Defaults to ["totp"] if not specified.
    """

    def __init__(
        self,
        message: str = "MFA verification required",
        pending_token: str | None = None,
        available_methods: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.pending_token = pending_token
        self.available_methods = available_methods or ["totp"]


class MfaInvalidError(MfaError):
    """Raised when MFA code is invalid.

    Used when TOTP code or backup code verification fails.
    """


class MfaSetupError(MfaError):
    """Raised when MFA setup fails.

    Examples:
        - TOTP secret generation failed
        - Backup code generation failed
    """


class BackupCodeExhaustedError(MfaError):
    """Raised when all backup codes have been used."""


# ═══════════════════════════════════════════════════════════════
# OAUTH ERRORS
# ═══════════════════════════════════════════════════════════════


class OAuthError(IdentityError):
    """Base class for OAuth-related errors."""


class OAuthStateError(OAuthError):
    """Raised when OAuth state parameter is invalid.

    This indicates a potential CSRF attack or expired session.
    """


class OAuthCallbackError(OAuthError):
    """Raised when OAuth callback processing fails.

    Examples:
        - IdP returned an error
        - Code exchange failed
        - Token validation failed
    """


class PKCEValidationError(OAuthError):
    """Raised when PKCE verification fails.

    The code_verifier does not match the code_challenge.
    """


# ═══════════════════════════════════════════════════════════════
# API KEY ERRORS
# ═══════════════════════════════════════════════════════════════


class ApiKeyError(IdentityError):
    """Base class for API key-related errors."""


class InvalidApiKeyError(ApiKeyError):
    """Raised when API key is invalid or not found."""


class ExpiredApiKeyError(ApiKeyError):
    """Raised when API key has expired."""


# ═══════════════════════════════════════════════════════════════
# SESSION ERRORS
# ═══════════════════════════════════════════════════════════════


class SessionError(IdentityError):
    """Base class for session-related errors."""


class SessionExpiredError(SessionError):
    """Raised when session has expired."""


class SessionInvalidError(SessionError):
    """Raised when session is invalid or not found."""


__all__: list[str] = [
    # Base
    "IdentityError",
    # Authentication
    "AuthenticationError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "InvalidCredentialsError",
    "AccountLockedError",
    "IdentityPermissionError",
    # MFA
    "MfaError",
    "MfaRequiredError",
    "MfaInvalidError",
    "MfaSetupError",
    "BackupCodeExhaustedError",
    # OAuth
    "OAuthError",
    "OAuthStateError",
    "OAuthCallbackError",
    "PKCEValidationError",
    # API Key
    "ApiKeyError",
    "InvalidApiKeyError",
    "ExpiredApiKeyError",
    # Session
    "SessionError",
    "SessionExpiredError",
    "SessionInvalidError",
]
