"""Backup codes service for MFA.

Generates and validates single-use backup codes that users can use
when they lose access to their primary MFA device.
"""

from __future__ import annotations

import secrets
import string

from .ports import IBackupCodesStore


class BackupCodesService(IBackupCodesStore):
    """Backup codes service for MFA recovery.

    Generates alphanumeric codes that are stored hashed (bcrypt).
    Each code is single-use and automatically deleted after use.

    Example:
        ```python
        # Requires an IBackupCodeRepository implementation
        # This is a Port-Adapter pattern - the app provides the implementation
        codes = await backup_service.generate("user-123", count=10)
        print(f"Save these codes: {codes}")

        # Later, when user needs to recover
        if await backup_service.consume("user-123", user_code):
            # Allow access, MFA bypassed
            pass
        ```
    """

    # Characters used in backup codes (exclude ambiguous: 0, O, l, 1, I)
    ALPHABET = string.ascii_uppercase.replace("O", "").replace(
        "I", ""
    ) + string.digits.replace("0", "").replace("1", "")

    def __init__(
        self,
        code_length: int = 8,
        default_count: int = 10,
    ) -> None:
        """Initialize the backup codes service.

        Args:
            code_length: Length of each backup code (default 8).
            default_count: Default number of codes to generate (default 10).
        """
        self.code_length = code_length
        self.default_count = default_count

    def _generate_code(self) -> str:
        """Generate a single backup code.

        Returns:
            Random alphanumeric code.
        """
        return "".join(secrets.choice(self.ALPHABET) for _ in range(self.code_length))

    def _format_code(self, code: str) -> str:
        """Format code with dashes for readability.

        Args:
            code: Raw code.

        Returns:
            Formatted code (e.g., "ABCD-EFGH").
        """
        # Split into groups of 4
        return "-".join(code[i : i + 4] for i in range(0, len(code), 4))

    async def generate(self, user_id: str, count: int = 10) -> list[str]:
        """Generate backup codes for a user.

        NOTE: This method returns plaintext codes that should be shown
        to the user ONCE and then discarded. The actual storage implementation
        must hash these codes before storing.

        Args:
            user_id: User identifier.
            count: Number of codes to generate.

        Returns:
            List of plaintext backup codes.

        Note:
            Implementations must store codes hashed (bcrypt) and
            associate them with the user_id.
        """
        codes = []
        for _ in range(count or self.default_count):
            code = self._generate_code()
            formatted = self._format_code(code)
            codes.append(formatted)

        # NOTE: Subclasses must override this to actually store the codes
        # This base implementation only generates the codes
        return codes

    async def consume(self, user_id: str, code: str) -> bool:
        """Consume a backup code (single-use).

        NOTE: Implementations must:
        1. Look up the stored hash for this user
        2. Verify the code matches (bcrypt)
        3. Delete the used code
        4. Return True if valid, False otherwise

        Args:
            user_id: User identifier.
            code: Backup code to consume.

        Returns:
            True if code was valid and consumed.
        """
        # NOTE: Subclasses must override this to verify against stored hashes
        raise NotImplementedError(
            "BackupCodesService.consume must be implemented by subclasses"
        )

    async def revoke(self, user_id: str) -> None:
        """Revoke all backup codes for a user.

        Args:
            user_id: User identifier.
        """
        # NOTE: Subclasses must override this to delete stored codes
        raise NotImplementedError(
            "BackupCodesService.revoke must be implemented by subclasses"
        )

    async def get_remaining_count(self, user_id: str) -> int:
        """Get remaining backup code count.

        Args:
            user_id: User identifier.

        Returns:
            Number of unused backup codes.
        """
        # NOTE: Subclasses must override this to count stored codes
        raise NotImplementedError(
            "BackupCodesService.get_remaining_count must be implemented by subclasses"
        )


class InMemoryBackupCodesService(BackupCodesService):
    """In-memory implementation of BackupCodesService for testing.

    Stores codes in plaintext per user. Not for production use.
    """

    def __init__(
        self,
        code_length: int = 8,
        default_count: int = 10,
    ) -> None:
        super().__init__(code_length=code_length, default_count=default_count)
        self._codes: dict[str, set[str]] = {}

    async def generate(self, user_id: str, count: int = 10) -> list[str]:
        codes = await super().generate(user_id, count=count)
        if user_id not in self._codes:
            self._codes[user_id] = set()
        self._codes[user_id].update(codes)
        return codes

    def _normalize_code(self, code: str) -> str:
        """Normalize backup code input: strip whitespace, accept with or without dash."""
        code = code.strip().upper()
        # If 8 chars without dash, add dash for lookup (format is XXXX-XXXX)
        if len(code) == 8 and "-" not in code:
            code = f"{code[:4]}-{code[4:]}"
        return code

    async def consume(self, user_id: str, code: str) -> bool:
        normalized = self._normalize_code(code)
        user_codes = self._codes.get(user_id)
        if not user_codes or normalized not in user_codes:
            return False
        user_codes.discard(normalized)
        return True

    async def revoke(self, user_id: str) -> None:
        self._codes[user_id] = set()

    async def get_remaining_count(self, user_id: str) -> int:
        return len(self._codes.get(user_id, set()))


__all__: list[str] = ["BackupCodesService", "InMemoryBackupCodesService"]
