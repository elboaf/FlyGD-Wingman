"""Exercise Api composition, committed master gates and both shutdown paths."""

import json
import threading
from types import SimpleNamespace
from typing import get_args

import pytest

from tests.test_api import FakeWindow, make_api, make_state, pushes
from tests.test_preview_metadata import client
from tests.test_preview_metadata import runtime as runtime
from tests.test_startup import startup as startup
from wingman import __main__ as main_mod
from wingman import settings
from wingman.preview.host import PreviewHost
from wingman.preview.store import LayoutStore
from wingman.ui import copy as copy_mod
from wingman.ui.api import Api
from wingman.wanderer.client import ErrorCode
from wingman.wanderer.worker import WorkerStatus


def test_api_composes_nonsecret_state_and_transaction_facades(tmp_path):
    api = make_api(tmp_path)
    assert hasattr(api, "wanderer_state")
    try:
        state = api.wanderer_state()
        assert state["enabled"] is False
        assert state["credential_present"] is False
        result = api.test_wanderer_connection(
            "https://EXAMPLE.test:443/prefix/map/", ""
        )
        assert not result["applied"] and not result["test_accepted"]
        assert result["acknowledged"]["base_url"] == ""
        assert api.set_wanderer_enabled(True)["applied"]
        assert settings.load()["wanderer"]["enabled"]
        result = api.test_wanderer_connection(
            "http://unsafe.example/map", "never-return-this"
        )
        assert not result["applied"]
        assert "never-return-this" not in json.dumps(result)
        api._publish_wanderer_state(api.wanderer_state())
        assert pushes(api._window)[-1][0] == "onWandererState"
    finally:
        api.shutdown_previews()


def test_metadata_availability_not_running_or_runtime_enabled(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    store = LayoutStore(lambda: settings.update(state.settings))
    host = PreviewHost(on_layout_changed=lambda *args: None, layout_store=store)
    api = Api(state, preview_host=host, layout_store=store)
    assert hasattr(api, "_wanderer")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(PreviewHost, "is_running", property(lambda self: True))
            assert host.is_running and not host.runtime_enabled
            assert not host.metadata_available()
            assert api._wanderer.start()
            assert not api.wanderer_state()["host_available"]
            assert api._wanderer._worker.state().previewed == 0
    finally:
        api.shutdown_previews()


def test_controller_receives_only_created_named_primary_sessions(
    tmp_path, runtime, monkeypatch
):
    from wingman.preview import host as host_mod

    create = host_mod.PreviewWindow.create
    monkeypatch.setattr(
        host_mod.PreviewWindow,
        "create",
        lambda libs, c, *a, **kw: (
            None if c.character == "Failed" else create(libs, c, *a, **kw)
        ),
    )
    runtime.host._excluded = lambda: ["Excluded"]
    good = tuple(client(f"Pilot {i}", i + 100) for i in range(91))
    # Bind both owners before modelling completed native activation. Api's
    # lifecycle callback intentionally revokes standalone pre-binding authority.
    runtime.host._hwnd = None
    monkeypatch.setattr(
        runtime.host,
        "set_metadata_generation",
        PreviewHost.set_metadata_generation.__get__(runtime.host),
    )
    state = make_state(tmp_path)
    store = LayoutStore(lambda: settings.update(state.settings))
    runtime.host._layout_store = store
    api = Api(state, preview_host=runtime.host, layout_store=store)
    runtime.host._hwnd = 999
    runtime.host._eve_admitted = True
    runtime.host._metadata_ready_epoch = runtime.host._eve_epoch
    runtime.roster(
        1, *good, client("Failed", 4), client("Excluded", 5), client(None, 6)
    )
    try:
        assert api._wanderer.start()
        assert api.wanderer_state()["previewed"] == 91
        assert api._wanderer._sessions == frozenset(c.session for c in good)
        assert all(
            s.character not in {"Failed", "Excluded"} for s in api._wanderer._sessions
        )
    finally:
        api._close_eve_runtime()
        runtime.host._teardown(runtime.native)
        api.shutdown_previews()


def test_failed_preview_master_transaction_does_not_change_wanderer_gate(
    tmp_path, monkeypatch
):
    api = make_api(tmp_path)
    assert hasattr(api, "_wanderer")
    try:
        assert api.set_preview_enabled(True) is True
        assert api.wanderer_state()["previews_enabled"]

        def fail(*args):
            raise OSError("save refused")

        monkeypatch.setattr(settings, "_save_locked", fail)
        assert api.set_preview_enabled(False) is False
        assert api.wanderer_state()["previews_enabled"]
    finally:
        api.shutdown_previews()


@pytest.mark.parametrize("entrypoint", ["_close_eve_runtime", "shutdown_previews"])
def test_early_and_final_shutdown_detach_before_host_native_stop(
    tmp_path, monkeypatch, entrypoint
):
    state = make_state(tmp_path)
    store = LayoutStore(lambda: settings.update(state.settings))
    host = PreviewHost(on_layout_changed=lambda *args: None, layout_store=store)
    api = Api(state, preview_host=host, layout_store=store)
    api._window = FakeWindow()
    assert hasattr(api, "_wanderer")
    assert api._wanderer.start()
    callback = host._metadata_callback
    seen = []

    def native_stop(*args, **kwargs):
        assert host._metadata_callback is None
        assert not host.metadata_available()
        assert api.wanderer_state()["status"] == "stopped"
        seen.append("native")
        return True

    monkeypatch.setattr(host, "stop", native_stop)
    try:
        getattr(api, entrypoint)()
        callback(999, frozenset(), True, 999)
        assert not api._wanderer.start()
        assert not api.wanderer_state()["host_available"]
        api._publish_wanderer_state({"status": "connected"})
        assert not any(
            payload == {"status": "connected"} for _, payload in pushes(api._window)
        )
    finally:
        api.shutdown_previews()
    assert seen


def test_main_binds_before_preview_start_and_closes_before_window_destroy(
    startup, monkeypatch
):
    from wingman.wanderer.controller import WandererController

    started = []
    real_start = WandererController.start
    real_previews = Api.start_previews_if_enabled

    def start(controller):
        result = real_start(controller)
        started.append(controller)
        return result

    def previews(api):
        assert started == [api._wanderer]
        return real_previews(api)

    monkeypatch.setattr(WandererController, "start", start)
    monkeypatch.setattr(Api, "start_previews_if_enabled", previews)

    def during_run():
        api = startup.captured["api"]
        window = startup.captured["window"]
        original = window.destroy

        def destroy():
            assert api.wanderer_state()["status"] == "stopped"
            assert not api._wanderer.start()
            original()

        window.destroy = destroy
        startup.captured["on_quit"]()

    startup.captured["during_run"] = during_run
    main_mod.main()
    assert startup.captured["window"].destroyed == 1
    assert startup.captured["api"]._wanderer.stop(1)


def test_wanderer_joins_are_outside_api_state_locks(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    assert hasattr(api, "_wanderer")
    original = api._wanderer.stop

    def stop(timeout=1):
        acquired = threading.Event()

        def probe():
            with api._eve_runtime_lock, api._preview_mode_lock:
                acquired.set()

        owner = threading.Thread(target=probe)
        owner.start()
        assert acquired.wait(2)
        owner.join(2)
        return original(timeout)

    monkeypatch.setattr(api._wanderer, "stop", stop)
    api.shutdown_previews()


@pytest.mark.parametrize(
    "status", [*get_args(WorkerStatus), "credential_error", "persistence_error"]
)
def test_status_copy_explains_every_safe_health_state(status):
    formatter = getattr(copy_mod, "wanderer_status", None)
    assert formatter is not None
    assert formatter(status, None)
    assert "unavailable" not in formatter("off", None).lower()
    if status == "persistence_error":
        assert "restart" in formatter(status, None).lower()
        assert "saved" in formatter(status, None).lower()


def test_invalid_configuration_copy_guides_input_correction():
    message = copy_mod.wanderer_status("error", "invalid_configuration")
    assert message == "Check the Wanderer map URL and token, then test again."
    assert message != copy_mod.wanderer_status("error", "transport_error")
    assert message != copy_mod.wanderer_status("error", "service_unavailable")


@pytest.mark.parametrize(
    "status,code", [("setup_incomplete", None), ("error", "redirect_refused")]
)
def test_connection_guidance_names_the_single_map_url_field(status, code):
    message = copy_mod.wanderer_status(status, code)
    assert "map URL" in message
    assert "application URL" not in message
    if status == "setup_incomplete":
        assert "token" in message and "test" in message


@pytest.mark.parametrize("code", get_args(ErrorCode))
def test_failure_copy_never_echoes_external_errors(code):
    formatter = getattr(copy_mod, "wanderer_status", None)
    assert formatter is not None
    assert formatter("error", code)
    assert "private-exception" not in formatter("error", "private-exception")


# --- Prime identity join (#296) ---------------------------------------------


def _identity_api(tmp_path, prime_identity=None, focused_session=None):
    """An Api whose host and Wanderer runtime answer fixed identity values.

    The two collaborators are fakes because this seam's contract is the
    JOIN, not either join's halves (those have their own tests): the
    focused session from the preview host, the identity from the
    Wanderer controller.
    """
    from types import SimpleNamespace

    api = make_api(tmp_path)

    def build(section):
        return SimpleNamespace(
            state=lambda: {"status": "stopped"},
            start=lambda: True,
            set_previews_enabled=lambda enabled: None,
            stop=lambda timeout=1.0: True,
            close_admission=lambda: None,
            test_connection=lambda *a: {"applied": False},
            set_enabled=lambda enabled: {"applied": True},
            remove_connection=lambda revision: {"applied": True},
            prime_identity=prime_identity,
        )

    api._build_wanderer_controller = build
    api._wanderer = build(None)
    api._preview_host = SimpleNamespace(
        focused_session=focused_session,
    )
    return api


def test_prime_identity_joins_focused_session_to_the_wanderer_snapshot(tmp_path):
    from wingman.telemetry.model import ClientSessionId
    from wingman.wanderer.model import PrimeIdentity

    session = ClientSessionId(16, 101, "Alice", 1)
    identity = PrimeIdentity(character_id=90000001, solar_system_id=30000142)
    api = _identity_api(
        tmp_path,
        prime_identity=lambda s: identity if s == session else None,
        focused_session=lambda: session,
    )
    assert api._wanderer_prime_identity() == identity


def test_prime_identity_is_none_without_a_focused_client(tmp_path):
    from wingman.wanderer.model import PrimeIdentity

    api = _identity_api(
        tmp_path,
        prime_identity=lambda s: PrimeIdentity(character_id=1, solar_system_id=2),
        focused_session=lambda: None,
    )
    assert api._wanderer_prime_identity() is None


def test_prime_identity_is_none_when_the_map_does_not_know_the_character(tmp_path):
    from wingman.telemetry.model import ClientSessionId

    api = _identity_api(
        tmp_path,
        prime_identity=lambda s: None,
        focused_session=lambda: ClientSessionId(16, 101, "Alice", 1),
    )
    assert api._wanderer_prime_identity() is None


def test_prime_identity_survives_a_raising_focus_read(tmp_path):
    """The focus read is a native-adjacent read on a host that may be
    tearing down. A failure there must answer None, never raise out of
    the staging slice."""
    from wingman.wanderer.model import PrimeIdentity

    api = _identity_api(
        tmp_path,
        prime_identity=lambda s: PrimeIdentity(character_id=1, solar_system_id=2),
        focused_session=lambda: (_ for _ in ()).throw(RuntimeError("tearing down")),
    )
    assert api._wanderer_prime_identity() is None
    # A missing host (previews never built) is the same closed answer.
    api._preview_host = None
    assert api._wanderer_prime_identity() is None


# ---- Prime staging relay (issue #297) -------------------------------------


class RelayEngine:
    """A running engine whose prime the test controls."""

    def __init__(self, prime):
        self.prime = prime

    def status(self, enabled, now=None):
        from wingman import hotkeys

        return hotkeys.EngineStatus(
            state="running",
            sig="MYR",
            root="J1234",
            next_num="21",
            next_alpha="A",
            prime=self.prime,
        )


class StubWanderer:
    def __init__(self, identity="IDENTITY", identity_sequence=()):
        self.identity = identity
        # Pop answers front-to-back, then fall back to `identity`.
        self.identity_sequence = list(identity_sequence)
        self.staged = []
        self.fail = False

    def prime_identity(self, session):
        if self.identity_sequence:
            return self.identity_sequence.pop(0)
        return self.identity

    def stage_prime(self, prime, identity, session=None):
        if self.fail:
            raise RuntimeError("staging exploded")
        self.staged.append((prime, identity, session))
        return True

    def prime_lifecycle(self):
        return None


def prime_record(captured=None):
    import time

    from wingman.hotkeys import PrimeRecord

    return PrimeRecord(
        jcode="J123456",
        flags=("e", "f"),
        event="0f0e0d0c0b0a09080706050403020100",
        captured=time.time() if captured is None else captured,
    )


class FocusedHost:
    def __init__(self):
        # One stable sentinel: the relay now hands the focused session to
        # the staging lane, so a test that inspects it needs the SAME
        # object across calls, not a fresh one each time.
        self.session = object()

    def focused_session(self):
        return self.session


def relay_api(tmp_path, prime):
    api = make_api(tmp_path)
    api._state.engine = RelayEngine(prime)
    api._state.settings.setdefault("eve_bookmarks", {})["enabled"] = True
    stub = StubWanderer()
    api._wanderer = stub
    api._preview_host = FocusedHost()
    return api, stub


def test_push_eve_status_relays_a_fresh_prime_with_identity(tmp_path):
    from wingman.hotkeys import PrimeRecord

    api, stub = relay_api(tmp_path, prime_record())
    api._push_eve_status()
    assert len(stub.staged) == 1
    relayed, identity, session = stub.staged[0]
    assert isinstance(relayed, PrimeRecord)
    assert relayed.event == "0f0e0d0c0b0a09080706050403020100"
    assert identity == "IDENTITY"
    assert session == api._preview_host.focused_session()
    # The page push is unchanged by staging: the prime still rides onEveStatus.
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime"]["jcode"] == "J123456"


def test_push_eve_status_relays_nothing_without_a_prime(tmp_path):
    api, stub = relay_api(tmp_path, None)
    api._push_eve_status()
    assert stub.staged == []
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime"] is None
    # No prime, no lifecycle word: the dot reads grey.
    assert payload["prime_state"] is None


def test_push_eve_status_skips_a_prime_older_than_the_consume_window(tmp_path):
    api, stub = relay_api(tmp_path, prime_record(captured=0.0))
    api._push_eve_status()
    assert stub.staged == []


def test_push_eve_status_survives_raising_identity_and_staging(tmp_path):
    api, stub = relay_api(tmp_path, prime_record())
    stub.fail = True
    api._wanderer_prime_identity = lambda: (_ for _ in ()).throw(
        RuntimeError("focus read exploded")
    )
    api._push_eve_status()
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime"] is not None


# ---- Bounded no_identity retry (#349) --------------------------------------


class StoppedEngine:
    """A bookmark engine whose status is anything but running."""

    def __init__(self, state="stopped"):
        self.state = state

    def status(self, enabled, now=None):
        from wingman import hotkeys

        return hotkeys.EngineStatus(state=self.state)


def retry_api(tmp_path, *, identity_sequence, focused=object):
    """An Api whose map answers identities from a sequence, tick by tick."""
    api, _stub = relay_api(tmp_path, None)
    api._state.engine = RelayEngine(None)
    api._wanderer = StubWanderer(identity=None, identity_sequence=identity_sequence)
    api._preview_host = (
        SimpleNamespace(focused_session=lambda: focused())
        if callable(focused)
        else focused
    )
    return api, api._wanderer


def test_no_identity_parks_the_prime_with_its_client_and_retries(tmp_path):
    from wingman.telemetry.model import ClientSessionId
    from wingman.wanderer.model import PrimeIdentity

    session = ClientSessionId(16, 101, "Alice", 1)
    # Tick 1: identity is None -> parked. Tick 2: identity returns -> staged.
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None, PrimeIdentity(character_id=1, solar_system_id=2)],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()
    assert stub.staged == []
    assert api._pending_prime is not None
    assert api._pending_prime[1] == session

    # The engine's standing prime persists; the second tick stages it.
    api._push_eve_status()
    assert len(stub.staged) == 1
    assert api._pending_prime is None


def test_retry_never_fires_when_the_engine_is_not_running(tmp_path):
    from wingman.telemetry.model import ClientSessionId

    session = ClientSessionId(16, 101, "Alice", 1)
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()  # parks
    assert api._pending_prime is not None

    # Engine gone (stopped/stale/off all answer prime=None without it).
    api._state.engine = StoppedEngine("stopped")
    api._push_eve_status()
    assert stub.staged == []
    # Suspended, not silently kept: no running engine means no retry.
    assert api._pending_prime is None


def test_retry_never_stages_under_a_newly_focused_client(tmp_path):
    from wingman.telemetry.model import ClientSessionId

    alice = ClientSessionId(16, 101, "Alice", 1)
    bob = ClientSessionId(17, 102, "Bob", 1)
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: alice),
    )
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()  # Alice captures; map identity is None -> parked

    # Focus moved to Bob by the next tick. The parked prime must drop,
    # never stage under Bob's identity.
    api._preview_host = SimpleNamespace(focused_session=lambda: bob)
    stub.identity = "BOBS-IDENTITY"
    api._push_eve_status()
    assert stub.staged == []


def test_retry_requires_a_provable_focused_client(tmp_path):
    from wingman.telemetry.model import ClientSessionId

    session = ClientSessionId(16, 101, "Alice", 1)
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()  # parked

    # Focus became unprovable: nothing stages, and the park is dropped --
    # the #296 rule is a front-door gate, not a retry-eligible state.
    api._preview_host = SimpleNamespace(focused_session=lambda: None)
    stub.identity = "IDENTITY"
    api._push_eve_status()
    assert stub.staged == []
    assert api._pending_prime is None


def test_a_capture_with_no_provable_client_is_never_parked(tmp_path):
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[],
        focused=SimpleNamespace(focused_session=lambda: None),
    )
    api._preview_host = SimpleNamespace(focused_session=lambda: None)
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()
    assert stub.staged == []
    assert api._pending_prime is None


def test_a_parked_prime_past_the_consume_window_stops_retrying(tmp_path):
    import time

    from wingman.telemetry.model import ClientSessionId

    session = ClientSessionId(16, 101, "Alice", 1)
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    # A prime captured before the consume window: every relay tick,
    # including the standing re-offer, drops it instead of parking.
    api._state.engine = RelayEngine(prime_record(captured=time.time() - 60 * 16))
    api._push_eve_status()
    assert stub.staged == []
    assert api._pending_prime is None


# ---- Prime lifecycle word on the status push (#353) ------------------------


def lifecycle_api(tmp_path, prime):
    """A relay Api whose Wanderer stub answers a fixed lifecycle word."""
    from wingman.wanderer.controller import PRIME_STAGED

    api, stub = relay_api(tmp_path, prime)
    stub.lifecycle = PRIME_STAGED

    def prime_lifecycle():
        return stub.lifecycle

    stub.prime_lifecycle = prime_lifecycle
    return api, stub


def test_prime_state_rides_the_status_push_while_a_prime_stands(tmp_path):
    api, stub = lifecycle_api(tmp_path, prime_record())
    api._push_eve_status()
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime_state"] == "staged"

    stub.lifecycle = "consumed"
    api._push_eve_status()
    assert pushes(api._window)[-1][1]["prime_state"] == "consumed"


def test_prime_state_is_absent_when_the_engine_primed_nothing(tmp_path):
    """A Set Root that primes nothing must not inherit the previous
    capture's word: grey until a prime stands again."""
    api, _stub = lifecycle_api(tmp_path, prime_record())
    api._push_eve_status()
    assert pushes(api._window)[-1][1]["prime_state"] == "staged"

    api._state.engine = RelayEngine(None)
    api._push_eve_status()
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime"] is None
    assert payload["prime_state"] is None


def test_prime_state_survives_a_raising_lifecycle_read(tmp_path):
    """The readout must never cost the status push an exception -- a
    degraded lifecycle degrades to grey, never to a dead poll tick."""
    api, _stub = lifecycle_api(tmp_path, prime_record())
    api._wanderer.prime_lifecycle = lambda: (_ for _ in ()).throw(
        RuntimeError("lifecycle exploded")
    )
    api._push_eve_status()
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime"] is not None
    assert payload["prime_state"] is None


def test_prime_state_is_yellow_while_the_parked_retry_is_alive(tmp_path):
    """#353's yellow includes the #349 parked-retry window: the prime is
    captured but unconfirmed. The controller was never handed that
    prime, so the Api synthesizes the word from its own park state."""
    from wingman.telemetry.model import ClientSessionId

    session = ClientSessionId(16, 101, "Alice", 1)
    api, stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    api._state.engine = RelayEngine(prime_record())
    api._push_eve_status()  # parks
    assert api._pending_prime is not None
    handler, payload = pushes(api._window)[-1]
    assert handler == "onEveStatus"
    assert payload["prime_state"] == "staging"

    # Identity returns: the park stages, the controller owns the word.
    from wingman.wanderer.model import PrimeIdentity

    stub.identity_sequence.append(PrimeIdentity(character_id=1, solar_system_id=2))
    api._push_eve_status()
    assert api._pending_prime is None
    assert pushes(api._window)[-1][1]["prime_state"] is None  # stub answers None


def test_prime_state_greys_out_when_the_parked_capture_passes_the_window(tmp_path):
    """The park is bounded by the same 15-minute consume window as any
    capture: past it, yellow would claim a prime the server ignores."""
    import time

    from wingman.telemetry.model import ClientSessionId

    session = ClientSessionId(16, 101, "Alice", 1)
    api, _stub = retry_api(
        tmp_path,
        identity_sequence=[None],
        focused=SimpleNamespace(focused_session=lambda: session),
    )
    old = prime_record(captured=time.time() - 14 * 60)
    api._state.engine = RelayEngine(old)
    api._push_eve_status()  # parks, still inside the window: yellow
    assert pushes(api._window)[-1][1]["prime_state"] == "staging"

    api._state.engine = RelayEngine(prime_record(captured=time.time() - 16 * 60))
    api._push_eve_status()
    assert pushes(api._window)[-1][1]["prime_state"] is None
