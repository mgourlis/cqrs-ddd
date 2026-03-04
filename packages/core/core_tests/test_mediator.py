from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.mediator import Mediator
from cqrs_ddd_core.cqrs.query import Query
from cqrs_ddd_core.cqrs.registry import HandlerRegistry
from cqrs_ddd_core.cqrs.response import CommandResponse, QueryResponse
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

# --- Mock Models ---


class MyCommand(Command[str]):
    name: str


class MyQuery(Query[str]):
    id: str


# --- Tests ---


@pytest.mark.asyncio
async def test_mediator_send_command_calls_uow_and_handler() -> None:
    # Setup
    uow = AsyncMock(spec=UnitOfWork)
    uow.__aenter__.return_value = uow
    uow_factory = MagicMock(return_value=uow)

    registry = MagicMock(spec=HandlerRegistry)
    handler_cls = MagicMock()
    handler = AsyncMock()
    handler.handle.return_value = CommandResponse(result="Success")
    handler_factory = MagicMock(return_value=handler)

    registry.get_command_handler.return_value = handler_cls

    registry.get_all_synchronous_event_handlers.return_value = {}

    mediator = Mediator(
        registry=registry, uow_factory=uow_factory, handler_factory=handler_factory
    )

    # Execute
    cmd = MyCommand(name="test")
    result = await mediator.send(cmd)

    # Verify
    assert result.result == "Success"
    uow_factory.assert_called_once()
    uow.__aenter__.assert_called_once()
    uow.__aexit__.assert_called_once()
    handler.handle.assert_called_once()
    actual_cmd = handler.handle.call_args[0][0]
    assert actual_cmd.name == cmd.name
    assert actual_cmd.correlation_id is not None


@pytest.mark.asyncio
async def test_mediator_query_calls_handler() -> None:
    # Setup
    registry = MagicMock(spec=HandlerRegistry)
    handler_cls = MagicMock()
    handler = AsyncMock()
    handler.handle.return_value = QueryResponse(result="Result")
    handler_factory = MagicMock(return_value=handler)

    registry.get_query_handler.return_value = handler_cls

    registry.get_all_synchronous_event_handlers.return_value = {}

    mediator = Mediator(
        registry=registry, uow_factory=MagicMock(), handler_factory=handler_factory
    )

    # Execute
    qry = MyQuery(id="123")
    result = await mediator.query(qry)

    # Verify
    assert result.result == "Result"
    handler.handle.assert_called_once()
    actual_qry = handler.handle.call_args[0][0]
    assert actual_qry.id == qry.id
    assert actual_qry.correlation_id is not None
