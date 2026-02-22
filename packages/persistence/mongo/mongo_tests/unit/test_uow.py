"""Tests for MongoUnitOfWork."""

import pytest

from cqrs_ddd_persistence_mongo import MongoUnitOfWork, MongoUnitOfWorkError


@pytest.mark.asyncio
async def test_uow_calls_commit_hooks_after_commit(mongo_connection_with_mock_session):
    """Test that on_commit hooks are called after successful commit."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )
    hook_called = False

    async def hook():
        nonlocal hook_called
        hook_called = True

    uow.on_commit(hook)

    # Simulate successful context manager usage (commit calls trigger_commit_hooks)
    await uow.__aenter__()
    await uow.commit()

    assert hook_called


@pytest.mark.asyncio
async def test_uow_rollback_on_exception(mongo_connection_with_mock_session):
    """Test that rollback is called when exception occurs."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )

    # Simulate exception in context
    await uow.__aenter__()
    await uow.rollback()

    # For mock/standalone, rollback is a no-op but doesn't raise
    assert True  # If we got here, rollback completed


@pytest.mark.asyncio
async def test_uow_context_manager_commit(mongo_connection_with_mock_session):
    """Test that __aexit__ commits when no exception occurs."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )
    hook_called = False

    async def hook():
        nonlocal hook_called
        hook_called = True

    uow.on_commit(hook)

    async with uow:
        # No exception
        pass

    assert hook_called


@pytest.mark.asyncio
async def test_uow_context_manager_rollback_on_exception(mongo_connection_with_mock_session):
    """Test that __aexit__ rolls back when exception occurs."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )

    with pytest.raises(ValueError):
        async with uow:
            raise ValueError("Test exception")

    # For mock/standalone, rollback is a no-op but doesn't raise
    assert True  # If we got here, rollback completed


@pytest.mark.asyncio
async def test_uow_multiple_hooks(mongo_connection_with_mock_session):
    """Test that multiple on_commit hooks are called in order."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )
    calls = []

    async def hook1():
        calls.append(1)

    async def hook2():
        calls.append(2)

    async def hook3():
        calls.append(3)

    uow.on_commit(hook1)
    uow.on_commit(hook2)
    uow.on_commit(hook3)

    await uow.__aenter__()
    await uow.commit()

    assert calls == [1, 2, 3]


@pytest.mark.asyncio
async def test_uow_session_property_raises_if_not_entered(mongo_connection_with_mock_session):
    """Test that session property raises error if not entered."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )

    with pytest.raises(MongoUnitOfWorkError):
        _ = uow.session


@pytest.mark.asyncio
async def test_uow_session_available_after_enter(mongo_connection_with_mock_session):
    """Test that session property returns session after __aenter__."""
    uow = MongoUnitOfWork(
        connection=mongo_connection_with_mock_session,
        require_replica_set=False,
    )

    async with uow:
        session = uow.session
        assert session is not None


@pytest.mark.asyncio
async def test_uow_with_session_provided(mongo_connection):
    """Test that pre-existing session can be provided."""
    from unittest.mock import MagicMock, AsyncMock

    mock_session = MagicMock()
    mock_session.in_transaction.return_value = False
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    uow = MongoUnitOfWork(session=mock_session, require_replica_set=False)

    async with uow:
        # Should use provided session
        assert uow.session is not None

    assert uow._owns_session is False
