"""Pinned fitting contracts: scopes, remote limits, local refusal
boundaries, and the accepted-flag inventory.

These tests exist to catch drift in two directions: a hand-typed constant
that no longer matches CCP's compatibility-dated schema, and a rack/flag
classification that has fallen out of sync with the flags ESI can
actually send. The fixture-consistency tests tie the sanitized sample
payloads under tests/fixtures/evefittings/ back to this same inventory,
so a fixture using a flag outside the pinned enum fails here rather than
silently exercising a code path the schema doesn't support.
"""

import json
import pathlib

from wingman.evefittings import contracts

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "evefittings"


def test_create_contract_is_pinned_to_current_esi_limits():
    assert contracts.READ_SCOPE == "esi-fittings.read_fittings.v1"
    assert contracts.WRITE_SCOPE == "esi-fittings.write_fittings.v1"
    assert contracts.MAX_NAME_CHARS == 50
    assert contracts.MAX_DESCRIPTION_CHARS == 500
    assert contracts.MAX_CREATE_ITEMS == 512
    assert contracts.READ_CACHE_SECONDS == 300
    assert contracts.MAX_COPY_WRITES == 20


def test_local_bounds_are_explicit_refusal_boundaries():
    assert contracts.MAX_REMOTE_FITTINGS == 500
    assert contracts.MAX_LIBRARY_ENTRIES == 10_000
    assert contracts.MAX_COLLECTIONS == 200
    assert contracts.MAX_ALIASES_PER_ENTRY == 100
    assert contracts.PAGE_SIZE == 100
    assert contracts.MAX_OPERATION_RECORDS == 200
    assert contracts.MAX_STATE_BYTES == 64 * 1024 * 1024


def test_paths_are_unversioned_templates_with_a_character_id_placeholder():
    """Resolved through X-Compatibility-Date, not a /vN/ path segment --
    and the placeholder must never be a value validate_path() would
    accept, so a caller cannot forget to fill it in without also failing
    path validation."""
    assert contracts.GET_PATH == "/characters/{character_id}/fittings"
    assert contracts.POST_PATH == "/characters/{character_id}/fittings"


def test_every_accepted_flag_is_classified_into_a_rack_or_explicitly_non_rack():
    """Guards the same invariant contracts.py asserts at import time, but
    as a named test rather than only an import-time crash: a future flag
    added to ACCEPTED_FLAGS without updating the rack groups or
    NON_RACK_FLAGS must fail here with a clear assertion, not just abort
    the whole test session on collection."""
    classified = set(contracts.RACK_BY_FLAG) | contracts.NON_RACK_FLAGS
    assert classified == contracts.ACCEPTED_FLAGS


def test_rack_group_sizes_match_esis_numbered_slot_spans():
    counts = {}
    for rack in contracts.RACK_BY_FLAG.values():
        counts[rack] = counts.get(rack, 0) + 1
    assert counts == {
        contracts.HIGH: 8,
        contracts.MEDIUM: 8,
        contracts.LOW: 8,
        contracts.RIG: 3,
        contracts.SUBSYSTEM: 4,
        contracts.SERVICE: 8,
    }


def test_non_rack_flags_are_bay_locations_and_invalid():
    assert frozenset({"Cargo", "DroneBay", "FighterBay", "Invalid"}) == (
        contracts.NON_RACK_FLAGS
    )


def test_numbered_slots_normalize_to_the_documented_rack():
    """Ports the design doc's own list of rack mappings as an assertion,
    not only a comment: HiSlot0...7 -> high, MedSlot0...7 -> medium,
    LoSlot0...7 -> low."""
    for i in range(8):
        assert contracts.RACK_BY_FLAG[f"HiSlot{i}"] == contracts.HIGH
        assert contracts.RACK_BY_FLAG[f"MedSlot{i}"] == contracts.MEDIUM
        assert contracts.RACK_BY_FLAG[f"LoSlot{i}"] == contracts.LOW


def test_invalid_is_accepted_but_not_rack_mapped():
    """The schema-defined Invalid flag is retained as distinct canonical
    content -- see the design doc -- so it must be an accepted flag, but
    it is never a numbered slot and must not appear in RACK_BY_FLAG."""
    assert "Invalid" in contracts.ACCEPTED_FLAGS
    assert "Invalid" not in contracts.RACK_BY_FLAG
    assert "Invalid" in contracts.NON_RACK_FLAGS


def _flags_in(fixture_name: str) -> set[str]:
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    return {item["flag"] for fitting in payload for item in fitting["items"]}


def test_get_small_fixture_only_uses_accepted_flags():
    assert _flags_in("get-small.json") <= contracts.ACCEPTED_FLAGS


def test_get_equivalent_slots_fixture_only_uses_accepted_flags():
    assert _flags_in("get-equivalent-slots.json") <= contracts.ACCEPTED_FLAGS


def test_get_invalid_flag_fixture_contains_the_invalid_flag():
    flags = _flags_in("get-invalid-flag.json")
    assert flags <= contracts.ACCEPTED_FLAGS
    assert "Invalid" in flags


def test_fixtures_carry_no_character_identity_or_token():
    """Sanitized fixtures must never contain a character ID, a token, or
    anything that looks like a live credential -- these files are
    committed to the repository."""
    for name in (
        "get-small.json",
        "get-equivalent-slots.json",
        "get-invalid-flag.json",
    ):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert "character_id" not in text
        assert "token" not in text.lower()
