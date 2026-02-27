"""Tests for OAuth2 PKCE utilities."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity.oauth2.pkce import (
    PKCEData,
    create_pkce_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    verify_pkce_challenge,
)


class TestGeneratePkceVerifier:
    def test_valid_length(self) -> None:
        v = generate_pkce_verifier(64)
        assert len(v) == 64

    def test_length_42_raises(self) -> None:
        with pytest.raises(ValueError, match="43 and 128"):
            generate_pkce_verifier(42)

    def test_length_129_raises(self) -> None:
        with pytest.raises(ValueError, match="43 and 128"):
            generate_pkce_verifier(129)


class TestGeneratePkceChallenge:
    def test_deterministic(self) -> None:
        v = "a" * 43
        c1 = generate_pkce_challenge(v)
        c2 = generate_pkce_challenge(v)
        assert c1 == c2

    def test_different_verifier_different_challenge(self) -> None:
        c1 = generate_pkce_challenge("a" * 43)
        c2 = generate_pkce_challenge("b" * 43)
        assert c1 != c2


class TestCreatePkceData:
    def test_returns_pkce_data(self) -> None:
        pkce = create_pkce_data(64)
        assert isinstance(pkce, PKCEData)
        assert pkce.code_challenge_method == "S256"
        assert len(pkce.code_verifier) == 64
        assert pkce.code_challenge == generate_pkce_challenge(pkce.code_verifier)


class TestVerifyPkceChallenge:
    def test_true_when_match(self) -> None:
        pkce = create_pkce_data(64)
        assert verify_pkce_challenge(pkce.code_verifier, pkce.code_challenge) is True

    def test_false_when_wrong_verifier(self) -> None:
        pkce = create_pkce_data(64)
        wrong_verifier = create_pkce_data(64).code_verifier
        assert verify_pkce_challenge(wrong_verifier, pkce.code_challenge) is False

    def test_false_when_empty_verifier(self) -> None:
        assert verify_pkce_challenge("", "challenge") is False

    def test_false_when_empty_challenge(self) -> None:
        v = generate_pkce_verifier(64)
        assert verify_pkce_challenge(v, "") is False

    def test_false_when_verifier_too_short(self) -> None:
        v = "a" * 42
        c = generate_pkce_challenge(v)
        assert verify_pkce_challenge(v, c) is False

    def test_false_when_verifier_too_long(self) -> None:
        v = "a" * 129
        c = generate_pkce_challenge(v)
        assert verify_pkce_challenge(v, c) is False
