"""Event handling examples for event-sourced aggregates.

This package demonstrates various aspects of event handler formalization:

- basic_usage.py: Simple introduction to EventSourcedAggregateMixin
- validation_modes.py: Demonstrates lenient, strict, and disabled validation
- decorators.py: @aggregate_event_handler and @aggregate_event_handler_validator
- error_handling.py: Demonstrates graceful error handling for missing handlers
- migration_guide.py: Step-by-step guide for migrating existing aggregates
"""

# Import examples directly (not as a subpackage)
from . import (
    basic_usage,
    decorators,
    error_handling,
    migration_guide,
    validation_modes,
)

__all__ = [
    "basic_usage",
    "decorators",
    "error_handling",
    "migration_guide",
    "validation_modes",
]
