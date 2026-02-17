"""SnapshotStrategyRegistry — manages snapshot strategies by aggregate type."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot

from ..ports.snapshots import ISnapshotStrategy  # noqa: TCH001


class SnapshotStrategyRegistry:
    """Registry for selecting snapshot strategies by aggregate type.

    Maps aggregate type names to their snapshot decision strategies.

    **Usage:**

        registry = SnapshotStrategyRegistry()

        # Register a strategy for a specific aggregate
        registry.register("Order", VersionBasedStrategy(snapshot_every=10))

        # Later, retrieve and use:
        strategy = registry.get("Order")
        if strategy and strategy.should_snapshot(order):
            await snapshot_store.save_snapshot(...)
    """

    def __init__(self) -> None:
        self._strategies: dict[str, ISnapshotStrategy] = {}
        self._default_strategy: ISnapshotStrategy | None = None

    # ── Registration ─────────────────────────────────────────────

    def register(self, aggregate_type: str, strategy: ISnapshotStrategy) -> None:
        """Register a snapshot strategy for an aggregate type."""
        self._strategies[aggregate_type] = strategy

    def set_default(self, strategy: ISnapshotStrategy) -> None:
        """Set a default strategy to use if no specific one is registered."""
        self._default_strategy = strategy

    # ── Lookup ───────────────────────────────────────────────────

    def get(self, aggregate_type: str) -> ISnapshotStrategy | None:
        """Retrieve a strategy by aggregate type name.

        If no specific strategy is registered, returns the default if set.
        """
        return self._strategies.get(aggregate_type) or self._default_strategy

    def has(self, aggregate_type: str) -> bool:
        """Return ``True`` if a strategy is registered for the aggregate type."""
        return aggregate_type in self._strategies

    # ── Convenience ──────────────────────────────────────────────

    def should_snapshot(
        self, aggregate_type: str, aggregate: AggregateRoot[Any]
    ) -> bool:
        """Check if an aggregate should be snapshotted.

        Retrieves the strategy for the aggregate type and calls its
        ``should_snapshot()`` method.

        Returns ``False`` if no strategy is registered and no default is set.
        """
        strategy = self.get(aggregate_type)
        if strategy is None:
            return False
        return strategy.should_snapshot(aggregate)

    # ── Introspection ────────────────────────────────────────────

    def list_registered(self) -> list[str]:
        """Return all registered aggregate type names."""
        return list(self._strategies.keys())

    # ── Cleanup ──────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all registrations (testing utility)."""
        self._strategies.clear()
        self._default_strategy = None


__all__ = ["SnapshotStrategyRegistry"]
