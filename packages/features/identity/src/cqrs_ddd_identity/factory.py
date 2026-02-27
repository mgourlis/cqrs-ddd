"""Factory functions for identity provider setup.

Provides convenient factory functions for common identity provider
configurations and a CompositeIdentityProvider for fallback chains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .exceptions import AuthenticationError, InvalidTokenError
from .ports import IIdentityProvider, TokenResponse

if TYPE_CHECKING:
    from .principal import Principal


class CompositeIdentityProvider(IIdentityProvider):
    """Identity provider that tries multiple providers in order.

    Useful for supporting multiple authentication methods simultaneously,
    such as JWT tokens + API keys, or multiple OAuth providers.

    The composite tries each provider in order until one succeeds.
    If all providers fail, the last error is raised.

    Example:
        ```python
        # Try JWT first, fall back to API key
        composite = CompositeIdentityProvider([
            keycloak_provider,
            api_key_provider,
        ])

        principal = await composite.resolve(token)
        ```
    """

    def __init__(
        self,
        providers: list[IIdentityProvider],
        *,
        stop_on_success: bool = True,
    ) -> None:
        """Initialize the composite provider.

        Args:
            providers: List of providers to try in order.
            stop_on_success: Whether to stop on first success (default True).
        """
        if not providers:
            raise ValueError("At least one provider is required")

        self._providers = providers
        self._stop_on_success = stop_on_success

    @property
    def providers(self) -> list[IIdentityProvider]:
        """Get the list of providers."""
        return self._providers

    async def resolve(self, token: str) -> Principal:
        """Resolve token by trying each provider in order.

        Args:
            token: The authentication token.

        Returns:
            Principal from the first successful provider.

        Raises:
            AuthenticationError: If all providers fail.
        """
        last_error: Exception | None = None

        for provider in self._providers:
            try:
                return await provider.resolve(token)
            except InvalidTokenError as e:
                # This provider didn't recognize the token, try next
                last_error = e
                continue
            except AuthenticationError:
                # Authentication failed but token was recognized
                # Re-raise immediately - don't try other providers
                raise

        # All providers failed with InvalidTokenError
        raise last_error or InvalidTokenError("No provider could resolve the token")

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh token using the first provider.

        Note: Token refresh is provider-specific, so we only use the first
        provider. If you need refresh for multiple providers, handle
        refresh separately per provider.

        Args:
            refresh_token: The refresh token.

        Returns:
            TokenResponse from the first provider.
        """
        return await self._providers[0].refresh(refresh_token)

    async def logout(self, token: str) -> None:
        """Logout from all providers.

        Tries to logout from each provider, continuing even if some fail.

        Args:
            token: The token to invalidate.
        """
        errors: list[Exception] = []

        for provider in self._providers:
            try:
                await provider.logout(token)
            except Exception as e:
                errors.append(e)

        # If all failed, raise the first error
        if len(errors) == len(self._providers) and errors:
            raise errors[0]


def create_composite_provider(
    *providers: IIdentityProvider,
) -> CompositeIdentityProvider:
    """Create a composite identity provider from multiple providers.

    Args:
        *providers: Identity providers to combine.

    Returns:
        CompositeIdentityProvider that tries each in order.

    Example:
        ```python
        provider = create_composite_provider(
            keycloak_provider,
            api_key_provider,
        )
        ```
    """
    return CompositeIdentityProvider(list(providers))


def create_hybrid_provider(
    primary: IIdentityProvider,
    fallback: IIdentityProvider,
) -> CompositeIdentityProvider:
    """Create a hybrid provider with primary and fallback.

    Convenience function for the common pattern of having a primary
    authentication method with a fallback.

    Args:
        primary: Primary identity provider (tried first).
        fallback: Fallback identity provider (tried if primary fails).

    Returns:
        CompositeIdentityProvider with primary and fallback.

    Example:
        ```python
        # JWT primary, API key fallback
        provider = create_hybrid_provider(
            primary=keycloak_provider,
            fallback=api_key_provider,
        )
        ```
    """
    return CompositeIdentityProvider([primary, fallback])


def create_api_only_provider(
    api_key_provider: IIdentityProvider,
) -> IIdentityProvider:
    """Create an API-only identity provider.

    For services that only accept API key authentication.

    Args:
        api_key_provider: API key identity provider.

    Returns:
        The API key provider unchanged.

    Example:
        ```python
        from cqrs_ddd_identity import ApiKeyIdentityProvider

        provider = create_api_only_provider(
            ApiKeyIdentityProvider(api_key_repository=repo)
        )
        ```
    """
    return api_key_provider


__all__: list[str] = [
    "CompositeIdentityProvider",
    "create_composite_provider",
    "create_hybrid_provider",
    "create_api_only_provider",
]
