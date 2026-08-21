"""The tooltip text decision. The widget machinery is untested by design."""
import pytest

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod
from pathlib import Path


def test_unreadable_duration_explains_itself():
    """The list showed a bare "?" in the Length column with nothing anywhere
    saying what it meant."""
    help_text = copy_mod.tooltip_for_cell("duration", "?")
    assert help_text is not None
    assert "ffprobe" in help_text


def test_pending_probe_is_distinguished_from_a_failed_one():
    """"…" and "?" mean opposite things -- not measured yet versus measured
    and unreadable -- and looked equally mysterious."""
    pending = copy_mod.tooltip_for_cell("duration", "…")
    failed = copy_mod.tooltip_for_cell("duration", "?")
    assert pending != failed
    assert "Measuring" in pending


def test_link_glyph_explains_both_of_its_gestures():
    help_text = copy_mod.tooltip_for_cell("link", "↗")
    assert "Double-click" in help_text
    assert "right-click" in help_text.lower()


def test_an_ordinary_duration_gets_no_tooltip():
    assert copy_mod.tooltip_for_cell("duration", "59:58") is None


def test_an_empty_link_cell_gets_no_tooltip():
    assert copy_mod.tooltip_for_cell("link", "") is None


def test_unknown_columns_get_no_tooltip():
    assert copy_mod.tooltip_for_cell("filename", "a.mkv") is None
    assert copy_mod.tooltip_for_cell("nonsense", "?") is None


@pytest.mark.parametrize("probed,duration,expected_help", [
    (False, None, True),   # "…"
    (True, None, True),    # "?"
    (True, 90.0, False),   # "1:30"
])
def test_the_keys_match_what_video_info_actually_renders(probed, duration,
                                                         expected_help):
    """Guards the coupling: the table is keyed on rendered text, so a change
    to duration_str's glyphs would silently orphan these entries."""
    info = library.VideoInfo(path=Path("a.mkv"), mtime=0.0, size=1,
                             duration=duration, probed=probed)
    got = copy_mod.tooltip_for_cell("duration", info.duration_str)
    assert (got is not None) is expected_help
