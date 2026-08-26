"""Alert section validation. Mirrors test_settings_preview.py's cases.

The clobber test at the bottom is the one that matters: it is the failure
mode that produces no error and loses the user's configuration.
"""

import json

import pytest

from wingman import settings


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_whole_section_of_wrong_type_falls_back(raw):
    assert settings.validated_alerts(raw) == settings._alerts_defaults()


def test_alerts_ship_off():
    """Enabling costs a polling thread on top of the preview thread."""
    assert settings._alerts_defaults()["enabled"] is False


def test_the_filter_and_persistence_ship_on():
    """The filter is what makes combat mean "a player is shooting you",
    and that is what makes a persistent alert tolerable rather than a
    ring that never stops during a Sleeper site."""
    d = settings._alerts_defaults()
    assert d["pve_filter"] is True and d["persist_until_selected"] is True


def test_every_parser_event_has_a_config_entry():
    """The schema is built from patterns.EVENTS. If the two drift, the
    section grows an event the renderer cannot draw, or loses one the
    tailer will emit."""
    from wingman.alerts import patterns

    assert set(settings._alerts_defaults()["events"]) == set(patterns.EVENTS)


@pytest.mark.parametrize(
    "key,given,expected",
    [
        ("cooldown_s", -5, 0),
        ("cooldown_s", 9999, 120),
        ("duration_ms", 1, 250),
        ("duration_ms", 999999, 15000),
        ("pulses", 0, 1),
        ("pulses", 99, 16),
    ],
)
def test_event_numbers_are_clamped(key, given, expected):
    out = settings.validated_alerts({"events": {"combat": {key: given}}})
    assert out["events"]["combat"][key] == expected


def test_a_bad_colour_falls_back_rather_than_reaching_pillow():
    """chrome.render passes the colour straight to Pillow, which raises on
    a malformed value -- on the preview thread, inside the paint path.
    """
    out = settings.validated_alerts({"events": {"combat": {"color": "red"}}})
    assert out["events"]["combat"]["color"] == "#ff4d4d"


def test_an_unknown_sound_becomes_silence_not_a_crash():
    out = settings.validated_alerts({"events": {"combat": {"sound": "airhorn"}}})
    assert out["events"]["combat"]["sound"] == "none"


def test_booleans_are_not_accepted_as_numbers():
    """bool is an int in Python; True would silently become a 1s cooldown.

    Uses warp_scramble (default 8s), not combat (default 1s): True == 1 as
    an int, so asserting combat's cooldown equals 1 passes whether or not
    the `not isinstance(value, bool)` guard exists and proves nothing.
    warp_scramble's default is not 1, so only the guard rejecting the bool
    can make this pass.
    """
    out = settings.validated_alerts({"events": {"warp_scramble": {"cooldown_s": True}}})
    assert out["events"]["warp_scramble"]["cooldown_s"] == 8
    assert not isinstance(out["events"]["warp_scramble"]["cooldown_s"], bool)


def test_one_malformed_event_drops_alone():
    """Same two-tier posture validated_preview already documents: a
    corrupt entry costs that event, not the whole section."""
    out = settings.validated_alerts(
        {"events": {"combat": {"cooldown_s": 7}, "decloak": "nonsense"}}
    )
    assert out["events"]["combat"]["cooldown_s"] == 7
    assert out["events"]["decloak"] == settings._alerts_defaults()["events"]["decloak"]


def test_unknown_events_are_dropped():
    """A hand-edited file must not be able to produce an event the
    renderer has no colour or severity rank for."""
    out = settings.validated_alerts({"events": {"nonsense": {"enabled": True}}})
    assert "nonsense" not in out["events"]


def test_the_section_survives_a_load_round_trip(tmp_path):
    """The key must be in _preview_defaults(), or validated_preview drops
    it from the section on every load and every update()."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["alerts"]["events"]["combat"]["color"] = "#00ff00"
    settings.save(data, path)
    loaded = settings.load(path)
    assert loaded["preview"]["alerts"]["events"]["combat"]["color"] == "#00ff00"


def test_a_layout_write_does_not_reset_the_alerts_section(tmp_path):
    """The regression this whole task exists to prevent.

    validated_preview rebuilds the section from _preview_defaults() on
    every _normalize, which every update() runs. A writer that touches
    only `layouts` -- which LayoutStore does, debounced by one second
    after any drag -- would silently revert the user's alert colours if
    `alerts` had no copy branch. No crash, no log line, and the user
    finds out the next time they look at the card.
    """
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["alerts"]["events"]["combat"]["color"] = "#00ff00"
    data["preview"]["alerts"]["persist_until_selected"] = False
    settings.save(data, path)

    live = settings.load(path)
    with settings.update(live, path) as doc:
        doc["preview"]["layouts"]["Alice"] = {"x": 1, "y": 2, "w": 3, "h": 4}

    on_disk = json.loads(path.read_text(encoding="utf-8"))["preview"]["alerts"]
    assert on_disk["events"]["combat"]["color"] == "#00ff00"
    assert on_disk["persist_until_selected"] is False
