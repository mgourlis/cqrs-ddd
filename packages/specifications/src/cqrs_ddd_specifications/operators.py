from enum import Enum


class SpecificationOperator(str, Enum):
    """Supported operators for specifications."""

    # Standard comparison
    EQ = "="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="
    IN = "in"
    NOT_IN = "not_in"
    ALL = "all"
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"

    # String operations
    LIKE = "like"
    NOT_LIKE = "not_like"
    ILIKE = "ilike"
    CONTAINS = "contains"
    ICONTAINS = "icontains"
    STARTSWITH = "startswith"
    ISTARTSWITH = "istartswith"
    ENDSWITH = "endswith"
    IENDSWITH = "iendswith"
    REGEX = "regex"
    IREGEX = "iregex"

    # Null/Empty checks
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"

    # JSON operations
    JSON_CONTAINS = "json_contains"
    JSON_CONTAINED_BY = "json_contained_by"
    JSON_HAS_KEY = "json_has_key"
    JSON_HAS_ANY = "json_has_any"
    JSON_HAS_ALL = "json_has_all"
    JSON_PATH_EXISTS = "json_path_exists"

    # Geometry operations
    INTERSECTS = "intersects"
    WITHIN = "within"
    CONTAINS_GEOM = "contains_geom"
    TOUCHES = "touches"
    CROSSES = "crosses"
    OVERLAPS = "overlaps"
    DISJOINT = "disjoint"
    GEOM_EQUALS = "geom_equals"
    DISTANCE_LT = "distance_lt"
    DWITHIN = "dwithin"
    BBOX_INTERSECTS = "bbox_intersects"

    # Full-text search
    FTS = "fts"
    FTS_PHRASE = "fts_phrase"

    # Logical operators
    AND = "and"
    OR = "or"
    NOT = "not"
