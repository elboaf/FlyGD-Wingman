"""Bridge-level tests for the js_api object.

These run headless with no webview installed: the Api never imports
pywebview, and every test drives it through a fake window that records the
JavaScript it was asked to evaluate. That is the whole reason `_window` is
assigned rather than constructed -- ui.window.create() does it in
production, and a test does it directly.
"""

import json
import os
import threading
from pathlib import Path

import pytest

from tests.test_scheduler import FakeClock
from wingman import durations, library, links, uploader
from wingman.ui.api import Api, AppState
from wingman.ui.rows import RowSnapshot


class FakeWindow:
    """Records evaluate_js calls instead of running them."""

    def __init__(self, fail=False):
        self.evaluated: list[str] = []
        self.minimized = 0
        self.hidden = 0
        self.shown = 0
        self.destroyed = 0
        self._fail = fail

    def evaluate_js(self, script: str):
        if self._fail:
            raise RuntimeError("window is gone")
        self.evaluated.append(script)

    def minimize(self):
        self.minimized += 1

    def hide(self):
        self.hidden += 1

    def show(self):
        self.shown += 1

    def destroy(self):
        self.destroyed += 1


def make_state(tmp_path, **overrides):
    settings = {
        "privacy": "unlisted",
        "category": "20",
        "notify_mode": "toast",
        "recording_dir": str(tmp_path),
        "discord_webhook": "",
        "gamelogs_dir": None,
        "channel_id": "",
        "channel_title": "",
    }
    settings.update(overrides)
    return AppState(
        recording_dir=Path(tmp_path),
        settings=settings,
        ffmpeg_bin="/usr/bin/ffmpeg",
        ffprobe_bin=None,
    )


def make_api(tmp_path, window=None, **kwargs):
    api = Api(make_state(tmp_path), **kwargs)
    api._window = window if window is not None else FakeWindow()
    return api


def pushes(window: FakeWindow) -> list[tuple[str, object]]:
    """Decode recorded JS back into (handler, payload) pairs."""
    out = []
    for script in window.evaluated:
        handler = script.split("window.", 1)[1].split(" ", 1)[0]
        payload = json.loads(
            script[script.index("(", script.rindex(handler)) + 1 : script.rindex(")")]
        )
        out.append((handler, payload))
    return out


def test_push_calls_the_named_handler_with_a_json_payload(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api._push("onStatus", {"text": "Found 3 video(s)", "kind": "FG"})

    assert pushes(window) == [("onStatus", {"text": "Found 3 video(s)", "kind": "FG"})]


def test_push_guards_on_the_handler_existing(tmp_path):
    # A worker can push before the page has finished defining its handlers.
    # Without the guard that is a ReferenceError thrown into a callback
    # nobody is watching, and the message is lost with no diagnostic.
    window = FakeWindow()
    make_api(tmp_path, window)._push("onStatus", {"text": "x", "kind": "FG"})

    assert "window.onStatus &&" in window.evaluated[0]


def test_push_survives_a_dead_window(tmp_path):
    # Workers keep pushing while the user is closing the window. A teardown
    # race must not take down the upload thread.
    make_api(tmp_path, FakeWindow(fail=True))._push(
        "onStatus", {"text": "x", "kind": "FG"}
    )


class RecordingSkills:
    def __init__(self):
        self.calls = []

    def _push_state(self, *, force=False):
        self.calls.append(force)


def test_eve_authority_change_pushes_the_shared_event_and_keeps_skills_compat(tmp_path):
    window = FakeWindow()
    skills = RecordingSkills()
    api = make_api(tmp_path, window=window, skills=skills)

    api._eve_authority_changed()

    assert pushes(window) == [("onEveAuthorityChanged", {})]
    assert skills.calls == [True]


def test_close_hides_rather_than_destroying(tmp_path):
    """REGRESSION GUARD. This is a tray app: the Tk window bound
    WM_DELETE_WINDOW to hide(), and destroying here would return from
    webview.start(), stop the tray, and end the process -- so closing the
    window would silently stop the recording watcher."""
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api.minimize()
    api.close()

    assert (window.minimized, window.hidden) == (1, 1)
    assert window.destroyed == 0, "close() must not destroy; only tray Quit does"


def test_api_exposes_no_public_non_method_attributes(tmp_path):
    """The single most expensive lesson from the spike, as an assertion.

    pywebview builds its JS proxy by walking the public attributes of the
    js_api object. A public attribute holding a webview.Window sends that
    walk into the WinForms native object, where Rectangle.Empty returns
    itself, and it recurses until RecursionError terminates the process --
    observed as a hard crash about eight seconds after launch, with no
    traceback pointing anywhere near the offending attribute.

    Checking dir() rather than __dict__ catches class-level constants and
    properties too, which the walk reaches just as readily.
    """
    api = make_api(tmp_path)

    public = [name for name in dir(api) if not name.startswith("_")]
    assert public, "guard is worthless if the class has no public surface at all"
    non_methods = [name for name in public if not callable(getattr(api, name))]
    assert non_methods == []


def test_alert_pushes_a_dialog_with_no_request_id(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)

    api._alert("warning", "Nothing selected", "Select at least one recording.")

    assert pushes(window) == [
        (
            "onDialog",
            {
                "kind": "warning",
                "title": "Nothing selected",
                "body": "Select at least one recording.",
                "request_id": None,
            },
        )
    ]


def test_confirm_blocks_the_worker_until_the_page_answers(tmp_path):
    """The one request/response pair in an otherwise fire-and-forget protocol.

    Driven from two threads on purpose: the worker parks in _confirm exactly
    as it used to park in messagebox.askyesno, and the answer arrives on the
    thread servicing pywebview.api.* -- a different thread, which is what
    makes the Event necessary rather than decorative.
    """
    answered = threading.Event()

    class SignallingWindow(FakeWindow):
        def evaluate_js(self, script):
            super().evaluate_js(script)
            answered.set()

    window = SignallingWindow()
    api = make_api(tmp_path, window)
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(
            ok=api._confirm("Delete 2 files?", "This cannot be undone.")
        )
    )
    worker.start()

    assert answered.wait(5), "confirm never reached the page"
    handler, payload = pushes(window)[0]
    assert handler == "onDialog"
    assert payload["kind"] == "confirm"
    assert payload["request_id"]
    assert worker.is_alive(), "confirm returned without waiting for an answer"

    api.dialog_response(payload["request_id"], True)
    worker.join(5)
    assert not worker.is_alive()
    assert result == {"ok": True}


def test_confirm_returns_false_when_the_page_declines(tmp_path):
    api = make_api(tmp_path, id_factory=lambda: "req-1")
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(ok=api._confirm("Upload 3 videos?", "body"))
    )
    worker.start()
    # id_factory is fixed, so the id is known without racing the push.
    for _ in range(500):
        api.dialog_response("req-1", False)
        worker.join(0.01)
        if not worker.is_alive():
            break
    assert result == {"ok": False}


def test_dialog_response_for_an_unknown_request_is_ignored(tmp_path):
    # A reloaded page can answer a dialog whose worker is long gone.
    make_api(tmp_path).dialog_response("nobody-is-waiting", True)


def test_confirm_forgets_the_request_once_answered(tmp_path):
    api = make_api(tmp_path, id_factory=lambda: "req-2")
    worker = threading.Thread(target=lambda: api._confirm("t", "b"))
    worker.start()
    for _ in range(500):
        api.dialog_response("req-2", True)
        worker.join(0.01)
        if not worker.is_alive():
            break
    # Left in the map, every dialog the app ever shows leaks an Event for the
    # life of the process.
    assert api._dialogs == {}


class InlineThread:
    """Runs the worker synchronously on start().

    The probe worker is a plain daemon thread in production. Running it
    inline is what lets these tests assert on a full drain with no sleeps
    and no join timeouts -- the queue is already loaded by the time
    list_rows() returns.
    """

    def __init__(self, target=None, daemon=False):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def recordings(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    for name in ("a.mkv", "b.mkv"):
        (folder / name).write_bytes(b"\0" * 2048)
    return folder


def rows_api(recordings, tmp_path, clock, probe, window=None, links_file=None):
    api = Api(
        make_state(recordings),
        rows=RowSnapshot(),
        durations_file=tmp_path / "durations.json",
        links_file=links_file or tmp_path / "links.json",
        spawn=InlineThread,
        probe=probe,
        timer=clock.timer,
    )
    api._window = window if window is not None else FakeWindow()
    return api


def test_list_rows_pushes_every_row_then_streams_durations(recordings, tmp_path):
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(
        recordings,
        tmp_path,
        clock,
        probe=lambda path, binary: (12.5, True),
        window=window,
    )

    api.list_rows()

    # Rows go out immediately, drawn from a plain stat. The whole point of
    # the split is that the list appears before any ffprobe has run.
    handler, payload = pushes(window)[0]
    assert handler == "onRows"
    assert {row["name"] for row in payload["rows"]} == {"a.mkv", "b.mkv"}

    clock.fire()  # one drain tick

    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert len(streamed) == 2
    # The RENDERED cell, not the float that was probed (U1). list.js writes
    # this straight into the Length column and parses it back out to sort,
    # so a number here is a column that shows `12.5` and stops sorting.
    assert {p["duration"] for p in streamed} == {library.format_duration(12.5)}
    assert all(p["definitive"] for p in streamed)
    # KEY IS `id`, matching the row objects onRows delivered.
    assert {p["id"] for p in streamed} == {r["id"] for r in payload["rows"]}


def test_preselect_marks_the_named_paths(recordings, tmp_path):
    """The watcher's channel: finish a fight, open the window, hit Upload."""
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(
        recordings,
        tmp_path,
        clock,
        probe=lambda path, binary: (12.5, True),
        window=window,
    )

    api.list_rows(preselect={recordings / "a.mkv"})

    _handler, payload = pushes(window)[0]
    marked = {row["name"]: row["preselected"] for row in payload["rows"]}
    assert marked == {"a.mkv": True, "b.mkv": False}


def test_the_panel_text_is_computed_in_python(recordings, tmp_path):
    """One tested implementation of each string, not two.

    Selection lives in the page, so the page asks for these rather than
    reimplementing format_selection_summary and format_title_hint in
    JavaScript. Both carry decisions subtle enough that a second copy would
    drift: the summary's "+" for an outstanding probe, and the title hint's
    disclosure that a batch is numbered.
    """
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]

    assert api.panel_text([], False)["summary"] == "Nothing selected"
    assert api.panel_text(ids[:1], False)["summary"].startswith("1 selected")


def test_the_title_hint_tracks_the_selection_and_the_stitch_flag(recordings, tmp_path):
    """Three distinct labels, because three distinct things happen.

    A batch is numbered per file, a stitch collapses to one video, and a
    single selection needs no disclosure at all. Asserted verbatim against
    format_title_hint's real strings -- this is copy, and copy is what
    regresses.
    """
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]  # the fixture holds two

    assert api.panel_text(ids, False)["title_hint"] == (
        "Title (applies to all 2, numbered 1-2)"
    )
    assert api.panel_text(ids, True)["title_hint"] == "Title (one stitched video)"
    assert api.panel_text(ids[:1], False)["title_hint"] == "Title"


def test_the_summary_ignores_ids_the_snapshot_does_not_know(recordings, tmp_path):
    """A stale page after a refresh must not make the summary lie."""
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()
    assert api.panel_text(["nonsense"], False)["summary"] == "Nothing selected"


def test_measured_durations_are_persisted_and_reused(recordings, tmp_path):
    cache_file = tmp_path / "durations.json"
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()
    clock.fire()

    assert set(durations.load(cache_file)) == {
        str(recordings / "a.mkv"),
        str(recordings / "b.mkv"),
    }

    # Second Api, same cache file: nothing left to probe, so no worker and
    # no drain loop at all.
    window2 = FakeWindow()
    clock2 = FakeClock()

    def explode(path, binary):
        raise AssertionError("probed a file already in the cache")

    rows_api(recordings, tmp_path, clock2, probe=explode, window=window2).list_rows()

    # The subject is the PROBE: a cache hit must produce no worker, no
    # drain loop, and above all no onDuration behind the rows. This read
    # `== ["onRows"]` until list_rows also began re-stating the combat-log
    # button's flag on every rebuild -- its only repair for a disarm lost
    # into a hidden window -- which has nothing to do with probing.
    names = [name for name, _ in pushes(window2)]
    assert "onRows" in names
    assert "onDuration" not in names
    assert clock2.timers == []

    # The rows must CARRY the cached durations, not merely skip the probe.
    # rebuild() freezes `duration` into each Row while it is still unknown,
    # and rows() serialises those frozen Rows rather than the VideoInfos
    # that durations.resolve() mutates -- so without an explicit re-apply
    # the page is handed the measuring glyph and, because a cache hit is
    # never in `pending`, no onDuration ever arrives to correct it. The
    # Length column then reads "measuring" forever for every recording that
    # has ever been probed.
    _, payload = pushes(window2)[0]
    assert [row["duration"] for row in payload["rows"]] == ["0:12", "0:12"]


def test_a_cached_duration_reaches_the_page_on_the_very_first_push(
    recordings, tmp_path
):
    """The regression above, isolated to one row and one assertion.

    The selection summary is computed in Python straight off the infos, so
    it showed the right total while the list showed the glyph -- which is
    what made this look like a rendering bug rather than a missing re-apply.
    """
    cache_file = tmp_path / "durations.json"
    for name in ("a.mkv", "b.mkv"):
        path = recordings / name
        stat = path.stat()
        cache = durations.load(cache_file)
        durations.remember(cache, path, stat.st_size, stat.st_mtime, 90.0)
        durations.save(cache_file, cache)

    window = FakeWindow()

    def explode(path, binary):
        raise AssertionError("probed a file the cache already knew")

    rows_api(
        recordings, tmp_path, FakeClock(), probe=explode, window=window
    ).list_rows()

    _, payload = pushes(window)[0]
    assert [row["duration"] for row in payload["rows"]] == ["1:30", "1:30"]


def _seed_link(links_file, path, url):
    """Record *url* against the file's real (size, mtime), as an upload
    would have on a previous run."""
    stat = path.stat()
    store = links.load(links_file)
    links.remember(store, path, stat.st_size, stat.st_mtime, url)
    links.save(links_file, store)


def test_a_link_from_a_previous_session_reaches_the_page_on_first_push(
    recordings, tmp_path
):
    """The whole point of persisting links. RowSnapshot._links is
    in-memory, so before the store existed the Link column was empty on
    every launch -- including for recordings that were already on YouTube,
    which is the one question the column is there to answer.
    """
    links_file = tmp_path / "links.json"
    url = uploader.watch_url("abc123")
    _seed_link(links_file, recordings / "a.mkv", url)

    window = FakeWindow()
    api = rows_api(
        recordings,
        tmp_path,
        FakeClock(),
        probe=lambda path, binary: (1.0, True),
        window=window,
        links_file=links_file,
    )
    api.list_rows()

    _, payload = pushes(window)[0]
    by_name = {row["name"]: row for row in payload["rows"]}
    assert by_name["a.mkv"]["link"] == url
    assert by_name["b.mkv"]["link"] is None
    # And the context menu can act on it: copy_path/open_path read a map
    # keyed by row id, which a restore that only filled the snapshot would
    # have left empty behind a link the page was already drawing.
    assert api.copy_path(by_name["a.mkv"]["id"]) == url


def test_the_row_id_link_map_does_not_grow_across_refreshes(recordings, tmp_path):
    """Every key in Api._links is a row id, and rebuild() mints new ones --
    so after a refresh they are all unreachable by definition.

    This became worth asserting when the restore loop was added: it re-adds
    a key per linked row on every refresh, and refresh runs on launch, tray
    open, settings save, delete and every watcher find. Left uncleared the
    map would grow for the life of the process, holding ids nothing can
    resolve.
    """
    links_file = tmp_path / "links.json"
    _seed_link(links_file, recordings / "a.mkv", uploader.watch_url("abc123"))
    api = rows_api(
        recordings,
        tmp_path,
        FakeClock(),
        probe=lambda path, binary: (1.0, True),
        links_file=links_file,
    )
    api.list_rows()
    first = dict(api._links)
    assert len(first) == 1

    api.list_rows()
    api.list_rows()

    assert len(api._links) == 1, (
        "one linked recording, one entry, however many refreshes"
    )
    # And it is the CURRENT id, not a survivor of an earlier snapshot.
    assert set(api._links) != set(first)
    live = {row["id"] for row in api._rows.rows()}
    assert set(api._links) <= live


def test_a_re_recording_within_one_session_loses_the_link_too(recordings, tmp_path):
    """The same-session half of the rule, and the one that nearly shipped
    wrong.

    RowSnapshot._links is keyed by PATH and survives rebuild -- that is
    deliberate, it is what keeps a link through the refresh an upload itself
    triggers. But it means a file re-recorded at a path that was uploaded
    earlier in this session inherits the old link from the snapshot,
    whatever the persisted store says. The restore loop is therefore
    authoritative in both directions: it sets a link when the store has one
    for this exact file, and CLEARS it when the store does not.
    """
    links_file = tmp_path / "links.json"
    target = recordings / "a.mkv"
    url = uploader.watch_url("abc123")
    _seed_link(links_file, target, url)

    window = FakeWindow()
    api = rows_api(
        recordings,
        tmp_path,
        FakeClock(),
        probe=lambda path, binary: (1.0, True),
        window=window,
        links_file=links_file,
    )
    api.list_rows()
    first = {r["name"]: r for r in pushes(window)[0][1]["rows"]}
    assert first["a.mkv"]["link"] == url, "fixture is wrong if this fails"

    # OBS writes a new recording over the same filename, same session.
    target.write_bytes(b"\0" * 4096)
    os.utime(target, (5000, 5000))
    window.evaluated.clear()
    api.list_rows()

    after = {r["name"]: r for r in pushes(window)[0][1]["rows"]}
    assert after["a.mkv"]["link"] is None, (
        "the row inherited the previous recording's video -- the one failure "
        "mode the (size, mtime) key exists to prevent"
    )
    assert api.copy_path(after["a.mkv"]["id"]) == ""


def test_a_re_recording_at_the_same_path_is_not_given_the_old_link(
    recordings, tmp_path
):
    """The reason the store is keyed on (size, mtime). A wrong duration is
    cosmetic; a wrong link opens a different fight, or somebody else's."""
    links_file = tmp_path / "links.json"
    target = recordings / "a.mkv"
    _seed_link(links_file, target, uploader.watch_url("abc123"))
    # OBS reuses filenames: same path, new recording.
    target.write_bytes(b"\0" * 4096)
    os.utime(target, (5000, 5000))

    window = FakeWindow()
    rows_api(
        recordings,
        tmp_path,
        FakeClock(),
        probe=lambda path, binary: (1.0, True),
        window=window,
        links_file=links_file,
    ).list_rows()

    _, payload = pushes(window)[0]
    assert [row["link"] for row in payload["rows"]] == [None, None]


def test_a_corrupt_link_store_costs_the_links_and_nothing_else(recordings, tmp_path):
    """Unlike durations, a lost link cannot be recomputed -- but it still
    must not stop the list rendering."""
    links_file = tmp_path / "links.json"
    links_file.write_text("{not json", encoding="utf-8")

    window = FakeWindow()
    rows_api(
        recordings,
        tmp_path,
        FakeClock(),
        probe=lambda path, binary: (1.0, True),
        window=window,
        links_file=links_file,
    ).list_rows()

    _, payload = pushes(window)[0]
    assert len(payload["rows"]) == 2
    assert [row["link"] for row in payload["rows"]] == [None, None]


def test_an_indefinite_probe_result_is_not_cached(recordings, tmp_path):
    """library.probe's second return value, honoured end to end.

    (None, False) means ffprobe never got a verdict -- no binary, launch
    failure, timeout. The cache key is (size, mtime) and never changes
    again for a finished recording, so remembering that answer would pin
    the row to "?" forever and permanently block its combat-log upload.
    """
    clock = FakeClock()
    window = FakeWindow()
    api = rows_api(
        recordings,
        tmp_path,
        clock,
        probe=lambda path, binary: (None, False),
        window=window,
    )
    api.list_rows()
    clock.fire()

    assert durations.load(tmp_path / "durations.json") == {}
    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert [p["definitive"] for p in streamed] == [False, False]


def test_a_superseded_answer_is_not_pushed_over_a_definitive_one(recordings, tmp_path):
    """The supersede rule reaches the PAGE, not just RowSnapshot.

    _probe_now sweeps the selection before a combat-log upload and can
    re-probe a row the drain already answered definitively. RowSnapshot
    declines that update; pushing anyway -- which the two call sites did
    when they pushed their own argument rather than what was rendered --
    left Python holding "0:12" and the column showing the timeout.
    """
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(
        recordings,
        tmp_path,
        clock,
        probe=lambda path, binary: (12.5, True),
        window=window,
    )
    api.list_rows()
    clock.fire()
    window.evaluated.clear()

    row_id = api._rows.rows()[0]["id"]
    api._push_duration(row_id, None, False)

    assert [p for name, p in pushes(window) if name == "onDuration"] == []
    assert api._rows.rows()[0]["duration"] == library.format_duration(12.5)


def test_the_drain_loop_stops_once_the_worker_is_done(recordings, tmp_path):
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()

    clock.fire()

    # The worker's sentinel arrived in that same tick; leaving the loop
    # armed would burn a timer every 100ms for the life of the process.
    assert clock.timers[-1].cancelled


def test_a_straggler_from_a_superseded_refresh_is_dropped(recordings, tmp_path):
    """The generation counter, which is what makes the async part safe.

    A probe started against the previous list can land after the list has
    been rebuilt -- the watcher fires a refresh on exactly the events that
    also start probes. Its result refers to rows that no longer exist, and
    writing it would put a duration from one recording onto another.
    """
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(
        recordings,
        tmp_path,
        clock,
        probe=lambda path, binary: (12.5, True),
        window=window,
    )
    api.list_rows()
    clock.fire()
    window.evaluated.clear()

    api.list_rows()  # bumps the generation; the drain above has stopped
    stale_id = api._rows.rows()[0]["id"]
    stale_info = api._rows.resolve(stale_id)
    api._probe_queue.put((0, stale_id, stale_info, 999.0, True))
    api._drain_probes(api._generation)

    assert [p for name, p in pushes(window) if name == "onDuration"] == []
    assert 999.0 not in {
        e.duration for e in durations.load(tmp_path / "durations.json").values()
    }


def test_a_drain_for_a_superseded_generation_stops_itself(recordings, tmp_path):
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    api.list_rows()
    stale_generation = api._generation
    api._generation += 1  # as a concurrent list_rows would

    api._drain_probes(stale_generation)

    assert clock.timers[-1].cancelled


def test_the_cache_is_written_on_every_tick_that_applied_something(
    recordings, tmp_path, monkeypatch
):
    """Persist per drain, not once at the end.

    A cold scan of a large folder runs for a while. Saving only when the
    worker finishes means a user who quits partway through loses every
    duration measured so far -- and pays for the whole scan again on the
    next launch, which is the exact cost this cache exists to avoid.
    """
    from wingman.ui import api as api_mod

    saves = []
    real_save = api_mod.durations.save
    monkeypatch.setattr(
        api_mod.durations,
        "save",
        lambda path, cache: (saves.append(len(cache)), real_save(path, cache)),
    )

    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock, probe=lambda path, binary: (12.5, True))
    # Hand-drive the queue so results land across two ticks rather than one.
    api._generation += 1
    generation = api._generation
    api._rows.rebuild(recordings)
    rows = api._rows.rows()

    for row in rows:
        api._probe_queue.put(
            (generation, row["id"], api._rows.resolve(row["id"]), 12.5, True)
        )
        api._drain_probes(generation)
    api._drain_probes(generation)  # a tick with nothing waiting

    assert saves == [1, 2], (
        "one save per tick that applied results, none for an empty tick"
    )


class _FakeHost:
    """Records what the bridge asked for, in place of a real PreviewHost."""

    def __init__(self):
        self.hotkeys = None
        self.status = {}
        self.chars = []
        self.started = False
        # Mirrors PreviewHost.is_running. Defaults True so existing fixtures
        # that never call start()/stop() still read as "the host is up",
        # matching what they asserted before this field existed; a test for
        # the stopped-host gate flips it explicitly.
        self.is_running = True

    def set_hotkeys(self, table):
        self.hotkeys = table

    def hotkey_status(self):
        return dict(self.status)

    def characters(self):
        return list(self.chars)

    def client_sizes(self):
        # get_preview_hotkey_state now reads this unconditionally when the
        # host is live (api.py); the existing fixtures here never set client
        # geometry, so an empty dict matches what they asserted before this
        # field existed.
        return {}

    def layout_entries(self):
        return {}

    def start(self):
        self.started = True
        self.is_running = True

    def stop(self):
        self.started = False
        self.is_running = False


def test_capture_preview_bind_returns_a_canonical_gesture(tmp_path):
    api = make_api(tmp_path)

    result = api.capture_preview_bind({"ctrl": True, "alt": True, "code": "F1"})

    assert result == {"gesture": "Ctrl+Alt+F1", "error": None}


def test_parse_preview_bind_reports_a_rejected_chord(tmp_path):
    api = make_api(tmp_path)

    assert api.parse_preview_bind("F1")["error"] == "unparseable"
    assert api.parse_preview_bind("Ctrl+F1")["gesture"] == "Ctrl+F1"


def test_set_preview_binds_persists_and_pushes_to_the_host(tmp_path):
    fake_host = _FakeHost()
    api = make_api(tmp_path, preview_host=fake_host)

    ok = api.set_preview_binds(
        {"characters": {"Alice": "ctrl+f1"}, "cycle_next": "", "cycle_prev": ""}
    )

    assert ok is True
    stored = api._state.settings["preview"]["hotkeys"]["characters"]
    assert stored == {"Alice": "Ctrl+F1"}  # canonicalised
    assert fake_host.hotkeys["characters"] == {"Alice": "Ctrl+F1"}


def test_set_preview_binds_rejects_an_unparseable_chord(tmp_path):
    fake_host = _FakeHost()
    api = make_api(tmp_path, preview_host=fake_host)
    # A real settings document always has this section (settings.DEFAULTS);
    # make_state's minimal fixture does not, so seed it to prove a rejected
    # chord leaves the existing table untouched rather than KeyError-ing.
    api._state.settings["preview"] = {
        "hotkeys": {"characters": {}, "cycle_next": "", "cycle_prev": ""}
    }

    assert api.set_preview_binds({"characters": {"Alice": "nonsense"}}) is False
    assert api._state.settings["preview"]["hotkeys"]["characters"] == {}


def test_hotkey_state_reports_registration_and_live_characters(tmp_path):
    fake_host = _FakeHost()
    fake_host.status = {"Ctrl+F1": False}
    fake_host.chars = ["Alice"]
    api = make_api(tmp_path, preview_host=fake_host)

    state = api.get_preview_hotkey_state()

    assert state["registration"] == {"Ctrl+F1": False}
    assert state["characters"] == ["Alice"]


def test_hotkey_state_is_readable_with_no_host(tmp_path):
    """Off Windows the host is None and every call site must stay a plain
    no-op rather than a platform check."""
    api = make_api(tmp_path)

    state = api.get_preview_hotkey_state()

    assert state["characters"] == []
    assert state["registration"] == {}


def test_hotkey_state_reports_nothing_live_once_the_host_has_stopped(tmp_path):
    """A host that exists but is not running (previews switched off) must
    not keep serving its last characters/registration snapshot -- that is
    exactly the state that reads as 'previews are on and every chord is
    registered' when neither is true. is_running, not merely `host is not
    None`, is what closes the window between stop() and _teardown running
    on the preview thread; both must report the same empty shape."""
    fake_host = _FakeHost()
    fake_host.status = {"Ctrl+F1": True}
    fake_host.chars = ["Alice"]
    fake_host.is_running = False
    api = make_api(tmp_path, preview_host=fake_host)

    state = api.get_preview_hotkey_state()

    assert state["characters"] == []
    assert state["registration"] == {}
    # Still well-formed, not partial: everything else the page needs.
    assert state["hotkeys"] == {}
    assert state["roster"] == []
    assert "bookmark_chords" in state


def test_bookmark_chords_are_active_only_when_they_are_registered(tmp_path):
    """A bookmark bind is registered only for enabled window titles under an
    enabled feature. Warning about chords that are not registered anywhere
    would cry wolf -- but the collision goes latent rather than away, so it
    is still reported, just not as a warning."""
    fake_host = _FakeHost()
    api = make_api(tmp_path, preview_host=fake_host)
    api._state.settings["eve_bookmarks"] = {
        "enabled": True,
        "keybinds": {"GrabSig": "^q"},
        "windows": {"EVE - A": True},
    }

    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": ["Ctrl+Q"], "latent": []}

    api._state.settings["eve_bookmarks"]["enabled"] = False
    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": [], "latent": ["Ctrl+Q"]}

    api._state.settings["eve_bookmarks"]["enabled"] = True
    api._state.settings["eve_bookmarks"]["windows"] = {"EVE - A": False}
    chords = api.get_preview_hotkey_state()["bookmark_chords"]
    assert chords == {"active": [], "latent": ["Ctrl+Q"]}


def test_preview_chords_are_active_only_when_windows_actually_holds_them(tmp_path):
    """C6's half of the collision, and deliberately NOT inferred the way
    _bookmark_chords infers its own. A preview chord is a RegisterHotKey, so
    the host can say whether Windows granted it -- and a chord Windows
    REFUSED takes nothing, so telling the Bookmarks screen that a preview
    keybind has stolen that bind would be a false accusation about a bind
    that is broken for an entirely different reason.

    Three outcomes: registered -> active; host not holding chords -> latent;
    running-but-refused (or not yet reported) -> neither, because both
    sentences the page could say would be untrue.
    """
    fake_host = _FakeHost()
    api = make_api(tmp_path, preview_host=fake_host)
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {"Alice": "Ctrl+Alt+1"},
            "cycle_next": "Ctrl+Alt+Right",
            "cycle_prev": "",
        }
    }
    # get_bookmarks reads its own section too; this test is about the
    # preview half of the payload, so the bookmark half is minimal.
    api._state.settings["eve_bookmarks"] = {
        "enabled": False,
        "keybinds": {},
        "windows": {},
    }

    fake_host.is_running = True
    fake_host.status = {"Ctrl+Alt+1": True, "Ctrl+Alt+Right": True}
    assert api.get_bookmarks()["preview_chords"] == {
        "active": ["Ctrl+Alt+1", "Ctrl+Alt+Right"],
        "latent": [],
    }

    # Windows refused one of them: it holds nothing, so it takes nothing.
    fake_host.status = {"Ctrl+Alt+1": False, "Ctrl+Alt+Right": True}
    assert api.get_bookmarks()["preview_chords"] == {
        "active": ["Ctrl+Alt+Right"],
        "latent": [],
    }

    # Host stopped: every configured chord is latent, because turning
    # previews back on WOULD take them.
    fake_host.is_running = False
    assert api.get_bookmarks()["preview_chords"] == {
        "active": [],
        "latent": ["Ctrl+Alt+1", "Ctrl+Alt+Right"],
    }

    # No host at all reports the same shape as a stopped one.
    bare = make_api(tmp_path)
    bare._state.settings["eve_bookmarks"] = {
        "enabled": False,
        "keybinds": {},
        "windows": {},
    }
    assert bare.get_bookmarks()["preview_chords"] == {"active": [], "latent": []}


def test_bookmark_chords_are_rendered_in_gesture_display_form(tmp_path):
    """The two features store different notation on purpose, so the clash
    check needs a common form or it silently never matches."""
    fake_host = _FakeHost()
    api = make_api(tmp_path, preview_host=fake_host)
    api._state.settings["eve_bookmarks"] = {
        "enabled": True,
        "windows": {"EVE - A": True},
        "keybinds": {"GrabSig": "^+s", "FinH": "^y"},
    }

    assert api.get_preview_hotkey_state()["bookmark_chords"]["active"] == [
        "Ctrl+Shift+S",
        "Ctrl+Y",
    ]
