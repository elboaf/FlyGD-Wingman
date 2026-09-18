"""Owned cross-repository test driver. Real Api/worker/client/storage/producers.

stdin/stdout is only test orchestration. HTTP uses an isolated trusted TLS server;
OS enumeration, browser opening and DPAPI are the explicit platform seams.
"""

import base64
import json
import os
import secrets
import socket
import ssl
import sys
import time
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, SimpleQueue

import pytest
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_der_private_key,
)

from tests.test_api import FakeWindow, make_state
from tests.test_api_fleetsharing import Timers
from tests.test_client_discovery import ALICE
from tests.test_fleet_bar import FleetWindow, _headless_fleet_window_helpers
from tests.test_fleetsharing_worker_state4 import FileStore
from tests.test_telemetry_gamelogs import (
    DAMAGE_LINE,
    OUTGOING_DAMAGE_LINE,
    _log,
)
from tests.test_telemetry_parsing import _fixture_line, _tackle_with_name
from wingman import settings
from wingman.fleetsharing import crypto
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient, _NoRedirectHandler
from wingman.fleetsharing.timing import TimingContext
from wingman.fleetsharing.worker import FleetSharingWorker, _noop_thread_factory
from wingman.telemetry.admission import _SourceAuthority
from wingman.telemetry.clients import ClientDiscovery
from wingman.telemetry.coordinator import TelemetryCoordinator
from wingman.telemetry.gamelogs import GameLogStream
from wingman.telemetry.metrics import FleetMetrics
from wingman.ui import chrome
from wingman.ui.api import Api


class CapturedWindow(FakeWindow):
    def __init__(self):
        super().__init__()
        self.messages = SimpleQueue()

    def evaluate_js(self, script):
        self.messages.put(script)

    def take(self):
        messages = []
        while True:
            try:
                messages.append(self.messages.get_nowait())
            except Empty:
                return messages


class RecordedTiming(TimingContext):
    """Record actual exchanges for diagnosing a failed gate; never alter a result."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.exchanges = []

    def _evaluate_diagnostic(self, **exchange):
        result = super()._evaluate_diagnostic(**exchange)
        self.exchanges.append({**exchange, "reason": getattr(result, "reason", None)})
        self.exchanges = self.exchanges[-64:]
        return result


def build(config, root, index, origin, ca):
    folder = root / str(index)
    folder.mkdir(exist_ok=True)
    logs = folder / "logs"
    logs.mkdir(exist_ok=True)
    key = load_der_private_key(base64.b64decode(config["key"]), None).private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    store = FileStore(folder / "sharing.json")
    initial = s.SharingState(
        identity=s.DeviceIdentity(
            base64.b64encode(b"owned test DPAPI seam").decode(),
            crypto.canonical_device_public_key_b64(crypto.public_key_spki(key)),
        ),
        relay_origin=origin,
        session_id=config["session"],
        last_revision=1,
    )
    if not store.path.exists():
        store.save(initial)
    app = make_state(folder, **settings.load())
    app.settings["fleet_bar"]["enabled"] = True
    app.settings["gamelogs_dir"] = str(logs)
    clock = time.monotonic
    context = RecordedTiming(
        clock=clock, db_continuity_token=object(), elapsed_lifetime_token=object()
    )
    tls = ssl.create_default_context(cafile=ca)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=tls),
        _NoRedirectHandler(),
    )
    worker = FleetSharingWorker(
        load_state=store.load,
        save_state=store.save,
        unwrap_private_key=lambda _: key,
        client_factory=lambda base: FleetRelayClient(base, transport=opener.open),
        sharing_enabled=lambda: app.settings["fleet_sharing"]["enabled"],
        timing_context=context,
        _thread_factory=_noop_thread_factory,
    )
    authority = _SourceAuthority()
    client = ALICE._replace(
        character=config["name"],
        title="EVE - " + config["name"],
        stable_key=config["name"],
    )
    discovery = ClientDiscovery(
        _enumerate_clients=lambda: [client],
        _thread_factory=_noop_thread_factory,
        _source_admission=authority,
    )
    stream = GameLogStream(
        _clock=clock, _thread_factory=_noop_thread_factory, _source_admission=authority
    )
    metrics = FleetMetrics(_clock=clock)

    def reset(event, timeout):
        coordinator.dispatch_once(0)
        return event.wait(0)

    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: False,
        fleet_enabled=lambda: app.settings["fleet_bar"]["enabled"],
        alerts_enabled=lambda: False,
        sharing_enabled=lambda: app.settings["fleet_sharing"]["enabled"],
        gamelogs_folder=lambda: logs,
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        _clock=clock,
        _thread_factory=_noop_thread_factory,
        _source_admission=authority,
        _wait_reset=reset,
    )
    timers = Timers()
    api = Api(
        app,
        fleet_sharing=worker,
        telemetry=coordinator,
        timer=timers,
        fleet_clock=clock,
    )
    api._window = CapturedWindow()
    api._sharing_page_ready = True  # The owned browser replaces the native WebView.
    api._fleetbar_window = FleetWindow(width=500, height=90)
    api._fleetbar_page_id = secrets.token_hex(32)
    api._fleetbar_ready = True
    api._fleetbar_resize_insets = chrome.ResizeInsets(0, 0, 0, 0)
    api._fleetbar_applied_x = api._fleetbar_applied_y = 0
    api._fleetbar_applied_outer_width = 500
    api._fleetbar_applied_outer_height = 90
    opened = []
    api._open_sharing_browser = lambda url: opened.append(url) or True
    api.fleet_sharing_watch(True)
    api._start_fleet_presentation()
    return dict(
        api=api,
        worker=worker,
        store=store,
        coordinator=coordinator,
        discovery=discovery,
        stream=stream,
        timers=timers,
        logs=logs,
        config=config,
        opened=opened,
    )


def pump(devices, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for d in devices:
            d["discovery"].scan_once()
            d["stream"].scan_once(datetime.now(UTC))
            d["coordinator"].dispatch_once(0)
            d["worker"].iterate_once()
            d["timers"].drain()
        time.sleep(0.025)


def main():
    config = json.loads(sys.stdin.readline())
    root = Path(config["root"])
    os.environ["LOCALAPPDATA"] = str(root / "local")
    devices = [
        build(c, root, i, config["origin"], config["ca"])
        for i, c in enumerate(config["devices"])
    ]
    try:
        print(
            json.dumps(
                {
                    "ready": True,
                    "page_ids": [d["api"]._fleetbar_page_id for d in devices],
                }
            ),
            flush=True,
        )
        for line in sys.stdin:
            command = json.loads(line)
            action = command["action"]
            result = None
            if action == "close":
                break
            if action == "api":
                method = command["method"]
                assert not method.startswith("_")
                result = getattr(devices[command["device"]]["api"], method)(
                    *command.get("args", [])
                )
            elif action == "combat":
                for d in devices:
                    result = d["api"].fleet_sharing_setup(
                        "combat",
                        d["api"].fleet_sharing_state()["setup_controls"]["setup"],
                    )
                    assert result["queued"], result
            elif action == "on":
                for d in devices:
                    result = d["api"].fleet_sharing_set_enabled(
                        True,
                        d["api"].fleet_sharing_state()["controls"]["participation"],
                    )
                    assert result["queued"], result
                d = devices[0]
                result = d["api"].fleet_sharing_automatic(
                    "on", d["api"].fleet_sharing_state()["setup_controls"]["automatic"]
                )
                assert result["queued"], result
            elif action == "damage":
                d = devices[0]
                stamp = datetime.now(UTC).strftime("%Y.%m.%d %H:%M:%S")
                text = OUTGOING_DAMAGE_LINE.replace(
                    "2026.08.25 11:30:00", stamp
                ).replace("299", "320")
                incoming = DAMAGE_LINE.replace("2026.08.25 11:30:00", stamp)
                _log(
                    d["logs"],
                    d["config"]["name"],
                    text
                    + incoming
                    + f"[ {stamp} ]"
                    + _tackle_with_name("Carol Vex")[1].split("]", 1)[1]
                    + "\n"
                    + f"[ {stamp} ]"
                    + _fixture_line("incoming_neut.txt", "energy neutralized")[1].split(
                        "]", 1
                    )[1]
                    + "\n",
                    stem=str(time.monotonic_ns()),
                    session=stamp,
                )
            elif action == "automatic_off":
                d = devices[0]
                result = d["api"].fleet_sharing_automatic(
                    "off", d["api"].fleet_sharing_state()["setup_controls"]["automatic"]
                )
                assert result["queued"], result
            elif action == "restart":
                for d in devices:
                    before = d["worker"]._timing_context
                    assert d["worker"].stop(timeout=2)
                    assert d["worker"].start()
                    assert d["worker"]._timing_context is before
            elif action != "pump":
                raise AssertionError(action)
            pump(devices, command.get("seconds", 3))
            print(
                json.dumps(
                    {
                        "result": result,
                        "pushes": [d["api"]._window.take() for d in devices],
                        "bars": [
                            d["api"].fleet_bar_snapshot(d["api"]._fleetbar_page_id)
                            for d in devices
                        ],
                        "timing": [
                            d["worker"]._timing_context.exchanges for d in devices
                        ],
                        "states": [d["api"].fleet_sharing_state() for d in devices],
                        "opened": [d["opened"] for d in devices],
                        "rows": [
                            [
                                asdict(row)
                                for row in d["api"]._remote_fleet.current(
                                    time.monotonic()
                                )
                            ]
                            for d in devices
                        ],
                        "local": [
                            [
                                (r.character, r.dps, r.incoming_dps)
                                for r in d["worker"]._latest.snapshot.rows
                            ]
                            if d["worker"]._latest
                            else []
                            for d in devices
                        ],
                    }
                ),
                flush=True,
            )
    finally:
        for d in devices:
            d["api"].shutdown_fleet_sharing()
            assert d["api"]._stop_fleet_presentation(timeout=2)
            d["coordinator"].stop()


if __name__ == "__main__":
    with pytest.MonkeyPatch.context() as native:
        lookup = socket.getaddrinfo
        blocked = []

        def loopback_only(host, *args, **kwargs):
            if host not in ("localhost", "127.0.0.1", "::1"):
                blocked.append(host)
                raise AssertionError("External network is forbidden in this test")
            return lookup(host, *args, **kwargs)

        native.setattr(socket, "getaddrinfo", loopback_only)
        _headless_fleet_window_helpers.__wrapped__(native)
        main()
        assert not blocked, blocked
