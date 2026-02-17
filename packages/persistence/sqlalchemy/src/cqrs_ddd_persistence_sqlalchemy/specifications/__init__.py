"""
Specification-to-SQLAlchemy compilation.

Public API:
    - ``build_sqla_filter(model, data)`` — compile a spec dict to a
      ``ColumnElement[bool]``
    - ``apply_query_options(stmt, model, options)`` — apply
      ``QueryOptions`` to a ``Select`` statement
    - ``DEFAULT_SQLA_REGISTRY`` — the default operator registry
    - ``SQLAlchemyOperator`` / ``SQLAlchemyOperatorRegistry`` — extension
      points for custom operators
    - ``SQLAlchemyResolutionContext`` / ``SQLAlchemyHookResult`` —
      SQLAlchemy-specific hook primitives
    - ``extract_tables_from_statement`` — utility for introspecting
      compiled statements
"""

from .compiler import apply_query_options, build_sqla_filter
from .hooks import SQLAlchemyHookResult, SQLAlchemyResolutionContext
from .operators import DEFAULT_SQLA_REGISTRY
from .strategy import SQLAlchemyOperator, SQLAlchemyOperatorRegistry
from .utils import extract_tables_from_statement

__all__ = [
    "build_sqla_filter",
    "apply_query_options",
    "DEFAULT_SQLA_REGISTRY",
    "SQLAlchemyOperator",
    "SQLAlchemyOperatorRegistry",
    "SQLAlchemyResolutionContext",
    "SQLAlchemyHookResult",
    "extract_tables_from_statement",
]
