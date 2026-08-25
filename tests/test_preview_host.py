"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""

import itertools
import logging
import sys

import pytest

from obs_youtube_uploader.preview import geometry, gestures, host, layout


def test_reconcile_reports_additions_and_removals():
    added, removed, kept = host.reconcile({"A", "B"}, {"B", "C"})
    assert set(added) == {"C"}
    assert set(removed) == {"A"}
    assert set(kept) == {"B"}


def test_reconcile_of_an_empty_desired_set_removes_everything():
    """EVE closing entirely must tear every preview down, not leave them
    showing the last frame of a dead client."""
    added, removed, kept = host.reconcile({"A", "B"}, set())
    assert set(removed) == {"A", "B"} and not added and not kept


def test_reconcile_keeps_live_previews_untouched():
    """A kept preview must not be rebuilt: re-registering its thumbnail
    every 700ms is a visible flicker."""
    added, removed, kept = host.reconcile({"A"}, {"A"})
    assert not added and not removed and set(kept) == {"A"}


def test_stop_before_start_is_a_no_op():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.stop()
    assert not h.is_running


def test_stop_is_idempotent(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(h, "_run", lambda: None)
    h.start()
    h.stop()
    h.stop()
    assert not h.is_running


def test_start_twice_does_not_spawn_two_threads(monkeypatch):
    """Enable clicked twice must not leave an orphan pump owning HWNDs
    that nothing will ever tear down.

    The fake worker blocks rather than returning immediately: a worker
    that has already exited would let an implementation which permits a
    later restart pass this by accident, making the result depend on
    thread scheduling rather than on the guard.
    """
    import threading

    started = []
    running = threading.Event()
    release = threading.Event()

    def fake_run():
        started.append(1)
        running.set()
        release.wait(5)

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(h, "_run", fake_run)
    h.start()
    running.wait(5)  # the first worker is definitely still alive
    h.start()
    release.set()
    h.stop()
    assert len(started) == 1


def test_shutdown_flushes_pending_layouts(monkeypatch):
    """Layout writes are debounced by a second. Quitting inside that window
    after a drag would otherwise discard the move -- and the plan called
    for this explicitly before anyone noticed it was missing."""
    flushed = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, flush_layouts=lambda: flushed.append(1)
    )

    class FakeUser32:
        def __getattr__(self, _name):
            return lambda *a, **k: 0

    h._teardown(type("L", (), {"user32": FakeUser32()})())
    assert flushed == [1]


def test_teardown_completes_even_if_the_flush_raises():
    """A settings file that cannot be written is not a reason to leak
    HWNDs and leave the pump running."""
    calls = []

    class FakeUser32:
        def __getattr__(self, name):
            def record(*a, **k):
                calls.append(name)
                return 0

            return record

    def boom():
        raise OSError("read-only filesystem")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, flush_layouts=boom)
    h._teardown(type("L", (), {"user32": FakeUser32()})())
    assert "PostQuitMessage" in calls


def test_a_layout_change_updates_the_in_session_cache():
    """A client that disappears and comes back mid-session is a new entry
    to the next sweep. If _saved still held only what was loaded at
    startup, the preview would be re-placed by default_stack and the
    user's dragged position would not return until a full restart."""
    from obs_youtube_uploader.preview.geometry import Rect

    sent = []
    h = host.PreviewHost(on_layout_changed=lambda *a: sent.append(a))
    h._layout_changed("Pilot", Rect(10, 20, 320, 210), False)

    assert h._saved["Pilot"].rect == Rect(10, 20, 320, 210)
    assert sent == [("Pilot", Rect(10, 20, 320, 210), False)]


def test_a_restored_lock_survives_into_the_new_window():
    """layout.Entry carries `locked`, deserialize restores it, and the
    window reports it back on the next drag. If the window started at
    False regardless, that report would erase the flag from settings."""
    from obs_youtube_uploader.preview.geometry import Rect
    from obs_youtube_uploader.preview.layout import Entry

    h = host.PreviewHost(
        on_layout_changed=lambda *a: None,
        saved_layouts={"Pilot": Entry(Rect(1, 2, 320, 210), locked=True)},
    )
    assert h._saved["Pilot"].locked is True


@pytest.mark.skipif(
    sys.platform != "win32", reason="needs a real message pump and window station"
)
def test_stop_from_another_thread_really_exits_the_pump(monkeypatch):
    """End to end, on the thread boundary that matters.

    stop() is called from the main thread while the pump runs on the
    preview thread. PostQuitMessage posts WM_QUIT to the CALLING thread's
    queue, so a teardown that ran anywhere but the preview thread would
    leave this pump running forever -- and the process unable to exit.

    Discovery is stubbed to find nothing so the test creates only the
    host's message-only window, not a preview per running EVE client.
    """
    from obs_youtube_uploader.preview import discovery

    monkeypatch.setattr(discovery, "list_clients", lambda **kw: [])

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.start()
    assert h._ready.wait(10), "preview thread never became ready"
    assert h.is_running

    thread = h._thread
    h.stop(timeout=10)
    assert not thread.is_alive(), "the pump outlived stop()"
    assert not h.is_running


class _FakeClient:
    def __init__(self, key, hwnd=0x1000, character=None):
        self.stable_key = key
        self.hwnd = hwnd
        self.character = character if character is not None else key
        self.title = f"EVE - {key}"
        self.pid = 4242


def test_the_client_registry_keeps_clients_with_no_window(monkeypatch):
    """A client whose preview could not be created is still running, and a
    chord aimed at it must still work."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(
        host.discovery,
        "list_clients",
        lambda: [_FakeClient("Alice"), _FakeClient("Bravo")],
    )
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])

    h._sweep(libs=None)

    assert h._windows == {}
    assert sorted(h._clients) == ["Alice", "Bravo"]
    assert h.characters() == ["Alice", "Bravo"]


def test_the_registry_refreshes_hwnds_for_a_kept_key(monkeypatch):
    """reconcile() compares stable keys only, so a character that reappears
    on a NEW hwnd counts as 'kept' -- a retained record would point at a
    dead window."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])

    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Alice", hwnd=0x1111)]
    )
    h._sweep(libs=None)
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Alice", hwnd=0x2222)]
    )
    h._sweep(libs=None)

    assert h._clients["Alice"].hwnd == 0x2222


def test_characters_excludes_clients_at_character_select(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(
        host.discovery,
        "list_clients",
        lambda: [_FakeClient("Alice"), _FakeClient("hwnd:0x9", character=None)],
    )
    h._sweep(libs=None)

    assert h.characters() == ["Alice"]


def test_a_changed_client_set_is_reported_once(monkeypatch):
    seen = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, on_clients_changed=seen.append
    )
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(host.discovery, "list_clients", lambda: [_FakeClient("Alice")])

    h._sweep(libs=None)
    h._sweep(libs=None)  # unchanged: must not report again

    assert seen == [["Alice"]]


def test_host_command_messages_are_distinct():
    """Two commands sharing a value would silently run the wrong handler.

    Lives here rather than in tests/test_preview_win32.py: that file's tests
    are skipped on non-Windows platforms because most of them exercise
    bind()'s DLL declarations, but these are plain module-scope integers
    that need no DLL -- and CI is ubuntu-latest only, so that skip would
    hide this assertion from every CI run.
    """
    commands = {
        host.win32.WM_APP_SHUTDOWN,
        host.win32.WM_APP_SWEEP_NOW,
        host.win32.WM_APP_REBIND,
        host.win32.WM_APP_ALERT,
        host.win32.WM_APP_RESTYLE,
    }
    assert len(commands) == 5
    assert all(c >= host.win32.WM_APP for c in commands)


def test_raise_alert_queues_without_a_window():
    """The service can raise before the pump exists: start() returns
    immediately and _hwnd is created later on the preview thread
    (host.py:139-147, :219-235). A queued alert must survive that gap
    rather than being posted into nothing."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert len(h._pending_alerts) == 1


def test_draining_returns_and_clears():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert len(h._drain_alerts()) == 1
    assert h._drain_alerts() == []


def test_raise_alert_posts_only_a_signal(monkeypatch):
    """PostMessageW carries integers only, so wparam/lparam must stay
    zero and the payload must travel in the field -- exercised through
    the real _post (not a stub standing in for it), so this actually
    proves what reaches PostMessageW rather than just that raise_alert
    delegates to whatever _post happens to be."""
    posted = []

    class _AlertUser32(_FakeUser32):
        def PostMessageW(self, hwnd, msg, wparam, lparam):
            posted.append((msg, wparam, lparam))
            return 1

    libs = _FakeLibs(_AlertUser32())
    monkeypatch.setattr(host.win32, "bind", lambda: libs)

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert posted == [(host.win32.WM_APP_ALERT, 0, 0)]


def test_plan_assigns_one_id_per_binding():
    plan = host.plan_registrations(
        {
            "characters": {"Bravo": "Ctrl+F2", "Alice": "Ctrl+F1"},
            "cycle_next": "Ctrl+Alt+Right",
            "cycle_prev": "Ctrl+Alt+Left",
        }
    )
    ids = [entry[0] for entry in plan]
    assert len(ids) == len(set(ids)) == 4
    assert all(0 < i <= 0xBFFF for i in ids)


def test_plan_is_stable_across_calls():
    """Rebinding unregisters and re-registers everything, so an unstable
    id assignment would churn registrations that did not change."""
    table = {
        "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
        "cycle_next": "",
        "cycle_prev": "",
    }
    assert host.plan_registrations(table) == host.plan_registrations(table)


def test_plan_drops_unparseable_and_empty_gestures():
    plan = host.plan_registrations(
        {
            "characters": {"Alice": "", "Bravo": "nonsense", "Carol": "Ctrl+F3"},
            "cycle_next": "",
            "cycle_prev": "",
        }
    )
    assert [entry[2] for entry in plan] == [("focus", "Carol")]


def test_plan_drops_a_duplicate_chord():
    """Windows would refuse the second registration anyway; catching it
    here keeps the reported status honest about which binding lost."""
    plan = host.plan_registrations(
        {
            "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
            "cycle_next": "",
            "cycle_prev": "",
        }
    )
    assert len(plan) == 1


def test_cycle_actions_carry_direction():
    plan = host.plan_registrations(
        {
            "characters": {},
            "cycle_next": "Ctrl+Alt+Right",
            "cycle_prev": "Ctrl+Alt+Left",
        }
    )
    actions = sorted(entry[2] for entry in plan)
    assert actions == [("cycle", -1), ("cycle", 1)]


class _FakeUser32:
    def __init__(self, refuse=(), foreground=0):
        self.registered = {}
        self.unregistered = []
        self.calls = []
        self._refuse = set(refuse)
        # Read by _apply_selection when the hook has not yet recorded a
        # foreground hwnd for this sweep (see _swept_host below).
        self._foreground = foreground

    def RegisterHotKey(self, hwnd, ident, mods, vk):
        self.calls.append(("register", ident))
        if (mods, vk) in self._refuse:
            return 0
        self.registered[ident] = (mods, vk)
        return 1

    def UnregisterHotKey(self, hwnd, ident):
        self.calls.append(("unregister", ident))
        self.unregistered.append(ident)
        self.registered.pop(ident, None)
        return 1

    def GetForegroundWindow(self):
        return self._foreground


class _FakeLibs:
    def __init__(self, user32):
        self.user32 = user32


def test_rebind_unregisters_everything_before_registering():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)

    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )
    user32.calls.clear()
    h._apply_hotkeys(
        libs, {"characters": {"Bravo": "Ctrl+F2"}, "cycle_next": "", "cycle_prev": ""}
    )

    kinds = [kind for kind, _ in user32.calls]
    assert kinds.index("unregister") < kinds.index("register")
    assert list(user32.registered.values()) == [
        (gestures.parse("Ctrl+F2").mods, gestures.parse("Ctrl+F2").vk)
    ]


def test_a_refused_chord_is_reported_and_the_others_still_register():
    refused = gestures.parse("Ctrl+F1")
    user32 = _FakeUser32(refuse={(refused.mods, refused.vk)})
    reported = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, on_hotkey_status=reported.append
    )
    h._hwnd = 0x99

    h._apply_hotkeys(
        _FakeLibs(user32),
        {
            "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
            "cycle_next": "",
            "cycle_prev": "",
        },
    )

    assert h.hotkey_status() == {"Ctrl+F1": False, "Ctrl+F2": True}
    assert reported == [{"Ctrl+F1": False, "Ctrl+F2": True}]


def test_apply_hotkeys_logs_a_one_line_registration_summary(caplog):
    """Risk 4 of the design -- whether WM_HOTKEY even reaches this window --
    is unverified on real hardware. If a chord silently never registers,
    this line (not the per-chord warning, which only fires on a refusal) is
    what tells 'nothing bound' from 'some bound, some refused'."""
    refused = gestures.parse("Ctrl+F1")
    user32 = _FakeUser32(refuse={(refused.mods, refused.vk)})
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99

    with caplog.at_level(logging.INFO):
        h._apply_hotkeys(
            _FakeLibs(user32),
            {
                "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
                "cycle_next": "",
                "cycle_prev": "",
            },
        )

    assert any(
        "1 registered" in r.message and "1 refused" in r.message for r in caplog.records
    )


def test_status_is_readable_after_a_pass_that_reported_to_nobody():
    """Previews start BEFORE the webview exists (__main__.py:406-411), so a
    conflict at launch is announced into the void. It has to be readable
    afterwards or it is lost for the session."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._apply_hotkeys(
        _FakeLibs(_FakeUser32()),
        {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""},
    )
    assert h.hotkey_status() == {"Ctrl+F1": True}


def test_teardown_releases_hotkeys_before_destroying_the_host_window():
    """Ordering the parent design's Lifecycle section requires: chords must
    be released before the window they are registered against dies."""
    order = []

    class _Tracking(_FakeUser32):
        def UnregisterHotKey(self, hwnd, ident):
            order.append("unregister-hotkey")
            return super().UnregisterHotKey(hwnd, ident)

        def UnhookWinEvent(self, hook):
            order.append("unhook")
            return 1

        def KillTimer(self, hwnd, ident):
            return 1

        def DestroyWindow(self, hwnd):
            order.append("destroy-window")
            return 1

        def PostQuitMessage(self, code):
            order.append("quit")

    user32 = _Tracking()
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._hook = 0x55
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )

    h._teardown(libs)

    assert order == ["unregister-hotkey", "unhook", "destroy-window", "quit"]


def test_teardown_clears_the_client_and_registration_reports():
    """characters() and hotkey_status() are read from any thread with no
    liveness check of their own -- ui/api.py gates on is_running instead.
    If teardown left these populated, a stopped host would keep reporting
    characters as online and chords as registered after the thread that
    owned them is gone and Windows holds none of them."""

    class _TeardownUser32(_FakeUser32):
        def __getattr__(self, name):
            # Anything _teardown calls beyond Register/UnregisterHotKey
            # (UnhookWinEvent, KillTimer, DestroyWindow, PostQuitMessage) --
            # a no-op stands in for the real Win32 call.
            return lambda *a, **k: 0

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    libs = _FakeLibs(_TeardownUser32())
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )
    assert h.characters() == ["Alice"]
    assert h.hotkey_status() == {"Ctrl+F1": True}

    h._teardown(libs)

    assert h.characters() == []
    assert h.hotkey_status() == {}


def test_teardown_clears_pending_alerts_and_selection():
    """_teardown clears _clients and _hotkey_status but had left
    _pending_alerts, _selected_key, and _foreground behind. Today
    _apply_alerts is a no-op, but the queue still grows between stop()
    and the next reconcile (ui/api.py's set_preview_enabled(False) calls
    host.stop() before alerts.reconcile()), and _apply_selection's
    `if key == self._selected_key: return` would leave a fresh window
    unselected forever across a stop/start if this were not cleared."""

    class _TeardownUser32(_FakeUser32):
        def __getattr__(self, name):
            return lambda *a, **k: 0

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    # Queued before _hwnd exists, same as test_raise_alert_queues_without_a_
    # window -- so _post's `if self._hwnd:` guard skips the real Win32 call
    # this fake libs object does not need to answer for.
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    h._hwnd = 0x99
    h._selected_key = "Alice"
    h._foreground = 0x1234
    libs = _FakeLibs(_TeardownUser32())

    h._teardown(libs)

    assert h._pending_alerts == []
    assert h._selected_key is None
    assert h._foreground == 0


def test_raise_alert_drops_oldest_beyond_the_cap():
    """The queue is drained every ~80ms in normal operation (WM_APP_ALERT
    fires _apply_alerts on the pump), so anything beyond a handful means
    nothing is draining -- previews disabled, or the host window not yet
    created. An hour of accumulated alerts must not all replay once the
    pump comes back; only the most recent ones should."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    for i in range(host.PENDING_ALERTS_MAX + 5):
        h.raise_alert(str(i), "combat", {})
    assert len(h._pending_alerts) == host.PENDING_ALERTS_MAX
    # Oldest dropped, newest kept.
    kept = [character for character, _event, _spec in h._pending_alerts]
    assert kept == [str(i) for i in range(5, host.PENDING_ALERTS_MAX + 5)]


def test_hotkey_focuses_the_named_character(monkeypatch):
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x1234]


def test_cycle_hotkey_anchors_on_the_foreground_client(monkeypatch):
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {
        "Alice": _FakeClient("Alice", hwnd=0x1111),
        "Bravo": _FakeClient("Bravo", hwnd=0x2222),
    }
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0x1111
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {}, "cycle_next": "Ctrl+Alt+Right", "cycle_prev": ""}
    )

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x2222]


def test_a_focus_chord_for_an_absent_character_does_nothing(monkeypatch):
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {}
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Ghost": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == []


def test_hotkey_dispatch_is_logged_including_silent_early_returns(monkeypatch, caplog):
    """_on_hotkey had no logging at all: an unknown id and a not-running
    target both returned silently, and a field report of 'my hotkey does
    nothing' had no dispatch line to distinguish 'never fired' from 'fired
    but the target was not running' from 'fired and worked'."""
    monkeypatch.setattr(host.window_mod, "activate", lambda libs, hwnd: True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs,
        {
            "characters": {"Alice": "Ctrl+F1", "Ghost": "Ctrl+F2"},
            "cycle_next": "",
            "cycle_prev": "",
        },
    )
    ident_by_action = {v: k for k, v in h._registered.items()}
    alice_ident = ident_by_action[("focus", "Alice")]
    ghost_ident = ident_by_action[("focus", "Ghost")]

    with caplog.at_level(logging.DEBUG):
        h._on_hotkey(libs, alice_ident)  # fires: target is running
        h._on_hotkey(libs, ghost_ident)  # silent early return: not running
        h._on_hotkey(libs, 0xDEAD)  # silent early return: unknown id

    messages = [r.message for r in caplog.records]
    assert any("Alice" in m for m in messages)
    assert any("not running" in m for m in messages)
    assert any("unknown" in m.lower() for m in messages)


def test_a_raising_status_callback_does_not_kill_the_registration_pass():
    """on_hotkey_status is outside code, called from _run() before
    SetTimer/_ready.set() on the initial pass. Unguarded, a raise here
    would unwind out of _run and kill the pump while self._hwnd stays
    set -- previews dead for the session, stop() then blocking for the
    full JOIN_TIMEOUT_S posting to a window nothing pumps for."""

    def boom(status):
        raise RuntimeError("bridge is gone")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, on_hotkey_status=boom)
    h._hwnd = 0x99
    libs = _FakeLibs(_FakeUser32())

    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )

    # The pass itself must have completed and recorded its own outcome,
    # despite the callback raising.
    assert h.hotkey_status() == {"Ctrl+F1": True}


def test_a_raising_clients_callback_does_not_kill_the_sweep(monkeypatch):
    """Identical hazard to on_hotkey_status: _sweep() runs from _run()
    before _ready.set() on the very first sweep, so a raise here would
    kill the preview thread the same way."""

    def boom(now):
        raise RuntimeError("bridge is gone")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, on_clients_changed=boom)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(host.discovery, "list_clients", lambda: [_FakeClient("Alice")])

    h._sweep(libs=None)  # must not raise

    # The sweep itself must have completed despite the callback raising.
    assert h.characters() == ["Alice"]


# --- Placement must land on a real display ----------------------------------

MONITORS = [
    geometry.Rect(3840, 291, 2560, 1440),
    geometry.Rect(-2560, 306, 2560, 1440),
    geometry.Rect(0, 0, 3840, 2160),
]
VIRTUAL = geometry.Rect(-2560, 0, 8960, 2160)


def _on_a_monitor(r):
    return any(
        not (r.right <= m.x or r.x >= m.right or r.bottom <= m.y or r.y >= m.bottom)
        for m in MONITORS
    )


def _placement_host(monkeypatch, saved=None, **kw):
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, saved_layouts=saved, size=(320, 210), **kw
    )
    monkeypatch.setattr(h, "_screen", lambda: VIRTUAL)
    return h


def test_a_defaulted_preview_lands_on_a_monitor(monkeypatch):
    """A first-time character must be placed on a display, below its top
    edge -- not in the dead zone above it, and not merely clamped flush
    against it.

    Pins the exact rect: an assertion that only checks for intersection
    passes with the nearest-monitor search inverted."""
    h = _placement_host(monkeypatch)
    assert h._resolve_rect("Guarzo Togenada", 0, MONITORS) == geometry.Rect(
        6062, 309, 320, 210
    )


def test_every_defaulted_preview_in_a_full_stack_is_fully_on_a_monitor(monkeypatch):
    """Fully on, not merely overlapping. A preview whose top is in the dead
    zone has its label band off-screen, and one clamped on top of its
    neighbour hides that neighbour -- both were real, observed on a
    three-monitor setup with staggered tops."""
    h = _placement_host(monkeypatch)
    placed = [h._resolve_rect(f"char-{i}", i, MONITORS) for i in range(6)]
    for i, r in enumerate(placed):
        host_mon = next(
            (
                m
                for m in MONITORS
                if r.x >= m.x
                and r.right <= m.right
                and r.y >= m.y
                and r.bottom <= m.bottom
            ),
            None,
        )
        assert host_mon is not None, (i, r)
    for a, b in itertools.pairwise(placed):
        assert b.y >= a.bottom, (a, b)


def test_a_saved_rect_on_a_detached_monitor_is_pulled_back(monkeypatch):
    h = _placement_host(
        monkeypatch,
        saved={"Gone": layout.Entry(geometry.Rect(-9000, 400, 320, 210), False)},
    )
    assert _on_a_monitor(h._resolve_rect("Gone", 0, MONITORS))


def test_a_saved_rect_that_is_already_visible_is_untouched(monkeypatch):
    placed = geometry.Rect(3106, 546, 320, 210)
    h = _placement_host(monkeypatch, saved={"Isiga": layout.Entry(placed, False)})
    assert h._resolve_rect("Isiga", 0, MONITORS) == placed


def test_placement_is_not_clamped_when_monitors_cannot_be_enumerated(monkeypatch):
    """An empty monitor list means "do not move anything". Clamping against
    a list that is missing a display would haul previews off it."""
    h = _placement_host(monkeypatch)
    unclamped = geometry.default_stack(0, VIRTUAL, (320, 210))
    assert h._resolve_rect("Nobody", 0, []) == unclamped


def test_the_sweep_places_a_new_preview_at_its_clamped_rect(monkeypatch):
    """Ties the two halves together. Without this, host.py could revert to
    the old unclamped expression and every other test here would pass."""
    seen = []

    class _Win:
        rect = geometry.Rect(0, 0, 0, 0)

        def close(self):
            pass

    def fake_create(cls, libs, client, rect, **kw):
        seen.append(rect)
        return _Win()

    h = host.PreviewHost(on_layout_changed=lambda *a: None, size=(320, 210))
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Guarzo Togenada")]
    )
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))
    monkeypatch.setattr(h, "_screen", lambda: VIRTUAL)
    monkeypatch.setattr(h, "_monitors", lambda: MONITORS)

    h._sweep(libs=None)

    assert seen == [geometry.Rect(6062, 309, 320, 210)]


def test_the_sweep_enumerates_monitors_once_for_a_whole_batch(monkeypatch):
    """One EnumDisplayMonitors per sweep, not per added preview -- and, when
    it fails, one log line rather than one per client."""
    calls = []

    def fake_create(cls, libs, client, rect, **kw):
        return None

    h = host.PreviewHost(on_layout_changed=lambda *a: None, size=(320, 210))
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.discovery,
        "list_clients",
        lambda: [_FakeClient("A"), _FakeClient("B"), _FakeClient("C")],
    )
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))
    monkeypatch.setattr(h, "_screen", lambda: VIRTUAL)
    monkeypatch.setattr(h, "_monitors", lambda: calls.append(1) or MONITORS)

    h._sweep(libs=None)

    assert len(calls) == 1


# --- restore_preview_positions gates the saved rect -------------------------


def test_a_saved_rect_is_ignored_when_restoring_is_off(monkeypatch):
    """Off means the preview opens where a first-time character's would --
    and not only at launch, but every time the client appears."""
    placed = geometry.Rect(3106, 546, 320, 210)
    h = _placement_host(
        monkeypatch,
        saved={"Isiga": layout.Entry(placed, False)},
        restore_positions=lambda: False,
    )
    assert h._resolve_rect("Isiga", 0, MONITORS) == h._resolve_rect(
        "never-seen", 0, MONITORS
    )


def test_the_off_path_is_clamped_to_a_monitor_too(monkeypatch):
    """The clamp must apply on BOTH paths. Branching early and returning
    the raw default would put the preview back in the dead zone above a
    staggered monitor -- the bug #30 fixed."""
    h = _placement_host(
        monkeypatch,
        saved={"Gone": layout.Entry(geometry.Rect(-9000, 400, 320, 210), False)},
        restore_positions=lambda: False,
    )
    assert h._resolve_rect("Gone", 0, MONITORS) == geometry.Rect(6062, 309, 320, 210)


def test_the_saved_path_is_still_clamped_when_restoring_is_on(monkeypatch):
    h = _placement_host(
        monkeypatch,
        saved={"Gone": layout.Entry(geometry.Rect(-9000, 400, 320, 210), False)},
        restore_positions=lambda: True,
    )
    assert _on_a_monitor(h._resolve_rect("Gone", 0, MONITORS))


def test_the_setting_is_read_per_placement_not_captured(monkeypatch):
    """A preview is created whenever its client appears, usually mid-
    session. Reading the setting once at construction would apply the
    value the app started with for the rest of the run."""
    wanted = [False]
    placed = geometry.Rect(3106, 546, 320, 210)
    h = _placement_host(
        monkeypatch,
        saved={"Isiga": layout.Entry(placed, False)},
        restore_positions=lambda: wanted[0],
    )
    assert h._resolve_rect("Isiga", 0, MONITORS) != placed
    wanted[0] = True
    assert h._resolve_rect("Isiga", 0, MONITORS) == placed


def test_an_unreadable_setting_restores_rather_than_discards(monkeypatch):
    """Placement runs on the preview thread inside the sweep. A raising
    callable must not take the sweep down, and the safe direction is the
    behaviour that predates the toggle."""
    placed = geometry.Rect(3106, 546, 320, 210)

    def boom():
        raise RuntimeError("settings vanished")

    h = _placement_host(
        monkeypatch,
        saved={"Isiga": layout.Entry(placed, False)},
        restore_positions=boom,
    )
    assert h._resolve_rect("Isiga", 0, MONITORS) == placed


def test_positions_are_recorded_even_while_restoring_is_off():
    """Switching back on must restore what the user last had rather than
    nothing, so a drag is persisted whatever the setting says."""
    recorded = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: recorded.append(a), restore_positions=lambda: False
    )
    rect = geometry.Rect(10, 20, 320, 210)
    h._layout_changed("Isiga", rect, False)
    assert recorded == [("Isiga", rect, False)]
    assert h._saved["Isiga"].rect == rect


# --- selection follows the real foreground window ---------------------------


def _swept_host(monkeypatch, keys, foreground):
    """A host swept once, with *keys* as the running clients and
    *foreground* as the real foreground hwnd -- following the _sweep fake
    set used throughout this file. Each client gets its own hwnd
    (0x1000, 0x2000, ...) so *foreground* can select any one of them.
    """
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(
        host.discovery,
        "list_clients",
        lambda: [_FakeClient(key, hwnd=0x1000 * (i + 1)) for i, key in enumerate(keys)],
    )
    libs = _FakeLibs(_FakeUser32(foreground=foreground))
    h._sweep(libs)
    return h


def test_the_foreground_client_becomes_the_selected_preview(monkeypatch):
    h = _swept_host(monkeypatch, ["Alice", "Bravo"], foreground=0x1000)
    assert h._selected_key == "Alice"


def test_a_foreground_window_that_is_not_a_client_selects_nothing(monkeypatch):
    """Deliberately not "the last EVE client used". A sticky highlight
    could not be told apart from an alert on that same client, and
    acknowledgement would clear alerts the user never saw."""
    h = _swept_host(monkeypatch, ["Alice"], foreground=0xDEAD)
    assert h._selected_key is None


def test_a_stale_selection_clears_once_the_client_loses_the_foreground(monkeypatch):
    """The from-cold case above cannot tell "correctly clears" from "never
    had anything to clear": a buggy _apply_selection that only assigns
    self._selected_key when a client IS found -- i.e. never clears it, the
    sticky behaviour rejected above -- would also leave _selected_key at its
    initial None and pass that test. This one actually exercises the clear:
    select Alice, then move the real foreground off any client, and check
    the selection follows it back to None.

    This matters beyond cosmetics: a later task clears a persistent alert
    when its client becomes selected. Sticky selection would mean the
    client you last used stays "selected" while you are in a browser, and
    its alert would clear itself without you ever seeing it.
    """
    h = _swept_host(monkeypatch, ["Alice"], foreground=0x1000)
    assert h._selected_key == "Alice"
    h._sweep(_FakeLibs(_FakeUser32(foreground=0xDEAD)))
    assert h._selected_key is None


def test_a_preview_created_on_retry_is_marked_selected(monkeypatch):
    """A preview whose window failed to create on one sweep and succeeded
    on a later one, while its client stayed foreground the whole time,
    hits _apply_selection's `key == self._selected_key` early return on
    the second sweep -- the key never changed, only whether a window
    existed for it. Without applying the selected state there too, the
    foreground client would show no ring until the user tabbed away and
    back."""

    class _FakeWindow:
        def __init__(self):
            self.selected = False

        def set_selected(self, selected):
            self.selected = selected

        def close(self):
            pass

    attempts = []

    def flaky_create(cls, *a, **k):
        attempts.append(None)
        return None if len(attempts) == 1 else _FakeWindow()

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(flaky_create))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Alice", hwnd=0x1000)]
    )
    libs = _FakeLibs(_FakeUser32(foreground=0x1000))

    h._sweep(libs)  # creation fails; Alice is selected but has no window yet
    assert h._selected_key == "Alice"
    assert "Alice" not in h._windows

    h._sweep(libs)  # creation succeeds; the selected key is unchanged
    assert h._windows["Alice"].selected is True


# --- live-read seams: show_labels, opacity, minimize_inactive_clients,
# never_minimize, locked -----------------------------------------------------


def test_show_labels_defaults_on_without_a_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._labels_shown() is True


def test_show_labels_reads_the_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None, show_labels=lambda: False)
    assert h._labels_shown() is False


def test_a_raising_show_labels_callable_falls_back_to_labels_on():
    """Runs on the preview thread inside _sweep and WM_APP_RESTYLE; a raise
    here must not be the thing that kills the pump."""

    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, show_labels=boom)
    assert h._labels_shown() is True


def test_opacity_defaults_opaque_without_a_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._current_opacity() == 255


def test_opacity_reads_the_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None, opacity=lambda: 180)
    assert h._current_opacity() == 180


def test_a_raising_opacity_callable_falls_back_to_opaque():
    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, opacity=boom)
    assert h._current_opacity() == 255


def test_minimize_inactive_defaults_off_without_a_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._minimizing_inactive() is False


def test_minimize_inactive_reads_the_callable():
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, minimize_inactive_clients=lambda: True
    )
    assert h._minimizing_inactive() is True


def test_a_raising_minimize_inactive_callable_falls_back_to_off():
    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, minimize_inactive_clients=boom
    )
    assert h._minimizing_inactive() is False


def test_never_minimize_defaults_to_nobody_without_a_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._is_never_minimize("Alice") is False


def test_never_minimize_checks_membership_in_the_live_list():
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, never_minimize=lambda: ["Alice"]
    )
    assert h._is_never_minimize("Alice") is True
    assert h._is_never_minimize("Bravo") is False


def test_a_raising_never_minimize_callable_falls_back_to_nobody_exempt():
    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, never_minimize=boom)
    assert h._is_never_minimize("Alice") is False


def test_locked_defaults_to_nobody_without_a_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._is_locked("Alice") is False


def test_locked_checks_membership_in_the_live_list():
    h = host.PreviewHost(on_layout_changed=lambda *a: None, locked=lambda: ["Alice"])
    assert h._is_locked("Alice") is True
    assert h._is_locked("Bravo") is False


def test_a_raising_locked_callable_falls_back_to_unlocked():
    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, locked=boom)
    assert h._is_locked("Alice") is False


# --- _sweep applies the live settings to a newly created window ------------


def _config_sweep_host(monkeypatch, *, client_key="Alice", saved=None, **kw):
    """A PreviewHost wired for a single-client sweep, with discovery,
    monitor enumeration and placement stubbed the same way
    test_the_sweep_places_a_new_preview_at_its_clamped_rect does."""
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, saved_layouts=saved, size=(320, 210), **kw
    )
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient(client_key)]
    )
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    return h


def test_the_sweep_resolves_lock_from_the_locked_callable_not_the_saved_entry(
    monkeypatch,
):
    """R1: Task 1 moved lock storage to the preview.locked character-name
    list. A saved layout entry that still says locked=True -- written by
    _layout_changed, still read by layout.py's own callers -- must NOT be
    what a new window opens locked as; only the live `locked` callable
    governs it."""
    seen = []

    def fake_create(cls, libs, client, rect, **kw):
        seen.append(kw["locked"])
        return

    h = _config_sweep_host(
        monkeypatch,
        saved={"Alice": layout.Entry(geometry.Rect(0, 0, 320, 210), True)},
        locked=list,
    )
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))

    h._sweep(libs=None)

    assert seen == [False]


def test_the_sweep_locks_a_new_window_when_the_locked_list_says_so(monkeypatch):
    seen = []

    def fake_create(cls, libs, client, rect, **kw):
        seen.append(kw["locked"])
        return

    h = _config_sweep_host(
        monkeypatch,
        saved={"Alice": layout.Entry(geometry.Rect(0, 0, 320, 210), False)},
        locked=lambda: ["Alice"],
    )
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))

    h._sweep(libs=None)

    assert seen == [True]


def test_the_sweep_passes_show_labels_and_opacity_at_creation(monkeypatch):
    """A preview appearing mid-session must be born with the current
    settings, not the shipped defaults -- otherwise a client that starts
    after a Settings change opens looking like the OLD configuration
    until the next restyle."""
    seen = []

    def fake_create(cls, libs, client, rect, **kw):
        seen.append((kw["show_labels"], kw["opacity"]))
        return

    h = _config_sweep_host(monkeypatch, show_labels=lambda: False, opacity=lambda: 180)
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))

    h._sweep(libs=None)

    assert seen == [(False, 180)]


# --- restyle(): the live-update entry point ---------------------------------


def test_restyle_posts_only_a_signal(monkeypatch):
    """Same shape as raise_alert()/set_hotkeys(): exercised through the
    real _post, not a stub standing in for it."""
    posted = []

    class _RestyleUser32(_FakeUser32):
        def PostMessageW(self, hwnd, msg, wparam, lparam):
            posted.append((msg, wparam, lparam))
            return 1

    libs = _FakeLibs(_RestyleUser32())
    monkeypatch.setattr(host.win32, "bind", lambda: libs)

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h.restyle()
    assert posted == [(host.win32.WM_APP_RESTYLE, 0, 0)]


def test_the_restyle_message_dispatches_to_the_handler(monkeypatch):
    """A message with nothing routing it to _restyle() falls through to
    DefWindowProcW and every open preview keeps whatever chrome it was
    created with, forever."""
    calls = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(h, "_restyle", lambda: calls.append(1))
    monkeypatch.setattr(host.win32, "bind", lambda: _FakeLibs(_FakeUser32()))

    h._host_proc(0x1, host.win32.WM_APP_RESTYLE, 0, 0)

    assert calls == [1]


class _FakeRestyleThumb:
    """Records every (rect, opacity) passed to update()."""

    def __init__(self):
        self.calls = []

    def update(self, rect, opacity=255):
        self.calls.append((rect, opacity))


class _RestyleWindow:
    """Duck-types just what _restyle touches: public chrome attributes,
    redraw(), and a thumbnail. Not a real PreviewWindow -- that needs an
    HWND, which is out of reach here."""

    def __init__(self, rect, show_labels=True, opacity=255, locked=False):
        self.rect = rect
        self.show_labels = show_labels
        self.opacity = opacity
        self.locked = locked
        self.redraws = 0
        self._thumb = _FakeRestyleThumb()

    def redraw(self, force=False):
        self.redraws += 1


def test_restyle_updates_every_open_window(monkeypatch):
    """WM_APP_RESTYLE must reach every window's chrome AND its DWM
    thumbnail: opacity is a thumbnail property, not a chrome pixel, so
    redraw() alone would leave the mirrored video at whatever opacity the
    preview was created with. locked is per-window, indexed by stable_key
    (R2) -- Alice and Bravo must land on opposite sides of it."""
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None,
        show_labels=lambda: False,
        opacity=lambda: 180,
        locked=lambda: ["Alice"],
    )
    alice = _RestyleWindow(geometry.Rect(0, 0, 320, 210))
    bravo = _RestyleWindow(geometry.Rect(0, 0, 320, 210))
    h._windows = {"Alice": alice, "Bravo": bravo}

    h._restyle()

    assert alice.show_labels is False
    assert alice.opacity == 180
    assert alice.locked is True
    assert bravo.locked is False
    assert alice.redraws == 1 and bravo.redraws == 1
    assert alice._thumb.calls == [
        (geometry.thumbnail_rect(alice.rect, host.window_mod.BORDER, 0), 180)
    ]


def test_restyle_reclaims_the_thumbnail_band_when_labels_are_off():
    """The thumbnail must be re-inset with the CURRENT label height, not
    the one the window was created with -- reverting to LABEL_H
    unconditionally here would leave the mirrored video sitting behind a
    band the chrome no longer draws once labels are turned off."""
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, show_labels=lambda: True, opacity=lambda: 255
    )
    win = _RestyleWindow(geometry.Rect(0, 0, 320, 210), show_labels=False)
    h._windows = {"Alice": win}

    h._restyle()

    assert win._thumb.calls == [
        (
            geometry.thumbnail_rect(
                win.rect, host.window_mod.BORDER, host.window_mod.LABEL_H
            ),
            255,
        )
    ]


def _captured_on_activate(monkeypatch, client_hwnd=0x1000):
    """Sweep once and return the on_activate the host handed the window,
    alongside a log of the window_mod.activate calls it makes.

    Goes through _sweep rather than calling _activate_client directly:
    the wiring at the create() call site is the half that breaks. A
    dropped or stubbed kwarg there leaves clicking a preview doing
    nothing, and nothing else in the suite looks at it.
    """
    calls = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: calls.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    captured = {}

    def fake_create(cls, *a, **k):
        # Returns no window, as the other _sweep fakes in this file do:
        # only the kwargs the host hands the window are under test.
        captured.update(k)

    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Alice", hwnd=client_hwnd)]
    )
    h._sweep(_FakeLibs(_FakeUser32()))
    return captured["on_activate"], calls


def test_the_host_performs_the_switch_a_clicked_preview_asks_for(monkeypatch):
    """The window no longer activates; it reports the gesture. If the host
    keeps handing it the old no-op stub, click-to-focus is dead and no
    other test notices -- window.py's own tests only see the callback
    fire, not what it does."""
    on_activate, calls = _captured_on_activate(monkeypatch)

    on_activate(_FakeClient("Alice", hwnd=0x1000))

    assert calls == [0x1000]


def test_the_hosts_activation_callback_switches_to_the_client_it_is_given(monkeypatch):
    """It must follow its argument rather than anything captured at
    creation: the roster is re-read every sweep, and the client record for
    a key is replaced whenever it reappears on a new hwnd."""
    on_activate, calls = _captured_on_activate(monkeypatch)

    on_activate(_FakeClient("Bravo", hwnd=0x2222))

    assert calls == [0x2222]


def test_the_hosts_activation_callback_reports_whether_it_took(monkeypatch):
    """window_mod.activate's verdict comes from GetForegroundWindow, and a
    switch can be refused. Anything the host does after a switch has to be
    able to tell -- dropping the bool here would make a refused switch
    indistinguishable from one that worked."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.window_mod, "activate", lambda libs, hwnd: False)
    assert h._activate_client(None, _FakeClient("Alice", hwnd=0x1000)) is False
    monkeypatch.setattr(host.window_mod, "activate", lambda libs, hwnd: True)
    assert h._activate_client(None, _FakeClient("Alice", hwnd=0x1000)) is True


def test_a_hotkey_and_a_click_go_through_the_same_switch(monkeypatch):
    """Both entry points must converge on _activate_client, or a step
    added to the switch silently applies to only one of them."""
    seen = []
    monkeypatch.setattr(
        host.PreviewHost,
        "_activate_client",
        lambda self, libs, client: seen.append(client.hwnd) or True,
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32(foreground=0)
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert seen == [0x1234]


class _SwitchUser32(_FakeUser32):
    """Records the foreground reads and the minimize sends into a shared
    order log, so a test can assert the SEQUENCE and not just the calls --
    the ordering is the whole feature here."""

    def __init__(self, order, foreground=0, send_result=1):
        super().__init__(foreground=foreground)
        self._order = order
        self._send_result = send_result

    def GetForegroundWindow(self):
        self._order.append(("foreground", self._foreground))
        return self._foreground

    def SendMessageTimeoutW(self, hwnd, msg, wparam, lparam, flags, timeout, result):
        self._order.append(("send", hwnd, msg, wparam, lparam, flags, timeout))
        return self._send_result


def _switching_host(
    monkeypatch,
    *,
    foreground,
    activated=True,
    send_result=1,
    minimize=True,
    never=(),
):
    """A host with two clients, Alice on 0x1111 and Bravo on 0x2222, whose
    activation, sleep and minimize send are all recorded in one log."""
    order = []
    monkeypatch.setattr(
        host.window_mod,
        "activate",
        lambda libs, hwnd: order.append(("activate", hwnd)) or activated,
    )
    monkeypatch.setattr(host.time, "sleep", lambda s: order.append(("sleep", s)))
    user32 = _SwitchUser32(order, foreground=foreground, send_result=send_result)
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None,
        minimize_inactive_clients=lambda: minimize,
        never_minimize=lambda: list(never),
    )
    h._clients = {
        "Alice": _FakeClient("Alice", hwnd=0x1111),
        "Bravo": _FakeClient("Bravo", hwnd=0x2222),
    }
    return h, _FakeLibs(user32), order


def test_the_switch_reads_the_foreground_activates_settles_minimizes_reactivates(
    monkeypatch,
):
    """The order is the feature. Reading the foreground after activating
    identifies the wrong client; minimizing before the settle races the
    switch; and skipping the second activation hands the foreground to
    whatever Windows picks after the minimize."""
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111)

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    assert order == [
        ("foreground", 0x1111),
        ("activate", 0x2222),
        ("sleep", host.SWITCH_SETTLE_MS / 1000.0),
        (
            "send",
            0x1111,
            host.win32.WM_SYSCOMMAND,
            host.win32.SC_MINIMIZE,
            0,
            host.win32.SMTO_ABORTIFHUNG,
            host.MINIMIZE_TIMEOUT_MS,
        ),
        ("activate", 0x2222),
    ]


def test_a_refused_switch_minimizes_nothing(monkeypatch):
    """The safety property, ported from TriffView. Minimizing after an
    activation that did not take leaves the user on an empty desktop with
    nothing focused -- their old client gone and the new one never
    arrived, which is strictly worse than the switch failing quietly."""
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111, activated=False)

    assert h._activate_client(libs, h._clients["Bravo"]) is False

    assert order == [("foreground", 0x1111), ("activate", 0x2222)]


def test_a_timed_out_minimize_does_not_reactivate(monkeypatch):
    """A zero return means the client never processed the message, so it
    is still exactly where it was. There is no foreground theft to undo,
    and a second activation would be an unexplained focus change."""
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111, send_result=0)

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    kinds = [entry[0] for entry in order]
    assert kinds == ["foreground", "activate", "sleep", "send"]


def test_a_never_minimize_character_is_left_alone(monkeypatch):
    """The roster names the client being switched AWAY from -- the one
    that would be minimized."""
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111, never=("Alice",))

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    assert order == [("foreground", 0x1111), ("activate", 0x2222)]


def test_the_switch_minimizes_nothing_while_the_setting_is_off(monkeypatch):
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111, minimize=False)

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    assert order == [("foreground", 0x1111), ("activate", 0x2222)]


def test_clicking_the_client_that_already_has_the_foreground_minimizes_nothing(
    monkeypatch,
):
    """window_mod.activate returns True EARLY when the target is already
    foreground, without touching anything -- so this arrives here as a
    successful activation whose previous and next client are the same.
    Minimizing on it would minimize the very client just clicked."""
    h, libs, order = _switching_host(monkeypatch, foreground=0x2222)

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    assert order == [("foreground", 0x2222), ("activate", 0x2222)]


def test_the_switch_reports_the_activation_verdict_even_when_it_minimizes(monkeypatch):
    """The bool is window_mod.activate's, not the minimize send's: the
    minimize is a side effect, and a caller asking whether the switch took
    must not be told 'no' because a client was slow to minimize."""
    h, libs, _ = _switching_host(monkeypatch, foreground=0x1111, send_result=0)
    assert h._activate_client(libs, h._clients["Bravo"]) is True

    h, libs, _ = _switching_host(monkeypatch, foreground=0x1111)
    assert h._activate_client(libs, h._clients["Bravo"]) is True


def test_a_foreground_that_is_not_a_client_minimizes_nothing(monkeypatch):
    """A browser, Discord, or Wingman itself. Nothing in the roster owns
    that hwnd, so there is no previous client to minimize -- and sending
    SC_MINIMIZE to whatever happened to be foreground would minimize the
    user's other application on every switch."""
    h, libs, order = _switching_host(monkeypatch, foreground=0xDEAD)

    assert h._activate_client(libs, h._clients["Bravo"]) is True

    assert order == [("foreground", 0xDEAD), ("activate", 0x2222)]
