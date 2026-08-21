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

from obs_youtube_uploader.ui.api import Api, AppState


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
