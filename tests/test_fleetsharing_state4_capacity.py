"""Independent byte arithmetic and future terminal headroom on real load/save."""

import json
from copy import deepcopy
from dataclasses import replace
from uuid import UUID as UUIDValue

import pytest

from tests.fleetsharing_state4_helpers import (
    CANCEL,
    COMMAND,
    CONSENT,
    DATE,
    EXPIRY,
    PENDING,
    RECEIPT,
    REQUEST,
    active,
    compact,
    legacy,
    put,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def maximal_document(*, completion="on"):
    raw = active()
    origin = "https://" + ".".join(["a" * 63] * 3 + ["a" * 61]) + ":65535"
    raw["relay_origin"] = origin
    raw["identity"]["protected_private_key_b64"] = "eHh4" * 2048
    date = "9999-12-31T23:59:59.999Z"
    raw.update(
        last_revision=2147483647,
        session_expires_at=date,
        acknowledged_capabilities=["shared-source-v1", "combat-v2"],
        observed_participation={"enabled": False, "generation": 2147483647},
    )
    raw["pending_pairing"].update(
        approval_url=origin + "/" + "\U00010000" * (2048 - len(origin) - 1),
        expires_at=date,
        completion_attempted=False,
    )
    raw["pending_recovery"].update(issued_at=date, completion_attempted=False)
    raw["pending_recovery"]["challenge"]["expires_at"] = date
    raw["pending_participation"].update(expected_generation=2147483646, attempted=False)
    raw["auth_pause"] = {"result": "account_ineligible", "retry_not_before": date}
    raw["pending_source_commands"] = [
        {
            "protocol": 2,
            "operation": "stop",
            "source_id": str(UUIDValue(int=i + 1, version=4)),
            "expected_generation": 2147483646,
            "request_id": REQUEST,
            "intent_created_at": date,
            "expected_automatic": {"consent_generation": 9007199254740991},
        }
        for i in range(256)
    ]
    old = legacy()
    old["identity"] = deepcopy(raw["identity"])
    old["relay_origin"] = origin
    old["pending_pairing"]["approval_url"] = raw["pending_pairing"]["approval_url"]
    old["pending_source_commands"] = [
        {
            "operation": "stop",
            "source_id": str(UUIDValue(int=i + 1, version=4)),
            "expected_generation": 2147483646,
        }
        for i in range(256)
    ]
    # Invalid SESSION metadata is legitimate evidence, not a padding/unknown key.
    # A lone surrogate must be escaped; astral evidence must stay UTF-8.
    old["session_id"] = "\ud800\U00010000"
    old["session_id"] += "x" * (65536 - len(compact(old)))
    assert len(compact(old)) == 65536
    outcomes = [
        {"selector": v, "status": "fenced"}
        for v in [
            "session",
            "pairing",
            "recovery",
            "participation",
            *["source:" + v["source_id"] for v in old["pending_source_commands"]],
        ]
    ]
    raw["cutover"] = {"original": old, "outcomes": outcomes}
    # Maximum digit widths with checked On (+1/+1) and reserved final Off.
    pending = deepcopy(PENDING)
    pending["command"].update(
        expected_generation=9007199254740989, expected_revision=9007199254740989
    )
    on_result = {
        **CONSENT,
        "generation": 9007199254740990,
        "revision": 9007199254740990,
    }
    on_receipt = {
        **deepcopy(RECEIPT),
        "command": deepcopy(pending["command"]),
        "result": on_result,
    }
    off_command = {
        **COMMAND,
        "enabled": False,
        "expected_generation": 9007199254740990,
        "expected_revision": 9007199254740990,
    }
    off_result = {
        **CONSENT,
        "generation": 9007199254740990,
        "revision": 9007199254740991,
        "enabled": False,
        "disabled_at": DATE,
        "closed_reason": "approver_revoked",
    }
    off_receipt = {
        "kind": "automatic",
        "command": off_command,
        "accepted_at": DATE,
        "expires_at": EXPIRY,
        "result": off_result,
    }
    raw["automatic"] = {
        "observed_consent": off_result,
        "pending": pending,
        "last_result": {
            "pending": {
                "command": off_command,
                "attempted": False,
                "cancel_after_on": None,
            },
            "outcome": "receipt",
            "receipt": off_receipt,
        },
    }
    if completion == "on":
        # Cancellation makes the full On completion larger than Off completion,
        # although the disabled Consent makes an Off receipt itself larger.
        raw["automatic"]["last_result"] = {
            "pending": deepcopy(pending),
            "outcome": "receipt",
            "receipt": deepcopy(on_receipt),
        }
    return raw, on_receipt


@pytest.mark.parametrize("completion", ["on", "off"])
def test_simultaneous_maximum_archive_sources_journals_automatic_and_derived_off(
    tmp_path,
    completion,
):
    path = tmp_path / "state.json"
    raw, receipt = maximal_document(completion=completion)
    put(path, raw)
    loaded = s.load(path)
    assert loaded.identity is not None
    s.save(path, loaded)
    stored = json.loads(path.read_bytes())
    assert stored == raw
    assert len(stored["cutover"]["outcomes"]) == 260
    assert len(stored["pending_source_commands"]) == 256
    assert len(compact(stored["cutover"]["original"])) == 65536
    assert len(compact(stored["cutover"]["outcomes"])) <= 32768
    assert (
        len(
            compact(
                {k: v for k, v in stored.items() if k not in ("cutover", "automatic")}
            )
        )
        <= 147456
    )
    assert all(len(compact(v)) <= 400 for v in stored["pending_source_commands"])
    assert len(compact(stored["automatic"])) <= 8192
    assert len(path.read_bytes()) <= 262144
    candidate = s.settle_automatic_receipt(loaded, p.parse_automatic_receipt(receipt))
    assert candidate.automatic.pending.command.expected_generation == 9007199254740990
    assert candidate.automatic.pending.command.expected_revision == 9007199254740990
    assert candidate.automatic.pending.command.request_id == CANCEL
    s.save(path, candidate)
    assert s.load(path) == candidate
    assert candidate.cutover == loaded.cutover
    off = {
        "kind": "automatic",
        "command": {
            **COMMAND,
            "request_id": CANCEL,
            "enabled": False,
            "expected_generation": 9007199254740990,
            "expected_revision": 9007199254740990,
        },
        "accepted_at": DATE,
        "expires_at": EXPIRY,
        "result": {
            **CONSENT,
            "generation": 9007199254740990,
            "revision": 9007199254740991,
            "enabled": False,
            "disabled_at": DATE,
            "closed_reason": "explicit_off",
        },
    }
    completed = s.settle_automatic_receipt(s.load(path), p.parse_automatic_receipt(off))
    assert completed.automatic.pending is None
    assert completed.automatic.last_result.receipt.result.revision == 9007199254740991
    assert completed.cutover == loaded.cutover
    s.save(path, completed)
    assert s.load(path) == completed


def test_exact_limit_legacy_raw_migrates_all_260_items_without_write(tmp_path):
    path = tmp_path / "state.json"
    raw, _ = maximal_document()
    original = raw["cutover"]["original"]
    before = put(path, original)
    assert len(before) == 65536
    loaded = s.load(path)
    assert loaded.cutover.original == original
    assert len(loaded.cutover.outcomes) == 260
    assert loaded.pending_source_commands == ()
    assert path.read_bytes() == before
    s.save(path, loaded)
    assert s.load(path) == loaded


def test_whole_future_reserve_exact_fit_plus_one_is_checked_before_write(
    tmp_path, monkeypatch
):
    path = tmp_path / "state.json"
    s.save(path, s.EMPTY)
    before = path.read_bytes()
    # Fixed archive/outcomes headroom cannot be borrowed by currently empty work.
    exact = 65536 + 32768 + (32768 + 256 * 400 + 255) + (512 + 512 + 1792 + 47) + 8192
    monkeypatch.setattr(s, "MAX_STATE_FILE_BYTES", exact)
    s.save(path, s.EMPTY)
    monkeypatch.setattr(s, "MAX_STATE_FILE_BYTES", exact - 1)
    with pytest.raises(ValueError):
        s.save(path, s.EMPTY)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "check", ["save", "check_admission_capacity", "check_control_capacity", "load"]
)
@pytest.mark.parametrize("partition", ["active", "automatic"])
def test_empty_state_reserves_all_future_slots_and_terminal_components(
    tmp_path, monkeypatch, check, partition
):
    path = tmp_path / "state.json"
    s.save(path, s.EMPTY)
    before = path.read_bytes()
    # Independent arithmetic: non-source root includes the empty source array;
    # the 255 separating commas are future array framing, not 256 objects.
    active_reserve = 32768 + 256 * 400 + 255
    automatic_reserve = (
        512
        + 512
        + 1792
        + len(compact({"observed_consent": None, "pending": None, "last_result": None}))
        - 3 * len(b"null")
    )
    limit_name, exact = (
        ("MAX_ACTIVE_BYTES", active_reserve)
        if partition == "active"
        else ("MAX_AUTOMATIC_BYTES", automatic_reserve)
    )
    monkeypatch.setattr(s, limit_name, exact)

    def exercise():
        if check == "save":
            s.save(path, s.EMPTY)
        elif check == "load":
            s.load(path)
        else:
            getattr(s, check)(s.EMPTY)

    exercise()
    monkeypatch.setattr(s, limit_name, exact - 1)
    with pytest.raises(ValueError):
        exercise()
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "partition,field",
    [("MAX_ORIGINAL_BYTES", "original"), ("MAX_OUTCOMES_BYTES", "outcomes")],
)
def test_archive_partition_exact_fit_plus_one_never_borrows(
    tmp_path, monkeypatch, partition, field
):
    path = tmp_path / "state.json"
    put(path, legacy())
    loaded = s.load(path)
    assert loaded.identity is not None
    s.save(path, loaded)
    before = path.read_bytes()
    size = len(compact(json.loads(before)["cutover"][field]))
    monkeypatch.setattr(s, partition, size)
    s.save(path, loaded)
    monkeypatch.setattr(s, partition, size - 1)
    with pytest.raises(ValueError):
        s.save(path, loaded)
    assert path.read_bytes() == before


def test_actual_source_commands_and_automatic_components_have_individual_ceilings(
    tmp_path, monkeypatch
):
    path = tmp_path / "state.json"
    raw, _ = maximal_document()
    put(path, raw)
    original = s.load(path)
    assert original.identity is not None
    s.save(path, original)
    before = path.read_bytes()
    components = {
        "MAX_SOURCE_COMMAND_BYTES": raw["pending_source_commands"][0],
        "MAX_PENDING_AUTOMATIC_BYTES": raw["automatic"]["pending"],
        "MAX_CONSENT_BYTES": raw["automatic"]["observed_consent"],
        "MAX_AUTOMATIC_COMPLETION_BYTES": raw["automatic"]["last_result"],
        "MAX_AUTOMATIC_RECEIPT_BYTES": raw["automatic"]["last_result"]["receipt"],
    }
    for name, value in components.items():
        with monkeypatch.context() as patch:
            patch.setattr(s, name, len(compact(value)) - 1)
            with pytest.raises(ValueError):
                s.save(path, original)
        assert path.read_bytes() == before


def test_reservation_does_not_rewrite_retained_source_bytes(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    raw = active()
    raw["pending_source_commands"] = raw["pending_source_commands"][:1]
    put(path, raw)
    loaded = s.load(path)
    assert loaded.identity is not None
    command_size = len(compact(raw["pending_source_commands"][0]))
    reserve = 32768 + command_size + 255 * 400 + 255
    monkeypatch.setattr(s, "MAX_ACTIVE_BYTES", reserve)
    s.save(path, loaded)
    assert (
        json.loads(path.read_bytes())["pending_source_commands"]
        == raw["pending_source_commands"]
    )
    monkeypatch.setattr(s, "MAX_ACTIVE_BYTES", reserve - 1)
    with pytest.raises(ValueError):
        s.check_control_capacity(loaded)


def test_invalid_candidate_or_nonfinite_evidence_never_calls_writer(
    tmp_path, monkeypatch
):
    path = tmp_path / "state.json"
    s.save(path, s.EMPTY)
    before = path.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid candidate reached writer")

    monkeypatch.setattr(s.atomicio, "write_atomic", forbidden)
    for revision in (True, float("nan"), float("inf")):
        candidate = replace(s.EMPTY, last_revision=revision)
        with pytest.raises(ValueError):
            s.save(path, candidate)
        assert path.read_bytes() == before
    with pytest.raises(TypeError):
        s.save(path, replace(s.EMPTY, identity=object()))
    assert path.read_bytes() == before
