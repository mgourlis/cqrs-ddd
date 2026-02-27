"""Tests for FastAPI AuthenticationMiddleware (optional; requires identity[fastapi])."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

starlette = pytest.importorskip("starlette")
fastapi = pytest.importorskip("fastapi")

from starlette.requests import Request
from starlette.responses import Response

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.contrib.fastapi.middleware import AuthenticationMiddleware


@pytest.fixture
def mock_app() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_provider() -> MagicMock:
    p = MagicMock()
    p.resolve = AsyncMock(
        return_value=Principal(
            user_id="u1", username="u", roles=frozenset(), permissions=frozenset()
        )
    )
    p.refresh = AsyncMock()
    p.logout = AsyncMock()
    return p


class TestAuthenticationMiddlewareInit:
    def test_creates_with_required_args(
        self, mock_app: MagicMock, mock_provider: MagicMock
    ) -> None:
        mw = AuthenticationMiddleware(mock_app, identity_provider=mock_provider)
        assert mw.identity_provider is mock_provider
        assert mw.public_paths == set()
        assert mw.api_key_provider is None

    def test_public_paths_set(
        self, mock_app: MagicMock, mock_provider: MagicMock
    ) -> None:
        mw = AuthenticationMiddleware(
            mock_app,
            identity_provider=mock_provider,
            public_paths=["/health", "/docs"],
        )
        assert mw.public_paths == {"/health", "/docs"}


class TestIsPublic:
    def test_exact_match(self, mock_app: MagicMock, mock_provider: MagicMock) -> None:
        mw = AuthenticationMiddleware(
            mock_app,
            identity_provider=mock_provider,
            public_paths=["/health", "/login"],
        )
        assert mw._is_public("/health") is True
        assert mw._is_public("/login") is True
        assert mw._is_public("/api/me") is False

    def test_prefix_match_with_star(
        self, mock_app: MagicMock, mock_provider: MagicMock
    ) -> None:
        mw = AuthenticationMiddleware(
            mock_app,
            identity_provider=mock_provider,
            public_paths=["/public*"],
        )
        assert mw._is_public("/public") is True
        assert mw._is_public("/public/foo") is True
        assert mw._is_public("/private") is False


class TestMiddlewareDispatch:
    @pytest.mark.asyncio
    async def test_public_path_calls_next_without_resolve(
        self, mock_app: MagicMock, mock_provider: MagicMock
    ) -> None:
        mw = AuthenticationMiddleware(
            mock_app,
            identity_provider=mock_provider,
            public_paths=["/health"],
        )
        request = Request(
            scope={
                "type": "http",
                "path": "/health",
                "method": "GET",
                "headers": [],
                "query_string": b"",
            }
        )
        call_next = AsyncMock(return_value=Response(content=b"ok"))

        response = await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()
        mock_provider.resolve.assert_not_called()
        assert response.body == b"ok"

    @pytest.mark.asyncio
    async def test_no_token_calls_next_without_resolve(
        self, mock_app: MagicMock, mock_provider: MagicMock
    ) -> None:
        mw = AuthenticationMiddleware(mock_app, identity_provider=mock_provider)
        request = Request(
            scope={
                "type": "http",
                "path": "/api",
                "method": "GET",
                "headers": [],
                "query_string": b"",
            }
        )
        call_next = AsyncMock(return_value=Response(content=b"ok"))

        await mw.dispatch(request, call_next)

        call_next.assert_awaited_once()
        mock_provider.resolve.assert_not_called()
