"""The row model that backs every id crossing the bridge.

The Tk window got this property for free: _delete_selected operated on
_chosen(), which could only hold objects from the current discovered list.
The page cannot be trusted with paths in the same way -- not because it is
hostile (it is local, bundled, and loads nothing remote) but because it goes
stale, and a stale page acting on a path whose meaning has changed is a
deletion of the wrong file. Ids resolved against the current snapshot make
that fail cleanly instead.
"""

import dataclasses
import os
from pathlib import Path

import pytest

from obs_youtube_uploader import library, uploader
from obs_youtube_uploader.ui import rows as rows_mod

# set_link takes a finished URL, not a video id -- uploader.watch_url is the
# one place that builds one (test_bridge_contract.py guards that). Derived
# here rather than typed so this file cannot disagree with it.
WATCH = uploader.watch_url("abc123")


def _touch(
    directory: Path, name: str, size: int = 1024, mtime: float | None = None
) -> Path:
    path = directory / name
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _snapshot_over(directory: Path, preselect=None):
    snapshot = rows_mod.RowSnapshot()
    listed = snapshot.rebuild(directory, preselect=preselect)
    return snapshot, listed


# --- identity --------------------------------------------------------------


def test_ids_are_not_paths(tmp_path):
    """The whole reason ids exist. A path crossing the bridge would let a
    stale page name a file the backend never listed."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["id"] != str(tmp_path / "a.mkv")
    assert "a.mkv" not in listed[0]["id"]
    assert os.sep not in listed[0]["id"]


def test_ids_are_unique_within_a_snapshot(tmp_path):
    for name in ("a.mkv", "b.mkv", "c.mkv"):
        _touch(tmp_path, name)
    _, listed = _snapshot_over(tmp_path)
    ids = [row["id"] for row in listed]
    assert len(set(ids)) == len(ids) == 3


def test_an_id_is_stable_for_the_life_of_its_snapshot(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    row_id = listed[0]["id"]
    snapshot.set_duration(row_id, 90.0, definitive=True)
    snapshot.set_link(row_id, WATCH)
    assert [row["id"] for row in snapshot.rows()] == [row_id]


def test_a_rebuild_mints_new_ids_so_a_stale_page_fails_cleanly(tmp_path):
    """The load-bearing case. After a refresh, an id the page is still
    holding must resolve to nothing -- not to whatever now sits in that
    position, which is how a delete hits the wrong recording."""
    _touch(tmp_path, "a.mkv", mtime=2000)
    snapshot, listed = _snapshot_over(tmp_path)
    stale_id = listed[0]["id"]

    (tmp_path / "a.mkv").unlink()
    _touch(tmp_path, "b.mkv", mtime=2000)
    snapshot.rebuild(tmp_path)

    assert snapshot.resolve(stale_id) is None
    assert snapshot.resolve_many([stale_id]) == []


# --- building --------------------------------------------------------------


def test_rows_are_newest_first_like_discover(tmp_path):
    _touch(tmp_path, "old.mkv", mtime=1000)
    _touch(tmp_path, "new.mkv", mtime=2000)
    _, listed = _snapshot_over(tmp_path)
    assert [row["name"] for row in listed] == ["new.mkv", "old.mkv"]


def test_a_row_carries_the_rendered_strings_not_raw_values(tmp_path):
    """The page does no formatting: date suppression, size units, and the
    duration glyphs are decisions library already owns, and a second
    implementation in JS would drift from it."""
    path = _touch(tmp_path, "a.mkv", size=2048, mtime=1000)
    _, listed = _snapshot_over(tmp_path)
    info = library.stat_info(path)
    assert listed[0]["size"] == info.size_str
    assert listed[0]["date"] == info.date_str
    assert listed[0]["duration"] == "…"  # not probed yet


def test_a_missing_directory_lists_nothing(tmp_path):
    _, listed = _snapshot_over(tmp_path / "gone")
    assert listed == []


def test_a_file_that_vanishes_mid_scan_is_skipped(tmp_path, monkeypatch):
    """discover() already tolerates this race, so the row build must too --
    otherwise one unlucky delete empties the whole list."""
    _touch(tmp_path, "a.mkv")
    _touch(tmp_path, "b.mkv")
    real = library.stat_info

    def flaky(path):
        if path.name == "a.mkv":
            raise OSError("vanished")
        return real(path)

    monkeypatch.setattr(library, "stat_info", flaky)
    _, listed = _snapshot_over(tmp_path)
    assert [row["name"] for row in listed] == ["b.mkv"]


# --- preselection ----------------------------------------------------------


def test_preselect_marks_only_the_named_paths(tmp_path):
    """The watcher's whole point: finish a fight, open the window, hit
    Upload with no clicking."""
    watched = _touch(tmp_path, "new.mkv", mtime=2000)
    _touch(tmp_path, "old.mkv", mtime=1000)
    _, listed = _snapshot_over(tmp_path, preselect={watched})
    marked = {row["name"]: row["preselected"] for row in listed}
    assert marked == {"new.mkv": True, "old.mkv": False}


def test_no_preselection_marks_nothing(tmp_path):
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["preselected"] is False


def test_a_preselected_path_that_is_gone_is_simply_absent(tmp_path):
    """The watcher fires on a path that a delete can beat to the refresh."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path, preselect={tmp_path / "gone.mkv"})
    assert [row["preselected"] for row in listed] == [False]


# --- resolution ------------------------------------------------------------


def test_resolve_returns_the_backing_video_info(tmp_path):
    path = _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    info = snapshot.resolve(listed[0]["id"])
    assert isinstance(info, library.VideoInfo)
    assert info.path == path


def test_resolve_of_an_unknown_id_returns_none(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    assert snapshot.resolve("nonsense") is None


def test_resolve_many_drops_ids_it_does_not_know(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    infos = snapshot.resolve_many([listed[0]["id"], "nonsense"])
    assert [info.path.name for info in infos] == ["a.mkv"]


def test_resolve_many_returns_snapshot_order_not_argument_order(tmp_path):
    """Uploads are numbered (n/total) in the order they are handed to
    build_body, so the batch must follow the list the user was looking at
    rather than whatever order the page's selection set iterated in."""
    _touch(tmp_path, "old.mkv", mtime=1000)
    _touch(tmp_path, "new.mkv", mtime=2000)
    snapshot, listed = _snapshot_over(tmp_path)
    ids = [row["id"] for row in listed]
    infos = snapshot.resolve_many(list(reversed(ids)))
    assert [info.path.name for info in infos] == ["new.mkv", "old.mkv"]


def test_resolve_many_of_nothing_is_empty(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    assert snapshot.resolve_many([]) == []


# --- links -----------------------------------------------------------------


def test_set_link_puts_a_watch_url_on_the_row(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], WATCH)
    assert snapshot.rows()[0]["link"] == WATCH


def test_a_row_starts_with_no_link(tmp_path):
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert listed[0]["link"] is None


def test_set_link_on_an_unknown_id_is_ignored(tmp_path):
    """An upload finishing against a row deleted mid-flight."""
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    snapshot.set_link("nonsense", WATCH)
    assert snapshot.rows()[0]["link"] is None


def test_a_link_survives_the_refresh_the_upload_itself_triggers(tmp_path):
    """The watcher fires a refresh the moment an upload finishes. Clearing
    links on rebuild made the glyph appear and vanish a moment later."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], WATCH)
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["link"] == WATCH


def test_a_link_is_dropped_once_its_recording_is_gone(tmp_path):
    """Pruned rather than kept: a path no longer listed cannot be shown or
    opened, so retaining it only grows the map for the life of the process."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_link(listed[0]["id"], WATCH)
    (tmp_path / "a.mkv").unlink()
    snapshot.rebuild(tmp_path)
    _touch(tmp_path, "a.mkv")
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["link"] is None


# --- durations -------------------------------------------------------------


def test_set_duration_renders_the_measured_length(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_set_duration_returns_the_cell_text_it_rendered(tmp_path):
    """The bridge payload comes from here, not from the caller's float.

    U1: api.py pushed the value it had passed IN, so a cold duration cache
    filled the Length column with floats and list.js -- which sorts that
    column by parsing its own rendered cell -- stopped sorting it.
    """
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    assert snapshot.set_duration(listed[0]["id"], 90.0, definitive=True) == "1:30"


def test_a_declined_update_renders_nothing_for_the_caller_to_push(tmp_path):
    """None, not the stale cell: the supersede rule above is only as good
    as what the caller does with it. Pushing over a declined update would
    leave Python holding "1:30" and the page showing the timeout's "—"."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    assert snapshot.set_duration(listed[0]["id"], None, definitive=False) is None
    assert snapshot.set_duration("nonsense", 90.0, definitive=True) is None


def test_set_duration_updates_the_backing_info_too(tmp_path):
    """format_selection_summary reads duration and probed off the infos, not
    off the rows, so the two must not drift."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    info = snapshot.resolve(listed[0]["id"])
    assert (info.duration, info.probed) == (90.0, True)


def test_an_unreadable_recording_stops_showing_as_pending(tmp_path):
    """ "…" and "?" mean opposite things. A finished probe that read nothing
    must move off "measuring", or the summary keeps its partial "+"."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], None, definitive=True)
    assert snapshot.rows()[0]["duration"] == "?"
    assert snapshot.resolve(listed[0]["id"]).probed is True


def test_a_definitive_answer_is_never_replaced_by_a_probe_that_never_ran(tmp_path):
    """The race app._apply_duration guarded: a synchronous probe resolves a
    row, then the background worker's timeout lands for the same row. A
    timeout says nothing about the file and must not overwrite a good
    duration -- which would then be cached and survive restarts."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    snapshot.set_duration(listed[0]["id"], None, definitive=False)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_a_probe_that_never_ran_renders_differently_from_an_unreadable_file(
    tmp_path,
):
    """The verdict flag reaches the CELL, not just the supersede rule above.

    It used to stop at the supersede rule: set_duration marked every
    completed attempt `probed` and rendered "?" for both Nones. So an
    install with no ffprobe at all -- packaging/bin is gitignored and
    fetched at build time -- told the user, once per row, that ffprobe
    could not open that particular file, which it had never tried to.
    """
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], None, definitive=False)
    assert snapshot.rows()[0]["duration"] == "—"
    info = snapshot.resolve(listed[0]["id"])
    # Still "probed": the attempt is over, so the row must stop reading
    # "measuring". It is `answered` that carries whether the attempt said
    # anything, and it is the one this had been discarding.
    assert info.probed is True
    assert info.answered is False


def test_a_probe_that_never_ran_can_still_be_superseded(tmp_path):
    """The mirror of the case above. "No ffprobe configured" is not a
    verdict, so a real one landing later must win."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], None, definitive=False)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "1:30"


def test_set_duration_on_an_unknown_id_is_ignored(tmp_path):
    """A probe landing for a list that has since been rebuilt."""
    _touch(tmp_path, "a.mkv")
    snapshot, _ = _snapshot_over(tmp_path)
    snapshot.set_duration("nonsense", 90.0, definitive=True)
    assert snapshot.rows()[0]["duration"] == "…"


def test_a_rebuild_forgets_durations_because_the_cache_owns_them(tmp_path):
    """Deliberate: durations.resolve is the cache's job and needs the cache
    dict, which this module has no business holding. The caller re-applies
    hits through set_duration after each rebuild."""
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    snapshot.set_duration(listed[0]["id"], 90.0, definitive=True)
    relisted = snapshot.rebuild(tmp_path)
    assert relisted[0]["duration"] == "…"


# --- shape -----------------------------------------------------------------


def test_rows_returns_plain_dicts_for_the_bridge(tmp_path):
    """pywebview serialises what it is handed; a dataclass does not survive
    the trip."""
    _touch(tmp_path, "a.mkv")
    _, listed = _snapshot_over(tmp_path)
    assert isinstance(listed[0], dict)
    assert set(listed[0]) == {
        "id",
        "name",
        "date",
        "size",
        "duration",
        "link",
        "preselected",
    }


def test_rebuild_returns_the_same_rows_it_stores(tmp_path):
    _touch(tmp_path, "a.mkv")
    snapshot, listed = _snapshot_over(tmp_path)
    assert listed == snapshot.rows()


def test_a_row_cannot_be_mutated_in_place(tmp_path):
    """Rows are replaced, never edited: an in-place edit that misses the
    stored copy shows one thing and resolves to another."""
    row = rows_mod.Row(
        id="r1",
        name="a.mkv",
        date="",
        size="",
        duration="",
        link=None,
        preselected=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.name = "b.mkv"
