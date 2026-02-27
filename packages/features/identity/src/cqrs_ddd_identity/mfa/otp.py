"""Email/SMS OTP service for one-time password delivery.

This service generates and verifies OTP codes, but the actual sending
via SMS or email is delegated to the application via IMfaDeliveryHook.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..exceptions import MfaInvalidError, MfaSetupError
from .ports import IMfaDeliveryHook, IOtpChallengeStore, IOtpRateLimitStore


@dataclass(frozen=True)
class OtpConfig:
    """OTP configuration.

    Attributes:
        code_length: Number of digits in OTP code.
        ttl_seconds: Time-to-live in seconds.
        max_attempts: Maximum verification attempts.
        cooldown_seconds: Minimum seconds between resends.
    """

    code_length: int = 6
    ttl_seconds: int = 300  # 5 minutes
    max_attempts: int = 3
    cooldown_seconds: int = 60  # 1 minute between resends


class EmailOtpService:
    """Email OTP service.

    Generates OTP codes and delegates sending to the application.
    Works with any email service (SendGrid, Mailgun, AWS SES, etc.)
    that the application implements via IMfaDeliveryHook.

    Example:
        ```python
        # Application provides the delivery hook
        class MyEmailHook(IMfaDeliveryHook):
            async def send_email_otp(self, email: str, code: str) -> None:
                # Use your email service
                await sendgrid.send(
                    to=email,
                    subject="Your verification code",
                    body=f"Your code is: {code}"
                )

        email_otp = EmailOtpService(
            challenge_store=InMemoryOtpChallengeStore(),
            delivery_hook=MyEmailHook(),
        )

        # Send OTP
        await email_otp.send("user@example.com")

        # Verify
        if await email_otp.verify("user@example.com", "123456"):
            print("Verified!")
        ```
    """

    def __init__(
        self,
        *,
        challenge_store: IOtpChallengeStore,
        delivery_hook: IMfaDeliveryHook,
        config: OtpConfig | None = None,
        rate_limit_store: IOtpRateLimitStore | None = None,
    ) -> None:
        """Initialize email OTP service.

        Args:
            challenge_store: Storage for OTP challenges.
            delivery_hook: Hook to send OTP via email.
            config: OTP configuration.
            rate_limit_store: Storage for rate limiting (optional, uses in-memory if not provided).
        """
        self.challenge_store = challenge_store
        self.delivery_hook = delivery_hook
        self.config = config or OtpConfig()
        self._rate_limit_store = rate_limit_store

    def _get_rate_limit_store(self) -> IOtpRateLimitStore:
        """Get or create rate limit store."""
        if self._rate_limit_store is None:
            self._rate_limit_store = InMemoryOtpRateLimitStore()
        return self._rate_limit_store

    def _generate_code(self) -> str:
        """Generate numeric OTP code.

        Returns:
            N-digit OTP code.
        """
        # Generate secure random number with correct digit count
        code = secrets.randbelow(10**self.config.code_length)
        return str(code).zfill(self.config.code_length)

    async def send(self, email: str) -> str:
        """Generate and send OTP to email.

        Args:
            email: Recipient email address.

        Returns:
            The generated OTP code (useful for testing).

        Note:
            In production, you should NOT return or log the code.
        """
        # Generate code
        code = self._generate_code()

        # Store challenge
        await self.challenge_store.create(
            identifier=email,
            code=code,
            ttl=self.config.ttl_seconds,
        )

        # Record send time for rate limiting
        rate_limit_store = self._get_rate_limit_store()
        await rate_limit_store.record_send(email)

        # Send via delivery hook
        await self.delivery_hook.send_email_otp(email, code)

        return code

    async def verify(self, email: str, code: str) -> bool:
        """Verify OTP code for email.

        Args:
            email: Email address that received the OTP.
            code: The OTP code to verify.

        Returns:
            True if valid.

        Raises:
            MfaInvalidError: If code is invalid or expired.
        """
        is_valid = await self.challenge_store.verify(email, code)
        if not is_valid:
            raise MfaInvalidError("Invalid or expired OTP code")
        return True

    async def resend(self, email: str) -> str:
        """Resend OTP with rate limiting.

        Args:
            email: Recipient email address.

        Returns:
            The new OTP code.

        Raises:
            MfaSetupError: If resend is requested too quickly (cooldown period).
        """
        rate_limit_store = self._get_rate_limit_store()

        # Check cooldown
        seconds_since_last = await rate_limit_store.seconds_since_last_send(email)
        if (
            seconds_since_last is not None
            and seconds_since_last < self.config.cooldown_seconds
        ):
            wait_seconds = self.config.cooldown_seconds - seconds_since_last
            raise MfaSetupError(
                f"Please wait {int(wait_seconds)} seconds before requesting a new code"
            )

        # Delete old challenge
        await self.challenge_store.delete(email)

        # Send new code
        return await self.send(email)


class SmsOtpService:
    """SMS OTP service.

    Generates OTP codes and delegates sending to the application.
    Works with any SMS service (Twilio, AWS SNS, etc.)
    that the application implements via IMfaDeliveryHook.

    Example:
        ```python
        # Application provides the delivery hook
        class MySmsHook(IMfaDeliveryHook):
            async def send_sms_otp(self, phone: str, code: str) -> None:
                # Use your SMS service
                await twilio.messages.create(
                    to=phone,
                    body=f"Your verification code is: {code}"
                )

        sms_otp = SmsOtpService(
            challenge_store=InMemoryOtpChallengeStore(),
            delivery_hook=MySmsHook(),
        )

        # Send OTP
        await sms_otp.send("+1234567890")

        # Verify
        if await sms_otp.verify("+1234567890", "123456"):
            print("Verified!")
        ```
    """

    def __init__(
        self,
        *,
        challenge_store: IOtpChallengeStore,
        delivery_hook: IMfaDeliveryHook,
        config: OtpConfig | None = None,
        rate_limit_store: IOtpRateLimitStore | None = None,
    ) -> None:
        """Initialize SMS OTP service.

        Args:
            challenge_store: Storage for OTP challenges.
            delivery_hook: Hook to send OTP via SMS.
            config: OTP configuration.
            rate_limit_store: Storage for rate limiting (optional, uses in-memory if not provided).
        """
        self.challenge_store = challenge_store
        self.delivery_hook = delivery_hook
        self.config = config or OtpConfig()
        self._rate_limit_store = rate_limit_store

    def _get_rate_limit_store(self) -> IOtpRateLimitStore:
        """Get or create rate limit store."""
        if self._rate_limit_store is None:
            self._rate_limit_store = InMemoryOtpRateLimitStore()
        return self._rate_limit_store

    def _generate_code(self) -> str:
        """Generate numeric OTP code."""
        code = secrets.randbelow(10**self.config.code_length)
        return str(code).zfill(self.config.code_length)

    async def send(self, phone: str) -> str:
        """Generate and send OTP via SMS.

        Args:
            phone: Phone number in E.164 format (e.g., +1234567890).

        Returns:
            The generated OTP code (useful for testing).
        """
        code = self._generate_code()

        await self.challenge_store.create(
            identifier=phone,
            code=code,
            ttl=self.config.ttl_seconds,
        )

        # Record send time for rate limiting
        rate_limit_store = self._get_rate_limit_store()
        await rate_limit_store.record_send(phone)

        await self.delivery_hook.send_sms_otp(phone, code)

        return code

    async def verify(self, phone: str, code: str) -> bool:
        """Verify OTP code for phone.

        Args:
            phone: Phone number that received the OTP.
            code: The OTP code to verify.

        Returns:
            True if valid.

        Raises:
            MfaInvalidError: If code is invalid or expired.
        """
        is_valid = await self.challenge_store.verify(phone, code)
        if not is_valid:
            raise MfaInvalidError("Invalid or expired OTP code")
        return True

    async def resend(self, phone: str) -> str:
        """Resend OTP with rate limiting.

        Args:
            phone: Phone number in E.164 format.

        Returns:
            The new OTP code.

        Raises:
            MfaSetupError: If resend is requested too quickly (cooldown period).
        """
        rate_limit_store = self._get_rate_limit_store()

        # Check cooldown
        seconds_since_last = await rate_limit_store.seconds_since_last_send(phone)
        if (
            seconds_since_last is not None
            and seconds_since_last < self.config.cooldown_seconds
        ):
            wait_seconds = self.config.cooldown_seconds - seconds_since_last
            raise MfaSetupError(
                f"Please wait {int(wait_seconds)} seconds before requesting a new code"
            )

        # Delete old challenge
        await self.challenge_store.delete(phone)

        # Send new code
        return await self.send(phone)


class InMemoryOtpChallengeStore(IOtpChallengeStore):
    """In-memory OTP challenge store for TESTING ONLY.

    ⚠️ WARNING: Codes are stored in plain text in memory.
    Do NOT use in production!

    Use Redis-backed implementation in production.
    """

    def __init__(self) -> None:
        self._challenges: dict[str, tuple[str, datetime]] = {}

    async def create(
        self,
        identifier: str,
        code: str,
        ttl: int = 300,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        self._challenges[identifier] = (code, expires_at)

    async def verify(self, identifier: str, code: str) -> bool:
        entry = self._challenges.get(identifier)
        if entry is None:
            return False

        stored_code, expires_at = entry

        # Check expiration
        if datetime.now(timezone.utc) > expires_at:
            del self._challenges[identifier]
            return False

        # Verify code
        if secrets.compare_digest(stored_code, code):
            # Delete after successful verification (single-use)
            del self._challenges[identifier]
            return True

        return False

    async def delete(self, identifier: str) -> None:
        self._challenges.pop(identifier, None)


class InMemoryOtpRateLimitStore(IOtpRateLimitStore):
    """In-memory OTP rate limit store for TESTING ONLY.

    ⚠️ WARNING: This is a simple in-memory implementation.
    Do NOT use in production!

    Use Redis-backed implementation in production for distributed systems.
    """

    def __init__(self) -> None:
        self._last_sent: dict[str, float] = {}

    async def record_send(self, identifier: str) -> None:
        """Record that an OTP was sent."""
        self._last_sent[identifier] = time.time()

    async def seconds_since_last_send(self, identifier: str) -> float | None:
        """Get seconds since last send."""
        last_sent = self._last_sent.get(identifier)
        if last_sent is None:
            return None
        return time.time() - last_sent


__all__: list[str] = [
    "OtpConfig",
    "EmailOtpService",
    "SmsOtpService",
    "InMemoryOtpChallengeStore",
    "InMemoryOtpRateLimitStore",
]
