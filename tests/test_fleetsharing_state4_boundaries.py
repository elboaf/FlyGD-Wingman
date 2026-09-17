"""Boundary regressions supplementary to the initial coupled production-path TDD."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fleetsharing_state4_helpers import (
    CONSENT,
    DATE,
    IDENTITY,
    PENDING,
    RECEIPT,
    UUID,
    active,
    compact,
    legacy,
    put,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def test_failed_open_after_existing_stat_is_not_absence(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    before = put(path, legacy(1))

    def failed_open(*args, **kwargs):
        raise FileNotFoundError("read race after existence was observed")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", failed_open)
        with pytest.raises(FileNotFoundError):
            s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_every_root_keyset_is_closed_and_legacy_v1_alone_allows_missing(
    tmp_path, version
):
    path = tmp_path / "state.json"
    raw = active() if version == 4 else legacy(version)
    for key in tuple(raw):
        candidate = deepcopy(raw)
        del candidate[key]
        put(path, candidate)
        if version == 1 and key not in ("version", "relay_origin"):
            loaded = s.load(path)
            assert loaded.cutover.original == candidate
        else:
            with pytest.raises(s.QuarantineError):
                s.load(path)


@pytest.mark.parametrize("version", [2, 3, 4])
def test_source_identity_uniqueness_ignores_case_without_rewriting_spelling(
    tmp_path, version
):
    path = tmp_path / "state.json"
    raw = active() if version == 4 else legacy(version)
    raw["pending_source_commands"][1]["source_id"] = UUID.lower()
    before = put(path, raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == before


def test_compact_original_bound_is_independent_of_raw_legacy_bound(tmp_path):
    path = tmp_path / "state.json"
    # 1e2 decodes to the FLOAT 100.0: exact decoded-value reserialization grows.
    raw = b'{"version":1,"session_id":[' + b",".join([b"1e2"] * 12000) + b"]}"
    assert len(raw) < 65536
    assert len(compact(json.loads(raw))) > 65536
    path.write_bytes(raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("value", [b"1e999", b"NaN", b"Infinity"])
def test_nonfinite_legacy_session_evidence_is_not_silently_changed(tmp_path, value):
    path = tmp_path / "state.json"
    raw = b'{"version":1,"session_id":' + value + b"}"
    path.write_bytes(raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("last_revision", 1),
        ("session_expires_at", DATE),
        ("session_approved_capabilities", []),
        ("acknowledged_capabilities", []),
    ],
)
def test_sessionless_active_metadata_cannot_keep_old_authority(tmp_path, field, value):
    path = tmp_path / "state.json"
    raw = active()
    raw.update(
        session_id=None,
        last_revision=0,
        session_expires_at=None,
        session_approved_capabilities=None,
        acknowledged_capabilities=None,
    )
    raw[field] = value
    put(path, raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)


@pytest.mark.parametrize(
    "field", ["command", "accepted_at", "expires_at", "result", "kind"]
)
def test_last_completion_cannot_save_mismatched_or_invalid_receipt(tmp_path, field):
    path = tmp_path / "state.json"
    raw = active()
    receipt = deepcopy(RECEIPT)
    if field == "command":
        receipt["command"]["intent_created_at"] = "2026-09-07T11:59:59.999Z"
    elif field == "accepted_at":
        receipt["accepted_at"] = "2026-09-07T11:59:59.999Z"
    elif field == "expires_at":
        receipt["expires_at"] = DATE
    elif field == "result":
        receipt["result"]["revision"] = 9
    else:
        receipt["kind"] = "source_stop"
    raw["automatic"]["last_result"] = {
        "pending": deepcopy(PENDING),
        "outcome": "receipt",
        "receipt": receipt,
    }
    before = put(path, raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == before


def test_receipt_needs_no_current_consent_and_never_infers_one(tmp_path):
    path = tmp_path / "state.json"
    raw = active()
    raw["automatic"]["pending"] = deepcopy(PENDING)
    put(path, raw)
    original = s.load(path)
    candidate = s.settle_automatic_receipt(
        original, p.parse_automatic_receipt(deepcopy(RECEIPT))
    )
    assert candidate.automatic.observed_consent is None
    assert candidate.automatic.pending.command.expected_generation == 5
    s.save(path, candidate)
    assert s.load(path) == candidate


@pytest.mark.parametrize("enabled", [False, True])
def test_exhausted_but_scalar_valid_pending_command_is_retained_not_admitted(
    tmp_path, enabled
):
    path = tmp_path / "state.json"
    raw = active()
    pending = deepcopy(PENDING)
    pending.update(attempted=True, cancel_after_on=None)
    pending["command"].update(
        enabled=enabled,
        expected_generation=9007199254740991,
        expected_revision=9007199254740991,
    )
    raw["automatic"]["pending"] = pending
    put(path, raw)
    loaded = s.load(path)
    s.save(path, loaded)
    assert json.loads(path.read_bytes()) == raw


def test_archive_outcomes_can_progress_without_rewriting_or_rebinding_device(tmp_path):
    path = tmp_path / "state.json"
    raw = legacy()
    put(path, raw)
    loaded = s.load(path)
    statuses = [
        "superseded_session",
        "recovered_identity",
        "expired_unproven",
        "observed_choice",
        "expired_unproven",
        "dismissed",
    ]
    archive = replace(
        loaded.cutover,
        outcomes=tuple(
            replace(v, status=status)
            for v, status in zip(loaded.cutover.outcomes, statuses, strict=True)
        ),
    )
    candidate = s.replace_session(
        replace(loaded, cutover=archive), "A" * 43, expires_at=DATE
    )
    s.save(path, candidate)
    saved = s.load(path)
    assert [v.status for v in saved.cutover.outcomes] == statuses
    assert saved.cutover.original == raw and saved.device_id == UUID


def test_saved_buffers_do_not_alias_caller_collections(tmp_path):
    path = tmp_path / "state.json"
    raw = legacy()
    put(path, raw)
    loaded = s.load(path)
    buffer = bytearray(compact(raw))
    outcomes = list(loaded.cutover.outcomes)
    caps = ["shared-source-v1"]
    commands = [p.SourceStart(UUID, 42, UUID, DATE)]
    candidate = replace(
        loaded,
        cutover=s.Cutover(buffer, outcomes),
        approved_capabilities=caps,
        pending_source_commands=commands,
        pending_pairing=s.PendingPairing("initial", requested_capabilities=caps),
    )
    buffer[:] = b"bad"
    outcomes.clear()
    caps.clear()
    commands.clear()
    s.save(path, candidate)
    assert s.load(path) == candidate
    assert candidate.cutover.original == raw
    assert candidate.approved_capabilities == ("shared-source-v1",)
    assert candidate.pending_pairing.requested_capabilities == ("shared-source-v1",)
    assert len(candidate.pending_source_commands) == 1


def test_one_atomic_replacement_receives_full_detached_candidate(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    raw = active()
    raw["automatic"]["observed_consent"] = deepcopy(CONSENT)
    put(path, raw)
    candidate = s.load(path)
    original_writer = s.atomicio.write_atomic
    writes = []

    def observed_writer(target, text):
        writes.append(json.loads(text))
        original_writer(target, text)

    monkeypatch.setattr(s.atomicio, "write_atomic", observed_writer)
    s.save(path, candidate)
    assert writes == [raw]
    writes[0]["identity"].clear()
    assert candidate.identity == s.DeviceIdentity(**IDENTITY)
    assert s.load(path) == candidate
