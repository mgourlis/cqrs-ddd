from __future__ import annotations

from cqrs_ddd_core.instrumentation import (
    HookRegistry,
    get_hook_registry,
    set_hook_registry,
)
from cqrs_ddd_observability.hooks import (
    ObservabilityInstrumentationHook,
    install_framework_hooks,
)


class _FakeHook(ObservabilityInstrumentationHook):
    async def __call__(self, operation, attributes, next_handler):  # type: ignore[override]
        return await next_handler()


async def test_instrumentation_hook_calls_next_handler() -> None:
    hook = _FakeHook()
    called = False

    async def _next() -> str:
        nonlocal called
        called = True
        return "ok"

    result = await hook("test.operation", {"a": 1}, _next)
    assert result == "ok"
    assert called


def test_install_framework_hooks_registers_hook() -> None:
    original = get_hook_registry()
    try:
        local = HookRegistry()
        set_hook_registry(local)
        install_framework_hooks(operations=["*"], priority=-100, enabled=True)
        assert len(local._registrations) == 1  # noqa: SLF001
    finally:
        set_hook_registry(original)
