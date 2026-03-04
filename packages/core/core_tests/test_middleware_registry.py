from unittest.mock import Mock

from cqrs_ddd_core.middleware.registry import MiddlewareRegistry


class Middleware1:
    def apply(self, c, n) -> None:
        pass


class Middleware2:
    def apply(self, c, n) -> None:
        pass


class Middleware3:
    def apply(self, c, n) -> None:
        pass


def test_middleware_registry_ordering() -> None:
    registry = MiddlewareRegistry()

    # Register with different priorities
    registry.register(Middleware2, priority=10)
    registry.register(Middleware1, priority=0)
    registry.register(Middleware3, priority=5)

    ordered = registry.get_ordered_middlewares()

    # Expected order: 0, 5, 10
    assert isinstance(ordered[0], Middleware1)
    assert isinstance(ordered[1], Middleware3)
    assert isinstance(ordered[2], Middleware2)


def test_middleware_registry_decorator() -> None:
    registry = MiddlewareRegistry()

    @registry.add(priority=99)
    class DecoratedMiddleware:
        def apply(self, c, n) -> None:
            pass

    ordered = registry.get_ordered_middlewares()
    assert len(ordered) == 1
    assert isinstance(ordered[0], DecoratedMiddleware)


def test_middleware_registry_factory() -> None:
    registry = MiddlewareRegistry()

    factory_mock = Mock(return_value=Middleware1())

    registry.register(Middleware1, factory=factory_mock, foo="bar")

    ordered = registry.get_ordered_middlewares()
    assert len(ordered) == 1
    factory_mock.assert_called_once()
    assert factory_mock.call_args[1]["foo"] == "bar"


def test_middleware_registry_clear() -> None:
    registry = MiddlewareRegistry()
    registry.register(Middleware1)
    registry.clear()
    assert len(registry.get_ordered_middlewares()) == 0
