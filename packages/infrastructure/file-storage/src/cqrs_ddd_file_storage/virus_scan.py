"""Virus-scanning protocol and result type for pass-through uploads."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class ScanVerdict(Enum):
    """Result of a virus scan."""

    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Immutable value object returned by :class:`IVirusScanner`.

    Attributes:
        verdict: Overall scan verdict.
        threat_name: Name of detected threat (``None`` when clean).
        details: Free-form detail map from the scanner engine.
    """

    verdict: ScanVerdict
    threat_name: str | None = None
    details: dict[str, str] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        """Return ``True`` if the scanned payload is clean."""
        return self.verdict is ScanVerdict.CLEAN


@runtime_checkable
class IVirusScanner(Protocol):
    """Protocol for virus scanning during pass-through uploads.

    Implementations may wrap ClamAV, cloud-native scanning APIs,
    or a no-op stub for development.
    """

    async def scan(self, data: bytes | AsyncIterator[bytes]) -> ScanResult:
        """Scan *data* for malware and return a :class:`ScanResult`."""
        ...
