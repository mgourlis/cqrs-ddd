"""Tests for ApiKeyIdentityProvider."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cqrs_ddd_identity.api_key.provider import ApiKeyIdentityProvider
from cqrs_ddd_identity.exceptions import ExpiredApiKeyError, InvalidApiKeyError
from cqrs_ddd_identity.ports import ApiKeyRecord
from cqrs_ddd_identity.token import hash_api_key


class MockApiKeyRepository:
    """Mock IApiKeyRepository for testing."""

    def __init__(
        self,
        record: ApiKeyRecord | None = None,
    ) -> None:
        self.record = record
        self.record_usage_calls: list[str] = []

    async def get_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        return self.record

    async def record_usage(self, key_id: str) -> None:
        self.record_usage_calls.append(key_id)


class TestApiKeyIdentityProviderResolve:
    @pytest.mark.asyncio
    async def test_resolve_valid_key_returns_principal(self) -> None:
        full_key = "sk_abcdefghijklmnopqrstuvwxyz123456"
        prefix = full_key[:8]
        key_hash = hash_api_key(full_key)
        record = ApiKeyRecord(
            key_id="key-1",
            key_prefix=prefix,
            key_hash=key_hash,
            name="Test Key",
            user_id="u1",
            roles=frozenset(["admin"]),
            permissions=frozenset(["read", "write"]),
        )
        repo = MockApiKeyRepository(record=record)
        provider = ApiKeyIdentityProvider(api_key_repository=repo)

        principal = await provider.resolve(full_key)

        assert principal.user_id == "u1"
        assert principal.username == "apikey:Test Key"
        assert principal.roles == frozenset(["admin"])
        assert principal.auth_method == "apikey"
        assert principal.claims["api_key_id"] == "key-1"
        assert repo.record_usage_calls == ["key-1"]

    @pytest.mark.asyncio
    async def test_resolve_empty_token_raises(self) -> None:
        repo = MockApiKeyRepository()
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(InvalidApiKeyError, match="API key is required"):
            await provider.resolve("")

    @pytest.mark.asyncio
    async def test_resolve_prefix_not_found_raises(self) -> None:
        repo = MockApiKeyRepository(record=None)
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(InvalidApiKeyError, match="Invalid API key"):
            await provider.resolve("sk_unknownkey12345678901234567890")

    @pytest.mark.asyncio
    async def test_resolve_wrong_hash_raises(self) -> None:
        full_key = "sk_abcdefghijklmnopqrstuvwxyz123456"
        prefix = full_key[:8]
        record = ApiKeyRecord(
            key_id="key-1",
            key_prefix=prefix,
            key_hash="wrong_hash",
            name="Key",
            user_id="u1",
        )
        repo = MockApiKeyRepository(record=record)
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(InvalidApiKeyError, match="Invalid API key"):
            await provider.resolve(full_key)

    @pytest.mark.asyncio
    async def test_resolve_inactive_raises(self) -> None:
        full_key = "sk_abcdefghijklmnopqrstuvwxyz123456"
        key_hash = hash_api_key(full_key)
        record = ApiKeyRecord(
            key_id="key-1",
            key_prefix=full_key[:8],
            key_hash=key_hash,
            name="Key",
            user_id="u1",
            is_active=False,
        )
        repo = MockApiKeyRepository(record=record)
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(InvalidApiKeyError, match="disabled"):
            await provider.resolve(full_key)

    @pytest.mark.asyncio
    async def test_resolve_expired_raises(self) -> None:
        full_key = "sk_abcdefghijklmnopqrstuvwxyz123456"
        key_hash = hash_api_key(full_key)
        record = ApiKeyRecord(
            key_id="key-1",
            key_prefix=full_key[:8],
            key_hash=key_hash,
            name="Key",
            user_id="u1",
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        repo = MockApiKeyRepository(record=record)
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(ExpiredApiKeyError, match="expired"):
            await provider.resolve(full_key)


class TestApiKeyIdentityProviderRefresh:
    @pytest.mark.asyncio
    async def test_refresh_raises_not_implemented(self) -> None:
        repo = MockApiKeyRepository()
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        with pytest.raises(NotImplementedError, match="do not support refresh"):
            await provider.refresh("refresh-token")


class TestApiKeyIdentityProviderLogout:
    @pytest.mark.asyncio
    async def test_logout_no_op(self) -> None:
        repo = MockApiKeyRepository()
        provider = ApiKeyIdentityProvider(api_key_repository=repo)
        await provider.logout("any-token")
