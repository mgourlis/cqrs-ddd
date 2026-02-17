"""Event Upcasting — schema evolution for stored domain events."""

from .registry import EventUpcaster, UpcasterChain, UpcasterRegistry

__all__ = [
    "EventUpcaster",
    "UpcasterChain",
    "UpcasterRegistry",
]
