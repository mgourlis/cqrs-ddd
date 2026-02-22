"""Tests for MongoEventStore."""

import pytest

from cqrs_ddd_core.ports.event_store import StoredEvent
from cqrs_ddd_persistence_mongo import MongoEventStore


@pytest.mark.asyncio
async def test_append_increments_position(mongo_connection):
    """Test that each append increments position."""
    store = MongoEventStore(mongo_connection)

    event1 = StoredEvent(
        event_id="evt1",
        event_type="TestEvent",
        aggregate_id="agg1",
        aggregate_type="TestAggregate",
        version=1,
    )
    event2 = StoredEvent(
        event_id="evt2",
        event_type="TestEvent",
        aggregate_id="agg1",
        aggregate_type="TestAggregate",
        version=2,
    )

    await store.append(event1)
    await store.append(event2)

    events = await store.get_events("agg1")

    assert len(events) == 2
    assert events[0].position == 1
    assert events[1].position == 2


@pytest.mark.asyncio
async def test_append_batch_assigns_positions(mongo_connection):
    """Test that batch append assigns sequential positions."""
    store = MongoEventStore(mongo_connection)

    events = [
        StoredEvent(
            event_id=f"evt{i}",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=i,
        )
        for i in range(1, 4)
    ]

    await store.append_batch(events)

    stored = await store.get_events("agg1")

    assert len(stored) == 3
    assert stored[0].position == 1
    assert stored[1].position == 2
    assert stored[2].position == 3


@pytest.mark.asyncio
async def test_get_events_after_version(mongo_connection):
    """Test that get_events respects after_version filter."""
    store = MongoEventStore(mongo_connection)

    for i in range(1, 6):
        await store.append(
            StoredEvent(
                event_id=f"evt{i}",
                event_type="TestEvent",
                aggregate_id="agg1",
                aggregate_type="TestAggregate",
                version=i,
            )
        )

    events = await store.get_events("agg1", after_version=2)

    assert len(events) == 3
    assert all(evt.version > 2 for evt in events)


@pytest.mark.asyncio
async def test_get_events_returns_in_version_order(mongo_connection):
    """Test that get_events returns events in version order."""
    store = MongoEventStore(mongo_connection)

    # Add events out of order
    await store.append(
        StoredEvent(
            event_id="evt3",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=3,
        )
    )
    await store.append(
        StoredEvent(
            event_id="evt1",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=1,
        )
    )
    await store.append(
        StoredEvent(
            event_id="evt2",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=2,
        )
    )

    events = await store.get_events("agg1")

    assert events[0].version == 1
    assert events[1].version == 2
    assert events[2].version == 3


@pytest.mark.asyncio
async def test_get_by_aggregate_filters_by_type(mongo_connection):
    """Test that get_by_aggregate filters by aggregate_type when provided."""
    store = MongoEventStore(mongo_connection)

    await store.append(
        StoredEvent(
            event_id="evt1",
            event_type="Event1",
            aggregate_id="agg1",
            aggregate_type="TypeA",
            version=1,
        )
    )
    await store.append(
        StoredEvent(
            event_id="evt2",
            event_type="Event2",
            aggregate_id="agg1",
            aggregate_type="TypeB",
            version=1,
        )
    )

    events_a = await store.get_by_aggregate("agg1", aggregate_type="TypeA")
    events_b = await store.get_by_aggregate("agg1", aggregate_type="TypeB")

    assert len(events_a) == 1
    assert events_a[0].aggregate_type == "TypeA"
    assert len(events_b) == 1
    assert events_b[0].aggregate_type == "TypeB"


@pytest.mark.asyncio
async def test_get_events_after_returns_correct_subset(mongo_connection):
    """Test that get_events_after returns events after given position."""
    store = MongoEventStore(mongo_connection)

    for i in range(1, 6):
        await store.append(
            StoredEvent(
                event_id=f"evt{i}",
                event_type="TestEvent",
                aggregate_id=f"agg{i}",
                aggregate_type="TestAggregate",
                version=i,
            )
        )

    events = await store.get_events_after(position=2, limit=10)

    assert len(events) == 3
    assert all(evt.position > 2 for evt in events)


@pytest.mark.asyncio
async def test_get_events_after_respects_limit(mongo_connection):
    """Test that get_events_after respects limit parameter."""
    store = MongoEventStore(mongo_connection)

    for i in range(1, 11):
        await store.append(
            StoredEvent(
                event_id=f"evt{i}",
                event_type="TestEvent",
                aggregate_id="agg1",
                aggregate_type="TestAggregate",
                version=i,
            )
        )

    events = await store.get_events_after(position=0, limit=5)

    assert len(events) == 5


@pytest.mark.asyncio
async def test_get_all_returns_all_events(mongo_connection):
    """Test that get_all returns all stored events."""
    store = MongoEventStore(mongo_connection)

    for i in range(1, 4):
        await store.append(
            StoredEvent(
                event_id=f"evt{i}",
                event_type="TestEvent",
                aggregate_id=f"agg{i}",
                aggregate_type="TestAggregate",
                version=i,
            )
        )

    events = await store.get_all()

    assert len(events) == 3


@pytest.mark.asyncio
async def test_custom_database(mongo_connection):
    """Test that event store can use a custom database."""
    store = MongoEventStore(mongo_connection, database="test_db")

    await store.append(
        StoredEvent(
            event_id="evt1",
            event_type="TestEvent",
            aggregate_id="agg1",
            aggregate_type="TestAggregate",
            version=1,
        )
    )

    events = await store.get_events("agg1")

    assert len(events) == 1
