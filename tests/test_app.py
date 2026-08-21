"""Pure formatters that live in app.py.

app.py imports without a display -- only constructing UploaderWindow needs
one -- so its module-level pure functions are testable here. The Tk wiring
that consumes them has no harness in this repo (see library.py's docstring),
which is exactly why the formatting lives in a function and not inline in a
label update.
"""
from pathlib import Path
import dataclasses
from types import SimpleNamespace

import pytest

from obs_youtube_uploader import app as app_mod, library
from obs_youtube_uploader.__main__ import tk_scaling_for


def _widget_at(dpi: int):
    """A widget whose `tk scaling` is what __main__.main() would have set for
    this DPI. Monkeypatching dpi_scale instead would prove only that the
    multiplication happens, not that it is fed the value the app really
    installs -- the two halves of that contract have drifted before
    (test_main.test_tk_scaling_and_dpi_scale_round_trip)."""
    return SimpleNamespace(tk=SimpleNamespace(
        call=lambda *args, _v=tk_scaling_for(dpi): _v))


def test_spacing_base_values_at_100_percent():
    pad = app_mod.spacing(_widget_at(96))
    assert (pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) == (
        4, 8, 12, 16, 8)


@pytest.mark.parametrize("dpi, expected", [
    (96, (4, 8, 12, 16, 8)),
    (120, (5, 10, 15, 20, 10)),
    (144, (6, 12, 18, 24, 12)),
])
def test_spacing_scales_with_tk_scaling(dpi, expected):
    pad = app_mod.spacing(_widget_at(dpi))
    assert (pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) == expected


def test_spacing_never_collapses_to_zero():
    """A pathological scale must still leave a visible gap: 0 padding reads as
    a layout bug, not as small spacing."""
    widget = SimpleNamespace(tk=SimpleNamespace(call=lambda *args: 0.01))
    pad = app_mod.spacing(widget)
    assert min(pad.tight, pad.normal, pad.loose, pad.margin, pad.frame) >= 1


def test_spacing_is_immutable():
    pad = app_mod.spacing(_widget_at(96))
    with pytest.raises(dataclasses.FrozenInstanceError):
        pad.tight = 99


def test_old_unscaled_pad_constants_are_gone():
    """They are removed, not deprecated: leaving them importable invites a new
    call site that silently ignores DPI."""
    for name in ("PAD_TIGHT", "PAD_NORMAL", "PAD_LOOSE", "FRAME_PADDING"):
        assert not hasattr(app_mod, name)


def _info(name="a.mkv", size=10, duration=60.0, probed=True):
    return library.VideoInfo(path=Path(name), mtime=100.0, size=size,
                             duration=duration, probed=probed)


def test_summary_of_an_empty_selection():
    assert app_mod.format_selection_summary([]) == "Nothing selected"


def test_summary_of_one_recording_is_not_pluralised():
    """"1 selected", not "1 selecteds": the noun is elided entirely, so the
    count needs no agreement at any value."""
    summary = app_mod.format_selection_summary([_info(size=1024, duration=5.0)])
    assert summary == "1 selected · 1.0 KB · 0:00:05"


def test_summary_totals_size_and_duration_across_recordings():
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=2700.0),
             _info(size=2048, duration=1535.0)]
    assert app_mod.format_selection_summary(infos) == "3 selected · 4.0 KB · 2:10:35"


def test_summary_marks_the_duration_partial_when_a_probe_is_outstanding():
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=None, probed=False)]
    assert app_mod.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00+"


def test_summary_size_is_never_marked_partial():
    """Size comes from stat, not from a probe, so an outstanding probe says
    nothing about it -- the "+" belongs to the duration alone."""
    infos = [_info(size=1024, duration=None, probed=False)]
    assert app_mod.format_selection_summary(infos) == "1 selected · 1.0 KB · 0:00:00+"


def test_summary_of_a_probed_recording_with_no_duration_is_not_partial():
    """probed=True with duration=None is a finished verdict (ffprobe ran and
    could not read the file). It contributes 0 and the total stays exact --
    the row's own "?" already reports the failure."""
    infos = [_info(size=1024, duration=3600.0),
             _info(size=1024, duration=None, probed=True)]
    assert app_mod.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00"


def test_summary_uses_a_middle_dot_separator():
    summary = app_mod.format_selection_summary([_info()])
    assert " · " in summary and "|" not in summary
