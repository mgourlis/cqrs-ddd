"""MessageRegistry — maps message type names to their classes for deserialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .command import Command
    from .query import Query

Message = "Command[Any] | Query[Any]"


class MessageRegistry:
    """Registry for mapping message type names to their Command and Query classes.

    Used to reconstruct messages (commands and queries) from stored payloads.

    **Explicit registration** is required via ``register_command()`` or
    ``register_query()``. Create instances per application context for
    isolation.

    Usage::

        registry = MessageRegistry()
        registry.register_command("CreateOrderCommand", CreateOrderCommand)
        registry.register_query("GetOrderQuery", GetOrderQuery)

        cmd = registry.hydrate_command("CreateOrderCommand", {"order_id": "123"})
        query = registry.hydrate_query("GetOrderQuery", {"id": "123"})
    """

    def __init__(self) -> None:
        self._commands: dict[str, type[Command[Any]]] = {}
        self._queries: dict[str, type[Query[Any]]] = {}

    # ── Command Registration ─────────────────────────────────────

    def register_command(self, name: str, command_class: type[Command[Any]]) -> None:
        """Register a command class under *name*."""
        self._commands[name] = command_class

    def get_command(self, command_type: str) -> type[Command[Any]] | None:
        """Look up a command class by type name."""
        return self._commands.get(command_type)

    def has_command(self, command_type: str) -> bool:
        """Return ``True`` if *command_type* is registered."""
        return command_type in self._commands

    def hydrate_command(
        self, command_type: str, data: dict[str, Any]
    ) -> Command[Any] | None:
        """Reconstruct a command from its type name and payload dict.

        Returns ``None`` if the command type is not registered.
        """
        command_class = self.get_command(command_type)
        if command_class is None:
            return None

        try:
            return command_class.model_validate(data)
        except (TypeError, ValueError):
            return None

    # ── Query Registration ──────────────────────────────────────

    def register_query(self, name: str, query_class: type[Query[Any]]) -> None:
        """Register a query class under *name*."""
        self._queries[name] = query_class

    def get_query(self, query_type: str) -> type[Query[Any]] | None:
        """Look up a query class by type name."""
        return self._queries.get(query_type)

    def has_query(self, query_type: str) -> bool:
        """Return ``True`` if *query_type* is registered."""
        return query_type in self._queries

    def hydrate_query(self, query_type: str, data: dict[str, Any]) -> Query[Any] | None:
        """Reconstruct a query from its type name and payload dict.

        Returns ``None`` if the query type is not registered.
        """
        query_class = self.get_query(query_type)
        if query_class is None:
            return None

        try:
            return query_class.model_validate(data)
        except (TypeError, ValueError):
            return None

    # ── Generic Hydration ───────────────────────────────────────

    def hydrate(
        self, message_type: str, data: dict[str, Any]
    ) -> Command[Any] | Query[Any] | None:
        """Reconstruct a message (command or query) from type name and payload.

        Tries command registry first, then query registry.
        Returns ``None`` if type is not registered in either.
        """
        result = self.hydrate_command(message_type, data)
        if result is not None:
            return result

        return self.hydrate_query(message_type, data)

    # ── Introspection ───────────────────────────────────────────

    def list_registered_commands(self) -> list[str]:
        """Return all registered command type names."""
        return list(self._commands.keys())

    def list_registered_queries(self) -> list[str]:
        """Return all registered query type names."""
        return list(self._queries.keys())

    def list_all_registered(self) -> dict[str, list[str]]:
        """Return all registered message types grouped by kind."""
        return {
            "commands": self.list_registered_commands(),
            "queries": self.list_registered_queries(),
        }

    # ── Cleanup ─────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all registrations (testing utility)."""
        self._commands.clear()
        self._queries.clear()

    def clear_commands(self) -> None:
        """Remove all command registrations."""
        self._commands.clear()

    def clear_queries(self) -> None:
        """Remove all query registrations."""
        self._queries.clear()


__all__ = ["MessageRegistry"]
