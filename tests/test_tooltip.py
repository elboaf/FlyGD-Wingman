"""The tooltip text decision. The widget machinery is untested by design."""

from pathlib import Path

import pytest

from wingman import library
from wingman.ui import copy as copy_mod


def test_unreadable_duration_explains_itself():
    """The list showed a bare "?" in the Length column with nothing anywhere
    saying what it meant."""
    help_text = copy_mod.tooltip_for_cell("duration", "?")
    assert help_text is not None
    assert "ffprobe" in help_text


def test_pending_probe_is_distinguished_from_a_failed_one():
    """ "…" and "?" mean opposite things -- not measured yet versus measured
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


def test_a_measurement_never_taken_blames_the_install_not_the_file():
    """Uploader 5 and 10. "?" says ffprobe could not open THIS FILE; the
    dash says ffprobe was never found. They shared the "?" glyph until
    round 2, so a build with no ffprobe accused all 25 recordings in the
    folder of being unreadable, one row at a time.

    The two must say different things about different subjects, and the
    dash has to name a way out -- the binary is bundled, so the install is
    the thing that is wrong and reinstalling is the fix."""
    unreadable = copy_mod.tooltip_for_cell("duration", "?")
    unmeasured = copy_mod.tooltip_for_cell("duration", "—")
    assert unmeasured is not None
    assert unmeasured != unreadable
    assert "this file" in unreadable
    assert "this file" not in unmeasured
    assert "not found" in unmeasured
    assert "reinstall" in unmeasured.lower()


@pytest.mark.parametrize(
    "probed,answered,duration,expected_help",
    [
        (False, True, None, True),  # "…" measuring
        (True, True, None, True),  # "?" ffprobe read it and could not
        (True, False, None, True),  # "—" ffprobe never gave a verdict
        (True, True, 90.0, False),  # "1:30"
    ],
)
def test_the_keys_match_what_video_info_actually_renders(
    probed, answered, duration, expected_help
):
    """Guards the coupling: the table is keyed on rendered text, so a change
    to duration_str's glyphs would silently orphan these entries."""
    info = library.VideoInfo(
        path=Path("a.mkv"),
        mtime=0.0,
        size=1,
        duration=duration,
        probed=probed,
        answered=answered,
    )
    got = copy_mod.tooltip_for_cell("duration", info.duration_str)
    assert (got is not None) is expected_help


def test_the_page_carries_the_same_table_this_one_describes():
    """The tooltip table is the one piece of copy the page owns a second
    copy of, and it is the one the codebase warns about by name
    (ui/rows.py: "a drift there orphans the tooltips silently").

    Everything else that would have needed a JavaScript twin goes over the
    bridge instead -- auth_labels(), panel_text(), format_destination --
    but these strings are needed synchronously while a row is being built,
    with no round trip available. So the duplication stays and this test
    makes drift loud instead of silent: the Python table is otherwise
    unreachable from the running product, so a change to it would pass its
    own tests and change nothing a user sees.

    Compared fragment by fragment because the page writes the multi-line
    entries as `+`-concatenated literals.
    """
    source = (
        Path(__file__).resolve().parent.parent / "wingman" / "web" / "list.js"
    ).read_text(encoding="utf-8")
    start = source.index("var CELL_HELP = {")
    block = source[start : source.index("};", start)]

    for column, entries in copy_mod.CELL_HELP.items():
        assert f"{column}:" in block, f"list.js has no {column} tooltips"
        for rendered, help_text in entries.items():
            assert f"'{rendered}'" in block, (
                f"list.js has no tooltip keyed on {rendered!r}"
            )
            for fragment in help_text.split("\n"):
                assert fragment in block, (
                    f"list.js is missing tooltip copy: {fragment!r}"
                )
