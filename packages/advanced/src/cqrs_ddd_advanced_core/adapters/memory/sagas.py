"""In-memory implementations of saga persistence for testing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cqrs_ddd_advanced_core.ports.saga_repository import ISagaRepository
from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
from cqrs_ddd_core.ports.search_result import SearchResult

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


class InMemorySagaRepository(ISagaRepository):
    """
    Dict-backed :class:`ISagaRepository` for unit / integration tests.

    No external dependencies — pure Python.
    """

    def __init__(self, saga_type: str = "BaseSaga") -> None:
        self._sagas: dict[str, SagaState] = {}
        self._saga_type = saga_type

    @property
    def saga_type(self) -> str:
        return self._saga_type

    async def add(self, entity: SagaState, _uow: UnitOfWork | None = None) -> str:
        """Persist a new or updated saga state."""
        # Simulate database version increment
        entity.increment_version()
        self._sagas[entity.id] = entity
        return entity.id

    async def get(
        self, entity_id: str, _uow: UnitOfWork | None = None
    ) -> SagaState | None:
        """Retrieve a saga by its ID."""
        return self._sagas.get(entity_id)

    async def delete(self, entity_id: str, _uow: UnitOfWork | None = None) -> str:
        """Delete a saga by its ID."""
        self._sagas.pop(entity_id, None)
        return entity_id

    async def list_all(
        self, entity_ids: list[str] | None = None, _uow: UnitOfWork | None = None
    ) -> builtins.list[SagaState]:
        """Retrieve sagas."""
        if entity_ids is None:
            return list(self._sagas.values())
        return [s for s_id, s in self._sagas.items() if s_id in entity_ids]

    async def search(
        self,
        criteria: ISpecification[SagaState],
        _uow: UnitOfWork | None = None,
    ) -> SearchResult[SagaState]:
        """Search for sagas matching the specification."""

        async def _list() -> builtins.list[SagaState]:
            return [s for s in self._sagas.values() if criteria.is_satisfied_by(s)]

        async def _stream(_batch_size: int | None) -> AsyncIterator[SagaState]:
            for s in self._sagas.values():
                if criteria.is_satisfied_by(s):
                    yield s

        return SearchResult(list_fn=_list, stream_fn=_stream)

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        for state in self._sagas.values():
            if state.correlation_id == correlation_id and state.saga_type == saga_type:
                return state
        return None

    async def find_stalled_sagas(self, limit: int = 10) -> builtins.list[SagaState]:
        """Return RUNNING sagas that still have pending commands."""
        result: list[SagaState] = []
        for state in self._sagas.values():
            if state.status == SagaStatus.RUNNING and state.pending_commands:
                result.append(state)
                if len(result) >= limit:
                    break
        return result

    async def find_suspended_sagas(self, limit: int = 10) -> builtins.list[SagaState]:
        result: list[SagaState] = []
        for state in self._sagas.values():
            if state.status == SagaStatus.SUSPENDED:
                result.append(state)
                if len(result) >= limit:
                    break
        return result

    async def find_expired_suspended_sagas(
        self, limit: int = 10
    ) -> builtins.list[SagaState]:
        now = datetime.now(timezone.utc)
        result: list[SagaState] = []
        for state in self._sagas.values():
            if (
                state.status == SagaStatus.SUSPENDED
                and state.timeout_at is not None
                and state.timeout_at <= now
            ):
                result.append(state)
                if len(result) >= limit:
                    break
        return result

    async def find_running_sagas_with_tcc_steps(
        self, limit: int = 10
    ) -> builtins.list[SagaState]:
        """Return RUNNING sagas that have TCC steps (state.tcc_steps non-empty)."""
        result: list[SagaState] = []
        for state in self._sagas.values():
            if state.status == SagaStatus.RUNNING and state.tcc_steps:
                result.append(state)
                if len(result) >= limit:
                    break
        return result

    # ── Test helpers ─────────────────────────────────────────────────

    def all_sagas(self) -> builtins.list[SagaState]:
        """Return all stored saga states (testing convenience)."""
        return list(self._sagas.values())

    def clear(self) -> None:
        """Wipe the store."""
        self._sagas.clear()
