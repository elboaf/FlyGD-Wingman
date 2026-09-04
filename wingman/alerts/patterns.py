"""One EVE gamelog line in, one alert event out.

Pure: no I/O, no clock, no Win32. Semantic line parsing now lives in
wingman.telemetry.parsing; this module stays the compatibility adapter that maps
those facts back to the alert events the existing tailer and service use.
"""

from typing import NamedTuple

from ..telemetry import parsing as telemetry_parsing

EVENTS = ("combat", "warp_scramble", "decloak")

# warp_scramble outranks combat because "I cannot leave" changes a different
# decision than "I am taking damage". A live higher-severity alert is never
# repainted by a lower one.
SEVERITY = {"warp_scramble": 3, "combat": 2, "decloak": 1}

# decloak carries no attacker source, so there is nothing for the NPC heuristic
# to test and it must not be applied.
FILTERED_EVENTS = frozenset({"combat", "warp_scramble"})

# Re-export the parsing helpers and regexes the tests pin directly. The parser
# is authoritative now; this module aliases it rather than carrying a second
# copy that could drift.
_INCOMING_COLOR = telemetry_parsing._INCOMING_COLOR
_SOURCE_RE = telemetry_parsing._SOURCE_RE
_SOURCE_FALLBACK_RE = telemetry_parsing._SOURCE_FALLBACK_RE
_TARGET_RE = telemetry_parsing._TARGET_RE
_TARGET_FALLBACK_RE = telemetry_parsing._TARGET_FALLBACK_RE
_MISS_RE = telemetry_parsing._MISS_RE
_TAG_RE = telemetry_parsing._TAG_RE
_WS_RE = telemetry_parsing._WS_RE
_LEADING_TIMESTAMP_RE = telemetry_parsing._LEADING_TIMESTAMP_RE
strip_markup = telemetry_parsing.strip_markup
_extract_target = telemetry_parsing._extract_target
_target_is_character = telemetry_parsing._target_is_character
_extract_source = telemetry_parsing._extract_source


class Match(NamedTuple):
    event: str
    source: str


# A bare name is NOT reliably an NPC: the real gamelog corpus has EVE's own
# client dropping a player's [Corp](Hull) tag entirely in wormhole space, where
# there is no local channel to resolve a pilot's info against. "Doran Velk"
# dealt hundreds of points of real damage and ran a real warp disruption with
# no bracket anywhere in the line; "Rendik Ashvale" and "Zarknabbertide Dovek"
# did the same across several unrelated fights. Any of those, treated as an
# NPC, is the exact silent-while-a-player-shoots-you failure this feature
# exists to prevent.
#
# Sleeper wormhole rats are the one bare-name vocabulary this heuristic can
# actually trust, because it is this product's own PvE content (a wormhole
# multiboxing toolkit, per PRODUCT.md) and CCP has kept it closed and stable
# for years: one adjective from this set in front of a rank word, and no player
# can register a character named that. CONCORD and empire police, and
# deployable sentry towers, are the same kind of reserved wording and appear
# the same way in the corpus.
#
# Anything bare that does not match is left unclassified -- including the
# Triglavian invasion's NPCs, which CCP deliberately names with
# ordinary-sounding human names attached to the same hulls (Drekavac, Leshak,
# Kikimora, ...) real players fly, making them genuinely indistinguishable from
# a player by name alone. Guessing at other regions' NPC vocabularies
# (Guristas, Sansha, Blood Raiders, ...) here would be inventing signal this
# corpus never tested. An extra alert during ratting is noise; a missed one
# during a fight is not, so the default for anything bare and unrecognised is
# "not an NPC".
_NPC_ADJECTIVES = (
    "sleepless",
    "awakened",
    "emergent",
    "faded hypnosian",
    "hypnosian",
    "corrupted",
    "bewildering",
)
_NPC_EXACT_PREFIXES = (
    "concord police",
    "caldari police",
    "gallente police",
    "amarr navy",
    "minmatar police",
    "tower sentry",
    "vigilant sentry",
    "wakeful sentry",
    "guristas lookout",
)


def is_likely_npc(source: str) -> bool:
    """True only when the source is confidently an NPC.

    Player attackers render with a corp ticker in brackets and a hull in
    parentheses, and player drones (in damage lines) as "Name's Hull" -- that
    punctuation is a reliable "not an NPC" signal, since no NPC has a corp. A
    bare name with none of it is NOT the mirror image: see the module-level
    comment above _NPC_ADJECTIVES for why guessing "no punctuation means NPC"
    is unsafe, and why only a closed, known-safe vocabulary is trusted for the
    positive case. It is a heuristic, which is why pve_filter is a toggle.

    A "misses you" line never carries this punctuation for anyone -- confirmed
    against the real gamelog corpus, where both "Sleepless Patroller misses you
    completely" (NPC) and "Farrowmark misses you completely" (a player,
    confirmed by that same name's bracketed damage lines moments later) render
    as a bare name. That used to mean a miss source could not be handed to this
    function at all: under the old "no punctuation means NPC" reading, every
    miss -- Farrowmark's included -- would have come back True. Under the
    closed allowlist above it is safe: "Sleepless Patroller" matches the NPC
    vocabulary and returns True, "Farrowmark" matches nothing and returns
    False, so match_line DOES route miss sources through here now; see its
    docstring.
    """
    if not source:
        return False
    if "'s " in source:
        return False
    if any(ch in source for ch in "[]()"):
        return False
    lowered = source.lower()
    return lowered.startswith(_NPC_ADJECTIVES) or lowered.startswith(
        _NPC_EXACT_PREFIXES
    )


def match_line(line: str, character: str) -> Match | None:
    """The only entry point. None means "not interesting".

    *character* is the Listener of the log the line came from -- the pilot this
    line is being read on behalf of.
    """
    if not line:
        return None
    parsed = telemetry_parsing.parse_line(line, character)
    for fact in parsed.facts:
        if fact.kind in {"incoming_damage", "incoming_miss"}:
            return Match("combat", fact.source)
        if fact.kind == "incoming_tackle":
            return Match("warp_scramble", fact.source)
        if fact.kind == "decloak":
            return Match("decloak", "")
    return None
