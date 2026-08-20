"""Concatenate recordings into a single file for upload.

The temp file's lifetime is owned by a context manager so cleanup happens on
every exit path. The pre-2.0 code deleted it only after a successful upload,
so any failure leaked a multi-gigabyte file permanently.
"""
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

from .library import VideoInfo

_PREFIX = "stitch-"
_SUFFIX = ".mkv"


class StitchError(RuntimeError):
    """ffmpeg failed to produce a concatenated file."""


def order_for_stitch(infos: list[VideoInfo]) -> list[VideoInfo]:
    """Earliest recording first, matching pre-2.0 behavior."""
    return sorted(infos, key=lambda i: i.mtime)


def build_command(sources: list[Path], out_path: Path, ffmpeg_bin: str) -> list[str]:
    cmd = [ffmpeg_bin, "-y"]
    for src in sources:
        cmd += ["-i", str(src)]
    streams = "".join(f"[{n}:v][{n}:a]" for n in range(len(sources)))
    cmd += [
        "-filter_complex", f"{streams}concat=n={len(sources)}:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return cmd


@contextmanager
def stitched(sources: list[Path], ffmpeg_bin: str, tmp_dir: Path, runner=subprocess.run):
    """Yield a concatenated file, deleting it on every exit path."""
    if len(sources) < 2:
        raise ValueError("stitching requires at least two sources")
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"{_PREFIX}{uuid.uuid4().hex}{_SUFFIX}"
    try:
        result = runner(build_command(sources, out_path, ffmpeg_bin),
                        capture_output=True, text=True)
        if result.returncode != 0:
            raise StitchError(result.stderr.strip() or "ffmpeg failed")
        if not out_path.exists():
            raise StitchError("ffmpeg reported success but produced no output")
        yield out_path
    finally:
        try:
            out_path.unlink()
        except OSError:
            pass


def sweep_orphans(tmp_dir: Path) -> int:
    """Delete stitch artifacts left behind by a crash. Returns the count."""
    tmp_dir = Path(tmp_dir)
    if not tmp_dir.is_dir():
        return 0
    removed = 0
    for path in tmp_dir.glob(f"{_PREFIX}*{_SUFFIX}"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
