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
_NO_WINDOW_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def format_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@dataclass
class VideoInfo:
    path: Path
    mtime: float
    size: int
    duration: float | None

    @property
    def date_str(self) -> str:
        return datetime.datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    @property
    def size_str(self) -> str:
        return format_size(self.size)

    @property
    def duration_str(self) -> str:
        if self.duration is None:
            return "?"
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


def probe_duration(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> float | None:
    """Duration in seconds, or None if ffprobe is absent or fails.

    Returning None rather than raising is deliberate: a missing ffprobe
    degrades the duration column to "?" instead of blocking the app.
    """
    if not ffprobe_bin:
        return None
    try:
        result = runner(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15, **_NO_WINDOW_KWARGS,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def build_info(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> VideoInfo:
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
