"""Cooldowns, the NPC filter, health, and lifecycle.

_handle takes `now` and returns what it dispatched, so the whole decision
layer is covered without a thread or a clock.
"""

import threading

from wingman.alerts import service, tailer
from wingman.alerts.service import POLL_INTERVAL_S

PLAYER = "Bob Smith[BURN](Rifter)"
NPC = "Sleepless Sentinel"


def _config(**over):
    cfg = {
        "enabled": True,
        "pve_filter": True,
        "persist_until_selected": True,
        "volume": 100,
        "defaults_version": 1,
        "events": {
            "combat": {
                "enabled": True,
                "cooldown_s": 1,
                "color": "#ff4d4d",
                "sound": "system-fault",
                "pulses": 3,
                "flash_rate": "normal",
            },
            "warp_scramble": {
                "enabled": True,
                "cooldown_s": 8,
                "color": "#ffd24d",
                "sound": "obey",
                "pulses": 3,
                "flash_rate": "normal",
            },
            "decloak": {
                "enabled": True,
                "cooldown_s": 8,
                "color": "#4dd2ff",
                "sound": "system-fault",
                "pulses": 3,
                "flash_rate": "normal",
            },
        },
    }
    cfg.update(over)
    return cfg


def _service(config=None, sounds=None, focused=None):
    """*sounds*, when given, records one (sound id, volume) pair per
    play: the volume is part of what the sink is told now, so a test that
    recorded only the id could not see it."""
    cfg = config or _config()
    return service.AlertService(
        config=lambda: cfg,
        folder=lambda: None,
        on_alert=lambda *a: None,
        sound=(
            (lambda sid, vol: sounds.append((sid, vol)))
            if sounds is not None
            else lambda _id, _vol: None
        ),
        focused=focused,
    )


def test_a_player_attack_is_dispatched():
    s = _service()
    out = s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert [e[1] for e in out] == ["combat"]


def test_an_npc_attack_is_filtered():
    """Sleeper sites put every client under continuous NPC fire. Without
    this the border never stops and a player landing mid-site is
    indistinguishable from the NPCs already firing."""
    s = _service()
    assert s._handle([tailer.Event("Alice", "combat", NPC)], 0.0) == []


def test_the_filter_also_covers_scrambles():
    """Sleepers and Drifters apply warp disruption routinely. Filtering
    only combat would leave any site producing a continuous, persistent,
    top-severity alert on every client."""
    s = _service()
    assert s._handle([tailer.Event("Alice", "warp_scramble", NPC)], 0.0) == []


def test_the_filter_does_not_touch_decloak():
    """Its line carries no attacker source, so an empty source must not
    be read as "bare name, therefore NPC" and swallowed."""
    s = _service()
    assert len(s._handle([tailer.Event("Alice", "decloak", "")], 0.0)) == 1


def test_the_filter_can_be_turned_off():
    s = _service(_config(pve_filter=False))
    assert len(s._handle([tailer.Event("Alice", "combat", NPC)], 0.0)) == 1


def test_a_second_event_inside_the_cooldown_is_suppressed():
    s = _service()
    ev = tailer.Event("Alice", "combat", PLAYER)
    assert len(s._handle([ev], 0.0)) == 1
    assert s._handle([ev], 0.5) == []
    assert len(s._handle([ev], 1.5)) == 1


def test_cooldowns_are_per_character_and_per_event():
    """One character being shot must not silence another's alert, and a
    scramble must not be swallowed by a combat cooldown."""
    s = _service()
    assert len(s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)) == 1
    assert len(s._handle([tailer.Event("Bravo", "combat", PLAYER)], 0.0)) == 1
    assert len(s._handle([tailer.Event("Alice", "warp_scramble", PLAYER)], 0.0)) == 1


def test_a_disabled_event_dispatches_nothing_and_burns_no_cooldown():
    cfg = _config()
    cfg["events"]["combat"]["enabled"] = False
    s = _service(cfg)
    assert s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0) == []


def test_a_suppressed_event_plays_no_sound():
    """Cooldown is checked before anything else happens. A suppressed
    event that still made a noise would be the worst of both."""
    sounds = []
    s = _service(sounds=sounds)
    ev = tailer.Event("Alice", "combat", PLAYER)
    s._handle([ev], 0.0)
    s._handle([ev], 0.5)
    assert sounds == [("system-fault", 100)]


def test_a_sound_of_none_is_not_played():
    cfg = _config()
    cfg["events"]["combat"]["sound"] = "none"
    sounds = []
    s = _service(cfg, sounds=sounds)
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == []


def test_config_is_read_per_event_not_captured():
    """settings._normalize reassigns data["preview"] wholesale on every
    call, so a captured subtree is orphaned after the first write. The
    service holds a callable for exactly this reason."""
    cfg = _config()
    holder = {"cfg": cfg}
    s = service.AlertService(
        config=lambda: holder["cfg"],
        folder=lambda: None,
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    assert len(s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)) == 1
    replacement = _config()
    replacement["events"]["combat"]["enabled"] = False
    holder["cfg"] = replacement
    assert s._handle([tailer.Event("Alice", "combat", PLAYER)], 10.0) == []


def test_health_reports_a_dead_thread():
    """A character count alone keeps reading "watching 4 characters"
    after the thread has died, which puts a healthy-looking card above a
    feature that has silently stopped alerting."""
    s = _service()
    assert s.health().running is False


def test_a_raising_poll_is_recorded_rather_than_killing_the_loop():
    s = _service()
    s._record_error(RuntimeError("disk gone"))
    assert "disk gone" in s.health().last_error


def test_reconcile_twice_with_an_unchanged_str_folder_does_not_restart(tmp_path):
    """Tailer stores its folder as a Path (tailer.py: `self._folder =
    Path(folder)`), but the callable returns whatever the caller was
    handed -- and the persisted setting everywhere else in this codebase
    is a plain str. Comparing Path to str is always unequal, so without
    normalizing the comparison this fast path can never fire: every
    settings write would tear the thread down and rebuild it, clearing
    cooldowns and blocking the caller on a join."""
    cfg = _config()
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: str(tmp_path),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    try:
        s.reconcile()
        first_thread = s._thread
        s.reconcile()
        assert s._thread is first_thread
    finally:
        s.stop()


# ---- the stop event is a parameter, not a re-read instance attribute -------


def test_run_stops_on_the_event_it_was_given_not_a_later_generation(tmp_path):
    """reconcile() replaces self._stop with a fresh Event when it rebuilds
    the thread (a folder move, or a wedged join timeout). A _run that
    re-read self._stop on every iteration would, in that second case, see
    the NEW generation's unset Event and keep polling forever -- two
    threads on one tailer. Passing the event in as a parameter and
    capturing it as a local makes the thread deaf to whatever self._stop
    is reassigned to after it started."""
    cfg = _config()
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: str(tmp_path),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    s._tailer = tailer.Tailer(tmp_path)
    my_generation = threading.Event()
    thread = threading.Thread(target=s._run, args=(my_generation, s._tailer))
    thread.start()
    try:
        # Simulate what reconcile() does when a join times out: install a
        # later generation while the old thread is still alive.
        s._stop = threading.Event()
        my_generation.set()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
    finally:
        my_generation.set()
        thread.join(timeout=2.0)


def test_run_only_touches_the_tailer_it_was_given(tmp_path):
    """Mirrors the stop-event test above, but for the other half of the
    fix: _run must poll the Tailer it was started with, not self._tailer
    re-read on every loop. reconcile() swaps self._tailer to a new
    generation whenever it rebuilds the thread -- if _run read the
    instance attribute instead of its captured local, a thread still
    running against its own generation would start polling the NEW
    Tailer the moment reconcile() installs one, splitting file positions
    between two threads."""
    own_tailer = tailer.Tailer(tmp_path)
    own_tailer.rescan = lambda now_utc: None
    own_tailer.poll = list

    class _ExplodingTailer(tailer.Tailer):
        def rescan(self, now_utc):
            raise AssertionError("must not touch a later generation's tailer")

        def poll(self):
            raise AssertionError("must not touch a later generation's tailer")

    other_tailer = _ExplodingTailer(tmp_path)

    cfg = _config()
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: str(tmp_path),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    stop_event = threading.Event()
    thread = threading.Thread(target=s._run, args=(stop_event, own_tailer))
    thread.start()
    try:
        # As reconcile() would after starting a replacement thread for a
        # folder change -- this thread must not notice.
        s._tailer = other_tailer
        stop_event.wait(POLL_INTERVAL_S * 2.5)
    finally:
        stop_event.set()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
    # _ExplodingTailer raises AssertionError from inside the worker
    # thread if _run ever touched it -- but _run's except clause catches
    # that and records it via _record_error rather than letting it kill
    # the loop or reach pytest, so the only way to actually observe it
    # here is to read health() back, same as
    # test_a_raising_poll_is_recorded_rather_than_killing_the_loop does.
    assert s.health().last_error is None


def test_reconcile_does_not_replace_a_wedged_thread(tmp_path):
    """A join that times out means the old generation is still running,
    possibly still polling files. Starting a replacement thread here --
    a second Tailer, a second poll loop -- would race the first over the
    same folder and its own _cooldowns. reconcile() must instead log and
    leave the old generation as the sole authority until it actually
    exits."""
    old_tailer = tailer.Tailer(tmp_path)
    stuck = threading.Event()  # never set -- stands in for a wedged thread
    stuck_thread = threading.Thread(target=stuck.wait, daemon=True)

    other_folder = tmp_path / "moved"
    other_folder.mkdir()
    cfg = _config()
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: str(other_folder),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    s._thread = stuck_thread
    s._tailer = old_tailer
    s._stop = threading.Event()
    stuck_thread.start()
    try:
        s.reconcile()
        assert s._tailer is old_tailer
        assert s._thread is stuck_thread
    finally:
        stuck.set()
        stuck_thread.join(timeout=2.0)


def test_a_timed_out_join_is_logged_not_silent(monkeypatch, tmp_path, caplog):
    """stop() and reconcile()'s teardown both check the join's result now,
    matching PreviewHost.stop's existing posture -- a thread that outlives
    its timeout must say so, not be assumed gone."""
    cfg = _config()
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: str(tmp_path),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    stuck = threading.Event()  # never set -- stands in for a wedged thread
    stuck_thread = threading.Thread(target=stuck.wait, daemon=True)
    s._thread = stuck_thread
    stuck_thread.start()
    s._stop = threading.Event()
    try:
        with caplog.at_level("WARNING"):
            s.stop()
        assert "did not exit within" in caplog.text
    finally:
        stuck.set()
        stuck_thread.join(timeout=2.0)


# ---- _wanted requires a real directory, not merely a configured path ------


def test_wanted_is_false_when_the_folder_no_longer_exists(tmp_path):
    """Path.glob on a missing directory yields nothing and raises nothing,
    so without this check a folder that was valid and stopped being one
    (an unmounted drive, an unlinked OneDrive folder) would still read as
    'watching' forever."""
    missing = tmp_path / "gone"
    s = service.AlertService(
        config=lambda: _config(),
        folder=lambda: str(missing),
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    assert s._wanted() is False


def test_reconcile_stops_the_thread_when_the_folder_disappears(tmp_path):
    """The design's own predicate is 'resolves to a real directory' -- a
    folder that vanishes out from under a running poll thread must be
    torn down by the next reconcile, not left polling a directory that is
    no longer there."""
    folder = {"path": str(tmp_path)}
    s = service.AlertService(
        config=lambda: _config(),
        folder=lambda: folder["path"],
        on_alert=lambda *a: None,
        sound=lambda _id, _vol: None,
    )
    try:
        s.reconcile()
        assert s.health().running
        folder["path"] = str(tmp_path / "gone")
        s.reconcile()
        assert s.health().running is False
    finally:
        s.stop()


# ---- the client you are already looking at ---------------------------------
# The sound is what makes an alert an interruption, and an interruption
# about the client already filling your screen is noise: you can see the
# fight. The flash still happens -- it is free, it is where the event is,
# and PreviewWindow.arm_alert already makes a focused client's alert timed
# rather than persistent, so it fades on its own rather than waiting to be
# acknowledged by a client you never left.


def test_the_focused_character_gets_no_sound():
    sounds = []
    s = _service(sounds=sounds, focused=lambda: "Alice")
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == []


def test_the_focused_character_still_gets_its_flash():
    """Suppressing the sound must not suppress the alert: the ring is
    what the preview is for, and an event that dispatched nothing would
    also skip its cooldown and re-fire on the next poll."""
    s = _service(focused=lambda: "Alice")
    out = s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert [e[1] for e in out] == ["combat"]


def test_another_character_still_makes_a_noise_while_you_fly_alice():
    """The whole point of the feature: an alert on a client you are NOT
    looking at is exactly the one that has to reach you."""
    sounds = []
    s = _service(sounds=sounds, focused=lambda: "Alice")
    s._handle([tailer.Event("Bravo", "combat", PLAYER)], 0.0)
    assert sounds == [("system-fault", 100)]


def test_no_focused_client_means_every_alert_sounds():
    """Focus is None the instant you click a browser or Wingman itself
    (host.py's _focused_key), which must not be read as "everything is
    focused" and silence the feature."""
    sounds = []
    s = _service(sounds=sounds, focused=lambda: None)
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == [("system-fault", 100)]


def test_a_focus_callable_that_raises_does_not_lose_the_alert(caplog):
    """It reaches across to the preview thread's host. A failure there
    must cost the suppression, not the alert."""

    def boom():
        raise RuntimeError("host gone")

    sounds = []
    s = _service(sounds=sounds, focused=boom)
    out = s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert [e[1] for e in out] == ["combat"]
    assert sounds == [("system-fault", 100)]


# ---- volume ----------------------------------------------------------------


def test_the_configured_volume_reaches_the_sink():
    sounds = []
    s = _service(_config(volume=40), sounds=sounds)
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == [("system-fault", 40)]


def test_a_missing_volume_key_plays_at_full_volume():
    """An upgrading install's settings.json predates the key, and a
    default of 0 there would silence alerts for everyone who had them."""
    cfg = _config()
    del cfg["volume"]
    sounds = []
    s = _service(cfg, sounds=sounds)
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == [("system-fault", 100)]


def test_a_silenced_alert_is_also_a_timed_one():
    """Silent and persistent is the worst pairing available: no sound
    because this thread saw the client focused, and a ring that pulses
    until acknowledged because the preview thread saw it lose focus a
    moment later. The two halves are decided together, here."""
    cfg = _config()
    cfg["persist_until_selected"] = True
    seen = []
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: None,
        on_alert=lambda character, event, spec: seen.append(spec),
        sound=lambda _id, _vol: None,
        focused=lambda: "Alice",
    )
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert seen[0]["persist_until_selected"] is False


def test_an_alert_you_can_hear_still_persists():
    """The other side of the pair: suppression must not leak into every
    alert and quietly retire persist_until_selected."""
    cfg = _config()
    cfg["persist_until_selected"] = True
    seen = []
    s = service.AlertService(
        config=lambda: cfg,
        folder=lambda: None,
        on_alert=lambda character, event, spec: seen.append(spec),
        sound=lambda _id, _vol: None,
        focused=lambda: "Alice",
    )
    s._handle([tailer.Event("Bravo", "combat", PLAYER)], 0.0)
    assert seen[0]["persist_until_selected"] is True
