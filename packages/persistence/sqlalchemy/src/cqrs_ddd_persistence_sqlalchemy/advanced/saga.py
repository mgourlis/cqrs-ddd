"""
SQLAlchemy implementation of Saga persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import select

from cqrs_ddd_advanced_core.ports.saga_repository import ISagaRepository
from cqrs_ddd_advanced_core.sagas.state import SagaState
from cqrs_ddd_advanced_core.sagas.state import SagaStatus as DomainSagaStatus

from ..core.repository import SQLAlchemyRepository, UnitOfWorkFactory
from .models import SagaStateModel, SagaStatus


class SQLAlchemySagaRepository(SQLAlchemyRepository[SagaState, str], ISagaRepository):
    """
    SQLAlchemy-backed repository for Saga state.
    Inherits from the generic SQLAlchemyRepository for standard CRUD,
    and implements ISagaRepository for specialized saga queries.
    """

    def __init__(
        self,
        saga_cls: type[SagaState] = SagaState,
        uow_factory: UnitOfWorkFactory | None = None,
    ) -> None:
        # We always use SagaStateModel for Sagas
        super().__init__(saga_cls, SagaStateModel, uow_factory=uow_factory)
        self._saga_domain_cls = saga_cls

    @property
    def saga_type(self) -> str:
        return self._saga_domain_cls.__name__

    def to_model(self, entity: SagaState) -> SagaStateModel:
        """
        Custom mapping for SagaState to handle step_history and state snapshot.
        """
        model = super().to_model(entity)

        # Ensure saga_type is set
        model.saga_type = self.saga_type

        # Map step_history to events JSON column
        model.events = [s.model_dump(mode="json") for s in entity.step_history]

        # Store full state minus the history in the state JSON column
        model.state = entity.model_dump(mode="json", exclude={"step_history"})

        return cast("SagaStateModel", model)

    def from_model(self, model: SagaStateModel) -> SagaState:
        """
        Convert SQLAlchemy model back to domain SagaState.
        """
        # We use the state snapshot if available, otherwise reconstruct from columns
        data = model.state.copy() if model.state else {}

        # Ensure critical fields from columns override state snapshot
        data["id"] = model.id
        data["correlation_id"] = model.correlation_id
        data["status"] = DomainSagaStatus(model.status.value)
        data["_version"] = model.version
        data["created_at"] = model.created_at
        data["updated_at"] = model.updated_at
        data["timeout_at"] = model.timeout_at

        # Maps events back to step_history
        if model.events:
            data["step_history"] = model.events

        # Use constructor to ensure AggregateRoot.__init__ runs
        # and sets private attributes
        return self._saga_domain_cls(**data)

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        """Find a saga instance by its correlation_id and type."""
        active_uow = self._get_active_uow()
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        stmt = select(SagaStateModel).where(
            SagaStateModel.correlation_id == correlation_id,
            SagaStateModel.saga_type == saga_type,
        )
        result = await active_uow.session.execute(stmt)
        model = result.scalars().first()
        return self.from_model(model) if model else None

    async def find_stalled_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return sagas that are RUNNING but have stalled (beyond update threshold)."""
        active_uow = self._get_active_uow()
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        # Assume anything not updated in 5 minutes is stalled.
        threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

        stmt = (
            select(SagaStateModel)
            .where(
                SagaStateModel.status == SagaStatus.RUNNING,
                SagaStateModel.updated_at < threshold,
                SagaStateModel.saga_type == self.saga_type,
            )
            .limit(limit)
        )
        result = await active_uow.session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]

    async def find_suspended_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return all currently suspended sagas."""
        active_uow = self._get_active_uow()
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        stmt = (
            select(SagaStateModel)
            .where(
                SagaStateModel.status == SagaStatus.SUSPENDED,
                SagaStateModel.saga_type == self.saga_type,
            )
            .limit(limit)
        )
        result = await active_uow.session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]

    async def find_expired_suspended_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return suspended sagas whose timeout_at has passed."""
        active_uow = self._get_active_uow()
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        now = datetime.now(timezone.utc)
        stmt = (
            select(SagaStateModel)
            .where(
                SagaStateModel.status == SagaStatus.SUSPENDED,
                SagaStateModel.timeout_at < now,
                SagaStateModel.saga_type == self.saga_type,
            )
            .limit(limit)
        )
        result = await active_uow.session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]
