from typing import Any

from cqrs_ddd_advanced_core.snapshots.strategy import EveryNEventsStrategy
from cqrs_ddd_advanced_core.upcasting.registry import UpcasterChain
from cqrs_ddd_core.domain.aggregate import AggregateRoot


class MockAggregate(AggregateRoot):
    pass


class MockUpcaster:
    @property
    def event_type(self) -> str:
        return "TestEvent"

    @property
    def source_version(self) -> int:
        return 1

    @property
    def target_version(self) -> int:
        return 2

    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        data["upcasted"] = True
        return data


def test_snapshot_strategy() -> None:
    strategy = EveryNEventsStrategy(n=3)
    agg = MockAggregate(id="1")

    assert strategy.should_snapshot(agg) is False

    # Simulate persistence-managed version (e.g. after 3 saves)
    object.__setattr__(agg, "_version", 3)
    assert strategy.should_snapshot(agg) is True


def test_upcasting_registry() -> None:
    upcaster = MockUpcaster()
    registry = UpcasterChain([upcaster])

    data = {"v": 1}
    upcasted, version = registry.upcast("TestEvent", data, 1)
    assert upcasted["upcasted"] is True
    assert version == 2


def test_missing_upcaster() -> None:
    registry = UpcasterChain([])
    data = {"v": 1}
    # Should return original data if no upcaster found
    upcasted, version = registry.upcast("OtherEvent", data, 1)
    assert upcasted == data
    assert version == 1
