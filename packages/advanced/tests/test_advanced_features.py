from typing import Any

import pytest

from cqrs_ddd_advanced_core.sagas.orchestration import Saga
from cqrs_ddd_advanced_core.sagas.state import SagaState
from cqrs_ddd_advanced_core.upcasting.registry import UpcasterChain


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


def test_upcaster_registry_happy_path() -> None:
    upcaster = MockUpcaster()
    registry = UpcasterChain(upcasters=[upcaster])

    data = {"old": "data"}
    result, version = registry.upcast("TestEvent", data, 1)
    assert result["upcasted"] is True
    assert result["old"] == "data"
    assert version == 2


def test_upcaster_registry_sorting() -> None:
    class UpcasterV1:
        event_type = "SortEvent"
        source_version = 1
        target_version = 2

        def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
            data["v1"] = True
            return data

    class UpcasterV2:
        event_type = "SortEvent"
        source_version = 2
        target_version = 3

        def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
            data["v2"] = True
            return data

    # Register out of order
    registry = UpcasterChain(upcasters=[UpcasterV2(), UpcasterV1()])

    data: dict[str, Any] = {}
    result, version = registry.upcast("SortEvent", data, 1)
    assert result["v1"] is True
    assert result["v2"] is True
    assert version == 3


@pytest.mark.asyncio
async def test_saga_event_already_processed() -> None:
    class MyStateV1(SagaState):
        def __init__(self) -> None:
            super().__init__(id="saga-2")

    class MySagaV1(Saga[MyStateV1]):
        def _handle_event(self, _event: Any) -> None:
            self.dispatch(Command())

    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

    registry = MessageRegistry()

    state = MyStateV1()
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.domain.events import DomainEvent

    class MyEventV1(DomainEvent):
        pass

    event = MyEventV1()

    state.mark_event_processed(event.event_id)
    saga = MySagaV1(state, registry)
    await saga.handle(event)

    assert len(saga.collect_commands()) == 0


@pytest.mark.asyncio
async def test_saga_logic_happy_path() -> None:
    class MyStateV2(SagaState):
        def __init__(self) -> None:
            super().__init__(id="saga-1")

    class MySagaV2(Saga[MyStateV2]):
        def _handle_event(self, _event: Any) -> None:
            from cqrs_ddd_core.cqrs.command import Command

            class MyCommand(Command):
                pass

            self.dispatch(MyCommand())

    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

    registry = MessageRegistry()
    state = MyStateV2()
    saga = MySagaV2(state, registry)

    from cqrs_ddd_core.domain.events import DomainEvent

    class MyEventV2(DomainEvent):
        pass

    event = MyEventV2()
    await saga.handle(event)

    cmds = saga.collect_commands()
    assert len(cmds) == 1
    assert state.is_event_processed(event.event_id)
