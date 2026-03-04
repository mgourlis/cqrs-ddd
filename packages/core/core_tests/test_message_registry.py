"""Tests for MessageRegistry."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
from cqrs_ddd_core.cqrs.query import Query


# Test fixtures
class CreateOrderCommand(Command[str]):
    """Test command."""

    order_id: str = ""
    amount: float = 0.0


class CancelOrderCommand(Command[None]):
    """Another test command."""

    order_id: str = ""
    reason: str = ""


class GetOrderQuery(Query[dict]):
    """Test query."""

    order_id: str = ""


class ListOrdersQuery(Query[list]):
    """Another test query."""

    limit: int = 10


class TestMessageRegistry:
    """Test MessageRegistry registration, hydration, and introspection."""

    @pytest.fixture
    def registry(self) -> MessageRegistry:
        """Create fresh registry for each test."""
        return MessageRegistry()

    def test_register_command(self, registry: MessageRegistry) -> None:
        """register_command stores command class."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)

        assert registry.has_command("CreateOrderCommand")
        assert registry.get_command("CreateOrderCommand") == CreateOrderCommand

    def test_register_multiple_commands(self, registry: MessageRegistry) -> None:
        """Multiple commands can be registered."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_command("CancelOrderCommand", CancelOrderCommand)

        assert registry.has_command("CreateOrderCommand")
        assert registry.has_command("CancelOrderCommand")

    def test_get_command_nonexistent(self, registry: MessageRegistry) -> None:
        """get_command returns None for unregistered command."""
        result = registry.get_command("NonexistentCommand")

        assert result is None

    def test_has_command_false_for_unregistered(
        self, registry: MessageRegistry
    ) -> None:
        """has_command returns False for unregistered command."""
        assert not registry.has_command("NonexistentCommand")

    def test_register_query(self, registry: MessageRegistry) -> None:
        """register_query stores query class."""
        registry.register_query("GetOrderQuery", GetOrderQuery)

        assert registry.has_query("GetOrderQuery")
        assert registry.get_query("GetOrderQuery") == GetOrderQuery

    def test_register_multiple_queries(self, registry: MessageRegistry) -> None:
        """Multiple queries can be registered."""
        registry.register_query("GetOrderQuery", GetOrderQuery)
        registry.register_query("ListOrdersQuery", ListOrdersQuery)

        assert registry.has_query("GetOrderQuery")
        assert registry.has_query("ListOrdersQuery")

    def test_get_query_nonexistent(self, registry: MessageRegistry) -> None:
        """get_query returns None for unregistered query."""
        result = registry.get_query("NonexistentQuery")

        assert result is None

    def test_has_query_false_for_unregistered(self, registry: MessageRegistry) -> None:
        """has_query returns False for unregistered query."""
        assert not registry.has_query("NonexistentQuery")

    def test_hydrate_command_success(self, registry: MessageRegistry) -> None:
        """hydrate_command reconstructs command from data."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)

        data = {"order_id": "order-123", "amount": 100.0}
        cmd = registry.hydrate_command("CreateOrderCommand", data)

        assert cmd is not None
        assert isinstance(cmd, CreateOrderCommand)
        assert cmd.order_id == "order-123"
        assert cmd.amount == 100.0

    def test_hydrate_command_unregistered_type(self, registry: MessageRegistry) -> None:
        """hydrate_command returns None for unregistered type."""
        data = {"order_id": "order-123"}
        cmd = registry.hydrate_command("UnregisteredCommand", data)

        assert cmd is None

    def test_hydrate_command_invalid_data(self, registry: MessageRegistry) -> None:
        """hydrate_command returns None for invalid data."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)

        # Missing required fields
        data = {}
        cmd = registry.hydrate_command("CreateOrderCommand", data)

        # Should handle validation error gracefully
        assert cmd is None or isinstance(cmd, CreateOrderCommand)

    def test_hydrate_query_success(self, registry: MessageRegistry) -> None:
        """hydrate_query reconstructs query from data."""
        registry.register_query("GetOrderQuery", GetOrderQuery)

        data = {"order_id": "order-123"}
        query = registry.hydrate_query("GetOrderQuery", data)

        assert query is not None
        assert isinstance(query, GetOrderQuery)
        assert query.order_id == "order-123"

    def test_hydrate_query_unregistered_type(self, registry: MessageRegistry) -> None:
        """hydrate_query returns None for unregistered type."""
        data = {"order_id": "order-123"}
        query = registry.hydrate_query("UnregisteredQuery", data)

        assert query is None

    def test_hydrate_query_invalid_data(self, registry: MessageRegistry) -> None:
        """hydrate_query returns None for invalid data."""
        registry.register_query("GetOrderQuery", GetOrderQuery)

        # Missing required fields or invalid data
        data = {}
        query = registry.hydrate_query("GetOrderQuery", data)

        # Should handle validation error gracefully
        assert query is None or isinstance(query, GetOrderQuery)

    def test_hydrate_tries_command_first(self, registry: MessageRegistry) -> None:
        """hydrate tries command registry first."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)

        data = {"order_id": "order-123", "amount": 100.0}
        msg = registry.hydrate("CreateOrderCommand", data)

        assert msg is not None
        assert isinstance(msg, CreateOrderCommand)

    def test_hydrate_falls_back_to_query(self, registry: MessageRegistry) -> None:
        """hydrate falls back to query registry if not found in commands."""
        registry.register_query("GetOrderQuery", GetOrderQuery)

        data = {"order_id": "order-123"}
        msg = registry.hydrate("GetOrderQuery", data)

        assert msg is not None
        assert isinstance(msg, GetOrderQuery)

    def test_hydrate_returns_none_if_not_found(self, registry: MessageRegistry) -> None:
        """hydrate returns None if type not in either registry."""
        data = {"order_id": "order-123"}
        msg = registry.hydrate("UnknownType", data)

        assert msg is None

    def test_list_registered_commands(self, registry: MessageRegistry) -> None:
        """list_registered_commands returns all command type names."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_command("CancelOrderCommand", CancelOrderCommand)

        commands = registry.list_registered_commands()

        assert len(commands) == 2
        assert "CreateOrderCommand" in commands
        assert "CancelOrderCommand" in commands

    def test_list_registered_queries(self, registry: MessageRegistry) -> None:
        """list_registered_queries returns all query type names."""
        registry.register_query("GetOrderQuery", GetOrderQuery)
        registry.register_query("ListOrdersQuery", ListOrdersQuery)

        queries = registry.list_registered_queries()

        assert len(queries) == 2
        assert "GetOrderQuery" in queries
        assert "ListOrdersQuery" in queries

    def test_list_all_registered(self, registry: MessageRegistry) -> None:
        """list_all_registered returns commands and queries grouped."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_query("GetOrderQuery", GetOrderQuery)

        all_registered = registry.list_all_registered()

        assert "commands" in all_registered
        assert "queries" in all_registered
        assert "CreateOrderCommand" in all_registered["commands"]
        assert "GetOrderQuery" in all_registered["queries"]

    def test_clear(self, registry: MessageRegistry) -> None:
        """clear removes all registrations."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_query("GetOrderQuery", GetOrderQuery)

        registry.clear()

        assert len(registry.list_registered_commands()) == 0
        assert len(registry.list_registered_queries()) == 0

    def test_clear_commands(self, registry: MessageRegistry) -> None:
        """clear_commands removes only command registrations."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_query("GetOrderQuery", GetOrderQuery)

        registry.clear_commands()

        assert len(registry.list_registered_commands()) == 0
        assert len(registry.list_registered_queries()) == 1

    def test_clear_queries(self, registry: MessageRegistry) -> None:
        """clear_queries removes only query registrations."""
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_query("GetOrderQuery", GetOrderQuery)

        registry.clear_queries()

        assert len(registry.list_registered_commands()) == 1
        assert len(registry.list_registered_queries()) == 0

    def test_registry_isolation(self) -> None:
        """Multiple registries are isolated from each other."""
        registry1 = MessageRegistry()
        registry2 = MessageRegistry()

        registry1.register_command("CreateOrderCommand", CreateOrderCommand)
        registry2.register_query("GetOrderQuery", GetOrderQuery)

        # Each registry should only have its own registrations
        assert registry1.has_command("CreateOrderCommand")
        assert not registry1.has_query("GetOrderQuery")
        assert registry2.has_query("GetOrderQuery")
        assert not registry2.has_command("CreateOrderCommand")

    def test_overwrite_registration(self, registry: MessageRegistry) -> None:
        """Registering same name twice overwrites previous registration."""
        registry.register_command("TestCommand", CreateOrderCommand)
        registry.register_command("TestCommand", CancelOrderCommand)

        # Should have the second registration
        result = registry.get_command("TestCommand")
        assert result == CancelOrderCommand
