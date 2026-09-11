"""Drive the real host/window ownership boundaries without a native pump."""

from types import SimpleNamespace

import pytest

from wingman.preview import geometry, host, window
from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot


def client(name="Alice", hwnd=16, pid=101, serial=1):
    return RosterClient(
        hwnd,
        pid,
        f"EVE - {name}" if name else "EVE",
        name,
        ClientSessionId(hwnd, pid, name, serial) if name else None,
    )


@pytest.fixture
def runtime(monkeypatch):
    from tests.test_preview_thumbnail import FakeDwm

    posted, closed, made = [], [], []
    native = SimpleNamespace(
        dwmapi=FakeDwm(),
        user32=SimpleNamespace(
            PostMessageW=lambda hwnd, message, wp, lp: posted.append(message) or 1,
            GetForegroundWindow=lambda: 0,
            GetClientRect=lambda *args: 0,
            DestroyWindow=lambda hwnd: closed.append(hwnd),
            PostQuitMessage=lambda code: None,
        ),
    )
    monkeypatch.setattr(host.win32, "bind", lambda: native)
    monkeypatch.setattr(window.layered, "push", lambda *args: None)
    h = host.PreviewHost(
        on_layout_changed=lambda *args: None, show_labels=lambda: False
    )
    h._hwnd = 999
    monkeypatch.setattr(h, "_screen", lambda: geometry.Rect(0, 0, 1920, 1080))
    monkeypatch.setattr(h, "_monitors", lambda: [geometry.Rect(0, 0, 1920, 1080)])

    def create(libs, source, rect, **kwargs):
        win = window.PreviewWindow(native, source, rect, **kwargs)
        win.hwnd = 1000 + len(made)
        made.append(win)
        return win

    monkeypatch.setattr(host.PreviewWindow, "create", create)

    def roster(generation, *entries):
        h.apply_roster(RosterSnapshot(generation, entries))
        h._apply_pending_roster(None)

    return SimpleNamespace(
        host=h, native=native, posted=posted, made=made, closed=closed, roster=roster
    )


def test_metadata_coalesces_values_and_wakes_without_touching_windows_at_ingress(
    runtime,
):
    r, c = runtime, client()
    r.roster(1, c)
    h = r.host
    h.set_metadata_generation(1)
    h._apply_metadata()
    r.posted.clear()
    values = {c.session: "OLD"}
    h.submit_metadata(1, values)
    values[c.session] = "MUTATED"
    h.submit_metadata(1, {c.session: "HOME"})
    h.submit_metadata(1, {c.session: "HOME"})
    assert r.made[0]._system_name is None
    assert r.posted == [host.win32.WM_APP_METADATA]
    h._host_proc(h._hwnd, host.win32.WM_APP_METADATA, 0, 0)
    assert r.made[0]._system_name == "HOME"
    h.submit_metadata(1, {c.session: None})
    assert r.posted == [host.win32.WM_APP_METADATA] * 2
    h._apply_metadata()
    assert r.made[0]._system_name is None


def test_metadata_roster_has_no_recent_name_cap_and_rejects_unknown_sessions(runtime):
    entries = tuple(client(f"Pilot {i}", i + 1) for i in range(91))
    runtime.roster(1, *entries)
    h = runtime.host
    assert h.metadata_sessions() == frozenset(c.session for c in entries)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "HOME" for c in entries})
    h.submit_metadata(
        1, {client("Unknown", i + 1000).session: "NO" for i in range(500)}
    )
    assert len(h._metadata_values) == 91
    h._apply_metadata()
    assert [w._system_name for w in runtime.made] == ["HOME"] * 91
    h.apply_roster(RosterSnapshot(2, entries[:1]))
    assert h.metadata_sessions() == frozenset({entries[0].session})
    assert len(h._metadata_values) == 1


def test_only_successful_named_primary_previews_are_published(runtime, monkeypatch):
    r, h = runtime, runtime.host
    create = host.PreviewWindow.create
    monkeypatch.setattr(
        host.PreviewWindow,
        "create",
        lambda libs, c, *a, **k: (
            None if c.character == "Failed" else create(libs, c, *a, **k)
        ),
    )
    h._excluded = lambda: ["Excluded"]
    good = client()
    r.roster(1, good, client("Failed", 17), client("Excluded", 18), client(None, 19))
    assert h.metadata_sessions() == frozenset({good.session})
    assert h.characters() == ["Alice", "Excluded", "Failed"]


def test_generation_fence_clears_old_data_and_does_not_rewind(runtime):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._apply_metadata()
    h.set_metadata_generation(2)
    h.submit_metadata(1, {c.session: "LATE"})
    h.set_metadata_generation(1)
    h._apply_metadata()
    assert runtime.made[0]._system_name is None
    h.submit_metadata(2, {c.session: "NEW"})
    h.set_metadata_generation(2)
    h._apply_metadata()
    assert runtime.made[0]._system_name == "NEW"


@pytest.mark.parametrize("departure", ["logout", "select", "pid", "hwnd", "session"])
def test_first_admitted_departure_revokes_metadata_before_roster_application(
    runtime, departure
):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._apply_metadata()
    next_client = {
        "logout": None,
        "select": client(None),
        "pid": client(pid=102),
        "hwnd": client(hwnd=17),
        "session": client(serial=2),
    }[departure]
    h.apply_roster(RosterSnapshot(2, (next_client,) if next_client else ()))
    h.submit_metadata(1, {c.session: "LATE"})
    if next_client and next_client.session:
        h.submit_metadata(1, {next_client.session: "TOO EARLY"})
    assert not h.metadata_sessions()
    h._apply_metadata()  # Metadata message beats the pending roster message.
    assert runtime.made[0]._system_name is None
    h._apply_pending_roster(None)
    assert all(w._system_name is None for w in h._windows.values())


def test_select_then_return_coalesced_roster_never_retains_old_system(runtime):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    primary = runtime.made[0]
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._apply_metadata()
    h.apply_roster(RosterSnapshot(2, (client(None),)))
    returned = client(serial=3)
    h.apply_roster(RosterSnapshot(3, (returned,)))
    h._apply_pending_roster(None)
    assert h._windows["Alice"] is primary
    assert primary._system_name is None
    assert h.metadata_sessions() == frozenset({returned.session})
    h.submit_metadata(1, {c.session: "LATE", returned.session: "NEW"})
    h._apply_metadata()
    assert primary._system_name == "NEW"


@pytest.mark.parametrize("change", [{"hwnd": 17}, {"pid": 102}])
def test_physical_replacement_recreates_preview_preserving_live_geometry(
    runtime, change
):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    old = runtime.made[0]
    old.rect = geometry.Rect(25, 40, 444, 333)
    runtime.roster(2, client(serial=2, **change))
    new = h._windows["Alice"]
    assert new is not old
    assert old.hwnd is None
    assert new.rect == geometry.Rect(25, 40, 444, 333)
    assert (new.client.hwnd, new.client.pid) == (
        change.get("hwnd", 16),
        change.get("pid", 101),
    )
    assert runtime.closed == [1000]  # Never the actual EVE HWND.


def test_stale_roster_cannot_reauthorize_departed_session_during_reconcile(
    runtime, monkeypatch
):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    reconcile = h._reconcile_roster

    def admit_newer(libs, snapshot):
        h.apply_roster(RosterSnapshot(3, ()))
        h.apply_roster(RosterSnapshot(1, (c,)))
        reconcile(libs, snapshot)
        h.submit_metadata(1, {c.session: "LATE"})
        h._apply_metadata()

    monkeypatch.setattr(h, "_reconcile_roster", admit_newer)
    runtime.roster(2, c)
    assert not h.metadata_sessions()
    assert runtime.made[0]._system_name is None
    assert h._pending_roster.generation == 3


def test_callback_is_detached_outside_lock_and_reports_availability(runtime):
    h, seen = runtime.host, []

    def changed(revision, sessions, available):
        assert h._lock.acquire(blocking=False)
        h._lock.release()
        assert isinstance(sessions, frozenset)
        seen.append((revision, sessions, available))

    h.set_metadata_callback(changed)
    c = client()
    runtime.roster(1, c)
    runtime.roster(2, c)
    h.apply_roster(RosterSnapshot(3, ()))
    assert [(sessions, available) for _, sessions, available in seen] == [
        (frozenset(), True),
        (frozenset({c.session}), True),
        (frozenset(), True),
    ]
    h.close_metadata_admission()
    assert seen[-1][1:] == (frozenset(), False)
    assert [n for n, _, _ in seen] == sorted({n for n, _, _ in seen})
    h.set_metadata_callback(None)
    h.submit_metadata(1, {c.session: "LATE"})
    h.set_metadata_generation(2)
    h.apply_roster(RosterSnapshot(4, (c,)))
    h._apply_pending_roster(None)
    assert not h.metadata_sessions()
    assert runtime.made[0]._system_name is None


def test_teardown_fences_metadata_before_any_native_destruction(runtime):
    h, c = runtime.host, client()
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._apply_metadata()
    seen = []
    h.set_metadata_callback(
        lambda revision, sessions, available: seen.append((sessions, available))
    )
    destroy = runtime.native.user32.DestroyWindow

    def late(hwnd):
        assert not h.metadata_sessions()
        h.submit_metadata(1, {c.session: "LATE"})
        destroy(hwnd)

    runtime.native.user32.DestroyWindow = late
    h._teardown(runtime.native)
    assert seen[-1] == (frozenset(), False)
    assert h._metadata_values == {}
    assert not h.metadata_available()


def test_ingress_does_not_wait_for_pump_render_and_revokes_its_captured_value(
    runtime, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    h, c = runtime.host, client()
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    win = runtime.made[0]
    setter = win.set_system_name

    def blocked(text):
        if text == "OLD":
            entered.set()
            assert release.wait(5)
        setter(text)

    monkeypatch.setattr(win, "set_system_name", blocked)
    with ThreadPoolExecutor(max_workers=2) as threads:
        painting = threads.submit(h._apply_metadata)
        try:
            assert entered.wait(5)
            threads.submit(h.apply_roster, RosterSnapshot(2, ())).result(5)
            threads.submit(h.submit_metadata, 1, {c.session: "LATE"}).result(5)
            assert not h.metadata_sessions()
        finally:
            release.set()
        painting.result(5)
    assert win._system_name is None


def test_generation_change_during_label_application_cannot_leave_stale_text(
    runtime, monkeypatch
):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    win = runtime.made[0]
    setter = win.set_system_name

    def reconfigure(text):
        if text == "OLD":
            h.set_metadata_generation(2)
        setter(text)

    monkeypatch.setattr(win, "set_system_name", reconfigure)
    h._apply_metadata()
    assert win._system_name is None


def test_metadata_does_not_consume_custom_alert_priority_mailbox(runtime):
    h, c = runtime.host, client()
    runtime.roster(1, c)
    h.raise_alert("Alice", "custom", {"rule_id": "test", "generation": 3})
    queued = list(h._pending_alerts)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "HOME"})
    h._apply_metadata()
    assert h._pending_alerts == queued
    assert h._crop_epoch == 0


def test_expiry_during_label_application_does_not_leave_old_text(runtime, monkeypatch):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    win = runtime.made[0]
    setter = win.set_system_name

    def expire(text):
        if text == "OLD":
            h.submit_metadata(1, {c.session: None})
        setter(text)

    monkeypatch.setattr(win, "set_system_name", expire)
    h._apply_metadata()
    assert win._system_name is None


def test_same_native_ids_new_session_refreshes_thumbnail_without_moving_preview(
    runtime,
):
    from tests.test_preview_thumbnail import FakeDwm

    c, h = client(), runtime.host
    runtime.native.dwmapi = FakeDwm()
    runtime.roster(1, c)
    win = runtime.made[0]
    old = window.Thumbnail.register(runtime.native, win.hwnd, c.hwnd)
    win._thumb = old
    rect = win.rect
    runtime.roster(2, client(serial=2))
    assert h._windows["Alice"] is win
    assert win.rect == rect
    assert win._thumb is not old
    assert len(runtime.native.dwmapi.unregistered) == 1
    assert win._thumb._src_hwnd == c.hwnd


def test_roster_drains_do_not_spend_a_metadata_signal_still_queued(runtime):
    c, h = client(), runtime.host
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    runtime.roster(2, c)
    h.submit_metadata(1, {c.session: "NEW"})
    runtime.roster(3, c)
    assert runtime.posted.count(host.win32.WM_APP_METADATA) == 1
    h._host_proc(h._hwnd, host.win32.WM_APP_METADATA, 0, 0)
    assert runtime.made[0]._system_name == "NEW"


def test_restarted_host_waits_for_a_new_worker_generation(runtime):
    h, c = runtime.host, client()
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._teardown(runtime.native)
    # Model a subsequent pump start, with discovery retaining the same session.
    h._stopping = False
    h._hwnd = 999
    h._notify_metadata()
    runtime.roster(2, c)
    h.submit_metadata(1, {c.session: "LATE FROM OLD RUNTIME"})
    h._apply_metadata()
    assert h._windows["Alice"]._system_name is None
    h.set_metadata_generation(2)
    h.submit_metadata(2, {c.session: "NEW"})
    h._apply_metadata()
    assert h._windows["Alice"]._system_name == "NEW"


def test_callback_failure_does_not_kill_roster_or_native_reconciliation(
    runtime, caplog
):
    h = runtime.host

    def bad_callback(*args):
        raise RuntimeError("bad consumer")

    h.set_metadata_callback(bad_callback)
    runtime.roster(1, client())
    assert h.metadata_sessions() == frozenset({client().session})
    assert "Metadata roster callback raised" in caplog.text


def test_close_clears_visible_metadata_and_refuses_late_publications(runtime):
    h, c = runtime.host, client()
    runtime.roster(1, c)
    h.set_metadata_generation(1)
    h.submit_metadata(1, {c.session: "OLD"})
    h._apply_metadata()
    h.close_metadata_admission()
    h.submit_metadata(1, {c.session: "LATE"})
    h._apply_metadata()
    assert runtime.made[0]._system_name is None
    assert not h.metadata_available()
