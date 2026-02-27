"""API key authentication provider.

Provides authentication for service-to-service communication using API keys.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..exceptions import ExpiredApiKeyError, InvalidApiKeyError
from ..ports import IApiKeyRepository, IIdentityProvider, TokenResponse
from ..principal import Principal
from ..token import get_api_key_prefix, hash_api_key


class ApiKeyIdentityProvider(IIdentityProvider):
    """API key-based identity provider.

    Authenticates services using API keys (X-API-Key header).
    Keys are stored as SHA-256 hashes, with lookup by prefix.

    Example:
        ```python
        # Application provides the repository implementation
        api_key_repo = SQLAlchemyApiKeyRepository(session)

        provider = ApiKeyIdentityProvider(
            api_key_repository=api_key_repo,
        )

        # In middleware
        api_key = extract_api_key(request.headers)
        principal = await provider.resolve(api_key)
        ```
    """

    def __init__(
        self,
        *,
        api_key_repository: IApiKeyRepository,
    ) -> None:
        """Initialize the API key identity provider.

        Args:
            api_key_repository: Repository for API key storage.
        """
        self.api_key_repository = api_key_repository

    async def resolve(self, token: str) -> Principal:
        """Resolve API key to Principal.

        Args:
            token: The API key string.

        Returns:
            Principal for the API key owner.

        Raises:
            InvalidApiKeyError: API key is invalid or not found.
            ExpiredApiKeyError: API key has expired.
        """
        if not token:
            raise InvalidApiKeyError("API key is required")

        # Get prefix for lookup (first 8 chars)
        prefix = get_api_key_prefix(token)

        # Look up by prefix
        key_record = await self.api_key_repository.get_by_prefix(prefix)
        if key_record is None:
            raise InvalidApiKeyError("Invalid API key")

        # Verify full key hash
        key_hash = hash_api_key(token)
        if key_hash != key_record.key_hash:
            raise InvalidApiKeyError("Invalid API key")

        # Check if active
        if not key_record.is_active:
            raise InvalidApiKeyError("API key is disabled")

        # Check expiration
        if key_record.expires_at and datetime.now(timezone.utc) > key_record.expires_at:
            raise ExpiredApiKeyError("API key has expired")

        # Record usage
        await self.api_key_repository.record_usage(key_record.key_id)

        # Create principal
        return Principal(
            user_id=key_record.user_id,
            username=f"apikey:{key_record.name}",
            roles=key_record.roles,
            permissions=key_record.permissions,
            claims={
                "api_key_id": key_record.key_id,
                "api_key_name": key_record.name,
            },
            auth_method="apikey",
            expires_at=key_record.expires_at,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh is not supported for API keys.

        Raises:
            NotImplementedError: API keys don't expire or refresh.
        """
        raise NotImplementedError("API keys do not support refresh")

    async def logout(self, token: str) -> None:
        """Logout is not applicable for API keys."""


__all__: list[str] = ["ApiKeyIdentityProvider"]
