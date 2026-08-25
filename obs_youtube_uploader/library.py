"""Video discovery, metadata, and deletion.

Pure filesystem logic with no GUI dependency: the old VideoEntry held a
tk.BooleanVar, which made it impossible to test. Selection state now lives
in the UI layer; this module deals only in data.
"""

import datetime
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTS = {".mkv", ".mp4", ".flv", ".mov", ".avi", ".ts", ".m4v", ".webm"}

# Avoids a flashed console window per ffprobe call in a console=False
# PyInstaller build — this runs once per file on every list refresh.
# CREATE_NO_WINDOW doesn't exist off Windows, and the test suite injects
# fake runners on Linux, so this must stay a no-op there.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


def format_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_date(mtime: float, now: datetime.datetime | None = None) -> str:
    """How long ago the file was last written, not when.

    Relative, deliberately. This column sits beside a filename that already
    carries OBS's own recording timestamp ("Fight 2026-08-21 06-49-29.mkv"),
    and an absolute time here read as that same fact printed twice -- except
    that it is NOT the same fact. This is the file's mtime, so a recording
    that was copied or remuxed shows a time minutes or hours off the one in
    its name. Two nearly-equal timestamps that disagree look like a bug in
    the app rather than like two different facts, which is exactly how it
    was reported.

    A relative string cannot be mistaken for the name's timestamp, and it
    answers the question the column is actually for: is this recent?

    Precision degrades with age on purpose -- minutes matter for something
    recorded during this session and are noise for something from March, so
    anything a week or more old falls back to a calendar date (with the year
    only when it is not the current one, which is what this function did
    before and is still the tightest useful form).

    Safe to change ONLY because no sort reads the rendered string:
    list.js's date branch orders by delivery index, since Python delivers
    rows newest-first. A sort keyed on this text would put "Aug" before
    "Dec", and "2 days ago" before "3h ago".

    `now` is injectable so every branch is testable without waiting for the
    clock -- the same convention as discover()'s runner=. It matters more
    now than it did for the year branch alone: every threshold here is
    relative to it.
    """
    when = datetime.datetime.fromtimestamp(mtime)  # noqa: DTZ006 - local wall-clock, shown to the user
    if now is None:
        now = datetime.datetime.now()  # noqa: DTZ005 - local wall-clock, shown to the user

    seconds = (now - when).total_seconds()
    # Future mtimes are real: a clock correction, a bad archive, a file
    # copied off a machine with a skewed clock. Fall through to the
    # calendar form rather than rendering "-3h ago".
    if seconds < 0:
        pass
    elif seconds < 90:
        return "just now"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    elif seconds < 172800:
        return "yesterday"
    elif seconds < 604800:
        return f"{int(seconds // 86400)}d ago"

    if when.year == now.year:
        return when.strftime("%b %d")
    return when.strftime("%Y %b %d")


@dataclass
class VideoInfo:
    path: Path
    mtime: float
    size: int
    duration: float | None
    # False while a background probe is still outstanding. Distinguishes
    # "not measured yet" from "measured, and ffprobe could not read it" --
    # both of which leave `duration` None, but which mean opposite things
    # to the combat-log upload (app._start_combat_log_upload). Defaults to
    # True so every existing construction keeps meaning "this is final".
    probed: bool = True
    # Whether a None duration is an ANSWER or the absence of one. probe()
    # already draws this line for the cache's sake -- a no-verdict result
    # must never be stored, or one antivirus quarantine of ffprobe.exe pins
    # a recording to "?" forever -- and the COLUMN has to draw it too. It
    # did not, and the consequence was visible on any install where
    # ffprobe was never found at all: every row rendered "?", whose help
    # text says "ffprobe could not open this file", diagnosing a file that
    # was never read; and the selection summary printed a confident
    # "0:00:00" for a 108.8 MB recording, because a no-verdict row looked
    # exactly like a finished one and so earned no partial marker. The two
    # states leave `duration` None together and mean opposite things: one
    # is about the recording, the other is about the install.
    # Defaults True for the same reason `probed` does.
    answered: bool = True

    @property
    def date_str(self) -> str:
        # Delegates rather than formatting inline so the format has exactly
        # one definition and can be tested without constructing a VideoInfo
        # (and therefore without touching the filesystem).
        return format_date(self.mtime)

    @property
    def size_str(self) -> str:
        return format_size(self.size)

    @property
    def duration_str(self) -> str:
        if not self.probed:
            return "…"
        if self.duration is None:
            # Three states, not two. "?" blames the file; the dash blames
            # the install. See `answered` above for what shipped while
            # these shared one glyph.
            return "?" if self.answered else "—"
        minutes, seconds = divmod(int(self.duration), 60)
        return f"{minutes}:{seconds:02d}"


def discover(directory: Path) -> list[Path]:
    """Video files in *directory*, newest first. Missing directory -> [].

    Skips files that disappear between iterdir and stat (race condition
    in active directories), rather than aborting the scan.
    """
    entries = []
    try:
        for p in Path(directory).iterdir():
            try:
                # is_file() stats too, so it belongs inside the guard. Left
                # outside, one unreadable entry raises out of the loop and
                # the outer handler returns [] -- turning a single bad file
                # into an empty recording list for the whole folder.
                if not (p.is_file() and p.suffix.lower() in VIDEO_EXTS):
                    continue
                # Stat exactly once, inside guarded region
                stat_result = p.stat()
                entries.append((p, stat_result.st_mtime))
            except OSError:
                # Skip files that disappear or cannot be read between
                # iterdir and stat; the rest of the scan still counts.
                continue
    except OSError:
        return []
    # Sort by mtime, newest first
    entries.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in entries]


def probe(
    path: Path, ffprobe_bin: str | None, runner=subprocess.run
) -> tuple[float | None, bool]:
    """Duration in seconds, plus whether the answer is worth remembering.

    Returns ``(duration, definitive)``. ``definitive`` is True only when
    ffprobe actually ran and gave a verdict about this file -- a duration,
    a non-zero exit, or output that is not a number. It is False when the
    probe never got a verdict: no binary configured, the process could not
    be launched, or it hit the timeout.

    That distinction is what keeps a cached failure safe. Both kinds look
    identical from the outside (None), but caching the second kind is a
    trap: the cache key is (size, mtime), which never changes again for a
    finished recording, so a single antivirus quarantine of ffprobe.exe or
    one timeout under disk load would pin that recording to "?" forever --
    and, because the combat-log upload refuses on a missing duration, would
    permanently block log uploads for it with a message blaming ffprobe.
    Restoring the binary would not help. Only a definitive verdict is
    allowed into the cache.
    """
    if not ffprobe_bin:
        return None, False
    try:
        result = runner(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            **_NO_WINDOW_KWARGS,
        )
    except Exception:  # noqa: BLE001 - could not launch, or timed out; not a verdict
        # Could not launch, or timed out. Says nothing about the file.
        return None, False
    if result.returncode != 0 or not result.stdout.strip():
        return None, True  # ffprobe ran and could not read a duration.
    try:
        return float(result.stdout.strip()), True
    except ValueError:
        return None, True


def probe_duration(
    path: Path, ffprobe_bin: str | None, runner=subprocess.run
) -> float | None:
    """Duration in seconds, or None if ffprobe is absent or fails.

    Returning None rather than raising is deliberate: a missing ffprobe
    degrades the duration column to "?" instead of blocking the app. Use
    ``probe`` when the caller needs to tell a real verdict apart from a
    probe that never ran.
    """
    duration, _ = probe(path, ffprobe_bin, runner=runner)
    return duration


def stat_info(path: Path) -> VideoInfo:
    """Everything about a recording that costs no subprocess.

    Split out of build_info so the window can draw its rows from a plain
    stat and let durations fill in afterwards, instead of blocking the Tk
    main thread on one ffprobe per file before showing anything at all.
    """
    stat = path.stat()
    return VideoInfo(
        path=path, mtime=stat.st_mtime, size=stat.st_size, duration=None, probed=False
    )


def build_info(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> VideoInfo:
    """Stat plus a synchronous probe, in one call.

    Nothing in the app uses this any more: the list view builds rows from
    stat_info and fills durations in from the cache or a background probe,
    and app._probe_now resolves a selection by calling probe_duration on
    infos it already holds. Kept as the module's straightforward "give me
    everything about this file" entry point, and still covered by tests.
    """
    stat = path.stat()
    return VideoInfo(
        path=path,
        mtime=stat.st_mtime,
        size=stat.st_size,
        duration=probe_duration(path, ffprobe_bin, runner=runner),
    )


def delete(items: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    """Permanently delete *items*.

    One failure does not abort the batch. Returns (deleted_count, failures)
    where each failure is (path, error_message).
    """
    deleted = 0
    failures: list[tuple[Path, str]] = []
    for path in items:
        try:
            path.unlink()
            deleted += 1
        except OSError as exc:
            failures.append((path, str(exc)))
    return deleted, failures
