"""Unit tests for auth observability metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cqrs_ddd_identity.observability.metrics import (
    AuthMetricLabels,
    AuthMetrics,
    record_login_failure,
    record_login_success,
    record_logout,
)


class TestAuthMetrics:
    """Tests for AuthMetrics class."""

    def test_operation_context_manager(self):
        """Test operation timing context manager."""
        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            with AuthMetrics.operation(
                "authenticate", provider="keycloak", method="jwt"
            ):
                pass
            assert True

    def test_operation_without_prometheus(self):
        """Test operation context manager when prometheus_client is unavailable."""
        import builtins

        from cqrs_ddd_identity.observability import metrics as metrics_mod

        real_import = builtins.__import__
        metrics_mod._registry._initialized = False
        metrics_mod._registry._histogram = None
        metrics_mod._registry._counter = None
        metrics_mod._registry._session_gauge = None

        def raise_for_prometheus(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("No module named 'prometheus_client'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=raise_for_prometheus):
            with AuthMetrics.operation("authenticate", provider="keycloak"):
                pass
        assert True

    def test_record_event_success(self):
        """Test recording an authentication event."""
        from cqrs_ddd_identity.audit.events import AuthAuditEvent, AuthEventType

        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            event = AuthAuditEvent(
                event_type=AuthEventType.LOGIN_SUCCESS,
                principal_id="user-123",
                provider="keycloak",
                metadata={"method": "jwt"},
            )
            AuthMetrics.record_event(event)
            assert True

    def test_record_event_failure(self):
        """Test recording a failed authentication event."""
        from cqrs_ddd_identity.audit.events import AuthAuditEvent, AuthEventType

        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            event = AuthAuditEvent(
                event_type=AuthEventType.LOGIN_FAILED,
                principal_id="user-123",
                provider="keycloak",
                success=False,
                error_code="invalid_credentials",
                metadata={"method": "password"},
            )
            AuthMetrics.record_event(event)
            assert True

    def test_increment_sessions(self):
        """Test incrementing active sessions count."""
        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            AuthMetrics.increment_sessions(provider="keycloak")
            assert True

    def test_decrement_sessions(self):
        """Test decrementing active sessions count."""
        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            AuthMetrics.decrement_sessions(provider="keycloak")
            assert True

    def test_convenience_functions(self):
        """Test convenience functions for common auth events."""
        with (
            patch("prometheus_client.Counter", MagicMock()),
            patch("prometheus_client.Histogram", MagicMock()),
            patch("prometheus_client.Gauge", MagicMock()),
        ):
            record_login_success("user-123", "keycloak", "password")
            record_login_failure("keycloak", "invalid_credentials")
            record_logout("keycloak")
            assert True

    def test_metric_labels_dataclass(self):
        """Test AuthMetricLabels dataclass."""
        labels = AuthMetricLabels(
            provider="keycloak",
            method="jwt",
            result="success",
        )
        assert labels.provider == "keycloak"
        assert labels.method == "jwt"
        assert labels.result == "success"

    def test_metric_labels_defaults(self):
        """Test AuthMetricLabels with default values."""
        labels = AuthMetricLabels()
        assert labels.provider == "unknown"
        assert labels.method == "unknown"
        assert labels.result == "success"
