"""Unit tests for geometry operators."""

import pytest

from cqrs_ddd_persistence_mongo.operators.geometry import compile_geometry
from cqrs_ddd_specifications.operators import SpecificationOperator


# Test WITHIN operator
def test_within_operator():
    field = "location"
    op = SpecificationOperator.WITHIN.value
    val = {"$geometry": {"type": "Polygon", "coordinates": [[[]]]}}
    expected = {
        "location": {
            "$geoWithin": {"$geometry": {"type": "Polygon", "coordinates": [[[]]]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test INTERSECTS operator
def test_intersects_operator():
    field = "location"
    op = SpecificationOperator.INTERSECTS.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test DISTANCE_LT with full geometry object
def test_distance_lt_with_coordinates():
    field = "location"
    op = SpecificationOperator.DISTANCE_LT.value
    val = {"coordinates": [1, 1], "maxDistance": 1000, "type": "Point"}
    expected = {
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [1, 1]},
                "$maxDistance": 1000,
            }
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test DISTANCE_LT without type defaults to Point
def test_distance_lt_defaults_to_point():
    field = "location"
    op = SpecificationOperator.DISTANCE_LT.value
    val = {"coordinates": [1, 1], "maxDistance": 1000}
    expected = {
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [1, 1]},
                "$maxDistance": 1000,
            }
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test DISTANCE_LT with simple value
def test_distance_lt_simple_value():
    field = "location"
    op = SpecificationOperator.DISTANCE_LT.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {"$near": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}}
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test DWITHIN operator
def test_dwithin_operator():
    field = "location"
    op = SpecificationOperator.DWITHIN.value
    val = [[1, 1], 0.1]
    expected = {"location": {"$geoWithin": {"$centerSphere": [[1, 1], 0.1]}}}
    result = compile_geometry(field, op, val)
    assert result == expected


# Test TOUCHES maps to geoIntersects
def test_touches_operator():
    field = "location"
    op = SpecificationOperator.TOUCHES.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test CROSSES maps to geoIntersects
def test_crosses_operator():
    field = "location"
    op = SpecificationOperator.CROSSES.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test OVERLAPS maps to geoIntersects
def test_overlaps_operator():
    field = "location"
    op = SpecificationOperator.OVERLAPS.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test DISJOINT maps to geoIntersects
def test_disjoint_operator():
    field = "location"
    op = SpecificationOperator.DISJOINT.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test GEOM_EQUALS maps to geoIntersects
def test_geom_equals_operator():
    field = "location"
    op = SpecificationOperator.GEOM_EQUALS.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test BBOX_INTERSECTS maps to geoIntersects
def test_bbox_intersects_operator():
    field = "location"
    op = SpecificationOperator.BBOX_INTERSECTS.value
    val = {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    expected = {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test CONTAINS_GEOM with valid dict
def test_contains_geom_valid_dict():
    field = "location"
    op = SpecificationOperator.CONTAINS_GEOM.value
    val = {"type": "Point", "coordinates": [1, 1]}
    expected = {
        "$expr": {"$geoWithin": [{"type": "Point", "coordinates": [1, 1]}, "$location"]}
    }
    result = compile_geometry(field, op, val)
    assert result == expected


# Test non-geometry operator returns None
def test_non_geometry_operator():
    field = "name"
    op = SpecificationOperator.EQ.value
    val = "test"
    result = compile_geometry(field, op, val)
    assert result is None


# Test invalid operator string returns None
def test_invalid_operator_string():
    field = "location"
    op = "invalid_op"
    val = {"coordinates": [1, 1]}
    result = compile_geometry(field, op, val)
    assert result is None


# Test CONTAINS_GEOM with non-dict returns None
def test_contains_geom_non_dict():
    field = "location"
    op = SpecificationOperator.CONTAINS_GEOM.value
    val = "not_a_dict"
    result = compile_geometry(field, op, val)
    assert result is None


@pytest.mark.parametrize(
    ("field", "op", "val"),
    [
        # Test DWITHIN with Polygon coordinates
        pytest.param(
            "location",
            SpecificationOperator.DWITHIN.value,
            [[[1, 1], [2, 2], [3, 3]], 0.1],
            id="dwithin_polygon",
        ),
        # Test WITHIN with Polygon
        pytest.param(
            "location",
            SpecificationOperator.WITHIN.value,
            {
                "$geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                }
            },
            id="within_polygon",
        ),
        # Test INTERSECTS with LineString
        pytest.param(
            "location",
            SpecificationOperator.INTERSECTS.value,
            {"$geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
            id="intersects_linestring",
        ),
        # Test DISTANCE_LT with MultiPoint
        pytest.param(
            "location",
            SpecificationOperator.DISTANCE_LT.value,
            {"coordinates": [[1, 1], [2, 2]], "maxDistance": 500, "type": "MultiPoint"},
            id="distance_lt_multipoint",
        ),
    ],
)
def test_geometry_various_types(field, op, val):
    """Test geometry operators with various geometry types."""
    result = compile_geometry(field, op, val)
    assert result is not None
    assert field in result


def test_geometry_with_mongodb_operator_symbols():
    """Test geometry with MongoDB-style operator values."""
    # Test that it works with string values matching SpecificationOperator enum
    result = compile_geometry(
        "location", "within", {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
    )
    assert result == {
        "location": {
            "$geoWithin": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }

    result = compile_geometry(
        "location",
        "intersects",
        {"$geometry": {"type": "Point", "coordinates": [1, 1]}},
    )
    assert result == {
        "location": {
            "$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [1, 1]}}
        }
    }

    result = compile_geometry(
        "location", "distance_lt", {"coordinates": [1, 1], "maxDistance": 1000}
    )
    assert result == {
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [1, 1]},
                "$maxDistance": 1000,
            }
        }
    }


def test_distance_lt_edge_cases():
    """Test DISTANCE_LT operator edge cases."""
    # Missing coordinates - falls back to simple near
    result = compile_geometry(
        "location", SpecificationOperator.DISTANCE_LT.value, {"maxDistance": 1000}
    )
    assert result == {"location": {"$near": {"maxDistance": 1000}}}

    # Missing maxDistance - falls back to simple near
    result = compile_geometry(
        "location", SpecificationOperator.DISTANCE_LT.value, {"coordinates": [1, 1]}
    )
    assert result == {"location": {"$near": {"coordinates": [1, 1]}}}


def test_non_standard_operators_return_none():
    """Test that standard comparison operators return None."""
    for op in ["=", "!=", ">", ">=", "<", "<=", "like", "in", "not_in"]:
        result = compile_geometry("location", op, {"coordinates": [1, 1]})
        assert result is None
