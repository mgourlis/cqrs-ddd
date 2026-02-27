"""Password hashing utilities.

Provides bcrypt-based password hashing with transparent algorithm upgrade.
Supports argon2id as an optional stronger algorithm.
"""

from __future__ import annotations

from typing import Any, Literal, cast


class PasswordHasher:
    """Password hasher using bcrypt or argon2id.

    Provides secure password hashing and verification with transparent
    algorithm upgrade on login.

    Example:
        ```python
        hasher = PasswordHasher()

        # Hash a password
        hashed = hasher.hash("user_password")

        # Verify password
        if hasher.verify(hashed, "user_password"):
            # Check if needs rehash
            if hasher.needs_rehash(hashed):
                new_hash = hasher.hash("user_password")
                await repo.update_password_hash(user_id, new_hash)
        ```
    """

    def __init__(
        self,
        *,
        algorithm: Literal["bcrypt", "argon2id"] = "bcrypt",
        rounds: int = 12,
    ) -> None:
        """Initialize the password hasher.

        Args:
            algorithm: Hashing algorithm (default bcrypt).
            rounds: bcrypt rounds (cost factor, default 12).
        """
        self.algorithm = algorithm
        self.rounds = rounds
        self._bcrypt: Any = None
        self._argon2: Any = None

    def _get_bcrypt(self) -> Any:
        """Lazy import bcrypt."""
        if self._bcrypt is None:
            try:
                import bcrypt

                self._bcrypt = bcrypt
            except ImportError as e:
                raise ImportError(
                    "bcrypt is required for password hashing. "
                    "Install with: pip install bcrypt"
                ) from e
        return self._bcrypt

    def _get_argon2(self) -> Any:
        """Lazy import argon2."""
        if self._argon2 is None:
            try:
                from argon2 import PasswordHasher as Argon2Hasher

                self._argon2 = Argon2Hasher()
            except ImportError as e:
                raise ImportError(
                    "argon2-cffi is required for argon2id hashing. "
                    "Install with: pip install argon2-cffi"
                ) from e
        return self._argon2

    def hash(self, password: str) -> str:
        """Hash a password.

        Args:
            password: Plaintext password.

        Returns:
            Hashed password string.
        """
        if self.algorithm == "argon2id":
            return self._hash_argon2id(password)
        return self._hash_bcrypt(password)

    def _hash_bcrypt(self, password: str) -> str:
        """Hash password with bcrypt."""
        bcrypt_module = self._get_bcrypt()
        salt = bcrypt_module.gensalt(rounds=self.rounds)
        return bcrypt_module.hashpw(password.encode(), salt).decode()  # type: ignore[no-any-return]

    def _hash_argon2id(self, password: str) -> str:
        """Hash password with argon2id."""
        hasher = self._get_argon2()
        return hasher.hash(password)  # type: ignore[no-any-return]

    def verify(self, hashed_password: str, password: str) -> bool:
        """Verify a password against a hash.

        Automatically detects the algorithm from the hash format.

        Args:
            hashed_password: The stored hash.
            password: Plaintext password to verify.

        Returns:
            True if password matches.
        """
        # Detect algorithm from hash prefix
        if hashed_password.startswith("$argon2"):
            return self._verify_argon2id(hashed_password, password)
        return self._verify_bcrypt(hashed_password, password)

    def _verify_bcrypt(self, hashed_password: str, password: str) -> bool:
        """Verify password with bcrypt."""
        bcrypt_module = self._get_bcrypt()
        try:
            return cast(
                "bool",
                bcrypt_module.checkpw(password.encode(), hashed_password.encode()),
            )
        except ValueError:
            # Invalid hash format or malformed hash
            return False

    def _verify_argon2id(self, hashed_password: str, password: str) -> bool:
        """Verify password with argon2id."""
        hasher = self._get_argon2()
        try:
            hasher.verify(hashed_password, password)
            return True
        except Exception:  # noqa: BLE001
            # Invalid hash or verification failed
            return False

    def needs_rehash(self, hashed_password: str) -> bool:
        """Check if password hash should be upgraded.

        Returns True if:
        - Algorithm is different from configured
        - bcrypt rounds are lower than configured
        - argon2id parameters are outdated

        Args:
            hashed_password: Current password hash.

        Returns:
            True if rehash is recommended.
        """
        if hashed_password.startswith("$argon2"):
            if self.algorithm != "argon2id":
                return True
            # Check if argon2 parameters need update
            hasher = self._get_argon2()
            try:
                return cast("bool", hasher.check_needs_rehash(hashed_password))
            except Exception:  # noqa: BLE001
                return False

        # bcrypt hash
        if self.algorithm != "bcrypt":
            return True

        # Check rounds
        # bcrypt format: $2b$12$...
        parts = hashed_password.split("$")
        if len(parts) >= 3:
            try:
                current_rounds = int(parts[2])
                return current_rounds < self.rounds
            except ValueError:
                pass

        return False


__all__: list[str] = ["PasswordHasher"]
