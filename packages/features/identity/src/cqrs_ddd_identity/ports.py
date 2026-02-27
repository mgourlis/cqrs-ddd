"""Core identity ports (protocols).

These protocols define the interfaces that identity providers and related
services must implement. All ports use @runtime_checkable for isinstance checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .audit.events import AuthAuditEvent, AuthEventType
    from .principal import Principal


# ═══════════════════════════════════════════════════════════════
# IDENTITY PROVIDER PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IIdentityProvider(Protocol):
    """Protocol for identity providers that resolve tokens to Principals.

    Identity providers are responsible for:
    - Validating authentication tokens (JWT, OAuth2, API keys, etc.)
    - Converting tokens to Principal value objects
    - Refreshing expired tokens
    - Logging out users

    Implementations:
        - KeycloakIdentityProvider
        - GenericOAuth2Provider
        - DatabaseIdentityProvider
        - ApiKeyIdentityProvider
        - LDAPIdentityProvider
    """

    async def resolve(self, token: str) -> Principal:
        """Resolve a token to a Principal.

        Args:
            token: The authentication token to resolve.

        Returns:
            Principal value object with user identity information.

        Raises:
            InvalidTokenError: Token is malformed or invalid.
            ExpiredTokenError: Token has expired.
            AuthenticationError: Authentication failed.
            MfaRequiredError: MFA verification required.
        """
        ...

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh an access token.

        Args:
            refresh_token: The refresh token.

        Returns:
            TokenResponse with new access token.

        Raises:
            InvalidTokenError: Refresh token is invalid.
            ExpiredTokenError: Refresh token has expired.
        """
        ...

    async def logout(self, token: str) -> None:
        """Logout and invalidate the token.

        Args:
            token: The token to invalidate.
        """
        ...


@runtime_checkable
class ITokenValidator(Protocol):
    """Protocol for token validation and decoding.

    Token validators are responsible for cryptographic verification
    of JWT tokens and claim extraction.
    """

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate a token and return its claims.

        Verifies:
            - Signature (RS256, ES256, HS256)
            - Expiration (exp claim)
            - Not before (nbf claim)
            - Audience (aud claim)
            - Issuer (iss claim)

        Args:
            token: The JWT token string.

        Returns:
            Dictionary of validated claims.

        Raises:
            InvalidTokenError: Token validation failed.
            ExpiredTokenError: Token has expired.
        """
        ...

    def decode_unsafe(self, token: str) -> dict[str, Any]:
        """Decode a token WITHOUT signature verification.

        WARNING: This does NOT verify the token signature.
        Only use for debugging or when you need to inspect claims
        before validation.

        Args:
            token: The JWT token string.

        Returns:
            Dictionary of claims (UNTRUSTED).
        """
        ...


# ═══════════════════════════════════════════════════════════════
# TOKEN RESPONSE
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TokenResponse:
    """OAuth2 token response from identity provider.

    Attributes:
        access_token: The access token for API calls.
        refresh_token: Token for refreshing the access token.
        token_type: Token type (usually "Bearer").
        expires_in: Access token lifetime in seconds.
        id_token: OpenID Connect ID token (optional).
        scope: Granted scopes.
        expires_at: Calculated expiration datetime.
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int = 3600
    id_token: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        """Calculate expires_at if not set."""
        if self.expires_at is None and self.expires_in > 0:
            object.__setattr__(
                self,
                "expires_at",
                datetime.now(timezone.utc) + timedelta(seconds=self.expires_in),
            )


# ═══════════════════════════════════════════════════════════════
# SESSION STORE PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class ISessionStore(Protocol):
    """Protocol for server-side session storage.

    Used for OAuth2 state parameters, PKCE verifiers, and session data.
    Implementations should use Redis or database-backed storage in production.

    WARNING: InMemorySessionStore is ONLY for development/testing.
    It will NOT work with multiple workers (Gunicorn/Uvicorn with workers>1).
    """

    async def store(
        self, key: str, data: dict[str, Any], ttl: int | None = None
    ) -> None:
        """Store session data.

        Args:
            key: Session key.
            data: Session data dictionary.
            ttl: Time-to-live in seconds (optional).
        """
        ...

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve session data.

        Args:
            key: Session key.

        Returns:
            Session data or None if not found/expired.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete session data.

        Args:
            key: Session key.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if session key exists.

        Args:
            key: Session key.

        Returns:
            True if key exists.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# USER CREDENTIALS REPOSITORY PORT (for DB auth)
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IUserCredentialsRepository(Protocol):
    """Protocol for user credential storage.

    This is a PORT that must be implemented by the application's
    infrastructure layer. The identity package does NOT provide
    implementations - it only defines the interface.

    This keeps the identity package decoupled from specific database schemas.
    """

    async def get_by_username(self, username: str) -> UserCredentials | None:
        """Get user credentials by username.

        Args:
            username: The username to look up.

        Returns:
            UserCredentials or None if not found.
        """
        ...

    async def get_by_email(self, email: str) -> UserCredentials | None:
        """Get user credentials by email.

        Args:
            email: The email to look up.

        Returns:
            UserCredentials or None if not found.
        """
        ...

    async def update_password_hash(self, user_id: str, new_hash: str) -> None:
        """Update user's password hash.

        Called after successful login when rehashing is needed.

        Args:
            user_id: The user ID.
            new_hash: The new password hash.
        """
        ...

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp.

        Args:
            user_id: The user ID.
        """
        ...


@dataclass(frozen=True)
class UserCredentials:
    """User credentials data structure.

    This is returned by IUserCredentialsRepository implementations.
    """

    user_id: str
    username: str
    email: str | None = None
    password_hash: str | None = None
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    is_active: bool = True
    is_locked: bool = False
    tenant_id: str | None = None
    mfa_enabled: bool = False


# ═══════════════════════════════════════════════════════════════
# API KEY REPOSITORY PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IApiKeyRepository(Protocol):
    """Protocol for API key storage.

    This is a PORT that must be implemented by the application's
    infrastructure layer.
    """

    async def get_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        """Get API key record by prefix (first 8 chars).

        Args:
            prefix: The key prefix.

        Returns:
            ApiKeyRecord or None if not found.
        """
        ...

    async def record_usage(self, key_id: str) -> None:
        """Record API key usage (last used timestamp).

        Args:
            key_id: The key ID.
        """
        ...


@dataclass(frozen=True)
class ApiKeyRecord:
    """API key record data structure.

    The full key is stored as SHA-256 hash. Lookup is by prefix (first 8 chars).
    """

    key_id: str
    key_prefix: str  # First 8 chars of original key
    key_hash: str  # SHA-256 hash of full key
    name: str
    user_id: str
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    is_active: bool = True
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


# ═══════════════════════════════════════════════════════════════
# LOCKOUT STORE PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class ILockoutStore(Protocol):
    """Protocol for account lockout tracking.

    Used to track failed authentication attempts and implement
    account lockout after too many failures.

    Implementations should use Redis for distributed systems.
    """

    async def record_failure(self, identifier: str) -> int:
        """Record a failed authentication attempt.

        Args:
            identifier: User identifier (username, IP, etc.).

        Returns:
            Current failure count.
        """
        ...

    async def get_failure_count(self, identifier: str) -> int:
        """Get current failure count.

        Args:
            identifier: User identifier.

        Returns:
            Number of failed attempts.
        """
        ...

    async def is_locked(self, identifier: str) -> bool:
        """Check if identifier is locked.

        Args:
            identifier: User identifier.

        Returns:
            True if locked.
        """
        ...

    async def clear(self, identifier: str) -> None:
        """Clear lockout and failure count.

        Args:
            identifier: User identifier.
        """
        ...

    async def set_lockout(self, identifier: str, duration_seconds: int) -> None:
        """Set explicit lockout for a duration.

        Args:
            identifier: User identifier.
            duration_seconds: Lockout duration in seconds.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# AUDIT PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IAuthAuditStore(Protocol):
    """Protocol for authentication audit event storage.

    Audit stores persist authentication events for compliance,
    security monitoring, and troubleshooting.

    Implementations should support:
    - Persistent storage (database, log files, SIEM)
    - Efficient querying by principal, event type, time range
    - Retention policies for compliance
    """

    async def record(self, event: AuthAuditEvent) -> None:
        """Record an audit event.

        Args:
            event: The audit event to record.
        """
        ...

    async def get_events(
        self,
        principal_id: str,
        *,
        event_types: list[AuthEventType] | None = None,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get audit events for a principal.

        Args:
            principal_id: User/service ID to query.
            event_types: Optional filter by event types.
            limit: Maximum number of events to return.

        Returns:
            List of audit events, most recent first.
        """
        ...

    async def get_events_by_type(
        self,
        event_type: AuthEventType,
        *,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get audit events by type across all principals.

        Args:
            event_type: Event type to query.
            limit: Maximum number of events to return.

        Returns:
            List of audit events, most recent first.
        """
        ...

    async def get_recent_failures(
        self,
        *,
        principal_id: str | None = None,
        minutes: int = 15,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get recent failed authentication events.

        Useful for detecting brute force attacks.

        Args:
            principal_id: Optional filter by principal.
            minutes: Time window in minutes.
            limit: Maximum number of events to return.

        Returns:
            List of failed authentication events.
        """
        ...


__all__: list[str] = [
    # Identity Provider
    "IIdentityProvider",
    "ITokenValidator",
    "TokenResponse",
    # Session
    "ISessionStore",
    # Credentials
    "IUserCredentialsRepository",
    "UserCredentials",
    # API Key
    "IApiKeyRepository",
    "ApiKeyRecord",
    # Lockout
    "ILockoutStore",
    # Audit
    "IAuthAuditStore",
]
