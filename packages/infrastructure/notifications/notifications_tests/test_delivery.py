"""Tests for delivery types."""

from cqrs_ddd_notifications.delivery import DeliveryRecord, DeliveryStatus, NotificationChannel


def test_delivery_record_sent():
    """Test creating a successful delivery record."""
    record = DeliveryRecord.sent(
        recipient="+1234567890",
        channel=NotificationChannel.SMS,
        provider_id="msg-123",
    )

    assert record.recipient == "+1234567890"
    assert record.channel == NotificationChannel.SMS
    assert record.status == DeliveryStatus.SENT
    assert record.provider_id == "msg-123"
    assert record.error is None


def test_delivery_record_failed():
    """Test creating a failed delivery record."""
    record = DeliveryRecord.failed(
        recipient="user@example.com",
        channel=NotificationChannel.EMAIL,
        error="SMTP connection timeout",
    )

    assert record.recipient == "user@example.com"
    assert record.channel == NotificationChannel.EMAIL
    assert record.status == DeliveryStatus.FAILED
    assert record.provider_id is None
    assert record.error == "SMTP connection timeout"


def test_notification_channel_enum():
    """Test notification channel enum values."""
    assert NotificationChannel.EMAIL.value == "email"
    assert NotificationChannel.SMS.value == "sms"
    assert NotificationChannel.PUSH.value == "push"
    assert NotificationChannel.WEBHOOK.value == "webhook"
