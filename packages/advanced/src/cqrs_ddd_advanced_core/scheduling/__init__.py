"""Command Scheduling — deferred command execution at a future time.

This module is deliberately **separate** from :mod:`background_jobs`.

* **Scheduling** answers the question *when* to execute a command.
  It persists a ``(command, execute_at)`` tuple and dispatches through
  the mediator once the time arrives.

* **Background Jobs** answers the question *how to track* long-running
  work.  It provides lifecycle state, progress, retries, and domain
  events.

The two can compose naturally: schedule a command that *starts* a
background job (e.g., ``ScheduleCommand(StartImportCommand(…), execute_at=…)``).
"""

from .service import CommandSchedulerService
from .worker import CommandSchedulerWorker

__all__ = ["CommandSchedulerService", "CommandSchedulerWorker"]
