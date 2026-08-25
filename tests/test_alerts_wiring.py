"""Wiring, with the alert service faked. What must hold: reconcile() runs
from every one of the five places that can change AlertService._wanted()'s
answer, set_alert_event refuses what settings.validated_alerts would
silently drop anyway, and a test alert never persists.

make_api is the existing helper in tests/test_api.py -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api().
"""

from obs_youtube_uploader.alerts import service as alert_service
from tests.test_api import make_api


class FakeAlerts:
    """Enough of AlertService for the bridge: counts what Api asks of it,
    the same spirit as test_preview_wiring.FakeHost."""

    def __init__(self):
        self.reconciled = 0
        self.stopped = 0
        self._health = alert_service.Health(
            running=False, last_poll=None, last_error=None, characters=()
        )

    def reconcile(self):
        self.reconciled += 1

    def stop(self):
        self.stopped += 1

    def health(self):
        return self._health


class FakePreviewHost:
    """Enough of PreviewHost for these tests: is_running, characters(),
    raise_alert(), and the lifecycle calls the preview bridge methods make
    regardless of whether alerts are involved."""

    def __init__(self, characters=()):
        self._characters = list(characters)
        self.raised = []
        self.started = self.stopped = 0
        self.hotkeys = None

    def start(self):
        self.started += 1

    def stop(self, timeout=5.0):
        self.stopped += 1

    def set_hotkeys(self, table):
        self.hotkeys = table

    def characters(self):
        return list(self._characters)

    def raise_alert(self, character, event, spec):
        self.raised.append((character, event, dict(spec)))

    @property
    def is_running(self):
        return self.started > self.stopped


def _alerts_section(**over):
    section = {
        "enabled": True,
        "pve_filter": True,
        "persist_until_selected": True,
        "events": {
            "combat": {
                "enabled": True,
                "cooldown_s": 1,
                "duration_ms": 1200,
                "pulses": 3,
                "color": "#ff4d4d",
                "sound": "chime",
            },
            "warp_scramble": {
                "enabled": True,
                "cooldown_s": 8,
                "duration_ms": 1200,
                "pulses": 3,
                "color": "#ffd24d",
                "sound": "bell",
            },
            "decloak": {
                "enabled": True,
                "cooldown_s": 8,
                "duration_ms": 1200,
                "pulses": 3,
                "color": "#4dd2ff",
                "sound": "chime",
            },
        },
    }
    section.update(over)
    return section


# ---- reconcile() fires from all five places --------------------------------


def test_changing_the_gamelogs_folder_repoints_the_tailer(tmp_path):
    """set_folder's gamelogs branch drives no watcher of its own, and the
    docstring above it records exactly what that costs: a folder that
    persisted while the window looked healthy and nothing ever polled."""
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)

    result = api.set_folder("gamelogs", str(tmp_path))

    assert result["applied"]
    assert alerts.reconciled == 1


def test_turning_previews_off_stops_the_tailer(tmp_path):
    """Otherwise it keeps polling and winsound keeps firing with nothing
    on screen to explain it."""
    alerts = FakeAlerts()
    host = FakePreviewHost()
    api = make_api(tmp_path, alerts=alerts, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}

    api.set_preview_enabled(False)

    assert alerts.reconciled == 1


def test_alerts_off_means_no_thread_even_with_previews_on(tmp_path):
    """set_alert_enabled is the flag AlertService._wanted() reads for
    "alerts enabled". Turning it off must reconcile even with previews
    staying on -- gating that call on previews' own state instead would
    leave the thread running with no way for this endpoint to stop it."""
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)
    api._state.settings["preview"] = {"enabled": True, "alerts": _alerts_section()}

    result = api.set_alert_enabled(False)

    assert result["applied"]
    assert alerts.reconciled == 1


def test_start_and_shutdown_also_reconcile(tmp_path):
    """The remaining two of the five: launch, and the final teardown.

    Both run whether or not self._preview_host exists -- the alerts flag
    and the gamelogs folder are settings, not a property of the host
    object, so a Windows-only preview subsystem failing to construct must
    not silently disable alerts wiring too.
    """
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts, preview_host=None)
    api._state.settings["preview"] = {"enabled": True, "alerts": _alerts_section()}

    api.start_previews_if_enabled()
    assert alerts.reconciled == 1

    api.shutdown_previews()
    assert alerts.reconciled == 2


def test_a_no_op_preview_toggle_does_not_reconcile(tmp_path):
    """set_preview_enabled returns early when the requested value already
    matches the stored one, so it never reaches the write or reconcile()
    at all -- set_folder owns the folder-changed case instead, which is
    why a no-op toggle reconciling nothing is correct, not a gap."""
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)
    api._state.settings["preview"] = {"enabled": True}

    api.set_preview_enabled(True)

    assert alerts.reconciled == 0  # no-op path never reaches the write


def test_set_preview_enabled_true_actually_starts_the_tailer(tmp_path):
    """Regression for the ordering the is_running gate depends on.

    reconcile() must run AFTER preview_host.start(), not before: while
    FakeAlerts only counts calls, this uses the real AlertService (wired
    the same way build_alert_service does) against a FakePreviewHost whose
    is_running reflects real start()/stop() counts -- if reconcile() were
    called too early, is_running would still read False, folder() would
    return None, and the gate would stay permanently closed.
    """
    from obs_youtube_uploader.__main__ import build_alert_service

    host = FakePreviewHost()
    api = make_api(tmp_path, preview_host=host)
    api._alerts = build_alert_service(api._state, host)
    api._state.settings["preview"] = {"enabled": False, "alerts": _alerts_section()}
    api._state.settings["gamelogs_dir"] = str(tmp_path)

    try:
        api.set_preview_enabled(True)
        assert host.is_running
        assert api._alerts.health().running
    finally:
        api._alerts.stop()


def test_start_previews_if_enabled_actually_starts_the_tailer(tmp_path):
    """The launch-path sibling of the test above.

    start_previews_if_enabled (not set_preview_enabled) is what runs on
    every app launch. If reconcile() there were ever reordered ahead of
    host.start(), alerts would never start on launch -- only once the user
    toggled the previews checkbox by hand -- and the failure would be
    silent, with the settings all reading correct. Same real AlertService,
    same live-is_running FakePreviewHost as the sibling test.
    """
    from obs_youtube_uploader.__main__ import build_alert_service

    host = FakePreviewHost()
    api = make_api(tmp_path, preview_host=host)
    api._alerts = build_alert_service(api._state, host)
    api._state.settings["preview"] = {"enabled": True, "alerts": _alerts_section()}
    api._state.settings["gamelogs_dir"] = str(tmp_path)

    try:
        api.start_previews_if_enabled()
        assert host.is_running
        assert api._alerts.health().running
    finally:
        api._alerts.stop()


def test_alert_config_tolerates_a_settings_document_with_no_preview_key(tmp_path):
    """build_alert_service's config callable used to index straight
    through settings["preview"]["alerts"], which raises KeyError on any
    settings document that predates the alerts section (an older
    settings.json, or -- as here -- tests/test_api.make_state's own
    partial dict, which settings._normalize's own docstring calls out by
    name). Only visible where AlertService is actually built: host is
    None off Windows (build_alert_service's docstring), so the crash was
    Windows-only in practice and slipped past ubuntu-latest CI entirely.
    Must behave like AlertService._resolved_folder's `cfg = self._config()
    or {}` and settings._normalize's setdefault -- absence is an empty
    section, not an error.
    """
    from obs_youtube_uploader.__main__ import build_alert_service

    host = FakePreviewHost()
    api = make_api(tmp_path, preview_host=host)
    assert "preview" not in api._state.settings

    service = build_alert_service(api._state, host)

    assert service is not None
    assert service._config() == {}
    assert service.health().running is False


# ---- a test alert is never persistent --------------------------------------


def test_a_test_alert_is_never_persistent(tmp_path):
    """The user is looking at Wingman, so no preview is selected and
    nothing would acknowledge it -- it would pulse until they alt-tabbed
    to that client."""
    host = FakePreviewHost(characters=["Alice"])
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"]
    assert result["persisted"] is False
    expected_spec = dict(_alerts_section()["events"]["combat"])
    expected_spec["persist_until_selected"] = False
    assert host.raised == [("Alice", "combat", expected_spec)]


def test_a_test_alert_refuses_an_unknown_event(tmp_path):
    api = make_api(tmp_path, preview_host=FakePreviewHost())

    result = api.test_alert("not-a-real-event")

    assert not result["applied"]
    assert result["error"]


def test_a_test_alert_plays_the_sound_once_per_preview_count(monkeypatch, tmp_path):
    """N previews ringing must not mean N overlapping sounds -- _handle
    plays one sound per dispatched event, and Test must match that."""
    played = []
    monkeypatch.setattr(alert_service, "play_sound", played.append)
    host = FakePreviewHost(characters=["Alice", "Bob", "Carol"])
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    api.test_alert("combat")

    assert played == ["chime"]
    assert len(host.raised) == 3


def test_a_test_alert_with_no_live_preview_still_plays_the_sound(monkeypatch, tmp_path):
    """Nothing was refused -- the sound genuinely fired -- so this is
    applied: True with a plain-language explanation, never a silent
    no-op and never applied: False."""
    played = []
    monkeypatch.setattr(alert_service, "play_sound", played.append)
    api = make_api(tmp_path)  # preview_host defaults to None
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"] is True
    assert result["persisted"] is False
    assert result["error"] == "Previews are off, so only the sound played."
    assert played == ["chime"]


def test_a_test_alert_with_no_named_clients_still_plays_the_sound(
    monkeypatch, tmp_path
):
    """Previews being on with no client open is a different situation from
    previews being off, and the copy has to say which -- otherwise a user
    with a live host and no logged-in character reads the same "previews
    are off" message as someone who never turned previews on at all."""
    played = []
    monkeypatch.setattr(alert_service, "play_sound", played.append)
    host = FakePreviewHost(characters=[])  # host present, nothing named
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"] is True
    assert result["error"] == "No EVE clients are open, so only the sound played."
    assert played == ["chime"]
    assert host.raised == []


# ---- set_alert_event refuses what it does not own --------------------------


def test_set_alert_event_refuses_an_unknown_event(tmp_path):
    api = make_api(tmp_path)

    result = api.set_alert_event("not-a-real-event", "cooldown_s", 5)

    assert not result["applied"]
    assert result["error"]


def test_set_alert_event_refuses_an_unknown_field(tmp_path):
    api = make_api(tmp_path)

    result = api.set_alert_event("combat", "not-a-real-field", 5)

    assert not result["applied"]
    assert result["error"]


def test_set_alert_event_lets_settings_clamp_the_value(tmp_path):
    """settings.validated_alerts owns the ranges, not this endpoint: the
    raw value is written and update()'s normalise pass clamps it."""
    api = make_api(tmp_path)

    result = api.set_alert_event("combat", "cooldown_s", 999)

    assert result["applied"]
    clamped = api._state.settings["preview"]["alerts"]["events"]["combat"]["cooldown_s"]
    assert clamped == 120  # settings._validated_alert_event's own ceiling


def test_set_alert_event_does_not_reconcile(tmp_path):
    """A per-event field is read live by the poll thread through the
    config callable on its next tick -- it cannot change whether the
    thread itself should be running, so this is not one of the five."""
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)

    api.set_alert_event("combat", "cooldown_s", 5)

    assert alerts.reconciled == 0


# ---- the remaining bridge methods -------------------------------------------


def test_set_alert_pve_filter_persists_and_does_not_reconcile(tmp_path):
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)

    result = api.set_alert_pve_filter(False)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["preview"]["alerts"]["pve_filter"] is False
    assert alerts.reconciled == 0


def test_set_alert_persist_persists_and_does_not_reconcile(tmp_path):
    alerts = FakeAlerts()
    api = make_api(tmp_path, alerts=alerts)

    result = api.set_alert_persist(False)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["preview"]["alerts"]["persist_until_selected"] is False
    assert alerts.reconciled == 0


def test_get_alert_state_reports_the_service_health(tmp_path):
    alerts = FakeAlerts()
    alerts._health = alert_service.Health(
        running=True, last_poll=1.0, last_error="boom", characters=("Alice",)
    )
    api = make_api(tmp_path, alerts=alerts)
    api._state.settings["preview"] = {"enabled": True, "alerts": _alerts_section()}
    api._state.settings["gamelogs_dir"] = str(tmp_path)

    state = api.get_alert_state()

    assert state["previews_enabled"] is True
    assert state["running"] is True
    assert state["last_error"] == "boom"
    assert state["characters"] == ["Alice"]
    assert state["gamelogs_folder"] == str(tmp_path)
    assert state["alerts"]["enabled"] is True


def test_get_alert_state_tolerates_no_alert_service(tmp_path):
    api = make_api(tmp_path)  # alerts defaults to None

    state = api.get_alert_state()

    assert state["running"] is False
    assert state["last_error"] is None
    assert state["characters"] == []


def test_get_alert_state_hides_a_gamelogs_folder_that_no_longer_exists(tmp_path):
    """set_folder validates is_dir() at write time, so the exposure this
    guards is a folder that was valid and stopped being one -- an
    unmounted drive, an unlinked OneDrive folder, a settings.json carried
    from another machine. Without this check the card would show
    'Watching gamelogs' with the no-folder banner hidden, exactly the
    'believes alerts are armed when nothing is watching' failure the
    feature exists to prevent. Mirrors AlertService._wanted's own is_dir()
    check in service.py."""
    missing = tmp_path / "gone"
    api = make_api(tmp_path)
    api._state.settings["gamelogs_dir"] = str(missing)

    state = api.get_alert_state()

    assert state["gamelogs_folder"] is None


# ---- The Alerts card itself -------------------------------------------------
#
# No JS test harness exists (test_preview_wiring.py's comment above
# test_an_absent_registration_entry_is_its_own_state explains why), so these
# assert on source text like that file does. That is a real limit: they pin
# the mechanism, not the rendered result.


def _web(name):
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    return (root / "obs_youtube_uploader" / "web" / name).read_text(encoding="utf-8")


def test_the_alerts_card_is_a_third_card_in_the_previews_section():
    """After the second card, not inside the first: splitting the first
    card's HTML on '<section' (test_preview_wiring.py's own technique for
    the position checkbox) would otherwise pick up whatever came next."""
    html = _web("index.html")
    route = html.split('id="section-previews"')[1].split('id="section-')[0]
    assert "<h2>Alerts</h2>" in route
    first_card = route.split("EVE client previews")[1].split("<section")[0]
    assert "Alerts" not in first_card
    second_card = route.split("Global keybinds")[1].split("<section")[0]
    assert "Alerts" not in second_card


def test_the_alerts_script_is_loaded():
    html = _web("index.html")
    assert '<script src="alerts.js"></script>' in html


def test_previews_off_state_is_reachable():
    """Alerts cannot draw with no preview to pulse. Named, not merely
    styled, so a rename of the mechanism breaks this loudly."""
    js = _web("alerts.js")
    assert "alerts-previews-off" in js
    assert "previews_enabled" in js


def test_no_gamelogs_folder_state_is_reachable():
    """The important one: without a folder, alerts silently do nothing,
    indistinguishable from nothing happening in game."""
    js = _web("alerts.js")
    assert "alerts-no-folder" in js
    assert "gamelogs_folder" in js
    html = _web("index.html")
    assert "Gamelogs folder is not set" in html


def test_health_and_character_count_render_together():
    """A count with no liveness beside it keeps reading "watching N
    characters" after the tailer thread has died -- get_alert_state's
    `running` flag must appear in the same rendered sentence as the
    character count, never the count alone."""
    js = _web("alerts.js")
    block = js.split("function healthText")[1].split("\n\n")[0]
    assert "state.running" in block
    assert "characters" in block


def test_a_failed_alert_write_says_it_will_not_survive_a_restart():
    """Mirrors test_the_position_toggle_says_when_the_choice_will_not_
    survive in test_preview_wiring.py -- a failed write must say so
    rather than silently reverting a checkbox that really did change for
    this session."""
    js = _web("alerts.js")
    block = js.split("function writeFlag")[1]
    assert "res.persisted" in block, "the flag is returned but never read"
    assert "will not survive a restart" in block
    assert "if (!res || !res.applied)" in block.split("box.checked = !wanted")[0]


def test_a_rolled_back_alert_write_reverts_the_checkbox():
    """api.py's _write_alert_setting reports a raise-and-rollback as
    `applied: false`, not `applied: true, persisted: false` -- the value
    genuinely never took effect this session either, so the checkbox
    must revert instead of being left showing a state the app is not
    in. Only a bridge failure (`res` itself null) used to be checked
    here."""
    js = _web("alerts.js")
    block = js.split("function writeFlag")[1]
    guard = block.split("box.checked = !wanted")[0]
    assert "res.applied" in guard
    assert "res.error" in block.split("box.checked = !wanted")[1].split("return")[0]


def test_get_alert_state_is_a_read_not_a_push():
    """Constraint from the brief: a new push handler is a two-file edit
    (WM.HANDLERS in app.js and a WM.handle registration) that
    tests/test_bridge_contract.py checks agree -- this card must not add
    one."""
    js = _web("alerts.js")
    assert "WM.handle(" not in js
    app_js = _web("app.js")
    assert "onAlert" not in app_js


def test_dev_harness_can_render_the_alerts_card():
    """dev.js's settingsPayload had no `preview` key at all and there was
    no get_alert_state stub -- without both, the card renders blank under
    ?dev=1 regardless of whether the real wiring is correct."""
    dev_js = _web("dev.js")
    assert "get_alert_state" in dev_js
    assert "preview:" in dev_js.split("function settingsPayload")[1].split("\n\n")[0]


def test_the_card_refreshes_when_previews_are_toggled_without_navigating():
    """#preview-enabled and this card share ONE section (#section-previews)
    with no navigation between them, so refresh() firing only on wm:section
    and after set_alert_enabled left the card stale the moment previews
    were toggled off: the backend really did stop the poll thread, but the
    card kept showing 'Watching gamelogs' with the previews-off banner
    hidden, indefinitely. settings.js dispatches a custom event once its
    own set_preview_enabled call settles (not on the raw DOM change, so
    this cannot race ahead of host.stop()/alerts.reconcile()); alerts.js
    must listen for it."""
    settings_js = _web("settings.js")
    preview_block = settings_js.split("EVE client previews")[1].split(
        "// ---- Where a preview opens"
    )[0]
    assert "wm:preview-enabled-changed" in preview_block

    js = _web("alerts.js")
    assert "wm:preview-enabled-changed" in js
    assert "refresh" in js.split("wm:preview-enabled-changed")[1][:80]
