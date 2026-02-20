# cqrs-ddd-health

Health check registry and infrastructure probes for the CQRS-DDD Toolkit. Provides a unified way to monitor the health of databases, caches, message brokers, and background workers.

## Installation

```bash
pip install cqrs-ddd-health
```

Optional extras for specific infrastructure:

```bash
# SQLAlchemy database health checks
pip install cqrs-ddd-health[sqlalchemy]

# Redis health checks
pip install cqrs-ddd-health[redis]
```

---

## Quick Start

```python
from cqrs_ddd_health import HealthRegistry, DatabaseHealthCheck, RedisHealthCheck

# Get the singleton registry
health = HealthRegistry.get_instance()

# Register infrastructure checks
health.register("database", DatabaseHealthCheck(session_factory))
health.register("redis", RedisHealthCheck(redis_client))

# Run all checks
status = await health.check_all()
# {"database": "up", "redis": "up"}

# Full status report
report = await health.status()
# {
#     "status": "healthy",
#     "components": {"database": "up", "redis": "up"},
#     "timestamp": "2026-02-20T12:00:00+00:00",
#     "heartbeats": {}
# }
```

---

## Health Registry

The `HealthRegistry` is a singleton that aggregates health checks and worker heartbeats into a unified status report.

### Registration

Register any callable (sync or async) that returns a truthy value for healthy, falsy for unhealthy:

```python
from cqrs_ddd_health import HealthRegistry

health = HealthRegistry.get_instance()

# Register an async check
health.register("database", DatabaseHealthCheck(session_factory))

# Register a sync check (lambda, function, etc.)
health.register("disk_space", lambda: shutil.disk_usage("/").free > 1_000_000_000)

# Register a custom async check
async def check_external_api():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.example.com/health", timeout=5)
        return resp.status_code == 200

health.register("external_api", check_external_api)
```

### Running Checks

```python
# Run all registered checks, returns a dict of component → "up" / "down"
components = await health.check_all()
# {"database": "up", "redis": "down", "disk_space": "up"}

# Full status report with overall health and timestamps
report = await health.status()
# {
#     "status": "unhealthy",        # "healthy" only if ALL components are "up"
#     "components": {
#         "database": "up",
#         "redis": "down",
#         "disk_space": "up"
#     },
#     "timestamp": "2026-02-20T12:00:00+00:00",
#     "heartbeats": {
#         "outbox_worker": "2026-02-20T11:59:55+00:00",
#         "saga_recovery": "2026-02-20T11:59:50+00:00"
#     }
# }
```

### Worker Heartbeats

Background workers (outbox processor, saga recovery, job sweeper, etc.) can report heartbeats. Workers that miss the heartbeat timeout are reported as `"down"`:

```python
health = HealthRegistry.get_instance()

# In your worker's processing loop
class MyWorker:
    async def _process_cycle(self):
        health.heartbeat("my_worker")
        # ... do work ...
```

The heartbeat timeout is configurable:

```python
# Workers must heartbeat within 30 seconds (default: 60)
health = HealthRegistry(heartbeat_timeout_seconds=30)
```

Heartbeat status is automatically included in `check_all()` and `status()`:

```python
status = await health.check_all()
# {"database": "up", "my_worker": "up"}  # worker heartbeated recently

# If worker hasn't heartbeated within the timeout:
# {"database": "up", "my_worker": "down"}
```

---

## Built-in Health Checks

### DatabaseHealthCheck

Verifies database connectivity by executing `SELECT 1` through an async SQLAlchemy session.

```python
from cqrs_ddd_health import DatabaseHealthCheck

# session_factory should return an async context manager (e.g., async_sessionmaker)
db_check = DatabaseHealthCheck(session_factory)
health.register("database", db_check)
```

Requirements:
- `session_factory()` must return an async context manager
- The session must support `await session.execute("SELECT 1")`
- Install `cqrs-ddd-health[sqlalchemy]` for SQLAlchemy support

### RedisHealthCheck

Verifies Redis connectivity by calling `PING`.

```python
from cqrs_ddd_health import RedisHealthCheck

# redis_client should be an async Redis client (e.g., redis.asyncio.Redis)
redis_check = RedisHealthCheck(redis_client)
health.register("redis", redis_check)
```

Requirements:
- The client must support `await client.ping()`
- Install `cqrs-ddd-health[redis]` for Redis support

### MessageBrokerHealthCheck

Verifies message broker connectivity by calling:

1. `health_check()` if available (preferred), otherwise
2. `is_connected()` as a fallback.

```python
from cqrs_ddd_health import MessageBrokerHealthCheck

# broker_client should expose async health_check() (preferred)
# or async is_connected() (fallback)
broker_check = MessageBrokerHealthCheck(broker_client)
health.register("message_broker", broker_check)
```

---

## Writing Custom Health Checks

Any callable (sync or async) that returns a truthy/falsy value works:

```python
# Async class-based check
class ElasticsearchHealthCheck:
    def __init__(self, es_client):
        self._es = es_client

    async def __call__(self) -> bool:
        try:
            return await self._es.ping()
        except Exception:
            return False

health.register("elasticsearch", ElasticsearchHealthCheck(es_client))

# Simple function check
def check_temp_dir():
    import os
    return os.path.isdir("/tmp") and os.access("/tmp", os.W_OK)

health.register("temp_dir", check_temp_dir)
```

---

## Exposing as an HTTP Endpoint

### FastAPI

```python
from fastapi import FastAPI
from cqrs_ddd_health import HealthRegistry

app = FastAPI()

@app.get("/health")
async def health_check():
    report = await HealthRegistry.get_instance().status()
    status_code = 200 if report["status"] == "healthy" else 503
    return JSONResponse(content=report, status_code=status_code)

@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    components = await HealthRegistry.get_instance().check_all()
    ready = all(v == "up" for v in components.values())
    return JSONResponse(
        content={"ready": ready, "components": components},
        status_code=200 if ready else 503,
    )
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
```

---

## Integration with Observability

The health package works alongside `cqrs-ddd-observability`. A common pattern is to report health status in tracing spans:

```python
from cqrs_ddd_core import get_hook_registry
from cqrs_ddd_health import HealthRegistry

class HealthReportingHook:
    async def __call__(self, operation, attributes, next_handler):
        result = await next_handler()
        if operation == "scheduler.worker.process":
            HealthRegistry.get_instance().heartbeat("scheduler_worker")
        return result

get_hook_registry().register(
    HealthReportingHook(),
    operations=["*.worker.*"],
)
```

---

## API Reference

| Symbol | Description |
|:-------|:------------|
| `HealthRegistry` | Singleton registry for health checks and heartbeats |
| `HealthRegistry.get_instance()` | Get the singleton instance |
| `HealthRegistry.register(name, check)` | Register a health check callable |
| `HealthRegistry.heartbeat(worker_name)` | Record a worker heartbeat |
| `HealthRegistry.check_all()` | Run all checks, return `dict[str, str]` |
| `HealthRegistry.status()` | Full status report with timestamps |
| `DatabaseHealthCheck(session_factory)` | SQLAlchemy database connectivity check |
| `RedisHealthCheck(redis_client)` | Redis PING check |
| `MessageBrokerHealthCheck(broker_client)` | Broker `health_check()` (or fallback `is_connected()`) |

---

## Infrastructure Integration: Prometheus + Grafana

Health checks become most valuable when scraped, stored, and visualized. This section walks through integrating `cqrs-ddd-health` with Prometheus and Grafana using a fully open-source stack.

### Quick Start (docker-compose)

If you already have the observability stack from `cqrs-ddd-observability`, add the following. Otherwise, save this as `docker-compose.health.yml`:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    depends_on:
      - prometheus
```

```bash
docker compose -f docker-compose.health.yml up -d
```

| Service | URL |
|:--------|:----|
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

---

### Step 1: Expose Health as Prometheus Metrics

The health registry returns Python dictionaries. To make this scrapeable by Prometheus, translate the results into Prometheus gauges using `prometheus_client`:

```bash
pip install prometheus-client
```

```python
from prometheus_client import Gauge, start_http_server
from cqrs_ddd_health import HealthRegistry

health_gauge = Gauge(
    "cqrs_health_component_up",
    "Whether a health-checked component is up (1) or down (0)",
    ["component"],
)

heartbeat_age_gauge = Gauge(
    "cqrs_health_heartbeat_age_seconds",
    "Seconds since last worker heartbeat",
    ["worker"],
)


async def refresh_health_metrics() -> None:
    """Call periodically (e.g., every 15 s) or on each /metrics scrape."""
    registry = HealthRegistry.get_instance()
    components = await registry.check_all()
    for name, status in components.items():
        health_gauge.labels(component=name).set(1 if status == "up" else 0)

    report = await registry.status()
    now = datetime.datetime.now(datetime.UTC)
    for worker, last_ts in report.get("heartbeats", {}).items():
        if last_ts:
            age = (now - datetime.datetime.fromisoformat(last_ts)).total_seconds()
            heartbeat_age_gauge.labels(worker=worker).set(age)
```

Expose the metrics endpoint alongside your application:

```python
start_http_server(9000)  # Prometheus scrapes http://your-app:9000/metrics
```

Configure Prometheus to scrape it:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: cqrs-ddd-app
    static_configs:
      - targets: ["host.docker.internal:9000"]
```

**Verify:** Open http://localhost:9090 and query `cqrs_health_component_up`. You should see one time-series per registered component.

---

### Step 2: Health Dashboard in Grafana

Add Prometheus as a data source in Grafana (http://localhost:3000 → Configuration → Data Sources → Prometheus → URL: `http://prometheus:9090`).

#### Component Health Status Panel

Use a **Stat** or **Status history** panel:

```promql
cqrs_health_component_up
```

Map values: `1` → green "UP", `0` → red "DOWN". Group by `component` label.

#### Worker Heartbeat Freshness Panel

Use a **Gauge** or **Time series** panel:

```promql
cqrs_health_heartbeat_age_seconds
```

Set thresholds: green (< 30 s), yellow (30–60 s), red (> 60 s). This mirrors the `heartbeat_timeout_seconds` you configured in `HealthRegistry`.

#### Alerting on Component Failures

In Grafana, create an alert rule:

```promql
cqrs_health_component_up == 0
```

Fire after **2 consecutive evaluations** to avoid transient blips. Route to Slack, PagerDuty, or email via Grafana Alerting.

For worker heartbeat staleness:

```promql
cqrs_health_heartbeat_age_seconds > 120
```

This fires when a worker hasn't heartbeated in 2 minutes.

---

### Step 3: Health Endpoint for Kubernetes + Uptime Monitors

The HTTP endpoints defined in the [Exposing as an HTTP Endpoint](#exposing-as-an-http-endpoint) section above double as targets for external uptime monitors (UptimeRobot, Pingdom, etc.) and Kubernetes probes.

For Kubernetes, the liveness and readiness probes map directly:

| Probe | Endpoint | What it checks |
|:------|:---------|:---------------|
| **Liveness** | `GET /health/live` | Process is alive (always returns 200) |
| **Readiness** | `GET /health/ready` | All infrastructure dependencies + workers are healthy |
| **Startup** | `GET /health/ready` | Same as readiness (use higher `failureThreshold`) |

The readiness probe returning `503` causes Kubernetes to remove the pod from the Service's endpoints, stopping traffic to an unhealthy instance.

---

### Step 4: Connecting Health with Traces and Logs

When combined with `cqrs-ddd-observability`, you can correlate health failures with traces and logs:

1. **Health → Metrics** (this section): `cqrs_health_component_up` in Prometheus/Grafana.
2. **Traces → Jaeger/Grafana**: When a command fails because a dependency is down, the trace in Jaeger shows the error span.
3. **Logs → Loki/Grafana**: `StructuredLoggingMiddleware` logs the error with `correlation_id`, searchable in Loki.

In Grafana, a single dashboard can show:
- Health gauges (Prometheus) — "is the database up?"
- Error-rate spike (Prometheus) — "commands started failing at 14:32"
- Correlated traces (Jaeger) — "this specific command hit a connection timeout"
- Correlated logs (Loki) — "full stack trace with the same `correlation_id`"

This provides complete visibility from a health status change through its impact on request processing down to individual log entries.

---

### Summary: Health in the Observability Stack

| Signal | Source | Storage | Visualization |
|:-------|:-------|:--------|:--------------|
| Component health | `HealthRegistry.check_all()` → Prometheus gauge | Prometheus | Grafana stat/status panel |
| Worker heartbeats | `HealthRegistry.heartbeat()` → Prometheus gauge | Prometheus | Grafana gauge panel |
| Health HTTP endpoints | `/health`, `/health/ready`, `/health/live` | N/A | Kubernetes probes, uptime monitors |
| Alerts | PromQL rules | Grafana Alerting | Slack, PagerDuty, email |
