"""
Example: Integrating NotificationEventHandler with HandlerRegistry and EventDispatcher

This demonstrates how to use NotificationEventHandler within the existing CQRS/DDD
infrastructure pattern.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

# Core CQRS/DDD imports
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher
from cqrs_ddd_core.cqrs.registry import HandlerRegistry
from cqrs_ddd_core.domain.events import DomainEvent

# Notifications imports
from cqrs_ddd_notifications import (
    NotificationChannel,
    NotificationEventHandler,
    NotificationTemplate,
    StringFormatRenderer,
    TemplateRegistry,
)
from cqrs_ddd_notifications.channel import ChannelRouter, RecipientInfo
from cqrs_ddd_notifications.memory.console import ConsoleSender
from cqrs_ddd_notifications.sanitization import MetadataSanitizer

# ── Domain Events ─────────────────────────────────────────────


@dataclass
class OrderShipped(DomainEvent):
    """Domain event emitted when an order is shipped."""

    order_id: str
    customer_name: str
    customer_phone: str
    tracking_number: str


@dataclass
class UserRegistered(DomainEvent):
    """Domain event emitted when a user registers."""

    user_id: str
    username: str
    email: str


# ── Channel Router ──────────────────────────────────────────────


class OrderEventRouter(ChannelRouter):
    """Routes order-related events to appropriate channels."""

    async def resolve(self, event: DomainEvent) -> RecipientInfo | None:
        if isinstance(event, OrderShipped):
            return RecipientInfo(
                address=event.customer_phone,
                channels=[NotificationChannel.SMS],
                locale="en",
            )
        return None


class UserEventRouter(ChannelRouter):
    """Routes user-related events to appropriate channels."""

    async def resolve(self, event: DomainEvent) -> RecipientInfo | None:
        if isinstance(event, UserRegistered):
            return RecipientInfo(
                address=event.email,
                channels=[NotificationChannel.EMAIL],
                locale="en",
            )
        return None


# ── Notification Context Builder ─────────────────────────────────


class NotificationContextBuilder:
    """
    Builds template context from domain events.

    This abstracts the knowledge of how to extract notification-relevant
    data from domain events.
    """

    def build(self, event: DomainEvent) -> dict[str, Any]:
        """
        Build template context from event.

        The context contains only the data needed for rendering templates.
        Sensitive fields are extracted explicitly rather than using raw event.__dict__.
        """
        if isinstance(event, OrderShipped):
            return {
                "order_id": event.order_id,
                "customer_name": event.customer_name,
                "tracking_number": event.tracking_number,
            }
        elif isinstance(event, UserRegistered):
            return {
                "username": event.username,
                "user_id": event.user_id,
            }
        else:
            return {}


# ── Application Bootstrap ────────────────────────────────────────


async def bootstrap_notification_system() -> EventDispatcher[Any]:
    """
    Bootstrap the notification system with all required components.

    This demonstrates the recommended pattern for setting up a complete
    notification infrastructure.
    """
    # 1. Create template registry
    template_registry = TemplateRegistry()

    # Register templates for all event types
    await template_registry.register(
        "OrderShipped",
        NotificationTemplate(
            template_id="order_shipped_sms",
            channel=NotificationChannel.SMS,
            subject_template=None,
            body_template="Hi {customer_name}, your order {order_id} has shipped! Track it: {tracking_number}",
            locale="en",
        ),
    )

    await template_registry.register(
        "UserRegistered",
        NotificationTemplate(
            template_id="user_welcome_email",
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome to our platform, {username}!",
            body_template=(
                "Hello {username},\n\n"
                "Thank you for registering! Your account is now active.\n\n"
                "Your user ID: {user_id}\n\n"
                "Best regards,\nThe Team"
            ),
            locale="en",
        ),
    )

    # 2. Create dependencies
    sender = ConsoleSender(output_to_stdout=True)
    renderer = StringFormatRenderer()
    sanitizer = MetadataSanitizer()
    NotificationContextBuilder()

    # 3. Create a router that handles all event types
    class UnifiedRouter(ChannelRouter):
        """Combines routing logic from multiple domain routers."""

        def __init__(self, routers: list[ChannelRouter]):
            self.routers = routers

        async def resolve(self, event: DomainEvent) -> RecipientInfo | None:
            for router in self.routers:
                result = await router.resolve(event)
                if result:
                    return result
            return None

    unified_router = UnifiedRouter([OrderEventRouter(), UserEventRouter()])

    # 4. Create notification handler
    notification_handler = NotificationEventHandler(
        sender=sender,
        renderer=renderer,
        registry=template_registry,
        router=unified_router,
        sanitizer=sanitizer,
    )

    # 5. Register with HandlerRegistry (optional, for discovery)
    registry = HandlerRegistry()
    registry.register_event_handler(
        OrderShipped,
        NotificationEventHandler,
        synchronous=True,
    )
    registry.register_event_handler(
        UserRegistered,
        NotificationEventHandler,
        synchronous=True,
    )

    # 6. Create EventDispatcher and wire up handler instances
    dispatcher: EventDispatcher[Any] = EventDispatcher()

    # Register the handler instance with the dispatcher
    dispatcher.register(OrderShipped, notification_handler)
    dispatcher.register(UserRegistered, notification_handler)

    return dispatcher


# ── Example Usage ──────────────────────────────────────────────


async def main() -> None:
    """Run the example demonstrating the notification system."""

    print("=" * 70)
    print("CQRS/DDD Notification System - Integration Example")
    print("=" * 70)
    print()

    # Bootstrap the system
    dispatcher = await bootstrap_notification_system()

    print("✓ Notification system bootstrapped")
    print()

    # Create and dispatch events
    print("─" * 70)
    print("Event 1: Order Shipped")
    print("─" * 70)

    order_shipped = OrderShipped.model_validate(
        {
            "order_id": "ORD-12345",
            "customer_name": "Alice Johnson",
            "customer_phone": "+1234567890",
            "tracking_number": "TRK-ABC123",
        }
    )

    await dispatcher.dispatch([order_shipped])

    print()
    print("─" * 70)
    print("Event 2: User Registered")
    print("─" * 70)

    user_registered = UserRegistered.model_validate(
        {
            "user_id": "USR-67890",
            "username": "alice_j",
            "email": "alice@example.com",
        }
    )

    await dispatcher.dispatch([user_registered])

    print()
    print("=" * 70)
    print("Example completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
