"""ISagaRepository — persistence port for saga state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cqrs_ddd_core.ports.repository import IRepository

if TYPE_CHECKING:
    from ..sagas.state import SagaState


@runtime_checkable
class ISagaRepository(IRepository["SagaState", str], Protocol):
    """
    Port for saga state persistence.

    Extends IRepository with saga-specific query methods.
    Infrastructure packages (SQLAlchemy, Mongo, …) provide the real
    implementation. :class:`InMemorySagaRepository` is available from
    :mod:`cqrs_ddd_advanced_core.adapters.memory` for testing.
    """

    @property
    def saga_type(self) -> str:
        """Saga type identifier."""
        ...

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        """Find a saga instance by its ``correlation_id`` and type."""
        ...

    async def find_stalled_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return sagas that are RUNNING but have stalled (e.g. pending commands)."""
        ...

    async def find_suspended_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return all currently suspended sagas."""
        ...

    async def find_expired_suspended_sagas(
        self,
        limit: int = 10,
    ) -> list[SagaState]:
        """Return suspended sagas whose ``timeout_at`` has passed."""
        ...

    async def find_running_sagas_with_tcc_steps(
        self, limit: int = 10
    ) -> list[SagaState]:
        """Return RUNNING sagas that have TCC steps (state.tcc_steps non-empty)."""
        ...
