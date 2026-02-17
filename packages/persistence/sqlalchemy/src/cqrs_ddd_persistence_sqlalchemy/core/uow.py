"""
SQLAlchemy implementation of the Unit of Work pattern.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from ..exceptions import SessionManagementError, UnitOfWorkError

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession

    AsyncSessionFactory = Callable[[], AsyncSession]


class SQLAlchemyUnitOfWork(UnitOfWork):
    """
    Unit of Work implementation using SQLAlchemy AsyncSession.

    Supports two usage patterns:

    1. **Caller-Managed Sessions** (Original pattern):
       ```python
       async with SQLAlchemyUnitOfWork(session=session) as uow:
           await uow.commit()
       ```
       The session lifecycle is managed by the dependency injection container.

    2. **Self-Managed Sessions** (New hybrid approach):
       ```python
       factory = sessionmaker(engine, class_=AsyncSession)
       async with SQLAlchemyUnitOfWork(session_factory=factory) as uow:
           # UoW creates and closes the session
           await uow.commit()
       ```
       The UoW creates and closes the session automatically.

    **Important:** Exactly one of `session` or `session_factory` must be provided.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        session_factory: AsyncSessionFactory | None = None,
    ) -> None:
        if session is not None and session_factory is not None:
            raise SessionManagementError(
                "Cannot provide both 'session' and 'session_factory'. "
                "Use either caller-managed (session) or self-managed "
                "(session_factory) pattern."
            )

        if session is None and session_factory is None:
            raise SessionManagementError(
                "Must provide either 'session' or 'session_factory'. "
                "Use caller-managed pattern with session=(AsyncSession) "
                "or self-managed pattern with session_factory=(callable)."
            )

        self._session: AsyncSession | None = session
        self._session_factory = session_factory
        self._owns_session = session_factory is not None and session is None
        super().__init__()

    @property
    def session(self) -> AsyncSession:
        """Get the active session. Raises if session not yet created."""
        if self._session is None:
            raise UnitOfWorkError(
                "Session not yet created. Ensure __aenter__ was called."
            )
        return self._session

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        """Begin a transaction, creating session if factory provided."""
        try:
            if self._owns_session and self._session_factory:
                self._session = self._session_factory()

            if not self.session.in_transaction():
                await self.session.begin()

            return self
        except Exception as e:  # noqa: BLE001
            # Catch all exceptions during session initialization and wrap them
            if isinstance(e, SessionManagementError | UnitOfWorkError):
                raise
            raise SessionManagementError(f"Failed to initialize UoW: {e}") from e

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        Commit or rollback transaction via base class, closing session if
        factory-created.
        """
        try:
            # Delegate to base class for commit/rollback/hooks logic
            await super().__aexit__(exc_type, exc_val, exc_tb)
        finally:
            if self._owns_session and self._session is not None:
                try:
                    await self._session.close()
                except Exception as e:  # noqa: BLE001
                    # Catch all session close errors and wrap them
                    raise SessionManagementError(f"Failed to close session: {e}") from e

    async def commit(self) -> None:
        """Commit the current transaction."""
        try:
            await self.session.commit()
        except Exception as e:  # noqa: BLE001
            # Catch all commit errors (constraint violations, network, etc.)
            # Safe rollback on commit failure
            with contextlib.suppress(Exception):
                await self.rollback()
            raise UnitOfWorkError(f"Failed to commit transaction: {e}") from e

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        try:
            if self.session.in_transaction():
                await self.session.rollback()
        except Exception as e:  # noqa: BLE001
            # Catch all rollback errors and wrap them
            raise UnitOfWorkError(f"Failed to rollback transaction: {e}") from e
