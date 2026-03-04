"""FastAPI integration for multitenancy.

Provides middleware and dependencies for FastAPI applications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from cqrs_ddd_multitenancy.context import (
    clear_tenant,
    get_current_tenant,
    get_current_tenant_or_none,
    set_tenant,
)
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.resolver import ITenantResolver

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request

__all__ = [
    "TenantMiddleware",
    "get_current_tenant_dep",
    "require_tenant_dep",
    "TenantContextMiddleware",
]

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware for tenant context management.

    This middleware extracts the tenant ID from incoming requests using
    a configurable resolver strategy and sets the tenant context for
    downstream request handlers.

    Order of Operations:
    1. Check if path is public → skip tenant resolution
    2. Resolve tenant ID using configured resolver
    3. Set tenant context
    4. Call next handler
    5. Clear tenant context in finally block

    Attributes:
        resolver: The tenant resolver strategy.
        public_paths: Paths that don't require tenant context.
        allow_anonymous: Whether to allow requests without tenant.

    Example:
        ```python
        from fastapi import FastAPI
        from cqrs_ddd_multitenancy.contrib.fastapi import TenantMiddleware
        from cqrs_ddd_multitenancy import HeaderResolver

        app = FastAPI()

        app.add_middleware(
            TenantMiddleware,
            resolver=HeaderResolver("X-Tenant-ID"),
            public_paths=["/health", "/docs", "/auth/login"],
            allow_anonymous=False,
        )
        ```
    """

    __slots__ = ("_resolver", "_public_paths", "_allow_anonymous")

    def __init__(
        self,
        app: Any,
        *,
        resolver: ITenantResolver,
        public_paths: list[str] | None = None,
        allow_anonymous: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The FastAPI/Starlette application.
            resolver: The tenant resolver strategy.
            public_paths: Paths that don't require tenant context.
            allow_anonymous: If True, allow requests without tenant context.
        """
        super().__init__(app)
        self._resolver = resolver
        self._public_paths = set(public_paths or [])
        self._allow_anonymous = allow_anonymous

    @property
    def resolver(self) -> ITenantResolver:
        """The configured tenant resolver."""
        return self._resolver

    def _is_public(self, path: str) -> bool:
        """Check if path is public (no tenant required).

        Args:
            path: The request path.

        Returns:
            True if path is in public_paths.
        """
        # Exact match
        if path in self._public_paths:
            return True

        # Prefix match for paths ending with *
        for public_path in self._public_paths:
            if public_path.endswith("*"):
                prefix = public_path[:-1]
                if path.startswith(prefix):
                    return True

        return False

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response from handler or error response.
        """
        from contextvars import Token

        from cqrs_ddd_multitenancy.context import reset_tenant

        # 1. Skip public paths
        if self._is_public(request.url.path):
            return await call_next(request)

        token: Token[str | None] | None = None

        try:
            # 2. Resolve tenant
            tenant_id = await self._resolve_tenant(request)

            # 3. Validate tenant context
            if tenant_id is None and not self._allow_anonymous:
                logger.warning(
                    "Tenant resolution failed",
                    extra={
                        "path": request.url.path,
                        "resolver": type(self._resolver).__name__,
                    },
                )
                return JSONResponse(
                    {"detail": "Tenant context required"},
                    status_code=400,
                )

            # 4. Set tenant context and save token for reset
            if tenant_id is not None:
                token = set_tenant(tenant_id)
                logger.debug(
                    "Tenant context set",
                    extra={"tenant_id": tenant_id, "path": request.url.path},
                )

            # 5. Process request
            return await call_next(request)

        except TenantContextMissingError as e:
            logger.warning(
                "Tenant context missing",
                extra={"path": request.url.path, "error": str(e)},
            )
            return JSONResponse(
                {"detail": str(e)},
                status_code=400,
            )

        except Exception:
            logger.exception(
                "Tenant middleware error",
                extra={"path": request.url.path},
            )
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
            )

        finally:
            # 6. Always reset tenant context using token
            if token is not None:
                reset_tenant(token)

    async def _resolve_tenant(self, request: Request) -> str | None:
        """Resolve tenant ID from the request.

        Args:
            request: The incoming request.

        Returns:
            The resolved tenant ID, or None.
        """
        try:
            return await self._resolver.resolve(request)
        except Exception as e:
            logger.warning(
                "Tenant resolution error",
                extra={
                    "resolver": type(self._resolver).__name__,
                    "error": str(e),
                },
            )
            return None


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Simplified tenant middleware that uses a function to extract tenant.

    This is a simpler alternative to TenantMiddleware for cases where
    you just need a function to extract tenant from the request.

    Example:
        ```python
        async def extract_tenant(request: Request) -> str | None:
            return request.headers.get("X-Tenant-ID")

        app.add_middleware(
            TenantContextMiddleware,
            extract_tenant=extract_tenant,
        )
        ```
    """

    __slots__ = ("_extract_tenant", "_public_paths", "_allow_anonymous")

    def __init__(
        self,
        app: Any,
        *,
        extract_tenant: Callable[[Request], Awaitable[str | None] | str | None],
        public_paths: list[str] | None = None,
        allow_anonymous: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The FastAPI/Starlette application.
            extract_tenant: Function to extract tenant from request.
            public_paths: Paths that don't require tenant context.
            allow_anonymous: If True, allow requests without tenant context.
        """
        super().__init__(app)
        self._extract_tenant = extract_tenant
        self._public_paths = set(public_paths or [])
        self._allow_anonymous = allow_anonymous

    def _is_public(self, path: str) -> bool:
        """Check if path is public."""
        if path in self._public_paths:
            return True
        for public_path in self._public_paths:
            if public_path.endswith("*") and path.startswith(public_path[:-1]):
                return True
        return False

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request."""
        if self._is_public(request.url.path):
            return await call_next(request)

        try:
            # Extract tenant
            result = self._extract_tenant(request)
            if hasattr(result, "__await__"):
                from typing import cast

                tenant_id: str | None = await cast("Awaitable[str | None]", result)
            else:
                tenant_id = result

            if tenant_id is None and not self._allow_anonymous:
                return JSONResponse(
                    {"detail": "Tenant context required"},
                    status_code=400,
                )

            if tenant_id is not None:
                set_tenant(tenant_id)

            return await call_next(request)

        finally:
            clear_tenant()


# -----------------------------------------------------------------------
# FastAPI Dependencies
# -----------------------------------------------------------------------


async def get_current_tenant_dep() -> str:
    """FastAPI dependency to get the current tenant ID.

    Use this with Depends() to inject the tenant ID into handlers.

    Returns:
        The current tenant ID.

    Raises:
        HTTPException: 400 if no tenant context is set.

    Example:
        ```python
        from fastapi import Depends
        from cqrs_ddd_multitenancy.contrib.fastapi import get_current_tenant_dep

        @app.get("/orders")
        async def list_orders(tenant_id: str = Depends(get_current_tenant_dep)):
            # tenant_id is guaranteed to be set
            return await order_repo.list_for_tenant(tenant_id)
        ```
    """
    try:
        return get_current_tenant()
    except TenantContextMissingError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="Tenant context required",
        ) from None


async def require_tenant_dep() -> str:
    """FastAPI dependency that requires a tenant context.

    This is an alias for get_current_tenant_dep for semantic clarity.

    Returns:
        The current tenant ID.

    Raises:
        HTTPException: 400 if no tenant context is set.
    """
    return await get_current_tenant_dep()


async def get_tenant_or_none_dep() -> str | None:
    """FastAPI dependency to get the current tenant ID or None.

    Use this when tenant context is optional.

    Returns:
        The current tenant ID, or None.

    Example:
        ```python
        from fastapi import Depends
        from cqrs_ddd_multitenancy.contrib.fastapi import get_tenant_or_none_dep

        @app.get("/public-data")
        async def get_public_data(tenant_id: str | None = Depends(get_tenant_or_none_dep)):
            # tenant_id may be None
            return await data_service.get_public_data(tenant_id)
        ```
    """
    return get_current_tenant_or_none()
