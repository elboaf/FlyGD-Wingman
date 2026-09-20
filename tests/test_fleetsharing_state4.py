"""Closed state4 codec and the pure receipt-derived cancellation prerequisite."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.fleetsharing_state4_helpers import (
    CANCEL,
    CONSENT,
    DATE,
    PENDING,
    RECEIPT,
    REQUEST,
    TOKEN,
    active,
    put,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def read_active(path, *, pending=False):
    raw = active()
    if pending:
        raw["automatic"]["pending"] = deepcopy(PENDING)
        raw["automatic"]["observed_consent"] = {
            **CONSENT,
            "generation": 8,
            "revision": 12,
        }
    put(path, raw)
    loaded = s.load(path)
    assert loaded.identity is not None
    return loaded


def test_v4_roundtrip_expired_journals_explicit_wire_fields_and_canonical_bytes(
    tmp_path,
):
    path = tmp_path / "state.json"
    raw = active()
    put(path, raw)
    loaded = s.load(path)
    assert loaded.identity is not None
    s.save(path, loaded)
    assert json.loads(path.read_bytes()) == raw
    assert b"\n" not in path.read_bytes()
    assert s.load(path) == loaded
    before = path.read_bytes()
    s.save(path, s.load(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "opaque"),
        ("last_revision", True),
        ("last_revision", 0.0),
        ("session_expires_at", "bad"),
        ("acknowledged_capabilities", ["unknown"]),
        ("device_id", "bad"),
        ("identity", None),
        ("relay_origin", None),
        (
            "pending_source_commands",
            [{"operation": "stop", "source_id": REQUEST, "expected_generation": 0}],
        ),
    ],
)
def test_invalid_active_v4_quarantines_never_salvages(tmp_path, field, value):
    path = tmp_path / "state.json"
    raw = active()
    raw[field] = value
    before = put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "where,key,value",
    [
        ("pending_recovery", "completion_attempted", 1),
        ("pending_recovery", "challenge", None),
        ("pending_pairing", "requested_capabilities", ["combat-v2"]),
        ("pending_pairing", "pairing_id", "opaque-id"),
        ("pending_pairing", "completion_attempted", 1),
        ("pending_participation", "expected_generation", None),
        ("pending_participation", "attempted", 1),
    ],
)
def test_new_journal_guards_are_closed_and_type_strict(tmp_path, where, key, value):
    path = tmp_path / "state.json"
    raw = active()
    raw[where][key] = value
    before = put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "attempt_type",
        "cancel_unsent",
        "cancel_off",
        "cancel_same",
        "extra",
        "missing_protocol",
        "missing_device",
    ],
)
def test_automatic_cancel_requires_attempted_on_and_distinct_bound_uuid(
    tmp_path, mutation
):
    path = tmp_path / "state.json"
    raw = active()
    raw["automatic"]["pending"] = deepcopy(PENDING)
    pending = raw["automatic"]["pending"]
    if mutation == "attempt_type":
        pending["attempted"] = 1
    elif mutation == "cancel_unsent":
        pending["attempted"] = False
    elif mutation == "cancel_off":
        pending["command"]["enabled"] = False
    elif mutation == "cancel_same":
        pending["cancel_after_on"]["request_id"] = REQUEST
    elif mutation == "extra":
        pending["cancel_after_on"]["cas"] = 1
    elif mutation == "missing_protocol":
        del pending["command"]["protocol"]
    else:
        raw["device_id"] = None
    put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)


@pytest.mark.parametrize(
    "outcome,enabled,attempted,has_receipt,valid",
    [
        ("receipt", True, True, True, True),
        ("receipt", True, False, True, True),  # Disk does not invent attempt history.
        ("receipt", True, True, False, False),
        ("already_off", False, True, False, True),
        ("observed_off", False, True, False, True),
        ("already_off", True, True, False, False),
        ("observed_off", True, True, False, False),
        ("rejected", True, True, False, True),
        ("superseded_unknown", True, True, False, True),
        ("cancelled_unsent", True, False, False, True),
        ("cancelled_unsent", True, True, False, False),
        ("rejected", True, True, True, False),
        ("arbitrary", True, True, False, False),
    ],
)
def test_completion_closed_relationships_not_invented_history(
    tmp_path, outcome, enabled, attempted, has_receipt, valid
):
    path = tmp_path / "state.json"
    raw = active()
    pending = deepcopy(PENDING)
    pending.update(attempted=attempted, cancel_after_on=None)
    pending["command"]["enabled"] = enabled
    raw["automatic"]["last_result"] = {
        "pending": pending,
        "outcome": outcome,
        "receipt": deepcopy(RECEIPT) if has_receipt else None,
    }
    put(path, raw)
    if valid:
        loaded = s.load(path)
        assert loaded.identity is not None
        s.save(path, loaded)
        assert json.loads(path.read_bytes()) == raw
    else:
        with pytest.raises(ValueError):
            s.load(path)


def test_relative_pairing_normalizes_before_storage_and_rechecks_expanded_limit(
    tmp_path,
):
    path = tmp_path / "state.json"
    raw = active()
    raw["pending_pairing"]["approval_url"] = "/approve"
    put(path, raw)
    loaded = s.load(path)
    assert loaded.identity is not None
    assert loaded.pending_pairing.approval_url == "https://relay.example.test/approve"
    s.save(path, loaded)
    assert (
        json.loads(path.read_bytes())["pending_pairing"]["approval_url"]
        == loaded.pending_pairing.approval_url
    )
    raw["pending_pairing"]["approval_url"] = "/" + "x" * 2047
    put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)


def test_receipt_derives_off_from_exact_historical_result_not_current_consent(tmp_path):
    path = tmp_path / "state.json"
    original = read_active(path, pending=True)
    s.save(path, original)
    original = s.load(path)
    receipt = p.parse_automatic_receipt(deepcopy(RECEIPT))
    candidate = s.settle_automatic_receipt(original, receipt)
    assert candidate.automatic.observed_consent == original.automatic.observed_consent
    assert candidate.automatic.pending.command == p.AutomaticCommand(
        CANCEL, DATE, False, 5, 8
    )
    assert candidate.automatic.pending.attempted is False
    assert candidate.automatic.pending.cancel_after_on is None
    assert candidate.automatic.last_result.pending == original.automatic.pending
    assert candidate.automatic.last_result.receipt == receipt
    assert candidate.automatic.last_result.outcome == "receipt"
    assert original.automatic.pending.command.enabled is True
    s.save(path, candidate)
    assert s.load(path) == candidate
    # Session replacement is independent of archive/automatic intent.
    replacement = s.replace_session(candidate, TOKEN, expires_at=DATE)
    assert replacement.automatic == candidate.automatic
    assert replacement.cutover == candidate.cutover


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_id", CANCEL),
        ("intent_created_at", "2026-09-07T11:59:59.999Z"),
        ("expected_generation", 3),
        ("expected_revision", 6),
        ("enabled", False),
    ],
)
def test_receipt_binding_is_whole_command_not_uuid_only(tmp_path, key, value):
    path = tmp_path / "state.json"
    original = read_active(path, pending=True)
    # Change pending (receipt stays independently valid), disable cancellation
    # only to keep changed Off itself a valid saved command.
    pending = replace(
        original.automatic.pending,
        command=replace(original.automatic.pending.command, **{key: value}),
        cancel_after_on=None,
    )
    original = replace(original, automatic=replace(original.automatic, pending=pending))
    s.save(path, original)
    with pytest.raises(ValueError):
        s.settle_automatic_receipt(
            s.load(path), p.parse_automatic_receipt(deepcopy(RECEIPT))
        )
    assert s.load(path) == original


def test_ordinary_receipt_settlement_clears_only_pending(tmp_path):
    path = tmp_path / "state.json"
    original = read_active(path, pending=True)
    original = replace(
        original,
        automatic=replace(
            original.automatic,
            pending=replace(original.automatic.pending, cancel_after_on=None),
        ),
    )
    candidate = s.settle_automatic_receipt(
        original, p.parse_automatic_receipt(deepcopy(RECEIPT))
    )
    assert candidate.automatic.pending is None
    assert candidate.automatic.last_result.pending == original.automatic.pending
    assert candidate.automatic.observed_consent == original.automatic.observed_consent
    s.save(path, candidate)
    assert s.load(path) == candidate


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_failed_derived_off_save_preserves_prior_on_and_cancel_bytes(
    tmp_path, monkeypatch, failure
):
    path = tmp_path / "state.json"
    original = read_active(path, pending=True)
    s.save(path, original)
    before = path.read_bytes()
    candidate = s.settle_automatic_receipt(
        original, p.parse_automatic_receipt(deepcopy(RECEIPT))
    )

    def failed(*args, **kwargs):
        raise OSError("injected failure")

    monkeypatch.setattr(s.atomicio.os, failure, failed)
    with pytest.raises(OSError):
        s.save(path, candidate)
    assert path.read_bytes() == before
    assert s.load(path) == original
    assert candidate.automatic.pending.command.enabled is False
    assert list(tmp_path.glob("*.tmp")) == []
