"""Enhanced instrumentation hooks — supports multiple hooks with filtering."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger("cqrs_ddd.instrumentation")

_MATCH_CACHE_MAX_SIZE = 2048


@runtime_checkable
class InstrumentationHook(Protocol):
    """Protocol for instrumentation hooks (tracing, metrics, etc.)."""

    async def __call__(
        self,
        operation: str,
        attributes: dict[str, Any],
        next_handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Wrap an operation with instrumentation."""
        ...


class HookRegistration:
    """A registered hook with filtering and priority."""

    def __init__(
        self,
        hook: InstrumentationHook,
        *,
        priority: int = 0,
        predicate: Callable[[str, dict[str, Any]], bool] | None = None,
        operations: list[str] | None = None,
        message_types: list[type[Any]] | None = None,
        enabled: bool = True,
    ) -> None:
        self.hook = hook
        self.priority = priority
        self.predicate = predicate
        self.operations = operations or []
        self.message_types = message_types or []
        self.enabled = enabled
        self._match_cache: dict[str, bool] = {}

    def matches(self, operation: str, attributes: dict[str, Any]) -> bool:
        """Check if this registration applies to the operation."""
        if not self.enabled:
            return False

        if not self._matches_predicate(operation, attributes):
            return False

        if not self._matches_operation(operation):
            return False

        return self._matches_message_type(attributes)

    def _matches_predicate(self, operation: str, attributes: dict[str, Any]) -> bool:
        if self.predicate is None:
            return True
        return self.predicate(operation, attributes)

    def _matches_operation(self, operation: str) -> bool:
        if not self.operations:
            return True
        if operation in self._match_cache:
            return self._match_cache[operation]
        matched = any(
            fnmatch.fnmatch(operation, pattern) for pattern in self.operations
        )
        if len(self._match_cache) >= _MATCH_CACHE_MAX_SIZE:
            self._match_cache.clear()
        self._match_cache[operation] = matched
        return matched

    def _matches_message_type(self, attributes: dict[str, Any]) -> bool:
        if not self.message_types:
            return True
        msg_type = attributes.get("message_type")
        if msg_type is None:
            return True
        return msg_type in self.message_types

    def clear_cache(self) -> None:
        """Clear the match cache."""
        self._match_cache.clear()


class HookRegistry:
    """Registry for multiple instrumentation hooks with filtering."""

    def __init__(self) -> None:
        self._registrations: list[HookRegistration] = []

    def register(
        self,
        hook: InstrumentationHook,
        *,
        priority: int = 0,
        predicate: Callable[[str, dict[str, Any]], bool] | None = None,
        operations: list[str] | None = None,
        message_types: list[type[Any]] | None = None,
        enabled: bool = True,
    ) -> HookRegistration:
        """Register a hook with optional filtering."""
        registration = HookRegistration(
            hook=hook,
            priority=priority,
            predicate=predicate,
            operations=operations,
            message_types=message_types,
            enabled=enabled,
        )
        self._registrations.append(registration)
        self._registrations.sort(key=lambda r: r.priority)
        return registration

    async def execute_all(
        self,
        operation: str,
        attributes: dict[str, Any],
        next_handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Execute all matching hooks in priority order."""
        matching = [r for r in self._registrations if r.matches(operation, attributes)]
        if not matching:
            return await next_handler()

        async def pipeline(index: int = 0) -> Any:
            if index >= len(matching):
                return await next_handler()
            registration = matching[index]
            return await registration.hook(
                operation,
                attributes,
                lambda: pipeline(index + 1),
            )

        return await pipeline()

    def clear(self) -> None:
        """Remove all registrations and clear caches."""
        for registration in self._registrations:
            registration.clear_cache()
        self._registrations.clear()

    def clear_caches(self) -> None:
        """Clear all match caches without removing registrations."""
        for registration in self._registrations:
            registration.clear_cache()


_hook_registry_var: ContextVar[HookRegistry | None] = ContextVar(
    "hook_registry", default=None
)


def get_hook_registry() -> HookRegistry:
    """Get the hook registry for the current context.

    Creates a fresh ``HookRegistry`` on first access within each context,
    providing automatic test isolation without leaking state across async
    tasks or test boundaries.
    """
    registry = _hook_registry_var.get()
    if registry is None:
        registry = HookRegistry()
        _hook_registry_var.set(registry)
    return registry


def set_hook_registry(registry: HookRegistry) -> None:
    """Set a custom hook registry in the current context."""
    _hook_registry_var.set(registry)


def set_instrumentation_hook(hook: InstrumentationHook) -> None:
    """Register a single hook (backward compatibility)."""
    registry = get_hook_registry()
    registry.clear()
    registry.register(hook, priority=0, operations=["*"])


def get_instrumentation_hook() -> InstrumentationHook:
    """Get first registered hook (backward compatibility)."""
    registry = get_hook_registry()
    if registry._registrations:
        return registry._registrations[0].hook

    class NoOpHook:
        async def __call__(
            self,
            _operation: str,
            _attributes: dict[str, Any],
            next_handler: Callable[[], Awaitable[Any]],
        ) -> Any:
            return await next_handler()

    return cast("InstrumentationHook", NoOpHook())


def _on_fire_and_forget_done(task: asyncio.Task[Any]) -> None:
    """Callback for fire-and-forget hook tasks.

    Logs exceptions instead of swallowing them.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("Fire-and-forget hook task failed: %s", exc, exc_info=exc)


def fire_and_forget_hook(
    registry: HookRegistry,
    operation: str,
    attributes: dict[str, Any],
) -> None:
    """Schedule a no-op hook execution as a fire-and-forget task.

    Safe to call from synchronous code inside a running event loop.
    Logs errors instead of swallowing them silently.
    Does nothing if there is no running event loop.
    """
    if not registry._registrations:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _no_op() -> None:
        return None

    task = loop.create_task(registry.execute_all(operation, attributes, _no_op))
    task.add_done_callback(_on_fire_and_forget_done)
