# cqrs-ddd-observability

Observability infrastructure for the CQRS-DDD Toolkit — tracing, metrics, structured logging, error capture, and framework-wide instrumentation hooks.

## Installation

```bash
pip install cqrs-ddd-observability
```

Optional extras for specific backends:

```bash
# OpenTelemetry tracing
pip install cqrs-ddd-observability[opentelemetry]

# Prometheus metrics
pip install cqrs-ddd-observability[prometheus]

# Sentry error tracking
pip install cqrs-ddd-observability[sentry]
```

---

## Architecture Overview

The observability system is built on three layers:

```
┌─────────────────────────────────────────────────────────────┐
│                  cqrs-ddd-observability                      │
│  TracingMiddleware · MetricsMiddleware · SentryMiddleware    │
│  StructuredLoggingMiddleware · ObservabilityInstrumentationHook  │
└────────────────────────────┬────────────────────────────────┘
                             │ depends on
┌────────────────────────────▼────────────────────────────────┐
│                      cqrs-ddd-core                          │
│  HookRegistry · InstrumentationHook (protocol)              │
│  CorrelationIdPropagator · ContextVar-based correlation IDs │
└─────────────────────────────────────────────────────────────┘
```

1. **Core Instrumentation Hooks** (`cqrs-ddd-core`) — A protocol-based hook registry embedded in every major framework component. Pure Python, zero dependencies.
2. **Correlation IDs** (`cqrs-ddd-core`) — `ContextVar`-based correlation and causation ID propagation across async boundaries.
3. **Observability Package** (`cqrs-ddd-observability`) — Concrete middleware and hook implementations that connect to OpenTelemetry, Prometheus, and Sentry.

---

## Quick Start

### 1. Install Framework Hooks (Automatic Tracing)

The simplest way to get observability across the entire framework — one call at startup:

```python
from cqrs_ddd_observability import install_framework_hooks

# Installs a production-oriented default trace profile
install_framework_hooks()
```

This registers an `ObservabilityInstrumentationHook` into the core `HookRegistry` using a curated default operation set optimized for high-throughput systems (lifecycle boundaries and orchestration control-plane). It intentionally avoids very chatty operation families by default.

Use `operations=["*"]` only for short diagnostics sessions.

Default profile includes:
- `uow.*`
- `event.dispatch.*`
- `publisher.publish.*`
- `consumer.consume.*`
- `outbox.process_batch`, `outbox.retry_failed`, `outbox.save_events`
- `saga.run.*`, `saga.recovery.*`
- `scheduler.dispatch.batch`, `scheduler.worker.process`
- `event_sourcing.mediator.*`, `persistence_orchestrator.orchestrate`
- `projection.process.*`, `replay.start.*`
- `lock.acquire.*`, `redis.lock.acquire.*`, `redis.lock.release.*`

If you want full framework tracing for debugging:

```python
install_framework_hooks(operations=["*"])
```

### 2. Add Middleware to the Mediator Pipeline

For per-command/query observability, add middleware to your Mediator:

```python
from cqrs_ddd_core import Mediator, CorrelationIdPropagator
from cqrs_ddd_observability import (
    TracingMiddleware,
    PayloadTracingMiddleware,
    MetricsMiddleware,
    StructuredLoggingMiddleware,
    SentryMiddleware,
)

mediator = Mediator(
    handler_registry=registry,
    middlewares=[
        CorrelationIdPropagator(),   # Propagate correlation IDs (core)
        TracingMiddleware(),          # OpenTelemetry spans per command/query
        PayloadTracingMiddleware(),   # Sanitized payload events (allowlist/redact/hash)
        MetricsMiddleware(),          # Prometheus counters and histograms
        StructuredLoggingMiddleware(),# JSON log entries with context
        SentryMiddleware(),           # Capture exceptions to Sentry
    ],
)
```

### 3. Set Up Correlation IDs

Correlation IDs flow automatically through `ContextVar`. Set them at the entry point (e.g., HTTP middleware):

```python
from cqrs_ddd_core import set_correlation_id, generate_correlation_id

# At the start of each request
set_correlation_id(generate_correlation_id())

# All downstream operations (mediator, events, sagas, outbox, etc.)
# automatically include the correlation_id in hook attributes and logs.
```

---

## Core Instrumentation Hooks

The hook system lives in `cqrs-ddd-core` and is the foundation for all framework observability.

### How It Works

Every major framework component is instrumented with calls to the `HookRegistry`. When an operation executes, the registry runs all matching hooks in a pipeline (similar to middleware), wrapping the actual operation:

```
Hook A → Hook B → Hook C → actual operation → result flows back
```

Hooks see the operation name, attributes dict, and a `next_handler` callable. They can add tracing spans, record metrics, enforce rate limits, log audit events, or any cross-cutting concern.

### The InstrumentationHook Protocol

```python
from cqrs_ddd_core import InstrumentationHook

class MyCustomHook:
    """Any class matching this protocol works as a hook."""

    async def __call__(
        self,
        operation: str,           # e.g. "event.dispatch.OrderCreated"
        attributes: dict[str, Any],  # context: event type, correlation_id, etc.
        next_handler,             # call this to continue the pipeline
    ) -> Any:
        # Before the operation
        print(f"Starting: {operation}")
        try:
            result = await next_handler()
            # After success
            print(f"Completed: {operation}")
            return result
        except Exception:
            # After failure
            print(f"Failed: {operation}")
            raise
```

### Registering Hooks

```python
from cqrs_ddd_core import get_hook_registry

registry = get_hook_registry()

# Register a hook for all operations
registry.register(MyCustomHook(), operations=["*"])

# Register only for event-related operations
registry.register(
    MyEventAuditHook(),
    operations=["event.*"],       # Wildcard matching (fnmatch)
    priority=-10,                  # Lower = runs first (outer in pipeline)
)

# Register with a runtime predicate
registry.register(
    SlowQueryLogger(),
    predicate=lambda op, attrs: attrs.get("duration_ms", 0) > 100,
)

# Register for specific message types only
from myapp.domain.events import OrderCreated, OrderShipped

registry.register(
    OrderAuditHook(),
    message_types=[OrderCreated, OrderShipped],
)

# Disable a hook at runtime
registration = registry.register(MyHook(), operations=["*"])
registration.enabled = False  # Temporarily disable
```

### Instrumented Operations

Every instrumented component emits a named operation. Operations follow a dot-separated naming convention:

#### Core Package

| Component | Operation Pattern | Attributes |
|:----------|:-----------------|:-----------|
| `EventDispatcher` | `event.dispatch.{EventType}` | event.type, event.id, correlation_id |
| `EventDispatcher` (per handler) | `event.handler.{EventType}.{HandlerType}` | handler.type, event.type, event.id |
| `TopicRoutingPublisher` | `publisher.publish.{topic}` | topic, correlation_id |
| `BaseEventConsumer` | `consumer.consume.{EventType}` | event.type, correlation_id |
| `OutboxService` | `outbox.process_batch` | outbox.batch_size, correlation_id |
| `OutboxService` | `outbox.retry_failed` | outbox.retry.batch_size, correlation_id |
| `BufferedOutbox` | `outbox.buffered.publish` | topic, correlation_id |
| `OutboxMiddleware` | `outbox.save_events` | outbox.event_count, correlation_id |
| `UnitOfWork` | `uow.commit` / `uow.rollback` | outcome, correlation_id |
| `CriticalSection` | `lock.acquire.{resource_type}` | resource, resource_type, resource_id |
| `InMemoryEventStore` | `event_store.append.{aggregate_type}` | aggregate_type, aggregate_id |
| `MessageRegistry` | `message_registry.register` | message_type, name, class_name |
| `enrich_event_metadata` | `event.enrich_metadata` | event.type, event.id, correlation_id |

#### Advanced Package

| Component | Operation Pattern | Attributes |
|:----------|:-----------------|:-----------|
| `SagaManager` | `saga.handle_event.{EventType}` | event.type, correlation_id |
| `SagaManager` | `saga.run.{SagaType}` | saga.type, event.type |
| `SagaManager` | `saga.recovery.pending` | correlation_id |
| `SagaManager` | `saga.recovery.timeouts` | correlation_id |
| `SagaManager` | `saga.recovery.tcc_timeouts` | correlation_id |
| `SagaRecoveryWorker` | `saga.recovery.run_once` | correlation_id |
| `BackgroundJobService` | `job.enqueue.{JobType}` | job.type, correlation_id |
| `BackgroundJobService` | `job.sweep.stale` | correlation_id |
| `JobSweeperWorker` | `job.sweep.worker` | correlation_id |
| `EventSourcedRepository` | `event_sourcing.load.{AggregateType}` | aggregate.type, aggregate.id |
| `EventSourcedRepository` | `event_sourcing.persist.{AggregateType}` | aggregate.type, aggregate.id |
| `EventSourcedMediator` | `event_sourcing.mediator.{CommandType}` | command.type, correlation_id |
| `PersistenceDispatcher` | `persistence.apply.{EntityType}` | entity.type, correlation_id |
| `PersistenceDispatcher` | `persistence.fetch.{EntityType}` | entity.type, correlation_id |
| `PersistenceDispatcher` | `persistence.query.{ResultType}` | result.type, correlation_id |
| `PersistenceOrchestrator` | `persistence_orchestrator.orchestrate` | aggregate.type, correlation_id |
| `CommandSchedulerService` | `scheduler.dispatch.batch` | correlation_id |
| `CommandSchedulerService` | `scheduler.dispatch.{CommandType}` | command.type, correlation_id |
| `CommandSchedulerWorker` | `scheduler.worker.process` | correlation_id |
| `PipelinedCommandHandler` | `handler.pipeline.stage.{CommandType}` | handler.type, command.type |
| `RetryBehaviorMixin` | `handler.retry.{HandlerType}` | handler.type, attempt, max_retries |
| `ConflictResolver` | `conflict.resolve.{StrategyType}` | strategy.type, correlation_id |
| `ConflictResolver` | `merge_strategy.apply.{StrategyType}` | strategy.type, correlation_id |
| `DefaultEventApplicator` | `event_applicator.apply.{EventType}` | event.type, aggregate.type |
| `EventSourcedLoader` | `snapshot.create.{AggregateType}` | aggregate.type, aggregate.id, version |
| `UpcasterChain` | `upcast.apply.{EventType}` | event.type, schema.from, schema.to |
| `UpcastingEventReader` | `upcast.apply.get_events` | correlation_id |
| `UpcastingEventReader` | `upcast.apply.get_by_aggregate` | aggregate_id, correlation_id |
| `UndoService` | `undo.execute.{EventType}` | event.type, aggregate.id |

#### Projections Engine

| Component | Operation Pattern | Attributes |
|:----------|:-----------------|:-----------|
| `ProjectionWorker` | `projection.process.{name}` | projection_name, event.type |
| `PartitionedProjectionWorker` | `projection.partition.{index}` | partition_index |
| `EventSinkRunner` | `projection_sink.write.{name}` | projection_name, event.type |
| `InMemoryCheckpointStore` | `checkpoint.save.{name}` | projection_name, position |
| `ReplayEngine` | `replay.start.{name}` | projection_name |

#### Redis Infrastructure

| Component | Operation Pattern | Attributes |
|:----------|:-----------------|:-----------|
| `RedlockLockStrategy` | `redis.lock.acquire.{resource_type}` | resource, timeout, ttl |
| `RedlockLockStrategy` | `redis.lock.release.{resource_type}` | resource |
| `FifoRedisLockStrategy` | `redis.lock.acquire.{resource_type}` | resource, timeout, ttl |
| `FifoRedisLockStrategy` | `redis.lock.release.{resource_type}` | resource |
| `RedisCacheService` | `redis.cache.get` / `redis.cache.set` | cache.key |
| `RedisCheckpointStore` | `redis.checkpoint.save.{name}` | projection_name, position |

### Filtering with Wildcards

Operation patterns use Python's `fnmatch` module for matching:

```python
# Match all event-related operations
registry.register(hook, operations=["event.*"])

# Match all saga operations
registry.register(hook, operations=["saga.*"])

# Match specific patterns
registry.register(hook, operations=["*.commit", "*.rollback"])

# Match everything (diagnostics mode; not the default)
registry.register(hook, operations=["*"])
```

### Fire-and-Forget Hooks

Some components (e.g., `MessageRegistry.register_command()`, `ConflictResolver.merge()`) are synchronous but still emit hook notifications. These use fire-and-forget tasks that log errors instead of silently swallowing them:

```python
from cqrs_ddd_core.instrumentation import fire_and_forget_hook, get_hook_registry

# Safe to call from sync code inside a running event loop
fire_and_forget_hook(
    get_hook_registry(),
    "my_operation.name",
    {"key": "value"},
)
```

---

## Middleware Reference

### TracingMiddleware

Creates an OpenTelemetry span per command/query dispatch. Records command type, correlation ID, and outcome (success/error).

```python
from cqrs_ddd_observability import TracingMiddleware

# Requires: pip install cqrs-ddd-observability[opentelemetry]
tracing = TracingMiddleware()
```

Span attributes:
- `cqrs.command_type` — The message class name
- `cqrs.correlation_id` — Correlation ID from context or message
- `cqrs.outcome` — `"success"` or `"error"`

### PayloadTracingMiddleware

Adds **sanitized** command/query payloads into the **current active OpenTelemetry span** as span events.

```python
from cqrs_ddd_observability import PayloadTracingMiddleware

payload_tracing = PayloadTracingMiddleware(
    # keep only explicitly allowed fields (recommended)
    include_fields={"order_id", "tenant_id", "item_count"},
    # always redact these fields
    redact_fields={"email", "phone", "address"},
    # hash these fields for correlation without exposing raw values
    hash_fields={"customer_id"},
    # payload event safety guard
    max_payload_chars=4096,
)
```

What it emits:
- Span event `cqrs.command_payload` with JSON payload (`payload` attribute)
- Span attributes:
  - `cqrs.payload_present`
  - `cqrs.payload_truncated`
  - `cqrs.payload_size`

Security defaults:
- Known sensitive keys are redacted by default (e.g. `password`, `token`, `email`, `card_number`)
- `hash_fields` are stored as `sha256:<digest>`
- Middleware never raises on serialization/sanitization failures (non-blocking)
- It does **not** create its own span (avoids duplicate/nested spans)

> Recommendation: use an **allowlist** (`include_fields`) in production instead of relying only on redaction.
> Place `TracingMiddleware()` before `PayloadTracingMiddleware()` so an active span exists.

### MetricsMiddleware

Records Prometheus histograms and counters per message type.

```python
from cqrs_ddd_observability import MetricsMiddleware

# Requires: pip install cqrs-ddd-observability[prometheus]
metrics = MetricsMiddleware()
```

Exposed metrics:
- `cqrs_message_duration_seconds` — Histogram with labels `kind`, `message_type`, `outcome`
- `cqrs_message_total` — Counter with labels `kind`, `message_type`, `outcome`

The `kind` label is `"command"`, `"query"`, or `"message"` (fallback), allowing you to slice dashboards by message kind.

### StructuredLoggingMiddleware

Emits JSON log entries with correlation context, duration, and outcome.

```python
from cqrs_ddd_observability import StructuredLoggingMiddleware

logging_mw = StructuredLoggingMiddleware()

# Or with a custom logger
import logging
logging_mw = StructuredLoggingMiddleware(logger=logging.getLogger("my_app.cqrs"))
```

Log entry format:
```json
{
    "kind": "command",
    "message_type": "CreateOrderCommand",
    "outcome": "success",
    "duration_ms": 12.34,
    "correlation_id": "a1b2c3d4-..."
}
```

### SentryMiddleware

Captures unhandled exceptions to Sentry with correlation context.

```python
from cqrs_ddd_observability import SentryMiddleware

# Requires: pip install cqrs-ddd-observability[sentry]
# Also requires sentry_sdk.init(...) at application startup
sentry = SentryMiddleware()
```

Tags set on Sentry scope:
- `cqrs.message_type` — The command/query class name
- `correlation_id` — Current correlation ID

---

## Correlation ID Propagation

Correlation IDs are managed via Python's `ContextVar`, ensuring they propagate across `async`/`await` boundaries automatically.

### Setting and Getting

```python
from cqrs_ddd_core import (
    set_correlation_id,
    get_correlation_id,
    generate_correlation_id,
    set_causation_id,
    get_causation_id,
)

# Generate and set at request entry point
correlation_id = generate_correlation_id()
set_correlation_id(correlation_id)

# Read anywhere downstream
current_id = get_correlation_id()  # Returns the same UUID

# Set causation chain (event → command tracing)
set_causation_id("parent-event-id")
```

### Propagating to Background Tasks

When spawning background tasks, capture and restore the context:

```python
from cqrs_ddd_core import get_context_vars, set_context_vars

# Capture before spawning
ctx = get_context_vars()
# Returns: {"correlation_id": "...", "causation_id": "..."}

async def background_task():
    set_context_vars(**ctx)  # Restore in new task
    await do_work()

asyncio.create_task(background_task())
```

### Automatic Propagation via Middleware

The `CorrelationIdPropagator` middleware automatically:
1. Injects the current correlation ID into outgoing messages
2. Extracts correlation IDs from incoming messages
3. Sets causation IDs from event IDs (for event → command chains)

```python
from cqrs_ddd_core import CorrelationIdPropagator

mediator = Mediator(
    handler_registry=registry,
    middlewares=[
        CorrelationIdPropagator(),  # Should be first in the pipeline
        # ... other middleware
    ],
)
```

---

## ObservabilityContext

The `ObservabilityContext` provides access to trace-level context (trace ID, span ID) alongside correlation IDs:

```python
from cqrs_ddd_observability import ObservabilityContext

# Get correlation ID (delegates to core)
cid = ObservabilityContext.get_correlation_id()

# Get OpenTelemetry trace/span IDs (if set)
trace_id = ObservabilityContext.get_trace_id()
span_id = ObservabilityContext.get_span_id()

# Set additional context
ObservabilityContext.set(trace_id="abc123", custom_field="value")
```

---

## Advanced: Custom Hook Examples

### Audit Trail Hook

```python
from cqrs_ddd_core import get_hook_registry

class AuditTrailHook:
    def __init__(self, audit_store):
        self._store = audit_store

    async def __call__(self, operation, attributes, next_handler):
        result = await next_handler()
        if operation.startswith("persistence.apply."):
            await self._store.record(
                operation=operation,
                entity_type=attributes.get("entity.type"),
                correlation_id=attributes.get("correlation_id"),
            )
        return result

registry = get_hook_registry()
registry.register(
    AuditTrailHook(my_audit_store),
    operations=["persistence.apply.*"],
    priority=100,  # Run after other hooks
)
```

### Rate Limiting Hook

```python
class RateLimitHook:
    def __init__(self, max_per_second: int = 100):
        self._limiter = TokenBucketLimiter(max_per_second)

    async def __call__(self, operation, attributes, next_handler):
        if not self._limiter.allow():
            raise RateLimitExceeded(operation)
        return await next_handler()

registry.register(
    RateLimitHook(max_per_second=50),
    operations=["publisher.publish.*"],
)
```

### Timing/Slow Operation Detector

```python
import time

class SlowOperationHook:
    def __init__(self, threshold_ms: float = 500):
        self._threshold = threshold_ms

    async def __call__(self, operation, attributes, next_handler):
        start = time.monotonic()
        try:
            return await next_handler()
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            if duration_ms > self._threshold:
                logger.warning(
                    "Slow operation: %s took %.1fms", operation, duration_ms
                )

registry.register(SlowOperationHook(threshold_ms=200), operations=["*"])
```

---

## Full Integration Example

```python
import asyncio
from cqrs_ddd_core import (
    Mediator,
    HandlerRegistry,
    CorrelationIdPropagator,
    set_correlation_id,
    generate_correlation_id,
    get_hook_registry,
)
from cqrs_ddd_observability import (
    install_framework_hooks,
    TracingMiddleware,
    PayloadTracingMiddleware,
    MetricsMiddleware,
    StructuredLoggingMiddleware,
    SentryMiddleware,
)

# 1. Install framework-wide hooks (production-oriented default profile)
install_framework_hooks()

# 2. Build the mediator with middleware
handler_registry = HandlerRegistry()
# ... register handlers ...

mediator = Mediator(
    handler_registry=handler_registry,
    middlewares=[
        CorrelationIdPropagator(),
        TracingMiddleware(),
        PayloadTracingMiddleware(),
        MetricsMiddleware(),
        StructuredLoggingMiddleware(),
        SentryMiddleware(),
    ],
)

# 3. At request time
async def handle_request(request):
    set_correlation_id(generate_correlation_id())
    result = await mediator.send(CreateOrderCommand(order_id="123"))
    return result
```

---

## API Reference

| Symbol | Module | Description |
|:-------|:-------|:------------|
| `install_framework_hooks()` | `cqrs_ddd_observability` | One-call setup for OTel tracing using production-oriented default operations |
| `DEFAULT_FRAMEWORK_TRACE_OPERATIONS` | `cqrs_ddd_observability` | Default high-throughput operation allowlist used by `install_framework_hooks()` |
| `ObservabilityInstrumentationHook` | `cqrs_ddd_observability` | The hook implementation that creates OTel spans |
| `TracingMiddleware` | `cqrs_ddd_observability` | Per-command/query OTel span middleware |
| `PayloadTracingMiddleware` | `cqrs_ddd_observability` | Sanitized payload span-event middleware (allowlist/redact/hash) |
| `MetricsMiddleware` | `cqrs_ddd_observability` | Prometheus histogram/counter middleware |
| `StructuredLoggingMiddleware` | `cqrs_ddd_observability` | JSON structured logging middleware |
| `SentryMiddleware` | `cqrs_ddd_observability` | Sentry exception capture middleware |
| `ObservabilityContext` | `cqrs_ddd_observability` | ContextVar storage for trace/span IDs |
| `ObservabilityError` | `cqrs_ddd_observability` | Base exception (never blocks commands) |
| `HookRegistry` | `cqrs_ddd_core` | Central registry for instrumentation hooks (ContextVar-backed) |
| `InstrumentationHook` | `cqrs_ddd_core` | Protocol that hooks must satisfy |
| `HookRegistration` | `cqrs_ddd_core` | Registration handle with filtering config |
| `get_hook_registry()` | `cqrs_ddd_core` | Get the hook registry for the current context |
| `set_hook_registry()` | `cqrs_ddd_core` | Replace the hook registry in the current context |
| `fire_and_forget_hook()` | `cqrs_ddd_core` | Safe fire-and-forget hook from sync code |
| `CorrelationIdPropagator` | `cqrs_ddd_core` | Middleware for correlation ID propagation |
| `get_correlation_id()` | `cqrs_ddd_core` | Get current correlation ID from ContextVar |
| `set_correlation_id()` | `cqrs_ddd_core` | Set correlation ID in ContextVar |
| `generate_correlation_id()` | `cqrs_ddd_core` | Generate a new UUID4 correlation ID |
| `get_causation_id()` | `cqrs_ddd_core` | Get current causation ID |
| `set_causation_id()` | `cqrs_ddd_core` | Set causation ID |
| `get_context_vars()` | `cqrs_ddd_core` | Snapshot all correlation vars for task spawning |
| `set_context_vars()` | `cqrs_ddd_core` | Restore correlation vars in a new task |

---

## Infrastructure Integration Guide

This section covers end-to-end setup for a fully open-source observability stack:

- **Jaeger** — distributed trace storage and UI
- **Prometheus** — metrics scraping and storage
- **Grafana Loki** — log aggregation (structured JSON logs)
- **Grafana** — unified dashboards for traces, metrics, and logs
- **OpenTelemetry Collector** — optional centralized telemetry pipeline

### Quick Start (docker-compose)

Save the following as `docker-compose.observability.yml` next to your application:

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"   # Jaeger UI
      - "4317:4317"     # OTLP gRPC
      - "4318:4318"     # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    depends_on:
      - prometheus
      - loki
      - jaeger
```

Create `prometheus.yml` in the same directory:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: cqrs-ddd-app
    static_configs:
      - targets: ["host.docker.internal:9000"]
```

Start everything:

```bash
docker compose -f docker-compose.observability.yml up -d
```

| Service | URL |
|:--------|:----|
| Jaeger UI | http://localhost:16686 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Loki | http://localhost:3100 |

---

### Step 1: Traces — OpenTelemetry SDK + Jaeger

Install the SDK and OTLP exporter:

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp
```

Configure at application startup (**once**, before any middleware runs):

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)

resource = Resource.create({"service.name": "cqrs-ddd-app"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint="http://localhost:4317",
            insecure=True,
        )
    )
)
trace.set_tracer_provider(provider)
```

Then wire the middleware and hooks:

```python
from cqrs_ddd_observability import (
    install_framework_hooks,
    TracingMiddleware,
    PayloadTracingMiddleware,
)

install_framework_hooks()

mediator = Mediator(
    handler_registry=registry,
    middlewares=[
        CorrelationIdPropagator(),
        TracingMiddleware(),
        PayloadTracingMiddleware(include_fields={"order_id", "tenant_id"}),
        # ...
    ],
)
```

**Verify:** Run a command, open Jaeger UI at http://localhost:16686, select service `cqrs-ddd-app`, and search. You should see spans like `cqrs.CreateOrderCommand` with child spans from instrumentation hooks.

#### Production: sampling

For high-throughput systems, configure a sampler to avoid exporting every trace:

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

provider = TracerProvider(
    resource=resource,
    sampler=TraceIdRatioBased(0.05),  # 5% of traces
)
```

---

### Step 2: Metrics — Prometheus + MetricsMiddleware

Install the Prometheus client:

```bash
pip install prometheus-client
```

Expose the `/metrics` endpoint at app startup:

```python
from prometheus_client import start_http_server

start_http_server(9000)  # Prometheus scrapes this
```

Add `MetricsMiddleware` to the pipeline:

```python
from cqrs_ddd_observability import MetricsMiddleware

mediator = Mediator(
    handler_registry=registry,
    middlewares=[
        CorrelationIdPropagator(),
        TracingMiddleware(),
        MetricsMiddleware(),
        # ...
    ],
)
```

**Verify:** Open http://localhost:9090, query `cqrs_message_duration_seconds_bucket` or `cqrs_message_total`. You should see per-message-type latency and throughput data.

#### Useful PromQL queries

```promql
# P99 command latency by type
histogram_quantile(0.99,
  rate(cqrs_message_duration_seconds_bucket{kind="command"}[5m])
)

# P99 query latency by type
histogram_quantile(0.99,
  rate(cqrs_message_duration_seconds_bucket{kind="query"}[5m])
)

# Command error rate
sum(rate(cqrs_message_total{kind="command",outcome="error"}[5m]))
/ sum(rate(cqrs_message_total{kind="command"}[5m]))

# All messages per second by kind
sum by (kind) (rate(cqrs_message_total[1m]))

# Commands per second by type
sum by (message_type) (
  rate(cqrs_message_total{kind="command"}[1m])
)
```

---

### Step 3: Structured Logging — Loki + StructuredLoggingMiddleware

`StructuredLoggingMiddleware` emits JSON log entries with `kind`, `correlation_id`, `message_type`, `outcome`, and `duration_ms`. To get these into Loki for Grafana querying you have several options, each suited to a different deployment model.

#### Loki vs systemd journal: when to use which

**systemd journal** and **Grafana Loki** are complementary, not competing:

| Concern | systemd journal | Loki |
|:--------|:----------------|:-----|
| Role | Local OS-level log transport and short-term storage | Centralized multi-service log aggregation and long-term querying |
| Scope | Single host | Entire fleet / cluster |
| Query | `journalctl` on the host | LogQL from Grafana (any browser) |
| Retention | Configured per host (default: rotate on disk usage) | Configured centrally (object storage, weeks/months) |
| Correlation | Manual (grep by ID) | Native label-based filtering + Grafana linking to traces |

**Recommendation:** Use both. Journal is always there as the OS transport. Ship logs from journal (or stdout) → Loki so they become queryable, correlatable, and alertable from Grafana.

#### Option A: journal → Promtail → Loki (bare-metal / VM)

On hosts running systemd, Promtail can read directly from the journal. This is the cleanest path for non-containerized deployments — your application writes to stdout/stderr (captured by systemd as a service unit), and Promtail ships everything to Loki:

```yaml
# promtail-config.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Ship all journal entries for your service unit
  - job_name: journal
    journal:
      labels:
        job: systemd-journal
      path: /var/log/journal
    relabel_configs:
      - source_labels: ["__journal__systemd_unit"]
        target_label: unit
    pipeline_stages:
      - match:
          selector: '{unit="cqrs-ddd-app.service"}'
          stages:
            - json:
                expressions:
                  kind: kind
                  correlation_id: correlation_id
                  message_type: message_type
                  outcome: outcome
            - labels:
                kind:
                correlation_id:
                message_type:
                outcome:
```

Your application runs as a systemd service that writes JSON to stdout:

```ini
# /etc/systemd/system/cqrs-ddd-app.service
[Unit]
Description=CQRS DDD Application
After=network.target

[Service]
ExecStart=/opt/cqrs-ddd/.venv/bin/python -m cqrs_ddd_app
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cqrs-ddd-app

[Install]
WantedBy=multi-user.target
```

With this setup you get:
- **Local access:** `journalctl -u cqrs-ddd-app.service -f` for live tailing
- **Centralized access:** Grafana → Loki for cross-service querying

#### Option B: stdout → Promtail → Loki (containers / Kubernetes)

In containerized deployments, applications write JSON to stdout. The container runtime captures logs to files, and Promtail (deployed as a DaemonSet in Kubernetes or sidecar in Docker) scrapes those files:

```yaml
# promtail-config.yml (container file scraping)
scrape_configs:
  - job_name: containers
    static_configs:
      - targets: [localhost]
        labels:
          job: cqrs-ddd-app
          __path__: /var/log/containers/*cqrs-ddd*.log
    pipeline_stages:
      - docker: {}
      - json:
          expressions:
            kind: kind
            correlation_id: correlation_id
            message_type: message_type
            outcome: outcome
      - labels:
          kind:
          correlation_id:
          message_type:
          outcome:
```

For Kubernetes, install Promtail via the Grafana Helm chart:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm install promtail grafana/promtail \
  --set "config.clients[0].url=http://loki:3100/loki/api/v1/push"
```

#### Option C: python-logging-loki (direct push, development)

For development or simple single-service setups, push logs directly from Python without a Promtail sidecar:

```bash
pip install python-logging-loki
```

```python
import logging
import logging_loki

loki_handler = logging_loki.LokiHandler(
    url="http://localhost:3100/loki/api/v1/push",
    tags={"application": "cqrs-ddd-app"},
    version="1",
)
logging.getLogger().addHandler(loki_handler)
```

This is convenient for local development but **not recommended for production** because it couples your process to Loki availability and adds network I/O to the logging hot path.

#### Verify

Open Grafana at http://localhost:3000, add Loki as a data source (`http://loki:3100`), then query:

```logql
{job="cqrs-ddd-app"} | json | outcome="error"
```

Filter by kind:

```logql
{job="cqrs-ddd-app"} | json | kind="command" | outcome="error"
```

Slow queries:

```logql
{job="cqrs-ddd-app"} | json | kind="query" | duration_ms > 500
```

#### Correlating logs with traces

Because `StructuredLoggingMiddleware` includes `correlation_id` in every log entry and `TracingMiddleware` sets the same `correlation_id` as a span attribute, Grafana can link from a log line to its trace:

1. In Grafana, configure Loki data source with a derived field:
   - **Name:** `TraceID`
   - **Regex:** `"correlation_id":\s*"([^"]+)"`
   - **Internal link:** Jaeger data source
2. Click a log line → jump directly to the correlated trace in Jaeger.

---

### Step 4: Grafana — Unified Dashboards

Add all three data sources in Grafana (http://localhost:3000 → Configuration → Data Sources):

| Data Source | Type | URL |
|:------------|:-----|:----|
| Jaeger | Jaeger | `http://jaeger:16686` |
| Prometheus | Prometheus | `http://prometheus:9090` |
| Loki | Loki | `http://loki:3100` |

#### Starter dashboard panels

**Command Throughput** (Prometheus):

```promql
sum by (message_type) (
  rate(cqrs_message_total{kind="command"}[5m])
)
```

**Query Throughput** (Prometheus):

```promql
sum by (message_type) (
  rate(cqrs_message_total{kind="query"}[5m])
)
```

**P95 Command Latency** (Prometheus):

```promql
histogram_quantile(0.95,
  sum by (le, message_type) (
    rate(cqrs_message_duration_seconds_bucket{kind="command"}[5m])
  )
)
```

**P95 Query Latency** (Prometheus):

```promql
histogram_quantile(0.95,
  sum by (le, message_type) (
    rate(cqrs_message_duration_seconds_bucket{kind="query"}[5m])
  )
)
```

**Error Rate % (all messages)** (Prometheus):

```promql
100 * sum(rate(cqrs_message_total{outcome="error"}[5m]))
/ sum(rate(cqrs_message_total[5m]))
```

**Error Rate % (commands only)** (Prometheus):

```promql
100 * sum(rate(cqrs_message_total{kind="command",outcome="error"}[5m]))
/ sum(rate(cqrs_message_total{kind="command"}[5m]))
```

**Recent Errors** (Loki):

```logql
{job="cqrs-ddd-app"} | json | outcome="error" | line_format "{{.kind}} {{.message_type}}: {{.duration_ms}}ms"
```

**Trace Search** (Jaeger): Service = `cqrs-ddd-app`, filter by `correlation_id` tag.

---

### Step 5 (Optional): OpenTelemetry Collector

For production, place an OTel Collector between your app and backends. It handles batching, retries, sampling, and fan-out:

```
App → OTel Collector → Jaeger (traces)
                     → Prometheus (metrics via remote write)
```

Collector config (`otel-collector.yml`):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger]
```

Add the collector to `docker-compose.observability.yml`:

```yaml
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4317:4317"
    volumes:
      - ./otel-collector.yml:/etc/otelcol-contrib/config.yaml
    depends_on:
      - jaeger
```

Then point your app's `OTLPSpanExporter` at `http://otel-collector:4317` instead of Jaeger directly.

---

### Summary: What Each Component Handles

| Signal | Emitted by | Collected by | Stored in | Viewed in |
|:-------|:-----------|:-------------|:----------|:----------|
| **Traces** | `TracingMiddleware`, `PayloadTracingMiddleware`, `install_framework_hooks()` | OTel SDK / OTel Collector | Jaeger | Jaeger UI / Grafana |
| **Metrics** | `MetricsMiddleware` (Prometheus client) | Prometheus scrape | Prometheus | Grafana |
| **Logs** | `StructuredLoggingMiddleware` (JSON) | Promtail / python-logging-loki | Loki | Grafana |
| **Health** | `HealthRegistry` (see `cqrs-ddd-health`) | HTTP endpoint scrape | N/A | Grafana / k8s probes |
