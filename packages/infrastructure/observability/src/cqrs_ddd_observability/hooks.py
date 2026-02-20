"""Connect observability to framework instrumentation hooks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Balanced defaults for high-throughput systems:
# prioritize command/event lifecycle boundaries and recovery/worker control-plane
# operations while avoiding very chatty per-handler/cache/checkpoint spans.
DEFAULT_FRAMEWORK_TRACE_OPERATIONS: list[str] = [
    # Core lifecycle
    "uow.*",
    "event.dispatch.*",
    "publisher.publish.*",
    "consumer.consume.*",
    "outbox.process_batch",
    "outbox.retry_failed",
    "outbox.save_events",
    # Advanced orchestration/recovery
    "saga.run.*",
    "saga.recovery.*",
    "scheduler.dispatch.batch",
    "scheduler.worker.process",
    "event_sourcing.mediator.*",
    "persistence_orchestrator.orchestrate",
    # Projection/replay control-plane
    "projection.process.*",
    "replay.start.*",
    # Distributed lock boundaries
    "lock.acquire.*",
    "redis.lock.acquire.*",
    "redis.lock.release.*",
]


class ObservabilityInstrumentationHook:
    """Implements InstrumentationHook protocol with tracing attributes."""

    async def __call__(
        self,
        operation: str,
        attributes: dict[str, Any],
        next_handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        try:
            trace_api = cast(
                "Any", __import__("opentelemetry.trace", fromlist=["trace"])
            )

            tracer = trace_api.get_tracer("cqrs-ddd-framework")
            with tracer.start_as_current_span(operation) as span:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))
                try:
                    result = await next_handler()
                    span.set_attribute("outcome", "success")
                    return result
                except Exception as exc:  # noqa: BLE001
                    span.set_attribute("outcome", "error")
                    span.record_exception(exc)
                    raise
        except ImportError:
            return await next_handler()


def install_framework_hooks(
    *,
    operations: list[str] | None = None,
    priority: int = -100,
    enabled: bool = True,
) -> None:
    """Install observability instrumentation hook into core hook registry."""
    try:
        from cqrs_ddd_core.instrumentation import get_hook_registry

        registry = get_hook_registry()
        registration = registry.register(
            ObservabilityInstrumentationHook(),
            priority=priority,
            operations=operations or DEFAULT_FRAMEWORK_TRACE_OPERATIONS,
            enabled=enabled,
        )
        logger.info("Observability hooks installed")
        logger.debug("Observability registration id=%s", id(registration))
    except ImportError:
        logger.warning("cqrs-ddd-core not found, skipping framework hook install")
