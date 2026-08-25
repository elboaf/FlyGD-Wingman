"""One log line in, one event out.

Every synthetic shape here encodes TriffView's matcher contract; the
corpus tests below are what is authoritative over it -- they run against
real anonymised excerpts from a live EVE install (see
tests/fixtures/gamelogs/), and every shape they turned up that the
synthetic fixtures had not anticipated (a scramble line's own markup, a
miss line's bare name, a bracket-less real player) is now also covered
here so the case does not need the corpus to be caught by CI.
"""

from pathlib import Path

import pytest

from obs_youtube_uploader.alerts import patterns

DAMAGE = (
    "[ 2026.08.24 20:42:50 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>"
)
MISS = "[ 2026.08.24 20:42:51 ] (combat) Bob Smith[BURN](Rifter) misses you completely"
DRONE_MISS = (
    "[ 2026.08.24 20:42:52 ] (combat) Hammerhead II belonging to Bob Smith "
    "misses you completely - Hammerhead II"
)
# Real incoming scramble/disruption lines wrap the attacker's name in an
# extra <fontsize=12>...</fontsize=12> pair the damage line's shape does
# not have. _SOURCE_RE's terminator has to walk past that tag rather than
# stopping on "<font" as a substring of "<fontsize=12>" -- confirmed
# against the real corpus, where every incoming scramble line came back
# with an empty source until the terminator was fixed to require a
# non-letter after "font".
SCRAMBLE = (
    "[ 2026.08.24 20:43:02 ] (combat) <color=0xffffffff>"
    "<b>Warp scramble attempt</b> <color=0x77ffffff><font size=10>from</font> "
    "<color=0xffffffff><b><color=0xffffffff><fontsize=12>Bob Smith [BURN]</color>"
    "<color=0xfff0f000> Rifter</color><color=0xffffffff></b> "
    "<color=0x77ffffff><font size=10>to <b><color=0xffffffff></font>you!"
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
# The load-bearing shape the corpus found: in wormhole space, with no
# local channel to resolve an attacker against, EVE's own client can
# render a real player as a bare name with no corp/hull at all --
# indistinguishable from an NPC's. Confirmed against three unrelated real
# characters across separate fights (a direct-fire damage line and a
# warp-disruption line each); this is the anonymised shape of one of
# them.
UNRESOLVED_PLAYER_DAMAGE = (
    "[ 2026.08.24 20:45:00 ] (combat) <color=0xffcc0000><b>341</b> "
    "<color=0x77ffffff><font size=10>from</font> "
    "<b><color=0xffffffff>Doran Velk</b><font size=10>"
    "<color=0x77ffffff> - 250mm Railgun II - Penetrates"
)
UNRESOLVED_PLAYER_SCRAMBLE = (
    "[ 2026.08.24 20:45:05 ] (combat) <color=0xffffffff>"
    "<b>Warp disruption attempt</b> <color=0x77ffffff><font size=10>from</font> "
    "<color=0xffffffff><b>Doran Velk  Proteus</b> "
    "<color=0x77ffffff><font size=10>to <b><color=0xffffffff></font>you!"
)


@pytest.mark.parametrize(
    "line,event",
    [
        (DAMAGE, "combat"),
        (MISS, "combat"),
        (DRONE_MISS, "combat"),
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


def test_scramble_source_is_extracted_without_markup():
    """The real corpus's first surprise: every warp-scramble line's source
    came back empty until _SOURCE_RE stopped mistaking <fontsize=12> for
    the <font ...> terminator it was looking for."""
    assert patterns.match_line(SCRAMBLE).source == "Bob Smith [BURN] Rifter"


def test_miss_source_is_blank():
    """A miss line's source is a bare name whether the attacker is a
    player or an NPC -- confirmed against the real corpus, where neither
    ever carries a corp ticket or hull. match_line does not extract it,
    so is_likely_npc is never asked to guess at something undecidable."""
    assert patterns.match_line(MISS).source == ""
    assert patterns.match_line(DRONE_MISS).source == ""


def test_strip_markup_drops_the_timestamp():
    """Everything up to the first "] " goes, or the timestamp's digits and
    brackets reach is_likely_npc and every NPC reads as a player."""
    assert "2026" not in patterns.strip_markup(DAMAGE)


def test_strip_markup_does_not_truncate_on_an_inner_bracket():
    """A scramble source can carry its own "] " (a corp ticker followed by
    a space) once it has been extracted as a standalone fragment. Only a
    *leading* bracket is the timestamp; an un-anchored partition ate the
    name in front of an inner one instead."""
    fragment = "Talia Renn [KVOS] Taranis"
    assert patterns.strip_markup(fragment) == fragment


@pytest.mark.parametrize(
    "source,npc",
    [
        ("Sleepless Sentinel", True),
        ("Bob Smith[BURN](Rifter)", False),
        ("Bob Smith's Hobgoblin II", False),
        ("Emergent Patroller", True),
        ("CONCORD Police Captain", True),
        ("Guristas Lookout Worm", True),
        # A bare name outside the closed NPC vocabulary must default to
        # "not an NPC" -- the corpus found real players rendered exactly
        # like this in wormhole space, with no corp/hull to hand at all.
        ("Doran Velk", False),
        ("Zarknabbertide Dovek", False),
    ],
)
def test_npc_heuristic(source, npc):
    """A corp ticker in brackets, a hull in parens, or "'s " for a drone.
    is a reliable "not an NPC" signal. Its absence is NOT the mirror image
    -- only a closed, corpus-verified vocabulary of Sleeper/police/sentry
    names is trusted for the positive case; everything else bare defaults
    to "not an NPC" so a false negative never silences a real fight."""
    assert patterns.is_likely_npc(source) is npc


def test_npc_damage_fixture_is_classified_as_npc():
    assert patterns.is_likely_npc(patterns.match_line(NPC_DAMAGE).source) is True


def test_unresolved_player_is_not_classified_as_an_npc():
    """The corpus's central finding: a real player attacking with no
    corp/hull at all must still survive the filter."""
    assert (
        patterns.is_likely_npc(patterns.match_line(UNRESOLVED_PLAYER_DAMAGE).source)
        is False
    )
    assert (
        patterns.is_likely_npc(patterns.match_line(UNRESOLVED_PLAYER_SCRAMBLE).source)
        is False
    )


def test_decloak_is_not_filtered():
    """Its line carries no attacker source, so there is nothing to test
    and the filter must not be applied to it."""
    assert "decloak" not in patterns.FILTERED_EVENTS


def test_events_and_severity_agree():
    """settings.py builds its schema from EVENTS. If the two lists drift,
    the schema grows an event the renderer cannot draw."""
    assert set(patterns.EVENTS) == set(patterns.SEVERITY)


# ---- the real corpus -------------------------------------------------
#
# Short, hand-anonymised excerpts from a live EVE install's Gamelogs
# folder. Structure is preserved exactly (bracket/paren/"'s " shape,
# length, NPC names verbatim) -- only character names and corp/alliance
# tickers were substituted, since this repository is public. See
# .superpowers/task-3-report.md for the anonymisation key and for which
# categories the corpus did and did not turn up.

FIXTURES = Path(__file__).parent / "fixtures" / "gamelogs"


def _corpus_lines():
    if not FIXTURES.is_dir():
        return []
    lines = []
    for path in sorted(FIXTURES.glob("*.txt")):
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            lines.extend(fh.read().splitlines())
    return lines


# Hand-built by reading the corpus and deciding, line by line, which
# sources belonged to real players -- not derived from is_likely_npc,
# which would only re-assert the heuristic against itself. Includes the
# bracketed/parenthesised shapes and the bare, corp-less shapes the
# corpus showed EVE's own client renders for a wormhole attacker it
# cannot resolve.
PLAYER_SOURCES = [
    "Bellrik Sanmar[VYKO](Vexor)",
    "Renar Duthie[VYKO](Vexor)",
    "Talia Renn [KVOS] Taranis",
    "Doran Velk",
    "Doran Velk Proteus",
]


@pytest.mark.skipif(not FIXTURES.is_dir(), reason="no gamelog corpus committed")
def test_corpus_yields_at_least_one_of_every_event():
    """A corpus that cannot produce an event is not exercising that
    matcher, and the matcher's first real input would be a fight."""
    seen = {m.event for m in filter(None, map(patterns.match_line, _corpus_lines()))}
    assert seen == set(patterns.EVENTS)


@pytest.mark.skipif(not FIXTURES.is_dir(), reason="no gamelog corpus committed")
def test_no_player_attack_in_the_corpus_is_classified_as_an_npc():
    """The load-bearing assertion of the whole feature. Any line here that
    a human confirmed was a player must survive the filter."""
    for source in PLAYER_SOURCES:
        assert patterns.is_likely_npc(source) is False
