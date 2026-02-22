"""IJobKillStrategy — protocol for runtime-level job cancellation / termination."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IJobKillStrategy(Protocol):
    """Port for registering running jobs and stopping them at the runtime level.

    Two escalation levels are supported:

    * :meth:`request_stop` — graceful signal (e.g. ``asyncio.Task.cancel()``,
      ``SIGTERM`` to a worker process).
    * :meth:`force_kill` — hard stop (e.g. ``SIGKILL``, pod eviction).

    Implementations are runtime-specific:

    * ``AsyncioJobTaskRegistry`` — ships in ``adapters/`` for in-process
      asyncio tasks.
    * For out-of-process workers (Celery, multiprocessing, k8s) users
      provide their own implementation.

    Usage::

        # When a handler starts executing a job:
        kill_strategy.register(job.id, asyncio.current_task())

        # Admin cancels the running job:
        await kill_strategy.request_stop(job.id)

        # Grace period expires and job is still alive:
        await kill_strategy.force_kill(job.id)
    """

    def register(self, job_id: str, handle: Any) -> None:
        """Register a runtime handle (Task, PID, pod name, …) for a job.

        Args:
            job_id: The background job ID.
            handle: Runtime-specific handle used by stop/kill.
        """
        ...

    def unregister(self, job_id: str) -> None:
        """Remove the runtime handle after a job finishes or is cleaned up.

        Args:
            job_id: The background job ID.
        """
        ...

    async def request_stop(self, job_id: str) -> None:
        """Send a graceful stop signal to the running job.

        For asyncio: ``task.cancel()``.
        For processes: ``os.kill(pid, signal.SIGTERM)``.

        Args:
            job_id: The background job ID.
        """
        ...

    async def force_kill(self, job_id: str) -> None:
        """Force-terminate the running job after grace period expires.

        For asyncio: same as request_stop (no harder escalation).
        For processes: ``os.kill(pid, signal.SIGKILL)``.

        Args:
            job_id: The background job ID.
        """
        ...
