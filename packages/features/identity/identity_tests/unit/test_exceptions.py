"""Tests for identity exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import DomainError
from cqrs_ddd_identity.exceptions import (
    AccountLockedError,
    ApiKeyError,
    AuthenticationError,
    IdentityError,
    InvalidApiKeyError,
    InvalidTokenError,
    MfaError,
    MfaInvalidError,
    MfaRequiredError,
)


class TestExceptionHierarchy:
    def test_identity_error_subclasses_domain_error(self) -> None:
        assert issubclass(IdentityError, DomainError)

    def test_authentication_error_subclasses_identity_error(self) -> None:
        assert issubclass(AuthenticationError, IdentityError)

    def test_invalid_token_error_subclasses_authentication_error(self) -> None:
        assert issubclass(InvalidTokenError, AuthenticationError)

    def test_mfa_error_subclasses_identity_error(self) -> None:
        assert issubclass(MfaError, IdentityError)

    def test_mfa_invalid_error_subclasses_mfa_error(self) -> None:
        assert issubclass(MfaInvalidError, MfaError)

    def test_api_key_error_subclasses_identity_error(self) -> None:
        assert issubclass(ApiKeyError, IdentityError)

    def test_invalid_api_key_error_subclasses_api_key_error(self) -> None:
        assert issubclass(InvalidApiKeyError, ApiKeyError)


class TestAccountLockedError:
    def test_default_message(self) -> None:
        e = AccountLockedError()
        assert "locked" in str(e).lower()

    def test_lockout_duration_and_failed_attempts(self) -> None:
        e = AccountLockedError(
            lockout_duration=300,
            failed_attempts=5,
        )
        assert e.lockout_duration == 300
        assert e.failed_attempts == 5


class TestMfaRequiredError:
    def test_default_available_methods(self) -> None:
        e = MfaRequiredError()
        assert e.available_methods == ["totp"]

    def test_pending_token_and_custom_methods(self) -> None:
        e = MfaRequiredError(
            pending_token="pt-123",
            available_methods=["totp", "backup"],
        )
        assert e.pending_token == "pt-123"
        assert e.available_methods == ["totp", "backup"]
