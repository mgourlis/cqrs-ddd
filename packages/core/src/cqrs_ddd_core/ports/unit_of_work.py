"""UnitOfWork — Abstract base class for the Unit of Work pattern."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger("cqrs_ddd.uow")


class UnitOfWork(ABC):
    """
    Abstract base class for Unit of Work implementations.

    **ALL IMPLEMENTATIONS MUST EXTEND THIS CLASS** to get post-commit hook support.

    This class provides the infrastructure for 'on_commit' hooks and enforces
    the critical lifecycle guarantee: **Commit happens BEFORE hooks are triggered**.

    This ensures that when a hook (e.g., outbox trigger) fires, the database
    transaction is fully committed and visible to other processes.

    Example:
        ```python
        from cqrs_ddd_core.ports import UnitOfWork

        class SQLAlchemyUnitOfWork(UnitOfWork):
            def __init__(self, session):
                super().__init__()
                self._session = session

            async def commit(self):
                self._session.commit()

            async def rollback(self):
                self._session.rollback()
        ```
    """

    def __init__(self) -> None:
        self._on_commit_hooks: deque[Callable[[], Awaitable[Any]]] = deque()

    def on_commit(self, callback: Callable[[], Awaitable[Any]]) -> None:
        """Register an async callback to be executed after a successful commit.

        Args:
            callback: An async function that takes no arguments.
        """
        self._on_commit_hooks.append(callback)

    async def trigger_commit_hooks(self) -> None:
        """Execute all registered on_commit hooks.

        Called automatically by __aexit__ AFTER commit completes.
        """
        while self._on_commit_hooks:
            callback = self._on_commit_hooks.popleft()
            try:
                await callback()
            except Exception as exc:
                logger.error("Error in on_commit hook: %s", exc, exc_info=True)

    @abstractmethod
    async def commit(self) -> None:
        """Commit the transaction. Must be implemented by subclasses."""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the transaction. Must be implemented by subclasses."""
        ...

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """
        Exit the context manager.

        CRITICAL ORDER:
        1. If successful (exc_type is None): commit() first
        2. Then trigger_commit_hooks() — ensures DB is flushed before hooks fire
        3. If exception: rollback() and skip hooks
        """
        if exc_type is None:
            await self.commit()
            await self.trigger_commit_hooks()
        else:
            await self.rollback()
