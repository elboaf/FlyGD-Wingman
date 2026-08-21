"""Tests for obs_youtube_uploader.app: the DPI-scaled Spacing helper."""
from types import SimpleNamespace

import pytest

from obs_youtube_uploader import app as app_mod
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
    with pytest.raises(Exception):
        pad.tight = 99


def test_old_unscaled_pad_constants_are_gone():
    """They are removed, not deprecated: leaving them importable invites a new
    call site that silently ignores DPI."""
    for name in ("PAD_TIGHT", "PAD_NORMAL", "PAD_LOOSE", "FRAME_PADDING"):
        assert not hasattr(app_mod, name)
