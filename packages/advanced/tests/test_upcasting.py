"""Tests for event upcasting infrastructure (EventUpcaster, UpcasterChain, UpcasterRegistry)."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_advanced_core.upcasting.registry import (
    EventUpcaster,
    UpcasterChain,
    UpcasterRegistry,
)


# Test upcaster implementations
class OrderCreatedV1ToV2(EventUpcaster):
    """Upcaster that adds currency field to OrderCreated events."""

    event_type = "OrderCreated"
    source_version = 1
    target_version = 2

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        event_data["currency"] = "USD"
        return event_data


class OrderCreatedV2ToV3(EventUpcaster):
    """Upcaster that adds tax_rate field."""

    event_type = "OrderCreated"
    source_version = 2
    target_version = 3

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        event_data["tax_rate"] = 0.1
        return event_data


class PaymentProcessedV1ToV2(EventUpcaster):
    """Upcaster for different event type."""

    event_type = "PaymentProcessed"
    source_version = 1
    target_version = 2

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        event_data["status"] = "completed"
        return event_data


class TestEventUpcaster:
    """Test EventUpcaster base class."""

    def test_target_version_auto_computed(self) -> None:
        """If target_version not set, it's auto-computed as source_version + 1."""

        class AutoVersionUpcaster(EventUpcaster):
            event_type = "TestEvent"
            source_version = 5
            # target_version not set

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                return event_data

        upcaster = AutoVersionUpcaster()

        assert upcaster.target_version == 6

    def test_explicit_target_version_not_overridden(self) -> None:
        """Explicit target_version is not overridden."""

        class ExplicitVersionUpcaster(EventUpcaster):
            event_type = "TestEvent"
            source_version = 1
            target_version = 10  # Jump multiple versions

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                return event_data

        upcaster = ExplicitVersionUpcaster()

        assert upcaster.target_version == 10

    def test_upcast_raises_not_implemented_error(self) -> None:
        """Base EventUpcaster.upcast raises NotImplementedError."""

        class UnimplementedUpcaster(EventUpcaster):
            event_type = "TestEvent"
            source_version = 1
            target_version = 2
            # upcast() not implemented

        upcaster = UnimplementedUpcaster()

        with pytest.raises(NotImplementedError):
            upcaster.upcast({})


class TestUpcasterChain:
    """Test UpcasterChain."""

    def test_upcast_single_step(self) -> None:
        """Chain with single upcaster transforms event."""
        upcaster = OrderCreatedV1ToV2()
        chain = UpcasterChain([upcaster])

        data = {"order_id": "123", "amount": 100.0}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=1
        )

        assert result_data["currency"] == "USD"
        assert result_version == 2

    def test_upcast_multi_step_chain(self) -> None:
        """Chain with multiple upcasters applies them in sequence."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = OrderCreatedV2ToV3()
        chain = UpcasterChain([upcaster1, upcaster2])

        data = {"order_id": "123", "amount": 100.0}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=1
        )

        # Both upcasters should have been applied
        assert result_data["currency"] == "USD"
        assert result_data["tax_rate"] == 0.1
        assert result_version == 3

    def test_upcast_skips_irrelevant_versions(self) -> None:
        """Chain skips upcasters that don't match current version."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = OrderCreatedV2ToV3()
        chain = UpcasterChain([upcaster1, upcaster2])

        # Start from version 2 -> should only apply V2ToV3
        data = {"order_id": "123", "amount": 100.0, "currency": "EUR"}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=2
        )

        assert result_data["currency"] == "EUR"  # Not overwritten
        assert result_data["tax_rate"] == 0.1  # Added by V2ToV3
        assert result_version == 3

    def test_upcast_skips_different_event_types(self) -> None:
        """Chain skips upcasters for different event types."""
        order_upcaster = OrderCreatedV1ToV2()
        payment_upcaster = PaymentProcessedV1ToV2()
        chain = UpcasterChain([order_upcaster, payment_upcaster])

        data = {"order_id": "123", "amount": 100.0}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=1
        )

        # Only order upcaster should be applied
        assert result_data["currency"] == "USD"
        assert "status" not in result_data
        assert result_version == 2

    def test_upcast_with_empty_chain(self) -> None:
        """Empty chain returns data unchanged."""
        chain = UpcasterChain([])

        data = {"order_id": "123"}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=1
        )

        assert result_data == data
        assert result_version == 1

    def test_latest_version_property(self) -> None:
        """latest_version returns highest target version in chain."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = OrderCreatedV2ToV3()
        chain = UpcasterChain([upcaster1, upcaster2])

        assert chain.latest_version == 3

    def test_latest_version_for_empty_chain(self) -> None:
        """latest_version returns 0 for empty chain."""
        chain = UpcasterChain([])

        assert chain.latest_version == 0

    def test_chain_sorts_by_source_version(self) -> None:
        """UpcasterChain sorts upcasters by source_version."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = OrderCreatedV2ToV3()
        # Pass in reverse order
        chain = UpcasterChain([upcaster2, upcaster1])

        # Should still apply in correct order (v1->v2 then v2->v3)
        data = {"order_id": "123", "amount": 100.0}
        result_data, result_version = chain.upcast(
            "OrderCreated", data, stored_version=1
        )

        assert result_data["currency"] == "USD"
        assert result_data["tax_rate"] == 0.1
        assert result_version == 3


class TestUpcasterRegistry:
    """Test UpcasterRegistry."""

    @pytest.fixture
    def registry(self) -> UpcasterRegistry:
        """Create fresh registry for each test."""
        return UpcasterRegistry()

    def test_register_single_upcaster(self, registry: UpcasterRegistry) -> None:
        """register() stores upcaster."""
        upcaster = OrderCreatedV1ToV2()

        registry.register(upcaster)

        assert registry.has_upcasters("OrderCreated")

    def test_register_multiple_upcasters_for_same_event(
        self, registry: UpcasterRegistry
    ) -> None:
        """Multiple upcasters can be registered for same event type."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = OrderCreatedV2ToV3()

        registry.register(upcaster1)
        registry.register(upcaster2)

        assert registry.has_upcasters("OrderCreated")

    def test_register_duplicate_source_version_raises_error(
        self, registry: UpcasterRegistry
    ) -> None:
        """Registering duplicate source_version raises ValueError."""
        upcaster1 = OrderCreatedV1ToV2()

        # Create another upcaster with same source version
        class DuplicateUpcaster(EventUpcaster):
            event_type = "OrderCreated"
            source_version = 1
            target_version = 3

            def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
                return event_data

        upcaster2 = DuplicateUpcaster()

        registry.register(upcaster1)

        with pytest.raises(ValueError, match="Duplicate upcaster"):
            registry.register(upcaster2)

    def test_chain_for_returns_chain(self, registry: UpcasterRegistry) -> None:
        """chain_for() returns UpcasterChain for event type."""
        upcaster = OrderCreatedV1ToV2()
        registry.register(upcaster)

        chain = registry.chain_for("OrderCreated")

        assert isinstance(chain, UpcasterChain)

    def test_chain_for_empty_returns_empty_chain(
        self, registry: UpcasterRegistry
    ) -> None:
        """chain_for() returns empty chain for unregistered event type."""
        chain = registry.chain_for("UnknownEvent")

        assert isinstance(chain, UpcasterChain)
        assert chain.latest_version == 0

    def test_upcast_convenience_method(self, registry: UpcasterRegistry) -> None:
        """upcast() convenience method works without building chain."""
        upcaster = OrderCreatedV1ToV2()
        registry.register(upcaster)

        data = {"order_id": "123", "amount": 100.0}
        result_data, result_version = registry.upcast(
            "OrderCreated", data, stored_version=1
        )

        assert result_data["currency"] == "USD"
        assert result_version == 2

    def test_has_upcasters_true(self, registry: UpcasterRegistry) -> None:
        """has_upcasters returns True for registered event type."""
        upcaster = OrderCreatedV1ToV2()
        registry.register(upcaster)

        assert registry.has_upcasters("OrderCreated")

    def test_has_upcasters_false(self, registry: UpcasterRegistry) -> None:
        """has_upcasters returns False for unregistered event type."""
        assert not registry.has_upcasters("UnknownEvent")

    def test_registered_event_types(self, registry: UpcasterRegistry) -> None:
        """registered_event_types returns list of event types with upcasters."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = PaymentProcessedV1ToV2()

        registry.register(upcaster1)
        registry.register(upcaster2)

        event_types = registry.registered_event_types()

        assert len(event_types) == 2
        assert "OrderCreated" in event_types
        assert "PaymentProcessed" in event_types

    def test_clear(self, registry: UpcasterRegistry) -> None:
        """clear() removes all registrations."""
        upcaster1 = OrderCreatedV1ToV2()
        upcaster2 = PaymentProcessedV1ToV2()

        registry.register(upcaster1)
        registry.register(upcaster2)

        registry.clear()

        assert not registry.has_upcasters("OrderCreated")
        assert not registry.has_upcasters("PaymentProcessed")
        assert len(registry.registered_event_types()) == 0

    def test_multiple_event_types_isolation(self, registry: UpcasterRegistry) -> None:
        """Upcasters for different event types are isolated."""
        order_upcaster = OrderCreatedV1ToV2()
        payment_upcaster = PaymentProcessedV1ToV2()

        registry.register(order_upcaster)
        registry.register(payment_upcaster)

        # Upcast order event
        order_data = {"order_id": "123"}
        order_result, _ = registry.upcast("OrderCreated", order_data, stored_version=1)
        assert "currency" in order_result
        assert "status" not in order_result

        # Upcast payment event
        payment_data = {"transaction_id": "tx-456"}
        payment_result, _ = registry.upcast(
            "PaymentProcessed", payment_data, stored_version=1
        )
        assert "status" in payment_result
        assert "currency" not in payment_result
