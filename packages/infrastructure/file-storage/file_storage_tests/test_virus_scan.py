"""Tests for IVirusScanner protocol and ScanResult."""

from __future__ import annotations

from cqrs_ddd_file_storage.virus_scan import IVirusScanner, ScanResult, ScanVerdict


class TestScanResult:
    def test_clean(self) -> None:
        result = ScanResult(verdict=ScanVerdict.CLEAN)
        assert result.is_clean is True
        assert result.threat_name is None

    def test_infected(self) -> None:
        result = ScanResult(verdict=ScanVerdict.INFECTED, threat_name="EICAR-Test")
        assert result.is_clean is False
        assert result.threat_name == "EICAR-Test"

    def test_error(self) -> None:
        result = ScanResult(verdict=ScanVerdict.ERROR, details={"reason": "timeout"})
        assert result.is_clean is False
        assert result.details["reason"] == "timeout"

    def test_immutable(self) -> None:
        import pytest

        result = ScanResult(verdict=ScanVerdict.CLEAN)
        with pytest.raises(AttributeError):
            result.verdict = ScanVerdict.INFECTED  # type: ignore[misc]


class TestIVirusScannerProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        class StubScanner:
            async def scan(self, data: bytes) -> ScanResult:
                return ScanResult(verdict=ScanVerdict.CLEAN)

        assert isinstance(StubScanner(), IVirusScanner)

    def test_non_conforming_is_not_instance(self) -> None:
        class NotScanner:
            pass

        assert not isinstance(NotScanner(), IVirusScanner)


class TestScanVerdict:
    def test_values(self) -> None:
        assert ScanVerdict.CLEAN.value == "clean"
        assert ScanVerdict.INFECTED.value == "infected"
        assert ScanVerdict.ERROR.value == "error"
