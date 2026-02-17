from typing import NoReturn

import pytest

from cqrs_ddd_core.adapters.memory.unit_of_work import InMemoryUnitOfWork


@pytest.mark.asyncio()
async def test_uow_context_manager_commit() -> None:
    uow = InMemoryUnitOfWork()

    async with uow:
        await uow.commit()

    assert uow.committed
    assert uow.commit_count == 1
    assert not uow.rolled_back


@pytest.mark.asyncio()
async def test_uow_context_manager_rollback_on_error() -> NoReturn:
    uow = InMemoryUnitOfWork()

    with pytest.raises(ValueError, match="oops"):
        async with uow:
            raise ValueError("oops")

    assert not uow.committed
    assert uow.rolled_back
    assert uow.rollback_count == 1


@pytest.mark.asyncio()
async def test_uow_manual_rollback() -> None:
    uow = InMemoryUnitOfWork()

    async with uow:
        await uow.rollback()

    assert uow.rolled_back
    assert not uow.committed


def test_uow_reset() -> None:
    uow = InMemoryUnitOfWork()
    uow.committed = True
    uow.rolled_back = True
    uow.commit_count = 5

    uow.reset()

    assert not uow.committed
    assert not uow.rolled_back
    assert uow.commit_count == 0
