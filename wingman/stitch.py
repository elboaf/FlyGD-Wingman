"""Concatenate recordings into a single file for upload.

The temp file's lifetime is owned by a context manager so cleanup happens on
every exit path. The pre-2.0 code deleted it only after a successful upload,
so any failure leaked a multi-gigabyte file permanently.
"""

import logging
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from .library import VideoInfo

logger = logging.getLogger(__name__)

_PREFIX = "stitch-"
_SUFFIX = ".mkv"
_LIST_SUFFIX = ".txt"

# In a console=False PyInstaller build, every subprocess.run() would
# otherwise flash a black console window — and this one runs for the
# entire multi-minute encode. CREATE_NO_WINDOW doesn't exist off Windows,
# and the Linux test suite injects fake runners, so this must not affect
# non-Windows platforms.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


class StitchError(RuntimeError):
    """ffmpeg failed to produce a concatenated file."""


def order_for_stitch(infos: list[VideoInfo]) -> list[VideoInfo]:
    """Earliest recording first, matching pre-2.0 behavior."""
    return sorted(infos, key=lambda i: i.mtime)


def write_concat_list(sources: list[Path], list_path: Path) -> None:
    """Write the concat demuxer's input list.

    Each line is ``file '<path>'``. Inside single quotes the demuxer's
    tokenizer treats every character literally -- backslashes included, so
    Windows paths pass through unchanged -- with one exception: a quote
    ends the quoted run. An apostrophe is therefore emitted as ``'\''``
    (close, escaped literal, reopen), which is what makes a recording under
    a folder like ``Gunny's clips`` parseable at all.

    Paths are absolute and ``-safe 0`` is passed, because relative entries
    would otherwise be resolved against the list file's directory (the temp
    dir), not the recording folder.
    """
    lines = []
    for src in sources:
        escaped = str(Path(src).resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    Path(list_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_command(list_path: Path, out_path: Path, ffmpeg_bin: str) -> list[str]:
    """Concatenate by stream copy -- no re-encode.

    The pre-2.0 script decoded and re-encoded through ``-filter_complex
    concat`` with libx264, which costs minutes of CPU and a generation of
    quality loss to join files that are already compatible. Every recording
    in the folder comes from one OBS output configuration, so the streams
    share codec, resolution, framerate and pixel format, and the concat
    demuxer can splice them at the container level in roughly the time it
    takes to copy the bytes.

    ffmpeg fails loudly on mismatched inputs, which `stitched` surfaces as
    a StitchError, so the narrower assumption is not a silent one.

    ``-movflags +faststart`` is gone with the re-encode: it is an MP4-only
    option, and the output is Matroska.
    """
    return [
        ffmpeg_bin,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(out_path),
    ]


@contextmanager
def stitched(
    sources: list[Path], ffmpeg_bin: str, tmp_dir: Path, runner=subprocess.run
):
    """Yield a concatenated file, deleting it on every exit path."""
    if len(sources) < 2:
        raise ValueError("stitching requires at least two sources")
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # One stem for both artifacts, so a crash leaves a list file that
    # sweep_orphans recognizes by the same prefix as the output.
    stem = f"{_PREFIX}{uuid.uuid4().hex}"
    out_path = tmp_dir / f"{stem}{_SUFFIX}"
    list_path = tmp_dir / f"{stem}{_LIST_SUFFIX}"
    try:
        write_concat_list(sources, list_path)
        result = runner(
            build_command(list_path, out_path, ffmpeg_bin),
            capture_output=True,
            text=True,
            **_NO_WINDOW_KWARGS,
        )
        if result.returncode != 0:
            raise StitchError(result.stderr.strip() or "ffmpeg failed")
        if not out_path.exists():
            raise StitchError("ffmpeg reported success but produced no output")
        yield out_path
    finally:
        for path in (out_path, list_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning(
                    "Could not remove stitched temp file %s", path, exc_info=True
                )


def sweep_orphans(tmp_dir: Path) -> int:
    """Delete stitch artifacts left behind by a crash. Returns the count."""
    tmp_dir = Path(tmp_dir)
    if not tmp_dir.is_dir():
        return 0
    removed = 0
    for suffix in (_SUFFIX, _LIST_SUFFIX):
        for path in tmp_dir.glob(f"{_PREFIX}*{suffix}"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
