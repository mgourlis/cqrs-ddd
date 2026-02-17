"""InMemoryUnitOfWork — tracks commit/rollback calls for unit tests."""

from __future__ import annotations

from ...ports.unit_of_work import UnitOfWork


class InMemoryUnitOfWork(UnitOfWork):
    """In-memory implementation of UnitOfWork for testing.

    Extends UnitOfWork to get on_commit hook support.
    Records commit/rollback calls for assertions.
    """

    def __init__(self) -> None:
        super().__init__()
        self.committed: bool = False
        self.rolled_back: bool = False
        self.commit_count: int = 0
        self.rollback_count: int = 0

    async def commit(self) -> None:
        """Record that commit was called."""
        if self.committed or self.rolled_back:
            return
        self.committed = True
        self.commit_count += 1

    async def rollback(self) -> None:
        """Record that rollback was called."""
        if self.committed or self.rolled_back:
            return
        self.rolled_back = True
        self.rollback_count += 1

    # ── Test helpers ─────────────────────────────────────────────

    def reset(self) -> None:
        """Reset commit/rollback tracking (for test setup)."""
        self.committed = False
        self.rolled_back = False
        self.commit_count = 0
        self.rollback_count = 0


def in_memory_unit_of_work_factory() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()
