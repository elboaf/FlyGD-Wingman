"""Real model/settings/store; only native/page effects use controlled ports."""

import copy
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace

import pytest

from wingman import settings
from wingman.preview import savedlayouts as model
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry
from wingman.preview.layoutadmission import PrimaryLayoutAdmission
from wingman.preview.store import LayoutStore
from wingman.telemetry.model import ClientSessionId


def settled(value):
    future = Future()
    future.set_result(value)
    return future


def record():
    return model.SavedLayout(
        "1" * 32, "Original", (model.SavedCharacter("Pilot", True, None),)
    )


def setup_controller(tmp_path, *, records=(), section=None):
    from wingman.preview.layoutcontroller import (
        PreviewLayoutsController,
        PreviewLayoutsPorts,
    )

    path = tmp_path / "settings.json"
    doc = settings.load(path)
    with settings.update(doc, path) as live:
        live["preview"].update(section or {})
        live["preview"]["saved_layouts"] = model.serialize(records)
    reader = settings.committed_preview(doc)
    gate = PrimaryLayoutAdmission()
    calls = []

    def capture(lease):
        calls.append(("capture", lease))
        return settled(
            model.PrimaryLayoutCapture(0, 0, 0, (), (), (), reader.snapshot())
        )

    def apply(lease, captured, commit, rectangles):
        calls.append(("apply", lease, captured, commit, rectangles))
        return settled(model.PrimaryLayoutLiveResult("deferred", None))

    ports = PreviewLayoutsPorts(
        read_preview=reader.snapshot,
        live_names=lambda: (),
        capture=capture,
        apply=apply,
        refresh_visibility=lambda lease: (
            calls.append(("visibility", lease))
            or settled(model.PrimaryLayoutLiveResult("applied", None))
        ),
        release=lambda lease: calls.append(("release", lease)),
        publish_state=lambda state: calls.append(("publish", state)),
    )
    store = LayoutStore(lambda: settings.update(doc, path))
    controller = PreviewLayoutsController(
        reader.snapshot(),
        store=store,
        admission=gate,
        ports=ports,
        id_factory=lambda: "2" * 32,
    )
    return controller, doc, path, gate, calls


def native_calls(calls):
    return [call for call in calls if call[0] in ("capture", "apply", "visibility")]


def test_rename_refuses_stale_revision_without_native_effects(tmp_path):
    saved = record()
    controller, _, path, gate, calls = setup_controller(tmp_path, records=(saved,))
    before = path.read_bytes()
    refused = controller.rename(saved.id, "stale", "Renamed")
    assert not refused["applied"] and not refused["persisted"]
    assert path.read_bytes() == before
    receipt = controller.rename(saved.id, model.record_revision(saved), "Renamed")
    assert receipt["applied"] and receipt["persisted"]
    assert (
        settings.load(path)["preview"]["saved_layouts"]["items"][0]["name"] == "Renamed"
    )
    assert not native_calls(calls)
    assert gate.wait_idle(0)


@pytest.mark.parametrize("action", ["apply", "update_saved", "remove"])
@pytest.mark.parametrize(
    "identity,revision", [("missing", "stale"), ("1" * 32, "stale")]
)
def test_stale_or_missing_record_has_no_write_or_native_effects(
    tmp_path, action, identity, revision
):
    controller, _, path, _, calls = setup_controller(tmp_path, records=(record(),))
    before = path.read_bytes()
    res = getattr(controller, action)(identity, revision)
    assert not res["applied"] and res["error"]
    assert path.read_bytes() == before
    assert not native_calls(calls)


@pytest.mark.parametrize("name", ["", "   ", "bad\n", None, " original ", "ORIGINAL"])
def test_invalid_or_duplicate_save_name_refuses_before_capture(tmp_path, name):
    controller, _, path, _, calls = setup_controller(tmp_path, records=(record(),))
    before = path.read_bytes()
    result = controller.save_current(name)
    assert not result["persisted"] and result["error"]
    assert path.read_bytes() == before
    assert not native_calls(calls)


def test_save_and_update_capture_all_sessions_live_and_offline_without_moving(tmp_path):
    controller, _, path, gate, calls = setup_controller(
        tmp_path, section={"excluded": ["Excluded"], "seen": ["Offline"]}
    )
    captures = []

    def capture(lease):
        value = model.PrimaryLayoutCapture(
            1,
            2,
            3,
            (
                ClientSessionId(11, 12, "Excluded", 13),
                ClientSessionId(21, 22, "Failed primary", 23),
            ),
            (("Offline", Entry(Rect(10, 20, 300, 200), True)),),
            (("Live", Rect(40, 50, 320, 210)),),
            controller._ports.read_preview(),
        )
        captures.append(value)
        return settled(value)

    controller._ports = replace(controller._ports, capture=capture)
    res = controller.save_current("  Fleet  ")
    assert res["applied"] and res["persisted"] and res["live"] is None
    saved = model.deserialize(settings.load(path)["preview"]["saved_layouts"])[0]
    assert saved.name == "Fleet"
    members = {c.name: c for c in saved.characters}
    assert set(members) == {"Excluded", "Failed primary", "Offline", "Live"}
    assert members["Excluded"] == model.SavedCharacter("Excluded", False, None)
    assert members["Failed primary"].rect is None
    assert members["Offline"].rect == Rect(10, 20, 300, 200)
    assert members["Live"].rect == Rect(40, 50, 320, 210)
    res = controller.update_saved(saved.id, model.record_revision(saved))
    assert res["applied"] and len(captures) == 2
    assert settings.load(path)["preview"]["layouts"] == {}
    assert not [c for c in calls if c[0] in ("apply", "visibility")]
    assert gate.wait_idle(0)


def test_apply_merges_one_commit_with_exact_capture_lease_and_null_member_map(tmp_path):
    saved = model.SavedLayout(
        "1" * 32,
        "Mixed",
        (
            model.SavedCharacter("Pilot", True, Rect(100, 200, 320, 210)),
            model.SavedCharacter("Hidden", False, None),
        ),
    )
    controller, _, path, gate, calls = setup_controller(
        tmp_path,
        records=(saved,),
        section={
            "excluded": ["Absent", "Pilot"],
            "restore_preview_positions": False,
            "layouts": {"Absent": {"x": 1, "y": 2, "w": 30, "h": 40, "locked": True}},
        },
    )
    captured = model.PrimaryLayoutCapture(
        1, 2, 3, (), (), (), controller._ports.read_preview()
    )
    controller._ports = replace(
        controller._ports, capture=lambda lease: settled(captured)
    )
    res = controller.apply(saved.id, model.record_revision(saved))
    assert res["applied"] and res["persisted"] and res["live"] == "deferred"
    call = next(c for c in calls if c[0] == "apply")
    assert call[2] is captured
    assert call[1] is next(c for c in calls if c[0] == "release")[1]
    assert call[4] == {"Pilot": Rect(100, 200, 320, 210), "Hidden": None}
    assert dict(call[3].layouts)["Pilot"].rect == Rect(100, 200, 320, 210)
    section = settings.load(path)["preview"]
    assert section["excluded"] == ["Absent", "Hidden"]
    assert section["layouts"]["Absent"]["locked"]
    assert not section["restore_preview_positions"]
    assert section["saved_layouts"] == model.serialize((saved,))
    assert gate.wait_idle(0)


def test_rename_noop_and_remove_leave_working_arrangement_alone(tmp_path, monkeypatch):
    saved = record()
    controller, _, path, _, calls = setup_controller(tmp_path, records=(saved,))
    before = settings.load(path)["preview"]
    writes = []
    original = settings._save_locked
    monkeypatch.setattr(
        settings,
        "_save_locked",
        lambda *args: (writes.append(args), original(*args))[1],
    )
    assert controller.rename(saved.id, model.record_revision(saved), " Original ")[
        "applied"
    ]
    assert not writes
    assert controller.remove(saved.id, model.record_revision(saved))["applied"]
    after = settings.load(path)["preview"]
    assert after["saved_layouts"]["items"] == []
    assert {k: v for k, v in after.items() if k != "saved_layouts"} == {
        k: v for k, v in before.items() if k != "saved_layouts"
    }
    assert not native_calls(calls)


@pytest.mark.parametrize("stage", ["capture", "persist", "native"])
def test_pending_stages_keep_slot_and_lease_until_settlement_and_shutdown_can_retry(
    tmp_path, monkeypatch, stage
):
    saved = record()
    controller, _, path, gate, calls = setup_controller(tmp_path, records=(saved,))
    entered, proceed = threading.Event(), threading.Event()
    original_save = settings._save_locked

    def block(value):
        entered.set()
        assert proceed.wait(5)
        return value

    if stage == "capture":
        controller._ports = replace(
            controller._ports,
            capture=lambda lease: settled(
                block(
                    model.PrimaryLayoutCapture(
                        0, 0, 0, (), (), (), controller._ports.read_preview()
                    )
                )
            ),
        )
    elif stage == "persist":

        def persist(*args):
            block(None)
            return original_save(*args)

        monkeypatch.setattr(settings, "_save_locked", persist)
    else:
        controller._ports = replace(
            controller._ports,
            apply=lambda *args: settled(
                block(model.PrimaryLayoutLiveResult("deferred", None))
            ),
        )
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(controller.apply, saved.id, model.record_revision(saved))
        try:
            assert entered.wait(5)
            state = controller.state()
            assert state["busy"] and state["operation"]["pending"]
            assert not pending.done()
            assert not controller.rename(saved.id, model.record_revision(saved), "New")[
                "applied"
            ]
            controller.close_admission()
            controller.close_admission()
            assert not controller.shutdown(0)
            assert not gate.wait_idle(0)
            published = len([c for c in calls if c[0] == "publish"])
        finally:
            proceed.set()
        res = pending.result(5)
    assert res["persisted"] == (stage != "capture")
    assert not res["state"]["operation"]["pending"]
    assert len([c for c in calls if c[0] == "publish"]) == published
    assert controller.shutdown(0) and gate.wait_idle(0)
    assert settings.load(path)["preview"]["saved_layouts"]["items"]


def test_shared_exclusions_accept_only_newer_store_sequence_and_receipts_return_latest(
    tmp_path, monkeypatch
):
    controller, _, path, gate, _ = setup_controller(tmp_path)
    entered, proceed = threading.Event(), threading.Event()
    original = controller._store.transact

    def delayed(mutate):
        commit = original(mutate)
        if commit.revision == 1:
            entered.set()
            assert proceed.wait(5)
        return commit

    monkeypatch.setattr(controller._store, "transact", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(controller.set_excluded, "First", True)
        try:
            assert entered.wait(5)
            second = controller.set_excluded("Second", True)
            assert second["state"]["excluded"] == ["First", "Second"]
        finally:
            proceed.set()
        old = first.result(5)
    assert old["state"]["excluded"] == ["First", "Second"]
    assert old["state"]["revision"] >= second["state"]["revision"]
    assert settings.load(path)["preview"]["excluded"] == ["First", "Second"]
    assert gate.wait_idle(0)


def test_unchanged_exclusion_acknowledges_prior_commit_before_delayed_callback(
    tmp_path, monkeypatch
):
    controller, _, path, _, _ = setup_controller(tmp_path)
    entered, proceed = threading.Event(), threading.Event()
    original = controller._store.transact

    def delayed(mutate):
        commit = original(mutate)
        if commit.revision == 1:
            entered.set()
            assert proceed.wait(5)
        return commit

    monkeypatch.setattr(controller._store, "transact", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(controller.set_excluded, "Pilot", True)
        try:
            assert entered.wait(5)
            res = controller.set_excluded("Pilot", True)
            assert res["applied"] and res["state"]["excluded"] == ["Pilot"]
        finally:
            proceed.set()
        assert first.result(5)["state"]["excluded"] == ["Pilot"]
    assert settings.load(path)["preview"]["excluded"] == ["Pilot"]


def test_state_unions_sampled_owners_but_never_reverts_committed_exclusions(tmp_path):
    controller, _, _, _, _ = setup_controller(tmp_path)
    stale = controller._ports.read_preview()
    controller.set_excluded("Hidden", True)
    stale["seen"] = ["New offline"]
    controller._ports = replace(
        controller._ports,
        read_preview=lambda: copy.deepcopy(stale),
        live_names=lambda: ("New live",),
    )
    state = controller.state()
    assert state["excluded"] == ["Hidden"]
    assert set(state["owners"]) == {"Hidden", "New offline", "New live"}
    state["excluded"].clear()
    assert controller.state()["excluded"] == ["Hidden"]


@pytest.mark.parametrize("effect", ["persist", "native", "publish", "cache", "release"])
def test_failures_distinguish_rollback_from_successful_commit(
    tmp_path, monkeypatch, effect
):
    saved = record()
    controller, _, path, gate, _ = setup_controller(tmp_path, records=(saved,))

    def fail(*args):
        raise OSError("injected " + effect)

    if effect == "persist":
        monkeypatch.setattr(settings, "_save_locked", fail)
    elif effect == "native":
        controller._ports = replace(controller._ports, refresh_visibility=fail)
    elif effect == "publish":
        controller._ports = replace(controller._ports, publish_state=fail)
    elif effect == "release":
        controller._ports = replace(controller._ports, release=fail)
    else:
        monkeypatch.setattr(controller, "_accept_commit", fail)
    res = controller.set_excluded("Pilot", True)
    assert res["persisted"] == res["applied"] == (effect != "persist")
    assert settings.load(path)["preview"]["excluded"] == (
        [] if effect == "persist" else ["Pilot"]
    )
    assert res["error"] if effect == "persist" else res["warning"]
    assert gate.wait_idle(0)


@pytest.mark.parametrize("stage", ["capture", "native"])
def test_unsettled_host_future_keeps_borrowed_caller_and_exact_lease(tmp_path, stage):
    saved = record()
    controller, _, _, gate, _ = setup_controller(tmp_path, records=(saved,))
    pending = Future()
    entered = threading.Event()
    captured = model.PrimaryLayoutCapture(
        0, 0, 0, (), (), (), controller._ports.read_preview()
    )

    def submit(*args):
        entered.set()
        return pending

    controller._ports = replace(
        controller._ports, **{("capture" if stage == "capture" else "apply"): submit}
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        caller = pool.submit(controller.apply, saved.id, model.record_revision(saved))
        try:
            assert entered.wait(5)
            assert not caller.done() and not gate.wait_idle(0)
            state = controller.state()
            assert state["operation"]["pending"]
            if stage == "native":
                assert state["operation"]["persisted"]
        finally:
            pending.set_result(
                captured
                if stage == "capture"
                else model.PrimaryLayoutLiveResult("applied", None)
            )
        assert caller.result(5)["persisted"]
    assert gate.wait_idle(0)


def test_capture_revalidates_record_inside_transaction(tmp_path):
    saved = record()
    controller, doc, path, gate, calls = setup_controller(tmp_path, records=(saved,))
    entered = threading.Event()
    pending = Future()
    captured = model.PrimaryLayoutCapture(
        0, 0, 0, (), (), (), controller._ports.read_preview()
    )
    controller._ports = replace(
        controller._ports, capture=lambda lease: (entered.set(), pending)[1]
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        caller = pool.submit(controller.apply, saved.id, model.record_revision(saved))
        try:
            assert entered.wait(5)
            with settings.update(doc, path) as live:
                live["preview"]["saved_layouts"] = model.serialize(
                    (replace(saved, name="Changed"),)
                )
            before = path.read_bytes()
        finally:
            pending.set_result(captured)
        result = caller.result(5)
    assert not result["persisted"] and "changed" in result["error"]
    assert path.read_bytes() == before
    assert not [call for call in calls if call[0] == "apply"]
    assert gate.wait_idle(0)


def test_publication_and_pure_ports_never_hold_controller_lock(tmp_path):
    saved = record()
    controller, _, _, _, _ = setup_controller(tmp_path, records=(saved,))
    original = controller._ports
    entered, proceed = threading.Event(), threading.Event()

    def publish(payload):
        if (
            payload["operation"]
            and payload["operation"]["pending"]
            and not entered.is_set()
        ):
            entered.set()
            assert proceed.wait(5)

    controller._ports = replace(original, publish_state=publish)
    with ThreadPoolExecutor(max_workers=2) as pool:
        named = pool.submit(
            controller.rename, saved.id, model.record_revision(saved), "Renamed"
        )
        try:
            assert entered.wait(5)
            # A shared metadata lease does not occupy the ordinary-write lane.
            ordinary = pool.submit(controller.set_excluded, "Other", True)
            assert ordinary.result(2)["persisted"]
            assert controller.state()["operation"]["action"] == "rename"
        finally:
            proceed.set()
        assert named.result(5)["persisted"]
    assert controller.state()["excluded"] == ["Other"]


@pytest.mark.parametrize(
    "name", [" leading ", "line\nbreak", "constructor", "__proto__"]
)
def test_exclusions_keep_legacy_name_acceptance_and_boolean_conversion(tmp_path, name):
    controller, _, path, _, _ = setup_controller(tmp_path)
    assert controller.set_excluded(name, "yes")["persisted"]
    assert settings.load(path)["preview"]["excluded"] == [name]
    assert controller.set_excluded(name, 0)["persisted"]
    assert settings.load(path)["preview"]["excluded"] == []


def test_save_empty_and_duplicate_id_refuse_without_replacing_records(tmp_path):
    controller, _, path, _, _ = setup_controller(tmp_path)
    before = path.read_bytes()
    assert not controller.save_current("Empty")["persisted"]
    assert path.read_bytes() == before
    controller.set_excluded("Pilot", True)
    assert controller.save_current("First")["persisted"]
    before = path.read_bytes()
    assert not controller.save_current("Second")["persisted"]
    assert path.read_bytes() == before


def test_metadata_can_share_drag_lease_but_capture_refuses_and_retry_is_possible(
    tmp_path,
):
    saved = record()
    controller, _, _, gate, _ = setup_controller(tmp_path, records=(saved,))
    drag = gate.try_begin(exclusive=False)
    assert not controller.state()["availability"]["capture"]
    assert controller.state()["availability"]["edit"]
    assert not controller.save_current("New")["applied"]
    assert controller.rename(saved.id, model.record_revision(saved), "Renamed")[
        "applied"
    ]
    gate.finish(drag)
    assert controller.save_current("New")["applied"]
