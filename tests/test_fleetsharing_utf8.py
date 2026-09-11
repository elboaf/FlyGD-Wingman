"""Legacy upgrade journals must grow without replacing consent or identity."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fleetsharing_capacity_helpers import (
    compact_bytes,
    legacy_bytes,
    maximal_state,
    source_id,
)
from tests.test_fleetsharing_capacity import DiskStore
from tests.test_fleetsharing_worker import (
    DATE,
    DEVICE,
    PAIRED_STATE,
    UUID,
    FakeRelayClient,
    _worker,
    drive,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def legacy_save(path, state):
    # Frozen f81c14d save body, only module-qualified names changed. This is the
    # actual old validation + atomic writer, not merely an equivalent encoder.
    data = json.dumps(s._to_dict(state), indent=2, allow_nan=False)
    if len(data.encode("utf-8")) > s.MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    s._parse_v3(p.decode_json(data.encode("utf-8")))
    s.atomicio.write_atomic(Path(path), data)


def legacy_upgrade():
    return replace(
        PAIRED_STATE,
        session_id=None,
        pending_pairing=s.PendingPairing("upgrade"),
        pending_source_commands=tuple(
            p.StartSource(source_id(i), 1, UUID, DATE) for i in range(200)
        ),
    )


def approval_url():
    prefix = PAIRED_STATE.relay_origin + "/"
    return prefix + "\U00010000" * (2048 - len(prefix))


def admitted_upgrade():
    return replace(
        legacy_upgrade(),
        pending_pairing=s.PendingPairing(
            "upgrade", "pair-id", approval_url(), "2026-09-07T12:10:00.000Z"
        ),
    )


def test_old_writer_upgrade_url_off_stop_and_sources_survive_restart(tmp_path):
    original = legacy_upgrade()
    path = tmp_path / "legacy-upgrade.json"
    legacy_save(path, original)
    before = path.read_bytes()
    assert before == legacy_bytes(original) and len(before) <= 65536
    assert s.load(path) == original
    assert path.read_bytes() == before  # Restart/load is not a migration write.
    # This journal was legal before admission reserves existed. Its first real
    # response cannot be stored even in ASCII compact JSON, before Off/metadata.
    assert len(compact_bytes(admitted_upgrade())) > 68000
    store = DiskStore.__new__(DiskStore)
    store.path, store.saved, store.rejected = path, [], []
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    begin_pairing = client.begin_pairing

    def long_url(*args, **kwargs):
        return replace(begin_pairing(*args, **kwargs), approval_url=approval_url())

    client.begin_pairing = long_url
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    worker.resume_pending()
    drive(worker, mono, 3)
    admitted = store.load()
    rendered_url = worker.status().approval_url
    assert path.stat().st_size <= 65536

    # Off and Stop are persisted alongside the original admitted URL, before
    # completion is eligible. Recreate the owner at that actual disk boundary.
    off = worker.request_participation(False)
    target = original.pending_source_commands[0].source_id
    assert worker.request_source_stop(target)
    assert worker.status().local_inhibited
    worker.iterate_once()
    saved = store.load()
    assert saved.pending_participation.intent_id == off
    assert saved.pending_pairing == admitted.pending_pairing
    assert saved.identity == original.identity
    assert saved.pending_source_commands == (
        *original.pending_source_commands[1:],
        p.StopSource(target, 0),
    )
    restarted = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    restarted.resume_pending()
    drive(restarted, mono, 30)
    assert not client.device.participation.enabled
    assert client.source_views[target].state == "ended"
    assert admitted == admitted_upgrade()
    assert rendered_url == approval_url()
    assert not store.rejected
    assert any(isinstance(c, p.StartSource) for c in client.controls)
    assert all(
        c in original.pending_source_commands
        for c in client.controls
        if isinstance(c, p.StartSource)
    )
    assert store.load().pending_participation is None
    assert store.load().pending_pairing is None
    assert store.load().identity == original.identity
    assert len(client.pair_keys) == 1  # No replacement admission/retry identity.
    retained = {c.source_id for c in store.load().pending_source_commands}
    assert all(
        c.source_id in retained or c.source_id in client.source_views
        for c in original.pending_source_commands
    )
    assert all(v.identity == original.identity for v in store.saved)
    assert client.cadence_refusals == 0


def test_utf8_fallback_retains_exact_values_and_real_file_bound(tmp_path):
    candidate = admitted_upgrade()
    # Quotes are escaped by JSON; non-ASCII scalar values are not. Preserve the
    # exact URL spelling rather than URL-normalizing it during serialization.
    url = candidate.pending_pairing.approval_url[:-6] + '"é漢𝄞?&'
    candidate = replace(
        candidate, pending_pairing=replace(candidate.pending_pairing, approval_url=url)
    )
    path = tmp_path / "utf8.json"
    assert len(compact_bytes(candidate)) > 65536
    s.save(path, candidate)
    data = path.read_bytes()
    assert len(data) <= 65536
    assert "\U00010000".encode() in data
    assert p.decode_json(data) == p.decode_json(compact_bytes(candidate))
    assert s.load(path) == candidate
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "value", ["\ud800", "\udfff", "\udfffX\ud800", "\x00\x1f", '\\u1234"\\', "é漢𝄞"]
)
def test_utf8_encoder_preserves_json_escaping_and_lone_surrogates(value):
    # Raw encoder compatibility, NOT a claim these values pass URL validation.
    # In particular literal backslash-u text must not become a Unicode escape.
    raw = {"value": value}
    encoded = s._compact_utf8(raw).encode("utf-8")
    assert p.decode_json(encoded) == raw


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "\x00", "\x1f", "\\"])
def test_old_writer_rejects_nontext_urls_without_losing_old_bytes(tmp_path, value):
    path = tmp_path / "old-validation.json"
    legacy_save(path, PAIRED_STATE)
    before = path.read_bytes()
    candidate = replace(
        PAIRED_STATE,
        pending_pairing=s.PendingPairing(
            "upgrade", "p", PAIRED_STATE.relay_origin + "/" + value, DATE
        ),
    )
    for save in (legacy_save, s.save):
        with pytest.raises(ValueError):
            save(path, candidate)
        assert path.read_bytes() == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_utf8_encoder_does_not_enable_nonjson_numbers(value):
    with pytest.raises(ValueError):
        s._compact_utf8({"value": value})


@pytest.mark.parametrize("encoding", ["indented", "ascii", "utf8"])
def test_serialization_failures_leave_last_good_bytes(tmp_path, monkeypatch, encoding):
    path = tmp_path / "serialization.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    dumps = json.dumps
    reached = []

    def fail(raw, **kwargs):
        mode = (
            "indented"
            if "indent" in kwargs
            else "ascii"
            if kwargs.get("ensure_ascii", True)
            else "utf8"
        )
        if mode == encoding:
            reached.append(mode)
            raise ValueError("controlled serialization failure")
        return dumps(raw, **kwargs)

    monkeypatch.setattr(s.json, "dumps", fail)
    with pytest.raises(ValueError, match="controlled serialization failure"):
        s.save(path, admitted_upgrade())
    assert reached == [encoding]
    assert path.read_bytes() == before
    assert s.load(path) == PAIRED_STATE


def test_utf8_atomic_replace_failure_preserves_bytes_and_cleans_stage(
    tmp_path, monkeypatch
):
    path = tmp_path / "atomic.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    candidate = admitted_upgrade()
    reached = []

    def fail(source, target):
        data = Path(source).read_bytes()
        assert len(data) <= 65536
        assert "\U00010000".encode() in data
        assert p.decode_json(data) == p.decode_json(compact_bytes(candidate))
        reached.append(target)
        raise OSError("controlled atomic replace failure")

    monkeypatch.setattr(s.atomicio.os, "replace", fail)
    with pytest.raises(OSError, match="controlled atomic replace failure"):
        s.save(path, candidate)
    assert reached == [path]
    assert path.read_bytes() == before
    assert s.load(path) == PAIRED_STATE
    assert list(tmp_path.iterdir()) == [path]


def test_old_indented_budget_covers_mutable_growth_and_next_stop():
    # Minimize old mutable metadata (empty capability arrays are shorter than
    # null), then account for every possible Start/Stop count and decimal width.
    # Fixed identity/origin growth is bounded separately; loading canonicalizes
    # their aliases, so an old noncanonical spelling cannot make this worse.
    minimum = replace(
        PAIRED_STATE,
        identity=replace(PAIRED_STATE.identity, protected_private_key_b64="AAAA"),
        relay_origin="https://a",
        session_id="a",
        approved_capabilities=(),
        session_approved_capabilities=(),
        acknowledged_capabilities=(),
    )
    assert s._parse_v3(p.decode_json(legacy_bytes(minimum))) == minimum
    start = p.StartSource(UUID, 1, UUID, DATE)
    stop = p.StopSource(UUID, 0)
    maximum_stop = replace(stop, expected_generation=p.INT4_MAX - 1)
    old_base = len(legacy_bytes(minimum))

    def increment(command, encode):
        return len(encode(replace(minimum, pending_source_commands=(command,)))) - len(
            encode(minimum)
        )

    # Nonempty indented arrays add two bracket-layout bytes; compact arrays
    # save the absent final comma. Pin that independently on two real commands.
    old_start = increment(start, legacy_bytes) - 2
    old_stop = increment(stop, legacy_bytes) - 2
    compact_start = increment(start, compact_bytes) + 1
    compact_stop = increment(maximum_stop, compact_bytes) + 1
    two = replace(
        minimum, pending_source_commands=(start, replace(stop, source_id=source_id(1)))
    )
    assert len(legacy_bytes(two)) == old_base + old_start + old_stop + 2
    assert len(compact_bytes(two)) == len(
        compact_bytes(minimum)
    ) + compact_start + increment(stop, compact_bytes)

    maximum = maximal_state()
    raw = s._to_dict(
        replace(
            maximum,
            identity=minimum.identity,
            relay_origin=minimum.relay_origin,
            pending_source_commands=(),
        )
    )
    # Deliberate sizing overestimates: even the URL origin is charged four UTF-8
    # bytes per character; the longest pause label and date coexist here.
    raw["pending_pairing"]["approval_url"] = "\U00010000" * 2048
    raw["auth_pause"]["result"] = "device_key_conflict"
    future_base = len(
        json.dumps(
            raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    identity_span = 8192 - 4 + len(maximum.relay_origin) - len(minimum.relay_origin)
    digit_span = len(str(p.JS_SAFE_MAX)) - 1
    largest = 0
    for starts in range(p.MAX_SOURCE_INTENTS + 1):
        for stops in range(p.MAX_SOURCE_INTENTS - starts + 1):
            count = starts + stops
            old_floor = (
                old_base + old_start * starts + old_stop * stops + (2 if count else 0)
            )
            if old_floor > 65536:
                continue
            # Every extra immutable byte costs the SAME byte in both encodings.
            extra = min(identity_span + digit_span * starts, 65536 - old_floor)
            next_stop = count < p.MAX_SOURCE_INTENTS
            future = (
                future_base
                + compact_start * starts
                + compact_stop * (stops + next_stop)
                + extra
                - (1 if count or next_stop else 0)
            )
            largest = max(largest, future)
    assert largest <= 65536


def test_true_utf8_overflow_still_preserves_previous_file(tmp_path):
    candidate = maximal_state()
    data = json.dumps(
        s._to_dict(candidate),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    assert s._parse_v3(p.decode_json(data)) == candidate
    assert len(data) > 65536  # The old 92,554-byte ASCII figure is not this size.
    path = tmp_path / "overflow.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    with pytest.raises(s.CapacityError):
        s.save(path, candidate)
    assert path.read_bytes() == before
