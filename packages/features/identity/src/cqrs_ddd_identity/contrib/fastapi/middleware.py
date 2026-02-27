"""FastAPI authentication middleware.

Provides HTTP middleware for extracting tokens and setting principal context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from starlette.responses import JSONResponse, Response

from ...context import (
    clear_principal,
    clear_tokens,
    set_access_token,
    set_principal,
)
from ...exceptions import MfaRequiredError
from ...token import TokenExtractor

if TYPE_CHECKING:
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware

    from ...ports import IIdentityProvider
else:
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: F401


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for authentication.

    Order of Operations:
    1. Exclusion — If path in public_paths, call_next immediately.
    2. Extraction — Try Bearer header → Cookie → API Key.
    3. Resolution — Call IIdentityProvider.resolve(token).
    4. Context — set_principal() for downstream use.
    5. Cleanup — Use `finally` block to clear_principal() to prevent leakage.

    Example:
        ```python
        from fastapi import FastAPI
        from cqrs_ddd_identity.contrib.fastapi import AuthenticationMiddleware
        from cqrs_ddd_identity import IIdentityProvider

        app = FastAPI()

        @app.on_event("startup")
        async def setup():
            identity_provider = KeycloakIdentityProvider(...)
            app.add_middleware(
                AuthenticationMiddleware,
                identity_provider=identity_provider,
                public_paths=["/health", "/docs", "/auth/login"],
            )
        ```
    """

    def __init__(
        self,
        app: Any,
        *,
        identity_provider: IIdentityProvider,
        public_paths: list[str] | None = None,
        token_extractor: TokenExtractor | None = None,
        api_key_provider: IIdentityProvider | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: FastAPI/Starlette application.
            identity_provider: Primary identity provider for tokens.
            public_paths: Paths that don't require authentication.
            token_extractor: Custom token extractor (optional).
            api_key_provider: Separate provider for API keys (optional).
        """
        super().__init__(app)
        self.identity_provider = identity_provider
        self.public_paths = set(public_paths or [])
        self.token_extractor = token_extractor or TokenExtractor()
        self.api_key_provider = api_key_provider

    def _is_public(self, path: str) -> bool:
        """Check if path is public (no auth required).

        Args:
            path: Request path.

        Returns:
            True if path is in public_paths.
        """
        # Exact match
        if path in self.public_paths:
            return True

        # Prefix match for paths ending with *
        for public_path in self.public_paths:
            if public_path.endswith("*"):
                prefix = public_path[:-1]
                if path.startswith(prefix):
                    return True

        return False

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process the request.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response from handler or error response.
        """
        # 1. Skip public paths
        if self._is_public(request.url.path):
            return cast("Response", await call_next(request))

        try:
            # 2. Extract token (Bearer header → Cookie → API Key)
            headers = dict(request.headers)
            cookies = dict(request.cookies)
            query_params = dict(request.query_params)

            token, source = self.token_extractor.extract(
                headers=headers,
                cookies=cookies,
                query_params=query_params,
            )

            if not token:
                # No token found - proceed without principal
                # Handlers can use require_authenticated() to enforce auth
                return cast("Response", await call_next(request))

            # 3. Resolve principal
            # Use API key provider if source is API_KEY
            provider = self.identity_provider
            if source and source.value == "api_key" and self.api_key_provider:
                provider = self.api_key_provider

            # Store access token in context before resolving
            set_access_token(token)

            principal = await provider.resolve(token)

            # 4. Set context for downstream use
            set_principal(principal)

            # 5. Continue pipeline
            return cast("Response", await call_next(request))

        except MfaRequiredError as e:
            # Return 403 with pending_token for MFA completion
            return JSONResponse(
                status_code=403,
                content={
                    "error": "mfa_required",
                    "message": str(e),
                    "pending_token": e.pending_token,
                    "available_methods": e.available_methods,
                },
            )

        except Exception:
            # Let other exceptions propagate (will be handled by exception handlers)
            raise

        finally:
            # ALWAYS cleanup to prevent context leakage between requests
            clear_principal()
            clear_tokens()
