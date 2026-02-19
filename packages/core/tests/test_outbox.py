"""Tests for the Outbox package — service, publisher, worker."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy
from cqrs_ddd_core.adapters.memory.outbox import InMemoryOutboxStorage
from cqrs_ddd_core.cqrs import BufferedOutbox as OutboxPublisher
from cqrs_ddd_core.cqrs import BufferedOutbox as OutboxWorker
from cqrs_ddd_core.cqrs import OutboxService
from cqrs_ddd_core.ports.outbox import OutboxMessage
from cqrs_ddd_core.primitives.exceptions import ConcurrencyError, OutboxError

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_publisher() -> AsyncMock:
    pub = AsyncMock()
    pub.publish = AsyncMock()
    return pub


def _make_message(
    event_type: str = "OrderCreated",
    payload: dict[str, object] | None = None,
    error: str | None = None,
    retry_count: int = 0,
    correlation_id: str = "test-correlation-id",
    causation_id: str | None = None,
) -> OutboxMessage:
    msg = OutboxMessage(
        event_type=event_type,
        payload=payload or {"order_id": "ord-1"},
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    msg.error = error
    msg.retry_count = retry_count
    return msg


# ═══════════════════════════════════════════════════════════════════════
# OutboxService tests
# ═══════════════════════════════════════════════════════════════════════


class TestOutboxService:
    @pytest.mark.asyncio
    async def test_process_batch_publishes_pending(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)

        msg = _make_message()
        await storage.save_messages([msg])

        count = await service.process_batch(batch_size=10)

        assert count == 1
        publisher.publish.assert_called_once_with(
            topic="OrderCreated",
            message={"order_id": "ord-1"},
            correlation_id="test-correlation-id",
        )
        # Message should be marked as published
        pending = await storage.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_process_batch_empty(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)

        count = await service.process_batch()
        assert count == 0
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_batch_handles_publish_failure(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        publisher.publish.side_effect = RuntimeError("broker down")
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)

        msg = _make_message()
        await storage.save_messages([msg])

        count = await service.process_batch()

        assert count == 0
        # Should be marked as failed with retry_count incremented
        pending = await storage.get_pending()
        assert len(pending) == 1
        assert pending[0].error == "broker down"
        assert pending[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_process_batch_partial_success(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        call_count = 0

        async def _sometimes_fail(topic: str, message: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("flaky")

        publisher.publish.side_effect = _sometimes_fail
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)

        m1 = _make_message(event_type="EventA")
        m2 = _make_message(event_type="EventB")
        m3 = _make_message(event_type="EventC")
        await storage.save_messages([m1, m2, m3])

        count = await service.process_batch()

        # 2 succeeded, 1 failed
        assert count == 2
        pending = await storage.get_pending()
        assert len(pending) == 1
        assert pending[0].event_type == "EventB"

    @pytest.mark.asyncio
    async def test_retry_failed(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(
            storage,
            publisher,
            lock_strategy,
            max_retries=3,
        )

        msg = _make_message(error="previous failure", retry_count=1)
        await storage.save_messages([msg])

        count = await service.retry_failed()

        assert count == 1
        publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_skips_exhausted(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(
            storage,
            publisher,
            lock_strategy,
            max_retries=3,
        )

        msg = _make_message(error="too many retries", retry_count=3)
        await storage.save_messages([msg])

        count = await service.retry_failed()
        assert count == 0
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_metadata_correlation_id_forwarded(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)

        msg = _make_message()
        msg.metadata["correlation_id"] = "corr-42"
        await storage.save_messages([msg])

        await service.process_batch()

        publisher.publish.assert_called_once_with(
            topic="OrderCreated",
            message={"order_id": "ord-1"},
            correlation_id="corr-42",
        )

    @pytest.mark.asyncio
    async def test_process_batch_publish_raises_mark_failed_called(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        publisher.publish.side_effect = RuntimeError("broker down")
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)
        msg = _make_message()
        await storage.save_messages([msg])

        count = await service.process_batch()

        assert count == 0
        pending = await storage.get_pending()
        failed = [m for m in pending if m.error]
        assert len(failed) == 1
        assert "broker down" in (failed[0].error or "")

    @pytest.mark.asyncio
    async def test_process_batch_lock_release_failure_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        lock_strategy.release = AsyncMock(side_effect=RuntimeError("release failed"))
        service = OutboxService(storage, publisher, lock_strategy)

        msg = _make_message()
        await storage.save_messages([msg])

        count = await service.process_batch()

        assert count == 1
        assert any(
            "release" in rec.message.lower() and "warning" in rec.levelname.lower()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_process_batch_concurrency_error_returns_zero(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        lock_strategy.acquire = AsyncMock(side_effect=ConcurrencyError("locked"))
        service = OutboxService(storage, publisher, lock_strategy)

        msg = _make_message()
        await storage.save_messages([msg])

        count = await service.process_batch()

        assert count == 0
        publisher.publish.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# OutboxPublisher tests
# ═══════════════════════════════════════════════════════════════════════


class TestOutboxPublisher:
    @pytest.mark.asyncio
    async def test_publish_dict(self) -> None:
        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)

        await pub.publish("OrderCreated", {"order_id": "1"})

        pending = await storage.get_pending()
        assert len(pending) == 1
        assert pending[0].event_type == "OrderCreated"
        assert pending[0].payload == {"order_id": "1"}

    @pytest.mark.asyncio
    async def test_publish_pydantic_model(self) -> None:
        from pydantic import BaseModel

        class EvtPayload(BaseModel):
            order_id: str = "ord-1"

        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)

        await pub.publish("OrderCreated", EvtPayload())

        pending = await storage.get_pending()
        assert len(pending) == 1
        assert pending[0].payload == {"order_id": "ord-1"}

    @pytest.mark.asyncio
    async def test_publish_plain_object(self) -> None:
        class Payload:
            def __init__(self) -> None:
                self.order_id = "ord-1"

        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)

        await pub.publish("OrderCreated", Payload())

        pending = await storage.get_pending()
        assert len(pending) == 1
        assert pending[0].payload["order_id"] == "ord-1"

    @pytest.mark.asyncio
    async def test_publish_with_metadata_kwargs(self) -> None:
        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)

        await pub.publish(
            "OrderCreated",
            {"order_id": "1"},
            correlation_id="corr-1",
            causation_id="cause-1",
        )

        pending = await storage.get_pending()
        assert pending[0].metadata["correlation_id"] == "corr-1"
        assert pending[0].metadata["causation_id"] == "cause-1"

    @pytest.mark.asyncio
    async def test_publish_string_fallback(self) -> None:
        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)

        await pub.publish("Topic", 42)

        pending = await storage.get_pending()
        assert "raw" in pending[0].payload


# ═══════════════════════════════════════════════════════════════════════
# OutboxWorker tests
# ═══════════════════════════════════════════════════════════════════════


class TestOutboxWorker:
    @pytest.mark.asyncio
    async def test_run_once(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage, broker=publisher, lock_strategy=lock_strategy
        )

        msg = _make_message()
        await storage.save_messages([msg])

        count = await worker._service.process_batch(worker.batch_size)
        assert count == 1

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage,
            broker=publisher,
            lock_strategy=lock_strategy,
            poll_interval=0.01,
        )

        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()

        assert not worker._running

    @pytest.mark.asyncio
    async def test_inject_service_directly(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        service = OutboxService(storage, publisher, lock_strategy)
        worker = OutboxWorker(service=service)

        msg = _make_message()
        await storage.save_messages([msg])

        count = await worker._service.process_batch(worker.batch_size)
        assert count == 1

    def test_missing_args_raises(self) -> None:
        with pytest.raises(OutboxError, match="Either 'service'"):
            OutboxWorker(
                storage=InMemoryOutboxStorage(),
            )

    @pytest.mark.asyncio
    async def test_worker_handles_errors_gracefully(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        publisher.publish.side_effect = RuntimeError("boom")
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage,
            broker=publisher,
            lock_strategy=lock_strategy,
            poll_interval=0.01,
        )

        msg = _make_message()
        await storage.save_messages([msg])

        # Should not raise
        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()

    @pytest.mark.asyncio
    async def test_trigger_wakes_loop(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage,
            broker=publisher,
            lock_strategy=lock_strategy,
            poll_interval=10.0,
            wait_delay=0.02,
            max_delay=0.05,
        )
        msg = _make_message()
        await storage.save_messages([msg])

        await worker.start()
        worker.trigger()
        await asyncio.sleep(0.1)
        await worker.stop()

        publisher.publish.assert_called()
        pending = await storage.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage,
            broker=publisher,
            lock_strategy=lock_strategy,
            poll_interval=10.0,
        )
        with patch.object(
            worker._service, "process_batch", new_callable=AsyncMock
        ) as mock_batch:
            mock_batch.return_value = 0
            await worker.start()
            await worker.start()
            await worker.stop()
        assert not worker._running
        assert worker._task is not None or not worker._running

    @pytest.mark.asyncio
    async def test_run_loop_logs_and_continues_on_process_batch_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        storage = InMemoryOutboxStorage()
        publisher = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        worker = OutboxWorker(
            storage=storage,
            broker=publisher,
            lock_strategy=lock_strategy,
            poll_interval=0.02,
            wait_delay=0.01,
            max_delay=0.02,
        )
        call_count = 0

        async def _raise_second(*args: Any, **kwargs: Any) -> int:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("batch failed")
            return 0

        with patch.object(worker._service, "process_batch", side_effect=_raise_second):
            await worker.start()
            worker.trigger()
            await asyncio.sleep(0.15)
            await worker.stop()

        assert any(
            "batch failed" in rec.message or "loop error" in rec.message.lower()
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_publish_with_uow_on_commit_calls_trigger(self) -> None:
        storage = InMemoryOutboxStorage()
        broker = _make_publisher()
        lock_strategy = InMemoryLockStrategy()
        pub = OutboxPublisher(storage, broker, lock_strategy)
        on_commit_callback: list[Any] = []

        class MockUoW:
            def on_commit(self, cb: Any) -> None:
                on_commit_callback.append(cb)

        with patch(
            "cqrs_ddd_core.cqrs.outbox.buffered.get_current_uow", return_value=MockUoW()
        ):
            await pub.publish("OrderCreated", {"order_id": "1"})

        assert len(on_commit_callback) == 1
        assert callable(on_commit_callback[0])
        assert getattr(on_commit_callback[0], "__self__", None) is pub
