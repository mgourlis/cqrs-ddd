"""Test configuration for cqrs-ddd-notifications."""

import pytest

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def event():
    """Sample domain event for testing."""

    class SampleEvent:
        def __init__(self, **kwargs):
            self.id = "event-123"
            for key, value in kwargs.items():
                setattr(self, key, value)

    return SampleEvent(
        customer_name="Alice",
        order_id="123",
        email="alice@example.com",
        phone="+1234567890",
    )


@pytest.fixture
def notification_content():
    """Sample rendered notification."""
    from cqrs_ddd_notifications.delivery import RenderedNotification

    return RenderedNotification(
        body_text="Test message body",
        subject="Test Subject",
    )
