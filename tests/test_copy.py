"""Pure copy formatters.

Moved from app.py to ui/copy.py ahead of the webview port; these tests
cover the copy module directly rather than the Tk window that used to be
their only harness.
"""

from pathlib import Path

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod


def _info(name="a.mkv", size=10, duration=60.0, probed=True):
    return library.VideoInfo(
        path=Path(name), mtime=100.0, size=size, duration=duration, probed=probed
    )


def test_summary_of_an_empty_selection():
    assert copy_mod.format_selection_summary([]) == "Nothing selected"


def test_summary_of_one_recording_is_not_pluralised():
    """ "1 selected", not "1 selecteds": the noun is elided entirely, so the
    count needs no agreement at any value."""
    summary = copy_mod.format_selection_summary([_info(size=1024, duration=5.0)])
    assert summary == "1 selected · 1.0 KB · 0:00:05"


def test_summary_totals_size_and_duration_across_recordings():
    infos = [
        _info(size=1024, duration=3600.0),
        _info(size=1024, duration=2700.0),
        _info(size=2048, duration=1535.0),
    ]
    assert copy_mod.format_selection_summary(infos) == "3 selected · 4.0 KB · 2:10:35"


def test_summary_marks_the_duration_partial_when_a_probe_is_outstanding():
    infos = [
        _info(size=1024, duration=3600.0),
        _info(size=1024, duration=None, probed=False),
    ]
    assert copy_mod.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00+"


def test_summary_size_is_never_marked_partial():
    """Size comes from stat, not from a probe, so an outstanding probe says
    nothing about it -- the "+" belongs to the duration alone."""
    infos = [_info(size=1024, duration=None, probed=False)]
    assert copy_mod.format_selection_summary(infos) == "1 selected · 1.0 KB · 0:00:00+"


def test_summary_of_a_probed_recording_with_no_duration_is_not_partial():
    """probed=True with duration=None is a finished verdict (ffprobe ran and
    could not read the file). It contributes 0 and the total stays exact --
    the row's own "?" already reports the failure."""
    infos = [
        _info(size=1024, duration=3600.0),
        _info(size=1024, duration=None, probed=True),
    ]
    assert copy_mod.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00"


def test_summary_uses_a_middle_dot_separator():
    summary = copy_mod.format_selection_summary([_info()])
    assert " · " in summary and "|" not in summary
