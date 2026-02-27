"""Tests for metadata sanitizer."""

from cqrs_ddd_notifications.sanitization import MetadataSanitizer, default_sanitizer


def test_default_sanitizer_redacts_sensitive_fields():
    """Test default sanitizer redacts sensitive fields."""
    sanitizer = MetadataSanitizer()

    metadata = {
        "event_id": "abc-123",
        "password": "secret123",
        "token": "xyz-token",
        "api_key": "secret-key",
        "normal_field": "keep-me",
    }

    result = sanitizer.sanitize(metadata)

    assert result["event_id"] == "abc-123"
    assert result["password"] == "***"
    assert result["token"] == "***"
    assert result["api_key"] == "***"
    assert result["normal_field"] == "keep-me"


def test_sanitizer_hash_fields():
    """Test sanitizer hashes specified fields."""
    sanitizer = MetadataSanitizer(hash_fields={"user_id"})

    metadata = {"user_id": "user-123", "name": "John"}

    result = sanitizer.sanitize(metadata)

    assert result["user_id"].startswith("sha256:")
    assert result["name"] == "John"


def test_sanitizer_custom_redact_fields():
    """Test sanitizer with custom redact fields."""
    sanitizer = MetadataSanitizer(redact_fields={"custom_secret"})

    metadata = {"custom_secret": "hidden", "public": "visible"}

    result = sanitizer.sanitize(metadata)

    assert result["custom_secret"] == "***"
    assert result["public"] == "visible"


def test_sanitizer_nested_structures():
    """Test sanitizer handles nested dicts and lists."""
    sanitizer = MetadataSanitizer()

    metadata = {
        "level1": {
            "password": "nested-secret",
            "level2": [
                {"token": "array-secret"},
                {"safe": "value"},
            ],
        },
    }

    result = sanitizer.sanitize(metadata)

    assert result["level1"]["password"] == "***"
    assert result["level1"]["level2"][0]["token"] == "***"
    assert result["level1"]["level2"][1]["safe"] == "value"


def test_default_sanitizer_instance():
    """Test default sanitizer instance."""
    metadata = {"password": "secret", "email": "user@example.com"}

    result = default_sanitizer.sanitize(metadata)

    assert result["password"] == "***"
    assert result["email"] == "user@example.com"  # Email NOT redacted (needed for delivery)
