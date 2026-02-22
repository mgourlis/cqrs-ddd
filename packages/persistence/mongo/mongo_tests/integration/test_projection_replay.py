"""Integration tests for projection replay with MongoDB."""

from dataclasses import dataclass

import pytest

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.ports.event_store import StoredEvent
from cqrs_ddd_persistence_mongo import (
    MongoCheckpointStore,
    MongoEventStore,
    MongoProjectionStore,
)


@dataclass(frozen=True)
class SampleEvent(DomainEvent):
    """Sample event for projection replay tests."""

    aggregate_id: str


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projection_replay_full(real_mongo_connection):
    """Test full projection replay from beginning."""
    # Setup
    event_store = MongoEventStore(real_mongo_connection, database="test_db")
    checkpoint_store = MongoCheckpointStore(real_mongo_connection, database="test_db")
    projection_store = MongoProjectionStore(
        connection=real_mongo_connection, database="test_db"
    )

    # Store events
    events = [
        StoredEvent(
            event_id=f"evt{i}",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=i,
            payload={"value": i * 10},
        )
        for i in range(1, 6)
    ]

    await event_store.append_batch(events)

    # Simulate projection worker
    projection_name = "test_projection"
    collection = "test_projections"

    # Clear collection for fresh replay
    await projection_store.drop_collection(collection)

    # Get events from beginning
    all_events = await event_store.get_all()

    for event in all_events:
        # Process event (simulate handler)
        await projection_store.upsert(
            collection,
            event.aggregate_id,
            {"id": event.aggregate_id, "value": event.payload["value"]},
        )

    # Save checkpoint
    last_position = all_events[-1].position
    await checkpoint_store.save_position(projection_name, last_position)

    # Verify
    position = await checkpoint_store.get_position(projection_name)
    assert position == last_position


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projection_resume_from_checkpoint(real_mongo_connection):
    """Test projection resumes from last checkpoint."""
    event_store = MongoEventStore(real_mongo_connection, database="test_db")
    checkpoint_store = MongoCheckpointStore(real_mongo_connection, database="test_db")
    projection_store = MongoProjectionStore(
        connection=real_mongo_connection, database="test_db"
    )

    # Initial batch
    events_batch1 = [
        StoredEvent(
            event_id=f"evt{i}",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=i,
            payload={"value": i},
        )
        for i in range(1, 4)
    ]

    await event_store.append_batch(events_batch1)

    # Process first batch
    projection_name = "test_projection_resume"
    collection = "test_projections_resume"

    await projection_store.drop_collection(collection)

    for event in await event_store.get_events_after(position=0):
        await projection_store.upsert(
            collection,
            event.aggregate_id,
            {"id": event.aggregate_id, "value": event.payload["value"]},
        )
        # Save checkpoint after each event
        await checkpoint_store.save_position(projection_name, event.position)

    # Add more events
    events_batch2 = [
        StoredEvent(
            event_id=f"evt{i}",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=i,
            payload={"value": i},
        )
        for i in range(4, 7)
    ]

    await event_store.append_batch(events_batch2)

    # Resume from checkpoint
    last_position = await checkpoint_store.get_position(projection_name)
    assert last_position == 3

    # Process new events
    for event in await event_store.get_events_after(position=last_position):
        await projection_store.upsert(
            collection,
            event.aggregate_id,
            {"id": event.aggregate_id, "value": event.payload["value"]},
        )
        await checkpoint_store.save_position(projection_name, event.position)

    # Verify final position
    final_position = await checkpoint_store.get_position(projection_name)
    assert final_position == 6


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projection_batch_upsert(real_mongo_connection):
    """Test batch upsert for efficient projection updates."""
    projection_store = MongoProjectionStore(
        connection=real_mongo_connection, database="test_db"
    )
    collection = "test_batch_projections"

    # Clear collection
    await projection_store.drop_collection(collection)

    # Batch upsert
    docs = [
        {"id": f"doc{i}", "value": i * 10}
        for i in range(1, 6)
    ]

    await projection_store.upsert_batch(collection, docs)

    # Verify all docs exist
    coll = projection_store._coll(collection)
    count = await coll.count_documents({})
    assert count == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projection_ttl_index(real_mongo_connection):
    """Test that TTL indexes can be created for projections."""
    projection_store = MongoProjectionStore(
        connection=real_mongo_connection, database="test_db"
    )
    collection = "test_ttl_projections"

    # Create TTL index
    await projection_store.ensure_ttl_index(
        collection,
        field="created_at",
        expire_after_seconds=3600,
    )

    # Verify index exists (just check it doesn't raise)
    coll = projection_store._coll(collection)
    indexes = [idx async for idx in coll.list_indexes()]

    # Check for TTL index
    ttl_indexes = [
        idx for idx in indexes
        if idx.get("expireAfterSeconds") == 3600
    ]

    assert len(ttl_indexes) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_projections_independent(real_mongo_connection):
    """Test that multiple projections maintain independent checkpoints."""
    checkpoint_store = MongoCheckpointStore(real_mongo_connection, database="test_db")

    # Save different positions for different projections
    await checkpoint_store.save_position("projection_a", 100)
    await checkpoint_store.save_position("projection_b", 200)
    await checkpoint_store.save_position("projection_c", 300)

    # Verify independence
    assert await checkpoint_store.get_position("projection_a") == 100
    assert await checkpoint_store.get_position("projection_b") == 200
    assert await checkpoint_store.get_position("projection_c") == 300

    # Update one projection
    await checkpoint_store.save_position("projection_b", 250)

    # Verify others unchanged
    assert await checkpoint_store.get_position("projection_a") == 100
    assert await checkpoint_store.get_position("projection_b") == 250
    assert await checkpoint_store.get_position("projection_c") == 300


@pytest.mark.integration
@pytest.mark.asyncio
async def test_projection_new_aggregate_creates_checkpoint(real_mongo_connection):
    """Test that get_position returns None for new projection."""
    checkpoint_store = MongoCheckpointStore(real_mongo_connection, database="test_db")

    # Never-before-seen projection
    position = await checkpoint_store.get_position("brand_new_projection")

    assert position is None
