"""Tests for tenant exceptions."""

from __future__ import annotations

import pytest

from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
    TenantDeactivatedError,
    TenantError,
    TenantIsolationError,
    TenantNotFoundError,
    TenantProvisioningError,
)


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_tenant_error_is_domain_error(self) -> None:
        """Test TenantError inherits from DomainError."""
        from cqrs_ddd_core.primitives.exceptions import DomainError

        assert issubclass(TenantError, DomainError)

    def test_tenant_isolation_error_is_infrastructure_error(self) -> None:
        """Test TenantIsolationError inherits from InfrastructureError."""
        from cqrs_ddd_core.primitives.exceptions import InfrastructureError

        assert issubclass(TenantIsolationError, InfrastructureError)

    def test_all_tenant_errors_inherit_from_tenant_error(self) -> None:
        """Test all tenant domain errors inherit from TenantError."""
        assert issubclass(TenantContextMissingError, TenantError)
        assert issubclass(TenantNotFoundError, TenantError)
        assert issubclass(TenantDeactivatedError, TenantError)
        assert issubclass(CrossTenantAccessError, TenantError)


class TestTenantContextMissingError:
    """Tests for TenantContextMissingError."""

    def test_default_message(self) -> None:
        """Test default message."""
        error = TenantContextMissingError()
        assert "not set" in str(error).lower()
        assert error.tenant_id is None

    def test_custom_message(self) -> None:
        """Test custom message."""
        error = TenantContextMissingError("Custom message")
        assert str(error) == "Custom message"

    def test_with_tenant_id(self) -> None:
        """Test with tenant_id."""
        error = TenantContextMissingError(tenant_id="tenant-123")
        assert error.tenant_id == "tenant-123"


class TestTenantNotFoundError:
    """Tests for TenantNotFoundError."""

    def test_default_message(self) -> None:
        """Test default message."""
        error = TenantNotFoundError("tenant-123")
        assert "tenant-123" in str(error)
        assert "not found" in str(error).lower()
        assert error.tenant_id == "tenant-123"

    def test_custom_message(self) -> None:
        """Test custom message."""
        error = TenantNotFoundError("tenant-123", "Custom message")
        assert str(error) == "Custom message"
        assert error.tenant_id == "tenant-123"


class TestTenantDeactivatedError:
    """Tests for TenantDeactivatedError."""

    def test_default_message(self) -> None:
        """Test default message."""
        error = TenantDeactivatedError("tenant-123")
        assert "tenant-123" in str(error)
        assert "deactivated" in str(error).lower()
        assert error.tenant_id == "tenant-123"

    def test_custom_message(self) -> None:
        """Test custom message."""
        error = TenantDeactivatedError("tenant-123", "Custom message")
        assert str(error) == "Custom message"


class TestCrossTenantAccessError:
    """Tests for CrossTenantAccessError."""

    def test_basic_message(self) -> None:
        """Test basic error message."""
        error = CrossTenantAccessError(
            current_tenant="tenant-1",
            target_tenant="tenant-2",
        )
        assert "Cross-tenant access denied" in str(error)
        assert "tenant-1" in str(error)
        assert "tenant-2" in str(error)
        assert error.current_tenant == "tenant-1"
        assert error.target_tenant == "tenant-2"

    def test_with_resource_info(self) -> None:
        """Test with resource information."""
        error = CrossTenantAccessError(
            current_tenant="tenant-1",
            target_tenant="tenant-2",
            resource_type="Order",
            resource_id="order-123",
        )
        assert "Order" in str(error)
        assert "order-123" in str(error)


class TestTenantIsolationError:
    """Tests for TenantIsolationError."""

    def test_basic_message(self) -> None:
        """Test basic error message."""
        error = TenantIsolationError("Something failed")
        assert str(error) == "Something failed"
        assert error.tenant_id is None
        assert error.strategy is None

    def test_with_context(self) -> None:
        """Test with context information."""
        error = TenantIsolationError(
            "Schema routing failed",
            tenant_id="tenant-123",
            strategy="SCHEMA_PER_TENANT",
        )
        assert error.tenant_id == "tenant-123"
        assert error.strategy == "SCHEMA_PER_TENANT"


class TestTenantProvisioningError:
    """Tests for TenantProvisioningError."""

    def test_basic_message(self) -> None:
        """Test basic error message."""
        error = TenantProvisioningError("tenant-123", "Schema creation failed")
        assert "tenant-123" in str(error)
        assert "Schema creation failed" in str(error)
        assert error.tenant_id == "tenant-123"

    def test_with_strategy(self) -> None:
        """Test with strategy."""
        error = TenantProvisioningError(
            "tenant-123",
            "Failed",
            strategy="DATABASE_PER_TENANT",
        )
        assert error.strategy == "DATABASE_PER_TENANT"
