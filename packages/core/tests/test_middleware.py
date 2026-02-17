import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_core.middleware import (
    EventStorePersistenceMiddleware,
    LoggingMiddleware,
    ValidatorMiddleware,
)
from cqrs_ddd_core.ports.event_store import IEventStore
from cqrs_ddd_core.ports.validation import IValidator
from cqrs_ddd_core.primitives.exceptions import ValidationError

# --- Test Models ---


class MyCommand(Command):
    data: str


class MyEvent:
    def model_dump(self):
        return {"foo": "bar"}


# --- LoggingMiddleware Tests ---


@pytest.mark.asyncio()
async def test_logging_middleware_logs_execution(caplog) -> None:
    caplog.set_level(logging.INFO)
    middleware = LoggingMiddleware()
    command = MyCommand(data="test")
    next_fn = AsyncMock(return_value=CommandResponse(result="ok"))

    await middleware(command, next_fn)

    assert "Handling MyCommand" in caplog.text
    assert "MyCommand completed in" in caplog.text


@pytest.mark.asyncio()
async def test_logging_middleware_logs_exception(caplog) -> None:
    caplog.set_level(logging.INFO)
    middleware = LoggingMiddleware()
    command = MyCommand(data="test")
    next_fn = AsyncMock(side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        await middleware(command, next_fn)

    assert "Handling MyCommand" in caplog.text
    assert "MyCommand failed after" in caplog.text


# --- ValidatorMiddleware Tests ---


@pytest.mark.asyncio()
async def test_validator_middleware_success() -> None:
    validator = AsyncMock(spec=IValidator)
    validator.validate.return_value = MagicMock(is_valid=True)
    middleware = ValidatorMiddleware(validator)
    command = MyCommand(data="valid")
    next_fn = AsyncMock(return_value=CommandResponse(result="ok"))

    result = await middleware(command, next_fn)

    assert result.result == "ok"
    validator.validate.assert_called_once_with(command)
    next_fn.assert_called_once_with(command)


@pytest.mark.asyncio()
async def test_validator_middleware_failure() -> None:
    validator = AsyncMock(spec=IValidator)
    validation_result = MagicMock(is_valid=False)
    validation_result.errors = {"field": ["error"]}
    validator.validate.return_value = validation_result
    middleware = ValidatorMiddleware(validator)
    command = MyCommand(data="invalid")
    next_fn = AsyncMock()

    with pytest.raises(ValidationError) as exc:
        await middleware(command, next_fn)

    assert exc.value.errors == {"field": ["error"]}
    next_fn.assert_not_called()


# --- EventStorePersistenceMiddleware Tests ---


@pytest.mark.asyncio()
async def test_persistence_middleware_saves_events() -> None:
    event_store = AsyncMock(spec=IEventStore)
    middleware = EventStorePersistenceMiddleware(event_store)
    command = MyCommand(data="test")

    event = MyEvent()
    response = CommandResponse(result="ok", events=[event])
    next_fn = AsyncMock(return_value=response)

    await middleware(command, next_fn)

    event_store.append_batch.assert_called_once()
    saved_events = event_store.append_batch.call_args[0][0]
    assert len(saved_events) == 1
    assert saved_events[0].event_type == "MyEvent"
    assert saved_events[0].payload == {"foo": "bar"}


@pytest.mark.asyncio()
async def test_persistence_middleware_no_events() -> None:
    event_store = AsyncMock(spec=IEventStore)
    middleware = EventStorePersistenceMiddleware(event_store)
    command = MyCommand(data="test")

    response = CommandResponse(result="ok", events=[])
    next_fn = AsyncMock(return_value=response)

    await middleware(command, next_fn)

    event_store.append_batch.assert_not_called()
