"""Concatenate recordings into a single file for upload, and split one file
into chunks short enough for YouTube's unverified-upload limit.

The temp artifacts' lifetime is owned by context managers so cleanup happens
on every exit path. The pre-2.0 code deleted the stitched file only after a
successful upload, so any failure leaked a multi-gigabyte file permanently.
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
_SPLIT_PREFIX = "split-"
_SUFFIX = ".mkv"
_LIST_SUFFIX = ".txt"

# Target length of one split chunk. The segment muxer can only cut on
# keyframes, so a chunk runs as long as the keyframe AT OR AFTER the target
# -- up to one GOP past it -- and YouTube's verification wall is on the
# length the container reports. 14m30s leaves minutes of headroom, which is
# cheap: one extra part per hour of footage is the whole cost.
SEGMENT_CHUNK_SECONDS = 870

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


class SplitError(RuntimeError):
    """ffmpeg failed to produce split chunks."""


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


def build_segment_command(src: Path, out_pattern: Path, ffmpeg_bin: str) -> list[str]:
    """Split by stream copy -- no re-encode, the same trade as the concat.

    The segment muxer cuts on input keyframes, so with `-c copy` each chunk
    is a valid standalone file produced at disk speed. The muxer never cuts
    BEFORE the target, so a chunk can overshoot it by up to one GOP; the
    target (SEGMENT_CHUNK_SECONDS) is chosen to absorb that.

    `-reset_timestamps 1` makes each chunk start at zero; without it every
    part carries the offset of its place in the source, which some players
    render as minutes of black before the first frame.
    """
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(src),
        "-f",
        "segment",
        "-segment_time",
        str(SEGMENT_CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        "-c",
        "copy",
        str(out_pattern),
    ]


@contextmanager
def segmented(src, tmp_dir, ffmpeg_bin, runner=subprocess.run):
    """Yield the chunk files a split produced, deleting them on every exit.

    Same contract as `stitched`: the caller consumes the chunks inside the
    block, and cleanup is unconditional -- including on a cancel or a failed
    upload partway through the list. ffmpeg numbers the chunks itself via
    the %03d in the output pattern, so the yielded order is playback order.
    """
    src = Path(src)
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_SPLIT_PREFIX}{uuid.uuid4().hex}"
    out_pattern = tmp_dir / f"{stem}%03d{_SUFFIX}"
    chunks: list[Path] = []
    try:
        result = runner(
            build_segment_command(src, out_pattern, ffmpeg_bin),
            capture_output=True,
            text=True,
            **_NO_WINDOW_KWARGS,
        )
        chunks = sorted(tmp_dir.glob(f"{stem}*{_SUFFIX}"))
        if result.returncode != 0:
            raise SplitError(result.stderr.strip() or "ffmpeg failed")
        if not chunks:
            raise SplitError("ffmpeg reported success but produced no output")
        yield chunks
    finally:
        for path in chunks:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Could not remove split chunk %s", path, exc_info=True)


def sweep_orphans(tmp_dir: Path) -> int:
    """Delete stitch and split artifacts left behind by a crash. Returns the count."""
    tmp_dir = Path(tmp_dir)
    if not tmp_dir.is_dir():
        return 0
    removed = 0
    for prefix in (_PREFIX, _SPLIT_PREFIX):
        for suffix in (_SUFFIX, _LIST_SUFFIX):
            for path in tmp_dir.glob(f"{prefix}*{suffix}"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed
