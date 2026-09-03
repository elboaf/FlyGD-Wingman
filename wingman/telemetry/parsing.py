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
# ever reached.
_SOURCE_RE = re.compile(
    r"<font[^>]*>\s*from\s*</font>\s*(?P<source>.+?)"
    r"(?:\s*<font(?=[\s=>])|\s*-\s*|\s*to\s*<|$)",
    re.IGNORECASE,
)
_SOURCE_FALLBACK_RE = re.compile(
    r"from\s+(?P<source>.+?)(?:\s+to\s+|\s+-\s+|$)", re.IGNORECASE
)
_TARGET_RE = re.compile(
    r"<font[^>]*>\s*to\s*(?:</font>)?\s*<b>(?P<target>.*)$", re.IGNORECASE
)
_TARGET_FALLBACK_RE = re.compile(r"^.*\bto\s+(?P<target>.+)$", re.IGNORECASE)
_MISS_RE = re.compile(r"\]\s*\(combat\)\s*(?P<source>.+?)\s+misses you", re.IGNORECASE)
_TAG_RE = re.compile(r"<.*?>")
_WS_RE = re.compile(r"\s+")
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
    if not target:
        return False
    text = target.strip().rstrip("!").strip()
    if text.lower() == "you":
        return True
    name = (character or "").strip()
    if not name:
        return False
    lowered, wanted = text.lower(), name.lower()
    if lowered == wanted:
        return True
    ticker = lowered.find("[")
    if ticker != -1:
        return lowered[:ticker].strip() == wanted
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
    return _extract_amount(line), target.strip(), source.strip()


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
