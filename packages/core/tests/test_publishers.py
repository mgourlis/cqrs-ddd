"""Tests for the Publishers package."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_core.cqrs import (
    PublishingEventHandler,
    TopicRoutingPublisher,
    route_to,
)
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.ports.messaging import IMessagePublisher
from cqrs_ddd_core.primitives.exceptions import PublisherNotFoundError

# ============================================================================
# Test Events
# ============================================================================


class DummyEvent(DomainEvent):
    """Test event."""

    message: str = "test"


@route_to("fast")
class FastEvent(DomainEvent):
    """Event routed to 'fast' destination."""

    data: str = "fast"


@route_to("slow")
class SlowEvent(DomainEvent):
    """Event routed to 'slow' destination."""

    data: str = "slow"


# ============================================================================
# Mock Publishers
# ============================================================================


class DummyPublisher(IMessagePublisher):
    """In-memory mock publisher for testing."""

    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        self.published.append((topic, message))


class FailingPublisher(IMessagePublisher):
    """Publisher that always fails."""

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        raise ValueError("Intentional failure")


# ============================================================================
# Tests: PublishingEventHandler
# ============================================================================


class TestPublishingEventHandler:
    """Test the PublishingEventHandler."""

    @pytest.mark.asyncio()
    async def test_publish_event_uses_class_name_as_topic(self) -> None:
        """Handler should use event class name as topic."""
        publisher = DummyPublisher()
        handler = PublishingEventHandler(publisher)
        event = DummyEvent()

        await handler.handle(event)

        assert len(publisher.published) == 1
        assert publisher.published[0][0] == "DummyEvent"
        assert publisher.published[0][1] is event

    @pytest.mark.asyncio()
    async def test_publish_event_reraises_on_failure(self) -> None:
        """Handler should re-raise exceptions from publisher."""
        publisher = FailingPublisher()
        handler = PublishingEventHandler(publisher)
        event = DummyEvent()

        with pytest.raises(ValueError, match="Intentional failure"):
            await handler.handle(event)


# ============================================================================
# Tests: TopicRoutingPublisher
# ============================================================================


class TestTopicRoutingPublisher:
    """Test the TopicRoutingPublisher routing logic."""

    @pytest.mark.asyncio()
    async def test_route_direct_topic_match(self) -> None:
        """Router should use explicit topic route."""
        pub1 = DummyPublisher()
        pub2 = DummyPublisher()

        router = TopicRoutingPublisher(routes={"DummyEvent": pub1, "OtherEvent": pub2})

        await router.publish("DummyEvent", DummyEvent())

        assert len(pub1.published) == 1
        assert len(pub2.published) == 0

    @pytest.mark.asyncio()
    async def test_route_to_destination_key(self) -> None:
        """Router should resolve @route_to destination keys."""
        fast_pub = DummyPublisher()
        slow_pub = DummyPublisher()

        router = TopicRoutingPublisher(
            destinations={"fast": fast_pub, "slow": slow_pub}
        )

        await router.publish("FastEvent", FastEvent())
        await router.publish("SlowEvent", SlowEvent())

        assert len(fast_pub.published) == 1
        assert len(slow_pub.published) == 1

    @pytest.mark.asyncio()
    async def test_explicit_route_overrides_destination(self) -> None:
        """Explicit topic route should override @route_to destination."""
        fast_pub = DummyPublisher()
        slow_pub = DummyPublisher()
        override_pub = DummyPublisher()

        router = TopicRoutingPublisher(
            routes={"FastEvent": override_pub},  # Override
            destinations={"fast": fast_pub, "slow": slow_pub},
        )

        await router.publish("FastEvent", FastEvent())

        assert len(override_pub.published) == 1
        assert len(fast_pub.published) == 0

    @pytest.mark.asyncio()
    async def test_fallback_to_default(self) -> None:
        """Router should fall back to default if no route found."""
        default_pub = DummyPublisher()
        router = TopicRoutingPublisher(default=default_pub)

        await router.publish("UnknownEvent", DummyEvent())

        assert len(default_pub.published) == 1

    @pytest.mark.asyncio()
    async def test_no_publisher_raises_error(self) -> None:
        """Router should raise PublisherNotFoundError if no publisher found (no default)."""
        router = TopicRoutingPublisher()

        with pytest.raises(PublisherNotFoundError, match="No publisher configured"):
            await router.publish("UnknownEvent", DummyEvent())

    @pytest.mark.asyncio()
    async def test_register_route_at_runtime(self) -> None:
        """register_route() should add routes dynamically."""
        pub = DummyPublisher()
        router = TopicRoutingPublisher()

        router.register_route("DummyEvent", pub)

        await router.publish("DummyEvent", DummyEvent())

        assert len(pub.published) == 1
