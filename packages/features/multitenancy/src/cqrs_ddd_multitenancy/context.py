"""Tenant context management using ContextVar.

Provides tenant isolation via context-local storage that propagates
correctly through async call chains. Uses the Token pattern for
safe context reset in nested scenarios.
"""

from __future__ import annotations

import functools
from contextvars import ContextVar, Token, copy_context
from typing import TYPE_CHECKING, Any, Final, TypeVar

from .exceptions import TenantContextMissingError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = [
    "SYSTEM_TENANT",
    "Token",
    "get_current_tenant",
    "get_current_tenant_or_none",
    "set_tenant",
    "reset_tenant",
    "clear_tenant",
    "require_tenant",
    "is_system_tenant",
    "is_tenant_context_set",
    "system_operation",
    "with_tenant_context",
    "get_tenant_context_vars",
]

T = TypeVar("T")

# Sentinel value for system/admin operations that bypass tenant isolation
SYSTEM_TENANT: Final[str] = "__system__"

# Module-level ContextVar for tenant storage
# Default is None to indicate no tenant context is set
_tenant_context: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def get_current_tenant() -> str:
    """Get the current tenant ID from context.

    Returns:
        The current tenant ID.

    Raises:
        TenantContextMissingError: If no tenant is set in the current context.

    Note:
        Use get_current_tenant_or_none() for optional tenant scenarios.
    """
    tenant = _tenant_context.get()
    if tenant is None:
        raise TenantContextMissingError(
            "No tenant context set. "
            "Ensure TenantMiddleware is configured or set_tenant() was called."
        )
    return tenant


def get_current_tenant_or_none() -> str | None:
    """Get the current tenant ID from context, or None if not set.

    Returns:
        The current tenant ID, or None if no tenant context is set.
    """
    return _tenant_context.get()


def set_tenant(tenant_id: str) -> Token[str | None]:
    """Set the tenant ID in the current context.

    Args:
        tenant_id: The tenant ID to set. Use SYSTEM_TENANT for system operations.

    Returns:
        A Token that can be used to reset the context to its previous state.

    Raises:
        ValueError: If tenant_id is empty or contains invalid characters.

    Example:
        ```python
        token = set_tenant("tenant-123")
        try:
            # ... tenant-scoped operations ...
        finally:
            reset_tenant(token)
        ```
    """
    if not tenant_id:
        raise ValueError("tenant_id cannot be empty")

    # Validate tenant ID format (allow SYSTEM_TENANT to bypass)
    if tenant_id != SYSTEM_TENANT:
        # Allow alphanumeric, hyphens, underscores
        if not all(c.isalnum() or c in "-_" for c in tenant_id):
            raise ValueError(
                f"Invalid tenant_id format: {tenant_id!r}. "
                "Tenant IDs must contain only alphanumeric characters, hyphens, and underscores."
            )
        # Reasonable length limits
        if len(tenant_id) > 128:
            raise ValueError(f"tenant_id too long (max 128 characters): {tenant_id!r}")

    return _tenant_context.set(tenant_id)


def reset_tenant(token: Token[str | None]) -> None:
    """Reset the tenant context to its previous state using a Token.

    Args:
        token: The Token returned by a previous set_tenant() call.

    This is the preferred way to restore context in finally blocks.
    """
    _tenant_context.reset(token)


def clear_tenant() -> None:
    """Clear the tenant context, setting it to None.

    Use this with caution - typically you want reset_tenant() with a token
    to properly restore previous context in nested scenarios.
    """
    _tenant_context.set(None)


def require_tenant() -> str:
    """Decorator/context manager that requires a tenant context to be set.

    This is an alias for get_current_tenant() for use as a validation helper.

    Raises:
        TenantContextMissingError: If no tenant is set.
    """
    return get_current_tenant()


def is_system_tenant() -> bool:
    """Check if the current context is running as system tenant.

    Returns:
        True if the current tenant is SYSTEM_TENANT, False otherwise.
    """
    return _tenant_context.get() == SYSTEM_TENANT


def is_tenant_context_set() -> bool:
    """Check if any tenant context is set (including system tenant).

    Returns:
        True if a tenant context is set, False if None.
    """
    return _tenant_context.get() is not None


def system_operation(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator that runs a function with SYSTEM_TENANT context.

    This allows the decorated function to bypass tenant isolation.
    Use with extreme caution and ensure proper authorization checks.

    Args:
        func: An async function to wrap.

    Returns:
        The wrapped function that runs with SYSTEM_TENANT context.

    Warning:
        This decorator should only be used on admin/system functions
        that have been properly gated by role/permission checks.

    Example:
        ```python
        @system_operation
        async def list_all_tenants() -> list[Tenant]:
            # This can query across all tenants
            return await tenant_repo.list_all()
        ```
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        token = set_tenant(SYSTEM_TENANT)
        try:
            return await func(*args, **kwargs)
        finally:
            reset_tenant(token)

    return wrapper


def with_tenant_context(tenant_id: str) -> _TenantContextManager:
    """Context manager for setting tenant context in a block.

    Args:
        tenant_id: The tenant ID to set for the context block.

    Returns:
        A context manager that sets/resets tenant context.

    Example:
        ```python
        async with with_tenant_context("tenant-123"):
            # All operations in this block use tenant-123
            await repo.add(entity)
        ```
    """
    return _TenantContextManager(tenant_id)


class _TenantContextManager:
    """Async context manager for tenant context."""

    __slots__ = ("_tenant_id", "_token")

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._token: Token[str | None] | None = None

    async def __aenter__(self) -> str:
        self._token = set_tenant(self._tenant_id)
        return self._tenant_id

    async def __aexit__(self, *args: Any) -> None:
        if self._token is not None:
            reset_tenant(self._token)


def get_tenant_context_vars() -> dict[str, str | None]:
    """Get tenant context variables for background task spawning.

    Use this to capture the current tenant context when spawning
    background tasks that need to preserve the tenant.

    Returns:
        A dictionary with tenant_id for context propagation.

    Example:
        ```python
        ctx = get_tenant_context_vars()
        # Pass ctx to background task
        await background_job.trigger(ctx=ctx)
        ```
    """
    return {
        "tenant_id": get_current_tenant_or_none(),
    }


def propagate_tenant_context(
    func: Callable[..., Awaitable[T]],
    tenant_id: str | None = None,
) -> Callable[..., Awaitable[T]]:
    """Wrap a function to propagate tenant context.

    Useful for background tasks that need to run in a specific tenant context.

    Args:
        func: The async function to wrap.
        tenant_id: Specific tenant to use. If None, captures current context.

    Returns:
        Wrapped function that runs with the specified tenant context.
    """
    captured_tenant = (
        tenant_id if tenant_id is not None else get_current_tenant_or_none()
    )

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        if captured_tenant is None:
            return await func(*args, **kwargs)

        token = set_tenant(captured_tenant)
        try:
            return await func(*args, **kwargs)
        finally:
            reset_tenant(token)

    return wrapper


def run_in_tenant_context(
    tenant_id: str,
    func: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run a synchronous function in a specific tenant context.

    Uses copy_context() for thread-safe context propagation.

    Args:
        tenant_id: The tenant ID to set.
        func: The synchronous function to run.
        *args: Arguments to pass to func.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        The result of func.
    """
    ctx = copy_context()

    def _run_with_tenant() -> T:
        set_tenant(tenant_id)
        return func(*args, **kwargs)

    return ctx.run(_run_with_tenant)
