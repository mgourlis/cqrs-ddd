"""OAuth2 state parameter management.

The state parameter prevents CSRF attacks during OAuth2 flows.
It must be generated randomly, stored securely, and validated on callback.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..ports import ISessionStore


@dataclass(frozen=True)
class OAuthStateData:
    """OAuth2 state parameter data.

    Stored between authorization redirect and callback to verify
    the request originated from this client.

    Attributes:
        state: Random state string (anti-CSRF token).
        nonce: Optional nonce for OpenID Connect.
        pkce_verifier: PKCE code_verifier for token exchange.
        redirect_uri: Where to redirect after authentication.
        created_at: When the state was created.
        provider: OAuth2 provider name (e.g., "keycloak", "google").
        extra: Additional custom data.
    """

    state: str
    pkce_verifier: str | None = None
    redirect_uri: str | None = None
    nonce: str | None = None
    created_at: datetime | None = None
    provider: str | None = None
    extra: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Set created_at if not provided."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for session storage.

        Returns:
            Dictionary representation.
        """
        result: dict[str, Any] = {
            "state": self.state,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if self.pkce_verifier:
            result["pkce_verifier"] = self.pkce_verifier
        if self.redirect_uri:
            result["redirect_uri"] = self.redirect_uri
        if self.nonce:
            result["nonce"] = self.nonce
        if self.provider:
            result["provider"] = self.provider
        if self.extra:
            result["extra"] = self.extra
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthStateData:
        """Create from dictionary (e.g., from session storage).

        Args:
            data: Dictionary representation.

        Returns:
            OAuthStateData instance.

        Raises:
            ValueError: If 'state' key is missing from data.
        """
        # Defensive check for required field
        state = data.get("state")
        if state is None:
            raise ValueError("Missing required 'state' in OAuth state data")

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
            # Treat naive datetime as UTC
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

        return cls(
            state=state,
            pkce_verifier=data.get("pkce_verifier"),
            redirect_uri=data.get("redirect_uri"),
            nonce=data.get("nonce"),
            created_at=created_at,
            provider=data.get("provider"),
            extra=data.get("extra"),
        )


def generate_oauth_state(length: int = 32) -> str:
    """Generate a cryptographically random state parameter.

    Args:
        length: Length of state string (default 32).

    Returns:
        URL-safe random state string.

    Example:
        ```python
        state = generate_oauth_state()
        # Returns: "xJ7kL9mN2pQ4rS6tU8vW0xY1zA3bC5dE"
        ```
    """
    return secrets.token_urlsafe(length)


class OAuthStateManager:
    """Manages OAuth2 state parameter lifecycle.

    Handles generation, storage, retrieval, and validation of OAuth2
    state parameters using a session store.

    Example:
        ```python
        session_store = InMemorySessionStore()
        state_manager = OAuthStateManager(session_store)

        # Before redirect
        state_data = state_manager.create_state(
            provider="keycloak",
            pkce_verifier="abc123...",
            redirect_uri="/auth/callback",
        )
        auth_url = f"{auth_endpoint}?state={state_data.state}&..."

        # On callback
        stored_data = await state_manager.validate_state(callback_state)
        if stored_data:
            # Use stored_data.pkce_verifier for token exchange
            pass
        ```
    """

    def __init__(
        self,
        session_store: ISessionStore,
        *,
        state_ttl: int = 600,  # 10 minutes
    ) -> None:
        """Initialize the state manager.

        Args:
            session_store: Session store for state persistence.
            state_ttl: State time-to-live in seconds (default 600).
        """
        self.session_store = session_store
        self.state_ttl = state_ttl

    def create_state(
        self,
        *,
        provider: str | None = None,
        pkce_verifier: str | None = None,
        redirect_uri: str | None = None,
        nonce: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> OAuthStateData:
        """Create a new OAuth2 state.

        Args:
            provider: OAuth2 provider name.
            pkce_verifier: PKCE code_verifier.
            redirect_uri: Post-authentication redirect URI.
            nonce: OpenID Connect nonce.
            extra: Additional custom data.

        Returns:
            OAuthStateData instance.
        """
        state = generate_oauth_state()
        return OAuthStateData(
            state=state,
            pkce_verifier=pkce_verifier,
            redirect_uri=redirect_uri,
            nonce=nonce,
            provider=provider,
            extra=extra,
        )

    async def store_state(self, state_data: OAuthStateData) -> None:
        """Store state data for later validation.

        Args:
            state_data: State data to store.
        """
        await self.session_store.store(
            key=f"oauth_state:{state_data.state}",
            data=state_data.to_dict(),
            ttl=self.state_ttl,
        )

    async def get_state(self, state: str) -> OAuthStateData | None:
        """Retrieve stored state data.

        Args:
            state: State string to look up.

        Returns:
            OAuthStateData or None if not found/expired.
        """
        data = await self.session_store.get(f"oauth_state:{state}")
        if data is None:
            return None
        return OAuthStateData.from_dict(data)

    async def validate_state(self, state: str) -> OAuthStateData | None:
        """Validate and consume state.

        Retrieves the state and deletes it to prevent replay attacks.

        Args:
            state: State string from callback.

        Returns:
            OAuthStateData if valid, None if invalid/expired.
        """
        state_data = await self.get_state(state)
        if state_data is None:
            return None

        # Delete state to prevent replay
        await self.delete_state(state)

        return state_data

    async def delete_state(self, state: str) -> None:
        """Delete stored state.

        Args:
            state: State string to delete.
        """
        await self.session_store.delete(f"oauth_state:{state}")


__all__: list[str] = [
    "OAuthStateData",
    "generate_oauth_state",
    "OAuthStateManager",
]
