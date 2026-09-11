"""Synthetic deployed-v1 HTTP -> retained owners -> real host/window label path.

HTTP, Win32 and encryption are external seams; a separate Windows test uses
real DPAPI. The URL stays HTTPS: loopback HTTP is injected below validation.
Events/condition re-parking order races; real timeouts only bound failed tests.
"""

import base64
import http.client
import importlib.util
import json
import queue
import shutil
import socket
import sys
import threading
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from PIL import ImageFont

from tests.test_preview_thumbnail import FakeDwm
from tests.test_wanderer_worker import Clock, ObservedCondition
from wingman import paths, settings
from wingman.preview import chrome, geometry, host, window
from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot
from wingman.ui.copy import wanderer_status
from wingman.wanderer.client import WandererClient
from wingman.wanderer.controller import WandererController, WandererPorts
from wingman.wanderer.credentials import CredentialStore
from wingman.wanderer.worker import WandererWorker

# Synthetic serializer reproduction; provenance names Wanderer 2ddff245, not HEAD.
BODY = (Path(__file__).parent / "fixtures/wanderer/deployed-v1.json").read_bytes()
BASE = "https://wanderer.example/deployment"
MAP = "Map-Slug"
TOKEN = "synthetic-integration-token"
ETAG = 'W/"fixture-revision"'


def renamed_body(name):
    data = json.loads(BODY)
    data["data"][0]["display_name"] = name
    data["revision"] = "renamed-revision"
    return json.dumps(data).encode()


def pilot(name="First Pilot", hwnd=101, pid=201, serial=1):
    return RosterClient(
        hwnd, pid, "EVE - " + name, name, ClientSessionId(hwnd, pid, name, serial)
    )


class Exchange:
    def __init__(self, handler):
        self.path, self.headers = handler.path, dict(handler.headers)
        self.ready = threading.Event()
        self.headers_sent = threading.Event()
        self.body_ready = threading.Event()
        self.status, self.body, self.etag = 200, BODY, ETAG

    def reply(self, status=200, body=BODY, *, etag=ETAG, block_body=False):
        self.status, self.body, self.etag = status, body, etag
        self.ready.set()
        if not block_body:
            self.body_ready.set()


class SnapshotServer:
    """One synthetic server boundary, with an observable blocked response body."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        self.requests = queue.Queue()
        self.exchanges = []
        self.closed = threading.Event()
        self.connections = []
        boundary = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                exchange = Exchange(self)
                boundary.exchanges.append(exchange)
                boundary.requests.put(exchange)
                assert exchange.ready.wait(5), "test never supplied HTTP response"
                self.send_response(exchange.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Wanderer-Locations-Version", "1")
                self.send_header("ETag", exchange.etag)
                self.send_header("Content-Length", str(len(exchange.body)))
                self.end_headers()
                self.wfile.flush()
                exchange.headers_sent.set()
                assert exchange.body_ready.wait(5), "test never released HTTP body"
                with suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(exchange.body)

            def log_message(self, *_args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.owner = threading.Thread(target=self._run, daemon=True)
        self.owner.start()

    def _run(self):
        while not self.closed.is_set():
            self.server.handle_request()

    def connection(self, hostname, port, timeout):
        self.connections.append((hostname, port, timeout))
        return http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=timeout
        )

    def call(self):
        return self.requests.get(timeout=3)

    def release(self):
        for exchange in self.exchanges:
            exchange.ready.set()
            exchange.body_ready.set()

    def close(self):
        self.closed.set()
        self.release()
        # Wake accept without polling, sleeps, or a second request owner.
        with socket.create_connection(self.server.server_address, timeout=2):
            pass
        self.owner.join(3)
        self.server.server_close()
        assert not self.owner.is_alive()


class Runtime:
    def __init__(self, monkeypatch, credentials, *, previews=True, entries=None):
        self.server = SnapshotServer()
        self.clock, self.cv = Clock(), ObservedCondition()
        self.messages = queue.Queue()
        self.destroyed, self.painted, self.delivered = [], [], []
        self.native = SimpleNamespace(
            dwmapi=FakeDwm(),
            kernel32=SimpleNamespace(GetModuleHandleW=lambda _: 1),
            user32=SimpleNamespace(
                PostMessageW=lambda hwnd, msg, wp, lp: self.messages.put(msg) or 1,
                GetForegroundWindow=lambda: 0,
                GetClientRect=lambda *args: 0,
                CreateWindowExW=lambda *args: 5000 + len(self.painted),
                DestroyWindow=lambda hwnd: self.destroyed.append(hwnd),
                ShowWindow=lambda *args: 1,
                PostQuitMessage=lambda _: None,
            ),
        )
        monkeypatch.setattr(host.win32, "bind", lambda: self.native)
        monkeypatch.setattr(
            window.layered,
            "push",
            lambda libs, hwnd, image, *args: self.painted.append((hwnd, image)),
        )
        self.host = host.PreviewHost(on_layout_changed=lambda *args: None)
        self.host._hwnd = 999
        monkeypatch.setattr(
            self.host, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080)
        )
        monkeypatch.setattr(
            self.host, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)]
        )
        self.created = []

        def create(libs, source, rect, **kwargs):
            preview = window.PreviewWindow(self.native, source, rect, **kwargs)
            preview.hwnd = 1000 + len(self.created)
            self.created.append(preview)
            preview._ensure_label_overlay()
            return preview

        monkeypatch.setattr(host.PreviewWindow, "create", create)
        self.roster(1, *(entries if entries is not None else (pilot(),)))
        self.cfg = settings.load()
        self.credentials = credentials

        def worker_factory(client, publish):
            self.worker = WandererWorker(
                client, publish, clock=self.clock, condition=self.cv
            )
            return self.worker

        self.controller = WandererController(
            self.cfg["wanderer"],
            ports=WandererPorts(
                update_settings=lambda: settings.update(self.cfg),
                set_metadata_callback=self.host.set_metadata_callback,
                set_metadata_generation=self.host.set_metadata_generation,
                submit_metadata=self.host.submit_metadata,
                close_metadata_admission=self.host.close_metadata_admission,
                publish_state=self.delivered.append,
                describe_status=wanderer_status,
            ),
            previews_enabled=previews,
            credentials=credentials,
            client=WandererClient(
                connection_factory=self.server.connection, clock=self.clock
            ),
            worker_factory=worker_factory,
        )
        assert self.controller.start()

    def roster(self, generation, *entries):
        self.host.apply_roster(RosterSnapshot(generation, entries))
        self.host._apply_pending_roster(None)

    def wait(self, predicate):
        with self.cv:
            assert self.cv.wait_for(lambda: predicate(self.controller.state()), 3), (
                self.controller.state()
            )
        return self.controller.state()

    def advance(self, now):
        with self.cv:
            before = self.cv.counts()
            self.clock.now = now
            self.cv.notify_all()
        self.cv.reparks(before, ("wanderer-expiry",))

    def labels(self, expected):
        def actual():
            return {name: win._system_name for name, win in self.host._windows.items()}

        while actual() != expected:
            try:
                message = self.messages.get(timeout=3)
            except queue.Empty:
                pytest.fail(f"Expected labels {expected!r}, got {actual()!r}")
            if message == host.win32.WM_APP_METADATA:
                self.host._host_proc(self.host._hwnd, message, 0, 0)
        for name, text in expected.items():
            preview = self.host._windows[name]
            assert preview._label_key[:2] == (name, text)
            assert preview._label_img.height == (47 if text else 31)
        return actual()

    def snapshot(self):
        exchange = self.server.call()
        exchange.reply()
        self.wait(lambda s: s["status"] == "connected" and not s["in_flight"])
        return exchange

    def close(self):
        self.controller.close_admission()
        self.server.release()
        assert self.controller.stop(3)
        self.server.close()


@pytest.fixture
def make_runtime(monkeypatch):
    cipher = Fernet(Fernet.generate_key())
    credentials = CredentialStore(protect=cipher.encrypt, unprotect=cipher.decrypt)
    credentials.replace(BASE, MAP, TOKEN)
    cfg = settings.load()
    cfg["wanderer"] = {"enabled": True, "base_url": BASE, "map_identifier": MAP}
    settings.save(cfg)
    runtimes = []

    def make(**kwargs):
        reloaded_store = CredentialStore(
            protect=cipher.encrypt, unprotect=cipher.decrypt
        )
        runtime = Runtime(monkeypatch, reloaded_store, **kwargs)
        runtimes.append(runtime)
        return runtime

    yield make
    for runtime in reversed(runtimes):
        if not runtime.server.closed.is_set():
            runtime.close()


def test_complete_http_snapshot_renders_only_current_preview_names(
    make_runtime, caplog
):
    names = [
        "First Pilot",
        "Hidden Pilot",
        "Unmapped Pilot",
        "Offline Pilot",
        "Unavailable Pilot",
        "Untracked Pilot",
    ]
    r = make_runtime(
        entries=tuple(pilot(n, 101 + i, 201 + i) for i, n in enumerate(names))
    )
    exchange = r.snapshot()
    r.labels(dict(zip(names, ["HOME", "Amarr", None, None, None, None], strict=True)))
    assert exchange.path == "/deployment/api/maps/Map-Slug/tracked-character-locations"
    assert exchange.headers["Authorization"] == "Bearer " + TOKEN
    assert exchange.headers["X-Wanderer-Locations-Version"] == "1"
    assert "If-None-Match" not in exchange.headers
    assert r.server.connections == [("wanderer.example", 443, 5.0)]
    state = r.controller.state()
    assert (
        state["previewed"],
        state["matched"],
        state["available"],
        state["stale"],
    ) == (6, 5, 2, 0)
    safe_output = (
        json.dumps([state, r.delivered])
        + caplog.text
        + paths.settings_file().read_text()
    )
    assert TOKEN not in safe_output
    assert "First Pilot" not in json.dumps(state)
    assert r.painted  # Real Pillow label images reached the native paint boundary.


def test_304_does_not_extend_expiry_while_next_http_request_is_blocked(make_runtime):
    r = make_runtime()
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    r.advance(102)
    unchanged = r.server.call()
    assert unchanged.headers["If-None-Match"] == ETAG
    unchanged.reply(304, b"")
    r.wait(lambda s: s["last_success_monotonic"] == 102 and not s["in_flight"])
    # Start this request late enough that its independent 10-second body budget
    # cannot expire alongside the location; only freshness should fire at 114.
    r.advance(110)
    blocked = r.server.call()
    blocked.reply(block_body=True)
    assert blocked.headers_sent.wait(2)
    r.advance(113.999)
    assert r.controller.state()["available"] == 1
    r.advance(114)  # Receipt 100 + (15 - server age 1), NOT 304 receipt + 14.
    r.labels({"First Pilot": None})
    state = r.wait(lambda s: s["stale"] == 1 and s["available"] == 0)
    assert state["in_flight"] and not blocked.body_ready.is_set()
    assert state["last_success_monotonic"] == 102


def test_auth_headers_clear_labels_before_blocked_error_body_finishes(make_runtime):
    r = make_runtime()
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    r.advance(102)
    denied = r.server.call()
    denied.reply(
        401, b'{"error":"synthetic detail","code":"invalid_token"}', block_body=True
    )
    assert denied.headers_sent.wait(2)
    r.wait(lambda s: s["paused"] and s["error_code"] == "invalid_token")
    r.labels({"First Pilot": None})
    assert r.clock() == 102 and r.controller.state()["in_flight"]
    assert not denied.body_ready.is_set()
    denied.body_ready.set()
    r.wait(lambda s: not s["in_flight"])
    r.advance(120)
    assert r.controller.state()["next_request_monotonic"] is None
    assert len(r.server.connections) == 2


def test_binding_replacement_fences_in_flight_response_and_serializes_test(
    make_runtime,
):
    r = make_runtime()
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    r.advance(102)
    old = r.server.call()
    worker = r.worker
    owner = worker._request_thread
    result = r.controller.test_connection(BASE, "Other-Map", "new-synthetic-token")
    assert result["persisted"] and result["test_accepted"]
    r.labels({"First Pilot": None})
    assert r.credentials.load(BASE, "Other-Map") == "new-synthetic-token"
    assert r.controller.state()["test_pending"]
    assert len(r.server.connections) == 2
    old.reply(body=renamed_body("OLD MAP"), etag='W/"renamed-revision"')
    state = r.wait(lambda s: not s["in_flight"])
    assert state["matched"] == state["available"] == 0
    r.labels({"First Pilot": None})
    r.advance(104)
    current = r.server.call()
    assert current.path == "/deployment/api/maps/Other-Map/tracked-character-locations"
    assert current.headers["Authorization"] == "Bearer new-synthetic-token"
    assert "If-None-Match" not in current.headers
    current.reply(body=renamed_body("NEW MAP"), etag='W/"renamed-revision"')
    r.wait(lambda s: s["test_result"] == "success")
    r.labels({"First Pilot": "NEW MAP"})
    assert r.worker is worker and worker._request_thread is owner


def test_session_replacement_and_logout_clear_at_discovery_admission(make_runtime):
    r = make_runtime()
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    old = r.host._windows["First Pilot"]
    rect = old.rect
    r.advance(102)
    blocked = r.server.call()
    replacement = pilot(pid=202, serial=2)
    with r.controller._handoff_lock:
        r.host.apply_roster(RosterSnapshot(2, (replacement,)))
        assert not r.host.metadata_sessions()
        r.labels({"First Pilot": None})  # Clear before native roster reconciliation.
        r.host._apply_pending_roster(None)
        current = r.host._windows["First Pilot"]
        assert current is not old and old.hwnd is None
        assert r.host.metadata_sessions() == frozenset({replacement.session})
        assert current.client.pid == 202 and current.rect == rect
        assert pilot().session not in r.host._metadata_values
    r.wait(lambda s: s["previewed"] == 1)
    # A fresh retained snapshot may legitimately match the new same-name session.
    r.labels({"First Pilot": "HOME"})
    r.host.apply_roster(RosterSnapshot(3, ()))
    r.labels({"First Pilot": None})
    r.host._apply_pending_roster(None)
    r.wait(lambda s: s["previewed"] == 0)
    blocked.reply(body=renamed_body("LATE ARRIVAL"), etag='W/"renamed-revision"')
    r.wait(lambda s: not s["in_flight"])
    assert r.host._windows == {} and r.host._metadata_values == {}
    assert 101 not in r.destroyed  # Only Wingman's natives, never the EVE source.


def test_off_test_and_preview_master_gate_keep_settings_and_one_worker(make_runtime):
    cfg = settings.load()
    cfg["wanderer"]["enabled"] = False
    settings.save(cfg)
    saved = paths.settings_file().read_bytes()
    r = make_runtime(previews=False)
    assert r.worker._request_thread is None and not r.server.connections
    assert r.controller.test_connection(BASE, MAP, "")["test_accepted"]
    r.snapshot()
    r.wait(lambda s: s["test_result"] == "success")
    r.labels({"First Pilot": None})
    assert paths.settings_file().read_bytes() == saved
    assert not r.controller.state()["enabled"]
    owner = r.worker._request_thread
    assert r.controller.set_enabled(True)["persisted"]
    assert not r.controller.state()["automatic_ready"]
    r.controller.set_previews_enabled(True)
    r.advance(102)
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    assert r.controller.set_enabled(False)["persisted"]
    r.labels({"First Pilot": None})
    assert r.credentials.load(BASE, MAP) == TOKEN
    assert r.worker._request_thread is owner


def test_committed_configuration_and_bound_credential_reload_then_remove(make_runtime):
    r = make_runtime()
    r.snapshot()
    assert r.controller.test_connection(
        "https://WANDERER.example:443/deployment/", MAP, ""
    )["persisted"]
    r.close()
    restarted = make_runtime()
    restarted.snapshot()
    restarted.labels({"First Pilot": "HOME"})
    assert restarted.cfg["wanderer"] == {
        "enabled": True,
        "base_url": BASE,
        "map_identifier": MAP,
    }
    assert restarted.controller.state()["credential_present"]
    assert restarted.controller.remove_connection(
        restarted.controller.state()["revision"]
    )["persisted"]
    restarted.labels({"First Pilot": None})
    assert settings.load()["wanderer"] == {
        "enabled": True,
        "base_url": "",
        "map_identifier": "",
    }
    assert not (paths.state_dir() / "wanderer_credentials.json").exists()
    restarted.close()
    without_token = make_runtime()
    assert without_token.controller.state()["status"] == "setup_incomplete"
    assert without_token.worker._request_thread is None
    assert not without_token.server.connections


def test_shutdown_fences_host_before_native_destruction_and_retains_http_owner(
    make_runtime,
):
    r = make_runtime()
    r.snapshot()
    r.labels({"First Pilot": "HOME"})
    r.advance(102)
    blocked = r.server.call()
    worker, owner = r.worker, r.worker._request_thread
    assert not r.controller.stop(0)
    assert not r.host.metadata_available()
    assert r.host._metadata_callback is None
    r.labels({"First Pilot": None})
    r.host._teardown(r.native)
    assert not r.host.metadata_sessions()
    assert owner.is_alive() and not r.controller.start()
    blocked.reply(body=renamed_body("AFTER QUIT"), etag='W/"renamed-revision"')
    assert r.controller.stop(3)
    assert r.worker is worker and worker._request_thread is owner
    assert r.controller.state()["status"] == "stopped"
    assert not r.host._metadata_values and not r.host._windows
    assert not r.controller.test_connection(BASE, MAP, TOKEN)["applied"]


@pytest.mark.skipif(
    sys.platform == "linux", reason="real Windows user-bound DPAPI required"
)
def test_real_windows_credential_document_roundtrip_replace_binding_and_remove(
    tmp_path,
):
    path = tmp_path / "wanderer_credentials.json"
    store = CredentialStore(path)  # Default protect/unprotect; no crypto seam.
    store.replace(BASE, MAP, TOKEN)
    raw = path.read_bytes()
    blob = base64.b64decode(json.loads(raw)["protected"])
    assert TOKEN.encode() not in raw + blob
    assert BASE.encode() not in raw + blob
    assert CredentialStore(path).load(BASE, MAP) == TOKEN
    assert CredentialStore(path).load(BASE, "Other-Map") is None
    store.replace(BASE, MAP, "replacement-synthetic-token")
    assert CredentialStore(path).load(BASE, MAP) == "replacement-synthetic-token"
    assert path.read_bytes() != raw
    store.remove()
    assert not path.exists() and CredentialStore(path).load(BASE, MAP) is None


def test_two_line_label_uses_existing_frozen_font_path(tmp_path, monkeypatch):
    source = (
        Path(chrome.__file__).resolve().parents[1] / "assets/fonts/Inter-Regular.ttf"
    )
    bundled = tmp_path / "assets/fonts/Inter-Regular.ttf"
    bundled.parent.mkdir(parents=True)
    shutil.copyfile(source, bundled)
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    # FONT_PATH is resolved once at import. Execute a detached real module rather
    # than reloading global chrome under other live window/renderer references.
    spec = importlib.util.spec_from_file_location(
        "wingman.preview._font_check", chrome.__file__
    )
    frozen_chrome = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen_chrome)
    assert bundled == frozen_chrome.FONT_PATH
    font = frozen_chrome._font(14)
    assert isinstance(font, ImageFont.FreeTypeFont)
    assert Path(font.path) == bundled
    image = frozen_chrome.render_label("First Pilot", 200, secondary="HOME")
    assert image.mode == "RGBA" and image.height == 47 and image.width <= 200
