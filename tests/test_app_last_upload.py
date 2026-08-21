"""The uploaded video's link: it must survive the refresh that follows an
upload, and it must be reachable without hunting for the row.

Uses the real-window fixture because both behaviours are about widget state
after a rebuild, which is exactly what a pure function cannot express.
"""
from pathlib import Path

import pytest

from obs_youtube_uploader import app


def test_a_link_set_during_upload_survives_the_next_refresh(make_window):
    """poll() fires a deferred refresh() as soon as an upload finishes, and
    refresh() used to clear self.links -- so the ↗ appeared and then vanished
    seconds later, which is the whole reason the link felt missing."""
    w = make_window()
    path = w.infos[0].path
    w._set_link(path, "abc123")
    assert w.tree.set(str(path), "link") == app.LINK_GLYPH

    w.refresh()

    assert w.links.get(path) == "https://www.youtube.com/watch?v=abc123"
    assert w.tree.set(str(path), "link") == app.LINK_GLYPH


def test_a_surviving_link_keeps_its_row_colour(make_window):
    """_row_tags reads self.links, so the has_link tint has to come back with
    the glyph rather than the two disagreeing after a rebuild."""
    w = make_window()
    path = w.infos[0].path
    w._set_link(path, "abc123")
    w.refresh()
    assert "has_link" in w.tree.item(str(path), "tags")


def test_links_for_files_that_no_longer_exist_are_dropped(make_window):
    """Keeping links across a rebuild must not turn self.links into a
    permanently growing map keyed by paths that are gone."""
    w = make_window(files=("a.mkv", "b.mkv"))
    doomed = w.infos[0].path
    kept = w.infos[1].path
    w._set_link(doomed, "gone")
    w._set_link(kept, "stays")

    doomed.unlink()
    w.refresh()

    assert doomed not in w.links
    assert w.links.get(kept) == "https://www.youtube.com/watch?v=stays"


def test_the_open_and_copy_controls_are_hidden_until_something_uploads(make_window):
    w = make_window()
    assert not w.last_upload_frame.winfo_ismapped()


def test_a_finished_upload_reveals_the_open_and_copy_controls(make_window):
    w = make_window()
    w._set_link(w.infos[0].path, "abc123")
    w.root.update()
    assert w.last_upload_frame.winfo_ismapped()
    assert w.last_upload_url == "https://www.youtube.com/watch?v=abc123"


def test_the_controls_track_the_most_recent_upload(make_window):
    w = make_window()
    w._set_link(w.infos[0].path, "first")
    w._set_link(w.infos[1].path, "second")
    assert w.last_upload_url.endswith("second")


def test_the_controls_survive_a_refresh(make_window):
    """The panel is not rebuilt by refresh(), but the link it points at is
    keyed by a path that is -- so this guards the two staying in step."""
    w = make_window()
    w._set_link(w.infos[0].path, "abc123")
    w.refresh()
    w.root.update()
    assert w.last_upload_frame.winfo_ismapped()
    assert w.last_upload_url.endswith("abc123")


def test_the_controls_go_away_when_their_file_does(make_window):
    """Offering "Open video" for a recording that has been deleted from the
    list would point at a row the user can no longer see."""
    w = make_window()
    path = w.infos[0].path
    w._set_link(path, "abc123")
    path.unlink()
    w.refresh()
    w.root.update()
    assert w.last_upload_url is None
    assert not w.last_upload_frame.winfo_ismapped()
