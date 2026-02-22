# Background Jobs

Track, execute, cancel, retry, and administer long-running work inside a
CQRS/DDD application.  Background jobs are modelled as **aggregate roots**
with a strict state machine, domain events on every transition, and two
dedicated services: one operational, one administrative.

---

## Architecture at a glance

```
                   schedule()
  Application  ──────────────►  BackgroundJobService
                                     │
                                     ▼
                              IBackgroundJobRepository ◄── InMemory / SQLAlchemy
                                     │
               ┌─────────────────────┼──────────────────────┐
               ▼                     ▼                      ▼
       BaseBackgroundJob     JobSweeperWorker     BackgroundJobAdminService
       (aggregate root)      (stale job cleanup)  (listing, stats, cancel,
                                                   bulk ops, purge)
               │
               ▼
    BackgroundJobEventHandler
    (load job → execute → complete/fail/cancel)
```

---

## State machine

Every `BaseBackgroundJob` follows a strict lifecycle.  Invalid transitions
raise `JobStateError`.

```
          ┌──────────── retry() ────────────┐
          ▼                                 │
       PENDING ──start_processing()──► RUNNING ──complete()──► COMPLETED
          │                              │  │
          │ cancel()            fail()   │  │ cancel()
          ▼                     ▼        │  ▼
       CANCELLED             FAILED ◄────┘ CANCELLED
```

Each transition emits a frozen domain event (`JobCreated`, `JobStarted`,
`JobCompleted`, `JobFailed`, `JobRetried`, `JobCancelled`).

---

## Quick start

### 1. Create and schedule a job

```python
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobService,
    BaseBackgroundJob,
)

repo = InMemoryBackgroundJobRepository()      # or SQLAlchemy impl
service = BackgroundJobService(persistence=repo)

job = BaseBackgroundJob.create(
    job_type="csv_import",
    total_items=1000,
    correlation_id="req-abc-123",
    metadata={"filename": "users.csv"},
)
await service.schedule(job)
# job.status == PENDING
```

### 2. Implement a handler

Subclass `BackgroundJobEventHandler` and implement `execute()`.  The base
class handles loading the job, transitioning to RUNNING, and persisting the
outcome.

```python
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobEventHandler,
    BaseBackgroundJob,
)

class CsvImportHandler(BackgroundJobEventHandler[ImportRequested]):

    async def execute(
        self, event: ImportRequested, job: BaseBackgroundJob
    ) -> dict[str, Any] | None:
        rows = load_csv(event.file_path)
        imported = 0
        for batch in chunked(rows, 100):
            # Cooperative cancellation: check between batches
            await self.checkpoint_cancellation(job.id)

            await process_batch(batch)
            imported += len(batch)
            job.update_progress(imported)
            await self._persistence.add(job)

        return {"imported": imported}

    async def on_cancellation(self, event: ImportRequested, job: BaseBackgroundJob) -> None:
        # Optional: release resources, delete temp files, send "aborted" notification
        pass
```

The handler's `handle()` lifecycle:

1. Loads the job via `correlation_id` from the triggering event.
2. Calls `before_processing()` hook (optional override).
3. Transitions to RUNNING (or retries if previously FAILED).
4. Calls your `execute()`.
5. On success: reloads the job from the repository (race-condition guard),
   skips `complete()` if it was cancelled concurrently, otherwise completes.
6. On `CancellationRequestedError`: calls `on_cancellation()` hook (override
   for cleanup), then ensures the job is persisted as CANCELLED and returns
   cleanly (no FAILED, no re-raise).
7. On other exceptions: calls `on_failure()` hook, then `fail()`.

### 3. Start the sweeper worker

The `JobSweeperWorker` runs in the background and marks RUNNING jobs that
have exceeded their timeout as FAILED.

```python
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobService,
    JobSweeperWorker,
)

service = BackgroundJobService(persistence=repo)
sweeper = JobSweeperWorker(
    service=service,
    poll_interval=60.0,       # check every 60s
    timeout_seconds=3600,     # 1 hour timeout
)

# Wire trigger so sweeper wakes immediately when a job starts running
service.set_sweeper_trigger(sweeper.trigger)

await sweeper.start()
# ... application runs ...
await sweeper.stop()
```

---

## Administration

`BackgroundJobAdminService` provides dashboards, bulk operations, and
cleanup.  It is intentionally separate from `BackgroundJobService` to keep
operational and administrative concerns apart.

```python
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobAdminService,
    BackgroundJobStatus,
)

admin = BackgroundJobAdminService(repository=repo)
```

### Dashboard statistics

```python
stats = await admin.get_statistics()
# stats.counts == {"PENDING": 5, "RUNNING": 2, "FAILED": 1}
# stats.total == 8
```

### List jobs by status (with pagination)

```python
failed = await admin.list_jobs(
    statuses=[BackgroundJobStatus.FAILED],
    limit=20,
    offset=0,
)
```

### Bulk cancel

```python
cancelled, skipped = await admin.bulk_cancel(
    [job.id for job in pending_jobs]
)
```

### Bulk retry

Only FAILED jobs within their `max_retries` budget are retried.  Others are
skipped.

```python
retried, skipped = await admin.bulk_retry(
    [job.id for job in failed_jobs]
)
```

### Purge old terminal jobs

Delete COMPLETED and CANCELLED jobs older than a threshold.

```python
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
deleted = await admin.purge_completed(before=cutoff)
```

---

## Cancelling running jobs

### Cooperative cancellation (Layer 1)

Inside `execute()`, call `checkpoint_cancellation()` between work units.
When an admin marks the job CANCELLED, the next checkpoint raises
`CancellationRequestedError` and the handler stops cleanly.

```python
async def execute(self, event, job):
    for batch in batches:
        await self.checkpoint_cancellation(job.id)   # <-- polls repo
        await process(batch)
```

Without a kill strategy, this is all that happens:

```python
await admin.cancel_running(job_id)
# Marks CANCELLED in DB; handler will notice at next checkpoint.
```

### Escalation with `IJobKillStrategy` (Layer 2)

For jobs that may not hit a checkpoint quickly (or at all), provide a kill
strategy that can signal the runtime.

**Asyncio tasks (same process):**

```python
from cqrs_ddd_advanced_core.adapters.asyncio_task_registry import (
    AsyncioJobTaskRegistry,
)

task_registry = AsyncioJobTaskRegistry()

# When launching the handler:
task = asyncio.create_task(handler.handle(event))
task_registry.register(job.id, task)

# Cancel with escalation:
await admin.cancel_running(
    job_id,
    kill_strategy=task_registry,
    grace_seconds=10.0,
)
```

The `cancel_running()` flow with a kill strategy:

1. Marks the job CANCELLED in the repository (cooperative signal).
2. Calls `kill_strategy.request_stop(job_id)` (e.g. `task.cancel()`).
3. Polls the repository every second for up to `grace_seconds`.
4. If the job is still RUNNING: calls `kill_strategy.force_kill(job_id)`,
   then marks the job FAILED with a descriptive message.

**Out-of-process workers:**

Implement `IJobKillStrategy` with your own runtime mechanics:

```python
from cqrs_ddd_advanced_core.ports.job_runner import IJobKillStrategy

class CeleryJobKillStrategy(IJobKillStrategy):
    def register(self, job_id: str, handle: Any) -> None:
        # handle is e.g. celery.result.AsyncResult
        self._tasks[job_id] = handle

    def unregister(self, job_id: str) -> None:
        self._tasks.pop(job_id, None)

    async def request_stop(self, job_id: str) -> None:
        self._tasks[job_id].revoke(terminate=True, signal="SIGTERM")

    async def force_kill(self, job_id: str) -> None:
        self._tasks[job_id].revoke(terminate=True, signal="SIGKILL")
```

---

## Operational service API

`BackgroundJobService` is for the application's operational path:

| Method               | Description                                            |
|:---------------------|:-------------------------------------------------------|
| `schedule(job)`      | Persist a newly created PENDING job.                   |
| `cancel(job_id)`     | Cancel a job (PENDING or RUNNING).                     |
| `retry(job_id)`      | Retry a FAILED job.                                    |
| `get(job_id)`        | Fetch a single job by ID.                              |
| `mark_running(id)`   | Transition PENDING to RUNNING; wakes the sweeper.      |
| `process_stale_jobs` | Mark timed-out RUNNING jobs as FAILED (used by worker).|

---

## Repository port

`IBackgroundJobRepository` extends `IRepository[BaseBackgroundJob, str]`
with job-specific queries:

| Method                       | Description                                           |
|:-----------------------------|:------------------------------------------------------|
| `get_stale_jobs(timeout)`    | RUNNING jobs that exceeded their timeout.             |
| `find_by_status(statuses)`   | Paginated listing by lifecycle status.                |
| `count_by_status()`          | Status-to-count mapping for dashboards.               |
| `purge_completed(before)`    | Bulk-delete COMPLETED/CANCELLED jobs older than date. |
| `is_cancellation_requested`  | Lightweight poll: is status CANCELLED?                |

Plus the standard `IRepository` methods: `add`, `get`, `delete`,
`list_all`, `search`.

**Shipped implementations:**

- `InMemoryBackgroundJobRepository` (in `adapters/memory/`) -- for tests.
- `SQLAlchemyBackgroundJobRepository` (in `cqrs-ddd-persistence-sqlalchemy`)
  -- for production.

---

## Domain events

Every state transition emits a frozen `DomainEvent`:

| Event          | Emitted when                          | Extra fields       |
|:---------------|:--------------------------------------|:-------------------|
| `JobCreated`   | `BaseBackgroundJob.create()`          | `job_type`, `total_items` |
| `JobStarted`   | `start_processing()`                  | --                 |
| `JobCompleted` | `complete()`                          | --                 |
| `JobFailed`    | `fail()`                              | `error_message`    |
| `JobRetried`   | `retry()`                             | `retry_count`      |
| `JobCancelled` | `cancel()`                            | --                 |

All events carry `correlation_id`, `aggregate_id`, and `aggregate_type`
automatically.

---

## Entity fields

`BaseBackgroundJob` is a Pydantic-based `AggregateRoot[str]`:

| Field                | Type                  | Default       | Description                        |
|:---------------------|:----------------------|:--------------|:-----------------------------------|
| `id`                 | `str`                 | UUID v4       | Unique job identifier.             |
| `job_type`           | `str`                 | `""`          | Discriminator for job kind.        |
| `status`             | `BackgroundJobStatus` | `PENDING`     | Current lifecycle state.           |
| `total_items`        | `int`                 | `0`           | Total units of work.               |
| `processed_items`    | `int`                 | `0`           | Units processed so far.            |
| `result_data`        | `dict[str, Any]`      | `{}`          | Arbitrary result payload.          |
| `error_message`      | `str \| None`         | `None`        | Set on fail/cancel.                |
| `broker_message_id`  | `str \| None`         | `None`        | Message broker tracking ID.        |
| `retry_count`        | `int`                 | `0`           | Times retried.                     |
| `max_retries`        | `int`                 | `3`           | Retry budget.                      |
| `created_at`         | `datetime`            | now (UTC)     | Creation timestamp.                |
| `updated_at`         | `datetime`            | now (UTC)     | Last modification timestamp.       |
| `metadata`           | `dict[str, Any]`      | `{}`          | Free-form metadata.                |
| `correlation_id`     | `str \| None`         | `None`        | Links job to triggering command.   |

---

## Exceptions

| Exception                    | Base          | Raised when                                       |
|:-----------------------------|:--------------|:--------------------------------------------------|
| `JobStateError`              | `DomainError` | Invalid state machine transition.                 |
| `CancellationRequestedError` | `DomainError` | Cooperative cancel detected via `checkpoint_cancellation()`. |

---

## Testing

Use `InMemoryBackgroundJobRepository` from `adapters.memory`:

```python
from cqrs_ddd_advanced_core.adapters.memory import (
    InMemoryBackgroundJobRepository,
)
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobAdminService,
    BackgroundJobService,
    BaseBackgroundJob,
    JobSweeperWorker,
)

repo = InMemoryBackgroundJobRepository()
service = BackgroundJobService(persistence=repo)
admin = BackgroundJobAdminService(repository=repo)

# Create and schedule
job = BaseBackgroundJob.create(job_type="test", total_items=10)
await service.schedule(job)

# Verify
fetched = await service.get(job.id)
assert fetched is not None
assert fetched.status.value == "PENDING"

# Run sweeper once (useful in tests)
sweeper = JobSweeperWorker(service=service, timeout_seconds=0)
swept = await sweeper.run_once()
```
