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
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

UTC = datetime.timezone.utc

logger = logging.getLogger(__name__)

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


# Plain Documents first, then the OneDrive-redirected location. Redirected
# Documents folders are common enough that omitting the second candidate
# presents as "no logs found" for a working install.
_GAMELOGS_SUFFIX = ("EVE", "logs", "Gamelogs")


def find_gamelogs_dir(home: Path | None = None) -> Path | None:
    """Locate the EVE Gamelogs folder, or None if it cannot be found."""
    base = Path(home) if home is not None else Path.home()
    for documents in (base / "Documents", base / "OneDrive" / "Documents"):
        candidate = documents.joinpath(*_GAMELOGS_SUFFIX)
        if candidate.is_dir():
            return candidate
    return None


WINDOW_PADDING = datetime.timedelta(minutes=5)
MAX_FILES = 64

# Stat-avoidance only, NOT a correctness filter. entry.stat() is ~4.6ms on a
# WSL 9p mount, so stat'ing every file in a folder spanning months costs ~25s.
# A log can only overlap the window if its session was still being written
# then, so one that started this long before it can be skipped without a
# stat. Deliberately generous: the bound only needs to exceed the longest
# plausible continuous EVE client session, and being wrong costs one missing
# log, so 30 days rather than something tight.
MAX_SESSION_SPAN = datetime.timedelta(days=30)

# EVE names gamelogs YYYYMMDD_HHMMSS_<characterID>.txt, and that timestamp is
# exactly the Session Started value — verified across a real folder.
_FILENAME_RE = re.compile(r"^(\d{8})_(\d{6})(?:_\d+)?\.txt$", re.IGNORECASE)


@dataclass(frozen=True)
class SelectedLog:
    path: Path
    listener: str
    span_start: datetime.datetime
    span_end: datetime.datetime


@dataclass(frozen=True)
class Selection:
    logs: list[SelectedLog]
    dropped: int


def _require_utc(name: str, value: datetime.datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != datetime.timedelta(0):
        raise ValueError(
            f"{name} must be a timezone-aware UTC datetime; got {value!r}. "
            "Gamelog timestamps are UTC and VideoInfo.mtime is local, so "
            "passing local time selects the wrong hour with no error."
        )


def _filename_start(name: str) -> datetime.datetime | None:
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(
            m.group(1) + m.group(2), "%Y%m%d%H%M%S"
        ).replace(tzinfo=UTC)
    except ValueError:
        return None


def select_logs(directory, start_utc, end_utc, *, max_files: int = MAX_FILES) -> Selection:
    """Gamelogs overlapping [start_utc, end_utc] padded by WINDOW_PADDING.

    Both bounds must be timezone-aware UTC — see the module docstring.
    """
    _require_utc("start_utc", start_utc)
    _require_utc("end_utc", end_utc)
    if end_utc < start_utc:
        start_utc, end_utc = end_utc, start_utc
    window_start = start_utc - WINDOW_PADDING
    window_end = end_utc + WINDOW_PADDING

    try:
        entries = list(os.scandir(Path(directory)))
    except OSError:
        return Selection(logs=[], dropped=0)

    matched: list[SelectedLog] = []
    stat_skipped = 0
    session_span_floor = window_start - MAX_SESSION_SPAN
    for entry in entries:
        if not entry.name.lower().endswith(".txt"):
            continue

        # Stat-avoidance guard (see MAX_SESSION_SPAN): a filename that parses
        # and starts long before the window cannot possibly still be being
        # written during it, so skip the stat() entirely. A filename that
        # does NOT parse must still fall through to stat() and the header
        # read -- an unexpected naming scheme degrades to doing more work,
        # never to silently skipping logs.
        name_start = _filename_start(entry.name)
        if name_start is not None and name_start < session_span_floor:
            stat_skipped += 1
            continue

        try:
            if not entry.is_file():
                continue
            last_write = datetime.datetime.fromtimestamp(entry.stat().st_mtime, UTC)
        except OSError:
            continue

        # Both predicates are cheap (name + scandir stat, no file opened) and
        # BOTH are needed. Filtering on session start alone excludes only logs
        # that began after the window closed -- of which there are none for a
        # recent recording -- so it removes essentially nothing. It is
        # last-write that excludes the thousands of historical logs.
        if last_write < window_start:
            continue
        if name_start is not None and name_start > window_end:
            continue

        # An unparseable name falls through to a header read rather than being
        # discarded, so an unexpected naming scheme degrades to reading
        # everything instead of silently skipping logs.
        header = parse_header(Path(entry.path))
        if header is None:
            continue
        if header.session_start > window_end or last_write < window_start:
            continue
        matched.append(
            SelectedLog(
                path=Path(entry.path),
                listener=header.listener,
                span_start=header.session_start,
                span_end=last_write,
            )
        )

    matched.sort(key=lambda log: log.span_end, reverse=True)
    dropped = max(0, len(matched) - max_files)
    if stat_skipped:
        logger.debug(
            "skipped %d logs older than the session-span guard (%s)",
            stat_skipped,
            MAX_SESSION_SPAN,
        )
    return Selection(logs=matched[:max_files], dropped=dropped)
