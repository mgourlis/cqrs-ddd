"""Decorators for event-sourcing and other cross-cutting configuration."""

from .event_sourcing import non_event_sourced

__all__ = ["non_event_sourced"]
