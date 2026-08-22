"""The pure formatters behind the upload panel's copy.

Same strategy as tests/test_app_selection_summary.py: everything decidable
about these strings is decided in module-level functions, because the labels
and dialogs they feed sit in the one layer this repo has no test harness for.
"""
import pytest

from obs_youtube_uploader import library
from obs_youtube_uploader.ui import copy as copy_mod


def info(name="a.mkv", size=1_000_000, duration=60.0, probed=True):
    from pathlib import Path
    return library.VideoInfo(path=Path(name), mtime=0.0, size=size,
                             duration=duration, probed=probed)


# --- format_progress -------------------------------------------------------

def test_progress_for_a_single_file_does_not_invent_a_file_count():
    assert copy_mod.format_progress(0, 1, 0.948) == "Uploading… 94.8%"


def test_progress_for_a_batch_names_which_file_the_percentage_belongs_to():
    """The bar tracks the batch and this text tracks one file. Before this
    was labelled, a bar at 34% sat beside the text "94.8%" and the two
    looked like a contradiction."""
    assert copy_mod.format_progress(2, 10, 0.948) == "Uploading file 3 of 10… 94.8%"


def test_progress_index_is_zero_based_but_displays_one_based():
    assert copy_mod.format_progress(0, 2, 0.0).startswith("Uploading file 1 of 2")


# --- format_destination ----------------------------------------------------

def test_destination_names_the_channel_once_it_is_known():
    assert copy_mod.format_destination("Zoolanders", "unlisted") == \
        "Uploads go to Zoolanders"


def test_destination_omits_the_privacy_setting():
    """"Uploads go to Zoolanders · unlisted" read as one compound name
    rather than two facts. Privacy belongs to Settings; repeating it here
    bought a misreading. Asserted separately from the line above so that
    reinstating it is a deliberate act with a named test to delete."""
    for privacy in ("public", "unlisted", "private"):
        assert privacy not in copy_mod.format_destination("Zoolanders", privacy)


def test_destination_is_honest_before_the_first_upload():
    """The app holds only the youtube.upload scope, so the channel cannot be
    looked up; it is learned from the first upload response."""
    assert copy_mod.format_destination("", "public") == \
        "Channel confirmed after the first upload"


# --- format_title_hint -----------------------------------------------------

def test_title_hint_is_plain_for_a_single_video():
    assert copy_mod.format_title_hint(1, stitch=False) == "Title"


def test_title_hint_warns_that_a_batch_is_numbered():
    """uploader.build_body silently appends "(n/total)" to every title in a
    batch. The field said only "Title", so ten videos published under ten
    numbered names with no warning."""
    assert copy_mod.format_title_hint(10, stitch=False) == \
        "Title (applies to all 10, numbered 1-10)"


def test_title_hint_for_a_stitched_batch_says_one_video():
    assert copy_mod.format_title_hint(10, stitch=True) == "Title (one stitched video)"


def test_title_hint_with_nothing_selected_is_plain():
    assert copy_mod.format_title_hint(0, stitch=False) == "Title"


def test_stitched_single_selection_is_still_plain():
    assert copy_mod.format_title_hint(1, stitch=True) == "Title"


# --- format_upload_confirm -------------------------------------------------

def test_confirm_names_channel_privacy_and_totals():
    body = copy_mod.format_upload_confirm(
        [info(size=2_000_000_000, duration=3600.0),
         info(size=2_000_000_000, duration=3600.0)],
        title="Null", privacy="unlisted", channel_title="Zoolanders",
        stitch=False, logs=False)
    assert "Zoolanders" in body
    assert "unlisted" in body
    assert "2 recordings" in body
    assert library.format_size(4_000_000_000) in body
    assert "2:00:00" in body


def test_confirm_shows_the_numbering_the_batch_will_actually_get():
    body = copy_mod.format_upload_confirm([info(), info(), info()], title="Fight",
                                     privacy="unlisted", channel_title="Z",
                                     stitch=False, logs=False)
    assert "Fight (1/3)" in body
    assert "Fight (3/3)" in body


def test_confirm_shows_the_untitled_fallback_rather_than_an_empty_quote():
    body = copy_mod.format_upload_confirm([info()], title="", privacy="unlisted",
                                     channel_title="Z", stitch=False, logs=False)
    assert "Untitled" in body


def test_confirm_for_a_stitch_describes_one_video():
    body = copy_mod.format_upload_confirm([info(), info()], title="Fight",
                                     privacy="unlisted", channel_title="Z",
                                     stitch=True, logs=False)
    assert "one video" in body
    assert "(1/2)" not in body


def test_confirm_flags_an_unknown_channel_rather_than_leaving_it_blank():
    body = copy_mod.format_upload_confirm([info()], title="x", privacy="unlisted",
                                     channel_title="", stitch=False, logs=False)
    assert "not known yet" in body


def test_confirm_says_it_is_public_and_irreversible():
    body = copy_mod.format_upload_confirm([info()], title="x", privacy="public",
                                     channel_title="Z", stitch=False, logs=False)
    assert "cannot be undone" in body.lower()


def test_confirm_says_when_combat_logs_will_follow_the_upload():
    """The confirm is the last thing shown before the irreversible action,
    so it must name everything that action now covers: one button posts to
    two places, and only this dialog says so before it happens."""
    body = copy_mod.format_upload_confirm([info()], title="x", privacy="unlisted",
                                          channel_title="Z", stitch=False,
                                          logs=True)
    assert "combat logs" in body.lower()
    assert "Discord" in body


def test_the_irreversibility_warning_covers_the_discord_half_too():
    """Posting to a webhook has no undo in this app either. Naming only
    YouTube in the closing line, under a dialog that is now confirming both,
    understates what the user is about to make permanent."""
    body = copy_mod.format_upload_confirm([info()], title="x", privacy="unlisted",
                                          channel_title="Z", stitch=False,
                                          logs=True)
    closing = body.rsplit("\n\n", 1)[-1]
    assert "cannot be undone" in closing
    assert "Discord" in closing


def test_confirm_stays_silent_about_logs_when_the_box_is_unchecked():
    body = copy_mod.format_upload_confirm([info()], title="x", privacy="unlisted",
                                          channel_title="Z", stitch=False,
                                          logs=False)
    assert "combat" not in body.lower()
    assert "Discord" not in body
