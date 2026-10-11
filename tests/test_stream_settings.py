"""The stream_coupling settings namespace (#317): defaults and validation
for ``preview.alerts.stream_coupling`` -- chord, quiet_s, mirror_on.

The spec fixes the shape: chord is an AHK-style string whose PRESENCE is
consent (no separate on/off; empty = inert), quiet_s clamps to 60-900
with 300 as the shipped default (the asymmetry decision: too short risks
the mid-fight toggle-off, too long only misses a fight the user can
start by hand), and mirror_on is the one toggle that is not consent --
it persists and is restored at launch, shipped default off.
"""

from wingman import settings


def sc(raw):
    return settings.validated_preview(
        {"enabled": True, "alerts": {"stream_coupling": raw}}
    )["alerts"]["stream_coupling"]


def test_defaults_are_off_inert_and_600s():
    """Rev 4 (#335): the quiet period is FIXED at 600 -- the range
    60-900 and the 300 default are retired. The stop is snapshot-gated
    now, so running long is a one-sided error: the probe can only end a
    stream later than the quiet clock, never earlier, and players want
    to watch the grid after combat ends."""
    fresh = settings.validated_preview({"enabled": True})
    coupling = fresh["alerts"]["stream_coupling"]
    assert coupling == {
        "chord": "",
        "quiet_s": 600,
        "mirror_on": False,
        "manual_live": False,
    }


def test_mirror_on_persists_through_normalization():
    assert sc({"mirror_on": True})["mirror_on"] is True
    assert sc({"mirror_on": False})["mirror_on"] is False
    # Absent keeps the default; a non-bool never lands.
    assert sc({})["mirror_on"] is False
    assert sc({"mirror_on": "yes"})["mirror_on"] is False


def test_chord_is_a_string_and_presence_is_consent():
    assert sc({"chord": "^!d"})["chord"] == "^!d"
    assert sc({"chord": ""})["chord"] == ""
    # A non-string chord is not a chord: falls back to inert, never to a
    # crash or a coercion that could invent a keybind.
    assert sc({"chord": 17})["chord"] == ""
    assert sc({"chord": None})["chord"] == ""


def test_quiet_s_clamps_to_600():
    """Fixed 600 (rev 4): any stored value normalizes to 600. An old
    build's 300 or a hand-edited 900 is read as 600 without error -- a
    migration by projection, not a rejection that would drop the chord
    alongside it."""
    assert sc({})["quiet_s"] == 600
    assert sc({"quiet_s": 300})["quiet_s"] == 600
    assert sc({"quiet_s": 900})["quiet_s"] == 600
    assert sc({"quiet_s": 10})["quiet_s"] == 600
    assert sc({"quiet_s": True})["quiet_s"] == 600
    assert sc({"quiet_s": "300"})["quiet_s"] == 600
    # bool is an int in Python; True must not become a quiet period of 1
    # -- with the fixed value it is 600 either way, but the guard stays.


def test_a_malformed_section_falls_back_whole():
    coupling = sc("junk")
    assert coupling == {
        "chord": "",
        "quiet_s": 600,
        "mirror_on": False,
        "manual_live": False,
    }


def test_a_malformed_chord_falls_back_alone():
    """A string the notation cannot spell is not a chord (#319): it falls
    back to the empty default ALONE -- quiet_s and mirror_on survive the
    same rebuild -- because the trigger (#320) spells its SendInput out of
    this notation and nothing anywhere may fire on a chord it cannot
    spell. Modifier-only notation names no key, so it is malformed too."""
    coupling = sc({"chord": "nonsense", "quiet_s": 120, "mirror_on": True})
    assert coupling["chord"] == ""
    assert coupling["quiet_s"] == 600
    assert coupling["mirror_on"] is True
    assert sc({"chord": "^"})["chord"] == ""
    assert sc({"chord": "   "})["chord"] == ""


def test_validating_alerts_never_drops_the_coupling_section():
    """The same trap validated_alerts' own comment records: a writer that
    rebuilds the section from defaults on every normalize silently reverts
    the user's configuration. Whatever else happens, a stored coupling
    survives a round trip."""
    once = sc({"chord": "^!d", "quiet_s": 120, "mirror_on": True})
    twice = sc(once)
    assert twice == {
        "chord": "^!d",
        "quiet_s": 600,
        "mirror_on": True,
        "manual_live": False,
    }
