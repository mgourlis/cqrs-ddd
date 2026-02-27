"""Delivery tracker port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..delivery import DeliveryRecord


@runtime_checkable
class IDeliveryTracker(Protocol):
    """Protocol for tracking notification delivery status."""

    async def record(self, record: DeliveryRecord) -> None:
        """Persist a delivery record."""
        ...
