"""State4 canonical UTF-8: exact values, owner exposure, restart and write faults.

Old pretty/ASCII fallback arithmetic is retired; the owner barriers remain.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.fleetsharing_capacity_helpers import compact_bytes, maximal_state, source_id
from tests.fleetsharing_worker_control_helpers import ControlRelay
from tests.test_fleetsharing_worker import DATE, EXPIRY, PAIRED_STATE, UUID, drive
from tests.test_fleetsharing_worker_state4 import file_rig
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def approval_url():
    prefix = PAIRED_STATE.relay_origin + "/"
    return prefix + "\U00010000" * (2048 - len(prefix))


def upgrade_state():
    return replace(
        PAIRED_STATE,
        pending_pairing=s.PendingPairing("upgrade"),
        pending_source_commands=tuple(
            p.SourceStart(source_id(i), 1, UUID, DATE) for i in range(200)
        ),
    )


def admitted_upgrade():
    return replace(
        upgrade_state(),
        pending_pairing=s.PendingPairing("upgrade", UUID, approval_url(), EXPIRY),
    )


def test_upgrade_url_off_stop_and_sources_survive_restart(tmp_path):
    worker, _, store, mono = file_rig(tmp_path, upgrade_state())
    relay = ControlRelay(worker, store)
    relay.approval_url = approval_url()
    exposed = []
    worker.subscribe_status(
        lambda value: (
            exposed.append((value.approval_url, s.load(store.path).pending_pairing))
            if value.approval_url
            else None
        )
    )
    worker.resume_pending()
    for _ in range(8):
        drive(worker, mono, 1)
        if worker.status().approval_url:
            break
    assert exposed and all(
        url == pairing.approval_url == approval_url() for url, pairing in exposed
    )
    assert s.load(store.path).pending_pairing.approval_url == approval_url()
    # Submit exact terminal journals before recreation; no hidden CAS rebinding.
    worker.set_source_watch(True)
    drive(worker, mono, 4)
    worker.set_source_watch(False)
    old = s.load(store.path).pending_source_commands[0]
    target = old.source_id
    generation = relay.sources[target].generation if target in relay.sources else 0
    assert worker.request_source_stop(
        target, expected_generation=generation, expected_automatic=None, supersedes=old
    )

    def hold_stop(request, saved):
        if request.method == "PUT" and request.full_url.endswith("/sources"):
            raise OSError("precommit Stop unavailable until restart")

    relay.before = hold_stop
    off = worker.request_participation(False)
    drive(worker, mono, 4)
    off = worker.confirm_participation(
        off, expected_generation=1, binding=worker.status().metadata.binding
    )
    assert off
    worker.iterate_once()
    journal = s.load(store.path)
    assert journal.identity == PAIRED_STATE.identity
    assert journal.pending_participation.intent_id == off
    stop = next(c for c in journal.pending_source_commands if c.source_id == target)
    assert isinstance(stop, p.SourceStop)
    assert worker.stop()
    from tests.test_fleetsharing_worker import FakeRelayClient, _worker

    restarted = _worker(
        FakeRelayClient(device=relay.device),
        store=store,
        timing_context=worker._timing_context,
        utc_clock=worker._utc_clock,
        sharing_enabled=lambda: False,
    )
    relay.worker = restarted
    relay.before = None
    from wingman.fleetsharing.client import FleetRelayClient

    restarted._client_factory = lambda origin: FleetRelayClient(
        origin, transport=relay.transport
    )
    restarted.resume_pending()
    drive(restarted, mono, 30)
    saved = s.load(store.path)
    assert saved.identity == journal.identity and saved.pending_participation is None
    assert not relay.device.participation.enabled
    assert stop.request_id in relay.receipts
    assert all(c.source_id != target for c in saved.pending_source_commands)
    assert all(
        c in upgrade_state().pending_source_commands
        for c in saved.pending_source_commands
    )
    assert all(v.identity == journal.identity for v in store.saves)


def test_canonical_utf8_retains_exact_values_and_real_file_bound(tmp_path):
    candidate = admitted_upgrade()
    url = candidate.pending_pairing.approval_url[:-6] + '"é漢𝄞?&'
    candidate = replace(
        candidate, pending_pairing=replace(candidate.pending_pairing, approval_url=url)
    )
    path = tmp_path / "utf8.json"
    s.save(path, candidate)
    data = path.read_bytes()
    assert len(data) < s.MAX_STATE_FILE_BYTES
    assert len(compact_bytes(candidate)) > len(data)
    assert "\U00010000".encode() in data
    assert p.decode_json(data) == p.decode_json(compact_bytes(candidate))
    assert s.load(path) == candidate
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "value", ["\ud800", "\udfff", "\udfffX\ud800", "\x00\x1f", '\\u1234"\\', "é漢𝄞"]
)
def test_utf8_encoder_preserves_json_escaping_and_lone_surrogates(value):
    raw = {"value": value}
    assert p.decode_json(s._compact_utf8(raw).encode()) == raw


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "\x00", "\x1f", "\\"])
def test_writer_rejects_nontext_urls_without_losing_old_bytes(tmp_path, value):
    path = tmp_path / "validation.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    candidate = replace(
        PAIRED_STATE,
        pending_pairing=s.PendingPairing(
            "upgrade", UUID, PAIRED_STATE.relay_origin + "/" + value, DATE
        ),
    )
    with pytest.raises(ValueError):
        s.save(path, candidate)
    assert path.read_bytes() == before and s.load(path) == PAIRED_STATE


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_utf8_encoder_does_not_enable_nonjson_numbers(value):
    with pytest.raises(ValueError):
        s._compact_utf8({"value": value})


def test_serialization_failures_leave_last_good_bytes(tmp_path, monkeypatch):
    path = tmp_path / "serialization.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    reached = []

    def fail(raw, **kwargs):
        reached.append(kwargs)
        raise ValueError("controlled serialization failure")

    with monkeypatch.context() as patch:
        patch.setattr(s.json, "dumps", fail)
        with pytest.raises(ValueError):
            s.save(path, admitted_upgrade())
    assert reached and all(not value.get("ensure_ascii", True) for value in reached)
    assert path.read_bytes() == before and s.load(path) == PAIRED_STATE


def test_utf8_atomic_replace_failure_preserves_bytes_and_cleans_stage(
    tmp_path, monkeypatch
):
    path = tmp_path / "atomic.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    candidate = admitted_upgrade()
    reached = []

    def fail(source, target):
        reached.append((target, Path(source).read_bytes()))
        raise OSError("controlled atomic replace failure")

    monkeypatch.setattr(s.atomicio.os, "replace", fail)
    with pytest.raises(OSError, match="controlled atomic replace failure"):
        s.save(path, candidate)
    assert len(reached) == 1 and reached[0][0] == path
    data = reached[0][1]
    assert len(data) <= s.MAX_STATE_FILE_BYTES and "\U00010000".encode() in data
    assert p.decode_json(data) == p.decode_json(compact_bytes(candidate))
    assert path.read_bytes() == before and s.load(path) == PAIRED_STATE
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("stops", [False, True])
def test_state4_maximum_fields_fit_without_ascii_fallback(tmp_path, stops):
    candidate = maximal_state(stops=stops)
    path = tmp_path / "maximum.json"
    s.save(path, candidate)
    assert s.load(path) == candidate
    assert len(path.read_bytes()) <= s.MAX_STATE_FILE_BYTES
    assert path.read_bytes() == s._compact_utf8(s._to_dict(candidate)).encode()


def test_partition_overflow_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "overflow.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    # Inject a smaller partition to exercise refusal, not the retired 64KiB bound.
    with monkeypatch.context() as patch:
        patch.setattr(s, "MAX_ACTIVE_BYTES", 32768)
        with pytest.raises(s.CapacityError):
            s.save(path, maximal_state())
    assert path.read_bytes() == before and s.load(path) == PAIRED_STATE
