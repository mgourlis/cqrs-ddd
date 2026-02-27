"""Tests for MFA services (TOTP, OTP, Backup Codes)."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity.exceptions import MfaInvalidError, MfaSetupError
from cqrs_ddd_identity.mfa import (
    BackupCodesService,
    EmailOtpService,
    InMemoryBackupCodesService,
    InMemoryOtpChallengeStore,
    InMemoryTotpSecretStore,
    OtpConfig,
    SmsOtpService,
    TotpService,
)


class MockDeliveryHook:
    """Mock delivery hook for testing."""

    def __init__(self) -> None:
        self.emails_sent: list[tuple[str, str]] = []
        self.sms_sent: list[tuple[str, str]] = []

    async def send_email_otp(self, email: str, code: str) -> None:
        self.emails_sent.append((email, code))

    async def send_sms_otp(self, phone: str, code: str) -> None:
        self.sms_sent.append((phone, code))


class TestTotpService:
    """Test TOTP service."""

    @pytest.fixture
    def totp_service(self) -> TotpService:
        return TotpService(secret_store=InMemoryTotpSecretStore())

    @pytest.mark.asyncio
    async def test_setup_totp(self, totp_service: TotpService) -> None:
        """Test TOTP setup generates valid secret."""
        setup = await totp_service.setup("user123")

        assert setup.secret is not None
        assert setup.qr_uri.startswith("otpauth://")
        assert setup.manual_key is not None
        assert await totp_service.is_enabled("user123")

    @pytest.mark.asyncio
    async def test_verify_without_setup_raises(self, totp_service: TotpService) -> None:
        """Test verification fails if TOTP not set up."""
        with pytest.raises(MfaSetupError, match="TOTP is not enabled"):
            await totp_service.verify("user123", "123456")

    @pytest.mark.asyncio
    async def test_verify_invalid_code_raises(self, totp_service: TotpService) -> None:
        """Test verification fails with invalid code."""
        await totp_service.setup("user123")

        with pytest.raises(MfaInvalidError, match="Invalid TOTP code"):
            await totp_service.verify("user123", "000000")

    @pytest.mark.asyncio
    async def test_disable_totp(self, totp_service: TotpService) -> None:
        """Test disabling TOTP."""
        await totp_service.setup("user123")
        assert await totp_service.is_enabled("user123")

        await totp_service.disable("user123")
        assert not await totp_service.is_enabled("user123")


class TestEmailOtpService:
    """Test Email OTP service."""

    @pytest.fixture
    def email_service(self) -> EmailOtpService:
        return EmailOtpService(
            challenge_store=InMemoryOtpChallengeStore(),
            delivery_hook=MockDeliveryHook(),
            config=OtpConfig(cooldown_seconds=1),
        )

    @pytest.mark.asyncio
    async def test_send_email_otp(self, email_service: EmailOtpService) -> None:
        """Test sending email OTP."""
        hook = email_service.delivery_hook
        assert isinstance(hook, MockDeliveryHook)

        code = await email_service.send("user@example.com")

        assert len(hook.emails_sent) == 1
        assert hook.emails_sent[0] == ("user@example.com", code)

    @pytest.mark.asyncio
    async def test_verify_email_otp(self, email_service: EmailOtpService) -> None:
        """Test verifying email OTP."""
        code = await email_service.send("user@example.com")

        result = await email_service.verify("user@example.com", code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_invalid_otp_raises(
        self, email_service: EmailOtpService
    ) -> None:
        """Test verifying invalid OTP raises exception."""
        await email_service.send("user@example.com")

        with pytest.raises(MfaInvalidError, match="Invalid or expired OTP code"):
            await email_service.verify("user@example.com", "000000")

    @pytest.mark.asyncio
    async def test_resend_with_cooldown(self, email_service: EmailOtpService) -> None:
        """Test resend is rate-limited."""
        await email_service.send("user@example.com")

        with pytest.raises(MfaSetupError, match="Please wait"):
            await email_service.resend("user@example.com")

    @pytest.mark.asyncio
    async def test_resend_after_cooldown(self, email_service: EmailOtpService) -> None:
        """Test resend works after cooldown period."""
        import asyncio

        code1 = await email_service.send("user@example.com")

        # Wait for cooldown
        await asyncio.sleep(1.1)

        code2 = await email_service.resend("user@example.com")

        assert code1 != code2


class TestSmsOtpService:
    """Test SMS OTP service."""

    @pytest.fixture
    def sms_service(self) -> SmsOtpService:
        return SmsOtpService(
            challenge_store=InMemoryOtpChallengeStore(),
            delivery_hook=MockDeliveryHook(),
            config=OtpConfig(cooldown_seconds=1),
        )

    @pytest.mark.asyncio
    async def test_send_sms_otp(self, sms_service: SmsOtpService) -> None:
        """Test sending SMS OTP."""
        hook = sms_service.delivery_hook
        assert isinstance(hook, MockDeliveryHook)

        code = await sms_service.send("+1234567890")

        assert len(hook.sms_sent) == 1
        assert hook.sms_sent[0] == ("+1234567890", code)

    @pytest.mark.asyncio
    async def test_verify_sms_otp(self, sms_service: SmsOtpService) -> None:
        """Test verifying SMS OTP."""
        code = await sms_service.send("+1234567890")

        result = await sms_service.verify("+1234567890", code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_invalid_sms_otp_raises(
        self, sms_service: SmsOtpService
    ) -> None:
        """Test verifying invalid SMS OTP raises exception."""
        await sms_service.send("+1234567890")

        with pytest.raises(MfaInvalidError, match="Invalid or expired OTP code"):
            await sms_service.verify("+1234567890", "000000")

    @pytest.mark.asyncio
    async def test_resend_with_cooldown(self, sms_service: SmsOtpService) -> None:
        """Test SMS resend is rate-limited."""
        await sms_service.send("+1234567890")

        with pytest.raises(MfaSetupError, match="Please wait"):
            await sms_service.resend("+1234567890")


class TestBackupCodesService:
    """Test backup codes service."""

    @pytest.fixture
    def backup_service(self) -> BackupCodesService:
        return InMemoryBackupCodesService()

    @pytest.mark.asyncio
    async def test_generate_backup_codes(
        self, backup_service: BackupCodesService
    ) -> None:
        """Test generating backup codes."""
        codes = await backup_service.generate("user123", count=5)

        assert len(codes) == 5
        # Codes are formatted as "XXXX-XXXX" (8 chars + dash = 9 total)
        assert all(len(code) == 9 for code in codes)
        assert all("-" in code for code in codes)

    @pytest.mark.asyncio
    async def test_consume_backup_code(
        self, backup_service: BackupCodesService
    ) -> None:
        """Test consuming backup codes."""
        codes = await backup_service.generate("user123", count=3)

        # First code should work
        result = await backup_service.consume("user123", codes[0])
        assert result is True

        # Same code should not work again
        result = await backup_service.consume("user123", codes[0])
        assert result is False

        # Remaining count should decrease
        remaining = await backup_service.get_remaining_count("user123")
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_revoke_backup_codes(
        self, backup_service: BackupCodesService
    ) -> None:
        """Test revoking backup codes."""
        await backup_service.generate("user123", count=5)

        await backup_service.revoke("user123")

        remaining = await backup_service.get_remaining_count("user123")
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_invalid_backup_code(
        self, backup_service: BackupCodesService
    ) -> None:
        """Test consuming invalid backup code."""
        await backup_service.generate("user123", count=3)

        result = await backup_service.consume("user123", "INVALID")
        assert result is False

    @pytest.mark.asyncio
    async def test_consume_backup_code_normalized_input(
        self, backup_service: BackupCodesService
    ) -> None:
        """Test that consume accepts code with or without dash and strips whitespace."""
        codes = await backup_service.generate("user123", count=2)
        # Stored format is XXXX-XXXX
        stored_code = codes[0]

        # Without dash (8 chars) should match
        no_dash = stored_code.replace("-", "")
        result = await backup_service.consume("user123", no_dash)
        assert result is True

        # With spaces should match (second code)
        with_spaces = "  " + codes[1] + "  "
        result = await backup_service.consume("user123", with_spaces)
        assert result is True

        remaining = await backup_service.get_remaining_count("user123")
        assert remaining == 0
