"""EVE combat log discovery, selection, and archiving.

Gamelog timestamps are UTC. Everything in this module that takes or returns a
datetime uses timezone-aware UTC, deliberately: the rest of this app works in
local time (VideoInfo.mtime is a POSIX timestamp rendered with
datetime.fromtimestamp), and comparing the two naively selects logs offset by
the local UTC offset — the wrong hour, or nothing, with no error raised.
Measured on a real folder: a log whose header reads 20:42:50 has an mtime of
21:55:16 UTC / 17:55:16 local. Only the UTC reading is coherent.
"""
import datetime
import re
from dataclasses import dataclass
from pathlib import Path

UTC = datetime.timezone.utc

# Real logs are CRLF, so both patterns tolerate trailing whitespace.
_LISTENER_RE = re.compile(r"^\s*Listener:\s*(.+?)\s*$")
_SESSION_RE = re.compile(
    r"^\s*Session Started:\s*(\d{4})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2}):(\d{2})"
)

# The header block is the first few lines; a character log can reach 1.6MB and
# there is no reason to read past it.
_HEADER_LINES = 10


@dataclass(frozen=True)
class LogHeader:
    listener: str
    session_start: datetime.datetime  # tz-aware UTC


def parse_header(path: Path) -> LogHeader | None:
    """Read a gamelog's header, or None if it is unusable.

    None means "do not select this log" for every reason: unreadable,
    truncated, malformed, or — most commonly — a client session where no
    character ever logged in. Those stubs are 47% of a real folder and carry
    no combat data, so excluding them here keeps them from consuming the
    file cap.
    """
    listener: str | None = None
    started: datetime.datetime | None = None
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            for _ in range(_HEADER_LINES):
                line = fh.readline()
                if not line:
                    break
                if listener is None:
                    m = _LISTENER_RE.match(line)
                    if m:
                        listener = m.group(1)
                        continue
                if started is None:
                    m = _SESSION_RE.match(line)
                    if m:
                        y, mo, d, h, mi, s = (int(g) for g in m.groups())
                        try:
                            started = datetime.datetime(y, mo, d, h, mi, s, tzinfo=UTC)
                        except ValueError:
                            return None
    except OSError:
        return None

    if listener is None or started is None:
        return None
    return LogHeader(listener=listener, session_start=started)
