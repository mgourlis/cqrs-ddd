"""ISnapshotStore — persistence protocol for event snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.aggregate import AggregateRoot


@runtime_checkable
class ISnapshotStore(Protocol):
    """Port for persisting and retrieving aggregate snapshots.

    Snapshots are periodic serializations of aggregate state, used to
    optimize event-sourced aggregate reconstruction.

    Usage::

        snapshot_store = SQLAlchemySnapshotStore(session)
        # Save a snapshot
        await snapshot_store.save_snapshot("OrderAggregate", order_id, snapshot_data)

        # Retrieve a snapshot
        snapshot = await snapshot_store.get_latest_snapshot("OrderAggregate", order_id)
    """

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
    ) -> None:
        """Save a snapshot of an aggregate's state.

        Args:
            aggregate_type: Type name of the aggregate (e.g., "Order").
            aggregate_id: The aggregate's ID.
            snapshot_data: Serialized state dict.
            version: The event version at the time of snapshot.
        """
        ...

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> dict[str, Any] | None:
        """Retrieve the most recent snapshot for an aggregate.

        Args:
            aggregate_type: Type name of the aggregate.
            aggregate_id: The aggregate's ID.

        Returns:
            Dict with snapshot_data, version, and created_at.
            None if no snapshot exists.
        """
        ...

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> None:
        """Delete all snapshots for an aggregate."""
        ...


class ISnapshotStrategy(Protocol):
    """
    Interface for deciding when an aggregate should be snapshotted.
    """

    def should_snapshot(self, aggregate: AggregateRoot[Any]) -> bool:
        ...
