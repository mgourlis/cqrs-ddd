"""Tenant isolation strategy definitions.

Defines the three main isolation strategies and their configuration:
- DISCRIMINATOR_COLUMN: Shared schema, tenant_id column filtering
- SCHEMA_PER_TENANT: PostgreSQL schema per tenant
- DATABASE_PER_TENANT: Separate database per tenant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "TenantIsolationStrategy",
    "IsolationConfig",
    "DEFAULT_TENANT_COLUMN",
    "DEFAULT_SCHEMA_PREFIX",
    "DEFAULT_DATABASE_PREFIX",
]

# Default naming conventions
DEFAULT_TENANT_COLUMN: Final[str] = "tenant_id"
DEFAULT_SCHEMA_PREFIX: Final[str] = "tenant_"
DEFAULT_DATABASE_PREFIX: Final[str] = "tenant_"


class TenantIsolationStrategy(str, Enum):
    """Tenant isolation strategy enumeration.

    Each strategy provides a different level of data isolation:

    - **DISCRIMINATOR_COLUMN**: All tenants share the same database schema.
      A `tenant_id` column on each table is used to filter queries.
      Simplest approach, suitable for low tenant counts or when physical
      isolation is not required.

    - **SCHEMA_PER_TENANT**: Each tenant gets their own PostgreSQL schema.
      Uses `SET search_path` to route queries. Provides logical isolation
      while sharing the same database server. PostgreSQL-specific.

    - **DATABASE_PER_TENANT**: Each tenant gets their own database.
      Maximum isolation, suitable for compliance requirements (GDPR, HIPAA).
      Requires connection routing per request.
    """

    DISCRIMINATOR_COLUMN = "discriminator_column"
    SCHEMA_PER_TENANT = "schema_per_tenant"
    DATABASE_PER_TENANT = "database_per_tenant"

    @property
    def requires_postgresql(self) -> bool:
        """Check if this strategy requires PostgreSQL."""
        return self == TenantIsolationStrategy.SCHEMA_PER_TENANT

    @property
    def requires_connection_routing(self) -> bool:
        """Check if this strategy requires per-request connection routing."""
        return self in (
            TenantIsolationStrategy.SCHEMA_PER_TENANT,
            TenantIsolationStrategy.DATABASE_PER_TENANT,
        )


@dataclass(frozen=True)
class IsolationConfig:
    """Configuration for tenant isolation.

    This immutable configuration defines how tenant isolation is implemented
    for a specific repository or service.

    Attributes:
        strategy: The isolation strategy to use.
        tenant_column: Name of the tenant discriminator column (for DISCRIMINATOR_COLUMN).
        schema_prefix: Prefix for tenant schemas (for SCHEMA_PER_TENANT).
        database_prefix: Prefix for tenant databases (for DATABASE_PER_TENANT).
        default_schema: Default schema to include in search_path (typically 'public').
        allow_cross_tenant: Whether to allow cross-tenant operations (admin only).

    Example:
        ```python
        # Discriminator column strategy (default)
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN,
            tenant_column="tenant_id",
        )

        # Schema per tenant strategy
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="tenant_",
            default_schema="public",
        )

        # Database per tenant strategy
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
            database_prefix="tenant_",
        )
        ```
    """

    strategy: TenantIsolationStrategy = TenantIsolationStrategy.DISCRIMINATOR_COLUMN
    tenant_column: str = DEFAULT_TENANT_COLUMN
    schema_prefix: str = DEFAULT_SCHEMA_PREFIX
    database_prefix: str = DEFAULT_DATABASE_PREFIX
    default_schema: str = "public"
    allow_cross_tenant: bool = False

    def get_schema_name(self, tenant_id: str) -> str:
        """Get the schema name for a tenant (SCHEMA_PER_TENANT strategy).

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The schema name for the tenant.
        """
        return f"{self.schema_prefix}{tenant_id}"

    def get_database_name(self, tenant_id: str) -> str:
        """Get the database name for a tenant (DATABASE_PER_TENANT strategy).

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The database name for the tenant.
        """
        return f"{self.database_prefix}{tenant_id}"

    def get_search_path(self, tenant_id: str) -> str:
        """Get the PostgreSQL search_path for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The search_path string (tenant_schema, default_schema).
        """
        tenant_schema = self.get_schema_name(tenant_id)
        return f"{tenant_schema}, {self.default_schema}"

    def validate_for_strategy(self) -> None:
        """Validate that configuration is appropriate for the chosen strategy.

        Raises:
            ValueError: If configuration is invalid for the strategy.
        """
        if self.strategy == TenantIsolationStrategy.DISCRIMINATOR_COLUMN:
            if not self.tenant_column:
                raise ValueError(
                    "tenant_column must be specified for DISCRIMINATOR_COLUMN strategy"
                )

        elif self.strategy == TenantIsolationStrategy.SCHEMA_PER_TENANT:
            if not self.schema_prefix:
                raise ValueError(
                    "schema_prefix must be specified for SCHEMA_PER_TENANT strategy"
                )

        elif self.strategy == TenantIsolationStrategy.DATABASE_PER_TENANT:
            if not self.database_prefix:
                raise ValueError(
                    "database_prefix must be specified for DATABASE_PER_TENANT strategy"
                )


@dataclass(frozen=True)
class TenantRoutingInfo:
    """Runtime tenant routing information.

    Contains the resolved tenant information needed for routing
    database operations.
    """

    tenant_id: str
    strategy: TenantIsolationStrategy
    schema_name: str | None = None
    database_name: str | None = None
    search_path: str | None = None

    @classmethod
    def from_config(
        cls,
        tenant_id: str,
        config: IsolationConfig,
    ) -> TenantRoutingInfo:
        """Create routing info from tenant ID and isolation config.

        Args:
            tenant_id: The tenant identifier.
            config: The isolation configuration.

        Returns:
            TenantRoutingInfo with appropriate routing details.
        """
        schema_name = None
        database_name = None
        search_path = None

        if config.strategy == TenantIsolationStrategy.SCHEMA_PER_TENANT:
            schema_name = config.get_schema_name(tenant_id)
            search_path = config.get_search_path(tenant_id)

        elif config.strategy == TenantIsolationStrategy.DATABASE_PER_TENANT:
            database_name = config.get_database_name(tenant_id)

        return cls(
            tenant_id=tenant_id,
            strategy=config.strategy,
            schema_name=schema_name,
            database_name=database_name,
            search_path=search_path,
        )
