from cqrs_ddd_advanced_core.conflict.resolution import (
    DeepMergeStrategy,
    FieldLevelMergeStrategy,
    MergeStrategyRegistry,
    TimestampLastWinsStrategy,
    UnionListMergeStrategy,
)


def test_field_level_merge_with_filters() -> None:
    # Include only
    strategy = FieldLevelMergeStrategy(include_fields={"name"})
    existing = {"id": 1, "name": "old", "status": "active"}
    incoming = {"id": 1, "name": "new", "status": "inactive"}
    result = strategy.merge(existing, incoming)
    assert result == {"id": 1, "name": "new", "status": "active"}

    # Exclude only
    strategy = FieldLevelMergeStrategy(exclude_fields={"id"})
    result = strategy.merge(existing, incoming)
    assert result == {"id": 1, "name": "new", "status": "inactive"}


def test_deep_merge_with_list_identity() -> None:
    strategy = DeepMergeStrategy(list_identity_key="id")
    existing = {"items": [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]}
    incoming = {"items": [{"id": 2, "val": "b-updated"}, {"id": 3, "val": "c"}]}
    result = strategy.merge(existing, incoming)
    assert len(result["items"]) == 3
    # Find item 2
    item2 = next(i for i in result["items"] if i["id"] == 2)
    assert item2["val"] == "b-updated"


def test_timestamp_merge_iso_parsing() -> None:
    strategy = TimestampLastWinsStrategy()
    existing = {"modified_at": "2023-01-01T10:00:00Z", "val": "old"}
    incoming = {"modified_at": "2023-01-01T11:00:00Z", "val": "new"}
    result = strategy.merge(existing, incoming)
    assert result["val"] == "new"

    # Reverse order
    incoming_old = {"modified_at": "2023-01-01T09:00:00Z", "val": "stale"}
    result = strategy.merge(existing, incoming_old)
    assert result["val"] == "old"


def test_union_list_identity_deduplication() -> None:
    strategy = UnionListMergeStrategy(identity_key="code")
    existing = [{"code": "A", "val": 1}, {"code": "B", "val": 2}]
    incoming = [{"code": "B", "val": 3}, {"code": "C", "val": 4}]
    result = strategy.merge(existing, incoming)
    assert len(result) == 3
    b_item = next(i for i in result if i["code"] == "B")
    assert b_item["val"] == 3  # Incoming wins


def test_stock_registry() -> None:
    registry = MergeStrategyRegistry.get_stock_registry()
    assert registry.get("deep") is DeepMergeStrategy
    assert registry.get("field") is FieldLevelMergeStrategy
    assert registry.get("timestamp") is TimestampLastWinsStrategy
    assert registry.get("union") is UnionListMergeStrategy


def test_deep_merge_with_callable_identity() -> None:
    # Identity is extracted by a custom function (e.g., composite key)
    def my_id_fn(item) -> str:
        return f"{item['type']}:{item['code']}"

    strategy = DeepMergeStrategy(list_identity_key=my_id_fn)
    existing = {"items": [{"type": "A", "code": 1, "val": "old"}]}
    incoming = {
        "items": [
            {"type": "A", "code": 1, "val": "new"},
            {"type": "B", "code": 2, "val": "other"},
        ]
    }
    result = strategy.merge(existing, incoming)
    assert len(result["items"]) == 2
    itemA = next(i for i in result["items"] if i["type"] == "A")
    assert itemA["val"] == "new"


def test_timestamp_merge_with_callable() -> None:
    # Extract timestamp from a nested or custom location
    def extract_ts(obj):
        return obj.get("meta", {}).get("updated")

    strategy = TimestampLastWinsStrategy(timestamp_field=extract_ts)
    existing = {"meta": {"updated": "2023-01-01T10:00:00Z"}, "val": "old"}
    incoming = {"meta": {"updated": "2023-01-01T11:00:00Z"}, "val": "new"}

    result = strategy.merge(existing, incoming)
    assert result["val"] == "new"


def test_union_list_with_callable_identity() -> None:
    strategy = UnionListMergeStrategy(identity_key=lambda x: x.upper())
    existing = ["a", "b"]
    incoming = ["B", "c"]
    result = strategy.merge(existing, incoming)
    # Result depends on how the map is built.
    # Current implementation: result_map maps identity -> item
    # existing: {"A": "a", "B": "b"}
    # incoming: "B" -> {"B": "B"}, "c" -> {"C": "c"}
    # result: ["a", "B", "c"] (case-insensitive deduplication, incoming "B" wins over "b")
    assert len(result) == 3
    assert "a" in result
    assert "B" in result
    assert "c" in result
