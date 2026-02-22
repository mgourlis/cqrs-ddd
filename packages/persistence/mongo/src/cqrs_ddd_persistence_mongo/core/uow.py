"""
MongoDB implementation of the Unit of Work pattern.

Supports MongoDB 4.0+ transactions with sessions, or non-transactional mode
for standalone deployments.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from motor.motor_asyncio import (
        AsyncIOMotorClient,
        AsyncIOMotorClientSession,
    )

    from ..connection import MongoConnectionManager

    AsyncSessionFactory = Any  # Callable[[], AsyncIOMotorClientSession]

from .session_utils import session_in_transaction

logger = logging.getLogger("cqrs_ddd.mongo.uow")

_REPLICA_SET_REQUIRED_MSG = (
    "MongoDB multi-document transactions require a Replica Set. "
    "Your MongoDB instance is running in standalone mode.\n\n"
    "Solutions:\n"
    "1. For local development: Use a single-node replica set — "
    "see docs/mongodb_infrastructure_requirements.md\n"
    "2. For testing: Set require_replica_set=False (not recommended for production)\n"
    "3. For production: Use MongoDB Atlas or deploy a 3-node replica set"
)


class MongoUnitOfWorkError(Exception):
    """Base exception for MongoDB Unit of Work errors."""


class MongoUnitOfWork(UnitOfWork):
    """
    Unit of Work implementation using MongoDB AsyncClientSession.

    Supports two usage patterns:

    1. **Client-managed sessions** (for transactions):
       ```python
       session = await client.start_session()
       async with MongoUnitOfWork(session=session) as uow:
           await uow.commit()
       ```

    2. **Self-managed sessions** (with connection manager):
       ```python
       connection = MongoConnectionManager(url="mongodb://localhost:27017")
       await connection.connect()
       async with MongoUnitOfWork(connection=connection) as uow:
           await uow.commit()
       ```

    **Important:**

    - MongoDB 4.0+ sessions require a **replica set** for multi-document transactions.
    - For standalone MongoDB, sessions are created but transactions are not used.
    - The UnitOfWork provides on_commit hooks support via the base class.
    """

    def __init__(
        self,
        session: AsyncIOMotorClientSession | None = None,
        connection: MongoConnectionManager | None = None,
        session_factory: AsyncSessionFactory | None = None,
        *,
        require_replica_set: bool = True,
    ) -> None:
        """
        Initialize the Unit of Work.

        Args:
            session: Pre-existing MongoDB session (client-managed).
            connection: Connection manager for creating sessions (self-managed).
            session_factory: Optional factory for creating sessions.
            require_replica_set: If True, verify MongoDB is a replica set before
                starting a transaction; raise RuntimeError otherwise. Set False
                for tests with standalone/mock. Default True.

        Raises:
            MongoUnitOfWorkError: If conflicting parameters are provided.
        """
        if session is not None and connection is not None:
            raise MongoUnitOfWorkError(
                "Cannot provide both 'session' and 'connection'. "
                "Use either client-managed (session) or self-managed "
                "(connection/session_factory) pattern."
            )

        super().__init__()
        self._session = session
        self._connection = connection
        self._session_factory = session_factory
        self._owns_session = session is None
        self._require_replica_set = require_replica_set

    async def _create_session(self) -> AsyncIOMotorClientSession:
        """Create a new session from the connection."""
        if self._connection is None:
            raise MongoUnitOfWorkError("No connection available to create session")
        client = self._connection.client
        return await client.start_session()

    @property
    def session(self) -> AsyncIOMotorClientSession:
        """Get the current session.

        Returns:
            The MongoDB session for this Unit of Work.

        Raises:
            MongoUnitOfWorkError: If session is not available (not entered context).
        """
        if self._session is None:
            raise MongoUnitOfWorkError(
                "Session not available. Use the Unit of Work as a context manager first."
            )
        return self._session

    async def _check_replica_set(self) -> None:
        """Raise RuntimeError if require_replica_set and MongoDB is not a replica set."""
        client = getattr(self._session, "client", None) if self._session else None
        if client is None and self._connection:
            client = self._connection.client
        if client is None:
            return
        try:
            result = await client.admin.command("replSetGetStatus")
            if result.get("ok") != 1:
                raise RuntimeError(_REPLICA_SET_REQUIRED_MSG)
        except Exception as e:
            if self._require_replica_set:
                if isinstance(e, RuntimeError):
                    raise
                raise RuntimeError(_REPLICA_SET_REQUIRED_MSG) from e

    async def __aenter__(self) -> MongoUnitOfWork:
        """Enter the context and create/validate the session.

        Returns:
            Self for use in async with statements.
        """
        if self._owns_session:
            if self._session_factory:
                result = self._session_factory()
                self._session = (
                    await result if asyncio.iscoroutine(result) else result
                )
            elif self._connection:
                self._session = await self._create_session()
            else:
                raise MongoUnitOfWorkError(
                    "No session_factory or connection provided for self-managed session."
                )
        if self._session and self._require_replica_set:
            await self._check_replica_set()
        # Only start a transaction when we require replica set (transactions need replica set)
        if (
            self._session
            and self._require_replica_set
            and not session_in_transaction(self._session)
        ):
            try:
                self._session.start_transaction()
            except (AttributeError, TypeError):
                pass
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context, commit or rollback, and trigger hooks.

        Commits on success, rolls back on exception.
        Always triggers on_commit hooks after a successful commit.
        """
        if self._session is None:
            return

        try:
            if exc_type is None:
                # No exception: commit and trigger hooks
                try:
                    await self.commit()
                except Exception:
                    await self.rollback()
                    raise
            else:
                # Exception occurred: rollback
                await self.rollback()
        finally:
            if self._owns_session and self._session is not None:
                self._session.end_session()
                self._session = None

    async def commit(self) -> None:
        """Commit the transaction.

        For MongoDB sessions with transactions started, commits the transaction.
        For sessions without transactions (standalone mode), this is a no-op.
        """
        if self._session is None:
            return

        if session_in_transaction(self._session):
            await self._session.commit_transaction()
        else:
            # Not in transaction: nothing to commit
            logger.debug("MongoDB session not in transaction, commit is no-op")

        # Trigger on_commit hooks after successful commit
        await self.trigger_commit_hooks()

    async def rollback(self) -> None:
        """Rollback the transaction.

        For MongoDB sessions with transactions started, aborts the transaction.
        For sessions without transactions (standalone mode), this is a no-op.
        """
        if self._session is None:
            return

        if session_in_transaction(self._session):
            await self._session.abort_transaction()
        else:
            logger.debug("MongoDB session not in transaction, rollback is no-op")
