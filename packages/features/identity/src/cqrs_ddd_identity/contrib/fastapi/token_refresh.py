"""Token refresh adapter and FastAPI middleware.

Provides proactive token refresh capabilities to prevent session expiration
during active use.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from starlette.middleware.base import BaseHTTPMiddleware

from ...context import (
    clear_tokens,
    get_access_token,
    get_refresh_token,
    set_access_token,
    set_refresh_token,
)
from ...ports import IIdentityProvider, TokenResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import Request, Response

    from ...principal import Principal


@dataclass(frozen=True)
class TokenRefreshConfig:
    """Configuration for token refresh behavior.

    Attributes:
        refresh_threshold_seconds: Seconds before expiry to trigger refresh.
        max_refresh_attempts: Maximum refresh retry attempts on failure.
        sliding_session: Whether to refresh on every request.
        store_refreshed_tokens: Whether to update context with new tokens.
        on_token_refreshed: Callback when tokens are refreshed.
    """

    refresh_threshold_seconds: int = 300  # 5 minutes before expiry
    max_refresh_attempts: int = 3
    sliding_session: bool = True
    store_refreshed_tokens: bool = True
    on_token_refreshed: Callable[[TokenResponse], None] | None = None


class TokenRefreshAdapter(IIdentityProvider):
    """Wraps an identity provider with proactive token refresh.

    This adapter checks if the access token is about to expire and
    automatically refreshes it before it does, ensuring seamless
    user experience without interrupted sessions.

    Example:
        ```python
        keycloak_provider = KeycloakIdentityProvider(config)
        refresh_adapter = TokenRefreshAdapter(
            provider=keycloak_provider,
            config=TokenRefreshConfig(
                refresh_threshold_seconds=300,
            ),
        )

        # Use refresh_adapter instead of keycloak_provider
        principal = await refresh_adapter.resolve(token)
        ```
    """

    def __init__(
        self,
        provider: IIdentityProvider,
        config: TokenRefreshConfig | None = None,
    ) -> None:
        """Initialize the token refresh adapter.

        Args:
            provider: The underlying identity provider.
            config: Token refresh configuration.
        """
        self._provider = provider
        self._config = config or TokenRefreshConfig()

    @property
    def provider(self) -> IIdentityProvider:
        """Get the underlying identity provider."""
        return self._provider

    @property
    def config(self) -> TokenRefreshConfig:
        """Get the token refresh configuration."""
        return self._config

    def _should_refresh(self, expires_at: datetime | None) -> bool:
        """Check if token should be refreshed.

        Args:
            expires_at: Token expiration time.

        Returns:
            True if refresh should be triggered.
        """
        if expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=self._config.refresh_threshold_seconds)

        return expires_at <= now + threshold

    async def _do_refresh(self, refresh_token: str) -> TokenResponse | None:
        """Attempt to refresh the token.

        Args:
            refresh_token: The refresh token.

        Returns:
            New TokenResponse or None if refresh failed.
        """

        for _attempt in range(self._config.max_refresh_attempts):
            try:
                return await self._provider.refresh(refresh_token)
            except Exception:
                # Log warning about failed attempt (would use logging in production)
                continue

        # All attempts failed
        return None

    async def resolve(self, token: str) -> Principal:
        """Resolve token to Principal, triggering refresh if needed.

        Args:
            token: The access token to resolve.

        Returns:
            Principal for the authenticated user.

        Raises:
            InvalidTokenError: Token is invalid.
            ExpiredTokenError: Token has expired and refresh failed.
        """
        # First resolve to get the principal and expiry
        principal = await self._provider.resolve(token)

        # Check if we should proactively refresh
        if self._should_refresh(principal.expires_at):
            refresh_token = get_refresh_token()

            if refresh_token:
                new_tokens = await self._do_refresh(refresh_token)

                if new_tokens:
                    # Store new tokens in context if configured
                    if self._config.store_refreshed_tokens:
                        set_access_token(new_tokens.access_token)
                        if new_tokens.refresh_token:
                            set_refresh_token(new_tokens.refresh_token)

                    # Call refresh callback if set
                    if self._config.on_token_refreshed:
                        try:
                            self._config.on_token_refreshed(new_tokens)
                        except Exception:
                            pass  # Don't fail on callback errors

        return principal

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
        return await self._provider.refresh(refresh_token)

    async def logout(self, token: str) -> None:
        """Logout and invalidate the token.

        Also clears tokens from context.

        Args:
            token: The token to invalidate.
        """
        try:
            await self._provider.logout(token)
        finally:
            clear_tokens()


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for proactive token refresh.

    This middleware intercepts responses and checks if the access token
    needs to be refreshed. If so, it performs the refresh and adds the
    new tokens to the response headers.

    Must be used AFTER AuthenticationMiddleware.

    Example:
        ```python
        from fastapi import FastAPI
        from cqrs_ddd_identity.contrib.fastapi import (
            AuthenticationMiddleware,
            TokenRefreshMiddleware,
        )

        app = FastAPI()

        # Add authentication middleware first
        app.add_middleware(
            AuthenticationMiddleware,
            identity_provider=keycloak_provider,
        )

        # Then add token refresh middleware
        app.add_middleware(
            TokenRefreshMiddleware,
            identity_provider=keycloak_provider,
            config=TokenRefreshConfig(
                refresh_threshold_seconds=300,
            ),
            token_header="X-New-Access-Token",
            refresh_header="X-New-Refresh-Token",
        )
        ```
    """

    def __init__(
        self,
        app: Any,
        *,
        identity_provider: IIdentityProvider,
        config: TokenRefreshConfig | None = None,
        token_header: str = "X-New-Access-Token",
        refresh_header: str = "X-New-Refresh-Token",
    ) -> None:
        """Initialize the middleware.

        Args:
            app: FastAPI/Starlette application.
            identity_provider: Identity provider for token refresh.
            config: Token refresh configuration.
            token_header: Header name for new access token.
            refresh_header: Header name for new refresh token.
        """
        super().__init__(app)
        self.identity_provider = identity_provider
        self.config = config or TokenRefreshConfig()
        self.token_header = token_header
        self.refresh_header = refresh_header

    def _should_refresh(self, expires_at: datetime | None) -> bool:
        """Check if token should be refreshed."""
        if expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        threshold = timedelta(seconds=self.config.refresh_threshold_seconds)

        return expires_at <= now + threshold

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Process the request.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response with potentially new token headers.
        """
        # Process the request first
        response = await call_next(request)

        # Check if we have tokens to potentially refresh
        access_token = get_access_token()
        refresh_token = get_refresh_token()

        if not access_token or not refresh_token:
            return cast("Response", response)

        # Check if we should refresh based on sliding session or expiry
        # For sliding session, we'd need access to principal.expires_at
        # which requires resolving the token. We can check context instead.
        # This is a simplified implementation - in production you might
        # want to decode the JWT to check exp claim directly.

        if self.config.sliding_session:
            # Perform refresh for sliding sessions
            try:
                new_tokens = await self.identity_provider.refresh(refresh_token)

                # Update context
                if self.config.store_refreshed_tokens:
                    set_access_token(new_tokens.access_token)
                    if new_tokens.refresh_token:
                        set_refresh_token(new_tokens.refresh_token)

                # Add new tokens to response headers
                response.headers[self.token_header] = new_tokens.access_token
                if new_tokens.refresh_token:
                    response.headers[self.refresh_header] = new_tokens.refresh_token

                # Call callback if set
                if self.config.on_token_refreshed:
                    with contextlib.suppress(Exception):
                        self.config.on_token_refreshed(new_tokens)

            except Exception:
                # Refresh failed - return response without new tokens
                pass

        return cast("Response", response)


__all__: list[str] = [
    "TokenRefreshConfig",
    "TokenRefreshAdapter",
    "TokenRefreshMiddleware",
]
