from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from cqrs_ddd_multitenancy.context import (
    get_current_tenant_or_none,
    reset_tenant,
    set_tenant,
)
from cqrs_ddd_multitenancy.contrib.fastapi.middleware import (
    TenantContextMiddleware,
    TenantMiddleware,
    get_current_tenant_dep,
    get_tenant_or_none_dep,
    require_tenant_dep,
)
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError


class MockResolver:
    def __init__(self, tenant_id=None):
        self.tenant_id = tenant_id

    async def resolve(self, request):
        return self.tenant_id


def build_mock_request(path="/", headers=None):
    scope = {"type": "http", "path": path, "headers": headers or [], "method": "GET"}
    return Request(scope)


@pytest.mark.asyncio
async def test_tenant_middleware_dispatch_success():
    middleware = TenantMiddleware(
        app=MagicMock(),
        resolver=MockResolver("t1"),
    )
    request = build_mock_request()

    async def call_next(req):
        assert get_current_tenant_or_none() == "t1"
        return PlainTextResponse("ok")

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert get_current_tenant_or_none() is None  # context cleared


@pytest.mark.asyncio
async def test_tenant_middleware_public_path():
    middleware = TenantMiddleware(
        app=MagicMock(),
        resolver=MockResolver(None),  # No tenant
        public_paths=["/public"],
    )
    request = build_mock_request(path="/public")

    async def call_next(req):
        assert get_current_tenant_or_none() is None
        return PlainTextResponse("ok")

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_tenant_middleware_missing_tenant_returns_400_or_raises():
    middleware = TenantMiddleware(
        app=MagicMock(),
        resolver=MockResolver(None),
    )
    request = build_mock_request(path="/private")

    async def call_next(req):
        return PlainTextResponse("ok")

    response = await middleware.dispatch(request, call_next)
    # The middleware returns JSONResponse with 400 when missing tenant
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_tenant_context_middleware():
    async def extract_tenant(req):
        return "t2"

    middleware = TenantContextMiddleware(app=MagicMock(), extract_tenant=extract_tenant)
    request = build_mock_request()

    async def call_next(req):
        assert get_current_tenant_or_none() == "t2"
        return PlainTextResponse("ok")

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fastapi_dependencies():
    token = set_tenant("t3")
    try:
        assert await get_current_tenant_dep() == "t3"
        assert await require_tenant_dep() == "t3"
        assert await get_tenant_or_none_dep() == "t3"
    finally:
        reset_tenant(token)

    assert await get_tenant_or_none_dep() is None
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await get_current_tenant_dep()
