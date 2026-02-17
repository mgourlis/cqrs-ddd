from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cqrs_ddd_persistence_sqlalchemy.core.uow import (
    SQLAlchemyUnitOfWork,
    UnitOfWorkError,
)


@pytest.mark.asyncio()
async def test_uow_initializes_base():
    """Test that SQLAlchemyUnitOfWork initializes base UnitOfWork (hooks)."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = False
    session.begin = AsyncMock()  # Ensure begin works as awaitable
    uow = SQLAlchemyUnitOfWork(session=session)

    # Check if _on_commit_hooks is initialized (attribute bound in base __init__)
    assert hasattr(uow, "_on_commit_hooks")
    assert uow._on_commit_hooks is not None


@pytest.mark.asyncio()
async def test_uow_commit_hooks_execution():
    """Test that hooks are executed after commit."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = False
    session.begin = AsyncMock()

    hook_called = False

    async def my_hook():
        nonlocal hook_called
        hook_called = True

    async with SQLAlchemyUnitOfWork(session=session) as uow:
        uow.on_commit(my_hook)
        # Verify hook is registered
        assert len(uow._on_commit_hooks) == 1

    # After exit (no exception), hook should be called
    session.commit.assert_awaited_once()
    assert hook_called is True


@pytest.mark.asyncio()
async def test_uow_rollback_on_exception():
    """Test that rollback happens on exception and hooks are NOT called."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = True  # Must be True for rollback to happen
    session.begin = AsyncMock()

    hook_called = False

    async def my_hook():
        nonlocal hook_called
        hook_called = True

    async def _failing_operation():
        async with SQLAlchemyUnitOfWork(session=session) as uow:
            uow.on_commit(my_hook)
            raise ValueError("Boom")

    with pytest.raises(ValueError, match="Boom"):
        await _failing_operation()

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    assert hook_called is False


@pytest.mark.asyncio()
async def test_uow_auto_rollback_on_commit_failure():
    """Test that explicit commit failure triggers rollback."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = True  # Must be True for rollback to happen
    session.begin = AsyncMock()
    session.commit.side_effect = Exception("Commit failed")

    with pytest.raises(UnitOfWorkError):
        async with SQLAlchemyUnitOfWork(session=session):
            pass  # Implicit commit should fail

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio()
async def test_uow_session_management():
    """Test self-managed session lifecycle."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = False
    session.begin = AsyncMock()
    factory = MagicMock(return_value=session)

    async with SQLAlchemyUnitOfWork(session_factory=factory) as uow:
        assert uow.session is session
        session.begin.assert_awaited_once()

    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()
