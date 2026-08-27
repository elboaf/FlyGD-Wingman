"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""

import ctypes
import itertools
import logging
import sys

import pytest

from wingman.preview import alertframes, geometry, gestures, host, layout


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
    from wingman.preview.geometry import Rect

    sent = []
    h = host.PreviewHost(on_layout_changed=lambda *a: sent.append(a))
    h._layout_changed("Pilot", Rect(10, 20, 320, 210), False)

    assert h._saved["Pilot"].rect == Rect(10, 20, 320, 210)
    assert sent == [("Pilot", Rect(10, 20, 320, 210), False)]


def test_a_saved_layout_entry_keeps_its_lock_flag():
    """layout.Entry carries `locked` and deserialize restores it onto
    _saved. That flag no longer decides how a window OPENS -- Task 1 moved
    that to the preview.locked name list, and
    test_the_sweep_resolves_lock_from_the_locked_callable_not_the_saved_entry
    pins it. This is only that the entry round-trips the field, which it
    must keep doing while existing settings files still carry it."""
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

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
    from wingman.preview import discovery

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
        host.win32.WM_APP_RESET_LAYOUTS,
        host.win32.WM_APP_RESIZE_ONE,
    }
    assert len(commands) == 7
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
    assert [entry[2] for entry in plan] == [("focus", ("Carol",))]


def test_plan_merges_duplicate_chords():
    """Two characters on one chord is a supported setup, not a mistake.

    A multiboxer runs a different subset of their characters each session
    and wants one physical key to mean "go to whichever of these is up".
    One registration carries every name bound to it -- Windows only has
    one to give -- and _on_hotkey picks among the names actually running.
    """
    plan = host.plan_registrations(
        {
            "characters": {"Bravo": "Ctrl+F1", "Alice": "Ctrl+F1"},
            "cycle_next": "",
            "cycle_prev": "",
        }
    )
    assert len(plan) == 1
    assert plan[0][2] == ("focus", ("Alice", "Bravo"))


def test_plan_drops_a_cycle_chord_a_character_already_owns():
    """Merging is for characters only.

    A cycle chord is a different ACTION, so there is nothing to merge into
    -- one of the two has to lose, and it is still the cycle chord, which
    is what the missing hotkey_status entry tells the page.
    """
    plan = host.plan_registrations(
        {
            "characters": {"Alice": "Ctrl+Alt+Right"},
            "cycle_next": "Ctrl+Alt+Right",
            "cycle_prev": "",
        }
    )
    assert [entry[2] for entry in plan] == [("focus", ("Alice",))]


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

    def GetClientRect(self, hwnd, rect_ptr):
        # Falsy: these tests are about selection and hotkeys, not sizing,
        # so declining to sample is the least assumption. A real rect is
        # exercised directly against _record_client_sizes by
        # test_record_client_sizes_samples_a_real_rect_and_skips_a_failed_probe,
        # not through this fake or through _sweep.
        return 0


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
    _pending_alerts, _selected_key, and _foreground behind. The queue
    grows between stop() and the next reconcile (ui/api.py's
    set_preview_enabled(False) calls host.stop() before
    alerts.reconcile()), so an hour-old batch would arm every preview at
    once on the next enable; and _apply_selection's
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
    h._focused_key = "Alice"
    h._foreground = 0x1234
    libs = _FakeLibs(_TeardownUser32())

    h._teardown(libs)

    assert h._pending_alerts == []
    assert h._selected_key is None
    assert h._focused_key is None
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


def test_shared_hotkey_skips_the_client_already_in_front(monkeypatch):
    """The tie-break for a chord several characters share.

    Both are running, so "focus the one bound to this key" has two
    answers. Picking the one that is NOT already in front means a press
    always moves you; picking first-by-name would make the key a no-op
    half the time.
    """
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
        libs,
        {
            "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
            "cycle_next": "",
            "cycle_prev": "",
        },
    )

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == [0x2222]


def test_shared_hotkey_ignores_names_that_are_not_running(monkeypatch):
    """The whole point of the feature: the same key every session, whoever
    of that group happens to be logged in."""
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    # Alice is bound first by name but is not logged in this session.
    h._clients = {"Bravo": _FakeClient("Bravo", hwnd=0x2222)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs,
        {
            "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
            "cycle_next": "",
            "cycle_prev": "",
        },
    )

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == [0x2222]


def test_shared_hotkey_refocuses_the_only_running_match(monkeypatch):
    """One running match that is ALREADY in front is still the answer.

    The not-in-front preference is a tie-break, not a filter -- dropping
    the only candidate would make the key dead exactly when the user is
    looking at that client.
    """
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1111)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0x1111
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs,
        {
            "characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
            "cycle_next": "",
            "cycle_prev": "",
        },
    )

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == [0x1111]


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


def test_an_armed_capture_reports_the_chord_instead_of_switching(monkeypatch):
    """The bug this exists for: rebinding a key that is already bound.

    A registered chord is delivered to THIS window as WM_HOTKEY and never
    reaches the focused WebView2 window, so previews.js' keydown listener
    never sees it -- the row sat on "Press a key..." while the press did
    its normal job and focused a client. Users found the workaround
    (clear the bind first, which unregisters it, then capture) which is
    exactly the shape of the diagnosis.
    """
    activated = []
    monkeypatch.setattr(
        host.window_mod, "activate", lambda libs, hwnd: activated.append(hwnd) or True
    )
    captured = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, on_bind_captured=captured.append
    )
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )
    h.set_capture(True)

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert captured == ["Ctrl+F1"]
    # The chord must not ALSO do its normal job: the press that was meant
    # to rebind a row would otherwise yank the foreground to a client and
    # take the window being typed into away with it.
    assert activated == []


def test_capture_expires_so_a_stuck_flag_cannot_kill_the_hotkeys(monkeypatch):
    """The failure mode that decides this is a deadline and not a bool.

    The page disarms on every exit path it knows about, but a WebView2
    crash or a reload with a capture armed knows none of them, and a flag
    left set turns every preview hotkey into a silent no-op with nothing
    on screen to say why. Expiry is checked where it is read, so no timer
    has to fire for the hotkeys to come back.
    """
    monkeypatch.setattr(host.window_mod, "activate", lambda libs, hwnd: True)
    captured = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, on_bind_captured=captured.append
    )
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )
    h.set_capture(True)
    h._capture_until -= host.CAPTURE_TIMEOUT_S + 1

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert captured == []


def test_capture_is_disarmed_by_the_chord_it_captured(monkeypatch):
    """One press, one capture. The page sends set_capture(False) too, but
    the round trip is not instant and a second press arriving inside it
    must not be eaten as well."""
    monkeypatch.setattr(host.window_mod, "activate", lambda libs, hwnd: True)
    captured = []
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, on_bind_captured=captured.append
    )
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(
        libs, {"characters": {"Alice": "Ctrl+F1"}, "cycle_next": "", "cycle_prev": ""}
    )
    h.set_capture(True)
    ident = next(iter(user32.registered))

    h._on_hotkey(libs, ident)
    h._on_hotkey(libs, ident)

    assert captured == ["Ctrl+F1"]


def test_a_raising_capture_callback_does_not_kill_the_pump():
    """on_bind_captured is outside code called from the wndproc, where
    sys.unraisablehook would swallow the traceback -- the same reasoning
    as on_hotkey_status and on_clients_changed."""

    def boom(text):
        raise RuntimeError("bridge is gone")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, on_bind_captured=boom)
    h._hwnd = 0x99
    h._registered = {1: ("focus", ("Alice",))}
    h._registered_text = {1: "Ctrl+F1"}
    h.set_capture(True)

    h._on_hotkey(_FakeLibs(_FakeUser32()), 1)  # must not raise


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
    alice_ident = ident_by_action[("focus", ("Alice",))]
    ghost_ident = ident_by_action[("focus", ("Ghost",))]

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

        # _apply_selection pushes both flags onto every live preview each
        # sweep, so a fake window has to answer for both even when the test
        # is only about placement.
        def set_selected(self, selected):
            pass

        def set_focused(self, focused):
            pass

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


def test_the_ring_stays_on_the_last_client_used_when_focus_leaves_eve(monkeypatch):
    """The ring answers "which client are you flying", not "which window
    has the foreground right now". Clicking a browser, Discord or Wingman
    itself must leave the ring where it was: the client is still the one
    on screen, and losing the highlight the moment you tab away was
    reported as unexpected.

    The old contract cleared it, on the grounds that a sticky ring could
    not be told apart from an alert on that same client. Selection and
    focus are separate flags now -- see the focus test below -- so the
    ring can stick without an alert ever counting as seen.
    """
    h = _swept_host(monkeypatch, ["Alice", "Bravo"], foreground=0x1000)
    assert h._selected_key == "Alice"
    h._sweep(_FakeLibs(_FakeUser32(foreground=0xDEAD)))
    assert h._selected_key == "Alice"


def test_the_ring_follows_a_switch_to_another_client(monkeypatch):
    """Sticky must not mean stuck: another client taking the foreground
    moves the ring, which is the whole point of the highlight."""
    h = _swept_host(monkeypatch, ["Alice", "Bravo"], foreground=0x1000)
    h._sweep(_FakeLibs(_FakeUser32(foreground=0x2000)))
    assert h._selected_key == "Bravo"


def test_the_ring_clears_when_the_client_it_marks_exits(monkeypatch):
    """A sticky key outlives the foreground on purpose; it must not
    outlive the client. Nothing else clears it, so a logged-out character
    would keep the ring for the session and, worse, hand it straight back
    to whatever reappeared under the same stable key.
    """
    h = _swept_host(monkeypatch, ["Alice"], foreground=0x1000)
    assert h._selected_key == "Alice"
    monkeypatch.setattr(host.discovery, "list_clients", list)
    h._sweep(_FakeLibs(_FakeUser32(foreground=0xDEAD)))
    assert h._selected_key is None


def test_focus_tracks_the_real_foreground_and_clears_off_a_client(monkeypatch):
    """The flag the alerts depend on. `PreviewWindow.set_focused` is what
    acknowledges a persistent alert, so it must follow the actual
    foreground window and clear the moment it leaves EVE -- if focus went
    sticky along with the ring, an alert arriving on the client you last
    used while you sit in a browser would count as already seen and expire
    unread. That is the failure the old non-sticky selection was
    protecting against; the protection now lives here.
    """
    h = _swept_host(monkeypatch, ["Alice"], foreground=0x1000)
    assert h._focused_key == "Alice"
    h._sweep(_FakeLibs(_FakeUser32(foreground=0xDEAD)))
    assert h._focused_key is None
    assert h._selected_key == "Alice"


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
            self.focused = False

        def set_selected(self, selected):
            self.selected = selected

        def set_focused(self, focused):
            self.focused = focused

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


def test_the_sweep_creates_no_window_for_a_disabled_character(monkeypatch):
    """The character is opted out of previews, so no mirror window is
    built -- but the client registry still holds them. A disabled
    character is still running, still listed on the Previews page, and
    still has to be re-enableable, so filtering the DESIRED WINDOW SET is
    not the same as filtering discovery."""
    created = []

    def fake_create(cls, libs, client, rect, **kw):
        created.append(client.stable_key)
        return

    h = _config_sweep_host(monkeypatch, disabled=lambda: ["Alice"])
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))

    h._sweep(libs=None)

    assert created == []
    assert sorted(h._clients) == ["Alice"]
    assert h.characters() == ["Alice"]


def test_the_sweep_closes_an_open_window_when_a_character_is_disabled(monkeypatch):
    """Ticking the box mid-session has to take the picture off the screen,
    not merely stop the next one being built."""
    closed = []

    class _Win:
        rect = geometry.Rect(0, 0, 0, 0)

        def set_selected(self, selected):
            pass

        def set_focused(self, focused):
            pass

        def close(self):
            closed.append(True)

    off = []
    h = _config_sweep_host(monkeypatch, disabled=lambda: list(off))
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: _Win())
    )

    h._sweep(libs=None)
    assert sorted(h._windows) == ["Alice"]

    off.append("Alice")
    h._sweep(libs=None)

    assert closed == [True]
    assert h._windows == {}


def test_a_disabled_character_gets_no_hotkey_registration(monkeypatch):
    """Chosen behaviour: opting a character out turns off their own focus
    keybind too. Filtered here rather than in plan_registrations, which
    stays pure -- and the disabled list changes independently of the
    binding table, so the filter has to be applied at every rebind."""
    h = _config_sweep_host(monkeypatch, disabled=lambda: ["Alice"])
    libs = _FakeLibs(_FakeUser32())
    h._hwnd = 0x1234

    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"}})

    assert sorted(h._registered_text.values()) == ["Ctrl+F2"]


def test_a_disabled_character_is_skipped_by_the_cycle_keybinds(monkeypatch):
    """Cycle walks the running clients; a character with no preview on
    screen must not be a stop on that walk."""
    h = _config_sweep_host(monkeypatch, disabled=lambda: ["Bravo"])
    monkeypatch.setattr(
        host.discovery,
        "list_clients",
        lambda: [_FakeClient("Alice"), _FakeClient("Bravo"), _FakeClient("Charlie")],
    )
    monkeypatch.setattr(
        host.PreviewWindow, "create", classmethod(lambda cls, *a, **k: None)
    )
    h._sweep(libs=None)

    assert h._cycle_keys() == ["Alice", "Charlie"]


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

    def __init__(self, rect, show_labels=True, opacity=255, locked=False, inset=None):
        self.rect = rect
        self.show_labels = show_labels
        self.opacity = opacity
        self.locked = locked
        self.redraws = 0
        # The real PreviewWindow widens this to ALERT_BORDER for the
        # duration of an alert, so _restyle cannot assume BORDER.
        self._inset = host.window_mod.BORDER if inset is None else inset
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


def test_restyle_keeps_a_widened_alert_inset():
    """An alert widens the thumbnail's inset to ALERT_BORDER so the 6px
    ring is not overpainted (PreviewWindow._set_inset). _restyle re-pushes
    the thumbnail rect, so it has to use the window's CURRENT inset:
    hardcoding BORDER here means changing any live setting -- opacity,
    labels, a lock -- while a client is under fire snaps the video back
    over the ring, leaving it showing as corner brackets until the alert
    clears and nothing to explain why.
    """
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None, show_labels=lambda: True, opacity=lambda: 255
    )
    win = _RestyleWindow(geometry.Rect(0, 0, 320, 210), inset=alertframes.ALERT_BORDER)
    h._windows = {"Alice": win}

    h._restyle()

    assert win._thumb.calls == [
        (
            geometry.thumbnail_rect(
                win.rect, alertframes.ALERT_BORDER, host.window_mod.LABEL_H
            ),
            255,
        )
    ]


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


# --- resize_preview()/reset_layouts(): on-demand sizing ---------------------


def test_resize_preview_stashes_the_payload_and_posts_only_a_signal(monkeypatch):
    """PostMessageW carries integers only, so the size travels in a field
    under the lock -- set_hotkeys' shape."""
    h = _placement_host(monkeypatch)
    h.resize_preview("Alice", (640, 392))
    assert h._pending_resize == {"Alice": (640, 392)}


def test_reset_layouts_clears_saved_and_calls_the_injected_clear(monkeypatch):
    cleared = []
    h = _placement_host(monkeypatch, clear_layouts=lambda: cleared.append(True))
    monkeypatch.setattr(h, "_monitors", lambda: MONITORS)
    h._saved["Alice"] = layout.Entry(geometry.Rect(1, 2, 3, 4))
    h._reset_layouts()
    assert cleared == [True]
    assert h._saved == {}


class _MovableWindow:
    """Minimal double for the one call both `_apply_resizes` and
    `_reset_layouts` make on every open preview: `.move(rect)` relocates it,
    same as the real PreviewWindow's effect on `.rect`."""

    def __init__(self, rect, locked=False):
        self.rect = rect
        self.locked = locked

    def move(self, rect):
        self.rect = rect


def test_reset_does_not_record_the_defaults_it_just_placed(monkeypatch):
    """Writing them back would repopulate the table the reset just
    emptied -- a reset leaving the file exactly as full as it found it."""
    recorded = []
    h = host.PreviewHost(on_layout_changed=lambda *a: recorded.append(a))
    monkeypatch.setattr(h, "_screen", lambda: VIRTUAL)
    monkeypatch.setattr(h, "_monitors", lambda: MONITORS)
    win = _MovableWindow(geometry.Rect(0, 0, 100, 100))
    h._windows = {"Alice": win}

    h._reset_layouts()

    # The loop actually ran -- move() placed the preview at its resolved
    # default rect, not left at its pre-reset position.
    assert win.rect != geometry.Rect(0, 0, 100, 100)
    assert recorded == []


def test_apply_resizes_moves_the_window_and_records_it_like_a_drag(monkeypatch):
    """A typed size is the user's choice and must survive a restart exactly
    as a dragged position does -- unlike _reset_layouts, this one records."""
    recorded = []
    h = host.PreviewHost(on_layout_changed=lambda *a: recorded.append(a))
    win = _MovableWindow(geometry.Rect(10, 20, 320, 210))
    h._windows = {"Alice": win}

    h.resize_preview("Alice", (640, 392))
    h._apply_resizes()

    expected = geometry.Rect(10, 20, 640, 392)
    assert win.rect == expected
    assert h._saved["Alice"] == layout.Entry(expected, False)
    assert recorded == [("Alice", expected, False)]


def test_record_client_sizes_samples_a_real_rect_and_skips_a_failed_probe():
    """The one branch of _record_client_sizes that has never run: every
    GetClientRect fake in this suite (including the module-level
    _FakeUser32) returns falsy, so the actual w/h computation and
    client_sizes()'s return value have never been exercised.

    Also pins the reused win32.RECT() across the loop: Bravo's failed probe
    must not leave it mapped to a stale size, and Cleo's later successful
    probe must not inherit whatever the struct held after Bravo's call.
    """

    class _SizingUser32:
        def __init__(self, dims):
            self._dims = dims  # hwnd -> (w, h), or absent to fail

        def GetClientRect(self, hwnd, rect_ptr):
            dims = self._dims.get(hwnd)
            if dims is None:
                return 0
            r = ctypes.cast(rect_ptr, ctypes.POINTER(host.win32.RECT)).contents
            r.left, r.top, r.right, r.bottom = 0, 0, dims[0], dims[1]
            return 1

    libs = _FakeLibs(_SizingUser32({0x1001: (1920, 1080), 0x1003: (800, 600)}))
    clients = {
        "Alice": _FakeClient("Alice", hwnd=0x1001),
        "Bravo": _FakeClient("Bravo", hwnd=0x1002),  # absent from _dims -> fails
        "Cleo": _FakeClient("Cleo", hwnd=0x1003),
    }

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._record_client_sizes(libs, clients)

    assert h.client_sizes() == {"Alice": (1920, 1080), "Cleo": (800, 600)}


def test_lock_aspect_defaults_on_without_a_callable():
    """The behaviour that predates the toggle: the handle has always held
    the client's shape."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    assert h._locking_aspect() is True


def test_lock_aspect_reads_the_callable():
    h = host.PreviewHost(on_layout_changed=lambda *a: None, lock_aspect=lambda: False)
    assert h._locking_aspect() is False


def test_a_raising_lock_aspect_callable_falls_back_to_locked():
    """Runs on the preview thread inside _sweep and WM_APP_RESTYLE; a raise
    here must not be the thing that kills the pump."""

    def boom():
        raise RuntimeError("settings vanished")

    h = host.PreviewHost(on_layout_changed=lambda *a: None, lock_aspect=boom)
    assert h._locking_aspect() is True


def test_restyle_pushes_lock_aspect_onto_every_open_window():
    """The checkbox is read when a resize drag BEGINS, so a restyle that
    updated chrome but not this flag would leave an already-open preview
    obeying the old setting until it was closed and reopened -- with the
    box in Settings showing the new one. _RestyleWindow duck-types the
    real window, and Python would happily accept the attribute without
    anyone asserting it arrived."""
    h = host.PreviewHost(
        on_layout_changed=lambda *a: None,
        lock_aspect=lambda: False,
    )
    alice = _RestyleWindow(geometry.Rect(0, 0, 320, 210))
    bravo = _RestyleWindow(geometry.Rect(0, 0, 320, 210))
    h._windows = {"Alice": alice, "Bravo": bravo}

    h._restyle()

    assert alice.lock_aspect is False
    assert bravo.lock_aspect is False


def test_a_newly_created_preview_is_born_with_the_current_lock_aspect(monkeypatch):
    """The other half of the restyle guard above. _restyle only reaches
    windows that already exist, so a client that STARTS while the box is
    unticked must be created unlocked -- otherwise it holds its client's
    shape until the next unrelated restyle happens to correct it, and the
    setting appears to apply to some previews and not others."""
    seen = {}

    class _Win:
        rect = geometry.Rect(0, 0, 320, 210)
        locked = False

        def destroy(self):
            pass

        # _apply_focus runs at the end of every sweep and touches both.
        def set_focused(self, value):
            pass

        def set_selected(self, value):
            pass

    def fake_create(cls, libs, client, rect, **kw):
        seen.update(kw)
        return _Win()

    h = host.PreviewHost(
        on_layout_changed=lambda *a: None,
        size=(320, 210),
        lock_aspect=lambda: False,
    )
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically", lambda: None)
    monkeypatch.setattr(
        host.discovery, "list_clients", lambda: [_FakeClient("Guarzo Togenada")]
    )
    monkeypatch.setattr(host.PreviewWindow, "create", classmethod(fake_create))
    monkeypatch.setattr(h, "_screen", lambda: VIRTUAL)
    monkeypatch.setattr(h, "_monitors", lambda: MONITORS)

    h._sweep(libs=None)

    assert seen["lock_aspect"] is False
