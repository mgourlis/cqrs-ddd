"""Unit tests for auth observability tracing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.observability.tracing import AuthTracing


class TestAuthTracing:
    """Tests for AuthTracing class."""

    def test_span_context_manager(self):
        """Test generic span context manager."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
            mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None

        with (
            patch("cqrs_ddd_identity.observability.tracing.HAS_OTEL", True),
            patch("cqrs_ddd_identity.observability.tracing.trace") as mock_trace,
        ):
            mock_trace.get_tracer.return_value = mock_tracer
            # Reset registry so it picks up the patched trace
            from cqrs_ddd_identity.observability import tracing as tracing_mod

            tracing_mod._registry._initialized = False
            tracing_mod._registry._tracer = None

            with AuthTracing.span(
                "resolve", provider="keycloak", attributes={"auth.method": "jwt"}
            ):
                pass
            assert True

    def test_span_without_opentelemetry(self):
        """Test span context manager when opentelemetry is unavailable."""
        with patch("cqrs_ddd_identity.observability.tracing.HAS_OTEL", False):
            from cqrs_ddd_identity.observability import tracing as tracing_mod

            tracing_mod._registry._initialized = False
            tracing_mod._registry._tracer = None
            with AuthTracing.span("authenticate", provider="keycloak"):
                pass
        assert True

    def test_resolve_span(self):
        """Test resolve-specific span."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
            mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None

        with (
            patch("cqrs_ddd_identity.observability.tracing.HAS_OTEL", True),
            patch("cqrs_ddd_identity.observability.tracing.trace") as mock_trace,
        ):
            mock_trace.get_tracer.return_value = mock_tracer
            from cqrs_ddd_identity.observability import tracing as tracing_mod

            tracing_mod._registry._initialized = False
            tracing_mod._registry._tracer = None
            with AuthTracing.resolve_span("jwt", provider="keycloak"):
                pass
        assert True

    def test_refresh_span(self):
        """Test refresh-specific span."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
            mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None

        with (
            patch("cqrs_ddd_identity.observability.tracing.HAS_OTEL", True),
            patch("cqrs_ddd_identity.observability.tracing.trace") as mock_trace,
        ):
            mock_trace.get_tracer.return_value = mock_tracer
            from cqrs_ddd_identity.observability import tracing as tracing_mod

            tracing_mod._registry._initialized = False
            tracing_mod._registry._tracer = None
            with AuthTracing.refresh_span(provider="keycloak"):
                pass
        assert True

    def test_logout_span(self):
        """Test logout-specific span."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
            mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None

        with (
            patch("cqrs_ddd_identity.observability.tracing.HAS_OTEL", True),
            patch("cqrs_ddd_identity.observability.tracing.trace") as mock_trace,
        ):
            mock_trace.get_tracer.return_value = mock_tracer
            from cqrs_ddd_identity.observability import tracing as tracing_mod

            tracing_mod._registry._initialized = False
            tracing_mod._registry._tracer = None
            with AuthTracing.logout_span(provider="keycloak"):
                pass
        assert True

    def test_set_principal(self):
        """Test setting principal attributes on current span."""
        mock_span = MagicMock()
        principal = Principal(
            user_id="user-123",
            username="testuser",
            roles=frozenset(["user", "admin"]),
            permissions=frozenset(["read", "write"]),
            tenant_id="tenant-1",
        )
        AuthTracing.set_principal(mock_span, principal)
        mock_span.set_attribute.assert_any_call("auth.user_id", "user-123")
        mock_span.set_attribute.assert_any_call("auth.username", "testuser")
        mock_span.set_attribute.assert_any_call("auth.tenant_id", "tenant-1")

    def test_set_principal_without_span(self):
        """Test set_principal when span is None is a no-op."""
        principal = Principal(
            user_id="user-123",
            username="testuser",
            tenant_id="tenant-1",
        )
        AuthTracing.set_principal(None, principal)
        assert True

    def test_set_success(self):
        """Test setting success status on span."""
        mock_span = MagicMock()
        with (
            patch("cqrs_ddd_identity.observability.tracing.Status"),
            patch("cqrs_ddd_identity.observability.tracing.StatusCode"),
        ):
            AuthTracing.set_success(mock_span)
            assert mock_span.set_status.called

    def test_set_success_without_span(self):
        """Test set_success when span is None is a no-op."""
        with (
            patch("cqrs_ddd_identity.observability.tracing.Status"),
            patch("cqrs_ddd_identity.observability.tracing.StatusCode"),
        ):
            AuthTracing.set_success(None)
        assert True

    def test_set_error(self):
        """Test setting error status on span."""
        mock_span = MagicMock()
        with (
            patch("cqrs_ddd_identity.observability.tracing.Status"),
            patch("cqrs_ddd_identity.observability.tracing.StatusCode"),
        ):
            AuthTracing.set_error(mock_span, ValueError("Invalid credentials"))
            assert mock_span.set_status.called
            assert mock_span.record_exception.called

    def test_set_error_without_span(self):
        """Test set_error when span is None is a no-op."""
        with (
            patch("cqrs_ddd_identity.observability.tracing.Status"),
            patch("cqrs_ddd_identity.observability.tracing.StatusCode"),
        ):
            AuthTracing.set_error(None, ValueError("err"))
        assert True
