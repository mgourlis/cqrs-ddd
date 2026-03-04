"""Schema routing for PostgreSQL schema-per-tenant isolation.

Provides functionality to route queries to tenant-specific PostgreSQL schemas
using SET search_path and SQLAlchemy's schema_translate_map.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from .context import get_current_tenant_or_none, is_system_tenant
from .exceptions import TenantIsolationError, TenantProvisioningError
from .isolation import IsolationConfig, TenantIsolationStrategy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "SchemaRouter",
    "with_tenant_schema",
    "set_search_path",
    "reset_search_path",
]

logger = logging.getLogger(__name__)


class SchemaRouter:
    """Routes database queries to tenant-specific PostgreSQL schemas.

    This router manages schema switching for the schema-per-tenant isolation
    strategy. It uses PostgreSQL's SET search_path command to route queries.

    Attributes:
        config: The isolation configuration.
        default_search_path: The default search_path to restore.

    Example:
        ```python
        from cqrs_ddd_multitenancy import SchemaRouter, IsolationConfig

        router = SchemaRouter(IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="tenant_",
            default_schema="public",
        ))

        async with router.with_schema(session, "tenant-123"):
            # All queries in this block use tenant_tenant-123 schema
            await session.execute(select(Order))
        ```
    """

    __slots__ = ("_config", "_default_search_path")

    def __init__(
        self,
        config: IsolationConfig,
        *,
        default_search_path: str | None = None,
    ) -> None:
        """Initialize the schema router.

        Args:
            config: The isolation configuration.
            default_search_path: Custom default search_path (default: config.default_schema).
        """
        if config.strategy != TenantIsolationStrategy.SCHEMA_PER_TENANT:
            raise ValueError(
                f"SchemaRouter requires SCHEMA_PER_TENANT strategy, got {config.strategy}"
            )

        self._config = config
        self._default_search_path = default_search_path or config.default_schema

    @property
    def config(self) -> IsolationConfig:
        """The isolation configuration."""
        return self._config

    @property
    def default_search_path(self) -> str:
        """The default search_path to restore."""
        return self._default_search_path

    def get_schema_name(self, tenant_id: str) -> str:
        """Get the schema name for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The schema name for the tenant.
        """
        return self._config.get_schema_name(tenant_id)

    def get_search_path(self, tenant_id: str) -> str:
        """Get the search_path for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The search_path string (tenant_schema, default_schema).
        """
        return self._config.get_search_path(tenant_id)

    async def set_search_path(
        self,
        session_or_connection: Any,
        tenant_id: str,
    ) -> str:
        """Set the search_path for the current transaction.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            tenant_id: The tenant identifier.

        Returns:
            The previous search_path (for restoration).
        """
        from sqlalchemy import text

        from .observability import TenantMetrics, TenantTracing

        search_path = self.get_search_path(tenant_id)

        # Validate search_path to prevent SQL injection
        # Only allow alphanumeric, underscore, and comma (for multiple schemas)
        if not all(c.isalnum() or c in "_, " for c in search_path):
            raise TenantIsolationError(
                f"Invalid schema name format: {search_path}. "
                "Schema names must contain only alphanumeric characters, underscores, and commas."
            )

        # Get the underlying connection
        connection = self._get_connection(session_or_connection)

        with TenantMetrics.operation("switch_schema"):
            with TenantTracing.schema_switch_span(
                tenant_id, schema=search_path
            ) as span:
                # Get current search_path
                result = await connection.execute(text("SHOW search_path"))
                previous_path = result.scalar()

                # Set new search_path using proper quoting
                # Use identifier quoting to prevent SQL injection
                await connection.execute(
                    text("SET search_path TO :search_path"),
                    {"search_path": search_path},
                )

                if span:
                    TenantTracing.set_schema(span, search_path)

                logger.debug(
                    "Set PostgreSQL search_path",
                    extra={
                        "tenant_id": tenant_id,
                        "search_path": search_path,
                        "previous_path": previous_path,
                    },
                )

                return str(previous_path or self._default_search_path)

    async def reset_search_path(
        self,
        session_or_connection: Any,
        previous_path: str | None = None,
    ) -> None:
        """Reset the search_path to default.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            previous_path: The previous search_path to restore (optional).
        """
        from sqlalchemy import text

        connection = self._get_connection(session_or_connection)
        path = previous_path or self._default_search_path

        # Validate path to prevent SQL injection
        if not all(c.isalnum() or c in "_, " for c in path):
            raise TenantIsolationError(
                f"Invalid schema name format: {path}. "
                "Schema names must contain only alphanumeric characters, underscores, and commas."
            )

        await connection.execute(
            text("SET search_path TO :search_path"), {"search_path": path}
        )

        logger.debug(
            "Reset PostgreSQL search_path",
            extra={"search_path": path},
        )

    @asynccontextmanager
    async def with_schema(
        self,
        session_or_connection: Any,
        tenant_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Context manager for tenant schema switching.

        Sets the search_path for the tenant at entry and restores
        the default at exit.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            tenant_id: The tenant identifier (uses current context if None).

        Yields:
            The schema name that was set.

        Raises:
            TenantIsolationError: If tenant cannot be determined.
        """
        # Resolve tenant ID
        effective_tenant = tenant_id or get_current_tenant_or_none()

        if effective_tenant is None:
            if is_system_tenant():
                # System tenant uses default schema
                yield self._default_search_path
                return
            raise TenantIsolationError(
                "Cannot set schema: no tenant in context",
                strategy="SCHEMA_PER_TENANT",
            )

        schema_name = self.get_schema_name(effective_tenant)

        try:
            previous_path = await self.set_search_path(
                session_or_connection, effective_tenant
            )
            yield schema_name
        finally:
            await self.reset_search_path(session_or_connection, previous_path)

    def get_schema_translate_map(
        self,
        tenant_id: str | None = None,
    ) -> dict[str, str]:
        """Get a schema_translate_map for SQLAlchemy execution options.

        This is an alternative to SET search_path that works at the
        connection level. Useful for connection pooling scenarios.

        Args:
            tenant_id: The tenant identifier (uses current context if None).

        Returns:
            A schema_translate_map dictionary.
        """
        effective_tenant = tenant_id or get_current_tenant_or_none()

        if effective_tenant is None:
            return {}

        schema_name = self.get_schema_name(effective_tenant)
        return {"tenant": schema_name}

    async def create_tenant_schema(
        self,
        session_or_connection: Any,
        tenant_id: str,
    ) -> None:
        """Create a schema for a new tenant.

        This is an admin operation typically called during tenant provisioning.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            tenant_id: The tenant identifier.

        Raises:
            TenantProvisioningError: If schema creation fails.
        """
        schema_name = self.get_schema_name(tenant_id)
        connection = self._get_connection(session_or_connection)

        try:
            # Check if schema exists
            result = await connection.execute(
                text(
                    "SELECT 1 FROM information_schema.schemata"
                    " WHERE schema_name = :name"
                ),
                {"name": schema_name},
            )
            if result.scalar() is not None:
                logger.info(
                    "Schema already exists",
                    extra={"schema_name": schema_name, "tenant_id": tenant_id},
                )
                return

            # Create schema
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await connection.commit()

            logger.info(
                "Created tenant schema",
                extra={"schema_name": schema_name, "tenant_id": tenant_id},
            )

        except Exception as e:
            await connection.rollback()
            raise TenantProvisioningError(
                tenant_id,
                f"Failed to create schema '{schema_name}': {e}",
                strategy="SCHEMA_PER_TENANT",
            ) from e

    async def drop_tenant_schema(
        self,
        session_or_connection: Any,
        tenant_id: str,
        *,
        cascade: bool = False,
    ) -> None:
        """Drop a tenant's schema.

        This is a destructive admin operation. Use with extreme caution.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            tenant_id: The tenant identifier.
            cascade: Whether to cascade the drop (drops all objects).

        Raises:
            TenantProvisioningError: If schema drop fails.
        """
        schema_name = self.get_schema_name(tenant_id)
        connection = self._get_connection(session_or_connection)

        try:
            cascade_clause = " CASCADE" if cascade else ""
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name}"{cascade_clause}')
            )
            await connection.commit()

            logger.warning(
                "Dropped tenant schema",
                extra={
                    "schema_name": schema_name,
                    "tenant_id": tenant_id,
                    "cascade": cascade,
                },
            )

        except Exception as e:
            await connection.rollback()
            raise TenantProvisioningError(
                tenant_id,
                f"Failed to drop schema '{schema_name}': {e}",
                strategy="SCHEMA_PER_TENANT",
            ) from e

    async def schema_exists(
        self,
        session_or_connection: Any,
        tenant_id: str,
    ) -> bool:
        """Check if a tenant schema exists.

        Args:
            session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
            tenant_id: The tenant identifier.

        Returns:
            True if the schema exists, False otherwise.
        """
        schema_name = self.get_schema_name(tenant_id)
        connection = self._get_connection(session_or_connection)

        result = await connection.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
            {"name": schema_name},
        )
        return result.scalar() is not None

    def _get_connection(self, session_or_connection: Any) -> AsyncConnection:
        """Extract the underlying connection from session or connection.

        Args:
            session_or_connection: AsyncSession or AsyncConnection.

        Returns:
            The AsyncConnection.
        """
        # Both session and connection types satisfy AsyncConnection interface at runtime
        return session_or_connection  # type: ignore[no-any-return]


# Convenience functions for direct use


async def set_search_path(
    session_or_connection: Any,
    tenant_id: str,
    config: IsolationConfig | None = None,
) -> str:
    """Set the search_path for a tenant.

    Args:
        session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
        tenant_id: The tenant identifier.
        config: Optional isolation config (uses defaults if None).

    Returns:
        The previous search_path.
    """
    router = SchemaRouter(config or IsolationConfig())
    return await router.set_search_path(session_or_connection, tenant_id)


async def reset_search_path(
    session_or_connection: Any,
    previous_path: str | None = None,
    config: IsolationConfig | None = None,
) -> None:
    """Reset the search_path to default.

    Args:
        session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
        previous_path: The previous search_path to restore.
        config: Optional isolation config (uses defaults if None).
    """
    router = SchemaRouter(config or IsolationConfig())
    return await router.reset_search_path(session_or_connection, previous_path)


@asynccontextmanager
async def with_tenant_schema(
    session_or_connection: Any,
    tenant_id: str | None = None,
    config: IsolationConfig | None = None,
) -> AsyncIterator[str]:
    """Context manager for tenant schema switching.

    Args:
        session_or_connection: SQLAlchemy AsyncSession or AsyncConnection.
        tenant_id: The tenant identifier (uses current context if None).
        config: Optional isolation config (uses defaults if None).

    Yields:
        The schema name that was set.
    """
    router = SchemaRouter(config or IsolationConfig())
    async with router.with_schema(session_or_connection, tenant_id) as schema_name:
        yield schema_name
