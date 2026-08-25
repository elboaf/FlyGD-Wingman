"""One log line in, one event out.

Every line here encodes TriffView's matcher contract rather than verified
EVE output: neither repository carries log bodies, so these are the shapes
the matchers were written against. The real corpus arrives in a later task
and is authoritative over anything asserted here.
"""

import pytest

from obs_youtube_uploader.alerts import patterns

DAMAGE = (
    "[ 2026.08.24 20:42:50 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>"
)
MISS = "[ 2026.08.24 20:42:51 ] (combat) Bob Smith[BURN](Rifter) misses you completely"
SCRAMBLE = (
    "[ 2026.08.24 20:43:02 ] (combat) <color=0xffe57f7f>"
    "<b>Warp scramble attempt</b> <color=0xffffffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b> <font size=10>to</font> <b>you!</b>"
)
DECLOAK = (
    "[ 2026.08.24 20:43:10 ] (notify) Your cloak deactivates due to a nearby object."
)
NPC_DAMAGE = (
    "[ 2026.08.24 20:44:00 ] (combat) <color=0xffcc0000><b>88</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Sleepless Sentinel</b><font size=10> - Hits</font>"
)
OUTGOING = (
    "[ 2026.08.24 20:42:50 ] (combat) <color=0xff00ffff><b>210</b> "
    "<color=0xff7fffff><font size=10>to</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>"
)


@pytest.mark.parametrize(
    "line,event",
    [
        (DAMAGE, "combat"),
        (MISS, "combat"),
        (SCRAMBLE, "warp_scramble"),
        (DECLOAK, "decloak"),
    ],
)
def test_each_shape_matches_its_event(line, event):
    assert patterns.match_line(line).event == event


def test_damage_and_miss_are_one_event():
    """TriffView splits these because the two lines look nothing alike --
    a colour code versus a literal. That is a parsing detail; a pilot being
    shot at and missed is being shot at."""
    assert patterns.match_line(DAMAGE).event == patterns.match_line(MISS).event


def test_outgoing_damage_does_not_alert():
    """The colour code is the whole discriminator. Without it, every shot
    you fire alerts you about yourself, continuously, during every fight."""
    assert patterns.match_line(OUTGOING) is None


@pytest.mark.parametrize("line", ["", "   ", "[ 2026.08.24 20:42:50 ] (None) x"])
def test_uninteresting_lines_return_none(line):
    assert patterns.match_line(line) is None


def test_source_is_extracted_without_markup():
    assert patterns.match_line(DAMAGE).source == "Bob Smith[BURN](Rifter)"


def test_miss_source_is_extracted():
    assert patterns.match_line(MISS).source == "Bob Smith[BURN](Rifter)"


def test_strip_markup_drops_the_timestamp():
    """Everything up to the first "] " goes, or the timestamp's digits and
    brackets reach is_likely_npc and every NPC reads as a player."""
    assert "2026" not in patterns.strip_markup(DAMAGE)


@pytest.mark.parametrize(
    "source,npc",
    [
        ("Sleepless Sentinel", True),
        ("Bob Smith[BURN](Rifter)", False),
        ("Bob Smith's Hobgoblin II", False),
        ("Emergent Patroller", True),
    ],
)
def test_npc_heuristic(source, npc):
    """A corp ticker in brackets, a hull in parens, or "'s " for a drone.
    NPCs are a bare name. This is a heuristic and the corpus task is what
    validates it -- a false negative here means silence while a player
    opens fire."""
    assert patterns.is_likely_npc(source) is npc


def test_decloak_is_not_filtered():
    """Its line carries no attacker source, so there is nothing to test
    and the filter must not be applied to it."""
    assert "decloak" not in patterns.FILTERED_EVENTS


def test_events_and_severity_agree():
    """settings.py builds its schema from EVENTS. If the two lists drift,
    the schema grows an event the renderer cannot draw."""
    assert set(patterns.EVENTS) == set(patterns.SEVERITY)
