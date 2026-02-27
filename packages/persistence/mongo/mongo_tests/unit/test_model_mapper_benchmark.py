"""Performance benchmark for MongoDBModelMapper (5k+ docs)."""

import time
from decimal import Decimal

import pytest
from pydantic import BaseModel

from cqrs_ddd_persistence_mongo.core.model_mapper import MongoDBModelMapper


class FlatModel(BaseModel):
    id: str = ""
    name: str = ""
    value: int = 0
    amount: Decimal = Decimal("0")


class NestedModel(BaseModel):
    id: str = ""
    name: str = ""
    nested: dict | None = None


@pytest.fixture
def flat_mapper():
    return MongoDBModelMapper(FlatModel)


@pytest.fixture
def nested_mapper():
    return MongoDBModelMapper(NestedModel)


def _make_flat_entities(n: int) -> list[FlatModel]:
    return [
        FlatModel(id=f"e{i}", name=f"name-{i}", value=i, amount=Decimal(f"{i}.99"))
        for i in range(n)
    ]


def _make_flat_docs(n: int) -> list[dict]:
    from bson.decimal128 import Decimal128

    return [
        {
            "_id": f"e{i}",
            "name": f"name-{i}",
            "value": i,
            "amount": Decimal128(f"{i}.99"),
        }
        for i in range(n)
    ]


def _make_nested_entities(n: int) -> list[NestedModel]:
    return [
        NestedModel(
            id=f"e{i}",
            name=f"name-{i}",
            nested={"a": i, "b": f"v{i}", "inner": {"x": i * 2}},
        )
        for i in range(n)
    ]


def test_benchmark_flat_serialize_5000(flat_mapper):
    """Benchmark: 5000 flat entities → docs via to_docs."""
    entities = _make_flat_entities(5000)
    start = time.perf_counter()
    docs = flat_mapper.to_docs(entities)
    elapsed = time.perf_counter() - start
    assert len(docs) == 5000
    # Sanity: 5k flat docs should complete in under 2 seconds on typical hardware
    assert elapsed < 2.0, f"to_docs(5000) took {elapsed:.2f}s (expected < 2s)"


def test_benchmark_flat_deserialize_5000(flat_mapper):
    """Benchmark: 5000 flat docs → entities via from_docs."""
    docs = _make_flat_docs(5000)
    start = time.perf_counter()
    entities = flat_mapper.from_docs(docs)
    elapsed = time.perf_counter() - start
    assert len(entities) == 5000
    assert entities[0].amount == Decimal("0.99")
    assert elapsed < 2.0, f"from_docs(5000) took {elapsed:.2f}s (expected < 2s)"


def test_benchmark_nested_serialize_5000(nested_mapper):
    """Benchmark: 5000 nested entities → docs (recursive _serialize_custom_types)."""
    entities = _make_nested_entities(5000)
    start = time.perf_counter()
    docs = nested_mapper.to_docs(entities)
    elapsed = time.perf_counter() - start
    assert len(docs) == 5000
    assert elapsed < 3.0, f"to_docs(5000 nested) took {elapsed:.2f}s (expected < 3s)"


def test_benchmark_nested_deserialize_5000(nested_mapper):
    """Benchmark: 5000 nested docs → entities (recursive _deserialize_custom_types)."""
    entities = _make_nested_entities(5000)
    docs = nested_mapper.to_docs(entities)
    start = time.perf_counter()
    back = nested_mapper.from_docs(docs)
    elapsed = time.perf_counter() - start
    assert len(back) == 5000
    assert back[0].nested["inner"]["x"] == 0
    assert elapsed < 3.0, f"from_docs(5000 nested) took {elapsed:.2f}s (expected < 3s)"
