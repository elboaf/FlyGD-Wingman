"""Thread-free alert decisions fed by the shared telemetry coordinator."""

import logging
from typing import NamedTuple

from wingman.alerts.service import AlertPolicy

PLAYER = "Bob Smith[BURN](Rifter)"
NPC = "Sleepless Sentinel"


class Event(NamedTuple):
    character: str
    event: str
    source: str


def _config(**over):
    cfg = {
        "enabled": True,
        "pve_filter": True,
        "persist_until_selected": True,
        "volume": 100,
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


def _policy(config=None, sounds=None, alerts=None, focused=None):
    cfg = config or _config()
    return AlertPolicy(
        config=lambda: cfg,
        sound=lambda sid, volume: (sounds if sounds is not None else []).append(
            (sid, volume)
        ),
        focused=focused or (lambda: None),
        on_alert=lambda *args: (alerts if alerts is not None else []).append(args),
    )


def test_player_attack_dispatches_with_sound_and_persistent_ring():
    sounds, alerts = [], []
    policy = _policy(sounds=sounds, alerts=alerts)

    out = policy.handle([Event("Alice", "combat", PLAYER)], 0.0)

    assert out == [("Alice", "combat", "#ff4d4d")]
    assert sounds == [("system-fault", 100)]
    assert alerts[0][2]["persist_until_selected"] is True


def test_pve_filter_blocks_npc_combat_and_scramble_but_not_decloak():
    policy = _policy()

    assert policy.handle([Event("Alice", "combat", NPC)], 0.0) == []
    assert policy.handle([Event("Alice", "warp_scramble", NPC)], 0.0) == []
    assert policy.handle([Event("Alice", "decloak", "")], 0.0)


def test_pve_filter_can_be_disabled():
    policy = _policy(_config(pve_filter=False))
    assert policy.handle([Event("Alice", "combat", NPC)], 0.0)


def test_cooldowns_are_per_character_and_event():
    policy = _policy()
    combat = Event("Alice", "combat", PLAYER)

    assert policy.handle([combat], 0.0)
    assert policy.handle([combat], 0.5) == []
    assert policy.handle([Event("Bravo", "combat", PLAYER)], 0.5)
    assert policy.handle([Event("Alice", "warp_scramble", PLAYER)], 0.5)
    assert policy.handle([combat], 1.5)


def test_disabled_event_dispatches_nothing_and_burns_no_cooldown():
    cfg = _config()
    cfg["events"]["combat"]["enabled"] = False
    policy = _policy(cfg)
    event = Event("Alice", "combat", PLAYER)

    assert policy.handle([event], 0.0) == []
    cfg["events"]["combat"]["enabled"] = True
    assert policy.handle([event], 0.1)


def test_suppressed_and_sound_none_events_play_nothing():
    cfg = _config()
    sounds = []
    policy = _policy(cfg, sounds=sounds)
    event = Event("Alice", "combat", PLAYER)
    policy.handle([event], 0.0)
    policy.handle([event], 0.5)
    assert sounds == [("system-fault", 100)]

    cfg["events"]["decloak"]["sound"] = "none"
    policy.handle([Event("Alice", "decloak", "")], 2.0)
    assert sounds == [("system-fault", 100)]


def test_config_is_read_live_and_volume_reaches_sound_sink():
    holder = {"cfg": _config(volume=25)}
    sounds = []
    policy = AlertPolicy(
        config=lambda: holder["cfg"],
        sound=lambda sid, volume: sounds.append((sid, volume)),
        focused=lambda: None,
        on_alert=lambda *args: None,
    )
    event = Event("Alice", "combat", PLAYER)

    assert policy.handle([event], 0.0)
    assert sounds == [("system-fault", 25)]
    holder["cfg"] = _config()
    holder["cfg"]["events"]["combat"]["enabled"] = False
    assert policy.handle([event], 10.0) == []


def test_focused_character_is_silent_and_forces_timed_ring():
    sounds, alerts = [], []
    policy = _policy(sounds=sounds, alerts=alerts, focused=lambda: "Alice")

    assert policy.handle([Event("Alice", "combat", PLAYER)], 0.0)

    assert sounds == []
    assert alerts[0][2]["persist_until_selected"] is False


def test_other_character_still_sounds_while_alice_is_focused():
    sounds = []
    policy = _policy(sounds=sounds, focused=lambda: "Alice")

    policy.handle([Event("Bravo", "combat", PLAYER)], 0.0)

    assert sounds == [("system-fault", 100)]


def test_focus_probe_failure_does_not_drop_alert(caplog):
    caplog.set_level(logging.DEBUG)

    def fail_focus():
        raise RuntimeError("foreground unavailable")

    policy = _policy(focused=fail_focus)

    assert policy.handle([Event("Alice", "combat", PLAYER)], 0.0)
    assert "Could not read the focused client" in caplog.text
