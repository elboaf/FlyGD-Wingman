"""Fixtures for the tests that drive a real Tk window.

The suite runs on Linux with no UI tests, but a display is usually
available (WSLg). These tests build real widgets rather than reasoning
about layout, and skip cleanly where there is no display — a headless CI
box must not turn a missing X server into a red suite.

Two traps that make a wrong check look identical to a right one:
  * every winfo_* is 0 until root.update() has run;
  * DPI is driven the way __main__.main() drives it, `tk scaling` = dpi/72,
    NOT by monkeypatching app.dpi_scale — patching the helper leaves Tk
    itself at 100%, so widget geometry would not move and the test would
    pass for the wrong reason.

Font metrics are meaningless here: this host's Tk has no Xft, so
tkfont.families() offers only a bitmap font. Never assert on text extents
or line heights; those checks belong in docs/smoke-checklist.md.
"""
import tkinter as tk

import pytest


@pytest.fixture
def make_window(tmp_path):
    """Build a real UploaderWindow at a given DPI over a temp recording dir."""
    windows = []

    def _make(dpi=96, ffmpeg_bin="/usr/bin/ffmpeg", files=("a.mkv", "b.mkv")):
        from obs_youtube_uploader import app as app_mod, theme

        try:
            root = tk.Tk()
        except tk.TclError:
            pytest.skip("no display available")
        root.tk.call("tk", "scaling", dpi / 72.0)
        theme.apply(root, "dark")
        for name in files:
            (tmp_path / name).write_bytes(b"\0" * 1024)
        state = app_mod.AppState(
            recording_dir=tmp_path,
            settings={"privacy": "unlisted", "category": "20"},
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=None,
        )
        window = app_mod.UploaderWindow(root, state)
        # Invalidate the probe refresh() just started: these tests set
        # duration state by hand, and a straggling probe result landing
        # mid-test would overwrite it.
        window._refresh_generation += 1
        root.update()
        windows.append(window)
        return window

    yield _make

    for window in windows:
        from obs_youtube_uploader import theme

        theme.unregister(window._on_theme_changed)
        window.root.destroy()
