"""Duration cache: the fix for refresh() re-probing every recording.

These tests cover the pure logic only. The Tk wiring in app.py that
consumes it has no test harness in this repo (see library.py's docstring),
so the cache API is deliberately shaped so the untestable layer stays thin.
"""
import json
import logging
from pathlib import Path

import pytest
from obs_youtube_uploader import durations, library


def _info(path, size=10, mtime=100.0):
    return library.VideoInfo(path=path, mtime=mtime, size=size,
                             duration=None, probed=False)


# --- round-tripping ------------------------------------------------------

def test_load_returns_empty_for_missing_file(tmp_path):
    assert durations.load(tmp_path / "nope.json") == {}


def test_load_returns_empty_for_corrupt_file(tmp_path):
    p = tmp_path / "d.json"
    p.write_text("{not json", encoding="utf-8")
    assert durations.load(p) == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "d.json"
    cache = {}
    durations.remember(cache, tmp_path / "a.mkv", 10, 100.0, 42.5)
    durations.save(p, cache)
    assert durations.load(p) == cache


def test_load_skips_malformed_entries_but_keeps_good_ones(tmp_path):
    """One bad entry must not throw away an entire cache -- mirrors
    watcher.load_seen, which does the same for seen.json."""
    p = tmp_path / "d.json"
    p.write_text(json.dumps({
        "/good.mkv": {"size": 10, "mtime": 100.0, "duration": 42.5},
        "/bad.mkv": {"size": "not-an-int", "mtime": 100.0, "duration": 1.0},
        "/missing-key.mkv": {"size": 10},
    }), encoding="utf-8")
    cache = durations.load(p)
    assert list(cache) == ["/good.mkv"]


def test_load_preserves_a_cached_probe_failure(tmp_path):
    """A null duration is a real cached result (ffprobe ran and failed), not
    a malformed entry -- dropping it would re-probe a corrupt file, at 15s
    of timeout each, on every single refresh."""
    p = tmp_path / "d.json"
    p.write_text(json.dumps(
        {"/corrupt.mkv": {"size": 10, "mtime": 100.0, "duration": None}}),
        encoding="utf-8")
    cache = durations.load(p)
    assert cache["/corrupt.mkv"].duration is None


# --- lookup keying -------------------------------------------------------

def test_lookup_hits_on_identical_size_and_mtime(tmp_path):
    cache = {}
    durations.remember(cache, tmp_path / "a.mkv", 10, 100.0, 42.5)
    assert durations.lookup(cache, tmp_path / "a.mkv", 10, 100.0) == (True, 42.5)


def test_lookup_misses_for_unknown_path(tmp_path):
    assert durations.lookup({}, tmp_path / "a.mkv", 10, 100.0) == (False, None)


@pytest.mark.parametrize("size,mtime", [(11, 100.0), (10, 101.0), (11, 101.0)])
def test_lookup_misses_when_the_file_changed(tmp_path, size, mtime):
    """A recording still being written keeps the same path. Keying on
    (size, mtime) is what makes a stale duration impossible."""
    cache = {}
    durations.remember(cache, tmp_path / "a.mkv", 10, 100.0, 42.5)
    assert durations.lookup(cache, tmp_path / "a.mkv", size, mtime) == (False, None)


def test_lookup_hit_reports_a_cached_failure_as_a_hit(tmp_path):
    """(True, None) and (False, None) must be distinguishable: the first
    means 'ffprobe ran and failed', the second 'not probed yet'."""
    cache = {}
    durations.remember(cache, tmp_path / "a.mkv", 10, 100.0, None)
    assert durations.lookup(cache, tmp_path / "a.mkv", 10, 100.0) == (True, None)


# --- resolve: the part refresh() delegates to ---------------------------

def test_resolve_splits_cached_from_pending(tmp_path):
    cache = {}
    durations.remember(cache, tmp_path / "cached.mkv", 10, 100.0, 42.5)
    infos = [_info(tmp_path / "cached.mkv"), _info(tmp_path / "fresh.mkv")]

    pending = durations.resolve(cache, infos)

    assert [i.path.name for i in pending] == ["fresh.mkv"]
    assert infos[0].duration == 42.5 and infos[0].probed is True
    assert infos[1].duration is None and infos[1].probed is False


def test_resolve_marks_a_cached_failure_as_probed(tmp_path):
    """Nothing to re-probe: ffprobe already ran on this exact file and
    failed. It must NOT come back as pending on every refresh."""
    cache = {}
    durations.remember(cache, tmp_path / "corrupt.mkv", 10, 100.0, None)
    infos = [_info(tmp_path / "corrupt.mkv")]

    assert durations.resolve(cache, infos) == []
    assert infos[0].probed is True and infos[0].duration is None


def test_resolve_on_an_empty_cache_makes_everything_pending(tmp_path):
    infos = [_info(tmp_path / "a.mkv"), _info(tmp_path / "b.mkv")]
    assert durations.resolve({}, infos) == infos


# --- pruning -------------------------------------------------------------

def test_prune_drops_entries_for_paths_no_longer_present(tmp_path):
    """Without this the cache grows forever as recordings are deleted --
    the same reason watcher.prune() exists for seen.json."""
    cache = {}
    durations.remember(cache, tmp_path / "kept.mkv", 10, 100.0, 1.0)
    durations.remember(cache, tmp_path / "gone.mkv", 10, 100.0, 2.0)

    removed = durations.prune(cache, [tmp_path / "kept.mkv"])

    assert removed == 1
    assert list(cache) == [str(tmp_path / "kept.mkv")]


def test_prune_reports_zero_when_nothing_to_do(tmp_path):
    cache = {}
    durations.remember(cache, tmp_path / "kept.mkv", 10, 100.0, 1.0)
    assert durations.prune(cache, [tmp_path / "kept.mkv"]) == 0


def test_prune_drops_entries_outside_the_scanned_folder(tmp_path):
    """prune() keys on membership in the list it is given, NOT on the file
    existing somewhere. app.refresh passes the folder it just scanned, so
    changing the recording folder legitimately discards the old folder's
    durations. Documented here because it reads like an existence check."""
    other = tmp_path / "other"
    other.mkdir()
    still_on_disk = other / "elsewhere.mkv"
    still_on_disk.write_bytes(b"x")
    cache = {}
    durations.remember(cache, still_on_disk, 10, 100.0, 1.0)

    assert durations.prune(cache, [tmp_path / "in-folder.mkv"]) == 1
    assert cache == {}
    assert still_on_disk.exists()  # dropped despite being present


def test_prune_count_is_usable_as_a_dirty_flag(tmp_path):
    """app.refresh persists only when prune returns non-zero, so the count
    must be exact -- a false zero would leak deleted recordings into
    durations.json forever, and a false non-zero would rewrite the file on
    every single refresh."""
    cache = {}
    durations.remember(cache, tmp_path / "a.mkv", 10, 100.0, 1.0)
    durations.remember(cache, tmp_path / "b.mkv", 10, 100.0, 2.0)
    live = [tmp_path / "a.mkv", tmp_path / "b.mkv"]

    assert durations.prune(cache, live) == 0
    assert durations.prune(cache, live[:1]) == 1
    assert durations.prune(cache, live[:1]) == 0


# --- caching policy ------------------------------------------------------

def test_only_a_definitive_verdict_reaches_the_cache(tmp_path):
    """The policy now lives in library.probe's `definitive` flag rather
    than in this module; these pin the contract remember() relies on."""
    cache = {}
    # A definitive failure is worth storing: re-probing a corrupt file on
    # every refresh is pure waste.
    durations.remember(cache, tmp_path / "corrupt.mkv", 10, 100.0, None)
    assert durations.lookup(cache, tmp_path / "corrupt.mkv", 10, 100.0) == (True, None)


# --- failure handling ----------------------------------------------------

def test_save_failure_does_not_raise(tmp_path, monkeypatch):
    """A read-only or full disk must degrade to "cache nothing this run",
    never crash a refresh -- watcher._save takes the same position.

    The failure is injected rather than produced with chmod: as root (which
    CI may well be) a read-only directory is still writable, and the test
    would pass without exercising the guard at all.
    """
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    durations.save(tmp_path / "d.json", {})  # must not raise


def test_save_failure_is_logged(tmp_path, monkeypatch, caplog):
    """Degrading silently would leave no trace of a cache that never
    persists -- the user would just see every launch re-probe forever."""
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    with caplog.at_level(logging.WARNING):
        durations.save(tmp_path / "d.json", {})
    assert "duration cache" in caplog.text
