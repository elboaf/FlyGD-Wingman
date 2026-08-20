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


def test_build_command_matches_shipped_encode_settings(tmp_path):
    """Argument order is semantic to ffmpeg; membership checks would pass
    even with -c:v and -c:a values swapped."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    expected_tail = [
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp_path / "out.mkv"),
    ]
    assert cmd[-len(expected_tail):] == expected_tail


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


def test_stitched_propagates_runner_exception(tmp_path):
    """A raising runner (e.g. ffmpeg binary not found) must still trigger
    cleanup via the finally, not just a return code check."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")

    def _raise(cmd, **kw):
        raise RuntimeError("ffmpeg binary not found")

    with pytest.raises(RuntimeError, match="ffmpeg binary not found"):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_raise):
            pass
    assert list(tmp_path.glob("stitch-*.mkv")) == []


def test_stitched_raises_when_ffmpeg_reports_success_but_no_output(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")

    def _no_output(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with pytest.raises(stitch.StitchError, match="no output"):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_no_output):
            pass


def test_stitched_creates_tmp_dir_when_absent(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    target = tmp_path / "does" / "not" / "exist"
    with stitch.stitched(srcs, "ffmpeg", target, runner=_ok) as out:
        assert out.exists()
    assert target.is_dir()


def test_sweep_orphans_survives_a_per_file_unlink_failure(tmp_path, monkeypatch):
    (tmp_path / "stitch-abc123.mkv").write_bytes(b"x")

    def _raise_unlink(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", _raise_unlink)
    assert stitch.sweep_orphans(tmp_path) == 0
    assert (tmp_path / "stitch-abc123.mkv").exists()
