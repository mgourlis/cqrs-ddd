#!/usr/bin/env python
"""Demo: Dependency-injected HandlerRegistry (no global singleton)."""

from __future__ import annotations

from typing import Any

from src.cqrs_ddd_core import (
    Command,
    CommandHandler,
    CommandResponse,
    HandlerRegistry,
    Mediator,
    Query,
    QueryHandler,
    QueryResponse,
)

# ─── Domain ───────────────────────────────────────────────────────


class CreateOrderCommand(Command):  # type: ignore[misc]
    """Example command."""

    order_id: str
    amount: float


class GetOrderQuery(Query):  # type: ignore[misc]
    """Example query."""

    order_id: str


class OrderCreatedEvent:
    """Example domain event."""

    order_id: str
    amount: float


# ─── Handlers (no auto-registration) ───────────────────────────────


class CreateOrderHandler(CommandHandler[CreateOrderCommand, str]):  # type: ignore[misc]
    """Handle CreateOrderCommand.

    **Must be registered explicitly** with registry.
    """

    async def handle(self, command: CreateOrderCommand) -> CommandResponse[str]:
        print(f"  ✓ CreateOrderHandler.handle({command.order_id})")
        return CommandResponse(
            result=command.order_id,
            events=[],
        )


class GetOrderHandler(QueryHandler[GetOrderQuery, dict]):  # type: ignore[misc]
    """Handle GetOrderQuery.

    **Must be registered explicitly** with registry.
    """

    async def handle(self, query: GetOrderQuery) -> QueryResponse[dict]:
        print(f"  ✓ GetOrderHandler.handle({query.order_id})")
        return QueryResponse(result={"order_id": query.order_id, "amount": 99.99})


# ─── Async Demo ───────────────────────────────────────────────────


async def demo_injection_based_registry() -> None:
    """Show the new dependency-injection pattern (no global singleton)."""
    print("\n=== Demo: Injection-Based HandlerRegistry ===\n")

    # 1. Create a registry instance (not a global singleton)
    print("1. Create a HandlerRegistry instance:")
    registry = HandlerRegistry()
    print(f"   registry = HandlerRegistry()  # {id(registry)}")

    # 2. Register handlers explicitly
    print("\n2. Register handlers explicitly (no auto-discovery):")
    registry.register_command_handler(CreateOrderCommand, CreateOrderHandler)
    print(
        "   registry.register_command_handler(CreateOrderCommand, CreateOrderHandler)"
    )
    registry.register_query_handler(GetOrderQuery, GetOrderHandler)
    print("   registry.register_query_handler(GetOrderQuery, GetOrderHandler)")

    # 3. Create a Mediator with the registry instance
    print("\n3. Inject registry into Mediator:")

    class DummyUoW:
        """Dummy UoW for demo."""

        async def __aenter__(self) -> DummyUoW:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

    def uow_factory() -> DummyUoW:
        """Return a new UoW instance."""
        return DummyUoW()

    mediator = Mediator(registry=registry, uow_factory=uow_factory)
    print("   mediator = Mediator(registry=registry, uow_factory=...)")

    # 4. Use the mediator
    print("\n4. Dispatch command and query:")
    cmd = CreateOrderCommand(order_id="ORD-123", amount=199.99)
    print("   await mediator.send(CreateOrderCommand(...))")
    result = await mediator.send(cmd)
    print(f"   → CommandResponse(result={result.result})")

    qry = GetOrderQuery(order_id="ORD-123")
    print("   await mediator.query(GetOrderQuery(...))")
    result = await mediator.query(qry)
    print(f"   → QueryResponse(result={result.result})")

    print("\n✓ Each Mediator instance has its own registry (no hidden global state)")
    print("✓ Multiple isolated message buses can coexist")
    print("✓ Perfect for testing with mock registries\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_injection_based_registry())
