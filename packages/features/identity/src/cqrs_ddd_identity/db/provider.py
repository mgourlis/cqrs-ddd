"""Database authentication provider with session support.

Provides username/password authentication against a local database.
Generates session tokens that can be resolved via resolve() for middleware compatibility.
Requires IUserCredentialsRepository implementation from the application.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from ..exceptions import (
    AccountLockedError,
    ExpiredTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
    MfaRequiredError,
)
from ..ports import (
    IIdentityProvider,
    ILockoutStore,
    ISessionStore,
    IUserCredentialsRepository,
    TokenResponse,
    UserCredentials,
)
from ..principal import Principal
from .hasher import PasswordHasher


class DatabaseIdentityProvider(IIdentityProvider):
    """Database-based identity provider with session token support.

    Authenticates users against a local database using username/password.
    After successful authentication, issues a session token that can be
    used with `resolve()` for middleware compatibility.

    Features:
    - bcrypt/argon2id password hashing with transparent rehash on login
    - Account lockout after failed attempts
    - Session token generation and management
    - MFA support (requires separate MFA service)
    - Full IIdentityProvider protocol compliance

    Usage Pattern:
        1. Login endpoint calls `authenticate(username, password)`
        2. Returns `TokenResponse` with `access_token` (session token)
        3. Client sends `Authorization: Bearer <session_token>`
        4. Middleware calls `resolve(session_token)` to get Principal

    Example:
        ```python
        # Application provides the repository implementation
        user_repo = SQLAlchemyUserRepository(session)
        lockout_store = RedisLockoutStore(redis)
        session_store = RedisSessionStore(redis)

        provider = DatabaseIdentityProvider(
            user_repository=user_repo,
            lockout_store=lockout_store,
            session_store=session_store,
        )

        # In login endpoint
        @app.post("/login")
        async def login(credentials: LoginRequest):
            try:
                token_response = await provider.authenticate(
                    credentials.username,
                    credentials.password,
                )
                return token_response  # Returns access_token, refresh_token
            except AccountLockedError:
                raise HTTPException(423, "Account locked")
            except InvalidCredentialsError:
                raise HTTPException(401, "Invalid credentials")

        # Middleware automatically uses resolve() with the session token
        ```
    """

    def __init__(
        self,
        *,
        user_repository: IUserCredentialsRepository,
        session_store: ISessionStore,
        password_hasher: PasswordHasher | None = None,
        lockout_store: ILockoutStore | None = None,
        max_failed_attempts: int = 5,
        lockout_duration_seconds: int = 900,  # 15 minutes
        session_ttl_seconds: int = 3600,  # 1 hour
        refresh_token_ttl_seconds: int = 604800,  # 7 days
    ) -> None:
        """Initialize the database identity provider.

        Args:
            user_repository: Repository for user credentials.
            session_store: Session store for session tokens.
            password_hasher: Password hasher (default bcrypt).
            lockout_store: Store for tracking failed attempts (optional).
            max_failed_attempts: Max attempts before lockout (default 5).
            lockout_duration_seconds: Lockout duration (default 900 = 15 min).
            session_ttl_seconds: Session token lifetime (default 3600 = 1 hour).
            refresh_token_ttl_seconds: Refresh token lifetime (default 604800 = 7 days).
        """
        self.user_repository = user_repository
        self.session_store = session_store
        self.password_hasher = password_hasher or PasswordHasher()
        self.lockout_store = lockout_store
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration_seconds = lockout_duration_seconds
        self.session_ttl_seconds = session_ttl_seconds
        self.refresh_token_ttl_seconds = refresh_token_ttl_seconds

    async def resolve(self, token: str) -> Principal:
        """Resolve a session token to Principal.

        Looks up the session token in the session store and returns
        the associated Principal.

        Args:
            token: Session token (access_token from authenticate()).

        Returns:
            Principal for the authenticated user.

        Raises:
            InvalidTokenError: Token is invalid or not found.
            ExpiredTokenError: Session has expired.
        """
        if not token:
            raise InvalidTokenError("Session token is required")

        # Look up session
        session_data = await self.session_store.get(f"session:{token}")
        if session_data is None:
            raise InvalidTokenError("Invalid or expired session token")

        # Check expiration
        expires_at_str = session_data.get("expires_at")
        expires_at: datetime | None = None
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            # Treat naive datetime as UTC
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                await self.session_store.delete(f"session:{token}")
                raise ExpiredTokenError("Session has expired")

        # Reconstruct Principal from session data
        return Principal(
            user_id=session_data["user_id"],
            username=session_data["username"],
            roles=frozenset(session_data.get("roles", [])),
            permissions=frozenset(session_data.get("permissions", [])),
            claims=session_data.get("claims", {}),
            tenant_id=session_data.get("tenant_id"),
            mfa_verified=session_data.get("mfa_verified", False),
            auth_method="db",
            session_id=token,
            expires_at=expires_at if expires_at_str else None,
        )

    async def authenticate(
        self,
        username: str,
        password: str,
        *,
        require_mfa: bool = False,
    ) -> TokenResponse:
        """Authenticate with username and password.

        Validates credentials and issues session tokens.

        Args:
            username: Username or email.
            password: Plaintext password.
            require_mfa: Whether MFA is required for this user.

        Returns:
            TokenResponse with access_token (session token) and refresh_token.

        Raises:
            InvalidCredentialsError: Invalid username or password.
            AccountLockedError: Account is locked.
            MfaRequiredError: MFA verification required.
        """
        # Check lockout
        if self.lockout_store and await self.lockout_store.is_locked(username):
            raise AccountLockedError(
                lockout_duration=self.lockout_duration_seconds,
                failed_attempts=self.max_failed_attempts,
            )

        # Look up user
        user = await self.user_repository.get_by_username(username)
        if user is None:
            # Try email lookup
            user = await self.user_repository.get_by_email(username)

        if user is None:
            await self._record_failure(username)
            raise InvalidCredentialsError("Invalid username or password")

        # Check if account is active
        if not user.is_active or user.is_locked:
            raise InvalidCredentialsError("Account is disabled or locked")

        # Verify password
        if not user.password_hash or not self.password_hasher.verify(
            user.password_hash, password
        ):
            await self._record_failure(username)
            raise InvalidCredentialsError("Invalid username or password")

        # Clear failed attempts on success
        if self.lockout_store:
            await self.lockout_store.clear(username)

        # Check for rehash
        if user.password_hash and self.password_hasher.needs_rehash(user.password_hash):
            new_hash = self.password_hasher.hash(password)
            await self.user_repository.update_password_hash(user.user_id, new_hash)

        # Update last login
        await self.user_repository.update_last_login(user.user_id)

        # Check MFA requirement
        if require_mfa and user.mfa_enabled:
            raise MfaRequiredError(
                pending_token=user.user_id,  # Use user_id as pending token
                available_methods=["totp", "backup"],
            )

        # Generate tokens
        return await self._create_session(user)

    async def _create_session(self, user: UserCredentials) -> TokenResponse:
        """Create a new session for an authenticated user.

        Args:
            user: The authenticated user credentials.

        Returns:
            TokenResponse with access and refresh tokens.
        """
        now = datetime.now(timezone.utc)

        # Generate session tokens
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        # Calculate expiration times
        access_expires_at = now + timedelta(seconds=self.session_ttl_seconds)
        refresh_expires_at = now + timedelta(seconds=self.refresh_token_ttl_seconds)

        # Store access token session
        session_data = {
            "user_id": user.user_id,
            "username": user.username,
            "roles": list(user.roles),
            "permissions": list(user.permissions),
            "claims": {"email": user.email} if user.email else {},
            "tenant_id": user.tenant_id,
            "mfa_verified": False,
            "expires_at": access_expires_at.isoformat(),
            "refresh_token": refresh_token,
        }
        await self.session_store.store(
            f"session:{access_token}",
            session_data,
            ttl=self.session_ttl_seconds,
        )

        # Store refresh token mapping
        refresh_data = {
            "user_id": user.user_id,
            "access_token": access_token,
            "expires_at": refresh_expires_at.isoformat(),
        }
        await self.session_store.store(
            f"refresh:{refresh_token}",
            refresh_data,
            ttl=self.refresh_token_ttl_seconds,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=self.session_ttl_seconds,
            expires_at=access_expires_at,
        )

    async def _record_failure(self, identifier: str) -> None:
        """Record a failed authentication attempt.

        Args:
            identifier: Username or email that failed.
        """
        if not self.lockout_store:
            return

        count = await self.lockout_store.record_failure(identifier)
        if count >= self.max_failed_attempts:
            await self.lockout_store.set_lockout(
                identifier, self.lockout_duration_seconds
            )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token from authenticate().

        Returns:
            New TokenResponse with fresh access_token.

        Raises:
            InvalidTokenError: Refresh token is invalid.
            ExpiredTokenError: Refresh token has expired.
        """
        if not refresh_token:
            raise InvalidTokenError("Refresh token is required")

        # Look up refresh token
        refresh_data = await self.session_store.get(f"refresh:{refresh_token}")
        if refresh_data is None:
            raise InvalidTokenError("Invalid refresh token")

        # Check expiration
        expires_at_str = refresh_data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                await self._cleanup_session(
                    refresh_data.get("access_token"), refresh_token
                )
                raise ExpiredTokenError("Refresh token has expired")

        # Get user for new session
        user_id = refresh_data["user_id"]
        user = await self.user_repository.get_by_username(user_id)
        if user is None:
            # Fallback: try to get from old session
            old_access_token = refresh_data.get("access_token")
            old_session = await self.session_store.get(f"session:{old_access_token}")
            if old_session is None:
                raise InvalidTokenError("User not found")

            # Create a mock user from session data
            user = UserCredentials(
                user_id=old_session["user_id"],
                username=old_session["username"],
                roles=frozenset(old_session.get("roles", [])),
                permissions=frozenset(old_session.get("permissions", [])),
                email=old_session.get("claims", {}).get("email"),
                tenant_id=old_session.get("tenant_id"),
            )

        # Check if account is still active
        if hasattr(user, "is_active") and not user.is_active:
            await self._cleanup_session(refresh_data.get("access_token"), refresh_token)
            raise InvalidTokenError("Account is disabled")

        # Clean up old session
        await self._cleanup_session(refresh_data.get("access_token"), refresh_token)

        # Create new session
        return await self._create_session(user)

    async def _cleanup_session(
        self, access_token: str | None, refresh_token: str
    ) -> None:
        """Clean up session tokens.

        Args:
            access_token: The access token to delete.
            refresh_token: The refresh token to delete.
        """
        if access_token:
            await self.session_store.delete(f"session:{access_token}")
        await self.session_store.delete(f"refresh:{refresh_token}")

    async def logout(self, token: str) -> None:
        """Logout and invalidate the session.

        Args:
            token: The access token (session token) to invalidate.
        """
        if not token:
            return

        # Get session to find refresh token
        session_data = await self.session_store.get(f"session:{token}")
        if session_data:
            refresh_token = session_data.get("refresh_token")
            if refresh_token:
                await self.session_store.delete(f"refresh:{refresh_token}")

        # Delete access token session
        await self.session_store.delete(f"session:{token}")


__all__: list[str] = ["DatabaseIdentityProvider"]
