"""Reconciliation and lifecycle. The pump itself is smoke-tested.

reconcile() is where a leak would live: a client that disappears without
being removed leaves a thumbnail registered against a dead source and a
window that never closes."""
import sys

import pytest

from obs_youtube_uploader.preview import host


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
