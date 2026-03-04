"""Tests for tenant resolvers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from cqrs_ddd_multitenancy.resolver import (
    CallableResolver,
    CompositeResolver,
    HeaderResolver,
    ITenantResolver,
    JwtClaimResolver,
    PathResolver,
    StaticResolver,
    SubdomainResolver,
)


@dataclass
class MockRequest:
    """Mock request for testing."""

    headers: dict[str, str]
    url: Any = None
    path: str = "/"
    host: str | None = None


@dataclass
class MockURL:
    """Mock URL for testing."""

    path: str
    hostname: str | None = None


class TestHeaderResolver:
    """Tests for HeaderResolver."""

    @pytest.mark.asyncio
    async def test_resolves_from_header(self) -> None:
        """Test resolving tenant from header."""
        resolver = HeaderResolver("X-Tenant-ID")
        request = MockRequest(headers={"X-Tenant-ID": "tenant-123"})

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_resolves_from_lowercase_header(self) -> None:
        """Test resolving tenant from lowercase header."""
        resolver = HeaderResolver("X-Tenant-ID")
        request = MockRequest(headers={"x-tenant-id": "tenant-123"})

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_header_missing(self) -> None:
        """Test returns None when header is missing."""
        resolver = HeaderResolver("X-Tenant-ID")
        request = MockRequest(headers={})

        result = await resolver.resolve(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_strips_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        resolver = HeaderResolver("X-Tenant-ID")
        request = MockRequest(headers={"X-Tenant-ID": "  tenant-123  "})

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_custom_header_name(self) -> None:
        """Test custom header name."""
        resolver = HeaderResolver("Tenant-Id")
        request = MockRequest(headers={"Tenant-Id": "tenant-123"})

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_resolves_from_dict(self) -> None:
        """Test resolving from dict message."""
        resolver = HeaderResolver("X-Tenant-ID")
        message = {"headers": {"X-Tenant-ID": "tenant-123"}}

        result = await resolver.resolve(message)
        assert result == "tenant-123"


class TestJwtClaimResolver:
    """Tests for JwtClaimResolver."""

    @pytest.mark.asyncio
    async def test_resolves_from_principal(self) -> None:
        """Test resolving from Principal object."""
        resolver = JwtClaimResolver()

        principal = MagicMock()
        principal.tenant_id = "tenant-123"

        result = await resolver.resolve(principal)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_resolves_from_claims_dict(self) -> None:
        """Test resolving from claims dictionary."""
        resolver = JwtClaimResolver()
        claims = {"sub": "user-1", "tenant_id": "tenant-123"}

        result = await resolver.resolve(claims)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_fallback_to_tenant_key(self) -> None:
        """Test fallback to 'tenant' key."""
        resolver = JwtClaimResolver()
        claims = {"sub": "user-1", "tenant": "tenant-123"}

        result = await resolver.resolve(claims)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_custom_claim_name(self) -> None:
        """Test custom claim name."""
        resolver = JwtClaimResolver(claim_name="custom_tenant")
        claims = {"custom_tenant": "tenant-123"}

        result = await resolver.resolve(claims)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_claims(self) -> None:
        """Test returns None when no claims."""
        resolver = JwtClaimResolver()

        result = await resolver.resolve({})
        assert result is None


class TestSubdomainResolver:
    """Tests for SubdomainResolver."""

    @pytest.mark.asyncio
    async def test_resolves_from_subdomain(self) -> None:
        """Test resolving from subdomain."""
        resolver = SubdomainResolver()

        url = MockURL(path="/", hostname="tenant-123.app.com")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_validates_domain_suffix(self) -> None:
        """Test domain suffix validation."""
        resolver = SubdomainResolver(domain_suffix=".app.com")

        url = MockURL(path="/", hostname="tenant-123.app.com")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_suffix(self) -> None:
        """Test returns None for wrong domain suffix."""
        resolver = SubdomainResolver(domain_suffix=".app.com")

        url = MockURL(path="/", hostname="tenant-123.other.com")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_common_subdomains(self) -> None:
        """Test that common subdomains are skipped."""
        resolver = SubdomainResolver()

        for subdomain in ["www", "api", "app", "admin"]:
            url = MockURL(path="/", hostname=f"{subdomain}.app.com")
            request = MockRequest(headers={}, url=url)

            result = await resolver.resolve(request)
            assert result is None, f"Should skip {subdomain}"

    @pytest.mark.asyncio
    async def test_resolves_from_host_header(self) -> None:
        """Test resolving from Host header."""
        resolver = SubdomainResolver()

        request = MockRequest(headers={"Host": "tenant-123.app.com:8080"})

        result = await resolver.resolve(request)
        assert result == "tenant-123"


class TestPathResolver:
    """Tests for PathResolver."""

    @pytest.mark.asyncio
    async def test_resolves_from_path(self) -> None:
        """Test resolving from path."""
        resolver = PathResolver()

        url = MockURL(path="/tenants/tenant-123/orders")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_custom_prefix(self) -> None:
        """Test custom prefix."""
        resolver = PathResolver(prefix="/t/")

        url = MockURL(path="/t/tenant-123/orders")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self) -> None:
        """Test returns None when no match."""
        resolver = PathResolver()

        url = MockURL(path="/orders/123")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_pattern(self) -> None:
        """Test custom pattern."""
        resolver = PathResolver(pattern=r"/org/([^/]+)")

        url = MockURL(path="/org/acme-inc/orders")
        request = MockRequest(headers={}, url=url)

        result = await resolver.resolve(request)
        assert result == "acme-inc"


class TestCompositeResolver:
    """Tests for CompositeResolver."""

    @pytest.mark.asyncio
    async def test_tries_resolvers_in_order(self) -> None:
        """Test that resolvers are tried in order."""
        resolver1 = StaticResolver("first")
        resolver2 = StaticResolver("second")

        composite = CompositeResolver([resolver1, resolver2])

        result = await composite.resolve({})
        assert result == "first"

    @pytest.mark.asyncio
    async def test_falls_back_to_next(self) -> None:
        """Test fallback to next resolver."""

        async def resolve_none(_: Any) -> str | None:
            return None

        resolver1 = CallableResolver(resolve_none)
        resolver2 = StaticResolver("fallback")

        composite = CompositeResolver([resolver1, resolver2])

        result = await composite.resolve({})
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_returns_none_if_all_fail(self) -> None:
        """Test returns None if all resolvers fail."""

        async def resolve_none(_: Any) -> str | None:
            return None

        composite = CompositeResolver(
            [
                CallableResolver(resolve_none),
                CallableResolver(resolve_none),
            ]
        )

        result = await composite.resolve({})
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_empty_resolvers(self) -> None:
        """Test raises on empty resolvers list."""
        with pytest.raises(ValueError, match="at least one resolver"):
            CompositeResolver([])

    @pytest.mark.asyncio
    async def test_add_resolver(self) -> None:
        """Test adding resolver."""
        resolver1 = StaticResolver("first")
        composite = CompositeResolver([resolver1])

        # First returns "first"
        result = await composite.resolve({})
        assert result == "first"

        # Add new resolver at end
        new_composite = composite.add_resolver(StaticResolver("second"))
        assert len(new_composite.resolvers) == 2


class TestStaticResolver:
    """Tests for StaticResolver."""

    @pytest.mark.asyncio
    async def test_returns_fixed_tenant(self) -> None:
        """Test returns fixed tenant ID."""
        resolver = StaticResolver("fixed-tenant")

        result = await resolver.resolve({})
        assert result == "fixed-tenant"

    @pytest.mark.asyncio
    async def test_ignores_message(self) -> None:
        """Test ignores message content."""
        resolver = StaticResolver("fixed-tenant")

        result = await resolver.resolve({"tenant_id": "other"})
        assert result == "fixed-tenant"

    def test_raises_on_empty_tenant_id(self) -> None:
        """Test raises on empty tenant ID."""
        with pytest.raises(ValueError, match="cannot be empty"):
            StaticResolver("")


class TestCallableResolver:
    """Tests for CallableResolver."""

    @pytest.mark.asyncio
    async def test_calls_sync_function(self) -> None:
        """Test calls sync function."""

        def get_tenant(message: Any) -> str | None:
            return message.get("tenant")

        resolver = CallableResolver(get_tenant)

        result = await resolver.resolve({"tenant": "tenant-123"})
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_calls_async_function(self) -> None:
        """Test calls async function."""

        async def get_tenant(message: Any) -> str | None:
            return message.get("tenant")

        resolver = CallableResolver(get_tenant)

        result = await resolver.resolve({"tenant": "tenant-123"})
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_returns_none_from_function(self) -> None:
        """Test returns None from function."""

        def get_tenant(_: Any) -> str | None:
            return None

        resolver = CallableResolver(get_tenant)

        result = await resolver.resolve({})
        assert result is None
