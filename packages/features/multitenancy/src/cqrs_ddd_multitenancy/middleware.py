"""CQRS middleware for tenant context management.

This middleware integrates with the CQRS pipeline to extract and set
tenant context before command/query handlers execute.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.middleware import IMiddleware

from .context import reset_tenant, set_tenant
from .exceptions import TenantContextMissingError
from .resolver import ITenantResolver

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = [
    "TenantMiddleware",
]

logger = logging.getLogger(__name__)


class TenantMiddleware(IMiddleware):
    """CQRS middleware for tenant context extraction and injection.

    This middleware runs early in the CQRS pipeline to:
    1. Extract tenant ID from the incoming message using configured resolver
    2. Set the tenant context for downstream handlers
    3. Ensure proper cleanup after handler execution

    The middleware is configured with an ITenantResolver strategy that
    determines how the tenant is extracted from the message.

    Attributes:
        resolver: The tenant resolver strategy.
        allow_anonymous: Whether to allow requests without tenant context.
        inject_into_message: Whether to inject tenant_id into message.

    Example:
        ```python
        from cqrs_ddd_multitenancy import TenantMiddleware, HeaderResolver

        # Configure with header resolver
        middleware = TenantMiddleware(
            resolver=HeaderResolver("X-Tenant-ID"),
            allow_anonymous=False,
        )

        # Register with mediator
        mediator.add_middleware(middleware)
        ```
    """

    __slots__ = ("_resolver", "_allow_anonymous", "_inject_into_message")

    def __init__(
        self,
        resolver: ITenantResolver,
        *,
        allow_anonymous: bool = False,
        inject_into_message: bool = False,
    ) -> None:
        """Initialize the tenant middleware.

        Args:
            resolver: The tenant resolver strategy to use.
            allow_anonymous: If True, allow requests without tenant context.
                            If False, raise TenantContextMissingError when
                            tenant cannot be resolved.
            inject_into_message: If True, inject tenant_id into the message
                                object (requires message to have tenant_id
                                field and support model_copy/update).
        """
        self._resolver = resolver
        self._allow_anonymous = allow_anonymous
        self._inject_into_message = inject_into_message

    @property
    def resolver(self) -> ITenantResolver:
        """The configured tenant resolver."""
        return self._resolver

    @property
    def allow_anonymous(self) -> bool:
        """Whether anonymous (no tenant) requests are allowed."""
        return self._allow_anonymous

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Process the message through the tenant middleware.

        Args:
            message: The incoming command, query, or event.
            next_handler: The next handler in the middleware chain.

        Returns:
            The result from the next handler.

        Raises:
            TenantContextMissingError: If tenant cannot be resolved and
                                       allow_anonymous is False.
        """
        # Resolve tenant from message
        tenant_id = await self._resolve_tenant(message)

        # Validate tenant context
        if tenant_id is None and not self._allow_anonymous:
            raise TenantContextMissingError(
                "Tenant could not be resolved from message. "
                f"Resolver: {type(self._resolver).__name__}"
            )

        # Set tenant context if resolved
        token = None
        if tenant_id is not None:
            token = set_tenant(tenant_id)
            logger.debug(
                "Tenant context set",
                extra={"tenant_id": tenant_id, "message_type": type(message).__name__},
            )

        try:
            # Optionally inject tenant_id into message
            processed_message = self._inject_tenant(message, tenant_id)

            # Execute next handler
            return await next_handler(processed_message)
        finally:
            # Reset tenant context
            if token is not None:
                reset_tenant(token)
                logger.debug("Tenant context reset")

    async def _resolve_tenant(self, message: Any) -> str | None:
        """Resolve tenant ID from the message.

        Args:
            message: The incoming message.

        Returns:
            The resolved tenant ID, or None.
        """
        try:
            return await self._resolver.resolve(message)
        except Exception as e:
            logger.warning(
                "Tenant resolution failed",
                extra={
                    "resolver": type(self._resolver).__name__,
                    "error": str(e),
                },
            )
            return None

    def _inject_tenant(self, message: Any, tenant_id: str | None) -> Any:
        """Inject tenant_id into the message if configured.

        Args:
            message: The original message.
            tenant_id: The resolved tenant ID.

        Returns:
            The message with tenant_id injected, or the original message.
        """
        if not self._inject_into_message or tenant_id is None:
            return message

        # Try Pydantic model_copy (for Pydantic v2)
        if hasattr(message, "model_copy"):
            try:
                return message.model_copy(update={"tenant_id": tenant_id})
            except Exception:
                pass

        # Try dict-style update
        if hasattr(message, "__dict__"):
            try:
                # Create a copy with tenant_id set
                message_dict = dict(message.__dict__)
                message_dict["tenant_id"] = tenant_id
                return type(message)(**message_dict)
            except Exception:
                pass

        # Cannot inject, return original
        logger.debug(
            "Could not inject tenant_id into message",
            extra={"message_type": type(message).__name__},
        )
        return message


class TenantContextInjectionMiddleware(TenantMiddleware):
    """Convenience middleware that injects tenant_id into messages.

    This is a pre-configured TenantMiddleware with inject_into_message=True.
    Use when you want the tenant_id available directly on command/query objects.

    Example:
        ```python
        middleware = TenantContextInjectionMiddleware(
            resolver=CompositeResolver([
                HeaderResolver("X-Tenant-ID"),
                JwtClaimResolver(),
            ])
        )
        ```
    """

    def __init__(
        self,
        resolver: ITenantResolver,
        *,
        allow_anonymous: bool = False,
    ) -> None:
        """Initialize with inject_into_message=True.

        Args:
            resolver: The tenant resolver strategy to use.
            allow_anonymous: If True, allow requests without tenant context.
        """
        super().__init__(
            resolver=resolver,
            allow_anonymous=allow_anonymous,
            inject_into_message=True,
        )
