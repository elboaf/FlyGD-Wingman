"""One EVE gamelog line in, one alert event out.

Pure: no I/O, no clock, no Win32. Everything that decides *whether* a line
is interesting lives here, so the tailer can stay about files and the
service about cooldowns.

The matchers are substring tests on the lowercased line rather than
regexes, which is what TriffView does and is the right call: the lines
carry nested colour and font markup whose exact shape varies, and a regex
over that is a way to stop matching after a patch that changed nothing
anyone cares about.
"""

import re
from typing import NamedTuple

EVENTS = ("combat", "warp_scramble", "decloak")

# warp_scramble outranks combat because "I cannot leave" changes a
# different decision than "I am taking damage". A live higher-severity
# alert is never repainted by a lower one.
SEVERITY = {"warp_scramble": 3, "combat": 2, "decloak": 1}

# decloak carries no attacker source, so there is nothing for the NPC
# heuristic to test and it must not be applied.
FILTERED_EVENTS = frozenset({"combat", "warp_scramble"})

# Incoming damage is red. Outgoing is not, and that colour code is the
# only thing separating "someone is shooting me" from "I am shooting".
_INCOMING_COLOR = "0xffcc0000"

# The lookahead on <font excludes real EVE markup like "<fontsize=12>",
# which is a distinct tag (no space before "size") that a bare "<font"
# terminator swallows by accident, truncating the source to nothing
# before the name is ever reached. Confirmed against real gamelogs: every
# incoming warp-scramble line uses <fontsize=12> immediately before the
# attacker's name, so this was not a hypothetical.
_SOURCE_RE = re.compile(
    r"<font[^>]*>\s*from\s*</font>\s*(?P<source>.+?)"
    r"(?:\s*<font(?=[\s=>])|\s*-\s*|\s*to\s*<|$)",
    re.IGNORECASE,
)
_SOURCE_FALLBACK_RE = re.compile(
    r"from\s+(?P<source>.+?)(?:\s+to\s+|\s+-\s+|$)", re.IGNORECASE
)
_MISS_RE = re.compile(r"\]\s*\(combat\)\s*(?P<source>.+?)\s+misses you", re.IGNORECASE)
_TAG_RE = re.compile(r"<.*?>")
_WS_RE = re.compile(r"\s+")
# Only a *leading* "[...]" is the log line's own timestamp. Matched
# anywhere else, this heuristic derails on the very sources it needs to
# read: a scramble source such as "Talia Renn [KVOS] Taranis" has a
# corp-ticket "] " of its own, and un-anchored partitioning happily eats
# the name in front of it, same as the timestamp.
_LEADING_TIMESTAMP_RE = re.compile(r"^\[.*?\]\s*")


class Match(NamedTuple):
    event: str
    source: str


def strip_markup(text: str) -> str:
    """Tags out, whitespace collapsed, leading timestamp dropped.

    The timestamp has to go before is_likely_npc sees the text: it is
    full of digits and brackets, and every NPC would read as a player.
    Only the leading bracket is a timestamp -- see _LEADING_TIMESTAMP_RE.
    """
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    return _LEADING_TIMESTAMP_RE.sub("", clean, count=1).strip()


# A bare name is NOT reliably an NPC: the real gamelog corpus has EVE's
# own client dropping a player's [Corp](Hull) tag entirely in wormhole
# space, where there is no local channel to resolve a pilot's info
# against. "Doran Velk" dealt hundreds of points of real damage and
# ran a real warp disruption with no bracket anywhere in the line;
# "Rendik Ashvale" and "Zarknabbertide Dovek" did the same across
# several unrelated fights. Any of those, treated as an NPC, is the
# exact silent-while-a-player-shoots-you failure this feature exists to
# prevent.
#
# Sleeper wormhole rats are the one bare-name vocabulary this heuristic
# can actually trust, because it is this product's own PvE content (a
# wormhole multiboxing toolkit, per PRODUCT.md) and CCP has kept it
# closed and stable for years: one adjective from this set in front of a
# rank word, and no player can register a character named that. CONCORD
# and empire police, and deployable sentry towers, are the same kind of
# reserved wording and appear the same way in the corpus.
#
# Anything bare that does not match is left unclassified -- including
# the Triglavian invasion's NPCs, which CCP deliberately names with
# ordinary-sounding human names attached to the same hulls (Drekavac,
# Leshak, Kikimora, ...) real players fly, making them genuinely
# indistinguishable from a player by name alone. Guessing at other
# regions' NPC vocabularies (Guristas, Sansha, Blood Raiders, ...) here
# would be inventing signal this corpus never tested. An extra alert
# during ratting is noise; a missed one during a fight is not, so the
# default for anything bare and unrecognised is "not an NPC".
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
    parentheses, and player drones (in damage lines) as "Name's Hull" --
    that punctuation is a reliable "not an NPC" signal, since no NPC has
    a corp. A bare name with none of it is NOT the mirror image: see the
    module-level comment above _NPC_ADJECTIVES for why guessing "no
    punctuation means NPC" is unsafe, and why only a closed, known-safe
    vocabulary is trusted for the positive case. It is a heuristic,
    which is why pve_filter is a toggle.

    A "misses you" line never carries this punctuation for anyone --
    confirmed against the real gamelog corpus, where both "Sleepless
    Patroller misses you completely" (NPC) and "Farrowmark misses you
    completely" (a player, confirmed by that same name's bracketed
    damage lines moments later) render as a bare name. match_line does
    not route miss sources through here for exactly that reason; see its
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


def _extract_source(line: str) -> str:
    m = _SOURCE_RE.search(line)
    if m:
        return strip_markup(m.group("source"))
    m = _SOURCE_FALLBACK_RE.search(strip_markup(line))
    if m:
        return m.group("source").strip()
    return ""


def match_line(line: str) -> Match | None:
    """The only entry point. None means "not interesting"."""
    if not line:
        return None
    lower = line.lower()

    if "(combat)" in lower:
        if _INCOMING_COLOR in lower and "from</font>" in lower.replace(" ", ""):
            return Match("combat", _extract_source(line))
        m = _MISS_RE.search(line)
        if m:
            # A miss line's source is a bare name whether the attacker is
            # a player or an NPC -- confirmed against the real corpus,
            # where neither ever carries a corp ticket or hull. Passing
            # it to is_likely_npc would silently drop the miss for any
            # real player, the exact false negative this feature exists
            # to prevent, so (like decloak) it gets no source to test.
            return Match("combat", "")
        if (
            "warp scramble attempt" in lower
            or "warp disruption attempt" in lower
            or "warp disruption zone" in lower
        ):
            return Match("warp_scramble", _extract_source(line))

    if "(notify)" in lower and "cloak deactivates" in lower:
        return Match("decloak", "")

    return None
