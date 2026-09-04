"""Shared telemetry wiring and alert bridge behavior.

Runtime-affecting settings reconcile the coordinator; policy-only settings do
not. Invalid event fields are refused and test alerts never persist.

make_api is the existing helper in tests/test_api.py -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api().
"""

import re

from tests.test_api import make_api
from wingman.alerts import service as alert_service
from wingman.telemetry.model import StreamHealth


class FakeTelemetry:
    def __init__(self, health=None, characters=()):
        self.reconciled = 0
        self.stopped = 0
        self._health = health or StreamHealth(state="stopped")
        self._characters = tuple(characters)

    def reconcile(self):
        self.reconciled += 1

    def stop(self):
        self.stopped += 1

    def stream_health(self):
        return self._health

    def stream_characters(self):
        return self._characters


class FakePreviewHost:
    """Enough of PreviewHost for these tests: is_running, characters(),
    focused_character(), raise_alert(), and the lifecycle calls the preview
    bridge methods make regardless of whether alerts are involved."""

    def __init__(self, characters=(), focused=None):
        self._characters = list(characters)
        self._focused = focused
        self.raised = []
        self.started = self.stopped = 0
        self.hotkeys = None

    def focused_character(self):
        return self._focused

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
        "volume": 100,
        "events": {
            "combat": {
                "enabled": True,
                "cooldown_s": 1,
                "pulses": 3,
                "flash_rate": "normal",
                "color": "#ff4d4d",
                "sound": "system-fault",
            },
            "warp_scramble": {
                "enabled": True,
                "cooldown_s": 8,
                "pulses": 3,
                "flash_rate": "normal",
                "color": "#ffd24d",
                "sound": "obey",
            },
            "decloak": {
                "enabled": True,
                "cooldown_s": 8,
                "pulses": 3,
                "flash_rate": "normal",
                "color": "#4dd2ff",
                "sound": "system-fault",
            },
        },
    }
    section.update(over)
    return section


# ---- runtime-affecting settings reconcile shared telemetry -----------------


def test_shared_telemetry_reconciles_for_folder_alert_and_preview_changes(tmp_path):
    telemetry = FakeTelemetry()
    host = FakePreviewHost()
    api = make_api(tmp_path, telemetry=telemetry, preview_host=host)
    api._state.settings["preview"] = {"enabled": False, "alerts": _alerts_section()}

    assert api.set_folder("gamelogs", str(tmp_path))["applied"]
    assert api.set_alert_enabled(False)["applied"]
    api.set_preview_enabled(True)

    assert telemetry.reconciled == 3


def test_shared_telemetry_health_drives_alert_state(tmp_path):
    telemetry = FakeTelemetry(
        StreamHealth(state="error", detail="source read failed"),
        characters=("Alice", "Bob"),
    )
    api = make_api(tmp_path, telemetry=telemetry, preview_host=FakePreviewHost())
    api._state.settings["preview"] = {"enabled": True, "alerts": _alerts_section()}
    api._state.settings["gamelogs_dir"] = str(tmp_path)

    state = api.get_alert_state()

    assert state["running"] is False
    assert state["last_error"] == "source read failed"
    assert state["characters"] == ["Alice", "Bob"]


def test_fleet_owned_stream_does_not_make_disabled_alerts_look_armed(tmp_path):
    telemetry = FakeTelemetry(StreamHealth(state="active"), characters=("Alice",))
    api = make_api(tmp_path, telemetry=telemetry)
    api._state.settings["preview"] = {
        "enabled": True,
        "alerts": _alerts_section(enabled=False),
    }

    state = api.get_alert_state()

    assert state["running"] is False
    assert state["characters"] == []


def test_shutdown_stops_shared_telemetry_once(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry, preview_host=FakePreviewHost())

    api.shutdown_previews()

    assert telemetry.stopped == 1


def test_a_no_op_preview_toggle_does_not_reconcile_shared_telemetry(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    api._state.settings["preview"] = {"enabled": True}

    api.set_preview_enabled(True)

    assert telemetry.reconciled == 0


def test_build_telemetry_reads_runtime_settings_live(monkeypatch, tmp_path):
    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    api = make_api(tmp_path)
    api._state.settings["preview"] = {"enabled": False, "alerts": {"enabled": False}}
    api._state.settings["fleet_bar"] = {"enabled": False}
    runtime = main_mod.build_telemetry(api._state, None, None)

    assert runtime is not None
    assert runtime._wants_discovery() is False
    api._state.settings["fleet_bar"]["enabled"] = True
    assert runtime._wants_discovery() is True
    runtime.stop()


def test_build_alert_policy_has_no_private_tailer(tmp_path):
    from wingman.__main__ import build_alert_policy

    host = FakePreviewHost()
    api = make_api(tmp_path)
    policy = build_alert_policy(api._state, host)

    assert isinstance(policy, alert_service.AlertPolicy)
    assert not hasattr(policy, "_tailer")


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
    monkeypatch.setattr(
        alert_service, "play_sound", lambda sid, vol: played.append((sid, vol))
    )
    host = FakePreviewHost(characters=["Alice", "Bob", "Carol"])
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    api.test_alert("combat")

    assert played == [("system-fault", 100)]
    assert len(host.raised) == 3


def test_a_test_alert_with_no_live_preview_still_plays_the_sound(monkeypatch, tmp_path):
    """Nothing was refused -- the sound genuinely fired -- so this is
    applied: True with a plain-language explanation, never a silent
    no-op and never applied: False."""
    played = []
    monkeypatch.setattr(
        alert_service, "play_sound", lambda sid, vol: played.append((sid, vol))
    )
    api = make_api(tmp_path)  # preview_host defaults to None
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"] is True
    assert result["persisted"] is False
    assert result["error"] == "Previews are off, so only the sound played."
    assert played == [("system-fault", 100)]


def test_a_test_alert_with_no_named_clients_still_plays_the_sound(
    monkeypatch, tmp_path
):
    """Previews being on with no client open is a different situation from
    previews being off, and the copy has to say which -- otherwise a user
    with a live host and no logged-in character reads the same "previews
    are off" message as someone who never turned previews on at all."""
    played = []
    monkeypatch.setattr(
        alert_service, "play_sound", lambda sid, vol: played.append((sid, vol))
    )
    host = FakePreviewHost(characters=[])  # host present, nothing named
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    result = api.test_alert("combat")

    assert result["applied"] is True
    assert result["error"] == "No EVE clients are open, so only the sound played."
    assert played == [("system-fault", 100)]
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
    """A per-event field is read live by AlertPolicy on its next batch; it
    cannot change whether shared telemetry itself should be running."""
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)

    api.set_alert_event("combat", "cooldown_s", 5)

    assert telemetry.reconciled == 0


# ---- volume and flash speed -------------------------------------------------


def test_set_alert_volume_persists_and_does_not_reconcile(tmp_path):
    """Nothing is playing between two alerts, so there is no live state to
    correct and no thread whose should-it-run answer changed."""
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)

    result = api.set_alert_volume(40)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["preview"]["alerts"]["volume"] == 40
    assert telemetry.reconciled == 0


def test_set_alert_volume_lets_settings_clamp_the_value(tmp_path):
    """Same division of labour as set_preview_opacity: validated_alerts
    owns the 0-100 range, in one place."""
    api = make_api(tmp_path)

    result = api.set_alert_volume(400)

    assert result["applied"]
    assert api._state.settings["preview"]["alerts"]["volume"] == 100


def test_set_alert_event_accepts_a_flash_rate(tmp_path):
    api = make_api(tmp_path)

    result = api.set_alert_event("combat", "flash_rate", "fast")

    assert result["applied"]
    assert (
        api._state.settings["preview"]["alerts"]["events"]["combat"]["flash_rate"]
        == "fast"
    )


def test_set_alert_event_no_longer_writes_a_duration(tmp_path):
    """The duration is derived from flash_rate x pulses at the one site
    that arms a ring. A writable copy here would be a second source of
    truth for how long an alert pulses."""
    api = make_api(tmp_path)

    result = api.set_alert_event("combat", "duration_ms", 5000)

    assert not result["applied"]
    assert result["error"]


def test_a_test_alert_plays_at_the_configured_volume(monkeypatch, tmp_path):
    """Test exists to show what an alert is like. One that ignored the
    slider would be the only control on the card that lies about what it
    does."""
    played = []
    monkeypatch.setattr(
        alert_service, "play_sound", lambda sid, vol: played.append((sid, vol))
    )
    api = make_api(tmp_path, preview_host=FakePreviewHost(characters=["Alice"]))
    api._state.settings["preview"] = {"alerts": _alerts_section(volume=25)}

    api.test_alert("combat")

    assert played == [("system-fault", 25)]


def test_a_test_alert_is_not_silenced_by_a_focused_client(monkeypatch, tmp_path):
    """You are looking at Wingman when you press Test, so no EVE client
    holds the foreground -- and Test reaches the host directly rather than
    through the poll path that does the suppressing."""
    played = []
    monkeypatch.setattr(
        alert_service, "play_sound", lambda sid, vol: played.append((sid, vol))
    )
    host = FakePreviewHost(characters=["Alice"], focused="Alice")
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"alerts": _alerts_section()}

    api.test_alert("combat")

    assert played == [("system-fault", 100)]


# ---- the remaining bridge methods -------------------------------------------


def test_set_alert_pve_filter_persists_and_does_not_reconcile(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)

    result = api.set_alert_pve_filter(False)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["preview"]["alerts"]["pve_filter"] is False
    assert telemetry.reconciled == 0


def test_set_alert_persist_persists_and_does_not_reconcile(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)

    result = api.set_alert_persist(False)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["preview"]["alerts"]["persist_until_selected"] is False
    assert telemetry.reconciled == 0


def test_get_alert_state_tolerates_no_telemetry_runtime(tmp_path):
    api = make_api(tmp_path)

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
    feature exists to prevent. Mirrors the coordinator's folder resolver."""
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
    return (root / "wingman" / "web" / name).read_text(encoding="utf-8")


def test_the_alerts_card_has_its_own_section_and_polls_on_it():
    """Round 5's D1. This card was the third in the Previews section; it is
    now the first in a section of its own.

    Two halves, and the second is the one that bites. Moving the markup
    alone leaves alerts.js polling on the WRONG name: its wm:section
    listener started the two-second poll on 'previews', which after the
    move means the poll runs while the user is on a pane this card is not
    rendered in, and stops the moment they open the pane it is. Inverted,
    and invisible in a diff of either file alone -- so the section name is
    asserted against the markup rather than trusted.
    """
    html = _web("index.html")
    js = _web("alerts.js")

    assert 'id="section-alerts"' in html, "Alerts has no section of its own"

    section = html.split('id="section-alerts"')[1].split('id="section-')[0]
    assert "<h2>Gamelog alerts</h2>" in section, (
        "the Alerts card is not in the Alerts section. Its heading may not "
        "be the rail label itself -- see test_settings_page.py"
    )

    previews = html.split('id="section-previews"')[1].split('id="section-')[0]
    assert "alert-events" not in previews, (
        "the Alerts card is still in the Previews section as well"
    )

    # The name alerts.js polls on must be the section the card lives in.
    # Anchored on the addEventListener call, not on the bare event name:
    # "wm:section" appears in this file's prose first, and splitting on it
    # reads a comment and passes or fails for the wrong reason.
    listener = js.split("addEventListener('wm:section'")[1].split("});")[0]
    assert "'alerts'" in listener, (
        "alerts.js still starts its poll on another section's name; after "
        "D1 the card is only rendered in #section-alerts"
    )
    assert "'previews'" not in listener


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


def test_health_and_characters_render_together():
    """A character list with no liveness beside it keeps reading
    "watching Alice, Bob" after the shared reader has failed --
    get_alert_state's `running` flag must appear in the same rendered
    sentence as the characters, never the characters alone.

    It renders NAMES rather than a count: with five clients running, "5
    characters online" is the number you already assumed, and the fact
    worth having is which one is missing when it says four.
    """
    js = _web("alerts.js")
    block = js.split("function healthText")[1].split("\n\n")[0]
    assert "state.running" in block
    assert "characters" in block
    assert "join(" in block, (
        "the health line must render the character NAMES, not a count"
    )


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
    were toggled off: the backend really did detach AlertPolicy, but the
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

    # Comments stripped first, the same way test_page_conventions.py does
    # it. This asserts a fact about the LISTENER, but it locates it by
    # splitting on the event's name in raw source -- so the first prose
    # mention of that name anywhere above the registration silently became
    # the split point, and the assertion started reading a comment. That
    # is exactly what happened when alerts.js grew a comment explaining
    # which events re-render the health line.
    js = re.sub(r"(?m)^\s*//.*$", "", _web("alerts.js"))
    assert "wm:preview-enabled-changed" in js
    assert "refresh" in js.split("wm:preview-enabled-changed")[1][:80]


def test_the_pve_filter_names_every_event_it_actually_filters():
    """patterns.FILTERED_EVENTS decides which events the NPC heuristic is
    applied to, and the checkbox's sentence is a hand-written claim about
    that set.

    It said "Ignore combat that looks like NPC fire" while the filter also
    governs warp scrambles, sitting card-level above three events -- which
    taught the reader that all three were filtered. decloak never is: it
    carries no attacker source for the heuristic to test
    (patterns.py:25-27), so a user reading the old sentence could believe
    their decloak alerts were NPC-filtered when nothing had ever filtered
    them.
    """
    from wingman.alerts import patterns

    sentence = re.search(
        r'id="alert-pve-filter".*?</label>', _web("index.html"), re.DOTALL
    )
    assert sentence, "the PvE filter checkbox is gone"
    words = " ".join(sentence.group(0).split()).lower()

    # The display name each event id goes by in the card's own rows.
    names = {"combat": "combat", "warp_scramble": "warp scramble"}
    for event in patterns.FILTERED_EVENTS:
        assert names[event] in words, (
            f"the PvE filter applies to {event!r} but its sentence does "
            f"not mention it: {words!r}"
        )
    for event in set(patterns.EVENTS) - set(patterns.FILTERED_EVENTS):
        assert names.get(event, event.replace("_", " ")) not in words, (
            f"the PvE filter does NOT apply to {event!r}, but its "
            f"sentence names it: {words!r}"
        )
