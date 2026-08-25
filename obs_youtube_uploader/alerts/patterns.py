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

_SOURCE_RE = re.compile(
    r"<font[^>]*>\s*from\s*</font>\s*(?P<source>.+?)"
    r"(?:\s*<font|\s*-\s*|\s*to\s*<|$)",
    re.IGNORECASE,
)
_SOURCE_FALLBACK_RE = re.compile(
    r"from\s+(?P<source>.+?)(?:\s+to\s+|\s+-\s+|$)", re.IGNORECASE
)
_MISS_RE = re.compile(r"\]\s*\(combat\)\s*(?P<source>.+?)\s+misses you", re.IGNORECASE)
_TAG_RE = re.compile(r"<.*?>")
_WS_RE = re.compile(r"\s+")


class Match(NamedTuple):
    event: str
    source: str


def strip_markup(text: str) -> str:
    """Tags out, whitespace collapsed, timestamp dropped.

    The timestamp has to go before is_likely_npc sees the text: it is
    full of digits and brackets, and every NPC would read as a player.
    """
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    _head, sep, tail = clean.partition("] ")
    return tail.strip() if sep else clean


def is_likely_npc(source: str) -> bool:
    """A bare name is an NPC; a player carries punctuation.

    Player attackers render with a corp ticker in brackets and a hull in
    parentheses, and player drones as "Name's Hull". NPCs are a bare
    name. It is a heuristic, which is why pve_filter is a toggle.
    """
    if not source:
        return False
    if "'s " in source:
        return False
    return not any(ch in source for ch in "[]()")


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
            return Match("combat", strip_markup(m.group("source")))
        if (
            "warp scramble attempt" in lower
            or "warp disruption attempt" in lower
            or "warp disruption zone" in lower
        ):
            return Match("warp_scramble", _extract_source(line))

    if "(notify)" in lower and "cloak deactivates" in lower:
        return Match("decloak", "")

    return None
