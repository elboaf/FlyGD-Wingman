"""Temporary files through production composition; no native workers or network.

Unlike the focused layer tests, these never synthesize CustomMatch/CombatFact
records or replace parser, matcher, policy or admission. Only the explicit
failure trace interrupts normalization, inside the real matcher.
"""

import datetime
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from tests.test_api import make_state
from tests.test_telemetry_coordinator import FakeDiscovery, _roster, _session
from tests.test_telemetry_gamelogs import (
    HEADER,
    NOW,
    OUTGOING_DAMAGE_LINE,
    SCRAMBLE_LINE,
    _log,
)
from wingman import __main__ as main_mod
from wingman import paths, settings
from wingman.alerts import custom, service
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
from wingman.fleetsharing.projection import project_snapshot
from wingman.preview.host import PENDING_ALERTS_MAX, PreviewHost
from wingman.telemetry import coordinator as coordinator_mod
from wingman.telemetry import gamelogs
from wingman.telemetry.coordinator import TelemetryCoordinator
from wingman.telemetry.gamelogs import MAX_AGE, MAX_FILES, GameLogStream
from wingman.telemetry.metrics import FleetMetrics
from wingman.ui.api import Api

PRIVATE_QUERY = "private-query-7f19"
PRIVATE_LINE = "private-line-c34e"
DAMAGE = OUTGOING_DAMAGE_LINE.replace("11:30:00", "12:00:00")


class NativeHost(PreviewHost):
    """Retain real mailbox/token checks, replacing only native pump lifetime."""

    def start(self):
        self._starting = True
        return True

    def stop(self, timeout=5.0, *, final=False):
        self._starting = False
        self._closing = final
        return True


@pytest.fixture
def live_alerts(tmp_path, monkeypatch, request):
    folder = tmp_path / "gamelogs"
    folder.mkdir()
    characters = ["Alice", "Bob"] + [
        f"Pilot{index:02}" for index in range(2, getattr(request, "param", 2))
    ]
    logs = {
        character: _log(
            folder, character, "fleet invite\n" * 20, stem=f"source-{index:02}"
        )
        for index, character in enumerate(characters)
    }
    # A discovered but unselected path makes known-path replacement distinct
    # from a genuinely new path created after monitoring begins.
    _log(folder, "EVE", stem="known", session="2026.08.25 11:30:00")
    state = make_state(tmp_path, gamelogs_dir=str(folder))
    with settings.update(state.settings) as document:
        document.setdefault("preview", {})["enabled"] = True
        document["preview"].setdefault("alerts", {})["enabled"] = True
        document["fleet_bar"] = {"enabled": True}
    assert settings.load()["preview"]["alerts"]["custom_rules"] == []
    assert not settings.load()["fleet_sharing"]["enabled"]
    box, sounds, visuals, fleet, streams, coordinators = {}, [], [], [], [], []
    host = NativeHost(
        on_layout_changed=lambda *_args: None,
        custom_alert_current=lambda *tokens: box["alerts"].is_current(*tokens),
    )
    host._clients = dict.fromkeys(characters)
    host._windows = {
        character: SimpleNamespace(
            arm_alert=lambda event, spec, now, name=character: visuals.append(
                (name, event, dict(spec))
            )
        )
        for character in characters
    }
    monkeypatch.setattr(service, "play_sound", lambda *args: sounds.append(args))
    controller = main_mod.build_alerts_controller(state, host, box)
    box["alerts"] = controller
    policy = main_mod.build_alert_policy(state, host, controller)
    assert policy is not None

    def build_stream(**kwargs):
        stream = GameLogStream(
            **kwargs,
            _thread_factory=gamelogs._noop_thread_factory,
            _utc_now=lambda: NOW,
        )
        streams.append(stream)
        return stream

    def build_coordinator(**kwargs):
        runtime = TelemetryCoordinator(
            **kwargs,
            _thread_factory=coordinator_mod._noop_thread_factory,
            _clock=lambda: 0,
        )
        coordinators.append(runtime)
        return runtime

    # Enter the Windows composition branch, not the app or any Win32 binding.
    with monkeypatch.context() as composition:
        composition.setattr(main_mod.sys, "platform", "win32")
        composition.setattr("wingman.telemetry.clients.ClientDiscovery", FakeDiscovery)
        composition.setattr(gamelogs, "GameLogStream", build_stream)
        composition.setattr(coordinator_mod, "TelemetryCoordinator", build_coordinator)
        composition.setattr(
            "wingman.telemetry.metrics.FleetMetrics",
            lambda: FleetMetrics(_clock=lambda: 0, _utc_now=lambda: NOW),
        )
        coordinator = main_mod.build_telemetry(state, host, policy, controller)
    assert coordinator is not None
    api = Api(
        state, preview_host=host, alerts_controller=controller, telemetry=coordinator
    )
    box["api"] = api
    api._fleet_worker._thread_factory = coordinator_mod._noop_thread_factory
    coordinator.subscribe_fleet(fleet.append)
    stream = coordinator._stream
    try:
        api.start_previews_if_enabled()
        stream.scan_once(NOW)
        coordinator._discovery.publish(
            _roster(
                *(
                    _session(name, hwnd=i + 1, pid=i + 100)
                    for i, name in enumerate(characters)
                )
            )
        )
        coordinator.dispatch_once(0)
        assert api.get_custom_alert_state()["matcher"]["state"] == "inactive"
        assert sounds == visuals == []
        yield SimpleNamespace(
            api=api,
            stream=stream,
            coordinator=coordinator,
            sounds=sounds,
            alice_log=logs["Alice"],
            now_utc=NOW,
            host=host,
            visuals=visuals,
            fleet=fleet,
            folder=folder,
            logs=logs,
        )
    finally:
        api.shutdown_previews()
        assert coordinator.stop()
        assert stream.stop()
        assert streams == [stream] and coordinators == [coordinator]
        assert not settings.load()["fleet_sharing"]["enabled"]


def _add_rule(r, search="fleet invite", **style):
    added = r.api.add_custom_alert()
    assert added["applied"] and added["persisted"]
    rule_id = added["rule_id"]
    rule = next(row for row in added["state"]["rules"] if row["id"] == rule_id)
    assert rule["search"] == "" and rule["enabled"] is False
    draft = dict(rule)
    draft.pop("id")
    draft.update(search=search, enabled=True, sound="sly", cooldown_s=0)
    draft.update(style)
    assert r.api.edit_custom_alert(rule_id, draft)["applied"]
    return rule_id, draft


def _append(path, text):
    with path.open("a", encoding="utf-8") as output:
        output.write(text)


def _dispatch(r):
    r.coordinator.dispatch_once(0)
    r.host._apply_alerts(None, r.host._drain_alerts())


def _scan_dispatch(r):
    r.stream.scan_once(r.now_utc)
    _dispatch(r)


def _assert_private(r, caplog):
    # Local and outbound projections are computed without starting the sharing
    # worker or supplying any credentials/relay. Authority remains local only.
    catalogue = FleetCatalogue(
        1,
        tuple(CatalogueCharacter(index + 1, name) for index, name in enumerate(r.logs)),
    )
    eligible = frozenset(character.character_id for character in catalogue.characters)
    output = repr(r.fleet) + repr(
        [
            project_snapshot(frame, catalogue, eligible_character_ids=eligible)
            for frame in r.fleet
        ]
    )
    output += repr(r.visuals) + caplog.text + repr(r.stream.custom_health())
    output += repr(tuple(r.coordinator._queue.queue))
    output += repr(r.coordinator._custom_pending) + repr(r.stream._pending_custom)
    output += repr(r.stream._dispatch_queue)
    assert PRIVATE_QUERY not in output
    assert PRIVATE_LINE not in output


def test_marked_broadcast_matches_each_listener_but_only_owner_gets_builtin(
    live_alerts,
):
    r = live_alerts
    added = r.api.add_custom_alert()
    assert not r.api.set_custom_alert_enabled(added["rule_id"], True)["applied"]
    first = dict(added["state"]["rules"][0])
    first.pop("id")
    first.update(search="warp scramble attempt", enabled=True, sound="sly")
    assert r.api.edit_custom_alert(added["rule_id"], first)["applied"]
    second_id, _ = _add_rule(r, "Carol Vex")
    line = SCRAMBLE_LINE.format(target="Alice").replace("11:30:05", "12:00:00")
    for path in r.logs.values():
        _append(path, line)
    _scan_dispatch(r)
    assert [(name, kind) for name, kind, _ in r.visuals if kind != "custom"] == [
        ("Alice", "warp_scramble")
    ]
    assert {
        (name, spec["custom_rule_id"])
        for name, kind, spec in r.visuals
        if kind == "custom"
    } == {
        (name, rule_id)
        for name in ("Alice", "Bob")
        for rule_id in (added["rule_id"], second_id)
    }
    assert len(r.visuals) == 5
    assert r.sounds == [("obey", 100)]
    assert {row.character: row.ewar for row in r.fleet[-1].rows} == {
        "Alice": ("SCRAM",),
        "Bob": (),
    }
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "active"


def test_removal_invalidates_an_already_admitted_match(live_alerts):
    r = live_alerts
    rule_id, _ = _add_rule(r)
    _append(r.alice_log, "(notify) fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    assert r.api.remove_custom_alert(rule_id)["applied"]
    _dispatch(r)
    assert r.sounds == r.visuals == []


@pytest.mark.parametrize("boundary", ["coordinator", "native"])
@pytest.mark.parametrize("mutation", ["edit", "clear", "remove"])
def test_queued_generation_cannot_arm_after_committed_change(
    live_alerts, boundary, mutation
):
    r = live_alerts
    rule_id, draft = _add_rule(r)
    _append(r.alice_log, "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    if boundary == "native":
        r.coordinator.dispatch_once(0)
        assert r.host._pending_alerts
        assert r.sounds == [("sly", 100)]  # Already begun sound is not retractable.
        r.sounds.clear()
    if mutation == "remove":
        assert r.api.remove_custom_alert(rule_id)["applied"]
    else:
        result = r.api.edit_custom_alert(
            rule_id, dict(draft, search="changed invite" if mutation == "edit" else "")
        )
        assert result["applied"]
        if mutation == "clear":
            assert result["state"]["rules"][0]["enabled"] is False
    _dispatch(r)
    assert r.sounds == r.visuals == []
    _append(r.alice_log, "fleet invite\nchanged invite\n")
    _scan_dispatch(r)
    assert r.sounds == ([("sly", 100)] if mutation == "edit" else [])
    assert len(r.visuals) == (1 if mutation == "edit" else 0)


@pytest.mark.parametrize("refuse", [False, True], ids=["commit", "rollback"])
def test_blocked_save_keeps_prior_matcher_and_style_live(
    live_alerts, monkeypatch, refuse
):
    r = live_alerts
    rule_id, draft = _add_rule(r)
    before = r.api._alerts_controller.runtime_snapshot()
    disk = paths.settings_file().read_bytes()
    entered, release = Event(), Event()
    save = settings._save_locked

    def held_save(document, path=None):
        entered.set()
        assert release.wait(5)
        if refuse:
            raise OSError("isolated save refusal")
        save(document, path)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edit = pool.submit(
            r.api.edit_custom_alert,
            rule_id,
            dict(draft, search="changed invite", sound="obey"),
        )
        try:
            assert entered.wait(3)
            _append(r.alice_log, "fleet invite\nchanged invite\n")
            pool.submit(_scan_dispatch, r).result(timeout=2)
            assert r.sounds == [("sly", 100)]
            assert len(r.visuals) == 1
            assert r.api._alerts_controller.runtime_snapshot() is before
            assert paths.settings_file().read_bytes() == disk
        finally:
            release.set()
        result = edit.result(timeout=3)
    assert result["applied"] is not refuse
    assert result["persisted"] is not refuse
    r.sounds.clear()
    r.visuals.clear()
    _append(r.alice_log, "fleet invite\nchanged invite\n")
    _scan_dispatch(r)
    assert r.sounds == [("sly" if refuse else "obey", 100)]
    assert len(r.visuals) == 1
    assert settings.load()["preview"]["alerts"]["custom_rules"][0]["search"] == (
        "fleet invite" if refuse else "changed invite"
    )


@pytest.mark.parametrize("replacement", ["truncated", "known", "new", "retired"])
def test_source_replacement_rejects_queued_old_match_and_preserves_replay_contract(
    live_alerts, replacement
):
    r = live_alerts
    _add_rule(r)
    # A fresh activation with an executable rule must baseline existing history,
    # not merely skip history because the original startup had no enabled rules.
    assert r.coordinator.stop()
    r.api._reconcile_eve_runtime()
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    _append(r.alice_log, "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    old = next(iter(r.coordinator._custom_pending.values()))
    if replacement == "truncated":
        path = r.alice_log
        path.write_text(
            HEADER.format(name="Alice", session="2026.08.25 11:00:00")
            + "fleet invite\n",
            encoding="utf-8",
        )
    elif replacement == "retired":
        path = r.alice_log
        expired = (NOW - MAX_AGE - datetime.timedelta(minutes=1)).timestamp()
        os.utime(path, (expired, expired))
        r.stream.scan_once(r.now_utc)
        _append(path, "fleet invite\n")
    else:
        path = _log(
            r.folder,
            "Alice",
            "fleet invite\n",
            stem="known" if replacement == "known" else "new",
            session="2026.08.25 11:30:00",
        )
    _scan_dispatch(r)
    assert len(r.visuals) == (1 if replacement == "new" else 0)
    assert r.sounds == ([("sly", 100)] if replacement == "new" else [])
    current = r.coordinator._custom_sources["Alice"]
    assert current.generation > old.source_generation
    r.sounds.clear()
    r.visuals.clear()
    _append(path, "fleet invite\n")
    _scan_dispatch(r)
    assert [(name, kind) for name, kind, _ in r.visuals] == [("Alice", "custom")]
    assert r.sounds == [("sly", 100)]
    r.stream.request_source("Alice")
    _scan_dispatch(r)
    assert len(r.visuals) == len(r.sounds) == 1


def test_partial_line_waits_for_newline_and_does_not_replay(live_alerts):
    r = live_alerts
    _add_rule(r)
    _append(r.alice_log, "[ 2026.08.25 12:00:00 ] (notify) <b>FLEET</b>   INVITE")
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    _append(r.alice_log, "\n")
    _scan_dispatch(r)
    _scan_dispatch(r)
    assert r.sounds == [("sly", 100)]
    assert len(r.visuals) == 1


def test_split_utf8_reaches_custom_presentation_and_fleet_only_after_newline(
    live_alerts,
):
    r = live_alerts
    rule_id, _ = _add_rule(r, "Straße")
    line = DAMAGE.replace("Mara Veld", "Straße").encode("utf-8")
    cut = line.index(b"\xc3\x9f") + 1
    with r.alice_log.open("ab") as output:
        output.write(line[:cut])
    _scan_dispatch(r)
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    assert not r.coordinator._custom_pending
    with r.alice_log.open("ab") as output:
        output.write(line[cut:-1])
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    _append(r.alice_log, "\n")
    _scan_dispatch(r)
    _scan_dispatch(r)
    assert r.sounds == [("sly", 100)]
    assert [(name, kind, spec["custom_rule_id"]) for name, kind, spec in r.visuals] == [
        ("Alice", "custom", rule_id)
    ]
    assert r.fleet[-1].rows[0].dps == 30
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "active"


def test_matcher_failure_is_private_and_fleet_continues_until_real_recovery(
    live_alerts, monkeypatch, caplog
):
    r = live_alerts
    caplog.set_level(logging.DEBUG, logger="wingman")
    rule_id, draft = _add_rule(r, PRIVATE_QUERY)
    normalize = custom.normalize_visible
    broken = True

    def interrupted(text):
        if broken and PRIVATE_LINE in text:
            raise ValueError(PRIVATE_QUERY + " " + text)
        return normalize(text)

    monkeypatch.setattr(custom, "normalize_visible", interrupted)
    _append(r.alice_log, DAMAGE.rstrip() + f" {PRIVATE_QUERY} {PRIVATE_LINE}\n")
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "degraded"
    assert r.api.get_custom_alert_state()["reader"]["running"] is True
    assert r.fleet[-1].rows[0].dps == 30
    _scan_dispatch(r)
    assert r.api.edit_custom_alert(rule_id, dict(draft, name="Renamed"))["applied"]
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "degraded"
    _assert_private(r, caplog)
    broken = False
    _append(r.alice_log, "(notify) unrelated, zero matches\n")
    _scan_dispatch(r)
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "active"
    assert r.sounds == []
    _append(r.alice_log, f"(notify) {PRIVATE_QUERY} {PRIVATE_LINE}\n")
    _scan_dispatch(r)
    assert r.sounds == [("sly", 100)]
    _assert_private(r, caplog)


@pytest.mark.parametrize("master", ["alerts", "preview"])
def test_fleet_only_inactivity_retires_queue_without_second_reader(
    live_alerts, monkeypatch, master
):
    r = live_alerts
    _add_rule(r)
    worker, dispatcher = r.stream._worker, r.coordinator._worker
    epoch = r.coordinator._stream_delivery_epoch
    _append(r.alice_log, "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    toggle = (
        r.api.set_alert_enabled if master == "alerts" else r.api.set_preview_enabled
    )
    result = toggle(False)
    assert result["applied"] if master == "alerts" else result
    calls = []
    normalize = custom.normalize_visible

    def counted(text):
        calls.append(text)
        return normalize(text)

    with monkeypatch.context() as inactive:
        inactive.setattr(custom, "normalize_visible", counted)
        _append(r.alice_log, "fleet invite\n" + DAMAGE)
        _scan_dispatch(r)
    assert calls == []
    assert r.sounds == r.visuals == []
    assert r.api.get_custom_alert_state()["matcher"]["state"] == "inactive"
    assert r.api.get_custom_alert_state()["reader"]["running"] is True
    assert r.fleet[-1].rows[0].dps == 30
    result = toggle(True)
    assert result["applied"] if master == "alerts" else result
    _dispatch(r)
    assert r.sounds == []
    _append(r.alice_log, "fleet invite\n")
    _scan_dispatch(r)
    assert r.sounds == [("sly", 100)]
    assert r.stream._worker is worker and r.coordinator._worker is dispatcher
    assert r.coordinator._stream_delivery_epoch == epoch
    # No dispatch while Off: the retired activation must not become current
    # merely because both masters are back On by the next policy call.
    _append(r.alice_log, "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    for enabled in (False, True):
        result = toggle(enabled)
        assert result["applied"] if master == "alerts" else result
    _dispatch(r)
    assert r.sounds == [("sly", 100)]
    assert len(r.visuals) == 1


@pytest.mark.parametrize("live_alerts", [MAX_FILES], indirect=True)
def test_capacity_and_stalled_drainer_do_not_drop_fleet_or_leak_text(
    live_alerts, caplog
):
    r = live_alerts
    caplog.set_level(logging.DEBUG, logger="wingman")
    for _ in range(custom.MAX_CUSTOM_RULES):
        _add_rule(r, PRIVATE_QUERY)
    cap = MAX_FILES * custom.MAX_CUSTOM_RULES
    entered, release = Event(), Event()

    def hold_first_batch(_batch):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)

    unsubscribe = r.stream.subscribe_batches(hold_first_batch)
    line = DAMAGE + f"(notify) {PRIVATE_QUERY} {PRIVATE_LINE}\n"
    with ThreadPoolExecutor(max_workers=1) as pool:
        for path in r.logs.values():
            _append(path, line)
        scanning = pool.submit(r.stream.scan_once, r.now_utc)
        try:
            assert entered.wait(3)
            for _ in range(2):
                for path in r.logs.values():
                    _append(path, line)
                r.stream.scan_once(r.now_utc)
                assert len(r.stream._pending_custom) == cap
                assert len(r.coordinator._custom_pending) == cap
            _assert_private(r, caplog)
        finally:
            release.set()
        scanning.result(timeout=3)
    unsubscribe()
    assert len(r.coordinator._custom_pending) == cap
    assert (
        sum(
            item is coordinator_mod._CUSTOM_DRAIN for item in r.coordinator._queue.queue
        )
        == 1
    )
    r.coordinator.dispatch_once(0)
    assert len(r.host._pending_alerts) == PENDING_ALERTS_MAX
    r.host._apply_alerts(None, r.host._drain_alerts())
    assert len(r.visuals) == PENDING_ALERTS_MAX
    assert r.sounds == [("sly", 100)]
    assert len(r.fleet[-1].rows) == MAX_FILES
    assert all(row.dps == 90 for row in r.fleet[-1].rows)
    assert r.fleet[-1].metric_error is None
    assert r.coordinator._custom_pending == r.stream._pending_custom == {}
    _assert_private(r, caplog)


@pytest.mark.parametrize("presentation", ["focused", "other-focused", "excluded"])
def test_listener_focus_and_missing_preview_do_not_redirect_custom_ring(
    live_alerts, presentation
):
    r = live_alerts
    _add_rule(r)
    assert r.api.set_alert_volume(23)["applied"]
    r.host._focused_key = "Alice" if presentation == "focused" else "Bob"
    if presentation == "excluded":
        del r.host._windows["Alice"]
    _append(r.alice_log, "fleet invite\n")
    _scan_dispatch(r)
    assert r.sounds == ([] if presentation == "focused" else [("sly", 23)])
    assert [(name, kind) for name, kind, _ in r.visuals] == (
        [] if presentation == "excluded" else [("Alice", "custom")]
    )
    if r.visuals:
        assert r.visuals[0][2]["persist_until_selected"] is (presentation != "focused")


def test_test_presentation_does_not_persist_or_consume_runtime_cooldown(live_alerts):
    r = live_alerts
    rule_id, draft = _add_rule(r, cooldown_s=120)
    disk = paths.settings_file().read_bytes()
    before = r.api._alerts_controller.runtime_snapshot()
    assert r.api.test_custom_alert(rule_id, draft) == {
        "applied": True,
        "persisted": False,
        "error": None,
    }
    r.host._apply_alerts(None, r.host._drain_alerts())
    assert r.sounds == [("sly", 100)]
    assert len(r.visuals) == 2
    assert all(
        not spec["persist_until_selected"] and spec["custom_test"]
        for _, _, spec in r.visuals
    )
    assert paths.settings_file().read_bytes() == disk
    assert r.api._alerts_controller.runtime_snapshot() is before
    _append(r.alice_log, "fleet invite\n")
    _scan_dispatch(r)
    assert r.sounds == [("sly", 100), ("sly", 100)]
    assert len(r.visuals) == 3
    _append(r.alice_log, "fleet invite\n")
    _scan_dispatch(r)
    assert len(r.sounds) == 2 and len(r.visuals) == 3


def test_shutdown_mid_policy_delivery_fences_remaining_native_and_audio_work(
    live_alerts, monkeypatch
):
    r = live_alerts
    _add_rule(r)
    _append(r.alice_log, "fleet invite\n")
    _append(r.logs["Bob"], "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    entered, release = Event(), Event()

    def hold_native_post(_message):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(r.host, "_post", hold_native_post)
    with ThreadPoolExecutor(max_workers=1) as pool:
        dispatch = pool.submit(r.coordinator.dispatch_once, 0)
        try:
            assert entered.wait(3)
            r.api._close_eve_runtime()
            assert not r.coordinator._custom_admission_open
        finally:
            release.set()
        dispatch.result(timeout=3)
    assert len(r.host._pending_alerts) == 1
    r.host._apply_alerts(None, r.host._drain_alerts())
    assert r.sounds == r.visuals == []
    r.api.shutdown_previews()
    assert r.api._reconcile_eve_runtime() is None
    assert not r.stream._started


def test_shutdown_during_pending_edit_cannot_reopen_custom_runtime(
    live_alerts, monkeypatch
):
    r = live_alerts
    rule_id, draft = _add_rule(r)
    _append(r.alice_log, "fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    entered, release = Event(), Event()
    save = settings._save_locked

    def held_save(document, path=None):
        entered.set()
        assert release.wait(5)
        save(document, path)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    with ThreadPoolExecutor(max_workers=1) as pool:
        edit = pool.submit(
            r.api.edit_custom_alert, rule_id, dict(draft, search="changed invite")
        )
        try:
            assert entered.wait(3)
            r.api._close_eve_runtime()
            _dispatch(r)
        finally:
            release.set()
        assert edit.result(timeout=3)["persisted"]
    snapshot = r.api._alerts_controller.runtime_snapshot()
    assert not r.api._alerts_controller.is_current(
        rule_id, snapshot.custom_rules[0].generation, snapshot.activation_epoch
    )
    _append(r.alice_log, "changed invite\n")
    _scan_dispatch(r)
    assert r.sounds == r.visuals == []
    assert not r.api.test_custom_alert(rule_id, draft)["applied"]
    assert (
        json.loads(paths.settings_file().read_text())["preview"]["alerts"][
            "custom_rules"
        ][0]["search"]
        == "changed invite"
    )
