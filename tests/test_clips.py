"""The pure half of the clip editor: keyframe probing, snapping, cutting.

The cut is deliberately keyframe-aligned rather than frame-accurate; these
tests pin what that trade means (start snaps DOWN, never later) the same
way test_stitch.py pins the stream-copy contract.
"""

import subprocess
from pathlib import Path

import pytest

from wingman import clips


def _probe_output(keys):
    def _run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="\n".join(str(k) for k in keys) + "\n", stderr=""
        )

    return _run


def test_keyframes_parses_pts_lines(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    assert clips.keyframes(src, "ffprobe", runner=_probe_output([0.0, 2.5, 31.0])) == [
        0.0,
        2.5,
        31.0,
    ]


def test_keyframes_ignores_junk_and_sorts(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")

    def _run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="31\nN/A\n0.0\n-\n2.5\n", stderr=""
        )

    assert clips.keyframes(src, "ffprobe", runner=_run) == [0.0, 2.5, 31.0]


def test_keyframes_empty_on_failure(tmp_path):
    """Missing ffprobe, a nonzero exit, an audio-only file -- all mean "no
    usable keys", and the caller falls back rather than refusing."""

    def _fail(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no video")

    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    assert clips.keyframes(src, "ffprobe", runner=_fail) == []

    def _raise(cmd, **kw):
        raise FileNotFoundError("ffprobe")

    assert clips.keyframes(src, "ffprobe", runner=_raise) == []


class _FakeProc:
    def __init__(self, out="", returncode=0, fail_communicate=False):
        self._out = out
        self.returncode = returncode
        self._fail_communicate = fail_communicate
        self.killed = False
        self.kill_count = 0

    def communicate(self, timeout=None):
        if self._fail_communicate:
            raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=timeout)
        return self._out, ""

    def poll(self):
        return self.returncode if self.killed else None

    def kill(self):
        self.kill_count += 1
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode


def _spawn(proc):
    def _spawner(cmd, **kw):
        return proc

    return _spawner


def test_start_keyframes_finishes_with_parsed_keys(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    proc = _FakeProc(out="0.0\n2.5\n")
    probe = clips.start_keyframes(src, "ffprobe", spawner=_spawn(proc))
    assert probe is not None
    assert probe.finish() == [0.0, 2.5]
    assert not proc.killed


def test_a_timed_out_probe_is_killed_and_answers_empty(tmp_path):
    """The reason the probe is cancellable: a 60-second decode holding the
    recording open must end the moment the caller stops waiting, not keep
    the file locked behind the timeout."""
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    proc = _FakeProc(fail_communicate=True)
    probe = clips.start_keyframes(src, "ffprobe", spawner=_spawn(proc))
    assert probe.finish(timeout=0.01) == []
    assert proc.killed


def test_kill_is_idempotent_and_tolerates_a_dead_process(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    proc = _FakeProc()
    probe = clips.start_keyframes(src, "ffprobe", spawner=_spawn(proc))
    probe.kill()
    probe.kill()
    assert proc.kill_count == 1


def test_start_keyframes_returns_none_when_ffprobe_is_missing(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")

    def _raise(cmd, **kw):
        raise FileNotFoundError("ffprobe")

    assert clips.start_keyframes(src, "ffprobe", spawner=_raise) is None


def test_snap_start_never_moves_the_marker_later():
    """The one direction that matters: a clip may begin EARLY (the cut
    opens on the keyframe that owns the marker's GOP), never after the
    moment the user chose."""
    keys = [0.0, 10.0, 20.0]
    assert clips.snap_start(12.0, keys, 100.0) == 10.0
    assert clips.snap_start(10.0, keys, 100.0) == 10.0
    assert clips.snap_start(99.0, keys, 100.0) == 20.0
    assert clips.snap_start(5.0, keys, 100.0) == 0.0


def test_snap_start_without_keys_stands_still():
    assert clips.snap_start(12.0, [], 100.0) == 0.0
    # ffmpeg's own input seek finds a keyframe; 0 is the honest fallback
    # only when nothing is known -- the editor's default band starts at 0.


def test_snap_end_clamps_inside_the_recording():
    assert clips.snap_end(50.0, 100.0) == 50.0
    assert clips.snap_end(150.0, 100.0) == 100.0
    assert clips.snap_end(-5.0, 100.0) == 0.0


def test_cut_command_seeks_before_input_with_relative_length(tmp_path):
    cmd = clips.build_cut_command(
        tmp_path / "in.mkv", tmp_path / "out.mkv", 30.0, 12.0, "ffmpeg"
    )
    assert cmd == [
        "ffmpeg",
        "-y",
        "-ss",
        "30.000",
        "-i",
        str(tmp_path / "in.mkv"),
        "-t",
        "12.000",
        "-c",
        "copy",
        str(tmp_path / "out.mkv"),
    ]


def test_cut_writes_the_clip(tmp_path):
    src = tmp_path / "in.mkv"
    src.write_bytes(b"x")
    out = tmp_path / "out.mkv"

    def _run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"clip")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    assert clips.cut(src, out, 0.0, 5.0, "ffmpeg", runner=_run) == out
    assert out.exists()


def test_cut_failure_leaves_no_half_file(tmp_path):
    """A failed cut must not leave something the list would announce as a
    finished recording."""
    src = tmp_path / "in.mkv"
    src.write_bytes(b"x")
    out = tmp_path / "out.mkv"

    def _fail(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"half")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    with pytest.raises(clips.ClipError, match="boom"):
        clips.cut(src, out, 0.0, 5.0, "ffmpeg", runner=_fail)
    assert not out.exists()


def test_cut_missing_output_is_an_error(tmp_path):
    src = tmp_path / "in.mkv"
    src.write_bytes(b"x")

    def _empty(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with pytest.raises(clips.ClipError, match="no clip"):
        clips.cut(src, tmp_path / "out.mkv", 0.0, 5.0, "ffmpeg", runner=_empty)


def test_clip_path_collision_suffix(tmp_path):
    first = clips.clip_path(tmp_path, "fight")
    first.write_bytes(b"x")
    second = clips.clip_path(tmp_path, "fight")
    assert first.name == "fight - clip.mkv"
    assert second.name == "fight - clip (2).mkv"
