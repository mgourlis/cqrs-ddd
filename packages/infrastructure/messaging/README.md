# cqrs-ddd-messaging

Message transport adapters implementing `IMessagePublisher` and `IMessageConsumer` from `cqrs-ddd-core` for RabbitMQ, Kafka, SQS, and in-memory testing.

---

## Installation

```bash
pip install cqrs-ddd-messaging
# With optional transports:
pip install cqrs-ddd-messaging[rabbitmq]
pip install cqrs-ddd-messaging[kafka]
pip install cqrs-ddd-messaging[sqs]
pip install cqrs-ddd-messaging[all]
```

Requires `cqrs-ddd-core`.

---

## Core types

- **MessageEnvelope** — Immutable wrapper: `message_id`, `event_type`, `payload`, `correlation_id`, `causation_id`, `timestamp`, `headers`, `attempt`.
- **EnvelopeSerializer** — JSON roundtrip; uses `EventTypeRegistry` from core for type-safe hydration of domain events.
- **RetryPolicy** — Exponential backoff, `max_attempts`, `base_delay`, `max_delay`, optional jitter.
- **IdempotencyFilter** — Deduplication by `message_id` via `ICacheService` or in-memory set (for tests).
- **DeadLetterHandler** — Routes failed messages after max retries; optional callback for DLQ publish or storage.

---

## Usage

### In-memory (testing)

Use a shared bus so that publish triggers subscribed handlers synchronously. Assert on published messages in tests.

```python
from cqrs_ddd_messaging import InMemoryPublisher, InMemoryConsumer, MessageEnvelope

pub = InMemoryPublisher()
consumer = InMemoryConsumer(pub.bus)

async def handler(payload):
    ...

await consumer.subscribe("orders", handler)
await pub.publish("orders", MessageEnvelope(event_type="OrderCreated", payload={"id": "1"}))

pub.assert_published("OrderCreated", count=1)
assert len(pub.get_published()) == 1
```

### RabbitMQ

Install with `[rabbitmq]`. Topic exchange, routing keys, prefetch, manual ack/nack. Optional retry and dead-letter.

```python
from cqrs_ddd_messaging.rabbitmq import (
    RabbitMQConnectionManager,
    RabbitMQPublisher,
    RabbitMQConsumer,
)

conn = RabbitMQConnectionManager(url="amqp://guest:guest@localhost/")
await conn.connect()

publisher = RabbitMQPublisher(connection=conn, exchange_name="events")
await publisher.publish("orders", MessageEnvelope(event_type="OrderCreated", payload={"id": "1"}))

consumer = RabbitMQConsumer(connection=conn, exchange_name="events")
await consumer.subscribe("orders", handler)
# Messages are delivered via aio-pika; ensure event loop runs
await conn.close()
```

### Kafka

Install with `[kafka]`. Partition key (e.g. `aggregate_id`) for ordering; consumer groups; manual offset commit.

```python
from cqrs_ddd_messaging.kafka import (
    KafkaConnectionManager,
    KafkaPublisher,
    KafkaConsumer,
)

conn = KafkaConnectionManager(bootstrap_servers="localhost:9092")
publisher = KafkaPublisher(connection=conn)
await publisher.publish("order-events", event)  # event with aggregate_id used as partition key

consumer = KafkaConsumer(connection=conn, group_id="my-service")
await consumer.subscribe("order-events", handler)
await consumer.run()  # or run in a background task
```

### SQS

Install with `[sqs]`. Long-polling, visibility timeout. FIFO queues use `message_id` as deduplication id.

```python
from cqrs_ddd_messaging.sqs import SQSConnectionManager, SQSPublisher, SQSConsumer

conn = SQSConnectionManager(region_name="us-east-1")
publisher = SQSPublisher(connection=conn)
await publisher.publish("my-queue", MessageEnvelope(event_type="OrderCreated", payload={...}))

consumer = SQSConsumer(connection=conn, wait_time_seconds=20)
await consumer.subscribe("my-queue", handler)
await consumer.run()
```

---

## Serialization

Domain events are wrapped in `MessageEnvelope` and serialized as JSON. Use `EventTypeRegistry` from core to hydrate payloads back to domain events:

```python
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_messaging import EnvelopeSerializer, MessageEnvelope

registry = EventTypeRegistry()
registry.register("OrderCreated", OrderCreated)

serializer = EnvelopeSerializer(registry=registry)
raw = serializer.serialize(envelope)
envelope = serializer.deserialize(raw)
event = serializer.hydrate(envelope)  # -> OrderCreated instance or payload dict
```

---

## Exceptions

- **MessagingError** — Base for all messaging failures (inherits from core `InfrastructureError`).
- **MessagingConnectionError** — Broker connectivity failure.
- **MessagingSerializationError** — Serialize/deserialize failure.
- **DeadLetterError** — Raised when a message is routed to DLQ after max retries; carries `message_id`.

---

## License

MIT — see the project `LICENSE` file.
