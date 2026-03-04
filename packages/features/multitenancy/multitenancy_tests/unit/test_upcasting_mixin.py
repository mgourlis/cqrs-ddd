"""Unit tests for MultitenantUpcasterMixin."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_multitenancy.mixins.upcasting import MultitenantUpcasterMixin

# ── Test Doubles ───────────────────────────────────────────────────────


class MockUpcaster:
    """Mock base upcaster for testing."""

    @property
    def event_type(self) -> str:
        return "OrderCreated"

    @property
    def source_version(self) -> int:
        return 1

    @property
    def target_version(self) -> int:
        return 2

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Simulate upcasting that renames a field."""
        # Simulate renaming 'customer_id' to 'customer_email'
        upcasted = dict(event_data)
        if "customer_id" in upcasted:
            upcasted["customer_email"] = (
                f"customer-{upcasted['customer_id']}@example.com"
            )
            del upcasted["customer_id"]
        return upcasted


class TestMultitenantUpcaster(MultitenantUpcasterMixin, MockUpcaster):
    """Test implementation combining mixin with mock base."""


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def upcaster() -> TestMultitenantUpcaster:
    """Create test upcaster."""
    return TestMultitenantUpcaster()


@pytest.fixture
def tenant_id() -> str:
    """Tenant ID."""
    return "tenant-123"


# ── Test Cases ──────────────────────────────────────────────────────────


class TestMultitenantUpcasterMixinProperties:
    """Tests for property delegation."""

    def test_event_type_delegates_to_base(
        self, upcaster: TestMultitenantUpcaster
    ) -> None:
        """Should delegate event_type to base upcaster."""
        assert upcaster.event_type == "OrderCreated"

    def test_source_version_delegates_to_base(
        self, upcaster: TestMultitenantUpcaster
    ) -> None:
        """Should delegate source_version to base upcaster."""
        assert upcaster.source_version == 1

    def test_target_version_delegates_to_base(
        self, upcaster: TestMultitenantUpcaster
    ) -> None:
        """Should delegate target_version to base upcaster."""
        assert upcaster.target_version == 2


class TestMultitenantUpcasterMixinUpcast:
    """Tests for upcast() method."""

    def test_upcast_preserves_tenant_id(
        self, upcaster: TestMultitenantUpcaster, tenant_id: str
    ) -> None:
        """Should preserve tenant_id through upcasting."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
            "tenant_id": tenant_id,
        }

        upcasted = upcaster.upcast(event_data)

        # Should preserve tenant_id
        assert upcasted.get("tenant_id") == tenant_id
        # Should apply upcasting transformation
        assert "customer_email" in upcasted
        assert "customer_id" not in upcasted

    def test_upcast_restores_missing_tenant_id(
        self, upcaster: TestMultitenantUpcaster, tenant_id: str
    ) -> None:
        """Should restore tenant_id if removed by base upcaster."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
            "tenant_id": tenant_id,
        }

        # Create upcaster that removes tenant_id
        class RemovingUpcaster:
            @property
            def event_type(self) -> str:
                return "OrderCreated"

            @property
            def source_version(self) -> int:
                return 1

            @property
            def target_version(self) -> int:
                return 2

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                upcasted = dict(event_data)
                # Simulate bug: removes tenant_id
                upcasted.pop("tenant_id", None)
                return upcasted

        class TestRemovingUpcaster(MultitenantUpcasterMixin, RemovingUpcaster):
            pass

        upcaster = TestRemovingUpcaster()
        upcasted = upcaster.upcast(event_data)

        # Should restore tenant_id
        assert upcasted.get("tenant_id") == tenant_id

    def test_upcast_logs_warning_for_missing_tenant_id(
        self, upcaster: TestMultitenantUpcaster, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log warning if tenant_id is missing from event data."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
            # No tenant_id
        }

        upcasted = upcaster.upcast(event_data)

        # Should log warning
        assert "Tenant ID field 'tenant_id' not found" in caplog.text
        # Should not add tenant_id if it wasn't there
        assert "tenant_id" not in upcasted

    def test_upcast_restores_modified_tenant_id(
        self, upcaster: TestMultitenantUpcaster, tenant_id: str
    ) -> None:
        """Should restore tenant_id if modified by base upcaster."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
            "tenant_id": tenant_id,
        }

        # Create upcaster that modifies tenant_id
        class ModifyingUpcaster:
            @property
            def event_type(self) -> str:
                return "OrderCreated"

            @property
            def source_version(self) -> int:
                return 1

            @property
            def target_version(self) -> int:
                return 2

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                upcasted = dict(event_data)
                # Simulate bug: modifies tenant_id
                upcasted["tenant_id"] = "wrong-tenant"
                return upcasted

        class TestModifyingUpcaster(MultitenantUpcasterMixin, ModifyingUpcaster):
            pass

        upcaster = TestModifyingUpcaster()
        upcasted = upcaster.upcast(event_data)

        # Should restore original tenant_id
        assert upcasted.get("tenant_id") == tenant_id

    def test_upcast_with_custom_tenant_field(self, tenant_id: str) -> None:
        """Should work with custom tenant field name."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
            "org_id": tenant_id,  # Custom field
        }

        # Create upcaster with custom tenant field
        class CustomFieldUpcaster(MultitenantUpcasterMixin, MockUpcaster):
            _tenant_field: str = "org_id"

        upcaster = CustomFieldUpcaster()
        upcasted = upcaster.upcast(event_data)

        # Should preserve custom tenant field
        assert upcasted.get("org_id") == tenant_id

    def test_upcast_does_not_add_tenant_if_not_present(
        self, upcaster: TestMultitenantUpcaster
    ) -> None:
        """Should not add tenant_id if it wasn't in original data."""
        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "customer_id": "cust-123",
        }

        upcasted = upcaster.upcast(event_data)

        # Should not add tenant_id
        assert "tenant_id" not in upcasted


class TestMultitenantUpcasterMixinIntegration:
    """Integration tests for upcaster mixin."""

    def test_upcast_chain_preserves_tenant_id(self, tenant_id: str) -> None:
        """Should preserve tenant_id through multiple upcasting steps."""

        # Create first upcaster (v1 -> v2)
        class UpcasterV1ToV2:
            @property
            def event_type(self) -> str:
                return "OrderCreated"

            @property
            def source_version(self) -> int:
                return 1

            @property
            def target_version(self) -> int:
                return 2

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                upcasted = dict(event_data)
                upcasted["version"] = 2
                return upcasted

        # Create second upcaster (v2 -> v3)
        class UpcasterV2ToV3:
            @property
            def event_type(self) -> str:
                return "OrderCreated"

            @property
            def source_version(self) -> int:
                return 2

            @property
            def target_version(self) -> int:
                return 3

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                upcasted = dict(event_data)
                upcasted["version"] = 3
                return upcasted

        class TestUpcasterV1ToV2(MultitenantUpcasterMixin, UpcasterV1ToV2):
            pass

        class TestUpcasterV2ToV3(MultitenantUpcasterMixin, UpcasterV2ToV3):
            pass

        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "tenant_id": tenant_id,
            "version": 1,
        }

        # Apply first upcaster
        upcaster1 = TestUpcasterV1ToV2()
        upcasted1 = upcaster1.upcast(event_data)

        # Apply second upcaster
        upcaster2 = TestUpcasterV2ToV3()
        upcasted2 = upcaster2.upcast(upcasted1)

        # Should preserve tenant_id through chain
        assert upcasted2.get("tenant_id") == tenant_id
        assert upcasted2.get("version") == 3

    def test_upcast_with_complex_transformation(self, tenant_id: str) -> None:
        """Should preserve tenant_id through complex transformations."""

        # Create upcaster with complex nested structure
        class ComplexUpcaster:
            @property
            def event_type(self) -> str:
                return "OrderCreated"

            @property
            def source_version(self) -> int:
                return 1

            @property
            def target_version(self) -> int:
                return 2

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                # Complex transformation
                return {
                    "aggregate_id": event_data["aggregate_id"],
                    "aggregate_type": event_data["aggregate_type"],
                    "order_details": {
                        "items": event_data.get("items", []),
                        "total": event_data.get("total", 0),
                    },
                    "metadata": {
                        "created_at": event_data.get("created_at"),
                    },
                }

        class TestComplexUpcaster(MultitenantUpcasterMixin, ComplexUpcaster):
            pass

        event_data = {
            "aggregate_id": "order-1",
            "aggregate_type": "Order",
            "tenant_id": tenant_id,
            "items": ["item1", "item2"],
            "total": 100,
            "created_at": "2024-01-01",
        }

        upcaster = TestComplexUpcaster()
        upcasted = upcaster.upcast(event_data)

        # Should restore tenant_id even though base upcaster removed it
        assert upcasted.get("tenant_id") == tenant_id
