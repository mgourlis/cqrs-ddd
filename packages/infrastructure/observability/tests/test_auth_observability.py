"""Tests for auth observability integration.

This test module demonstrates how to use auth observability
in the identity package.
"""

from __future__ import annotations

import pytest

from cqrs_ddd_observability import auth_observability


class TestAuthMetrics:
    """Test auth metrics context managers."""

    def test_operation_context_manager_success(self):
        """Test that operation context manager records metrics."""
        with auth_observability.AuthMetrics.operation(
            "resolve",
            provider="keycloak",
            method="jwt",
        ):
            # Simulate successful operation
            pass

        # Should not raise, metrics recorded internally

    def test_operation_context_manager_failure(self):
        """Test that operation context manager records failure."""
        with pytest.raises(ValueError):
            with auth_observability.AuthMetrics.operation(
                "resolve",
                provider="keycloak",
                method="jwt",
            ):
                raise ValueError("Auth failed")

        # Should record failure metric before re-raising

    def test_record_event(self):
        """Test recording a single auth event."""
        labels = auth_observability.AuthLabels(
            provider="database",
            method="session",
            operation="login",
            result="success",
        )
        auth_observability.AuthMetrics.record(labels)

    def test_session_gauge(self):
        """Test session gauge increment/decrement."""
        auth_observability.AuthMetrics.increment_sessions(provider="keycloak")
        auth_observability.AuthMetrics.decrement_sessions(provider="keycloak")


class TestAuthTracing:
    """Test auth tracing context managers."""

    def test_span_context_manager(self):
        """Test span context manager."""
        with auth_observability.AuthTracing.span(
            "resolve",
            provider="keycloak",
            attributes={"auth.method": "jwt"},
        ) as span:
            # Span may be None if OpenTelemetry not available
            if span:
                span.set_attribute("custom.attr", "value")

    def test_resolve_span(self):
        """Test resolve span helper."""
        with auth_observability.AuthTracing.resolve_span(
            method="jwt",
            provider="keycloak",
        ):
            # Simulate token resolution
            pass

    def test_refresh_span(self):
        """Test refresh span helper."""
        with auth_observability.AuthTracing.refresh_span(
            provider="keycloak",
        ):
            # Simulate token refresh
            pass

    def test_logout_span(self):
        """Test logout span helper."""
        with auth_observability.AuthTracing.logout_span(
            provider="keycloak",
        ):
            # Simulate logout
            pass

    def test_mfa_span(self):
        """Test MFA verification span helper."""
        with auth_observability.AuthTracing.mfa_span(
            method="totp",
            provider="keycloak",
        ):
            # Simulate MFA verification
            pass


class MockPrincipal:
    """Mock principal for testing."""

    def __init__(self):
        self.user_id = "user-123"
        self.username = "testuser"
        self.tenant_id = "tenant-456"
        self.auth_method = "jwt"
        self.roles = ["admin", "user"]


class TestAuthTracingHelpers:
    """Test auth tracing helper methods."""

    def test_set_principal(self):
        """Test setting principal attributes on span."""
        with auth_observability.AuthTracing.span(
            "resolve",
            provider="keycloak",
        ) as span:
            principal = MockPrincipal()
            auth_observability.AuthTracing.set_principal(span, principal)

            if span:
                # Span attributes should be set
                pass

    def test_set_success(self):
        """Test marking span as successful."""
        with auth_observability.AuthTracing.span(
            "resolve",
            provider="keycloak",
        ) as span:
            auth_observability.AuthTracing.set_success(span)

    def test_set_error(self):
        """Test marking span as failed."""
        with auth_observability.AuthTracing.span(
            "resolve",
            provider="keycloak",
        ) as span:
            error = ValueError("Auth failed")
            # Should not raise, just record error on span
            # (actual error recording happens if we raise)
            auth_observability.AuthTracing.set_error(span, error)


class TestConvenienceFunctions:
    """Test convenience helper functions."""

    def test_record_login_success(self):
        """Test login success recording."""
        auth_observability.record_login_success(
            user_id="user-123",
            provider="keycloak",
            method="jwt",
        )

    def test_record_login_failure(self):
        """Test login failure recording."""
        auth_observability.record_login_failure(
            provider="keycloak",
            error_code="invalid_token",
            method="jwt",
        )

    def test_record_logout(self):
        """Test logout recording."""
        auth_observability.record_logout(provider="keycloak")

    def test_record_token_refresh(self):
        """Test token refresh recording."""
        auth_observability.record_token_refresh(provider="keycloak")

    def test_record_mfa_verification_success(self):
        """Test MFA verification success recording."""
        auth_observability.record_mfa_verification(
            provider="keycloak",
            method="totp",
            success=True,
        )

    def test_record_mfa_verification_failure(self):
        """Test MFA verification failure recording."""
        auth_observability.record_mfa_verification(
            provider="keycloak",
            method="totp",
            success=False,
        )


class TestIntegrationExample:
    """Integration example showing how to use with identity package."""

    @pytest.mark.asyncio
    async def test_auth_flow_with_observability(self):
        """Example of full auth flow with observability."""
        # Simulate authentication flow with metrics + tracing

        # 1. Token resolution
        with (
            auth_observability.AuthMetrics.operation(
                "resolve",
                provider="keycloak",
                method="jwt",
            ),
            auth_observability.AuthTracing.resolve_span(
                method="jwt",
                provider="keycloak",
            ) as span,
        ):
            # Simulate resolving token
            principal = MockPrincipal()

            if span:
                auth_observability.AuthTracing.set_principal(span, principal)
                auth_observability.AuthTracing.set_success(span)

            auth_observability.record_login_success(
                user_id=principal.user_id,
                provider="keycloak",
                method="jwt",
            )

        # 2. Token refresh
        with (
            auth_observability.AuthMetrics.operation(
                "refresh",
                provider="keycloak",
                method="jwt",
            ),
            auth_observability.AuthTracing.refresh_span(
                provider="keycloak",
            ) as span,
        ):
            # Simulate refresh
            auth_observability.record_token_refresh(provider="keycloak")

        # 3. Logout
        with (
            auth_observability.AuthMetrics.operation(
                "logout",
                provider="keycloak",
                method="jwt",
            ),
            auth_observability.AuthTracing.logout_span(
                provider="keycloak",
            ) as span,
        ):
            # Simulate logout
            auth_observability.record_logout(provider="keycloak")
