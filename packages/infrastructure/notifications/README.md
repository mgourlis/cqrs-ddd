# CQRS-DDD Notifications

Multi-channel notification infrastructure for CQRS/DDD applications. Provides Email, SMS, Push, and Webhook delivery capabilities triggered by Domain Events.

## Features

- **Framework-Agnostic**: Pure Python with no framework dependencies (Django, FastAPI, etc.)
- **Multi-Channel**: Support for Email, SMS, Push, and Webhook notifications
- **Template Engine**: Built-in Jinja2 and string format renderers
- **I18n Ready**: Locale-aware template resolution
- **Correlation Tracing**: Automatic propagation of correlation/causation IDs
- **Metadata Sanitization**: Prevents PII leakage into logs and provider dashboards
- **Testable**: In-memory and console adapters for development and testing

## Installation

```bash
# Core (minimum dependencies)
pip install cqrs-ddd-notifications

# With SMTP support
pip install cqrs-ddd-notifications[smtp]

# With HTTP support (Bulker.gr, Webhooks)
pip install cqrs-ddd-notifications[http]

# With AWS SES support
pip install cqrs-ddd-notifications[aws]

# With Jinja2 templating
pip install cqrs-ddd-notifications[jinja2]

# With Twilio support
pip install cqrs-ddd-notifications[twilio]

# All features
pip install cqrs-ddd-notifications[all]
```

## Quick Start

```python
from cqrs_ddd_notifications import (
    NotificationEventHandler,
    NotificationChannel,
    TemplateRegistry,
    StringFormatRenderer,
    InMemorySender,
    ChannelRouter,
)
from cqrs_ddd_notifications.memory.fake import SentMessage

# 1. Set up template registry
registry = TemplateRegistry()
registry.register("OrderShipped", NotificationTemplate(
    template_id="order_shipped_sms",
    channel=NotificationChannel.SMS,
    body_template="Hi {customer_name}, your order {order_id} is on the way!",
    locale="en"
))

# 2. Create a router
class OrderRouter(ChannelRouter):
    async def resolve(self, event):
        # Return RecipientInfo with recipient address and channels
        return RecipientInfo(
            address=event.customer_phone,
            channels=[NotificationChannel.SMS],
            locale="en",
        )

# 3. Set up handler
handler = NotificationEventHandler(
    sender=InMemorySender(),
    renderer=StringFormatRenderer(),
    registry=registry,
    router=OrderRouter(),
)

# 4. Handle domain event
await handler.handle(OrderShipped(
    order_id="123",
    customer_name="Alice",
    customer_phone="+1234567890",
))

# 5. Verify in tests
handler.sender.assert_sent("+1234567890", NotificationChannel.SMS)
```

## Supported Providers

### Email
- **SMTP** (`aiosmtplib`): Standard SMTP server support with TLS
- **AWS SES** (`aiobotocore`): AWS SES integration

### SMS
- **Bulker.gr** (`httpx`): Greek SMS provider
- **Twilio** (`twilio`): Global SMS provider

### Webhooks
- **Generic Webhooks** (`httpx`): HTTP POST with HMAC-SHA256 signature

## Architecture

The package follows the CQRS/DDD separation of concerns:

1. **Domain Layer**: Pure domain events (`OrderShipped`, `UserRegistered`, etc.)
2. **Application Layer**: Handlers that process domain events
3. **Infrastructure Layer**: This package - actual notification delivery

## Correlation Propagation

All notifications automatically include correlation context:

```python
# Metadata sent to providers
{
    "event_id": "abc-123",
    "event_type": "OrderShipped",
    "correlation_id": "xyz-789",
    "causation_id": "uvw-456",
}
```

Webhook headers include:
- `X-Correlation-ID`
- `X-Causation-ID`

## Metadata Sanitization

The `MetadataSanitizer` prevents PII leakage:

- Default sensitive fields: `password`, `token`, `api_key`, `secret`, etc.
- Customizable via constructor parameters
- Email/phone are preserved (needed for delivery)
- Hash or redact sensitive values

```python
from cqrs_ddd_notifications import MetadataSanitizer

sanitizer = MetadataSanitizer(
    redact_fields={"custom_field"},
    hash_fields={"user_id"},
)
```

## Template System

### String Format Renderer (Zero Dependencies)

```python
from cqrs_ddd_notifications import StringFormatRenderer

renderer = StringFormatRenderer()
# Uses Python's str.format() syntax
# "Hello {name}" -> "Hello World" with {"name": "World"}
```

### Jinja2 Renderer

```python
from cqrs_ddd_notifications import JinjaTemplateRenderer

renderer = JinjaTemplateRenderer()
# Supports conditionals, loops, filters, etc.
# "Hello {% if name %}{{ name }}{% endif %}"
```

### Filesystem Templates

```python
from pathlib import Path
from cqrs_ddd_notifications import FileSystemTemplateLoader

loader = FileSystemTemplateLoader(templates_dir=Path("templates"))
# templates/email/Welcome_en.j2
# templates/sms/TwoFactorCodeRequested_en.j2
```

## Testing

Use `InMemorySender` for test assertions:

```python
from cqrs_ddd_notifications.memory import InMemorySender

sender = InMemorySender()
await handler.handle(event)

# Assert message was sent
sender.assert_sent("+1234567890", NotificationChannel.SMS, count=1)

# Clear for next test
sender.clear()
```

Use `ConsoleSender` for local development:

```python
from cqrs_ddd_notifications.memory import ConsoleSender

sender = ConsoleSender()
await handler.handle(event)
# Prints nicely formatted notification to stdout
```

## Development Adapters

### InMemorySender
- Records all sent messages for test assertions
- `assert_sent(recipient, channel, count)` helper
- `clear()` method to reset between tests

### ConsoleSender
- Prints notifications to console for debugging
- Shows subject, body, attachments, HTML info
- Optionally logs via logger

## License

MIT
