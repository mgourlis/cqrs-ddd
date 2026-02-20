"""PartitionedProjectionWorker —
distribute work by aggregate_id hash using ILockStrategy."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

from .worker import ProjectionWorker

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent
    from cqrs_ddd_core.ports.locking import ILockStrategy

    from .ports import ICheckpointStore, IProjectionRegistry


class PartitionedProjectionWorker(IBackgroundWorker):
    """
    Projection worker that claims a partition via ILockStrategy and only processes
    events for that partition.

    Events are partitioned by hash of aggregate_id, ensuring all events for a given
    aggregate are processed by the same worker, maintaining ordering guarantees.
    """

    def __init__(
        self,
        event_store: IEventStore,
        projection_registry: IProjectionRegistry,
        checkpoint_store: ICheckpointStore,
        lock_strategy: ILockStrategy,
        *,
        partition_index: int = 0,
        partition_count: int = 1,
        projection_name: str = "partitioned",
        event_registry: EventTypeRegistry | None = None,
        batch_size: int = 100,
        poll_interval_seconds: float = 1.0,
        error_policy: Any = None,
    ) -> None:
        self._partition_index = partition_index
        self._partition_count = partition_count
        self._lock_strategy = lock_strategy
        self._worker = ProjectionWorker(
            event_store,
            projection_registry,
            checkpoint_store,
            projection_name=f"{projection_name}_p{partition_index}",
            event_registry=event_registry,
            batch_size=batch_size,
            poll_interval_seconds=poll_interval_seconds,
            error_policy=error_policy,
        )
        # Store reference to original worker for partition filtering
        self._worker._partition_filter = self._should_process_event
        self._lock_token: str | None = None

    def _should_process_event(self, stored: StoredEvent) -> bool:
        """
        Determine if an event belongs to this worker's partition.

        Uses SHA-256 hash of aggregate_id modulo partition_count.
        """
        aggregate_id = stored.aggregate_id
        hash_val = int(hashlib.sha256(aggregate_id.encode()).hexdigest(), 16)
        partition = hash_val % self._partition_count
        return partition == self._partition_index

    async def start(self) -> None:
        from cqrs_ddd_core.primitives.locking import ResourceIdentifier

        resource = ResourceIdentifier(
            "projection",
            f"partition_{self._partition_index}",
        )
        self._lock_token = await self._lock_strategy.acquire(resource)
        await self._worker.start()

    async def stop(self) -> None:
        await self._worker.stop()
        if self._lock_token:
            from cqrs_ddd_core.primitives.locking import ResourceIdentifier

            resource = ResourceIdentifier(
                "projection",
                f"partition_{self._partition_index}",
            )
            await self._lock_strategy.release(resource, self._lock_token)
            self._lock_token = None
