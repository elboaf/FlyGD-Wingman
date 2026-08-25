"""Headless doubles for the bridge tests.

The Api reaches the page through exactly one call -- window.evaluate_js --
so a window that records that call is a complete stand-in for WebView2.
That is what lets these tests run on ubuntu-latest with no webview, no
display, and no Tk.
"""

import sys
import types
from pathlib import Path

from obs_youtube_uploader import library, uploader
from obs_youtube_uploader.ui import api as api_mod


class FakeWindow:
    """Records every script the bridge evaluates in the page."""

    def __init__(self):
        self.calls = []
        self.dialogs = []
        self.dialog_result = None

    def evaluate_js(self, script):
        self.calls.append(script)

    def create_file_dialog(self, dialog_type, directory=""):
        self.dialogs.append((dialog_type, directory))
        return self.dialog_result


class FakeRows:
    """ui.rows.RowSnapshot's methods, backed by a dict."""

    def __init__(self, mapping=None):
        self.infos = dict(mapping or {})
        self.links = {}

    def resolve(self, row_id):
        return self.infos.get(row_id)

    def resolve_many(self, ids):
        return [self.infos[i] for i in ids if i in self.infos]

    def set_link(self, row_id, video_id):
        self.links[row_id] = video_id

    def set_duration(self, row_id, duration, definitive):
        info = self.infos.get(row_id)
        if info is None:
            return
        info.duration = duration
        info.probed = True

    def rows(self):
        return [{"id": rid} for rid in self.infos]

    def rebuild(self, directory, preselect=None):
        return self.rows()


class FakeWatcher:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.rebound = []
        self.forgotten = []

    def rebind(self, directory):
        self.rebound.append(Path(directory))
        self.directory = Path(directory)

    def forget(self, path):
        self.forgotten.append(Path(path))


class FakeYouTube:
    """youtube.videos().insert(...) without a network or a discovery doc."""

    def __init__(self):
        self.bodies = []

    def videos(self):
        return self

    def insert(self, part=None, body=None, media_body=None):
        self.bodies.append(body)
        return types.SimpleNamespace(body=body, media=media_body)


class Answers:
    """Stands in for _confirm, which normally blocks on the page."""

    def __init__(self, answer=True):
        self.answer = answer
        self.asked = []

    def __call__(self, title, body):
        self.asked.append((title, body))
        return self.answer


class Alerts:
    """Stands in for _alert."""

    def __init__(self):
        self.raised = []

    def __call__(self, kind, title, body):
        self.raised.append((kind, title, body))

    def titles(self):
        return [t for _, t, _ in self.raised]


def info(path, size=1000, duration=60.0, mtime=1000.0, probed=True):
    return library.VideoInfo(
        path=Path(path), mtime=mtime, size=size, duration=duration, probed=probed
    )


def build_api(tmp_path, rows=None, settings=None, watcher=None):
    """Construct an Api the way ui.window.create() does: state in, window after."""
    cfg = {
        "privacy": "unlisted",
        "category": "20",
        "notify_mode": "toast",
        "recording_dir": str(tmp_path),
        "discord_webhook": "",
        "gamelogs_dir": None,
        "channel_id": "",
        "channel_title": "",
    }
    cfg.update(settings or {})
    state = api_mod.AppState(
        recording_dir=Path(tmp_path),
        settings=cfg,
        ffmpeg_bin="/usr/bin/ffmpeg",
        ffprobe_bin=None,
    )
    window = FakeWindow()
    api = api_mod.Api(state, rows=rows if rows is not None else FakeRows())
    api._window = window
    api._watcher = watcher
    return api, window


def record_pushes(api):
    """Record every semantic push AND let the real one run.

    Wrapping rather than replacing keeps the real _push in the path, so a
    payload that cannot be serialised still fails the test, while the
    assertions stay independent of the wire format.
    """
    sent = []
    real = api._push

    def spy(handler, payload):
        sent.append((handler, payload))
        real(handler, payload)

    api._push = spy
    return sent


def payloads(sent, handler):
    return [p for h, p in sent if h == handler]


def stub_auth(monkeypatch):
    """Credentials that are already valid, saved nowhere."""
    creds = types.SimpleNamespace(valid=True)
    monkeypatch.setattr(uploader, "load_credentials", lambda p: creds)
    monkeypatch.setattr(uploader, "needs_reauth", lambda c: False)
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)
    return creds


def install_google(monkeypatch, insert):
    """Fake googleapiclient modules for the worker's function-level imports."""

    class MediaFileUpload:
        def __init__(self, path, chunksize=None, resumable=False):
            self.path = path
            self.closed = False

        def stream(self):
            outer = self

            def close():
                outer.closed = True

            return types.SimpleNamespace(close=close)

    pkg = types.ModuleType("googleapiclient")
    disc = types.ModuleType("googleapiclient.discovery")
    http = types.ModuleType("googleapiclient.http")
    disc.build = lambda *a, **k: insert
    http.MediaFileUpload = MediaFileUpload
    monkeypatch.setitem(sys.modules, "googleapiclient", pkg)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", disc)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http)
    return MediaFileUpload
