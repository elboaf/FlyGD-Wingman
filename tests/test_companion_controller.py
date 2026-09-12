"""Controller transactions exercise real settings with an asynchronous native seam."""

import copy
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from wingman import settings
from wingman.preview.companioncontroller import CompanionController, CompanionPorts
from wingman.preview.companions import (
    CompanionDefinition,
    CompanionEvent,
    GeometryDelta,
    PreparedCompanion,
    RegionSelection,
    SourceBinding,
    SourceDescriptor,
    region_from_pixels,
    serialize_definitions,
)
from wingman.preview.layout import Rect
from wingman.preview.runtime import RuntimeState, SelectionLease


def until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline, "controller did not settle"
        time.sleep(0.005)


class Runtime:
    def __init__(self):
        self.lease = None
        self.demands = []
        self.current = RuntimeState(
            1, 1, 0, 1, "active", "stopped", "active", False, None
        )

    def snapshot(self):
        return replace(self.current, selection_pending=self.lease is not None)

    def acquire_selection(self, operation_id):
        if self.lease is not None:
            return None
        self.lease = SelectionLease(operation_id, 1)
        return self.lease

    def release_selection(self, lease):
        if self.lease == lease:
            self.lease = None

    def set_companions(self, enabled, revision):
        self.demands.append((enabled, revision))
        return self.snapshot()


class Harness:
    def __init__(self, tmp_path, initial=None):
        self.path = tmp_path / "settings.json"
        self.data = settings.load(self.path)
        self.data["companion_previews"] = initial or {
            "enabled": False,
            "definitions": [],
        }
        self.runtime = Runtime()
        self.commands = []
        self.publications = []
        self.fail = False
        self.block = None
        self.entered = threading.Event()
        self.worker_threads = []
        self.controller = CompanionController(
            CompanionPorts(self.update, self.runtime, self.submit, self.publish),
            self.data["companion_previews"],
            available=True,
        )

    @contextmanager
    def update(self):
        self.worker_threads.append(threading.get_ident())
        with settings.update(self.data, self.path) as data:
            yield data
            self.entered.set()
            if self.block:
                self.block.wait(3)
            if self.fail:
                raise OSError("disk full")

    def submit(self, command):
        self.commands.append(command)
        return True

    def publish(self, state):
        self.worker_threads.append(threading.get_ident())
        self.publications.append(state)

    def command(self, kind):
        until(lambda: any(c.kind == kind for c in self.commands))
        return next(c for c in reversed(self.commands) if c.kind == kind)

    def event(self, kind, command, payload=None):
        self.controller.native_event(CompanionEvent(kind, command.token, payload))

    def receipt(self, pending):
        def done():
            return next(
                (
                    r
                    for r in self.controller.state()["operations"]
                    if r["operation_id"] == pending["operation_id"] and not r["pending"]
                ),
                None,
            )

        until(done)
        return done()

    def sources(self):
        pending = self.controller.sources()
        command = self.command("enumerate")
        binding = SourceBinding(
            15, 20, 30, r"c:\apps\map.exe", "Map", "Map", (800, 600)
        )
        self.event(
            "sources",
            command,
            (
                [
                    {
                        "candidate_token": "opaque",
                        "application": "map.exe",
                        "title": "Map",
                    }
                ],
                {"opaque": binding},
            ),
        )
        assert self.receipt(pending)["sources"][0]["candidate_token"] == "opaque"
        return binding

    def prepare(self, mode="whole", identity=None, generation=None):
        binding = self.sources()
        pending = self.controller.select(
            identity, "opaque", mode, "Mapper", "exact", "Map", generation
        )
        if mode == "region":
            picker = self.command("pick-region")
            region = region_from_pixels(Rect(20, 30, 200, 150), binding.client_size)
            self.event(
                "region-selected",
                picker,
                RegionSelection(binding, binding.client_size, region),
            )
        command = self.command("prepare")
        definition, _ = command.payload
        return (
            pending,
            command,
            PreparedCompanion(
                binding, binding.client_size, definition.window, definition.region
            ),
        )


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    yield harness
    if harness.block:
        harness.block.set()
    assert harness.controller.shutdown()


def test_no_boot_publication_and_all_io_publication_use_one_noncaller_worker(h):
    assert not h.publications
    h.controller.state()
    pending = h.controller.set_master(True)
    assert pending["pending"] and not pending["applied"]
    assert h.receipt(pending)["persisted"]
    until(lambda: h.publications)
    assert set(h.worker_threads) != {threading.get_ident()}
    assert len(set(h.worker_threads)) == 1


@pytest.mark.parametrize("mode", ["whole", "region"])
def test_candidate_is_not_persisted_until_prepared_then_promotes(h, mode):
    pending, command, facts = h.prepare(mode)
    assert h.data["companion_previews"]["definitions"] == []
    assert not any(c.kind == "promote" for c in h.commands)
    h.event("prepared", command, facts)
    receipt = h.receipt(pending)
    assert receipt["applied"] and receipt["persisted"]
    assert h.data["companion_previews"]["definitions"][0]["id"] == pending["id"]
    assert h.command("promote").token == command.token
    assert h.runtime.lease is not None
    h.event("closed", command)
    until(lambda: h.runtime.lease is None)


def test_failed_save_discards_candidate_without_fabricating_definition(h):
    pending, command, facts = h.prepare()
    h.fail = True
    h.event("prepared", command, facts)
    receipt = h.receipt(pending)
    assert not receipt["applied"] and not receipt["persisted"]
    assert "disk full" in receipt["error"]
    assert h.data["companion_previews"]["definitions"] == []
    assert h.command("discard").token == command.token
    assert h.runtime.lease is not None


def test_changed_region_source_size_refuses_before_persistence(h):
    pending, command, facts = h.prepare("region")
    h.event("prepared", command, replace(facts, source_size=(900, 600)))
    assert not h.receipt(pending)["applied"]
    assert not h.path.exists()
    h.command("discard")


def test_native_callbacks_never_wait_for_settings_and_admitted_save_stays_real(h):
    pending, command, facts = h.prepare()
    h.block = threading.Event()
    h.event("prepared", command, facts)
    assert h.entered.wait(2)
    before = time.monotonic()
    h.event("failed", command, "Source closed")
    h.controller.close_admission()
    h.controller.close_publication()
    assert time.monotonic() - before < 0.2
    assert not h.controller.shutdown(timeout=0.01)
    h.block.set()
    assert h.controller.shutdown()
    assert h.data["companion_previews"]["definitions"][0]["id"] == pending["id"]
    receipt = h.receipt(pending)
    assert receipt["persisted"] and receipt["applied"]


def test_disable_and_remove_save_before_native_and_failure_keeps_authority(h):
    pending, command, facts = h.prepare()
    h.event("prepared", command, facts)
    assert h.receipt(pending)["persisted"]
    h.event("closed", command)
    until(lambda: h.runtime.lease is None)
    row = h.controller.state()["rows"][0]
    before = copy.deepcopy(h.data["companion_previews"])
    h.fail = True
    removal = h.controller.remove(row["id"], row["generation"])
    assert not h.receipt(removal)["applied"]
    assert h.data["companion_previews"] == before
    h.fail = False
    removal = h.controller.remove(row["id"], row["generation"])
    assert h.receipt(removal)["persisted"]
    h.event("prepared", command, facts)
    assert h.controller.drain().result(2)
    assert not h.controller.state()["rows"]


def test_stale_geometry_is_rejected_and_failure_is_honest_session_only(h):
    pending, command, facts = h.prepare()
    h.event("prepared", command, facts)
    h.receipt(pending)
    h.event("closed", command)
    until(lambda: h.runtime.lease is None)
    row = h.controller.state()["rows"][0]
    h.controller.native_event(
        CompanionEvent(
            "status",
            None,
            (
                {
                    "id": row["id"],
                    "generation": 1,
                    "binding_revision": 1,
                    "status": "live",
                    "error": None,
                    "binding": facts.binding,
                },
            ),
        )
    )
    h.controller.drain().result(2)
    h.fail = True
    h.controller.record_geometry(
        GeometryDelta(row["id"], 1, 1, 1, Rect(100, 100, 400, 300))
    )
    assert not h.controller.drain().result(2)
    state = h.controller.state()
    assert state["rows"][0]["window"] == facts.window._asdict()
    assert "session" in state["rows"][0]["error"].lower()
    h.fail = False
    h.controller.record_geometry(GeometryDelta(row["id"], 1, 0, 2, Rect(5, 5, 20, 20)))
    assert h.controller.drain().result(2)
    assert (
        h.data["companion_previews"]["definitions"][0]["window"]
        == facts.window._asdict()
    )


def commit(h, mode="whole"):
    pending, command, facts = h.prepare(mode)
    h.event("prepared", command, facts)
    h.receipt(pending)
    h.event("closed", command)
    until(lambda: h.runtime.lease is None)
    return h.controller.state()["rows"][0], facts


def test_failed_reselection_preserves_id_generation_and_committed_definition(h):
    row, _ = commit(h)
    before = copy.deepcopy(h.data["companion_previews"])
    h.commands.clear()
    pending, command, facts = h.prepare("region", row["id"], row["generation"])
    h.fail = True
    h.event("prepared", command, facts)
    assert not h.receipt(pending)["persisted"]
    assert h.data["companion_previews"] == before
    assert h.controller.state()["rows"][0]["generation"] == row["generation"]
    h.command("discard")


def test_source_lost_while_waiting_for_settings_lock_cannot_admit_save(h):
    pending, command, facts = h.prepare()
    with settings._SAVE_LOCK:
        h.event("prepared", command, facts)
        # The worker reaches the transaction lock, not disk admission.
        until(
            lambda: (
                command.token.operation_id in h.controller._operations
                and h.controller._operations[command.token.operation_id].phase
                == "prepared"
            )
        )
        h.event("failed", command, "Source closed before save")
    receipt = h.receipt(pending)
    assert not receipt["persisted"]
    assert not h.data["companion_previews"]["definitions"]


def test_successful_remove_revokes_a_delayed_native_promotion(h):
    pending, command, facts = h.prepare()
    h.event("prepared", command, facts)
    h.receipt(pending)
    assert h.controller.selection_valid(command.token)
    row = h.controller.state()["rows"][0]
    removed = h.controller.remove(row["id"], row["generation"])
    assert h.receipt(removed)["persisted"]
    assert not h.controller.selection_valid(command.token)


def test_master_off_preserves_selection_lease_and_save_but_original_epoch_token(h):
    assert h.receipt(h.controller.set_master(True))["persisted"]
    pending, command, facts = h.prepare("region")
    assert h.receipt(h.controller.set_master(False))["persisted"]
    h.runtime.current = replace(
        h.runtime.current, companion_epoch=2, companions="stopped"
    )
    assert h.controller.selection_valid(command.token)
    h.event("prepared", command, facts)
    assert h.receipt(pending)["persisted"]
    assert not h.data["companion_previews"]["enabled"]
    assert h.command("promote").token.family_epoch == 1


def test_movement_during_replacement_save_rebases_only_pre_swap_geometry(h):
    row, old_facts = commit(h)
    h.controller.native_event(
        CompanionEvent(
            "status",
            None,
            (
                {
                    "id": row["id"],
                    "generation": 1,
                    "binding_revision": 1,
                    "status": "live",
                    "error": None,
                    "binding": old_facts.binding,
                },
            ),
        )
    )
    h.controller.drain().result(2)
    h.commands.clear()
    pending, command, facts = h.prepare("whole", row["id"], 1)
    h.entered.clear()
    h.block = threading.Event()
    h.event("prepared", command, facts)
    assert h.entered.wait(2)
    moved = Rect(700, 100, 320, 210)
    h.controller.record_geometry(GeometryDelta(row["id"], 1, 1, 1, moved))
    h.block.set()
    h.receipt(pending)
    h.controller.native_event(
        CompanionEvent(
            "status",
            None,
            (
                {
                    "id": row["id"],
                    "generation": 2,
                    "binding_revision": 3,
                    "status": "live",
                    "error": None,
                    "binding": facts.binding,
                },
            ),
        )
    )
    h.controller.record_geometry(GeometryDelta(row["id"], 1, 1, 2, Rect(1, 2, 50, 50)))
    h.event("closed", command)
    assert h.controller.drain().result(2)
    assert h.data["companion_previews"]["definitions"][0]["window"] == moved._asdict()
    reset = h.command("reset")
    assert reset.payload == moved
    assert reset.token.selection_lease is None


def test_native_recovery_clears_runtime_error_but_not_geometry_warning(h):
    row, facts = commit(h)

    def status(kind, error):
        h.controller.native_event(
            CompanionEvent(
                "status",
                None,
                (
                    {
                        "id": row["id"],
                        "generation": 1,
                        "binding_revision": 1,
                        "status": kind,
                        "error": error,
                        "binding": facts.binding,
                    },
                ),
            )
        )
        h.controller.drain().result(2)

    status("source-unavailable", "Capture unavailable")
    status("live", None)
    assert h.controller.state()["rows"][0]["error"] is None
    h.fail = True
    h.controller.record_geometry(
        GeometryDelta(row["id"], 1, 1, 1, Rect(400, 400, 320, 210))
    )
    h.controller.drain().result(2)
    status("live", None)
    assert "session" in h.controller.state()["rows"][0]["error"].lower()


def test_geometry_is_debounced_and_successful_reset_discards_older_delta(h):
    row, facts = commit(h)
    h.controller.native_event(
        CompanionEvent(
            "status",
            None,
            (
                {
                    "id": row["id"],
                    "generation": 1,
                    "binding_revision": 1,
                    "status": "live",
                    "error": None,
                    "binding": facts.binding,
                },
            ),
        )
    )
    assert h.controller.drain().result(2)
    h.controller.record_geometry(
        GeometryDelta(row["id"], 1, 1, 1, Rect(500, 500, 400, 300))
    )
    assert (
        h.data["companion_previews"]["definitions"][0]["window"]
        == facts.window._asdict()
    )
    reset = h.controller.reset_geometry(row["id"], row["generation"])
    assert h.receipt(reset)["persisted"]
    assert h.controller.drain().result(2)
    assert h.data["companion_previews"]["definitions"][0]["window"] == {
        "x": 100,
        "y": 100,
        "w": 280,
        "h": 210,
    }


@pytest.mark.parametrize("identity", [[], {}, 1, True])
def test_bad_identity_is_a_receipt_not_a_bridge_exception(h, identity):
    for method, args in [
        (h.controller.remove, (identity, 1)),
        (h.controller.edit, (identity, "Map", "exact", "Map", 1)),
        (h.controller.reselect_region, (identity, 1)),
        (h.controller.set_enabled, (identity, False, 1)),
        (h.controller.reset_geometry, (identity, 1)),
    ]:
        result = method(*args)
        assert not result["pending"] and not result["applied"]


def test_label_edit_queued_during_geometry_save_keeps_latest_saved_position(h):
    row, facts = commit(h)
    h.controller.native_event(
        CompanionEvent(
            "status",
            None,
            (
                {
                    "id": row["id"],
                    "generation": 1,
                    "binding_revision": 1,
                    "status": "live",
                    "error": None,
                    "binding": facts.binding,
                },
            ),
        )
    )
    h.controller.drain().result(2)
    moved = Rect(700, 500, 320, 210)
    h.block = threading.Event()
    h.entered.clear()
    h.controller.record_geometry(GeometryDelta(row["id"], 1, 1, 1, moved))
    barrier = h.controller.drain()
    assert h.entered.wait(2)
    edit = h.controller.edit(row["id"], "Renamed", "exact", "Map", 1)
    h.block.set()
    assert barrier.result(2)
    assert h.receipt(edit)["persisted"]
    assert h.data["companion_previews"]["definitions"][0]["window"] == moved._asdict()


def test_source_tokens_expire_and_terminal_receipts_are_bounded(h):
    h.sources()
    h.controller._catalog_until = time.monotonic() - 1
    assert not h.controller.select(
        None, "opaque", "whole", "Map", "exact", "Map", None
    )["pending"]
    for n in range(40):
        assert h.receipt(h.controller.set_master(bool(n % 2)))["persisted"]
    assert len(h.controller.state()["operations"]) == 32


def test_enable_missing_source_persists_waiting_without_candidate(h):
    row, _ = commit(h)
    disabled = h.controller.set_enabled(row["id"], False, 1)
    assert h.receipt(disabled)["persisted"]
    h.commands.clear()
    enabled = h.controller.set_enabled(row["id"], True, 2)
    command = h.command("enumerate")
    h.event("sources", command, ([], {}))
    assert h.receipt(enabled)["persisted"]
    assert not any(c.kind == "prepare" for c in h.commands)
    assert h.data["companion_previews"]["definitions"][0]["enabled"]
    until(lambda: h.runtime.lease is None)


def test_max_enabled_is_admission_not_global_native_capacity(tmp_path):
    definitions = tuple(
        CompanionDefinition(
            1,
            uuid4().hex,
            "Map",
            True,
            "whole",
            SourceDescriptor(
                r"c:\apps\map.exe", "map.exe", "Map", "Map", "exact", "Map"
            ),
            Rect(0, 0, 320, 210),
            None,
        )
        for _ in range(8)
    )
    harness = Harness(
        tmp_path, {"enabled": False, "definitions": serialize_definitions(definitions)}
    )
    try:
        harness.sources()
        refused = harness.controller.select(
            None, "opaque", "whole", "Map", "exact", "Map", None
        )
        assert not refused["pending"] and not refused["applied"]
        assert "8" in refused["error"]
    finally:
        assert harness.controller.shutdown()
