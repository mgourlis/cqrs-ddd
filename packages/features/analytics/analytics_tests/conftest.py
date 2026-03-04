"""Shared test fixtures for analytics tests."""

from __future__ import annotations

import pytest
from pydantic import Field

from cqrs_ddd_core.domain.events import DomainEvent

# ── Test event types ─────────────────────────────────────────────


class OrderCreated(DomainEvent):
    """Test event: an order was created."""

    order_id: str = ""
    total_amount: float = 0.0
    aggregate_type: str | None = "Order"


class OrderCancelled(DomainEvent):
    """Test event: an order was cancelled."""

    order_id: str = ""
    reason: str = ""
    aggregate_type: str | None = "Order"


class DeliveryLocationUpdated(DomainEvent):
    """Test event: delivery location updated (for geo tests)."""

    delivery_id: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    aggregate_type: str | None = "Delivery"


class UnmappedEvent(DomainEvent):
    """Test event: not registered with any mapper."""

    data: str = ""


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def order_created() -> OrderCreated:
    return OrderCreated(
        order_id="ord-123",
        total_amount=99.99,
        aggregate_id="ord-123",
    )


@pytest.fixture
def order_cancelled() -> OrderCancelled:
    return OrderCancelled(
        order_id="ord-123",
        reason="Customer requested",
        aggregate_id="ord-123",
    )


@pytest.fixture
def delivery_location_event() -> DeliveryLocationUpdated:
    return DeliveryLocationUpdated(
        delivery_id="dlv-456",
        latitude=37.7749,
        longitude=-122.4194,
        aggregate_id="dlv-456",
    )
