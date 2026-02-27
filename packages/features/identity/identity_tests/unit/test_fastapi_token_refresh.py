"""Tests for FastAPI token refresh (optional; requires identity[fastapi])."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.contrib.fastapi.token_refresh import (
    TokenRefreshAdapter,
    TokenRefreshConfig,
)
from cqrs_ddd_identity.ports import TokenResponse


class TestTokenRefreshConfig:
    def test_defaults(self) -> None:
        c = TokenRefreshConfig()
        assert c.refresh_threshold_seconds == 300
        assert c.max_refresh_attempts == 3
        assert c.sliding_session is True
        assert c.store_refreshed_tokens is True
        assert c.on_token_refreshed is None


class TestTokenRefreshAdapter:
    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        p = MagicMock()
        p.resolve = AsyncMock(
            return_value=Principal(
                user_id="u1",
                username="u",
                roles=frozenset(),
                permissions=frozenset(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        p.refresh = AsyncMock(
            return_value=TokenResponse(access_token="new_at", refresh_token="new_rt")
        )
        p.logout = AsyncMock()
        return p

    def test_provider_and_config_properties(self, mock_provider: MagicMock) -> None:
        config = TokenRefreshConfig(refresh_threshold_seconds=600)
        adapter = TokenRefreshAdapter(mock_provider, config=config)
        assert adapter.provider is mock_provider
        assert adapter.config.refresh_threshold_seconds == 600

    @pytest.mark.asyncio
    async def test_resolve_delegates_to_provider(
        self, mock_provider: MagicMock
    ) -> None:
        adapter = TokenRefreshAdapter(mock_provider)
        principal = await adapter.resolve("token")
        mock_provider.resolve.assert_awaited_once_with("token")
        assert principal.user_id == "u1"
