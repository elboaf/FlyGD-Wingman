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


def test_a_no_op_preview_toggle_still_reconciles(tmp_path):
    """set_preview_enabled's early-return no-op path is a settings
    optimisation, not a reason to skip reconcile(): the folder callable
    can still have changed in the meantime via set_folder."""
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
    played = []
    monkeypatch.setattr(alert_service, "play_sound", played.append)
    host = FakePreviewHost(characters=[])  # host present, nothing named
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"] is True
    assert result["error"] == "Previews are off, so only the sound played."
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
