"""Tests for Database identity provider."""

from __future__ import annotations

import pytest

pytest.importorskip(
    "bcrypt", reason="bcrypt required for DatabaseIdentityProvider tests"
)

from cqrs_ddd_identity import AccountLockedError, InvalidCredentialsError
from cqrs_ddd_identity.db import DatabaseIdentityProvider, PasswordHasher
from cqrs_ddd_identity.ports import (
    ILockoutStore,
    ISessionStore,
    IUserCredentialsRepository,
    UserCredentials,
)
from cqrs_ddd_identity.session import InMemorySessionStore


class InMemoryUserCredentialsRepository(IUserCredentialsRepository):
    """In-memory user credentials for testing."""

    def __init__(self) -> None:
        self._users: dict[str, UserCredentials] = {}

    def add(self, user: UserCredentials) -> None:
        self._users[user.username] = user
        if user.email:
            self._users[user.email] = user

    async def get_by_username(self, username: str) -> UserCredentials | None:
        return self._users.get(username)

    async def get_by_email(self, email: str) -> UserCredentials | None:
        return self._users.get(email)

    async def update_password_hash(self, user_id: str, new_hash: str) -> None:
        for k, u in list(self._users.items()):
            if u.user_id == user_id:
                self._users[k] = UserCredentials(
                    user_id=u.user_id,
                    username=u.username,
                    email=u.email,
                    password_hash=new_hash,
                    roles=u.roles,
                    permissions=u.permissions,
                    is_active=u.is_active,
                    is_locked=u.is_locked,
                    tenant_id=u.tenant_id,
                    mfa_enabled=u.mfa_enabled,
                )
                break

    async def update_last_login(self, user_id: str) -> None:
        pass


class InMemoryLockoutStore(ILockoutStore):
    """In-memory lockout store for testing."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._locked: dict[str, int] = {}  # identifier -> duration_seconds

    async def record_failure(self, identifier: str) -> int:
        self._failures[identifier] = self._failures.get(identifier, 0) + 1
        return self._failures[identifier]

    async def get_failure_count(self, identifier: str) -> int:
        return self._failures.get(identifier, 0)

    async def is_locked(self, identifier: str) -> bool:
        return identifier in self._locked

    async def clear(self, identifier: str) -> None:
        self._failures.pop(identifier, None)
        self._locked.pop(identifier, None)

    async def set_lockout(self, identifier: str, duration_seconds: int) -> None:
        self._locked[identifier] = duration_seconds


@pytest.fixture
def user_repo() -> InMemoryUserCredentialsRepository:
    return InMemoryUserCredentialsRepository()


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def lockout_store() -> InMemoryLockoutStore:
    return InMemoryLockoutStore()


@pytest.fixture
def db_provider(
    user_repo: InMemoryUserCredentialsRepository,
    session_store: ISessionStore,
    lockout_store: InMemoryLockoutStore,
) -> DatabaseIdentityProvider:
    hasher = PasswordHasher()
    user_repo.add(
        UserCredentials(
            user_id="user-1",
            username="alice",
            email="alice@example.com",
            password_hash=hasher.hash("correct-password"),
            roles=frozenset(["user"]),
            permissions=frozenset(),
            is_active=True,
        )
    )
    return DatabaseIdentityProvider(
        user_repository=user_repo,
        session_store=session_store,
        lockout_store=lockout_store,
        max_failed_attempts=3,
        lockout_duration_seconds=300,
    )


class TestDatabaseIdentityProviderAccountLocked:
    """Test account lockout and AccountLockedError."""

    @pytest.mark.asyncio
    async def test_account_locked_after_max_failed_attempts(
        self,
        db_provider: DatabaseIdentityProvider,
        lockout_store: InMemoryLockoutStore,
    ) -> None:
        """After max_failed_attempts, authenticate raises AccountLockedError with attributes."""
        # Exhaust failed attempts for "alice"
        for _ in range(3):
            with pytest.raises(InvalidCredentialsError):
                await db_provider.authenticate("alice", "wrong-password")

        # Next attempt (wrong or right) should hit lockout
        with pytest.raises(AccountLockedError) as exc_info:
            await db_provider.authenticate("alice", "correct-password")

        err = exc_info.value
        assert err.lockout_duration == 300
        assert err.failed_attempts == 3

    @pytest.mark.asyncio
    async def test_successful_login_clears_lockout(
        self,
        db_provider: DatabaseIdentityProvider,
    ) -> None:
        """Successful login clears failure count."""
        with pytest.raises(InvalidCredentialsError):
            await db_provider.authenticate("alice", "wrong-password")
        # One failure; now correct password should work
        token_response = await db_provider.authenticate("alice", "correct-password")
        assert token_response.access_token
        assert token_response.refresh_token
