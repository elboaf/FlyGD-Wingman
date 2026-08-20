import subprocess
from pathlib import Path

import pytest
from obs_youtube_uploader import library, stitch


def _info(path: Path, mtime: float) -> library.VideoInfo:
    return library.VideoInfo(path=path, mtime=mtime, size=1, duration=None)


def _ok(cmd, **kw):
    # Simulate ffmpeg producing its output file.
    out = Path(cmd[-1])
    out.write_bytes(b"stitched")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _fail(cmd, **kw):
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ffmpeg exploded")


def test_order_for_stitch_is_earliest_first():
    a = _info(Path("a.mkv"), 300)
    b = _info(Path("b.mkv"), 100)
    c = _info(Path("c.mkv"), 200)
    assert [i.path.name for i in stitch.order_for_stitch([a, b, c])] == ["b.mkv", "c.mkv", "a.mkv"]


def test_build_command_includes_every_source(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    assert cmd[0] == "ffmpeg"
    for s in srcs:
        assert str(s) in cmd
    assert cmd[-1] == str(tmp_path / "out.mkv")


def test_build_command_concat_filter_matches_input_count(tmp_path):
    srcs = [tmp_path / f"{n}.mkv" for n in "abc"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    assert "n=3" in " ".join(cmd)


def test_build_command_includes_codec_flags(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    cmd_str = " ".join(cmd)
    # Check that video codec flags are present
    assert "-c:v" in cmd
    assert "libx264" in cmd
    assert "-preset" in cmd
    assert "fast" in cmd
    assert "-crf" in cmd
    assert "23" in cmd
    # Check that audio codec flags are present
    assert "-c:a" in cmd
    assert "aac" in cmd
    assert "-b:a" in cmd
    assert "192k" in cmd
    # Check that movflags is present
    assert "-movflags" in cmd
    assert "+faststart" in cmd
    # Check that output path is still last
    assert cmd[-1] == str(tmp_path / "out.mkv")
    # Check order: codec flags should come after -map and before output
    map_index = cmd.index("-map")
    c_v_index = cmd.index("-c:v")
    assert c_v_index > map_index, "codec flags should come after -map"
    assert cmd.index("-movflags") < len(cmd) - 1, "-movflags should come before output path"


def test_stitched_yields_an_existing_file(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
        assert out.exists()


def test_stitched_cleans_up_on_success(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
        captured = out
    assert not captured.exists()


def test_stitched_cleans_up_when_body_raises(tmp_path):
    """This is the leak the old code had: cleanup must not depend on success."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    captured = None
    with pytest.raises(RuntimeError):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
            captured = out
            raise RuntimeError("upload failed")
    assert captured is not None
    assert not captured.exists()


def test_stitched_raises_when_ffmpeg_fails(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with pytest.raises(stitch.StitchError):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_fail):
            pass


def test_stitched_requires_at_least_two_sources(tmp_path):
    with pytest.raises(ValueError):
        with stitch.stitched([tmp_path / "a.mkv"], "ffmpeg", tmp_path, runner=_ok):
            pass


def test_output_names_are_unique_across_runs(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    names = []
    for _ in range(2):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
            names.append(out.name)
    assert names[0] != names[1]


def test_sweep_orphans_removes_only_stitch_artifacts(tmp_path):
    (tmp_path / "stitch-abc123.mkv").write_bytes(b"x")
    (tmp_path / "unrelated.txt").write_bytes(b"x")
    assert stitch.sweep_orphans(tmp_path) == 1
    assert (tmp_path / "unrelated.txt").exists()


def test_sweep_orphans_handles_missing_directory(tmp_path):
    assert stitch.sweep_orphans(tmp_path / "nope") == 0
