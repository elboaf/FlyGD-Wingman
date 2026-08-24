"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""
import sys

import pytest

from obs_youtube_uploader.preview import geometry, gestures, host


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
    running.wait(5)          # the first worker is definitely still alive
    h.start()
    release.set()
    h.stop()
    assert len(started) == 1


def test_shutdown_flushes_pending_layouts(monkeypatch):
    """Layout writes are debounced by a second. Quitting inside that window
    after a drag would otherwise discard the move -- and the plan called
    for this explicitly before anyone noticed it was missing."""
    flushed = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         flush_layouts=lambda: flushed.append(1))

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

    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         flush_layouts=boom)
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

    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         saved_layouts={"Pilot": Entry(Rect(1, 2, 320, 210),
                                                       locked=True)})
    assert h._saved["Pilot"].locked is True


@pytest.mark.skipif(sys.platform != "win32",
                    reason="needs a real message pump and window station")
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
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice"), _FakeClient("Bravo")])
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))

    h._sweep(libs=None)

    assert h._windows == {}
    assert sorted(h._clients) == ["Alice", "Bravo"]
    assert h.characters() == ["Alice", "Bravo"]


def test_the_registry_refreshes_hwnds_for_a_kept_key(monkeypatch):
    """reconcile() compares stable keys only, so a character that reappears
    on a NEW hwnd counts as 'kept' -- a retained record would point at a
    dead window."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))

    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice", hwnd=0x1111)])
    h._sweep(libs=None)
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice", hwnd=0x2222)])
    h._sweep(libs=None)

    assert h._clients["Alice"].hwnd == 0x2222


def test_characters_excludes_clients_at_character_select(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(
        host.discovery, "list_clients",
        lambda: [_FakeClient("Alice"),
                 _FakeClient("hwnd:0x9", character=None)])
    h._sweep(libs=None)

    assert h.characters() == ["Alice"]


def test_a_changed_client_set_is_reported_once(monkeypatch):
    seen = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         on_clients_changed=seen.append)
    monkeypatch.setattr(host.discovery, "flush_image_cache_periodically",
                        lambda: None)
    monkeypatch.setattr(host.PreviewWindow, "create",
                        classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(host.discovery, "list_clients",
                        lambda: [_FakeClient("Alice")])

    h._sweep(libs=None)
    h._sweep(libs=None)      # unchanged: must not report again

    assert seen == [["Alice"]]


def test_host_command_messages_are_distinct():
    """Two commands sharing a value would silently run the wrong handler.

    Lives here rather than in tests/test_preview_win32.py: that file's tests
    are skipped on non-Windows platforms because most of them exercise
    bind()'s DLL declarations, but these are plain module-scope integers
    that need no DLL -- and CI is ubuntu-latest only, so that skip would
    hide this assertion from every CI run.
    """
    commands = {host.win32.WM_APP_SHUTDOWN, host.win32.WM_APP_SWEEP_NOW,
                host.win32.WM_APP_REBIND}
    assert len(commands) == 3
    assert all(c >= host.win32.WM_APP for c in commands)


def test_plan_assigns_one_id_per_binding():
    plan = host.plan_registrations(
        {"characters": {"Bravo": "Ctrl+F2", "Alice": "Ctrl+F1"},
         "cycle_next": "Ctrl+Alt+Right", "cycle_prev": "Ctrl+Alt+Left"})
    ids = [entry[0] for entry in plan]
    assert len(ids) == len(set(ids)) == 4
    assert all(0 < i <= 0xBFFF for i in ids)


def test_plan_is_stable_across_calls():
    """Rebinding unregisters and re-registers everything, so an unstable
    id assignment would churn registrations that did not change."""
    table = {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
             "cycle_next": "", "cycle_prev": ""}
    assert host.plan_registrations(table) == host.plan_registrations(table)


def test_plan_drops_unparseable_and_empty_gestures():
    plan = host.plan_registrations(
        {"characters": {"Alice": "", "Bravo": "nonsense", "Carol": "Ctrl+F3"},
         "cycle_next": "", "cycle_prev": ""})
    assert [entry[2] for entry in plan] == [("focus", "Carol")]


def test_plan_drops_a_duplicate_chord():
    """Windows would refuse the second registration anyway; catching it
    here keeps the reported status honest about which binding lost."""
    plan = host.plan_registrations(
        {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F1"},
         "cycle_next": "", "cycle_prev": ""})
    assert len(plan) == 1


def test_cycle_actions_carry_direction():
    plan = host.plan_registrations(
        {"characters": {}, "cycle_next": "Ctrl+Alt+Right",
         "cycle_prev": "Ctrl+Alt+Left"})
    actions = sorted(entry[2] for entry in plan)
    assert actions == [("cycle", -1), ("cycle", 1)]


class _FakeUser32:
    def __init__(self, refuse=()):
        self.registered = {}
        self.unregistered = []
        self.calls = []
        self._refuse = set(refuse)

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


class _FakeLibs:
    def __init__(self, user32):
        self.user32 = user32


def test_rebind_unregisters_everything_before_registering():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)

    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})
    user32.calls.clear()
    h._apply_hotkeys(libs, {"characters": {"Bravo": "Ctrl+F2"},
                            "cycle_next": "", "cycle_prev": ""})

    kinds = [kind for kind, _ in user32.calls]
    assert kinds.index("unregister") < kinds.index("register")
    assert list(user32.registered.values()) == [
        (gestures.parse("Ctrl+F2").mods, gestures.parse("Ctrl+F2").vk)]


def test_a_refused_chord_is_reported_and_the_others_still_register():
    refused = gestures.parse("Ctrl+F1")
    user32 = _FakeUser32(refuse={(refused.mods, refused.vk)})
    reported = []
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         on_hotkey_status=reported.append)
    h._hwnd = 0x99

    h._apply_hotkeys(_FakeLibs(user32),
                     {"characters": {"Alice": "Ctrl+F1", "Bravo": "Ctrl+F2"},
                      "cycle_next": "", "cycle_prev": ""})

    assert h.hotkey_status() == {"Ctrl+F1": False, "Ctrl+F2": True}
    assert reported == [{"Ctrl+F1": False, "Ctrl+F2": True}]


def test_status_is_readable_after_a_pass_that_reported_to_nobody():
    """Previews start BEFORE the webview exists (__main__.py:406-411), so a
    conflict at launch is announced into the void. It has to be readable
    afterwards or it is lost for the session."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._apply_hotkeys(_FakeLibs(_FakeUser32()),
                     {"characters": {"Alice": "Ctrl+F1"},
                      "cycle_next": "", "cycle_prev": ""})
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
    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    h._teardown(libs)

    assert order == ["unregister-hotkey", "unhook", "destroy-window", "quit"]


def test_hotkey_focuses_the_named_character(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1234)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {"Alice": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x1234]


def test_cycle_hotkey_anchors_on_the_foreground_client(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {"Alice": _FakeClient("Alice", hwnd=0x1111),
                  "Bravo": _FakeClient("Bravo", hwnd=0x2222)}
    user32 = _FakeUser32()
    user32.GetForegroundWindow = lambda: 0x1111
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {}, "cycle_next": "Ctrl+Alt+Right",
                            "cycle_prev": ""})

    ident = next(iter(user32.registered))
    h._on_hotkey(libs, ident)

    assert activated == [0x2222]


def test_a_focus_chord_for_an_absent_character_does_nothing(monkeypatch):
    activated = []
    monkeypatch.setattr(host.window_mod, "activate",
                        lambda libs, hwnd: activated.append(hwnd) or True)
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._clients = {}
    user32 = _FakeUser32()
    libs = _FakeLibs(user32)
    h._apply_hotkeys(libs, {"characters": {"Ghost": "Ctrl+F1"},
                            "cycle_next": "", "cycle_prev": ""})

    h._on_hotkey(libs, next(iter(user32.registered)))

    assert activated == []
