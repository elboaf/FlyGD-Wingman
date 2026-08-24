"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""
import sys

import pytest

from obs_youtube_uploader.preview import geometry, host


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
