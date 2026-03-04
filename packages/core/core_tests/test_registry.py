import logging

import pytest

from cqrs_ddd_core.cqrs.registry import HandlerRegistry
from cqrs_ddd_core.primitives.exceptions import HandlerRegistrationError


class Cmd1:
    pass


class Cmd2:
    pass


class Query1:
    pass


class Event1:
    pass


def handler_func(x) -> None:
    pass


class HandlerClass:
    pass


def test_registry_command_handlers(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    registry = HandlerRegistry()

    # Register success
    registry.register_command_handler(Cmd1, handler_func)
    assert registry.get_command_handler(Cmd1) is handler_func

    # Duplicate same handler - allowed (idempotent-ish in logic, or at least check impl)
    # The impl says: if existing is not None and existing is not handler_cls: raise
    registry.register_command_handler(Cmd1, handler_func)

    from cqrs_ddd_core.primitives.exceptions import HandlerRegistrationError

    # Duplicate different handler - raises
    with pytest.raises(HandlerRegistrationError, match="Duplicate command handler"):
        registry.register_command_handler(Cmd1, HandlerClass)

    # Introspection
    snapshot = registry.get_registered_handlers()
    assert "Cmd1" in snapshot["commands"]


def test_registry_query_handlers() -> None:
    registry = HandlerRegistry()

    registry.register_query_handler(Query1, handler_func)
    assert registry.get_query_handler(Query1) is handler_func

    with pytest.raises(HandlerRegistrationError, match="Duplicate query handler"):
        registry.register_query_handler(Query1, HandlerClass)


def test_registry_event_handlers() -> None:
    registry = HandlerRegistry()

    # Event handlers allow multiples
    registry.register_event_handler(Event1, handler_func, synchronous=True)
    registry.register_event_handler(Event1, HandlerClass, synchronous=False)

    # Check synchronous handlers
    sync_handlers = registry.get_synchronous_event_handlers(Event1)
    assert len(sync_handlers) == 1
    assert sync_handlers[0] == handler_func

    # Check asynchronous handlers
    async_handlers = registry.get_asynchronous_event_handlers(Event1)
    assert len(async_handlers) == 1
    assert async_handlers[0] == HandlerClass

    # Idempotency checks
    registry.register_event_handler(Event1, handler_func, synchronous=True)
    assert len(registry.get_synchronous_event_handlers(Event1)) == 1


def test_registry_clear() -> None:
    registry = HandlerRegistry()
    registry.register_command_handler(Cmd1, handler_func)
    registry.clear()
    assert registry.get_command_handler(Cmd1) is None
