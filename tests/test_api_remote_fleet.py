"""Remote rows enter only the display merge, using the existing presentation owner."""

import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from tests.test_api import make_api
from tests.test_fleet_bar import PAGE_A, PAGE_CALLBACKS, FleetWindow, _set_resizable_bar
from tests.test_fleet_bar import (
    _headless_fleet_window_helpers as _headless_fleet_window_helpers,
)
from tests.test_remote_fleet_store import row
from wingman import settings
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
from wingman.fleetsharing.worker import RemoteEvent
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth


def setup(tmp_path):
    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    with api._fleetbar_lifecycle_lock:
        api._publish_fleet_page_locked(FleetWindow(), PAGE_A)
    mono = [100.0]
    api._fleet_clock = lambda: mono[0]
    api._fleet_worker._clock = api._fleet_clock
    return api, mono


def remote(
    api,
    order=1,
    *,
    rows=None,
    receipt=100,
    elapsed=0,
    epoch=1,
    identity=1,
    binding="a",
    kind="replace",
):
    event = RemoteEvent(
        (row(),) if rows is None else rows,
        receipt,
        elapsed,
        epoch,
        identity,
        kind,
        order,
        binding,
    )
    assert hasattr(api, "_receive_remote_fleet_snapshot"), (
        "remote stream has no display ingress"
    )
    api._receive_remote_fleet_snapshot(event)
    return event


def catalogue(
    api, order=2, *, chars=((1, "Local"),), revision=9, epoch=1, identity=1, binding="a"
):
    from wingman.fleetsharing.worker import CatalogueEvent

    event = CatalogueEvent(
        FleetCatalogue(revision, tuple(CatalogueCharacter(*c) for c in chars)),
        binding,
        epoch,
        identity,
        order,
    )
    api._receive_fleet_catalogue(event)
    return event


def test_remote_only_without_telemetry_hydrates_and_ages_on_existing_owner(tmp_path):
    api, mono = setup(tmp_path)
    remote(api)
    live = api.fleet_bar_snapshot(PAGE_A)
    assert live["rows"] == [
        {
            "character": "Remote",
            "outgoing_dps": 10,
            "incoming_dps": None,
            "ewar": ["SCRAM/POINT"],
            "log_status": None,
            "remote": True,
            "state": "live",
        }
    ]
    assert live["running_count"] == 0 and live["stream_health"]["state"] == "stopped"
    api._fleet_worker.iterate_once()
    pushes = len(api._fleetbar_window.calls)
    mono[0] = 102.9
    api._fleet_worker.iterate_once()
    assert len(api._fleetbar_window.calls) == pushes
    mono[0] = 103
    api._fleet_worker.iterate_once()
    stale = api.fleet_bar_snapshot(PAGE_A)
    assert stale["rows"][0]["state"] == "stale"
    assert stale["revision"] > live["revision"]
    assert len(api._fleetbar_window.calls) == pushes + 1
    mono[0] = 110
    api._fleet_worker.iterate_once()
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []
    assert len(api._fleetbar_window.calls) == pushes + 2
    assert api._state.settings["fleet_bar"]["seen"] == []
    assert api._fleet_roster.pending == {}
    assert api.fleet_bar_settings()["characters"] == []
    assert api._window.evaluated == []  # timers do not dirty local Settings


def test_directional_local_and_remote_rows_keep_local_order_and_health(tmp_path):
    api, _ = setup(tmp_path)
    api._install_fleet_generation(1)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            (
                FleetRow("Zulu", 12, incoming_dps=80),
                FleetRow("Alpha", 0, incoming_dps=90),
            ),
            StreamHealth("stale", "Local log stale"),
            activation_generation=1,
        )
    )
    remote(
        api,
        rows=(
            row(character_id=20, character_name="Remote Z"),
            row(character_id=10, character_name="Remote A"),
        ),
    )
    payload = api.fleet_bar_snapshot(PAGE_A)
    assert [r["character"] for r in payload["rows"]] == [
        "Zulu",
        "Alpha",
        "Remote A",
        "Remote Z",
    ]
    assert [(r["outgoing_dps"], r["incoming_dps"]) for r in payload["rows"]] == [
        (12, 80),
        (0, 90),
        (10, None),
        (10, None),
    ]
    assert all("dps" not in r for r in payload["rows"])
    assert all(r["log_status"] is None for r in payload["rows"][2:])
    assert payload["running_count"] == 2
    assert payload["stream_health"] == {"state": "stale", "detail": "Local log stale"}


@pytest.mark.parametrize("method,args", PAGE_CALLBACKS)
def test_remote_events_do_not_change_creation_callback_admission(
    tmp_path, monkeypatch, method, args
):
    from wingman.ui import fleetbar

    api, mono = setup(tmp_path)
    api._fleet_worker.start = lambda: True
    urls = []

    def create_window(title, url, **kwargs):
        urls.append(url)
        bar = FleetWindow(
            width=kwargs["width"],
            height=kwargs["height"],
            x=kwargs["x"],
            y=kwargs["y"],
        )
        bar.hidden = True
        return bar

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sigbar_mod, "_apply_tool_style", lambda bar: None)
    first = fleetbar.create(api)
    token = urls[-1].partition("#fleet-page=")[2]
    assert token == api._fleetbar_page_id and len(token) == 64
    event = remote(api)
    assert api.fleet_bar_snapshot(token)["rows"][0]["incoming_dps"] is None
    assert api.toggle_fleet_bar(False)["applied"]
    mono[0] = 103
    remote(api, 2, receipt=103, rows=(row(age_ms=3000),))
    assert api._fleetbar_page_id == token
    assert api.fleet_bar_snapshot(token)["rows"] == []
    api.fleet_bar_ready(token)
    assert api._fleetbar_ready and first.hidden
    api.save_fleet_bar_pos(token, 25, -40)
    api.fit_fleet_bar_height(token, 112)
    assert first.resized == first.moved == []
    assert api.toggle_fleet_bar(True)["applied"]
    assert api._fleetbar_window is first and api._fleetbar_page_id == token
    assert not first.hidden
    assert api.fleet_bar_snapshot(token)["rows"][0]["state"] == "stale"

    first.alive = False
    second = fleetbar.create(api)
    current = urls[-1].partition("#fleet-page=")[2]
    assert current != token
    remote(api, 3, receipt=103, rows=(row(age_ms=3000),))
    catalogue(api, 4)
    before = dict(api._state.settings["fleet_bar"])
    call = getattr(api, method)
    assert call(*args) is None  # old tokenless callers are not admitted
    assert call(token, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert second.resized == second.moved == []
    assert second.hidden and not api._fleetbar_ready
    result = call(current, *args)
    if method == "fleet_bar_snapshot":
        assert result["rows"][0]["state"] == "stale"
    elif method == "fit_fleet_bar_height":
        assert second.resized == [(second.width, args[0])]
    elif method == "save_fleet_bar_pos":
        assert (
            api._state.settings["fleet_bar"]["x"],
            api._state.settings["fleet_bar"]["y"],
        ) == args
    else:
        assert not second.hidden and api._fleetbar_ready
    api.shutdown_previews()
    assert api._fleetbar_page_id is None and not api._fleetbar_ready
    assert api._fleetbar_window is second  # native shutdown still owns its target
    before = dict(api._state.settings["fleet_bar"])
    api._receive_remote_fleet_snapshot(event)
    remote(api, 99, receipt=103)
    catalogue(api, 100)
    assert api._remote_fleet.current(103) == ()
    assert api._fleet_catalogue is None
    assert call(current, *args) is None
    assert api._state.settings["fleet_bar"] == before


@pytest.mark.parametrize("dps", [None, 0, 1])
def test_verified_local_precedes_remote_even_hidden_quiet_or_no_log(tmp_path, dps):
    api, _ = setup(tmp_path)
    api._state.settings["fleet_bar"]["hidden"] = ["Local"]
    api._install_fleet_generation(1)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            (FleetRow("Local", dps),), StreamHealth("active"), activation_generation=1
        )
    )
    remote(api, rows=(row(), row(2, character_id=2, character_name="Other")))
    catalogue(api)
    payload = api.fleet_bar_snapshot(PAGE_A)
    assert [r["character"] for r in payload["rows"]] == ["Other"]
    assert payload["running_count"] == 1
    assert [r["name"] for r in api.fleet_bar_settings()["characters"]] == ["Local"]
    assert not api.set_fleet_bar_character_visible("Other", False)["applied"]


def test_unverified_same_name_and_ambiguous_catalogue_never_deduplicate(tmp_path):
    api, _ = setup(tmp_path)
    api._install_fleet_generation(1)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            (FleetRow("Remote", 0),), StreamHealth("active"), activation_generation=1
        )
    )
    remote(api)
    catalogue(api, chars=((1, "Remote"), (2, "remote")))
    assert len(api.fleet_bar_snapshot(PAGE_A)["rows"]) == 2
    catalogue(api, 3, chars=((1, "Remote"),), revision=1)
    assert len(api.fleet_bar_snapshot(PAGE_A)["rows"]) == 1


def test_independent_stream_order_and_context_transition_retire_old_callbacks(tmp_path):
    api, _ = setup(tmp_path)
    old = remote(api)
    catalogue(api, 5)
    remote(api, 3, rows=(), kind="clear")  # newer catalogue cannot swallow valid clear
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []
    api._receive_remote_fleet_snapshot(old)
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []
    remote(api, 6, binding="b", epoch=2)
    catalogue(api, 4, binding="a", epoch=1)
    assert api._fleet_catalogue is None
    remote(api, 5, binding="a", epoch=1)
    assert api._remote_context == (2, 1, "b")
    remote(api, 7, kind="clear", rows=(), binding="b", epoch=2)
    remote(api, 6, binding="b", epoch=2)
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []


def test_reobservation_without_semantic_change_rearms_but_does_not_repaint(tmp_path):
    api, mono = setup(tmp_path)
    remote(api)
    api._fleet_worker.iterate_once()
    before = len(api._fleetbar_window.calls)
    revision = api.fleet_bar_snapshot(PAGE_A)["revision"]
    mono[0] = 101
    remote(api, 2, rows=(row(age_ms=1000),), receipt=101)
    api._fleet_worker.iterate_once()
    assert api.fleet_bar_snapshot(PAGE_A)["revision"] == revision
    assert len(api._fleetbar_window.calls) == before


def test_payload_freshness_and_revision_use_one_clock_sample(tmp_path):
    api, _ = setup(tmp_path)
    remote(api)
    samples = iter([102.9, 103, 103, 103, 103])
    api._fleet_clock = lambda: next(samples)
    first = api.fleet_bar_snapshot(PAGE_A)
    second = api.fleet_bar_snapshot(PAGE_A)
    assert first["rows"][0]["state"] == "live"
    assert second["rows"][0]["state"] == "stale"
    assert first["revision"] < second["revision"]


def test_deadline_cannot_skip_stale_when_clock_crosses_during_delivery(tmp_path):
    api, _ = setup(tmp_path)
    remote(api)
    api._fleet_worker.iterate_once()
    # No semantic change at the first read. A later clock sample must not
    # silently choose the expiry deadline instead of waking for stale.
    samples = iter([102.999, 103.001, 103.001])
    api._fleet_clock = lambda: next(samples)
    assert api._present_fleet_snapshot() == 103


def test_off_gates_display_not_age_and_shutdown_closes_ingress(tmp_path):
    api, mono = setup(tmp_path)
    remote(api, elapsed=2)
    api._state.settings["fleet_bar"]["enabled"] = False
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []
    mono[0] = 104
    api._state.settings["fleet_bar"]["enabled"] = True
    assert api.fleet_bar_snapshot(PAGE_A)["rows"][0]["state"] == "stale"
    api.shutdown_fleet_sharing()
    remote(api, 5, rows=(row(2),), receipt=104)
    assert api.fleet_bar_snapshot(PAGE_A)["rows"] == []


@pytest.mark.parametrize("transition,age", [("stale", 2.95), ("expired", 9.95)])
def test_actual_owner_wakes_for_deadline_without_telemetry_or_notifications(
    tmp_path, transition, age
):
    api, _ = setup(tmp_path)
    api._fleet_clock = time.monotonic
    api._fleet_worker._clock = time.monotonic
    reached = threading.Event()

    def display(script):
        payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
        if (
            not payload["rows"]
            if transition == "expired"
            else payload["rows"][0]["state"] == "stale"
        ):
            reached.set()

    api._fleetbar_window.evaluate_js = display
    remote(api, receipt=time.monotonic(), elapsed=age)
    # This production startup path must own presentation even with telemetry None.
    api._start_fleet_telemetry_if_enabled()
    try:
        assert reached.wait(2), "no autonomous freshness transition"
    finally:
        assert api._stop_fleet_presentation(5)


@pytest.mark.parametrize("stage", ["save", "main", "fleet"])
def test_stale_hydration_retires_delivery_captured_before_blocking_stage(
    tmp_path, monkeypatch, stage
):
    api, mono = setup(tmp_path)
    api._install_fleet_generation(1)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            (FleetRow("Local", 1),), StreamHealth("active"), activation_generation=1
        )
    )
    remote(api, rows=(row(character_id=2),))
    entered, release = threading.Event(), threading.Event()
    original_save = settings._save_locked
    frames = []

    def block(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        if stage == "save":
            return original_save(*args, **kwargs)
        if stage == "fleet":
            frames.append(
                json.loads(args[0].split("window.onFleetSnapshot(", 1)[1][:-1])
            )
        return None

    if stage == "save":
        monkeypatch.setattr(settings, "_save_locked", block)
    elif stage == "main":
        api._window.evaluate_js = block
    else:
        api._fleetbar_window.evaluate_js = block
    thread = threading.Thread(target=api._fleet_worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        mono[0] = 103
        hydration = api.fleet_bar_snapshot(PAGE_A)
        assert hydration["rows"][-1]["state"] == "stale"
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        api._fleet_worker.iterate_once()
        if stage == "fleet":
            # Entered evaluate_js is not cancellable. Page revision prevents a
            # delayed live script overwriting this newer hydration/next push.
            assert frames[0]["revision"] < hydration["revision"]
            assert frames[-1]["rows"][-1]["state"] == "stale"
        assert api._state.settings["fleet_bar"]["seen"] == ["Local"]
    finally:
        release.set()
        thread.join(5)


@pytest.mark.parametrize(
    "entrypoint", ["_stop_fleet_presentation", "shutdown_previews"]
)
def test_main_presentation_stop_detaches_remote_ingress_before_its_first_join(
    tmp_path, monkeypatch, entrypoint
):
    from tests.test_fleetsharing_worker import rig

    worker, _, _, _ = rig()
    api = make_api(tmp_path, fleet_sharing=worker)
    api._fleet_clock = lambda: 100
    with api._fleetbar_lifecycle_lock:
        api._publish_fleet_page_locked(FleetWindow(), PAGE_A)
    api._fleetbar_ready = True
    remote(api)
    joined = []

    def stop(timeout):
        assert api._fleetbar_page_id is None and not api._fleetbar_ready
        assert not worker._subscribers["remote"]
        assert not worker._subscribers["catalogue"]
        assert api._remote_fleet.current(100) == ()
        joined.append(True)
        return True

    sharing_stop = worker.stop
    sharing_admission = []

    def stop_sharing(timeout):
        # Assertions inside stop() are caught by best-effort teardown; record
        # admission and assert on the test thread after that boundary instead.
        sharing_admission.append((api._fleetbar_page_id, api._fleetbar_ready))
        assert not worker._subscribers["remote"]
        assert not worker._subscribers["catalogue"]
        return sharing_stop(timeout)

    monkeypatch.setattr(worker, "stop", stop_sharing)
    api._fleet_worker.stop = stop
    assert getattr(api, entrypoint)() is not False
    assert joined == [True]
    assert sharing_admission == (
        [(None, False)] if entrypoint == "shutdown_previews" else []
    )
    api.shutdown_fleet_sharing()


def test_real_coordinator_and_publisher_never_persist_or_rebroadcast_remote(tmp_path):
    from tests.test_fleetsharing_worker import drive, rig
    from tests.test_telemetry_coordinator import _harness, _roster, _session
    from wingman import paths

    harness = _harness(tmp_path, fleet=True)
    harness.metrics.rows = (FleetRow("Alice", 10),)
    worker, client, journal, mono = rig()
    api = make_api(tmp_path, telemetry=harness.coordinator, fleet_sharing=worker)
    with api._fleetbar_lifecycle_lock:
        api._publish_fleet_page_locked(FleetWindow(), PAGE_A)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleet_clock = lambda: mono[0]
    # Deterministic presenter; real coordinator dispatcher and subscriptions.
    api._fleet_worker.start = lambda: True
    api._reconcile_fleet_generation(transition=True)
    harness.discovery.publish(_roster(_session("Alice")))
    harness.pump()
    drive(worker, mono, 12)
    try:
        api._fleet_worker.iterate_once()
        assert [r["character"] for r in api.fleet_bar_snapshot(PAGE_A)["rows"]] == [
            "Alice",
            "Bob",
        ]
        assert [r.character for r in harness.coordinator.snapshot().rows] == ["Alice"]
        assert all(
            row.character_id == 1 for _, rows in client.publish_calls for row in rows
        )
        assert client.publish_calls
        assert settings.load(paths.settings_file())["fleet_bar"]["seen"] == ["Alice"]
        assert "Bob" not in repr(journal.saves)
        assert "publication_id" not in paths.settings_file().read_text()
        assert api._fleet_roster.pending == {}
        assert (
            len(worker._subscribers["remote"])
            == len(worker._subscribers["catalogue"])
            == 1
        )
        old_remote = next(iter(worker._subscribers["remote"].values()))
        api.shutdown_fleet_sharing()
        assert (
            not worker._subscribers["remote"] and not worker._subscribers["catalogue"]
        )
        old_remote(RemoteEvent(client.remote, mono[0], 0, 1, 1, "replace", 999, "late"))
        assert all(not r.get("remote") for r in api.fleet_bar_snapshot(PAGE_A)["rows"])
    finally:
        api.shutdown_previews()


def test_remote_events_do_not_change_resize_reset_page_identity(tmp_path):
    api, _ = setup(tmp_path)
    _set_resizable_bar(api)
    before = dict(api._state.settings["fleet_bar"])

    remote(api)

    assert api.fit_fleet_bar_height("b" * 64, 112) is None
    assert api.settle_fleet_bar_resize("b" * 64, 480, 40) is None
    assert api.reset_fleet_bar_page_width("b" * 64) is None
    assert api._state.settings["fleet_bar"] == before
    assert api._fleetbar_window.resized == []
    assert api._fleetbar_window.moved == []

    api.fit_fleet_bar_height(PAGE_A, 112)
    settled = api.settle_fleet_bar_resize(PAGE_A, 480, 40)
    reset = api.reset_fleet_bar_page_width(PAGE_A)

    assert api._fleetbar_window.resized == [(512, 112), (492, 112), (512, 112)]
    assert settled == {"applied": True, "persisted": True, "error": None}
    assert reset == {"applied": True, "persisted": True, "error": None}
