"""Tests for in-memory specification operators (geometry, jsonb, fts, string, standard)."""

from __future__ import annotations

import re
from typing import Any

import pytest

from cqrs_ddd_specifications.operators import SpecificationOperator
from cqrs_ddd_specifications.operators_memory.fts import FtsOperator, FtsPhraseOperator
from cqrs_ddd_specifications.operators_memory.jsonb import (
    JsonContainedByOperator,
    JsonContainsOperator,
    JsonHasAllOperator,
    JsonHasAnyOperator,
    JsonHasKeyOperator,
    JsonPathExistsOperator,
)
from cqrs_ddd_specifications.operators_memory.null import (
    IsNotNullOperator,
    IsNullOperator,
)
from cqrs_ddd_specifications.operators_memory.standard import (
    EqualOperator,
    GreaterEqualOperator,
    GreaterThanOperator,
    LessEqualOperator,
    LessThanOperator,
    NotEqualOperator,
)
from cqrs_ddd_specifications.operators_memory.string import (
    ContainsOperator,
    EndsWithOperator,
    IContainsOperator,
    IEndsWithOperator,
    ILikeOperator,
    IRegexOperator,
    IStartsWithOperator,
    LikeOperator,
    NotLikeOperator,
    RegexOperator,
    StartsWithOperator,
)

# Try to import geometry operators (shapely is optional)
try:
    from cqrs_ddd_specifications.operators_memory.geometry import (
        BboxIntersectsOperator,
        ContainsGeomOperator,
        CrossesOperator,
        DisjointOperator,
        DistanceLtOperator,
        DWithinOperator,
        GeomEqualsOperator,
        IntersectsOperator,
        OverlapsOperator,
        TouchesOperator,
        WithinOperator,
    )

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════
# Standard comparison operators tests
# ══════════════════════════════════════════════════════════════════════


class TestStandardOperators:
    """Test standard comparison operators (EQ, NE, GT, LT, GE, LE)."""

    def test_equal_operator_with_matching_values(self) -> None:
        """EQ returns True for matching values."""
        op = EqualOperator()
        assert op.evaluate(42, 42) is True
        assert op.evaluate("test", "test") is True
        assert op.evaluate(None, None) is True

    def test_equal_operator_with_different_values(self) -> None:
        """EQ returns False for different values."""
        op = EqualOperator()
        assert op.evaluate(42, 43) is False
        assert op.evaluate("test", "TEST") is False
        assert op.evaluate(None, 42) is False

    def test_not_equal_operator(self) -> None:
        """NE returns True for different values."""
        op = NotEqualOperator()
        assert op.evaluate(42, 43) is True
        assert op.evaluate("test", "TEST") is True
        assert op.evaluate(42, 42) is False

    def test_greater_than_operator(self) -> None:
        """GT compares numeric and string values."""
        op = GreaterThanOperator()
        assert op.evaluate(100, 50) is True
        assert op.evaluate(50, 100) is False
        assert op.evaluate(50, 50) is False
        assert op.evaluate(None, 50) is False

    def test_less_than_operator(self) -> None:
        """LT compares numeric and string values."""
        op = LessThanOperator()
        assert op.evaluate(50, 100) is True
        assert op.evaluate(100, 50) is False
        assert op.evaluate(50, 50) is False
        assert op.evaluate(None, 50) is False

    def test_greater_equal_operator(self) -> None:
        """GE compares numeric values with equality."""
        op = GreaterEqualOperator()
        assert op.evaluate(100, 50) is True
        assert op.evaluate(50, 50) is True
        assert op.evaluate(30, 50) is False
        assert op.evaluate(None, 50) is False

    def test_less_equal_operator(self) -> None:
        """LE compares numeric values with equality."""
        op = LessEqualOperator()
        assert op.evaluate(30, 50) is True
        assert op.evaluate(50, 50) is True
        assert op.evaluate(100, 50) is False
        assert op.evaluate(None, 50) is False

    def test_operator_names(self) -> None:
        """Verify operator names match specification operators."""
        assert EqualOperator().name == SpecificationOperator.EQ
        assert NotEqualOperator().name == SpecificationOperator.NE
        assert GreaterThanOperator().name == SpecificationOperator.GT
        assert LessThanOperator().name == SpecificationOperator.LT
        assert GreaterEqualOperator().name == SpecificationOperator.GE
        assert LessEqualOperator().name == SpecificationOperator.LE


# ══════════════════════════════════════════════════════════════════════
# String operators tests
# ══════════════════════════════════════════════════════════════════════


class TestStringOperators:
    """Test string operators (LIKE, CONTAINS, STARTSWITH, ENDSWITH, REGEX)."""

    def test_like_operator_with_wildcards(self) -> None:
        """LIKE matches SQL patterns with % and _ wildcards."""
        op = LikeOperator()
        assert op.evaluate("hello world", "hello%") is True
        assert op.evaluate("hello world", "%world") is True
        assert op.evaluate("hello world", "%llo wor%") is True
        assert op.evaluate("hello world", "hello_world") is True
        assert op.evaluate("hello world", "goodbye%") is False

    def test_like_operator_with_none(self) -> None:
        """LIKE returns False for None values."""
        op = LikeOperator()
        assert op.evaluate(None, "hello%") is False

    def test_not_like_operator(self) -> None:
        """NOT_LIKE inverts LIKE matching."""
        op = NotLikeOperator()
        assert op.evaluate("hello world", "goodbye%") is True
        assert op.evaluate("hello world", "hello%") is False
        assert op.evaluate(None, "hello%") is False

    def test_ilike_operator_case_insensitive(self) -> None:
        """ILIKE matches patterns case-insensitively."""
        op = ILikeOperator()
        assert op.evaluate("Hello World", "hello%") is True
        assert op.evaluate("HELLO WORLD", "%world") is True
        assert op.evaluate("hello world", "HELLO%") is True

    def test_contains_operator(self) -> None:
        """CONTAINS checks substring presence (case-sensitive)."""
        op = ContainsOperator()
        assert op.evaluate("hello world", "llo") is True
        assert op.evaluate("hello world", "LLO") is False
        assert op.evaluate(None, "hello") is False

    def test_icontains_operator_case_insensitive(self) -> None:
        """ICONTAINS checks substring presence (case-insensitive)."""
        op = IContainsOperator()
        assert op.evaluate("Hello World", "llo") is True
        assert op.evaluate("hello world", "LLO") is True
        assert op.evaluate("hello world", "WORLD") is True

    def test_startswith_operator(self) -> None:
        """STARTSWITH checks prefix (case-sensitive)."""
        op = StartsWithOperator()
        assert op.evaluate("hello world", "hello") is True
        assert op.evaluate("hello world", "Hello") is False
        assert op.evaluate(None, "hello") is False

    def test_istartswith_operator_case_insensitive(self) -> None:
        """ISTARTSWITH checks prefix (case-insensitive)."""
        op = IStartsWithOperator()
        assert op.evaluate("Hello World", "hello") is True
        assert op.evaluate("hello world", "HELLO") is True

    def test_endswith_operator(self) -> None:
        """ENDSWITH checks suffix (case-sensitive)."""
        op = EndsWithOperator()
        assert op.evaluate("hello world", "world") is True
        assert op.evaluate("hello world", "WORLD") is False
        assert op.evaluate(None, "world") is False

    def test_iendswith_operator_case_insensitive(self) -> None:
        """IENDSWITH checks suffix (case-insensitive)."""
        op = IEndsWithOperator()
        assert op.evaluate("Hello World", "world") is True
        assert op.evaluate("hello world", "WORLD") is True

    def test_regex_operator(self) -> None:
        """REGEX matches regular expressions (case-sensitive)."""
        op = RegexOperator()
        assert op.evaluate("hello123world", r"\d+") is True
        assert op.evaluate("hello world", r"^hello") is True
        assert op.evaluate("hello world", r"world$") is True
        assert op.evaluate("hello world", r"^goodbye") is False
        assert op.evaluate(None, r"hello") is False

    def test_iregex_operator_case_insensitive(self) -> None:
        """IREGEX matches regular expressions (case-insensitive)."""
        op = IRegexOperator()
        assert op.evaluate("Hello World", r"hello") is True
        assert op.evaluate("hello world", r"HELLO") is True
        assert op.evaluate("HELLO WORLD", r"hello world") is True


# ══════════════════════════════════════════════════════════════════════
# JSON/JSONB operators tests
# ══════════════════════════════════════════════════════════════════════


class TestJsonOperators:
    """Test JSONB operators (@>, <@, ?, ?|, ?&, path existence)."""

    def test_json_contains_operator_simple(self) -> None:
        """@> checks if field contains the value (simple case)."""
        op = JsonContainsOperator()
        field = {"name": "Alice", "age": 30}
        assert op.evaluate(field, {"name": "Alice"}) is True
        assert op.evaluate(field, {"age": 30}) is True
        assert op.evaluate(field, {"name": "Bob"}) is False

    def test_json_contains_operator_nested(self) -> None:
        """@> works with nested dicts."""
        op = JsonContainsOperator()
        field = {"user": {"name": "Alice", "email": "alice@example.com"}}
        assert op.evaluate(field, {"user": {"name": "Alice"}}) is True
        assert op.evaluate(field, {"user": {"email": "alice@example.com"}}) is True
        assert op.evaluate(field, {"user": {"name": "Bob"}}) is False

    def test_json_contains_operator_with_list(self) -> None:
        """@> works with lists."""
        op = JsonContainsOperator()
        field = {"tags": ["python", "testing", "cqrs"]}
        assert op.evaluate(field, {"tags": ["python"]}) is True
        assert op.evaluate(field, {"tags": ["python", "testing"]}) is True
        assert op.evaluate(field, {"tags": ["java"]}) is False

    def test_json_contains_operator_with_none(self) -> None:
        """@> returns False for None field."""
        op = JsonContainsOperator()
        assert op.evaluate(None, {"name": "Alice"}) is False

    def test_json_contained_by_operator(self) -> None:
        """<@ checks if field is contained by the value."""
        op = JsonContainedByOperator()
        field = {"name": "Alice"}
        container = {"name": "Alice", "age": 30, "city": "NYC"}
        assert op.evaluate(field, container) is True
        assert op.evaluate(container, field) is False
        assert op.evaluate(None, container) is False

    def test_json_has_key_operator(self) -> None:
        """? checks if dict has the given key."""
        op = JsonHasKeyOperator()
        field = {"name": "Alice", "age": 30}
        assert op.evaluate(field, "name") is True
        assert op.evaluate(field, "age") is True
        assert op.evaluate(field, "email") is False
        assert op.evaluate(None, "name") is False
        assert op.evaluate("not a dict", "key") is False

    def test_json_has_any_operator_single_key(self) -> None:
        """?| checks if dict has any of the given keys."""
        op = JsonHasAnyOperator()
        field = {"name": "Alice", "age": 30}
        assert op.evaluate(field, ["name"]) is True
        assert op.evaluate(field, ["email", "phone"]) is False

    def test_json_has_any_operator_multiple_keys(self) -> None:
        """?| returns True if at least one key exists."""
        op = JsonHasAnyOperator()
        field = {"name": "Alice", "age": 30}
        assert op.evaluate(field, ["email", "name"]) is True
        assert op.evaluate(field, ["email", "phone", "age"]) is True

    def test_json_has_any_operator_with_non_dict(self) -> None:
        """?| returns False for non-dict values."""
        op = JsonHasAnyOperator()
        assert op.evaluate("not a dict", ["key"]) is False
        assert op.evaluate(None, ["key"]) is False

    def test_json_has_all_operator(self) -> None:
        """?& checks if dict has all of the given keys."""
        op = JsonHasAllOperator()
        field = {"name": "Alice", "age": 30, "city": "NYC"}
        assert op.evaluate(field, ["name", "age"]) is True
        assert op.evaluate(field, ["name", "age", "city"]) is True
        assert op.evaluate(field, ["name", "email"]) is False

    def test_json_has_all_operator_with_non_dict(self) -> None:
        """?& returns False for non-dict values."""
        op = JsonHasAllOperator()
        assert op.evaluate("not a dict", ["key"]) is False
        assert op.evaluate(None, ["key"]) is False

    def test_json_path_exists_operator_simple(self) -> None:
        """JSON path existence checks simple dot paths."""
        op = JsonPathExistsOperator()
        field = {"user": {"name": "Alice", "email": "alice@example.com"}}
        assert op.evaluate(field, "user.name") is True
        assert op.evaluate(field, "user.email") is True
        assert op.evaluate(field, "user.phone") is False

    def test_json_path_exists_operator_with_dollar_sign(self) -> None:
        """JSON path existence strips leading $ and dots."""
        op = JsonPathExistsOperator()
        field = {"user": {"name": "Alice"}}
        assert op.evaluate(field, "$.user.name") is True
        assert op.evaluate(field, "$user.name") is True

    def test_json_path_exists_operator_with_none(self) -> None:
        """JSON path existence returns False for None field."""
        op = JsonPathExistsOperator()
        assert op.evaluate(None, "user.name") is False


# ══════════════════════════════════════════════════════════════════════
# Full-text search operators tests
# ══════════════════════════════════════════════════════════════════════


class TestFtsOperators:
    """Test full-text search operators (FTS, FTS_PHRASE)."""

    def test_fts_operator_all_tokens_present(self) -> None:
        """FTS returns True when all tokens are present."""
        op = FtsOperator()
        text = "The quick brown fox jumps over the lazy dog"
        assert op.evaluate(text, "quick fox") is True
        assert op.evaluate(text, "brown lazy dog") is True

    def test_fts_operator_case_insensitive(self) -> None:
        """FTS is case-insensitive."""
        op = FtsOperator()
        text = "The Quick Brown Fox"
        assert op.evaluate(text, "quick brown") is True
        assert op.evaluate(text, "QUICK BROWN") is True

    def test_fts_operator_missing_token(self) -> None:
        """FTS returns False if any token is missing."""
        op = FtsOperator()
        text = "The quick brown fox"
        assert op.evaluate(text, "quick cat") is False

    def test_fts_operator_with_none(self) -> None:
        """FTS returns False for None values."""
        op = FtsOperator()
        assert op.evaluate(None, "quick fox") is False

    def test_fts_phrase_operator_exact_match(self) -> None:
        """FTS_PHRASE matches exact phrase."""
        op = FtsPhraseOperator()
        text = "The quick brown fox jumps"
        assert op.evaluate(text, "quick brown fox") is True
        assert op.evaluate(text, "brown fox jumps") is True

    def test_fts_phrase_operator_case_insensitive(self) -> None:
        """FTS_PHRASE is case-insensitive."""
        op = FtsPhraseOperator()
        text = "The Quick Brown Fox"
        assert op.evaluate(text, "quick brown fox") is True
        assert op.evaluate(text, "QUICK BROWN") is True

    def test_fts_phrase_operator_no_match(self) -> None:
        """FTS_PHRASE returns False for non-matching phrase."""
        op = FtsPhraseOperator()
        text = "The quick brown fox"
        assert op.evaluate(text, "quick fox") is False  # Not contiguous

    def test_fts_phrase_operator_with_none(self) -> None:
        """FTS_PHRASE returns False for None values."""
        op = FtsPhraseOperator()
        assert op.evaluate(None, "quick fox") is False


# ══════════════════════════════════════════════════════════════════════
# Null operators tests
# ══════════════════════════════════════════════════════════════════════


class TestNullOperators:
    """Test null checking operators."""

    def test_is_null_operator(self) -> None:
        """IS_NULL checks for None values."""
        op = IsNullOperator()
        assert op.evaluate(None, True) is True
        assert op.evaluate("value", True) is False
        assert op.evaluate(0, True) is False
        assert op.evaluate("", True) is False

    def test_is_not_null_operator(self) -> None:
        """IS_NOT_NULL checks for non-None values."""
        op = IsNotNullOperator()
        assert op.evaluate("value", True) is True
        assert op.evaluate(0, True) is True
        assert op.evaluate("", True) is True
        assert op.evaluate(None, True) is False


# ══════════════════════════════════════════════════════════════════════
# Geometry operators tests (requires shapely)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="Shapely not installed")
class TestGeometryOperators:
    """Test geometry operators (requires shapely)."""

    @pytest.fixture
    def point_geojson(self) -> dict[str, Any]:
        """GeoJSON point at (0, 0)."""
        return {"type": "Point", "coordinates": [0, 0]}

    @pytest.fixture
    def polygon_geojson(self) -> dict[str, Any]:
        """GeoJSON polygon surrounding origin."""
        return {
            "type": "Polygon",
            "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
        }

    @pytest.fixture
    def line_geojson(self) -> dict[str, Any]:
        """GeoJSON line through origin."""
        return {"type": "LineString", "coordinates": [[-1, 0], [1, 0]]}

    def test_intersects_operator(
        self, point_geojson: dict[str, Any], polygon_geojson: dict[str, Any]
    ) -> None:
        """INTERSECTS checks if geometries intersect."""
        op = IntersectsOperator()
        assert op.evaluate(point_geojson, polygon_geojson) is True
        # Non-intersecting point
        outside_point = {"type": "Point", "coordinates": [10, 10]}
        assert op.evaluate(outside_point, polygon_geojson) is False

    def test_intersects_operator_with_none(self) -> None:
        """INTERSECTS returns False for None values."""
        op = IntersectsOperator()
        polygon = {"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
        assert op.evaluate(None, polygon) is False

    def test_within_operator(
        self, point_geojson: dict[str, Any], polygon_geojson: dict[str, Any]
    ) -> None:
        """WITHIN checks if field geometry is within query geometry."""
        op = WithinOperator()
        assert op.evaluate(point_geojson, polygon_geojson) is True
        # Point outside
        outside_point = {"type": "Point", "coordinates": [10, 10]}
        assert op.evaluate(outside_point, polygon_geojson) is False

    def test_within_operator_with_none(self, polygon_geojson: dict[str, Any]) -> None:
        """WITHIN returns False for None values."""
        op = WithinOperator()
        assert op.evaluate(None, polygon_geojson) is False

    def test_contains_geom_operator(
        self, point_geojson: dict[str, Any], polygon_geojson: dict[str, Any]
    ) -> None:
        """CONTAINS_GEOM checks if field geometry contains query geometry."""
        op = ContainsGeomOperator()
        assert op.evaluate(polygon_geojson, point_geojson) is True
        assert op.evaluate(point_geojson, polygon_geojson) is False

    def test_touches_operator(self) -> None:
        """TOUCHES checks if geometries touch."""
        op = TouchesOperator()
        # Point on polygon edge
        edge_point = {"type": "Point", "coordinates": [1, 0]}
        polygon = {"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
        assert op.evaluate(edge_point, polygon) is True

    def test_crosses_operator(self) -> None:
        """CROSSES checks if geometries cross."""
        op = CrossesOperator()
        line = {"type": "LineString", "coordinates": [[-2, 0], [2, 0]]}
        polygon = {"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
        assert op.evaluate(line, polygon) is True

    def test_overlaps_operator(self) -> None:
        """OVERLAPS checks if geometries overlap."""
        op = OverlapsOperator()
        poly1 = {"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
        poly2 = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
        assert op.evaluate(poly1, poly2) is True

    def test_disjoint_operator(self) -> None:
        """DISJOINT checks if geometries are disjoint (don't touch)."""
        op = DisjointOperator()
        point1 = {"type": "Point", "coordinates": [0, 0]}
        point2 = {"type": "Point", "coordinates": [10, 10]}
        assert op.evaluate(point1, point2) is True
        # Same point is not disjoint
        assert op.evaluate(point1, point1) is False

    def test_geom_equals_operator(self, point_geojson: dict[str, Any]) -> None:
        """GEOM_EQUALS checks geometric equality."""
        op = GeomEqualsOperator()
        same_point = {"type": "Point", "coordinates": [0, 0]}
        different_point = {"type": "Point", "coordinates": [1, 1]}
        assert op.evaluate(point_geojson, same_point) is True
        assert op.evaluate(point_geojson, different_point) is False

    def test_dwithin_operator(self) -> None:
        """DWITHIN checks if distance is within threshold."""
        op = DWithinOperator()
        point1 = {"type": "Point", "coordinates": [0, 0]}
        point2 = {"type": "Point", "coordinates": [3, 4]}  # Distance = 5
        assert op.evaluate(point1, (point2, 6)) is True  # Within 6 units
        assert op.evaluate(point1, (point2, 4)) is False  # Not within 4 units

    def test_distance_lt_operator(self) -> None:
        """DISTANCE_LT checks if distance is strictly less than threshold."""
        op = DistanceLtOperator()
        point1 = {"type": "Point", "coordinates": [0, 0]}
        point2 = {"type": "Point", "coordinates": [3, 4]}  # Distance = 5
        assert op.evaluate(point1, (point2, 6)) is True  # Less than 6
        assert op.evaluate(point1, (point2, 5)) is False  # Not less than 5 (equal)
        assert op.evaluate(point1, (point2, 4)) is False  # Not less than 4

    def test_bbox_intersects_operator(self) -> None:
        """BBOX_INTERSECTS uses bounding box for fast intersection check."""
        op = BboxIntersectsOperator()
        point = {"type": "Point", "coordinates": [0.5, 0.5]}
        bbox = (-1, -1, 1, 1)  # (minx, miny, maxx, maxy)
        assert op.evaluate(point, bbox) is True

        outside_point = {"type": "Point", "coordinates": [10, 10]}
        assert op.evaluate(outside_point, bbox) is False

    def test_geometry_operator_with_shapely_object(self, point_geojson: dict[str, Any]) -> None:
        """Geometry operators accept Shapely geometry objects directly."""
        from shapely.geometry import Point

        op = IntersectsOperator()
        shapely_point = Point(0, 0)
        assert op.evaluate(shapely_point, point_geojson) is True

    def test_geometry_operator_invalid_value(self) -> None:
        """Geometry operators raise error for invalid geometry values."""
        op = IntersectsOperator()
        with pytest.raises(ValueError, match="Cannot convert"):
            op.evaluate("invalid", {"type": "Point", "coordinates": [0, 0]})
