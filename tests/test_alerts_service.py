"""Cooldowns, the NPC filter, health, and lifecycle.

_handle takes `now` and returns what it dispatched, so the whole decision
layer is covered without a thread or a clock.
"""

from obs_youtube_uploader.alerts import service, tailer

PLAYER = "Bob Smith[BURN](Rifter)"
NPC = "Sleepless Sentinel"


def _config(**over):
    cfg = {
        "enabled": True,
        "pve_filter": True,
        "persist_until_selected": True,
        "defaults_version": 1,
        "events": {
            "combat": {
                "enabled": True,
                "cooldown_s": 1,
                "color": "#ff4d4d",
                "sound": "chime",
                "duration_ms": 1200,
                "pulses": 3,
            },
            "warp_scramble": {
                "enabled": True,
                "cooldown_s": 8,
                "color": "#ffd24d",
                "sound": "bell",
                "duration_ms": 1200,
                "pulses": 3,
            },
            "decloak": {
                "enabled": True,
                "cooldown_s": 8,
                "color": "#4dd2ff",
                "sound": "chime",
                "duration_ms": 1200,
                "pulses": 3,
            },
        },
    }
    cfg.update(over)
    return cfg


def _service(config=None, sounds=None):
    cfg = config or _config()
    return service.AlertService(
        config=lambda: cfg,
        folder=lambda: None,
        on_alert=lambda *a: None,
        sound=(sounds.append if sounds is not None else lambda _id: None),
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
    assert sounds == ["chime"]


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
        sound=lambda _id: None,
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
        sound=lambda _id: None,
    )
    try:
        s.reconcile()
        first_thread = s._thread
        s.reconcile()
        assert s._thread is first_thread
    finally:
        s.stop()
