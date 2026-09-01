"""The persisted Link column: which recordings are already on YouTube.

The pure store only. Its wiring into refresh and into a finished upload is
covered in test_api_upload.py, which is where the two failures that matter
live -- an empty column after a restart, and a link served for the wrong
recording.
"""

import json
from pathlib import Path

from wingman import links

URL = "https://www.youtube.com/watch?v=abc123"


# --- round-tripping ------------------------------------------------------


def test_load_returns_empty_for_a_missing_file(tmp_path):
    assert links.load(tmp_path / "nope.json") == {}


def test_load_returns_empty_for_a_corrupt_file(tmp_path):
    p = tmp_path / "links.json"
    p.write_text("{not json", encoding="utf-8")
    assert links.load(p) == {}


def test_load_returns_empty_for_a_file_that_is_not_an_object(tmp_path):
    p = tmp_path / "links.json"
    p.write_text('["a", "b"]', encoding="utf-8")
    assert links.load(p) == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "links.json"
    store = {}
    links.remember(store, tmp_path / "a.mkv", 10, 100.0, URL)
    links.save(p, store)
    assert links.load(p) == store


def test_save_creates_the_state_directory(tmp_path):
    p = tmp_path / "deep" / "links.json"
    store = {}
    links.remember(store, tmp_path / "a.mkv", 10, 100.0, URL)
    links.save(p, store)
    assert p.exists()


def test_save_never_raises_on_an_unwritable_path(tmp_path):
    """A finished upload must not become a crash because the disk is full.
    The link is lost; the video is not."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    store = {}
    links.remember(store, tmp_path / "a.mkv", 10, 100.0, URL)
    links.save(blocker / "links.json", store)


def test_a_failed_save_leaves_the_previous_store_intact(tmp_path, monkeypatch):
    """The reason save() goes through atomicio. A plain write_text truncates
    before it writes, so a crash inside that window costs EVERY link rather
    than the one being added -- and unlike a duration, none of them can be
    rebuilt by re-running anything.
    """
    p = tmp_path / "links.json"
    store = {}
    links.remember(store, tmp_path / "a.mkv", 10, 100.0, URL)
    links.save(p, store)

    def boom(*args, **kwargs):
        raise OSError("destination locked")

    monkeypatch.setattr(links.atomicio, "replace_with_retry", boom)
    links.remember(store, tmp_path / "b.mkv", 20, 200.0, URL)
    links.save(p, store)

    reloaded = links.load(p)
    assert links.lookup(reloaded, tmp_path / "a.mkv", 10, 100.0) == URL
    # And no debris beside it, which is atomicio's own guarantee.
    assert sorted(x.name for x in tmp_path.iterdir()) == ["links.json"]


def test_one_malformed_entry_does_not_cost_the_others(tmp_path):
    """A duration can be recomputed by probing again. A link cannot be
    recomputed by anything, so discarding the whole file over one bad
    record is a worse trade here than it is for durations."""
    p = tmp_path / "links.json"
    p.write_text(
        json.dumps(
            {
                "/a.mkv": {"size": 10, "mtime": 100.0, "url": URL},
                "/b.mkv": {"size": "not a number", "mtime": 1.0, "url": URL},
                "/c.mkv": {"mtime": 1.0, "url": URL},
            }
        ),
        encoding="utf-8",
    )
    assert list(links.load(p)) == ["/a.mkv"]


def test_a_non_string_url_is_dropped_rather_than_stringified(tmp_path):
    """str(None) is "None", which renders as a Link cell that looks
    populated and goes nowhere."""
    p = tmp_path / "links.json"
    p.write_text(
        json.dumps(
            {
                "/a.mkv": {"size": 10, "mtime": 100.0, "url": None},
                "/b.mkv": {"size": 10, "mtime": 100.0, "url": ""},
                "/c.mkv": {"size": 10, "mtime": 100.0, "url": 7},
            }
        ),
        encoding="utf-8",
    )
    assert links.load(p) == {}


# --- the identity key ----------------------------------------------------


def test_a_link_is_served_for_the_exact_file_it_was_recorded_against():
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    assert links.lookup(store, Path("/a.mkv"), 10, 100.0) == URL


def test_a_re_recording_at_the_same_path_gets_no_link():
    """THE reason the key is (size, mtime) rather than the path. OBS reuses
    filenames; a path key would hand the new fight the old fight's video."""
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    assert links.lookup(store, Path("/a.mkv"), 4096, 200.0) is None


def test_a_file_still_being_written_gets_no_link():
    """Same path, growing size -- the case watcher.SeenEntry keys this way
    for as well."""
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    assert links.lookup(store, Path("/a.mkv"), 11, 100.0) is None


def test_an_unknown_path_gets_no_link():
    assert links.lookup({}, Path("/a.mkv"), 10, 100.0) is None


def test_an_empty_url_is_never_stored():
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, "")
    assert store == {}


# --- rename ----------------------------------------------------------------
# A rename changes the path a link is keyed under, and NOTHING rebuilds this
# file (see the module docstring). Losing the key here loses the answer the
# Link column exists to give, permanently.


def test_rename_moves_a_link_to_the_new_path():
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    links.rename(store, Path("/a.mkv"), Path("/b.mkv"))
    assert links.lookup(store, Path("/b.mkv"), 10, 100.0) == URL
    assert links.lookup(store, Path("/a.mkv"), 10, 100.0) is None


def test_rename_preserves_the_identity_the_link_was_recorded_against():
    """The (size, mtime) pair is untouched by a rename, so the moved entry
    must still refuse a re-recording at the NEW path."""
    store = {}
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    links.rename(store, Path("/a.mkv"), Path("/b.mkv"))
    assert links.lookup(store, Path("/b.mkv"), 4096, 200.0) is None


def test_rename_of_an_unknown_path_does_nothing():
    """Not every recording has been uploaded. Renaming one that has not
    must not invent an entry, or the Link column grows a glyph for a video
    that does not exist."""
    store = {}
    links.rename(store, Path("/a.mkv"), Path("/b.mkv"))
    assert store == {}


def test_rename_overwrites_an_orphan_at_the_destination():
    """Nothing prunes this file, so an entry for a long-gone file can be
    sitting on the destination key. It cannot match anyway -- lookup
    validates (size, mtime) -- but leaving it would keep a stale URL under
    a name the user just chose."""
    store = {}
    links.remember(store, Path("/b.mkv"), 1, 1.0, "https://youtu.be/old")
    links.remember(store, Path("/a.mkv"), 10, 100.0, URL)
    links.rename(store, Path("/a.mkv"), Path("/b.mkv"))
    assert links.lookup(store, Path("/b.mkv"), 10, 100.0) == URL
