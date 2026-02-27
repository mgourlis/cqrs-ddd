"""OAuth2 token client for authorization code flow.

Implements the OAuth2 Authorization Code Flow with PKCE support
for secure token exchange with identity providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from ..exceptions import OAuthError

if TYPE_CHECKING:
    from ..ports import TokenResponse
    from .pkce import PKCEData


@dataclass(frozen=True)
class OAuth2ProviderConfig:
    """Configuration for OAuth2 provider.

    Attributes:
        authorization_endpoint: URL for authorization redirect.
        token_endpoint: URL for token exchange.
        introspection_endpoint: URL for token introspection.
        userinfo_endpoint: URL for user info (optional).
        end_session_endpoint: URL for logout (optional).
        jwks_uri: URL for JWKS (optional, for local JWT validation).
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret (optional for public clients).
        redirect_uri: Default redirect URI.
        scope: Space-separated scopes.
        issuer: Token issuer for validation.
        audience: Expected audience for tokens.
    """

    authorization_endpoint: str
    token_endpoint: str
    client_id: str
    redirect_uri: str
    scope: str = "openid profile email"
    client_secret: str | None = None
    introspection_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    end_session_endpoint: str | None = None
    jwks_uri: str | None = None
    issuer: str | None = None
    audience: str | None = None


class OAuth2TokenClient(ABC):
    """Abstract OAuth2 token client for authorization code flow.

    Handles authorization URL generation; subclasses must implement
    exchange_code, refresh_token, and introspect with an HTTP client.
    Designed to work with any OAuth2/OIDC provider.

    Example:
        ```python
        config = OAuth2ProviderConfig(
            authorization_endpoint="https://auth.example.com/oauth2/auth",
            token_endpoint="https://auth.example.com/oauth2/token",
            client_id="my-client",
            client_secret="secret",
            redirect_uri="https://app.example.com/auth/callback",
        )
        client = OAuth2TokenClient(config)

        # Generate authorization URL
        auth_url = client.get_authorization_url(state="xyz", pkce=pkce)
        ```
    """

    def __init__(self, config: OAuth2ProviderConfig) -> None:
        """Initialize the OAuth2 client.

        Args:
            config: Provider configuration.
        """
        self.config = config

    def get_authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str | None = None,
        scope: str | None = None,
        pkce: PKCEData | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Generate OAuth2 authorization URL.

        Args:
            state: Anti-CSRF state parameter.
            redirect_uri: Override default redirect URI.
            scope: Override default scope.
            pkce: PKCE data (code_challenge will be included).
            extra_params: Additional query parameters.

        Returns:
            Authorization URL to redirect user to.

        Example:
            ```python
            pkce = create_pkce_data()
            url = client.get_authorization_url(
                state="random-state",
                pkce=pkce,
            )
            ```
        """
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri or self.config.redirect_uri,
            "scope": scope or self.config.scope,
            "state": state,
        }

        # Add PKCE challenge
        if pkce:
            params["code_challenge"] = pkce.code_challenge
            params["code_challenge_method"] = pkce.code_challenge_method

        # Add extra parameters
        if extra_params:
            params.update(extra_params)

        # Build URL with proper URL encoding
        query = urlencode(params, safe="")
        return f"{self.config.authorization_endpoint}?{query}"

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> TokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback.
            redirect_uri: Must match the one used in authorization URL.
            code_verifier: PKCE code_verifier (required if PKCE was used).

        Returns:
            TokenResponse with access_token, refresh_token, etc.

        Raises:
            OAuthCallbackError: If exchange fails.

        Note:
            This is an abstract method. Implementations should use httpx
            or similar to make the actual HTTP request to the token endpoint.
        """
        # Build request body
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.config.redirect_uri,
            "client_id": self.config.client_id,
        }

        # Add client secret if available
        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        # Add PKCE verifier
        if code_verifier:
            data["code_verifier"] = code_verifier

        # NOTE: Implementations must override this method to make HTTP request
        # This is a placeholder that raises NotImplementedError
        raise NotImplementedError(
            "Subclasses must implement exchange_code with HTTP client"
        )

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token.

        Args:
            refresh_token: The refresh token.

        Returns:
            TokenResponse with new access_token.

        Raises:
            OAuthError: If refresh fails.
        """
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        # NOTE: Implementations must override this method
        raise NotImplementedError(
            "Subclasses must implement refresh_token with HTTP client"
        )

    @abstractmethod
    async def introspect(self, token: str) -> dict[str, Any]:
        """Introspect token at the provider.

        Args:
            token: Access token to introspect.

        Returns:
            Introspection response with token claims.

        Raises:
            OAuthError: If introspection fails.

        Note:
            Requires introspection_endpoint to be configured.
        """
        if not self.config.introspection_endpoint:
            raise OAuthError("Introspection endpoint not configured")

        # NOTE: Implementations must override this method
        raise NotImplementedError(
            "Subclasses must implement introspect with HTTP client"
        )

    async def revoke(self, token: str) -> None:
        """Revoke a token.

        Args:
            token: Token to revoke.

        Note:
            Requires revocation_endpoint to be configured.
            This is a placeholder for subclasses to implement.
        """
        # NOTE: Implementations should override this method

    def get_logout_url(
        self,
        *,
        redirect_uri: str | None = None,
        id_token_hint: str | None = None,
    ) -> str | None:
        """Get logout URL for the provider.

        Args:
            redirect_uri: Where to redirect after logout.
            id_token_hint: ID token hint for OIDC logout.

        Returns:
            Logout URL or None if not configured.
        """
        if not self.config.end_session_endpoint:
            return None

        params: dict[str, str] = {}
        if redirect_uri:
            params["post_logout_redirect_uri"] = redirect_uri
        if id_token_hint:
            params["id_token_hint"] = id_token_hint

        if not params:
            return self.config.end_session_endpoint

        # Build URL with proper URL encoding
        query = urlencode(params, safe="")
        return f"{self.config.end_session_endpoint}?{query}"


__all__: list[str] = [
    "OAuth2ProviderConfig",
    "OAuth2TokenClient",
]
