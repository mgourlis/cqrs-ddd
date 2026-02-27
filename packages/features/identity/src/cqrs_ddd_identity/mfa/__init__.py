"""MFA module for cqrs-ddd-identity.

Supports:
- TOTP (Google Authenticator, Microsoft Authenticator, Authy, etc.)
- Backup codes (single-use recovery codes)
- Email OTP (via application hook)
- SMS OTP (via application hook)
"""

from .backup_codes import BackupCodesService, InMemoryBackupCodesService
from .otp import (
    EmailOtpService,
    InMemoryOtpChallengeStore,
    InMemoryOtpRateLimitStore,
    OtpConfig,
    SmsOtpService,
)
from .ports import (
    IBackupCodesStore,
    IMfaDeliveryHook,
    IMfaPolicy,
    IOtpChallengeStore,
    IOtpRateLimitStore,
    ITotpVerifier,
    TotpSetup,
)
from .totp import (
    InMemoryTotpSecretStore,
    ITotpSecretStore,
    TotpService,
)

__all__: list[str] = [
    # Ports
    "ITotpVerifier",
    "TotpSetup",
    "IBackupCodesStore",
    "IOtpChallengeStore",
    "IOtpRateLimitStore",
    "IMfaDeliveryHook",
    "IMfaPolicy",
    # TOTP (Google/Microsoft Authenticator)
    "TotpService",
    "ITotpSecretStore",
    "InMemoryTotpSecretStore",
    # Backup Codes
    "BackupCodesService",
    "InMemoryBackupCodesService",
    # Email/SMS OTP
    "EmailOtpService",
    "SmsOtpService",
    "OtpConfig",
    "InMemoryOtpChallengeStore",
    "InMemoryOtpRateLimitStore",
]
