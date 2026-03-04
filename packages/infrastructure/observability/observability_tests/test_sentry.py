"""Tests for SentryMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_observability.sentry import SentryMiddleware


@pytest.mark.asyncio
async def test_sentry_without_sentry_sdk():
    """Test middleware works without sentry_sdk installed."""
    import builtins

    real_import = builtins.__import__

    def raise_for_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=raise_for_sentry):
        mw = SentryMiddleware()
        next_handler = AsyncMock(return_value="ok")
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        result = await mw(message, next_handler)
        assert result == "ok"
        next_handler.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_sentry_does_not_capture_success():
    """Test middleware does not capture successful operations."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mw = SentryMiddleware()
        next_handler = AsyncMock(return_value="ok")
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        result = await mw(message, next_handler)

        assert result == "ok"
        # Should not call capture_exception on success
        mock_sentry_sdk.capture_exception.assert_not_called()


@pytest.mark.asyncio
async def test_sentry_captures_exception():
    """Test middleware captures exception with context."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    test_exception = ValueError("Test error")

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=test_exception)
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        with pytest.raises(ValueError, match="Test error"):
            await mw(message, next_handler)

        # Should capture exception
        mock_sentry_sdk.capture_exception.assert_called_once_with(test_exception)


@pytest.mark.asyncio
async def test_sentry_sets_message_type_tag():
    """Test middleware sets message_type tag on error."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=RuntimeError("Error"))
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        with pytest.raises(RuntimeError):
            await mw(message, next_handler)

        # Should set message_type tag
        mock_scope.set_tag.assert_any_call("cqrs.message_type", "TestMessage")


@pytest.mark.asyncio
async def test_sentry_sets_correlation_id_from_context():
    """Test middleware sets correlation_id from context."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=fake_import),
        patch(
            "cqrs_ddd_observability.sentry.get_correlation_id",
            return_value="test-correlation-123",
        ),
    ):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=RuntimeError("Error"))
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        with pytest.raises(RuntimeError):
            await mw(message, next_handler)

        # Should set correlation_id tag
        mock_scope.set_tag.assert_any_call("correlation_id", "test-correlation-123")


@pytest.mark.asyncio
async def test_sentry_sets_correlation_id_from_message():
    """Test middleware sets correlation_id from message when context is None."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=fake_import),
        patch("cqrs_ddd_observability.sentry.get_correlation_id", return_value=None),
    ):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=RuntimeError("Error"))
        message = type(
            "TestMessage",
            (),
            {"__name__": "TestMessage", "correlation_id": "msg-correlation-456"},
        )()

        with pytest.raises(RuntimeError):
            await mw(message, next_handler)

        # Should set correlation_id from message
        mock_scope.set_tag.assert_any_call("correlation_id", "msg-correlation-456")


@pytest.mark.asyncio
async def test_sentry_skips_correlation_id_when_none():
    """Test middleware does not set correlation_id when both context and message are None."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=fake_import),
        patch("cqrs_ddd_observability.sentry.get_correlation_id", return_value=None),
    ):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=RuntimeError("Error"))
        message = type(
            "TestMessage", (), {"__name__": "TestMessage"}
        )()  # No correlation_id attribute

        with pytest.raises(RuntimeError):
            await mw(message, next_handler)

        # Should not set correlation_id tag
        # Check that set_tag was called for message_type but not for correlation_id
        tag_names = [args[0] for args, _ in mock_scope.set_tag.call_args_list]
        assert "cqrs.message_type" in tag_names
        assert "correlation_id" not in tag_names


@pytest.mark.asyncio
async def test_sentry_handles_capture_exception_failure():
    """Test middleware handles sentry capture_exception failures gracefully."""
    import builtins

    real_import = builtins.__import__
    mock_scope = MagicMock()
    mock_sentry_sdk = MagicMock()
    mock_sentry_sdk.capture_exception.side_effect = RuntimeError("Sentry API failed")
    mock_sentry_sdk.configure_scope.return_value.__enter__.return_value = mock_scope

    test_exception = ValueError("Original error")

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            return mock_sentry_sdk
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        mw = SentryMiddleware()
        next_handler = AsyncMock(side_effect=test_exception)
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        # Should still raise original error even if sentry fails
        with pytest.raises(ValueError, match="Original error"):
            await mw(message, next_handler)
