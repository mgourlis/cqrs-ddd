import pytest

from cqrs_ddd_core.cqrs import (
    Command,
    CommandResponse,
    EventDispatcher,
    HandlerRegistry,
    Mediator,
)
from cqrs_ddd_core.domain.events import DomainEvent


class MockEvent(DomainEvent):
    pass


class MockCommand(Command[str]):
    pass


class PriorityHandler:
    def __init__(self):
        self.called = False

    async def handle(self, event: MockEvent):
        self.called = True


class BackgroundHandler:
    def __init__(self):
        self.called = False

    async def handle(self, event: MockEvent):
        self.called = True


@pytest.mark.asyncio()
async def test_registry_to_dispatcher_mapping():
    # Setup
    registry = HandlerRegistry()
    registry.register_event_handler(MockEvent, PriorityHandler, synchronous=True)
    registry.register_event_handler(MockEvent, BackgroundHandler, synchronous=False)

    dispatcher = EventDispatcher()

    # We need to provide a factory that returns our pre-built instances for tracking
    p_handler = PriorityHandler()
    b_handler = BackgroundHandler()

    def factory(cls):
        if cls == PriorityHandler:
            return p_handler
        if cls == BackgroundHandler:
            return b_handler
        return cls()

    # Act
    # Manual wiring check (since we removed dispatcher.load_from_registry)
    for event_type in [MockEvent]:
        for h_cls in registry.get_synchronous_event_handlers(event_type):
            dispatcher.register(event_type, factory(h_cls))
        for h_cls in registry.get_asynchronous_event_handlers(event_type):
            dispatcher.register(event_type, factory(h_cls))

    # Verify mapping (all handlers are in the same list now)
    assert len(dispatcher._handlers[MockEvent]) == 2
    assert p_handler in dispatcher._handlers[MockEvent]
    assert b_handler in dispatcher._handlers[MockEvent]


@pytest.mark.asyncio()
async def test_mediator_dispatches_only_sync_from_consolidated_registry():
    # Setup
    registry = HandlerRegistry()
    p_handler = PriorityHandler()
    b_handler = BackgroundHandler()

    class TestCommandHandler:
        async def handle(self, cmd: MockCommand):
            return CommandResponse(result="ok", events=[MockEvent()])

    registry.register_command_handler(MockCommand, TestCommandHandler)
    registry.register_event_handler(MockEvent, PriorityHandler, synchronous=True)
    registry.register_event_handler(MockEvent, BackgroundHandler, synchronous=False)

    dispatcher = EventDispatcher()

    def factory(cls):
        if cls == PriorityHandler:
            return p_handler
        if cls == BackgroundHandler:
            return b_handler
        if cls == TestCommandHandler:
            return TestCommandHandler()
        return cls()

    # Mock UoW
    class MockUoW:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    mediator = Mediator(
        registry=registry,
        uow_factory=lambda: MockUoW(),
        event_dispatcher=dispatcher,
        handler_factory=factory,
    )

    # Act
    # No need to call mediator.autoload_event_handlers() manually

    # Verify: Background handler should NOT be loaded into the dispatcher
    assert len(dispatcher._handlers.get(MockEvent, [])) == 1
    assert dispatcher._handlers[MockEvent][0] == p_handler

    await mediator.send(MockCommand())

    # Verify
    assert p_handler.called is True
    # Background handlers were NOT loaded into this dispatcher instance
    assert b_handler.called is False
