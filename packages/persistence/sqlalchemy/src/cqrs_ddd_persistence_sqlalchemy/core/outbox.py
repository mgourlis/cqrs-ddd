"""
SQLAlchemy implementation of the transactional outbox storage.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cqrs_ddd_core.ports.outbox import IOutboxStorage, OutboxMessage
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from .models import OutboxMessage as OutboxMessageModel
from .models import OutboxStatus


class SQLAlchemyOutboxStorage(IOutboxStorage):
    """
    Transactional outbox storage implementation using SQLAlchemy.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_messages(
        self,
        messages: list[OutboxMessage],
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> None:
        """
        Persist outbox messages in the same transaction as the aggregate changes.
        """
        for msg in messages:
            model = OutboxMessageModel(
                event_id=msg.message_id,
                event_type=msg.event_type,
                payload=msg.payload,
                status=OutboxStatus.PENDING,
                created_at=msg.created_at,
                occurred_at=msg.created_at,
                retry_count=msg.retry_count,
                error=msg.error,
                event_metadata=msg.metadata,
            )
            self.session.add(model)

    async def get_pending(
        self,
        limit: int = 100,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> list[OutboxMessage]:
        """
        Retrieve unpublished messages, ordered by creation time.
        """
        stmt = (
            select(OutboxMessageModel)
            .where(OutboxMessageModel.status == OutboxStatus.PENDING)
            .order_by(OutboxMessageModel.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [
            OutboxMessage(
                message_id=m.event_id,
                event_type=m.event_type,
                payload=m.payload,
                metadata=m.event_metadata or {},
                created_at=m.created_at,
                published_at=None,
                error=m.error,
                retry_count=m.retry_count,
            )
            for m in models
        ]

    async def mark_published(
        self,
        message_ids: list[str],
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> None:
        """
        Mark messages as successfully published.
        """
        stmt = (
            update(OutboxMessageModel)
            .where(OutboxMessageModel.event_id.in_(message_ids))
            .values(status=OutboxStatus.PUBLISHED)
        )
        await self.session.execute(stmt)

    async def mark_failed(
        self,
        message_id: str,
        error: str,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> None:
        """
        Record a publication failure for retry logic.
        """
        stmt = (
            update(OutboxMessageModel)
            .where(OutboxMessageModel.event_id == message_id)
            .values(
                status=OutboxStatus.FAILED,
                error=error,
                retry_count=OutboxMessageModel.retry_count + 1,
            )
        )
        await self.session.execute(stmt)
