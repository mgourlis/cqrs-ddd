"""FilterParser — query params -> BaseSpecification + QueryOptions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from cqrs_ddd_specifications.ast import SpecificationFactory

from .syntax import ColonSeparatedSyntax, FilterSyntax

if TYPE_CHECKING:
    from cqrs_ddd_specifications.evaluator import MemoryOperatorRegistry

    from .whitelist import FieldWhitelist


class QueryOptions(NamedTuple):
    """Parsed pagination, sort, and projection."""

    offset: int | None
    limit: int | None
    sort: list[tuple[str, str]]
    fields: list[str] | None
    cursor: str | None


class FilterParser:
    """Parse API params into specification tree + QueryOptions."""

    def __init__(
        self,
        registry: MemoryOperatorRegistry,
        default_syntax: FilterSyntax | None = None,
    ) -> None:
        """
        Initialize FilterParser with required registry.

        Args:
            registry: MemoryOperatorRegistry for specification evaluation.
            default_syntax: Optional filter syntax parser (defaults to
                ColonSeparatedSyntax).
        """
        if registry is None:
            raise ValueError(
                "registry parameter is required. "
                "Use build_default_registry() from "
                "cqrs_ddd_specifications.operators_memory to create one."
            )
        self._registry = registry
        self._syntax = default_syntax or ColonSeparatedSyntax()

    def parse(
        self,
        query_params: dict[str, Any],
        whitelist: FieldWhitelist | None = None,
        filter_key: str = "filter",
        sort_key: str = "sort",
        limit_key: str = "limit",
        offset_key: str = "offset",
        fields_key: str = "fields",
    ) -> tuple[Any, QueryOptions]:
        """Return (specification, query_options)."""
        raw_filter = query_params.get(filter_key)
        spec_dict = self._syntax.parse_filter(raw_filter) if raw_filter else {}
        if whitelist and spec_dict:
            self._validate_spec_dict(spec_dict, whitelist)
        allowed = list(whitelist.filterable_fields.keys()) if whitelist else None
        spec: Any = (
            SpecificationFactory.from_dict(
                spec_dict, allowed_fields=allowed, registry=self._registry
            )
            if spec_dict
            else None
        )
        sort_raw = query_params.get(sort_key)
        sort_list = self._parse_sort(sort_raw, whitelist)
        limit = self._int_param(query_params.get(limit_key))
        offset = self._int_param(query_params.get(offset_key))
        fields_raw = query_params.get(fields_key)
        fields = self._parse_fields(fields_raw, whitelist)
        cursor = query_params.get("cursor")
        options = QueryOptions(
            offset=offset,
            limit=limit,
            sort=sort_list,
            fields=fields,
            cursor=cursor,
        )
        return spec, options

    def _int_param(self, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _validate_spec_dict(
        self, data: dict[str, Any], whitelist: FieldWhitelist
    ) -> None:
        if "attr" in data:
            whitelist.allow_filter(data["attr"], str(data.get("op", "")))
            return
        for c in data.get("conditions", []):
            self._validate_spec_dict(c, whitelist)

    def _parse_sort(
        self, raw: Any, whitelist: FieldWhitelist | None
    ) -> list[tuple[str, str]]:
        if not raw:
            return []
        if isinstance(raw, list):
            return self._parse_sort_list(raw, whitelist)
        if isinstance(raw, str):
            return self._parse_sort_string(raw)
        return []

    def _parse_sort_list(
        self, raw: list[Any], whitelist: FieldWhitelist | None
    ) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for item in raw:
            parsed = self._parse_sort_item(item)
            if parsed is None:
                continue
            field, direction = parsed
            if whitelist:
                whitelist.allow_sort(field)
            out.append((field, direction))
        return out

    def _parse_sort_item(self, item: Any) -> tuple[str, str] | None:
        if isinstance(item, dict):
            return item.get("field", ""), item.get("dir", "asc")
        if isinstance(item, str):
            if item.startswith("-"):
                return item[1:], "desc"
            return item, "asc"
        return None

    def _parse_sort_string(self, raw: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for part in raw.split(","):
            stripped = part.strip()
            if stripped.startswith("-"):
                out.append((stripped[1:], "desc"))
            else:
                out.append((stripped, "asc"))
        return out

    def _parse_fields(
        self, raw: Any, whitelist: FieldWhitelist | None
    ) -> list[str] | None:
        if not raw:
            return None
        if isinstance(raw, str):
            fields = [f.strip() for f in raw.split(",") if f.strip()]
        elif isinstance(raw, list):
            fields = list(raw)
        else:
            return None
        if whitelist:
            for f in fields:
                whitelist.allow_project(f)
        return fields
