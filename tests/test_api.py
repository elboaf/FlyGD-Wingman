"""Bridge-level tests for the js_api object.

These run headless with no webview installed: the Api never imports
pywebview, and every test drives it through a fake window that records the
JavaScript it was asked to evaluate. That is the whole reason `_window` is
assigned rather than constructed -- ui.window.create() does it in
production, and a test does it directly.
"""
import json
import threading
from pathlib import Path

import pytest

from obs_youtube_uploader import durations
from obs_youtube_uploader.ui.api import Api, AppState
from obs_youtube_uploader.ui.rows import RowSnapshot
from obs_youtube_uploader.ui.scheduler import Scheduler
from tests.test_scheduler import FakeClock


class FakeWindow:
    """Records evaluate_js calls instead of running them."""

    def __init__(self, fail=False):
        self.evaluated: list[str] = []
        self.minimized = 0
        self.hidden = 0
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

    def destroy(self):
        self.destroyed += 1


def make_state(tmp_path, **overrides):
    settings = {"privacy": "unlisted", "category": "20", "notify_mode": "toast",
                "recording_dir": str(tmp_path), "discord_webhook": "",
                "gamelogs_dir": None, "channel_id": "", "channel_title": ""}
    settings.update(overrides)
    return AppState(recording_dir=Path(tmp_path), settings=settings,
                    ffmpeg_bin="/usr/bin/ffmpeg", ffprobe_bin=None)


def make_api(tmp_path, window=None, **kwargs):
    api = Api(make_state(tmp_path), **kwargs)
    api._window = window if window is not None else FakeWindow()
    return api


def pushes(window: FakeWindow) -> list[tuple[str, object]]:
    """Decode recorded JS back into (handler, payload) pairs."""
    out = []
    for script in window.evaluated:
        handler = script.split("window.", 1)[1].split(" ", 1)[0]
        payload = json.loads(script[script.index("(", script.rindex(handler)) + 1:
                                    script.rindex(")")])
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
    make_api(tmp_path, FakeWindow(fail=True))._push("onStatus",
                                                    {"text": "x", "kind": "FG"})


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

    assert pushes(window) == [("onDialog", {
        "kind": "warning",
        "title": "Nothing selected",
        "body": "Select at least one recording.",
        "request_id": None,
    })]


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
        target=lambda: result.update(ok=api._confirm("Delete 2 files?",
                                                     "This cannot be undone.")))
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
        target=lambda: result.update(ok=api._confirm("Upload 3 videos?", "body")))
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


def rows_api(recordings, tmp_path, clock, probe, window=None):
    api = Api(make_state(recordings), rows=RowSnapshot(),
              durations_file=tmp_path / "durations.json",
              spawn=InlineThread, probe=probe, timer=clock.timer)
    api._window = window if window is not None else FakeWindow()
    return api


def test_list_rows_pushes_every_row_then_streams_durations(recordings, tmp_path):
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True), window=window)

    api.list_rows()

    # Rows go out immediately, drawn from a plain stat. The whole point of
    # the split is that the list appears before any ffprobe has run.
    handler, payload = pushes(window)[0]
    assert handler == "onRows"
    assert {row["name"] for row in payload["rows"]} == {"a.mkv", "b.mkv"}

    clock.fire()  # one drain tick

    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert len(streamed) == 2
    assert {p["duration"] for p in streamed} == {12.5}
    assert all(p["definitive"] for p in streamed)
    # KEY IS `id`, matching the row objects onRows delivered.
    assert {p["id"] for p in streamed} == {r["id"] for r in payload["rows"]}


def test_preselect_marks_the_named_paths(recordings, tmp_path):
    """The watcher's channel: finish a fight, open the window, hit Upload."""
    window = FakeWindow()
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True), window=window)

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
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]

    assert api.panel_text([], False)["summary"] == "Nothing selected"
    assert api.panel_text(ids[:1], False)["summary"].startswith("1 selected")


def test_the_title_hint_tracks_the_selection_and_the_stitch_flag(
        recordings, tmp_path):
    """Three distinct labels, because three distinct things happen.

    A batch is numbered per file, a stitch collapses to one video, and a
    single selection needs no disclosure at all. Asserted verbatim against
    format_title_hint's real strings -- this is copy, and copy is what
    regresses.
    """
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    ids = [row["id"] for row in api._rows.rows()]  # the fixture holds two

    assert api.panel_text(ids, False)["title_hint"] == (
        "Title (applies to all 2, numbered 1-2)")
    assert api.panel_text(ids, True)["title_hint"] == "Title (one stitched video)"
    assert api.panel_text(ids[:1], False)["title_hint"] == "Title"


def test_the_summary_ignores_ids_the_snapshot_does_not_know(recordings, tmp_path):
    """A stale page after a refresh must not make the summary lie."""
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    assert api.panel_text(["nonsense"], False)["summary"] == "Nothing selected"


def test_measured_durations_are_persisted_and_reused(recordings, tmp_path):
    cache_file = tmp_path / "durations.json"
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()
    clock.fire()

    assert set(durations.load(cache_file)) == {
        str(recordings / "a.mkv"), str(recordings / "b.mkv")}

    # Second Api, same cache file: nothing left to probe, so no worker and
    # no drain loop at all.
    window2 = FakeWindow()
    clock2 = FakeClock()

    def explode(path, binary):
        raise AssertionError("probed a file already in the cache")

    rows_api(recordings, tmp_path, clock2, probe=explode,
             window=window2).list_rows()

    assert [name for name, _ in pushes(window2)] == ["onRows"]
    assert clock2.timers == []


def test_an_indefinite_probe_result_is_not_cached(recordings, tmp_path):
    """library.probe's second return value, honoured end to end.

    (None, False) means ffprobe never got a verdict -- no binary, launch
    failure, timeout. The cache key is (size, mtime) and never changes
    again for a finished recording, so remembering that answer would pin
    the row to "?" forever and permanently block its combat-log upload.
    """
    clock = FakeClock()
    window = FakeWindow()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (None, False), window=window)
    api.list_rows()
    clock.fire()

    assert durations.load(tmp_path / "durations.json") == {}
    streamed = [p for name, p in pushes(window) if name == "onDuration"]
    assert [p["definitive"] for p in streamed] == [False, False]


def test_the_drain_loop_stops_once_the_worker_is_done(recordings, tmp_path):
    clock = FakeClock()
    api = rows_api(recordings, tmp_path, clock,
                   probe=lambda path, binary: (12.5, True))
    api.list_rows()

    clock.fire()

    # The worker's sentinel arrived in that same tick; leaving the loop
    # armed would burn a timer every 100ms for the life of the process.
    assert clock.timers[-1].cancelled
