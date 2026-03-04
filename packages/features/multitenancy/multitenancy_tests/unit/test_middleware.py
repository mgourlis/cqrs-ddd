from typing import Any

import pytest
from pydantic import BaseModel

from cqrs_ddd_multitenancy.context import get_current_tenant_or_none
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.middleware import (
    TenantContextInjectionMiddleware,
    TenantMiddleware,
)
from cqrs_ddd_multitenancy.resolver import ITenantResolver


class MockResolver(ITenantResolver):
    def __init__(self, tenant_id: str | None = None, should_fail: bool = False):
        self.tenant_id = tenant_id
        self.should_fail = should_fail

    async def resolve(self, request: Any) -> str | None:
        if self.should_fail:
            raise ValueError("Resolver error")
        return self.tenant_id


class DummyMessage(BaseModel):
    id: str
    tenant_id: str | None = None


@pytest.mark.asyncio
async def test_tenant_middleware_resolves_and_sets_context():
    resolver = MockResolver("tenant-1")
    middleware = TenantMiddleware(resolver)

    message = DummyMessage(id="1")

    async def next_handler(msg):
        assert get_current_tenant_or_none() == "tenant-1"
        return "success"

    result = await middleware(message, next_handler)
    assert result == "success"
    assert get_current_tenant_or_none() is None  # context reset


@pytest.mark.asyncio
async def test_tenant_middleware_anonymous_allowed():
    resolver = MockResolver(None)
    middleware = TenantMiddleware(resolver, allow_anonymous=True)

    async def next_handler(msg):
        assert get_current_tenant_or_none() is None
        return "success"

    await middleware(DummyMessage(id="1"), next_handler)


@pytest.mark.asyncio
async def test_tenant_middleware_anonymous_rejected():
    resolver = MockResolver(None)
    middleware = TenantMiddleware(resolver, allow_anonymous=False)

    with pytest.raises(TenantContextMissingError):
        await middleware(DummyMessage(id="1"), lambda m: m)


@pytest.mark.asyncio
async def test_tenant_middleware_resolver_error_treated_as_none():
    resolver = MockResolver(should_fail=True)
    middleware = TenantMiddleware(resolver, allow_anonymous=False)

    with pytest.raises(TenantContextMissingError):
        await middleware(DummyMessage(id="1"), lambda m: m)


@pytest.mark.asyncio
async def test_tenant_context_injection_middleware():
    resolver = MockResolver("tenant-2")
    middleware = TenantContextInjectionMiddleware(resolver)

    message = DummyMessage(id="2")

    async def next_handler(msg):
        assert msg.tenant_id == "tenant-2"
        return msg

    result = await middleware(message, next_handler)
    assert result.tenant_id == "tenant-2"
