"""TOTP (Time-based One-Time Password) service.

Works with any TOTP-compatible authenticator app:
- Google Authenticator
- Microsoft Authenticator
- Authy
- 1Password
- LastPass Authenticator
- FreeOTP

Uses pyotp library internally.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..exceptions import MfaInvalidError, MfaSetupError
from .ports import ITotpVerifier, TotpSetup


class TotpService(ITotpVerifier):
    """TOTP service for authenticator apps.

    Generates and verifies TOTP codes compatible with:
    - Google Authenticator
    - Microsoft Authenticator
    - Authy
    - Any RFC 6238 TOTP app

    Example:
        ```python
        totp_service = TotpService(
            issuer="MyApp",
            secret_store=MySecretStore(),  # App provides storage
        )

        # Setup - show QR code to user
        setup = await totp_service.setup("user-123")
        print(f"Scan this QR: {setup.qr_uri}")
        print(f"Or enter manually: {setup.manual_key}")

        # Verify - check code from authenticator app
        if await totp_service.verify("user-123", "123456"):
            print("Valid!")
        ```
    """

    def __init__(
        self,
        *,
        issuer: str = "MyApp",
        digits: int = 6,
        interval: int = 30,
        valid_window: int = 1,
        secret_store: ITotpSecretStore | None = None,
    ) -> None:
        """Initialize TOTP service.

        Args:
            issuer: Application name shown in authenticator app.
            digits: Number of digits in code (default 6).
            interval: Time interval in seconds (default 30).
            valid_window: Accept codes ±N intervals for clock drift (default 1).
            secret_store: Storage for TOTP secrets (app provides implementation).
        """
        self.issuer = issuer
        self.digits = digits
        self.interval = interval
        self.valid_window = valid_window
        self.secret_store = secret_store

    def _get_pyotp(self) -> Any:
        """Lazy import pyotp."""
        try:
            import pyotp

            return pyotp
        except ImportError as e:
            raise ImportError(
                "pyotp is required for TOTP support. "
                "Install with: pip install cqrs-ddd-identity[mfa]"
            ) from e

    async def setup(self, user_id: str) -> TotpSetup:
        """Generate TOTP secret for a user.

        Creates a new secret and returns data needed to configure
        an authenticator app.

        Args:
            user_id: User identifier.

        Returns:
            TotpSetup with:
                - secret: Base32-encoded secret (store this!)
                - qr_uri: otpauth:// URI for QR code generation
                - manual_key: Formatted key for manual entry

        Raises:
            MfaSetupError: If secret_store is not configured.

        Note:
            You MUST store the secret securely after setup.
            Use the secret_store to persist it.
        """
        if self.secret_store is None:
            raise MfaSetupError(
                "TotpService requires a secret_store for setup and verification. "
                "Provide an ITotpSecretStore implementation when creating TotpService."
            )

        pyotp = self._get_pyotp()

        # Generate random secret
        secret = pyotp.random_base32()

        # Create TOTP instance
        totp = pyotp.TOTP(
            secret,
            digits=self.digits,
            interval=self.interval,
            issuer=self.issuer,
        )

        # Get username for display (could be enhanced to fetch from user store)
        account_name = user_id

        # Generate provisioning URI for QR code
        qr_uri = totp.provisioning_uri(
            name=account_name,
            issuer_name=self.issuer,
        )

        # Format secret for manual entry (groups of 4)
        manual_key = self._format_secret(secret)

        # Store secret if store is provided
        if self.secret_store:
            await self.secret_store.store_secret(user_id, secret)

        return TotpSetup(
            secret=secret,
            qr_uri=qr_uri,
            manual_key=manual_key,
        )

    def _format_secret(self, secret: str) -> str:
        """Format secret for manual entry.

        Args:
            secret: Base32 secret.

        Returns:
            Secret formatted as groups of 4 characters.
        """
        # Remove any padding
        secret = secret.rstrip("=")
        # Add spaces every 4 characters for readability
        return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))

    async def verify(self, user_id: str, code: str) -> bool:
        """Verify TOTP code for a user.

        Validates a 6-digit code from the authenticator app.
        Accepts codes within ±valid_window intervals for clock drift.

        Args:
            user_id: User identifier.
            code: 6-digit TOTP code from authenticator.

        Returns:
            True if code is valid.

        Raises:
            MfaSetupError: If TOTP is not configured for the user.
            MfaInvalidError: If the code is invalid.
        """
        pyotp = self._get_pyotp()

        # Get stored secret
        if not self.secret_store:
            raise MfaSetupError(
                "TOTP secret store not configured. "
                "Provide a secret_store to TotpService."
            )

        secret = await self.secret_store.get_secret(user_id)
        if not secret:
            raise MfaSetupError(f"TOTP is not enabled for user {user_id}")

        # Create TOTP verifier
        totp = pyotp.TOTP(
            secret,
            digits=self.digits,
            interval=self.interval,
        )

        # Verify with time window tolerance
        if not totp.verify(code, valid_window=self.valid_window):
            raise MfaInvalidError("Invalid TOTP code")

        return True

    async def is_enabled(self, user_id: str) -> bool:
        """Check if TOTP is enabled for a user.

        Args:
            user_id: User identifier.

        Returns:
            True if TOTP secret exists for this user.
        """
        if not self.secret_store:
            return False

        secret = await self.secret_store.get_secret(user_id)
        return secret is not None

    async def disable(self, user_id: str) -> None:
        """Disable TOTP for a user.

        Removes the stored TOTP secret.

        Args:
            user_id: User identifier.
        """
        if self.secret_store:
            await self.secret_store.delete_secret(user_id)


class ITotpSecretStore(Protocol):
    """Protocol for TOTP secret storage.

    Applications MUST implement this to store TOTP secrets securely.
    Secrets should be encrypted at rest.

    Example implementation:
        ```python
        class DatabaseTotpSecretStore(ITotpSecretStore):
            async def store_secret(self, user_id: str, secret: str) -> None:
                # Encrypt and store in database
                encrypted = encrypt(secret)
                await db.execute(
                    "INSERT INTO user_totp (user_id, secret) VALUES (?, ?)",
                    (user_id, encrypted)
                )

            async def get_secret(self, user_id: str) -> str | None:
                row = await db.fetch_one(
                    "SELECT secret FROM user_totp WHERE user_id = ?",
                    (user_id,)
                )
                if row:
                    return decrypt(row["secret"])
                return None
        ```
    """

    async def store_secret(self, user_id: str, secret: str) -> None:
        """Store TOTP secret for a user.

        Args:
            user_id: User identifier.
            secret: Base32-encoded TOTP secret.
        """
        ...

    async def get_secret(self, user_id: str) -> str | None:
        """Get TOTP secret for a user.

        Args:
            user_id: User identifier.

        Returns:
            Base32-encoded secret or None if not set.
        """
        ...

    async def delete_secret(self, user_id: str) -> None:
        """Delete TOTP secret for a user.

        Args:
            user_id: User identifier.
        """
        ...


class InMemoryTotpSecretStore(ITotpSecretStore):
    """In-memory TOTP secret store for TESTING ONLY.

    ⚠️ WARNING: Secrets are stored in plain text in memory.
    Do NOT use in production!

    Use this only for unit tests.
    """

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    async def store_secret(self, user_id: str, secret: str) -> None:
        self._secrets[user_id] = secret

    async def get_secret(self, user_id: str) -> str | None:
        return self._secrets.get(user_id)

    async def delete_secret(self, user_id: str) -> None:
        self._secrets.pop(user_id, None)


__all__: list[str] = [
    "TotpService",
    "ITotpSecretStore",
    "InMemoryTotpSecretStore",
]
