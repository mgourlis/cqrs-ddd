"""IBackgroundWorker — general protocol for async background processes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IBackgroundWorker(Protocol):
    """
    General lifecycle protocol for background workers.

    Used by: ``OutboxWorker``, ``SagaRecoveryWorker``, ``JobSweeperWorker``.
    """

    async def start(self) -> None:
        """Start the background process."""
        ...

    async def stop(self) -> None:
        """Stop the background process gracefully."""
        ...
