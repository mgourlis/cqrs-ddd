"""Message broker context propagation utilities.

This module provides utilities for propagating tenant context through message
brokers (RabbitMQ, Kafka, etc.) to ensure tenant isolation in asynchronous
messaging scenarios.
"""

from __future__ import annotations

import logging
from typing import Any

from ..context import Token, get_current_tenant_or_none, reset_tenant, set_tenant

__all__ = [
    "TenantMessagePropagator",
    "inject_tenant_to_message",
    "extract_tenant_from_message",
    "with_tenant_from_message",
]

logger = logging.getLogger(__name__)


# Standard message header for tenant ID
TENANT_HEADER = "x-tenant-id"


def inject_tenant_to_message(
    message: dict[str, Any],
    headers: dict[str, Any] | None = None,
    tenant_header: str = TENANT_HEADER,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inject tenant context into message headers.

    Args:
        message: The message body.
        headers: Existing message headers (optional).
        tenant_header: Header key for tenant ID.

    Returns:
        Tuple of (message, headers) with tenant injected.
    """
    tenant_id = get_current_tenant_or_none()

    if headers is None:
        headers = {}

    if tenant_id is not None:
        headers[tenant_header] = tenant_id
        logger.debug(f"Injected tenant context into message: tenant_id={tenant_id}")
    else:
        logger.warning(
            "No tenant context available to inject into message. "
            "Message will be sent without tenant context."
        )

    return message, headers


def extract_tenant_from_message(
    headers: dict[str, Any],
    tenant_header: str = TENANT_HEADER,
) -> str | None:
    """Extract tenant ID from message headers.

    Args:
        headers: Message headers.
        tenant_header: Header key for tenant ID.

    Returns:
        Tenant ID if found, None otherwise.
    """
    tenant_id = headers.get(tenant_header)

    if tenant_id is None:
        logger.warning(
            f"No tenant context found in message headers (header: {tenant_header})"
        )
    else:
        logger.debug(f"Extracted tenant context from message: tenant_id={tenant_id}")

    return tenant_id


class TenantMessagePropagator:
    """Utility class for tenant context propagation in message brokers.

    This class provides methods for injecting and extracting tenant context
    from message headers, making it easy to integrate with various message
    broker clients (RabbitMQ, Kafka, SQS, etc.).

    Usage:
        ```python
        # Producer side
        propagator = TenantMessagePropagator()
        message, headers = propagator.inject_tenant(
            message={"order_id": "123"},
            headers={"content-type": "application/json"}
        )
        await broker.publish(message, headers)

        # Consumer side
        async def message_handler(message: dict, headers: dict):
            propagator = TenantMessagePropagator()
            async with propagator.with_tenant_context(headers):
                # Process message in tenant context
                ...
        ```
    """

    def __init__(self, tenant_header: str = TENANT_HEADER) -> None:
        """Initialize the message propagator.

        Args:
            tenant_header: Header key for tenant ID.
        """
        self.tenant_header = tenant_header

    def inject_tenant(
        self,
        message: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Inject tenant context into message.

        Args:
            message: The message body.
            headers: Existing headers (optional).

        Returns:
            Tuple of (message, headers) with tenant injected.
        """
        return inject_tenant_to_message(
            message, headers, tenant_header=self.tenant_header
        )

    def extract_tenant(self, headers: dict[str, Any]) -> str | None:
        """Extract tenant ID from message headers.

        Args:
            headers: Message headers.

        Returns:
            Tenant ID if found, None otherwise.
        """
        return extract_tenant_from_message(headers, tenant_header=self.tenant_header)

    def with_tenant_context(
        self, headers: dict[str, Any]
    ) -> _TenantMessageContextManager:
        """Context manager for processing messages with tenant context.

        Args:
            headers: Message headers containing tenant ID.

        Returns:
            Context manager that sets/resets tenant context.

        Example:
            ```python
            async with propagator.with_tenant_context(headers):
                # Tenant context is set
                tenant_id = get_current_tenant()
                # Process message
                ...
            # Context is automatically reset
            ```
        """
        return _TenantMessageContextManager(headers, tenant_header=self.tenant_header)


class _TenantMessageContextManager:
    """Internal context manager for tenant context from messages."""

    def __init__(self, headers: dict[str, Any], tenant_header: str) -> None:
        """Initialize context manager.

        Args:
            headers: Message headers.
            tenant_header: Header key for tenant ID.
        """
        self.headers = headers
        self.tenant_header = tenant_header
        self.token: Token[str | None] | None = None

    async def __aenter__(self) -> str | None:
        """Enter tenant context.

        Returns:
            Tenant ID if found, None otherwise.
        """
        tenant_id = extract_tenant_from_message(
            self.headers, tenant_header=self.tenant_header
        )

        if tenant_id is not None:
            self.token = set_tenant(tenant_id)

        return tenant_id

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        """Exit tenant context."""
        if self.token is not None:
            reset_tenant(self.token)
            self.token = None


def with_tenant_from_message(tenant_header: str = TENANT_HEADER) -> Any:
    """Decorator for message handlers that automatically sets tenant context.

    Args:
        tenant_header: Header key for tenant ID.

    Returns:
        Decorator function.

    Example:
        ```python
        @with_tenant_from_message()
        async def handle_order(message: dict, headers: dict):
            # Tenant context is automatically set
            tenant_id = get_current_tenant()
            # Process message
            ...
        ```
    """

    def decorator(func: Any) -> Any:
        async def wrapper(
            message: dict[str, Any], headers: dict[str, Any], *args: Any, **kwargs: Any
        ) -> Any:
            propagator = TenantMessagePropagator(tenant_header=tenant_header)
            async with propagator.with_tenant_context(headers):
                return await func(message, headers, *args, **kwargs)

        return wrapper

    return decorator
