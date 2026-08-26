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
# A warp-attempt line names its target as well as its source, and the
# target is the only thing that says whose alert it is. EVE writes these
# notifications into EVERY fleet member's gamelog -- confirmed against a
# live install, where one disruption line appeared verbatim in four
# different characters' logs, none of them either party -- so without
# reading the target, one tackle arms every preview on the screen. In a
# real Gamelogs folder 5238 of 5839 warp lines are not the pilot reading
# them: 4674 name two other pilots entirely, and a further 564 are that
# pilot's OWN outgoing tackle, which lit their preview just as wrongly.
#
# The terminator problem _SOURCE_RE documents does not arise here: the
# target runs to end of line in every real shape, so this captures the
# rest and lets strip_markup do the work.
#
# The optional "</font>" is not speculative. Warp lines render the
# preposition as "<font size=10>to <b>", but the SAME folder renders
# other message types as "<font size=10>to</font> <b>" a quarter of a
# million times, and a warp line that ever adopted that shape would fall
# through to the fallback below -- which is where the "Yoshi To" problem
# in its comment starts biting.
_TARGET_RE = re.compile(
    r"<font[^>]*>\s*to\s*(?:</font>)?\s*<b>(?P<target>.*)$", re.IGNORECASE
)
# Leading ".*" is load-bearing: it is greedy, so this anchors on the LAST
# " to " in the line rather than the first. The source half sits to the
# left and can contain the word, which is not hypothetical -- the corpus
# has a pilot named "Yoshi To", and a leftmost match on
# "from Yoshi To [SUNGR] Exequror Navy Issue to Mpmoller1 [I P A]
# Hyperion" returns everything after the pilot's SURNAME as the target.
# That is worse than returning nothing: a non-empty wrong target passes
# the gate's emptiness check and then silently fails to match anyone, so
# a real tackle goes quiet with no error anywhere.
_TARGET_FALLBACK_RE = re.compile(r"^.*\bto\s+(?P<target>.+)$", re.IGNORECASE)
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
    damage lines moments later) render as a bare name. That used to mean
    a miss source could not be handed to this function at all: under the
    old "no punctuation means NPC" reading, every miss -- Farrowmark's
    included -- would have come back True. Under the closed allowlist
    above it is safe: "Sleepless Patroller" matches the NPC vocabulary
    and returns True, "Farrowmark" matches nothing and returns False, so
    match_line DOES route miss sources through here now; see its
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


def _extract_target(line: str) -> str:
    m = _TARGET_RE.search(line)
    if m:
        return strip_markup(m.group("target"))
    m = _TARGET_FALLBACK_RE.search(strip_markup(line))
    if m:
        return m.group("target").strip()
    return ""


def _target_is_character(target: str, character: str) -> bool:
    """True when *target* is the pilot whose log this line came from.

    Two real renderings, both confirmed against a live install's corpus:
    the log's own pilot appears either as the literal "you!" (594 lines)
    or spelled out by name with corp ticker and hull, exactly as a third
    party would be (the shape tests/fixtures/gamelogs/npc_scramble.txt
    carries). Only checking for "you!" would go silent during a real
    tackle rendered the second way, which is this feature's worst
    failure mode.

    A target that could not be extracted returns False -- i.e. no alert.
    That is the uncomfortable direction for this module, which elsewhere
    prefers noise to silence, but the ratio decides it: 5238 of 5839 real
    warp lines (90%) are not the pilot reading them, so treating an
    unreadable target as "probably mine" restores the
    every-preview-flashes bug wholesale rather than risking one missed
    alert.

    What keeps that branch off the hot path is _TARGET_RE, not this
    function: the corpus test asserts the PRIMARY pattern matches every
    real warp line, so the fallback -- and with it an empty target --
    never runs today. The sharper failure is not an empty target anyway
    but a non-empty WRONG one, which clears the check below and then
    matches nobody; that is what the greedy anchor on
    _TARGET_FALLBACK_RE exists to prevent.
    """
    if not target:
        return False
    # The trailing "!" belongs to EVE's phrasing ("to you!"), not the name.
    text = target.strip().rstrip("!").strip()
    if text.lower() == "you":
        return True
    name = (character or "").strip()
    if not name:
        return False
    lowered, wanted = text.lower(), name.lower()
    if lowered == wanted:
        return True
    # A corp ticker ends the name exactly, so when one is present compare
    # against just that much. EVE names are two OR three words, which
    # makes a prefix test alone genuinely wrong rather than merely loose:
    # "Bob Smith" is a word-boundary prefix of the equally valid name
    # "Bob Smith Jones", so without this a pilot would alert for a
    # fleet-mate whose name simply starts the same way.
    ticker = lowered.find("[")
    if ticker != -1:
        return lowered[:ticker].strip() == wanted
    # No ticker: EVE's own client renders a pilot it cannot resolve as a
    # bare "Name Hull" with no bracket anywhere (the shape documented
    # above _NPC_ADJECTIVES, confirmed against real fights). There is
    # nothing to anchor on, so fall back to a boundary-checked prefix --
    # loose in the "Bob Smith Jones" case above, but the alternative is
    # going silent on a real tackle, which this module consistently
    # treats as the worse error.
    return lowered.startswith(wanted) and lowered[len(wanted)] == " "


def _extract_source(line: str) -> str:
    m = _SOURCE_RE.search(line)
    if m:
        return strip_markup(m.group("source"))
    m = _SOURCE_FALLBACK_RE.search(strip_markup(line))
    if m:
        return m.group("source").strip()
    return ""


def match_line(line: str, character: str) -> Match | None:
    """The only entry point. None means "not interesting".

    *character* is the Listener of the log the line came from -- the
    pilot this line is being read on behalf of.
    """
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
            # where neither ever carries a corp ticket or hull. That used
            # to mean handing it to is_likely_npc would drop every real
            # player's miss under the old "bare means NPC" reading. The
            # heuristic is a closed allowlist now (see is_likely_npc):
            # only a recognised Sleeper/police/sentry prefix returns
            # True, so preserving the source is SAFE and strictly
            # better -- an NPC miss ("Sleepless Patroller misses you")
            # is correctly filtered, and an unrecognised bare name (a
            # real player, e.g. "Farrowmark misses you") still returns
            # False and alerts.
            return Match("combat", strip_markup(m.group("source")))
        if (
            "warp scramble attempt" in lower
            or "warp disruption attempt" in lower
            # Dead, and now dead twice over: real bubble lines read
            # "(notify) You are within a warp disruption zone", so this
            # never matched inside a (combat) branch, and the gate below
            # rejects it a second time because that phrasing names no
            # target. Left for a separate change -- moving it to the
            # (notify) branch alongside decloak puts it outside this
            # gate, which is right, since the wording is already
            # self-referential.
            or "warp disruption zone" in lower
        ):
            # The ownership gate. Damage lines get this for free: they
            # name no target at all, so _INCOMING_COLOR alone settles
            # whose they are. (34 of 44950 distinct incoming-damage lines
            # do appear verbatim in more than one pilot's log, which is
            # what identically-fit fleetmates taking the same bomb looks
            # like -- 0.08%, nowhere near a broadcast rate.) A warp line
            # has neither property: it is broadcast to the whole fleet
            # AND it names both parties, so the target has to be read and
            # compared against this log's pilot. This also drops
            # the outgoing case ("from you to X"), for the same reason
            # test_outgoing_damage_does_not_alert drops outgoing damage:
            # the alert means "I cannot leave", and holding someone else
            # is the opposite of that.
            if not _target_is_character(_extract_target(line), character):
                return None
            return Match("warp_scramble", _extract_source(line))

    if "(notify)" in lower and "cloak deactivates" in lower:
        return Match("decloak", "")

    return None
