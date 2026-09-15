"""Cut one clip out of a recording with a keyframe-aligned stream copy.

Everything here is pure and testable off Windows: the runner is injected,
the same way `stitch` is. The cut is deliberately NOT frame-accurate --
`-c copy` can only start a clip on an input keyframe, so the start snaps
to the nearest keyframe at or BEFORE the marker (a clip may begin a few
seconds early, never late or past the marker). That buys an instant cut
with zero quality loss; the editor shows the snapped times so the dialog
never promises frames the file cannot deliver.
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

_PROBE_TIMEOUT_S = 60
# A long recording's keyframe list is bounded by ffprobe's frame walk; a
# stuck probe must not hold a bridge thread past this.
_CUT_TIMEOUT_S = 600


class ClipError(RuntimeError):
    """ffmpeg failed to produce the clip."""


def keyframes(path: Path, ffprobe_bin: str, runner=subprocess.run) -> list[float]:
    """Keyframe timestamps of the first video stream, in seconds.

    `-skip_frame nokey` makes the decoder walk only keyframes, which is
    what keeps a multi-hour recording to seconds of probe. Any answer that
    fails to parse -- missing ffprobe, a nonzero exit, an audio-only file,
    junk on stderr -- comes back as an empty list, and the CALLER decides
    the fallback: no known keys means the marker positions stand as given
    and ffmpeg's own seek finds a keyframe, rather than the editor refusing.
    """
    try:
        result = runner(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-skip_frame",
                "nokey",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=pts_time",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            **_NO_WINDOW_KWARGS,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Keyframe probe could not run for %s", path, exc_info=True)
        return []
    if result.returncode != 0:
        return []
    keys = []
    for line in result.stdout.splitlines():
        try:
            keys.append(float(line.strip()))
        except ValueError:
            continue
    return sorted(set(keys))


def snap_start(start: float, keys: list[float], duration: float) -> float:
    """The start marker snapped DOWN to the nearest keyframe.

    A stream-copy clip cannot open mid-GOP, so the honest start is the
    last keyframe at or before the marker: snapping later would drop the
    user's own in-point. With no usable keys, the marker stands and
    ffmpeg's own seek finds a keyframe. Clamped inside the recording so a
    marker past the end can never produce a start at or beyond it.
    """
    candidates = [k for k in keys if k <= start]
    snapped = candidates[-1] if candidates else 0.0
    return min(snapped, max(0.0, duration))


def snap_end(end: float, duration: float) -> float:
    """The end marker clamped inside the recording."""
    return max(0.0, min(end, duration))


def build_cut_command(
    src: Path, out_path: Path, start: float, seconds: float, ffmpeg_bin: str
) -> list[str]:
    """Keyframe seek + relative length + stream copy.

    `-ss` BEFORE `-i` seeks by keyframe -- instant, and exactly the cut
    point `snap_start` already promised. The length is `-t` relative to
    the seek rather than `-to` absolute, because `-to` after an input seek
    counts from the NEW zero and would silently cut the wrong span.
    """
    return [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{seconds:.3f}",
        "-c",
        "copy",
        str(out_path),
    ]


def clip_path(folder: Path, stem: str) -> Path:
    """`<stem> - clip.mkv`, collision-suffixed ` - clip (2)`, and so on."""
    base = f"{stem} - clip"
    candidate = folder / f"{base}.mkv"
    n = 2
    while candidate.exists():
        candidate = folder / f"{base} ({n}).mkv"
        n += 1
    return candidate


def cut(
    src: Path,
    out_path: Path,
    start: float,
    seconds: float,
    ffmpeg_bin: str,
    runner=subprocess.run,
) -> Path:
    """Run the cut. Returns out_path; raises ClipError on any failure.

    A failed cut must not leave a half-written file that the list would
    announce as a finished recording, so the candidate is unlinked on
    every failure path -- the same trade stitch.py records for its temps.
    """
    seconds = max(0.001, seconds)
    try:
        result = runner(
            build_cut_command(src, out_path, start, seconds, ffmpeg_bin),
            capture_output=True,
            text=True,
            timeout=_CUT_TIMEOUT_S,
            **_NO_WINDOW_KWARGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _discard(out_path)
        raise ClipError(f"ffmpeg could not run: {exc}") from exc
    if result.returncode != 0:
        _discard(out_path)
        raise ClipError(result.stderr.strip() or "ffmpeg failed")
    if not out_path.exists():
        raise ClipError("ffmpeg reported success but produced no clip")
    return out_path


def _discard(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        logger.warning("Could not remove failed clip %s", path, exc_info=True)
