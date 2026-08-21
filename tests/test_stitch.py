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


def test_write_concat_list_quotes_every_source(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    list_path = tmp_path / "list.txt"
    stitch.write_concat_list(srcs, list_path)
    assert list_path.read_text(encoding="utf-8").splitlines() == [
        f"file '{srcs[0]}'",
        f"file '{srcs[1]}'",
    ]


def test_write_concat_list_escapes_apostrophes(tmp_path):
    """The concat demuxer treats a bare ' as the end of the quoted path, so
    a recording folder like "Gunny's clips" would otherwise be unparseable."""
    src = tmp_path / "Gunny's clip.mkv"
    list_path = tmp_path / "list.txt"
    stitch.write_concat_list([src], list_path)
    line = list_path.read_text(encoding="utf-8").strip()
    assert line == "file '" + str(src).replace("'", "'\\''") + "'"
    assert line.count("'") == 5


def test_write_concat_list_keeps_backslashes_literal(tmp_path):
    """Inside single quotes the demuxer applies no backslash escaping, so a
    backslash must be written through unchanged -- which is what lets a
    Windows path be listed verbatim."""
    src = tmp_path / "back\\slash.mkv"
    stitch.write_concat_list([src], tmp_path / "l.txt")
    assert (tmp_path / "l.txt").read_text(encoding="utf-8").strip() == f"file '{src}'"
    assert "\\" in str(src)


def test_build_command_is_a_stream_copy(tmp_path):
    """Argument order is semantic to ffmpeg; membership checks would pass
    even with the flags scrambled."""
    cmd = stitch.build_command(tmp_path / "list.txt", tmp_path / "out.mkv", "ffmpeg")
    assert cmd == [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(tmp_path / "list.txt"),
        "-c", "copy",
        str(tmp_path / "out.mkv"),
    ]


def test_build_command_re_encodes_nothing(tmp_path):
    """A re-encode is minutes of CPU per stitch; -c copy is the whole point."""
    cmd = stitch.build_command(tmp_path / "list.txt", tmp_path / "out.mkv", "ffmpeg")
    for flag in ("-filter_complex", "-c:v", "libx264", "-c:a", "aac", "-movflags"):
        assert flag not in cmd


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
    (tmp_path / "stitch-abc123.txt").write_bytes(b"x")
    (tmp_path / "unrelated.txt").write_bytes(b"x")
    assert stitch.sweep_orphans(tmp_path) == 2
    assert (tmp_path / "unrelated.txt").exists()


def test_stitched_cleans_up_the_concat_list(tmp_path):
    """The list file is as much a temp artifact as the output; leaking it
    would litter the temp dir on every single stitch."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok):
        pass
    assert list(tmp_path.glob("stitch-*.txt")) == []


def test_stitched_cleans_up_the_concat_list_when_ffmpeg_fails(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with pytest.raises(stitch.StitchError):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_fail):
            pass
    assert list(tmp_path.glob("stitch-*.txt")) == []


def test_stitched_feeds_ffmpeg_a_list_naming_every_source(tmp_path):
    """End to end: whatever path stitched() passes as -i must exist at the
    moment the runner is called and name all the sources, in order."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    seen = {}

    def _capture(cmd, **kw):
        seen["list"] = Path(cmd[cmd.index("-i") + 1]).read_text(encoding="utf-8")
        return _ok(cmd, **kw)

    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_capture):
        pass
    assert seen["list"].splitlines() == [f"file '{srcs[0]}'", f"file '{srcs[1]}'"]


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
