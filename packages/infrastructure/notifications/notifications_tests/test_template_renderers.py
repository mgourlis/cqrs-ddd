"""Tests for template renderers."""

import pytest

from cqrs_ddd_notifications.delivery import NotificationChannel
from cqrs_ddd_notifications.ports.renderer import NotificationTemplate
from cqrs_ddd_notifications.template.engines.string import StringFormatRenderer

# Check if jinja2 is installed
try:
    import jinja2  # noqa: F401

    from cqrs_ddd_notifications.template.engines.jinja import JinjaTemplateRenderer

    _JINJA_AVAILABLE = True
except ImportError:
    _JINJA_AVAILABLE = False
    JinjaTemplateRenderer = None


@pytest.mark.asyncio
async def test_string_renderer_basic():
    """Test string format renderer."""
    renderer = StringFormatRenderer()

    template = NotificationTemplate(
        template_id="test",
        channel=NotificationChannel.EMAIL,
        body_template="Hello {name}, your order {order_id} is ready!",
        subject_template="Order Update",
        locale="en",
    )

    result = await renderer.render(template, {"name": "Alice", "order_id": "123"})

    assert result.subject == "Order Update"
    assert result.body_text == "Hello Alice, your order 123 is ready!"


@pytest.mark.asyncio
async def test_string_renderer_missing_variable():
    """Test string renderer raises on missing variable."""
    renderer = StringFormatRenderer()

    template = NotificationTemplate(
        template_id="test",
        channel=NotificationChannel.EMAIL,
        body_template="Hello {name}",
        locale="en",
    )

    with pytest.raises(KeyError):
        await renderer.render(template, {})


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="Jinja2 not installed")
@pytest.mark.asyncio
async def test_jinja_renderer_basic():
    """Test Jinja2 renderer."""
    renderer = JinjaTemplateRenderer()

    template = NotificationTemplate(
        template_id="test",
        channel=NotificationChannel.EMAIL,
        body_template="Hello {{ name }}, your order {{ order_id }} is ready!",
        subject_template="Order Update",
        locale="en",
    )

    result = await renderer.render(template, {"name": "Alice", "order_id": "123"})

    assert result.subject == "Order Update"
    assert result.body_text == "Hello Alice, your order 123 is ready!"


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="Jinja2 not installed")
@pytest.mark.asyncio
async def test_jinja_renderer_html_detection():
    """Test Jinja2 renderer detects HTML content."""
    renderer = JinjaTemplateRenderer()

    template = NotificationTemplate(
        template_id="test",
        channel=NotificationChannel.EMAIL,
        body_template="<html><body><h1>Hello {{ name }}</h1></body></html>",
        locale="en",
    )

    result = await renderer.render(template, {"name": "Alice"})

    assert result.body_html is not None
    assert "<html>" in result.body_html
