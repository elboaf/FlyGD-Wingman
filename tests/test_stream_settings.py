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


def test_defaults_are_off_inert_and_300s():
    fresh = settings.validated_preview({"enabled": True})
    coupling = fresh["alerts"]["stream_coupling"]
    assert coupling == {"chord": "", "quiet_s": 300, "mirror_on": False}


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


def test_quiet_s_clamps_to_the_documented_range():
    assert sc({"quiet_s": 300})["quiet_s"] == 300
    assert sc({"quiet_s": 60})["quiet_s"] == 60
    assert sc({"quiet_s": 900})["quiet_s"] == 900
    assert sc({"quiet_s": 10})["quiet_s"] == 60
    assert sc({"quiet_s": 5000})["quiet_s"] == 900
    # bool is an int in Python; True must not become a quiet period of 1.
    assert sc({"quiet_s": True})["quiet_s"] == 300
    assert sc({"quiet_s": "300"})["quiet_s"] == 300


def test_a_malformed_section_falls_back_whole():
    coupling = sc("junk")
    assert coupling == {"chord": "", "quiet_s": 300, "mirror_on": False}


def test_validating_alerts_never_drops_the_coupling_section():
    """The same trap validated_alerts' own comment records: a writer that
    rebuilds the section from defaults on every normalize silently reverts
    the user's configuration. Whatever else happens, a stored coupling
    survives a round trip."""
    once = sc({"chord": "^!d", "quiet_s": 120, "mirror_on": True})
    twice = sc(once)
    assert twice == {"chord": "^!d", "quiet_s": 120, "mirror_on": True}
