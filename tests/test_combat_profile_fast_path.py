"""Frozen NFC's identity path avoids Python composition work, not validation."""

import pytest

from wingman import combatprofile as profile


def test_large_unchanged_names_need_no_decomposition(monkeypatch):
    calls = []
    original = profile._decompose

    def count(cp, output):
        calls.append(cp)
        return original(cp, output)

    monkeypatch.setattr(profile, "_decompose", count)
    for index in range(128):
        # Distinct legal maximum-sized labels prevent a memoization-only win.
        name = chr(0x20000 + index) + "😀" * 63
        assert profile.normalize_observed_name(name) == name
    assert calls == []


@pytest.mark.parametrize(
    "text",
    ["e\u0301", "\u1100\u1161\u11a8", "\uac00\u11a8", "\u09c7\u09be", "A\u0315\u0300"],
)
def test_composition_sensitive_sequences_keep_the_full_frozen_algorithm(
    text, monkeypatch
):
    expected = profile._nfc(map(ord, text))
    # Disable only the optimization: the original frozen algorithm is the oracle.
    monkeypatch.setattr(profile, "_nfc_work", set(map(ord, text)))
    assert profile._nfc(map(ord, text)) == expected
