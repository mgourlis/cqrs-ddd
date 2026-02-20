from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cqrs_ddd_core.instrumentation import (
    HookRegistry,
    get_hook_registry,
    set_hook_registry,
    set_instrumentation_hook,
)


class RecordingHook:
    def __init__(self, name: str, order: list[str]) -> None:
        self._name = name
        self._order = order

    async def __call__(
        self,
        _operation: str,
        _attributes: dict[str, Any],
        next_handler: Any,
    ) -> Any:
        self._order.append(f"before:{self._name}")
        result = await next_handler()
        self._order.append(f"after:{self._name}")
        return result


@dataclass
class MsgType:
    value: str


@pytest.mark.asyncio
async def test_hook_registry_executes_in_priority_order() -> None:
    order: list[str] = []
    registry = HookRegistry()
    registry.register(RecordingHook("outer", order), priority=-10, operations=["*"])
    registry.register(RecordingHook("inner", order), priority=0, operations=["*"])

    async def _handler() -> str:
        order.append("handler")
        return "ok"

    result = await registry.execute_all("event.dispatch.Sample", {}, _handler)
    assert result == "ok"
    assert order == [
        "before:outer",
        "before:inner",
        "handler",
        "after:inner",
        "after:outer",
    ]


@pytest.mark.asyncio
async def test_hook_registry_wildcard_and_message_type_filtering() -> None:
    order: list[str] = []
    registry = HookRegistry()
    registry.register(
        RecordingHook("event", order),
        operations=["event.*"],
        message_types=[MsgType],
    )

    async def _handler() -> None:
        order.append("handler")

    await registry.execute_all(
        "event.dispatch.Sample",
        {"message_type": MsgType},
        _handler,
    )
    assert "before:event" in order

    order.clear()
    await registry.execute_all(
        "event.dispatch.Sample",
        {"message_type": str},
        _handler,
    )
    assert order == ["handler"]


@pytest.mark.asyncio
async def test_hook_registry_disabled_registration_and_cache_clear() -> None:
    order: list[str] = []
    registry = HookRegistry()
    reg = registry.register(
        RecordingHook("disabled", order),
        enabled=False,
        operations=["event.*"],
    )

    async def _handler() -> None:
        order.append("handler")

    await registry.execute_all("event.dispatch.Sample", {}, _handler)
    assert order == ["handler"]

    reg.enabled = True
    await registry.execute_all("event.dispatch.Sample", {}, _handler)
    assert "before:disabled" in order

    reg.clear_cache()
    registry.clear_caches()
    registry.clear()
    assert registry._registrations == []  # noqa: SLF001


@pytest.mark.asyncio
async def test_set_instrumentation_hook_backward_compatibility() -> None:
    original = get_hook_registry()
    try:
        new_registry = HookRegistry()
        set_hook_registry(new_registry)
        order: list[str] = []
        set_instrumentation_hook(RecordingHook("single", order))

        async def _handler() -> str:
            return "done"

        result = await get_hook_registry().execute_all("any.op", {}, _handler)
        assert result == "done"
        assert order[0] == "before:single"
    finally:
        set_hook_registry(original)
