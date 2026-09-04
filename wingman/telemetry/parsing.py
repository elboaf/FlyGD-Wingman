"""Pure telemetry parsing for EVE combat and notify lines."""

from __future__ import annotations

import datetime
import re

from .model import ParsedFact, ParsedLine

UTC = datetime.UTC

# Incoming damage is red. Outgoing is not, and that colour code is the only
# thing separating "someone is shooting me" from "I am shooting".
_INCOMING_COLOR = "0xffcc0000"
_OUTGOING_COLOR = "0xff00ffff"

# The lookahead on <font excludes real EVE markup like "<fontsize=12>", which
# is a distinct tag (no space before "size") that a bare "<font" terminator
# swallows by accident, truncating the source to nothing before the name is
# ever reached. Confirmed against real gamelogs: every incoming
# warp-scramble line uses <fontsize=12> immediately before the attacker's
# name, so this was not a hypothetical.
_SOURCE_RE = re.compile(
    r"<font[^>]*>\s*from\s*</font>\s*(?P<source>.+?)"
    r"(?:\s*<font(?=[\s=>])|\s*-\s*|\s*to\s*<|$)",
    re.IGNORECASE,
)
_SOURCE_FALLBACK_RE = re.compile(
    r"from\s+(?P<source>.+?)(?:\s+to\s+|\s+-\s+|$)", re.IGNORECASE
)
# A warp-attempt line names its target as well as its source, and the target
# is the only thing that says whose event it is. EVE writes these
# notifications into EVERY fleet member's gamelog -- confirmed against a live
# install, where one disruption line appeared verbatim in four different
# characters' logs, none of them either party -- so without reading the
# target, one tackle arms every preview on the screen. In a real Gamelogs
# folder 5238 of 5839 warp lines are not the pilot reading them: 4674 name two
# other pilots entirely, and a further 564 are that pilot's OWN outgoing
# tackle, which lit their preview just as wrongly.
#
# The terminator problem _SOURCE_RE documents does not arise here: the target
# runs to end of line in every real shape, so this captures the rest and lets
# strip_markup do the work.
#
# The optional "</font>" is not speculative. Warp lines render the preposition
# as "<font size=10>to <b>", but the SAME folder renders other message types
# as "<font size=10>to</font> <b>" a quarter of a million times, and a warp
# line that ever adopted that shape would fall through to the fallback below --
# which is where the "Yoshi To" problem in its comment starts biting.
_TARGET_RE = re.compile(
    r"<font[^>]*>\s*to\s*(?:</font>)?\s*<b>(?P<target>.*)$", re.IGNORECASE
)
# Leading ".*" is load-bearing: it is greedy, so this anchors on the LAST
# " to " in the line rather than the first. The source half sits to the left
# and can contain the word, which is not hypothetical -- the corpus has a
# pilot named "Yoshi To", and a leftmost match on
# "from Yoshi To [SUNGR] Exequror Navy Issue to Mpmoller1 [I P A] Hyperion"
# returns everything after the pilot's SURNAME as the target. That is worse
# than returning nothing: a non-empty wrong target passes the gate's emptiness
# check and then silently fails to match anyone, so a real tackle goes quiet
# with no error anywhere.
_TARGET_FALLBACK_RE = re.compile(r"^.*\bto\s+(?P<target>.+)$", re.IGNORECASE)
# A miss line's source is a bare name whether the attacker is a player or an
# NPC -- confirmed against the real corpus, where neither ever carries a corp
# ticker or hull. Preserving the source is therefore load-bearing: downstream
# policy needs it to distinguish a recognised Sleeper/police/sentry miss from a
# real player miss.
_MISS_RE = re.compile(r"\]\s*\(combat\)\s*(?P<source>.+?)\s+misses you", re.IGNORECASE)
_TAG_RE = re.compile(r"<.*?>")
_WS_RE = re.compile(r"\s+")
# Only a *leading* "[...]" is the log line's own timestamp. Matched anywhere
# else, this heuristic derails on the very sources it needs to read: a
# scramble source such as "Talia Renn [KVOS] Taranis" has a corp-ticket "] "
# of its own, and un-anchored partitioning happily eats the name in front of
# it, same as the timestamp.
_LEADING_TIMESTAMP_RE = re.compile(r"^\[.*?\]\s*")
_TIMESTAMP_RE = re.compile(
    r"^\[\s*(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})"
    r"\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\s*\]"
)
_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\s*(?P<stamp>[^\]]+)\s*\]")
_AMOUNT_RE = re.compile(
    r"\(combat\)\s*<color=[^>]+><b>(?P<amount>[\d,]+)</b>", re.IGNORECASE
)
_OUTGOING_TEXT_RE = re.compile(
    r"^\(combat\)\s+(?P<amount>[\d,]+)\s+to\s+(?P<rest>.+)$", re.IGNORECASE
)


def strip_markup(text: str) -> str:
    """Tags out, whitespace collapsed, leading timestamp dropped.

    The timestamp has to go before policy sees the text: it is full of digits
    and brackets, and every NPC would read as a player. Only the leading
    bracket is a timestamp -- see _LEADING_TIMESTAMP_RE.
    """
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    return _LEADING_TIMESTAMP_RE.sub("", clean, count=1).strip()


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

    Two real renderings, both confirmed against a live install's corpus: the
    log's own pilot appears either as the literal "you!" (594 lines) or
    spelled out by name with corp ticker and hull, exactly as a third party
    would be (the shape tests/fixtures/gamelogs/npc_scramble.txt carries). Only
    checking for "you!" would go silent during a real tackle rendered the
    second way, which is this feature's worst failure mode.

    A target that could not be extracted returns False -- i.e. no fact. That is
    the uncomfortable direction for this module, which elsewhere prefers noise
    to silence, but the ratio decides it: 5238 of 5839 real warp lines (90%)
    are not the pilot reading them, so treating an unreadable target as
    "probably mine" restores the every-preview-flashes bug wholesale rather
    than risking one missed alert.

    What keeps that branch off the hot path is _TARGET_RE, not this function:
    the corpus test asserts the PRIMARY pattern matches every real warp line,
    so the fallback -- and with it an empty target -- never runs today. The
    sharper failure is not an empty target anyway but a non-empty WRONG one,
    which clears the check below and then matches nobody; that is what the
    greedy anchor on _TARGET_FALLBACK_RE exists to prevent.
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
    # against just that much. EVE names are two OR three words, which makes a
    # prefix test alone genuinely wrong rather than merely loose: "Bob Smith"
    # is a word-boundary prefix of the equally valid name "Bob Smith Jones",
    # so without this a pilot would answer for a fleet-mate whose name simply
    # starts the same way.
    ticker = lowered.find("[")
    if ticker != -1:
        return lowered[:ticker].strip() == wanted
    # No ticker: EVE's own client renders a pilot it cannot resolve as a bare
    # "Name Hull" with no bracket anywhere (the shape documented above
    # _SOURCE_RE/_TARGET_RE, confirmed against real fights). There is nothing
    # to anchor on, so fall back to a boundary-checked prefix -- loose in the
    # "Bob Smith Jones" case above, but the alternative is going silent on a
    # real tackle, which this module consistently treats as the worse error.
    return (
        lowered.startswith(wanted)
        and len(lowered) > len(wanted)
        and lowered[len(wanted)] == " "
    )


def _extract_source(line: str) -> str:
    m = _SOURCE_RE.search(line)
    if m:
        return strip_markup(m.group("source"))
    m = _SOURCE_FALLBACK_RE.search(strip_markup(line))
    if m:
        return m.group("source").strip()
    return ""


def parse_timestamp(line: str) -> datetime.datetime | None:
    occurred_at, _error = _parse_timestamp_detail(line)
    return occurred_at


def parse_line(line: str, character: str) -> ParsedLine:
    occurred_at, timestamp_error = _parse_timestamp_detail(line)
    if not line:
        return ParsedLine(
            line=line,
            character=character,
            occurred_at=occurred_at,
            timestamp_error=timestamp_error,
        )

    lower = line.lower()
    facts: list[ParsedFact] = []

    if "(combat)" in lower:
        if _is_incoming_damage(lower):
            facts.append(
                ParsedFact(
                    kind="incoming_damage",
                    amount=_extract_amount(line),
                    source=_extract_source(line),
                )
            )
        else:
            miss = _MISS_RE.search(line)
            if miss:
                facts.append(
                    ParsedFact(
                        kind="incoming_miss", source=strip_markup(miss.group("source"))
                    )
                )
            elif _is_incoming_tackle(lower):
                target = _extract_target(line)
                if _target_is_character(target, character):
                    facts.append(
                        ParsedFact(
                            kind="incoming_tackle",
                            source=_extract_source(line),
                            target=target,
                        )
                    )
            elif _is_outgoing_damage(lower):
                details = _extract_outgoing_damage(line)
                if details is not None:
                    amount, target, source = details
                    facts.append(
                        ParsedFact(
                            kind="outgoing_damage",
                            amount=amount,
                            target=target,
                            source=source,
                        )
                    )

    if "(notify)" in lower and "cloak deactivates" in lower:
        facts.append(ParsedFact(kind="decloak"))

    return ParsedLine(
        line=line,
        character=character,
        occurred_at=occurred_at,
        facts=tuple(facts),
        timestamp_error=timestamp_error,
    )


def _parse_timestamp_detail(line: str) -> tuple[datetime.datetime | None, str | None]:
    match = _TIMESTAMP_RE.match(line)
    if match is not None:
        parts = {key: int(value) for key, value in match.groupdict().items()}
        try:
            return (
                datetime.datetime(tzinfo=UTC, **parts),
                None,
            )
        except ValueError as exc:
            return None, str(exc)
    prefix = _TIMESTAMP_PREFIX_RE.match(line)
    if prefix is not None:
        return None, f"malformed timestamp: {prefix.group('stamp').strip()}"
    return None, None


def _extract_amount(line: str) -> int | None:
    match = _AMOUNT_RE.search(line)
    if match is None:
        return None
    return int(match.group("amount").replace(",", ""))


def _extract_outgoing_damage(line: str) -> tuple[int | None, str, str] | None:
    plain = strip_markup(line)
    match = _OUTGOING_TEXT_RE.match(plain)
    if match is None:
        return None
    rest = match.group("rest")
    if " - " not in rest:
        return None
    target, remainder = rest.split(" - ", 1)
    if " - " not in remainder:
        return None
    source, _outcome = remainder.rsplit(" - ", 1)
    amount = _extract_amount(line)
    if amount is None:
        # Plain-text or tag-shape variants still carried the amount through
        # the markup-stripped expression that established this as outgoing.
        amount = int(match.group("amount").replace(",", ""))
    return amount, target.strip(), source.strip()


def _is_incoming_damage(lower: str) -> bool:
    return _INCOMING_COLOR in lower and "from</font>" in lower.replace(" ", "")


def _is_outgoing_damage(lower: str) -> bool:
    return _OUTGOING_COLOR in lower and "to</font>" in lower.replace(" ", "")


def _is_incoming_tackle(lower: str) -> bool:
    return (
        "warp scramble attempt" in lower
        or "warp disruption attempt" in lower
        or "warp disruption zone" in lower
    )
