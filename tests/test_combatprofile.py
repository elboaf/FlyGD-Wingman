"""Shared, literal Unicode-16 expectations — not the host Unicode release."""

import hashlib
import json
from pathlib import Path

import pytest

from wingman import combatprofile
from wingman.combatprofile import (
    LIMITS,
    normalize_observed_name,
    observed_name_key,
    validate_observed_name,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_BYTES = (ROOT / "tests/fixtures/fleet-combat-v2.json").read_bytes()
FIXTURE = json.loads(FIXTURE_BYTES)
PROFILE_BYTES = (ROOT / "wingman/data/fleet-combat-v2-profile.json").read_bytes()
PROFILE = json.loads(PROFILE_BYTES)


def test_shared_fixture_and_installed_profile_are_byte_pinned():
    assert hashlib.sha256(FIXTURE_BYTES).hexdigest() == (
        "d9ccb14c6142bf66afd9f49e1c859b73834cbdbb88be002fbe1e052115725b7c"
    )
    assert hashlib.sha256(PROFILE_BYTES).hexdigest() == FIXTURE["profile_sha256"]
    assert (ROOT / "docs/fleet-combat-v2-profile.json").read_bytes() == PROFILE_BYTES


@pytest.mark.parametrize("vector", FIXTURE["names"], ids=lambda v: v["id"])
def test_shared_name_vector(vector):
    value = vector["input"]
    assert normalize_observed_name(value) == vector["normalized"]
    assert validate_observed_name(value) is vector["valid"]
    assert observed_name_key(value) == vector["key"]
    if vector["normalized"] is not None:
        canonical = vector["normalized"]
        assert normalize_observed_name(canonical) == canonical
        assert validate_observed_name(canonical) is True
        assert observed_name_key(canonical) == vector["normalized_key"]


def test_limits_are_complete_derived_and_immutable():
    expected = {**PROFILE["limits"], **FIXTURE["derived_limits"]}
    expected["effect_order"] = tuple(expected["effect_order"])
    assert dict(LIMITS) == expected
    with pytest.raises(TypeError):
        LIMITS["observed_name_scalars"] = 1
    with pytest.raises(TypeError):
        LIMITS["effect_order"][0] = "NEUT"
    assert normalize_observed_name("A" * 64) == "A" * 64


@pytest.mark.parametrize("value", [b"Pilot", object(), 1.5, {"Pilot"}])
def test_non_json_external_values_are_not_coerced(value):
    assert normalize_observed_name(value) is None
    assert validate_observed_name(value) is False
    assert observed_name_key(value) is None


@pytest.mark.parametrize(
    "value,forbidden",
    [
        (0, True),
        (0x200D, True),
        (0xD800, True),
        (0xE000, True),
        (0x378, True),
        (0x2028, True),
        (0x2029, True),
        (0x10FFFF, True),
        (ord("A"), False),
        (ord("<"), False),
        (ord(">"), False),
        (0x20, False),
        (0xA0, False),
        (0x301, False),
        (0x1FAE9, False),
        (-1, True),
        (0x110000, True),
        (True, True),
        (False, True),
        (65.0, True),
        ("A", True),
        (None, True),
        ([], True),
    ],
)
def test_public_scalar_predicate_is_frozen_category_only_and_fails_closed(
    value, forbidden
):
    assert combatprofile.is_forbidden_scalar(value) is forbidden


def test_public_scalar_predicate_rejects_integer_subclasses():
    class Point(int):
        pass

    assert combatprofile.is_forbidden_scalar(Point(65)) is True


def test_public_scalar_predicate_matches_every_frozen_range_edge():
    ranges = PROFILE["forbidden_ranges"]
    for start, end in ranges:
        for point in (start - 1, start, end, end + 1):
            expected = not 0 <= point <= 0x10FFFF or any(
                low <= point <= high for low, high in ranges
            )
            assert combatprofile.is_forbidden_scalar(point) is expected
