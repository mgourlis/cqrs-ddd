from typing import Any

from cqrs_ddd_core.domain.aggregate import AggregateRoot

from ..ports.snapshots import ISnapshotStrategy


class EveryNEventsStrategy(ISnapshotStrategy):
    """
    Snapshots an aggregate whenever its version is a multiple of N.
    """

    def __init__(self, n: int = 50) -> None:
        self.n = n

    def should_snapshot(self, aggregate: AggregateRoot[Any]) -> bool:
        return aggregate.version > 0 and aggregate.version % self.n == 0
