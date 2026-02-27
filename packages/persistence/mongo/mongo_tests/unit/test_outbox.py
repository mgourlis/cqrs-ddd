"""Tests for MongoOutboxStorage."""

import pytest

from cqrs_ddd_core.ports.outbox import OutboxMessage
from cqrs_ddd_persistence_mongo import MongoOutboxStorage


@pytest.mark.asyncio
async def test_save_messages(mongo_connection):
    """Test that messages are persisted to outbox."""
    storage = MongoOutboxStorage(mongo_connection)

    messages = [
        OutboxMessage(
            message_id="msg1",
            event_type="TestEvent",
            payload={"key": "value"},
        ),
        OutboxMessage(
            message_id="msg2",
            event_type="AnotherEvent",
            payload={"another": "data"},
        ),
    ]

    await storage.save_messages(messages)

    # Verify messages were saved
    pending = await storage.get_pending(limit=10)
    assert len(pending) == 2
    assert pending[0].message_id == "msg1"
    assert pending[1].message_id == "msg2"


@pytest.mark.asyncio
async def test_get_pending_returns_only_pending(mongo_connection):
    """Test that get_pending only returns pending messages."""
    storage = MongoOutboxStorage(mongo_connection)

    # Add a published message
    await storage.save_messages(
        [OutboxMessage(message_id="published", event_type="TestEvent", payload={})]
    )
    await storage.mark_published(["published"])

    # Add pending messages
    await storage.save_messages(
        [
            OutboxMessage(message_id="pending1", event_type="TestEvent", payload={}),
            OutboxMessage(message_id="pending2", event_type="TestEvent", payload={}),
        ]
    )

    pending = await storage.get_pending(limit=10)

    assert len(pending) == 2
    assert all(msg.message_id in ("pending1", "pending2") for msg in pending)


@pytest.mark.asyncio
async def test_get_pending_orders_by_created_at(mongo_connection):
    """Test that get_pending returns messages in creation order."""
    storage = MongoOutboxStorage(mongo_connection)

    # Add messages with slight delay to ensure different timestamps
    import asyncio

    await storage.save_messages(
        [OutboxMessage(message_id="first", event_type="TestEvent", payload={})]
    )
    await asyncio.sleep(0.01)
    await storage.save_messages(
        [OutboxMessage(message_id="second", event_type="TestEvent", payload={})]
    )
    await asyncio.sleep(0.01)
    await storage.save_messages(
        [OutboxMessage(message_id="third", event_type="TestEvent", payload={})]
    )

    pending = await storage.get_pending(limit=10)

    assert len(pending) == 3
    assert pending[0].message_id == "first"
    assert pending[1].message_id == "second"
    assert pending[2].message_id == "third"


@pytest.mark.asyncio
async def test_get_pending_respects_limit(mongo_connection):
    """Test that get_pending respects the limit parameter."""
    storage = MongoOutboxStorage(mongo_connection)

    # Add multiple messages
    messages = [
        OutboxMessage(message_id=f"msg{i}", event_type="TestEvent", payload={})
        for i in range(10)
    ]
    await storage.save_messages(messages)

    # Request only 5
    pending = await storage.get_pending(limit=5)

    assert len(pending) == 5


@pytest.mark.asyncio
async def test_mark_published(mongo_connection):
    """Test that messages are marked as published."""
    storage = MongoOutboxStorage(mongo_connection)

    await storage.save_messages(
        [
            OutboxMessage(message_id="msg1", event_type="TestEvent", payload={}),
            OutboxMessage(message_id="msg2", event_type="TestEvent", payload={}),
        ]
    )
    await storage.mark_published(["msg1"])

    pending = await storage.get_pending(limit=10)

    assert len(pending) == 1
    assert pending[0].message_id == "msg2"


@pytest.mark.asyncio
async def test_mark_failed_increments_retry_count(mongo_connection):
    """Test that mark_failed increments retry count."""
    storage = MongoOutboxStorage(mongo_connection)

    await storage.save_messages(
        [OutboxMessage(message_id="msg1", event_type="TestEvent", payload={})]
    )

    await storage.mark_failed("msg1", "Test error")

    # Check retry count - need to query directly since get_pending doesn't show failed
    coll = storage._collection()
    doc = await coll.find_one({"_id": "msg1"})

    assert doc["status"] == "failed"
    assert doc["retry_count"] == 1
    assert doc["error"] == "Test error"


@pytest.mark.asyncio
async def test_mark_failed_multiple_times(mongo_connection):
    """Test that mark_failed increments retry count on multiple failures."""
    storage = MongoOutboxStorage(mongo_connection)

    await storage.save_messages(
        [OutboxMessage(message_id="msg1", event_type="TestEvent", payload={})]
    )

    await storage.mark_failed("msg1", "Error 1")
    await storage.mark_failed("msg1", "Error 2")

    coll = storage._collection()
    doc = await coll.find_one({"_id": "msg1"})

    assert doc["retry_count"] == 2
    assert doc["error"] == "Error 2"


@pytest.mark.asyncio
async def test_custom_database(mongo_connection):
    """Test that outbox storage can use a custom database."""
    storage = MongoOutboxStorage(mongo_connection, database="test_db")

    await storage.save_messages(
        [OutboxMessage(message_id="msg1", event_type="TestEvent", payload={})]
    )

    pending = await storage.get_pending(limit=10)

    assert len(pending) == 1
