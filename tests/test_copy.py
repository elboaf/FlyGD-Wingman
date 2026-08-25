"""Pure copy formatters.

Moved from app.py to ui/copy.py ahead of the webview port; these tests
cover the copy module directly rather than the Tk window that used to be
their only harness.
"""

import pathlib
from pathlib import Path

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod


def _info(name="a.mkv", size=10, duration=60.0, probed=True, answered=True):
    return library.VideoInfo(
        path=Path(name),
        mtime=100.0,
        size=size,
        duration=duration,
        probed=probed,
        answered=answered,
    )


def test_summary_of_an_empty_selection():
    assert copy_mod.format_selection_summary([]) == "Nothing selected"


def test_summary_of_one_recording_is_not_pluralised():
    """ "1 selected", not "1 selecteds": the noun is elided entirely, so the
    count needs no agreement at any value."""
    summary = copy_mod.format_selection_summary([_info(size=1024, duration=5.0)])
    assert summary == "1 selected · 1.0 KB · 0:05"


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
    assert copy_mod.format_selection_summary(infos) == "1 selected · 1.0 KB · 0:00+"


def test_summary_of_a_probed_recording_with_no_duration_is_not_partial():
    """probed=True with duration=None is a finished verdict (ffprobe ran and
    could not read the file). It contributes 0 and the total stays exact --
    the row's own "?" already reports the failure."""
    infos = [
        _info(size=1024, duration=3600.0),
        _info(size=1024, duration=None, probed=True),
    ]
    assert copy_mod.format_selection_summary(infos) == "2 selected · 2.0 KB · 1:00:00"


def test_summary_of_a_recording_that_was_never_measured_is_partial():
    """Uploader 10, and the half of it that is not the column.

    A probe that reached no verdict -- no ffprobe on the machine, a launch
    failure, a timeout -- contributes 0 exactly like an outstanding one,
    but it used to be indistinguishable from a finished verdict, so the
    total came out unmarked. On an install with no ffprobe that made the
    line read "1 selected · 108.8 MB · 0:00": a stated zero for a
    108.8 MB recording, which is the one thing a blank never claims.
    """
    infos = [_info(size=1024, duration=None, probed=True, answered=False)]
    assert copy_mod.format_selection_summary(infos) == "1 selected · 1.0 KB · 0:00+"

    # And it still marks a total that has real content in it, rather than
    # only the degenerate all-zero case.
    mixed = [
        _info(size=1024, duration=3600.0),
        _info(size=1024, duration=None, probed=True, answered=False),
    ]
    assert copy_mod.format_selection_summary(mixed) == "2 selected · 2.0 KB · 1:00:00+"


def test_summary_uses_a_middle_dot_separator():
    summary = copy_mod.format_selection_summary([_info()])
    assert " · " in summary and "|" not in summary


# --- format_eve_copy_confirm ----------------------------------------------


def test_the_copy_confirm_counts_what_the_user_actually_ticked():
    """It said "3 other file(s)" at someone who had just ticked three
    character names. Wrong noun, and the "(s)" is exactly the padding
    PRODUCT.md's tone rule rules out -- in the last thing shown before an
    irreversible write."""
    body = copy_mod.format_eve_copy_confirm(3, "character", eve_running=False)
    assert "3 other characters" in body
    assert "file(s)" not in body
    assert "(s)" not in body


def test_the_copy_confirm_does_not_pluralise_a_single_target():
    body = copy_mod.format_eve_copy_confirm(1, "character", eve_running=False)
    assert "1 other character?" in body


def test_the_copy_confirm_uses_the_word_the_screen_uses_for_accounts():
    """The page offers a Characters / Accounts switch. DESIGN.md's "one
    name per concept" makes the dialog use the same two words."""
    body = copy_mod.format_eve_copy_confirm(2, "account", eve_running=False)
    assert "2 other accounts" in body


def test_an_unrecognised_selection_falls_back_to_naming_files():
    """Degraded, not wrong: it is what the dialog said for every selection
    before it could tell the difference. Reached when the targets are mixed
    or are not EVE settings files at all."""
    body = copy_mod.format_eve_copy_confirm(2, None, eve_running=False)
    assert "2 other settings files" in body


def test_the_copy_confirm_repeats_the_running_client_hazard():
    """The screen renders a warn-toned "EVE running" pill precisely because
    copying into a profile while a client is open is the hazard -- EVE
    rewrites its own settings on exit. The pill is advisory and the dialog
    is modal, so the warning was on the wrong one of the two."""
    body = copy_mod.format_eve_copy_confirm(3, "character", eve_running=True)
    assert "EVE is running" in body
    # Says what to do, not only what is wrong (PRODUCT.md's tone rule).
    assert "Close every client first" in body


def test_the_copy_confirm_stays_quiet_about_eve_when_nothing_is_running():
    body = copy_mod.format_eve_copy_confirm(3, "character", eve_running=False)
    assert "EVE is running" not in body


def test_the_copy_confirm_always_states_the_cost():
    """PRODUCT.md: state cost before an irreversible action. The backup and
    the irreversibility are true in every branch above."""
    for running in (True, False):
        body = copy_mod.format_eve_copy_confirm(3, "character", eve_running=running)
        assert "backed up first" in body
        assert "cannot be undone" in body


def test_the_completion_line_uses_the_same_noun_as_the_confirm():
    """These two sentences are a second apart on the same screen. A dialog
    saying "3 other characters" followed by a strip saying "Copied to 3
    file(s)." is a worse disagreement than the one the confirm fixed, and
    it is one this change would have introduced by fixing only the dialog.
    """
    for kind, expected in (
        ("character", "characters"),
        ("account", "accounts"),
        (None, "settings files"),
    ):
        confirm = copy_mod.format_eve_copy_confirm(3, kind, eve_running=False)
        done = copy_mod.format_eve_copy_done(3, kind)
        assert f"3 other {expected}?" in confirm
        assert done == f"Copied to 3 {expected}."


def test_the_completion_line_does_not_pluralise_a_single_target():
    assert copy_mod.format_eve_copy_done(1, "character") == "Copied to 1 character."
    assert copy_mod.format_eve_copy_done(1, "account") == "Copied to 1 account."


def test_the_completion_line_drops_the_padded_plural():
    """ "(s)" is the padding PRODUCT.md's tone rule rules out, and it
    survived here after the confirm stopped using it."""
    assert "(s)" not in copy_mod.format_eve_copy_done(2, "character")


# --- one duration format across every surface that shows one ---------------


def test_one_recording_reads_the_same_on_all_three_surfaces():
    """Round 3's findings 4 and 17: one recording, three renderings.

    The list's Length column said "17:07", the panel summary "0:17:07",
    and Confirm Upload's Total "0:17:07" -- the first two visible at once
    in a single screenshot. Two of them were built inline, six lines apart
    in this module, which is how they were free to drift.

    Asserted as equality between the surfaces rather than three literals:
    a fourth format is only excluded if the check has no copy of its own
    to update. The literal below is here to pin which format won, once.
    """
    seconds = 1027
    one = _info(size=1024, duration=float(seconds))

    column = one.duration_str
    summary = copy_mod.format_selection_summary([one])
    total = copy_mod.format_upload_confirm(
        [one],
        title="Fight",
        privacy="unlisted",
        channel_title="Z",
        stitch=False,
        discord_webhook="",
    )

    assert column == library.format_duration(seconds) == "17:07"
    assert summary.endswith("· " + column)
    assert f"· {column}\n" in total


def test_an_hour_long_recording_reads_the_same_on_all_three_surfaces():
    """The case the old list column could not render at all: it divided by
    60 alone, so this was "127:07" there and "2:07:07" in the dialog."""
    seconds = 7627
    one = _info(size=1024, duration=float(seconds))

    assert one.duration_str == "2:07:07"
    assert copy_mod.format_selection_summary([one]).endswith("· 2:07:07")
    assert "· 2:07:07\n" in copy_mod.format_upload_confirm(
        [one],
        title="Fight",
        privacy="unlisted",
        channel_title="Z",
        stitch=False,
        discord_webhook="",
    )


def test_the_progress_text_carries_the_percent_the_bar_can_show():
    """The bar rounds to whole percent (panel.js's Math.round), and on a
    single-file upload it is measuring exactly what this text measures --
    they read "Uploading… 69.9%" beside "70%", about 500 CSS px apart.

    Precision, not value: mid-batch the two still differ, because the text
    tracks the file and the bar tracks the batch.
    """
    text = copy_mod.format_progress(0, 1, 0.699)
    assert text == "Uploading… 70%"
    assert "." not in text.split("…")[1]

    # Same MODE, not merely the same precision. Read out of panel.js so
    # this notices if the bar stops rounding half-up: "{:.0f}" is
    # round-half-even, which at an exact tie prints 0% beside a bar
    # reading 1% -- the disagreement this whole change removes, back one
    # value at a time.
    panel = (
        pathlib.Path(__file__).resolve().parents[1]
        / "obs_youtube_uploader"
        / "web"
        / "panel.js"
    ).read_text(encoding="utf-8")
    assert "Math.round(value)" in panel, (
        "the bar no longer rounds half-up; format_progress's int(x + 0.5) "
        "was chosen to match it and has to move with it"
    )
    assert copy_mod.format_progress(0, 1, 0.005) == "Uploading… 1%"
    assert copy_mod.format_progress(0, 1, 0.025) == "Uploading… 3%"
