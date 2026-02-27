"""MFA ports (protocols) for multi-factor authentication.

Defines interfaces for TOTP verification, backup codes, and OTP delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..principal import Principal


@dataclass(frozen=True)
class TotpSetup:
    """TOTP setup data returned when setting up TOTP.

    Attributes:
        secret: Base32-encoded TOTP secret.
        qr_uri: otpauth:// URI for QR code generation.
        manual_key: Human-readable key for manual entry.
    """

    secret: str
    qr_uri: str
    manual_key: str


@runtime_checkable
class ITotpVerifier(Protocol):
    """Protocol for TOTP verification.

    Implementations handle TOTP secret generation, storage, and verification.
    Uses pyotp library internally.
    """

    async def setup(self, user_id: str) -> TotpSetup:
        """Generate TOTP secret for a user.

        Args:
            user_id: User identifier.

        Returns:
            TotpSetup with secret and QR URI.
        """
        ...

    async def verify(self, user_id: str, code: str) -> bool:
        """Verify TOTP code for a user.

        Args:
            user_id: User identifier.
            code: 6-digit TOTP code.

        Returns:
            True if code is valid.

        Note:
            Should accept codes within ±1 time window for clock drift.
        """
        ...

    async def is_enabled(self, user_id: str) -> bool:
        """Check if TOTP is enabled for a user.

        Args:
            user_id: User identifier.

        Returns:
            True if TOTP is configured for this user.
        """
        ...

    async def disable(self, user_id: str) -> None:
        """Disable TOTP for a user.

        Args:
            user_id: User identifier.
        """
        ...


@runtime_checkable
class IBackupCodesStore(Protocol):
    """Protocol for backup code storage.

    Backup codes allow users to authenticate when they lose access
    to their primary MFA device.
    """

    async def generate(self, user_id: str, count: int = 10) -> list[str]:
        """Generate backup codes for a user.

        Args:
            user_id: User identifier.
            count: Number of codes to generate (default 10).

        Returns:
            List of plaintext backup codes (only shown once).
        """
        ...

    async def consume(self, user_id: str, code: str) -> bool:
        """Consume a backup code (single-use).

        Args:
            user_id: User identifier.
            code: Backup code to consume.

        Returns:
            True if code was valid and consumed.
        """
        ...

    async def revoke(self, user_id: str) -> None:
        """Revoke all backup codes for a user.

        Args:
            user_id: User identifier.
        """
        ...

    async def get_remaining_count(self, user_id: str) -> int:
        """Get remaining backup code count.

        Args:
            user_id: User identifier.

        Returns:
            Number of unused backup codes.
        """
        ...


@runtime_checkable
class IOtpChallengeStore(Protocol):
    """Protocol for OTP challenge storage.

    Used for email/SMS OTP where a code is sent and must be verified.
    """

    async def create(
        self,
        identifier: str,
        code: str,
        ttl: int = 300,
    ) -> None:
        """Create an OTP challenge.

        Args:
            identifier: User identifier (email, phone, user_id).
            code: The OTP code.
            ttl: Time-to-live in seconds (default 300 = 5 min).
        """
        ...

    async def verify(self, identifier: str, code: str) -> bool:
        """Verify and consume an OTP challenge.

        Args:
            identifier: User identifier.
            code: The OTP code to verify.

        Returns:
            True if valid, False otherwise.
        """
        ...

    async def delete(self, identifier: str) -> None:
        """Delete an OTP challenge.

        Args:
            identifier: User identifier.
        """
        ...


@runtime_checkable
class IOtpRateLimitStore(Protocol):
    """Protocol for OTP rate limiting.

    Tracks when OTP codes were last sent to prevent abuse.
    """

    async def record_send(self, identifier: str) -> None:
        """Record that an OTP was sent to this identifier.

        Args:
            identifier: Email, phone, or user identifier.
        """
        ...

    async def seconds_since_last_send(self, identifier: str) -> float | None:
        """Get seconds elapsed since last OTP was sent.

        Args:
            identifier: Email, phone, or user identifier.

        Returns:
            Seconds since last send, or None if never sent.
        """
        ...


@runtime_checkable
class IMfaDeliveryHook(Protocol):
    """Protocol for MFA delivery hooks.

    Applications implement this to send OTP codes via email or SMS.
    The identity package does NOT include email/SMS sending - it only
    provides hooks for the application to implement.
    """

    async def send_email_otp(self, email: str, code: str) -> None:
        """Send OTP code via email.

        Args:
            email: Recipient email address.
            code: The OTP code.
        """
        ...

    async def send_sms_otp(self, phone: str, code: str) -> None:
        """Send OTP code via SMS.

        Args:
            phone: Recipient phone number.
            code: The OTP code.
        """
        ...


@runtime_checkable
class IMfaPolicy(Protocol):
    """Protocol for MFA policy decisions.

    Applications implement this to determine when MFA is required.
    """

    async def is_required_for_user(self, principal: Principal) -> bool:
        """Check if MFA is required for a user.

        Args:
            principal: The user's principal.

        Returns:
            True if MFA is required.
        """
        ...

    async def get_allowed_methods(self, principal: Principal) -> list[str]:
        """Get allowed MFA methods for a user.

        Args:
            principal: The user's principal.

        Returns:
            List of allowed method names (e.g., ["totp", "backup", "sms"]).
        """
        ...


__all__: list[str] = [
    "TotpSetup",
    "ITotpVerifier",
    "IBackupCodesStore",
    "IOtpChallengeStore",
    "IOtpRateLimitStore",
    "IMfaDeliveryHook",
    "IMfaPolicy",
]
