"""Integration tests for FastAPI middleware with real ASGI request/response cycle.

These tests exercise TenantMiddleware and its dependencies using httpx
and a real FastAPI application, verifying the full HTTP request lifecycle
including tenant context injection, isolation, and cleanup.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from cqrs_ddd_multitenancy.context import get_current_tenant_or_none
from cqrs_ddd_multitenancy.contrib.fastapi.middleware import (
    TenantContextMiddleware,
    TenantMiddleware,
    get_current_tenant_dep,
    get_tenant_or_none_dep,
    require_tenant_dep,
)
from cqrs_ddd_multitenancy.resolver import HeaderResolver, StaticResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_app(
    *,
    resolver: Any = None,
    public_paths: list[str] | None = None,
    allow_anonymous: bool = False,
) -> FastAPI:
    """Build a minimal FastAPI app with TenantMiddleware wired up."""
    if resolver is None:
        resolver = HeaderResolver("X-Tenant-ID")

    app = FastAPI()
    app.add_middleware(
        TenantMiddleware,
        resolver=resolver,
        public_paths=public_paths or [],
        allow_anonymous=allow_anonymous,
    )

    @app.get("/tenant")
    async def get_tenant_endpoint(tenant_id: str = Depends(get_current_tenant_dep)):
        return {"tenant_id": tenant_id}

    @app.get("/tenant-optional")
    async def get_tenant_optional_endpoint(
        tenant_id: str | None = Depends(get_tenant_or_none_dep),
    ):
        return {"tenant_id": tenant_id}

    @app.get("/require-tenant")
    async def require_tenant_endpoint(tenant_id: str = Depends(require_tenant_dep)):
        return {"tenant_id": tenant_id}

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    @app.get("/health/detailed")
    async def health_detailed_endpoint():
        return {"status": "ok", "detailed": True}

    @app.get("/context-check")
    async def context_check_endpoint():
        """Return the current tenant context visible inside a handler."""
        return {"tenant_id": get_current_tenant_or_none()}

    return app


async def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> Any:
    """Send a GET request to the app and return the httpx response."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.get(path, headers=headers or {})


# ---------------------------------------------------------------------------
# Header resolver — happy path
# ---------------------------------------------------------------------------


async def test_header_resolver_sets_tenant_in_handler():
    """Middleware extracts header and the FastAPI dependency sees the tenant."""
    app = build_app()
    response = await _get(app, "/tenant", headers={"X-Tenant-ID": "acme"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "acme"}


async def test_header_resolver_sets_tenant_visible_as_context():
    """Tenant injected by middleware is accessible via context inside handler."""
    app = build_app()
    response = await _get(app, "/context-check", headers={"X-Tenant-ID": "acme-corp"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "acme-corp"}


async def test_tenant_id_with_underscores_and_hyphens_accepted():
    """Valid tenant IDs with hyphens and underscores should be accepted."""
    app = build_app()
    for tenant_id in ("org-123", "tenant_A", "alpha-beta-gamma"):
        response = await _get(app, "/tenant", headers={"X-Tenant-ID": tenant_id})
        assert response.status_code == 200, f"Expected 200 for tenant_id={tenant_id!r}"
        assert response.json()["tenant_id"] == tenant_id


# ---------------------------------------------------------------------------
# Missing tenant — 400 errors
# ---------------------------------------------------------------------------


async def test_missing_header_returns_400():
    """Request without X-Tenant-ID header should receive 400."""
    app = build_app()
    response = await _get(app, "/tenant")
    assert response.status_code == 400
    assert "detail" in response.json()


async def test_missing_header_on_context_check_returns_400():
    """Even non-dependency endpoints return 400 when tenant is missing."""
    app = build_app()
    response = await _get(app, "/context-check")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Anonymous mode
# ---------------------------------------------------------------------------


async def test_allow_anonymous_passes_request_without_tenant():
    """With allow_anonymous=True, missing header should not block the request."""
    app = build_app(allow_anonymous=True)
    response = await _get(app, "/tenant-optional")
    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}


async def test_allow_anonymous_context_is_none_in_handler():
    """Tenant context is None (not set) when request is anonymous."""
    app = build_app(allow_anonymous=True)
    response = await _get(app, "/context-check")
    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}


async def test_allow_anonymous_with_header_sets_tenant():
    """Even with allow_anonymous=True, if header present, tenant IS set."""
    app = build_app(allow_anonymous=True)
    response = await _get(app, "/context-check", headers={"X-Tenant-ID": "with-header"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "with-header"}


# ---------------------------------------------------------------------------
# Public paths
# ---------------------------------------------------------------------------


async def test_public_path_exact_bypasses_tenant_check():
    """Exact public path should bypass middleware; no tenant required."""
    app = build_app(public_paths=["/health"])
    response = await _get(app, "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_public_path_wildcard_bypasses_tenant_check():
    """Wildcard public path prefix (/health*) matches sub-paths."""
    app = build_app(public_paths=["/health*"])
    response = await _get(app, "/health/detailed")
    assert response.status_code == 200


async def test_non_public_path_still_requires_tenant():
    """Only the declared public paths are exempt; others still need tenant."""
    app = build_app(public_paths=["/health"])
    # /health is exempt, but /tenant is not
    response = await _get(app, "/tenant")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Context isolation
# ---------------------------------------------------------------------------


async def test_context_cleared_after_request():
    """Tenant context must not leak from one request into the next."""
    app = build_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # First request sets tenant
        r1 = await client.get("/context-check", headers={"X-Tenant-ID": "first-tenant"})
        assert r1.json()["tenant_id"] == "first-tenant"

        # Second request with no header should fail (not inherit previous tenant)
        r2 = await client.get("/context-check")
        assert r2.status_code == 400

        # Third request with different tenant should see only its own tenant
        r3 = await client.get(
            "/context-check", headers={"X-Tenant-ID": "second-tenant"}
        )
        assert r3.json()["tenant_id"] == "second-tenant"


# ---------------------------------------------------------------------------
# Static resolver
# ---------------------------------------------------------------------------


async def test_static_resolver_always_sets_fixed_tenant():
    """StaticResolver provides hardcoded tenant regardless of request headers."""
    app = build_app(resolver=StaticResolver("global-tenant"))
    response = await _get(app, "/tenant")
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "global-tenant"}


# ---------------------------------------------------------------------------
# FastAPI Depends — get_current_tenant_dep / require_tenant_dep
# ---------------------------------------------------------------------------


async def test_require_tenant_dep_raises_http_400_when_no_tenant():
    """require_tenant_dep() causes a 400 if called without middleware setting tenant."""
    # App with allow_anonymous=True so middleware lets it through,
    # but the depend itself will raise because get_current_tenant() is called.
    app = build_app(allow_anonymous=True)
    response = await _get(
        app, "/require-tenant"
    )  # no header → anonymous → 400 from dep
    assert response.status_code == 400


async def test_require_tenant_dep_succeeds_when_tenant_set():
    """require_tenant_dep() succeeds when tenant is set by middleware."""
    app = build_app()
    response = await _get(app, "/require-tenant", headers={"X-Tenant-ID": "dep-tenant"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "dep-tenant"}


# ---------------------------------------------------------------------------
# TenantContextMiddleware (simpler alternative)
# ---------------------------------------------------------------------------


async def test_tenant_context_middleware_sets_and_clears_tenant():
    """TenantContextMiddleware extracts via callable and clears after response."""
    app = FastAPI()

    async def extract_from_header(request: Any) -> str | None:
        return request.headers.get("X-Custom-Tenant")

    app.add_middleware(
        TenantContextMiddleware,
        extract_tenant=extract_from_header,
        allow_anonymous=False,
    )

    @app.get("/ctx")
    async def ctx_endpoint():
        return {"tenant_id": get_current_tenant_or_none()}

    response = await _get(app, "/ctx", headers={"X-Custom-Tenant": "ctx-tenant"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "ctx-tenant"}


async def test_tenant_context_middleware_missing_returns_400():
    """TenantContextMiddleware returns 400 when tenant is required but absent."""
    app = FastAPI()

    async def extract_from_header(request: Any) -> str | None:
        return request.headers.get("X-Custom-Tenant")

    app.add_middleware(
        TenantContextMiddleware,
        extract_tenant=extract_from_header,
        allow_anonymous=False,
    )

    @app.get("/ctx")
    async def ctx_endpoint():
        return {"status": "ok"}

    response = await _get(app, "/ctx")
    assert response.status_code == 400


async def test_tenant_context_middleware_public_path_bypassed():
    """TenantContextMiddleware respects public_paths."""
    app = FastAPI()

    async def extract_from_header(request: Any) -> str | None:
        return request.headers.get("X-Custom-Tenant")

    app.add_middleware(
        TenantContextMiddleware,
        extract_tenant=extract_from_header,
        allow_anonymous=False,
        public_paths=["/public"],
    )

    @app.get("/public")
    async def public_endpoint():
        return {"public": True}

    response = await _get(app, "/public")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# get_tenant_or_none_dep
# ---------------------------------------------------------------------------


async def test_get_tenant_or_none_dep_returns_tenant_when_set():
    """Optional dependency returns the tenant ID when middleware sets it."""
    app = build_app()
    response = await _get(
        app, "/tenant-optional", headers={"X-Tenant-ID": "optional-t"}
    )
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "optional-t"}
