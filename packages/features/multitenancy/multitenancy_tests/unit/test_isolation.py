"""Tests for isolation strategies."""

from __future__ import annotations

import pytest

from cqrs_ddd_multitenancy.isolation import (
    DEFAULT_DATABASE_PREFIX,
    DEFAULT_SCHEMA_PREFIX,
    DEFAULT_TENANT_COLUMN,
    IsolationConfig,
    TenantIsolationStrategy,
    TenantRoutingInfo,
)


class TestTenantIsolationStrategy:
    """Tests for TenantIsolationStrategy enum."""

    def test_discriminator_column_strategy(self) -> None:
        """Test DISCRIMINATOR_COLUMN strategy."""
        strategy = TenantIsolationStrategy.DISCRIMINATOR_COLUMN
        assert strategy.value == "discriminator_column"
        assert not strategy.requires_postgresql
        assert not strategy.requires_connection_routing

    def test_schema_per_tenant_strategy(self) -> None:
        """Test SCHEMA_PER_TENANT strategy."""
        strategy = TenantIsolationStrategy.SCHEMA_PER_TENANT
        assert strategy.value == "schema_per_tenant"
        assert strategy.requires_postgresql
        assert strategy.requires_connection_routing

    def test_database_per_tenant_strategy(self) -> None:
        """Test DATABASE_PER_TENANT strategy."""
        strategy = TenantIsolationStrategy.DATABASE_PER_TENANT
        assert strategy.value == "database_per_tenant"
        assert not strategy.requires_postgresql
        assert strategy.requires_connection_routing


class TestIsolationConfig:
    """Tests for IsolationConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = IsolationConfig()

        assert config.strategy == TenantIsolationStrategy.DISCRIMINATOR_COLUMN
        assert config.tenant_column == DEFAULT_TENANT_COLUMN
        assert config.schema_prefix == DEFAULT_SCHEMA_PREFIX
        assert config.database_prefix == DEFAULT_DATABASE_PREFIX
        assert config.default_schema == "public"
        assert config.allow_cross_tenant is False

    def test_discriminator_column_config(self) -> None:
        """Test discriminator column configuration."""
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN,
            tenant_column="org_id",
        )

        assert config.strategy == TenantIsolationStrategy.DISCRIMINATOR_COLUMN
        assert config.tenant_column == "org_id"

    def test_schema_per_tenant_config(self) -> None:
        """Test schema per tenant configuration."""
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="org_",
            default_schema="shared",
        )

        assert config.strategy == TenantIsolationStrategy.SCHEMA_PER_TENANT
        assert config.schema_prefix == "org_"
        assert config.default_schema == "shared"

    def test_database_per_tenant_config(self) -> None:
        """Test database per tenant configuration."""
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
            database_prefix="db_",
        )

        assert config.strategy == TenantIsolationStrategy.DATABASE_PER_TENANT
        assert config.database_prefix == "db_"

    def test_get_schema_name(self) -> None:
        """Test get_schema_name method."""
        config = IsolationConfig(schema_prefix="tenant_")

        assert config.get_schema_name("123") == "tenant_123"
        assert config.get_schema_name("acme-corp") == "tenant_acme-corp"

    def test_get_database_name(self) -> None:
        """Test get_database_name method."""
        config = IsolationConfig(database_prefix="db_")

        assert config.get_database_name("123") == "db_123"
        assert config.get_database_name("acme-corp") == "db_acme-corp"

    def test_get_search_path(self) -> None:
        """Test get_search_path method."""
        config = IsolationConfig(
            schema_prefix="tenant_",
            default_schema="public",
        )

        assert config.get_search_path("123") == "tenant_123, public"

    def test_validate_for_strategy_discriminator(self) -> None:
        """Test validation for discriminator strategy."""
        # Valid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN,
            tenant_column="tenant_id",
        )
        config.validate_for_strategy()  # Should not raise

        # Invalid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN,
            tenant_column="",
        )
        with pytest.raises(ValueError, match="tenant_column"):
            config.validate_for_strategy()

    def test_validate_for_strategy_schema(self) -> None:
        """Test validation for schema strategy."""
        # Valid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="tenant_",
        )
        config.validate_for_strategy()  # Should not raise

        # Invalid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="",
        )
        with pytest.raises(ValueError, match="schema_prefix"):
            config.validate_for_strategy()

    def test_validate_for_strategy_database(self) -> None:
        """Test validation for database strategy."""
        # Valid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
            database_prefix="tenant_",
        )
        config.validate_for_strategy()  # Should not raise

        # Invalid
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
            database_prefix="",
        )
        with pytest.raises(ValueError, match="database_prefix"):
            config.validate_for_strategy()


class TestTenantRoutingInfo:
    """Tests for TenantRoutingInfo."""

    def test_from_config_discriminator(self) -> None:
        """Test from_config for discriminator strategy."""
        config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)

        info = TenantRoutingInfo.from_config("tenant-123", config)

        assert info.tenant_id == "tenant-123"
        assert info.strategy == TenantIsolationStrategy.DISCRIMINATOR_COLUMN
        assert info.schema_name is None
        assert info.database_name is None
        assert info.search_path is None

    def test_from_config_schema_per_tenant(self) -> None:
        """Test from_config for schema strategy."""
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
            schema_prefix="tenant_",
            default_schema="public",
        )

        info = TenantRoutingInfo.from_config("123", config)

        assert info.tenant_id == "123"
        assert info.strategy == TenantIsolationStrategy.SCHEMA_PER_TENANT
        assert info.schema_name == "tenant_123"
        assert info.search_path == "tenant_123, public"
        assert info.database_name is None

    def test_from_config_database_per_tenant(self) -> None:
        """Test from_config for database strategy."""
        config = IsolationConfig(
            strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
            database_prefix="db_",
        )

        info = TenantRoutingInfo.from_config("123", config)

        assert info.tenant_id == "123"
        assert info.strategy == TenantIsolationStrategy.DATABASE_PER_TENANT
        assert info.database_name == "db_123"
        assert info.schema_name is None
        assert info.search_path is None
