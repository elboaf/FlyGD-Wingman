"""Acknowledged working-layout writes and owned-native capture/application."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, get_ident

import pytest

from tests.test_preview_cropcontroller import client
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_runtime_review import eve_on, parked
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from tests.test_preview_store import FakeTimer
from wingman import settings
from wingman.preview import host as host_mod
from wingman.preview import layout, savedlayouts, win32, window
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry
from wingman.preview.store import LayoutStore
from wingman.telemetry.model import RosterSnapshot


@pytest.fixture
def writer(tmp_path):
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    reader = settings.committed_preview(doc)
    store = LayoutStore(lambda: settings.update(doc, path), timer=FakeTimer)
    return store, doc, path, reader


def test_failed_batch_keeps_the_prior_drag(writer, monkeypatch):
    store, doc, path, reader = writer
    store.record("Pilot", Entry(Rect(9, 2, 320, 210)))

    def fail_save(*args, **kwargs):
        raise OSError("disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(settings, "_save_locked", fail_save)
        with pytest.raises(OSError, match="disk unavailable"):
            store.transact(lambda preview: preview["excluded"].append("Pilot"))
    assert doc["preview"]["excluded"] == reader.get("excluded") == []
    store.flush()
    assert settings.load(path)["preview"]["layouts"]["Pilot"]["x"] == 9


def test_batch_cannot_overtake_an_earlier_debounce(writer, monkeypatch):
    store, doc, path, reader = writer
    entered, release, attempted = Event(), Event(), Event()
    lock = Lock()

    class ObservedLock:
        def __enter__(self):
            if entered.is_set():
                attempted.set()
            lock.acquire()

        def __exit__(self, *_):
            lock.release()

    store._write_lock = ObservedLock()
    save = settings._save_locked
    writes = []

    def blocked_save(data, path):
        writes.append(data["preview"]["layouts"]["Pilot"]["x"])
        if len(writes) == 1:
            entered.set()
            assert release.wait(5)
        save(data, path)

    monkeypatch.setattr(settings, "_save_locked", blocked_save)
    store.record("Pilot", Entry(Rect(9, 2, 320, 210)))
    mutate_entered = Event()

    def mutate(preview):
        mutate_entered.set()
        preview["layouts"]["Pilot"]["x"] = 70

    # Resolve the new seam before starting the blocked writer: RED must not
    # strand a thread when the transaction API does not exist yet.
    transact = store.transact
    with ThreadPoolExecutor(max_workers=2) as pool:
        earlier = pool.submit(store.flush)
        assert entered.wait(5)
        try:
            batch = pool.submit(transact, mutate)
            assert attempted.wait(5)
            assert not mutate_entered.is_set()
            assert reader.get("layouts") == {}
        finally:
            release.set()
        earlier.result(5)
        commit = batch.result(5)
    assert writes == [9, 70]
    assert dict(commit.layouts)["Pilot"].rect.x == 70
    assert settings.load(path)["preview"] == reader.snapshot() == doc["preview"]


@pytest.mark.parametrize("failure", ["mutation", "save"])
def test_failed_batch_restores_names_and_newer_pending_wins(
    writer, monkeypatch, failure
):
    store, doc, path, _reader = writer
    store.record("Pilot", Entry(Rect(9, 2, 320, 210)))
    store.record("Other", Entry(Rect(11, 2, 320, 210)))
    store.record_character("Old")
    store.record_character("Again")
    entered, release = Event(), Event()

    def fail():
        entered.set()
        assert release.wait(5)
        raise OSError("batch failed")

    def mutate(preview):
        preview["excluded"].append("Pilot")
        if failure == "mutation":
            fail()

    transact = store.transact
    with monkeypatch.context() as patch:
        if failure == "save":
            patch.setattr(settings, "_save_locked", lambda *args: fail())
        with ThreadPoolExecutor(max_workers=1) as pool:
            batch = pool.submit(transact, mutate)
            assert entered.wait(5)
            try:
                store.record("Pilot", Entry(Rect(90, 2, 320, 210)))
                store.record_character("New")
                store.record_character("Again")
            finally:
                release.set()
            with pytest.raises(OSError, match="batch failed"):
                batch.result(5)
    assert doc["preview"]["excluded"] == []
    assert store._timer is not None and not store._timer.cancelled
    store._timer.fire()
    preview = settings.load(path)["preview"]
    assert preview["layouts"]["Pilot"]["x"] == 90
    assert preview["layouts"]["Other"]["x"] == 11
    assert preview["seen"] == ["Again", "New", "Old"]


@pytest.mark.parametrize("failure", ["receipt", "normalization", "publication"])
def test_preparation_failure_is_before_save_and_does_not_spend_sequence(
    writer, monkeypatch, failure
):
    store, doc, path, reader = writer
    first = store.transact(lambda preview: None)
    before = path.read_bytes()
    store.record("Pilot", Entry(Rect(9, 2, 320, 210)))

    def fail(*args, **kwargs):
        raise MemoryError("prepare failed")

    with monkeypatch.context() as patch:
        if failure == "receipt":
            patch.setattr(savedlayouts, "LayoutCommit", fail)
        elif failure == "normalization":
            patch.setattr(settings, "validated_preview", fail)
        else:
            patch.setattr(settings, "_prepare_preview_publication", fail)
        with pytest.raises(MemoryError, match="prepare failed"):
            store.transact(lambda preview: preview["excluded"].append("Pilot"))
    assert path.read_bytes() == before
    assert doc["preview"] == reader.snapshot()
    second = store.transact(lambda preview: None)
    assert second.revision == first.revision + 1
    assert dict(second.layouts)["Pilot"].rect.x == 9
    assert second.excluded == ()


def test_receipt_is_normalized_detached_fixed_point(writer):
    store, doc, path, reader = writer
    store.record("Pilot", Entry(Rect(9, 2, 320, 210), True))
    snapshot = savedlayouts.SavedLayout(
        "one",
        "First",
        (savedlayouts.SavedCharacter("Pilot", True, Rect(80, 2, 320, 210)),),
    )

    def mutate(preview):
        preview["saved_layouts"] = savedlayouts.serialize((snapshot,))
        preview["excluded"] = ["Hidden", "Hidden", "hwnd:0x1"]

    commit = store.transact(mutate)
    assert commit.revision == 1
    assert commit.excluded == ("Hidden",)
    assert dict(commit.layouts) == {"Pilot": Entry(Rect(9, 2, 320, 210), True)}
    assert commit.saved == (snapshot,)
    assert doc["preview"] == reader.snapshot() == settings.load(path)["preview"]
    assert settings.validated_preview(doc["preview"]) == doc["preview"]
    with settings.update(doc, path) as live:
        live["preview"]["layouts"]["Pilot"]["x"] = 99
        live["preview"]["saved_layouts"]["items"][0]["name"] = "Later"
    assert dict(commit.layouts)["Pilot"].rect.x == 9
    assert commit.saved[0].name == "First"


@pytest.mark.parametrize("hidden_first", [False, True])
def test_apply_transaction_is_lossless_for_absent_and_null_members(
    writer, hidden_first
):
    store, _doc, path, reader = writer
    absent = [f"Offline{i}" for i in range(64)]
    store.transact(
        lambda preview: preview.update(
            excluded=(["Hidden", *absent] if hidden_first else absent)
        )
    )
    store.record("Null", Entry(Rect(9, 2, 320, 210), True))
    store.record("Absent", Entry(Rect(11, 2, 320, 210)))
    snapshot = savedlayouts.SavedLayout(
        "one",
        "Hidden",
        (
            savedlayouts.SavedCharacter("Hidden", False, None),
            savedlayouts.SavedCharacter("Null", True, None),
        ),
    )
    commit = store.transact(
        lambda preview: savedlayouts.apply_snapshot(preview, snapshot)
    )
    assert set(commit.excluded) == {*absent, "Hidden"}
    assert len(commit.excluded) == 65
    assert dict(commit.layouts)["Null"] == Entry(Rect(9, 2, 320, 210), True)
    assert dict(commit.layouts)["Absent"].rect.x == 11
    assert settings.load(path)["preview"] == reader.snapshot()


@pytest.fixture
def batch_host(runtime_pump, writer, monkeypatch):
    store, doc, path, reader = writer
    r = runtime_pump(
        start=False,
        initial={},
        layout_store=store,
        update_settings=lambda: settings.update(doc, path),
    )
    h = r.host
    monkeypatch.setattr(
        h, "_reconcile_roster", host_mod.PreviewHost._reconcile_roster.__get__(h)
    )
    monkeypatch.setattr(window, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(window.PreviewWindow, "redraw", lambda self, force=False: None)
    h._preview_snapshot = reader.snapshot
    h._excluded = lambda: reader.get("excluded")
    h._locked = lambda: reader.get("locked")
    h._restore_positions = lambda: reader.get("restore_preview_positions")
    h._show_labels = lambda: False
    h._flush_layouts = store.flush
    r.store._flush_primary = store.flush
    h._on_layout_changed = lambda key, rect, locked: store.record(
        key, Entry(rect, locked)
    )
    h._on_clients_changed = None
    r.rectangles = {}
    create = r.native.CreateWindowExW
    move = r.native.SetWindowPos

    def create_window(*args):
        hwnd = create(*args)
        if hwnd:
            r.rectangles[hwnd] = Rect(*args[4:8])
        return hwnd

    def move_window(hwnd, after, x, y, w, h, flags):
        ok = move(hwnd, after, x, y, w, h, flags)
        if ok:
            r.rectangles[hwnd] = Rect(x, y, w, h)
        return ok

    def get_rect(hwnd, ptr):
        assert get_ident() == h._thread.ident
        assert hwnd in r.native.windows and hwnd not in r.native.sources
        rect = r.rectangles[hwnd]
        ptr._obj.left, ptr._obj.top = rect.x, rect.y
        ptr._obj.right, ptr._obj.bottom = rect.right, rect.bottom
        return True

    monkeypatch.setattr(r.native, "CreateWindowExW", create_window)
    monkeypatch.setattr(r.native, "SetWindowPos", move_window)
    monkeypatch.setattr(r.native, "GetWindowRect", get_rect, raising=False)
    monkeypatch.setattr(r.native, "RegisterHotKey", lambda *args: True, raising=False)
    monkeypatch.setattr(r.native, "UnregisterHotKey", lambda *args: True, raising=False)
    r.layouts, r.doc, r.reader, r.path = store, doc, reader, path
    return r


def roster(r, generation, *entries):
    for entry in entries:
        r.native.sources.setdefault(entry.hwnd, (1280, 720))
    r.host.apply_roster(RosterSnapshot(generation, entries))
    r.call(lambda: None)


def capture(r):
    lease = r.host._layout_admission.try_begin(exclusive=True)
    assert lease is not None
    try:
        captured = r.host.capture_primary_layout(lease).result(5)
    except BaseException:
        r.host.release_primary_layout(lease)
        raise
    return lease, captured


def apply(r, lease, captured, *members):
    snapshot = savedlayouts.SavedLayout("one", "Chosen", tuple(members))
    commit = r.layouts.transact(
        lambda preview: savedlayouts.apply_snapshot(preview, snapshot)
    )
    result = r.host.apply_primary_layout(
        lease, captured, commit, {m.name: m.rect for m in members}
    ).result(5)
    return commit, result


def test_capture_actual_default_and_live_excluded_offline_detached(batch_host):
    r = batch_host
    r.layouts.transact(lambda p: p.update(excluded=["Bob"], seen=["Offline"]))
    r.host.sync_layout("Offline", Entry(Rect(700, 50, 320, 210)))
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    hwnd = r.call(lambda: r.host._windows["Alice"].hwnd)
    r.rectangles[hwnd] = Rect(600, 40, 330, 220)  # OS differs from cached/default rect.
    lease, captured = capture(r)
    try:
        assert {s.character for s in captured.sessions} == {"Alice", "Bob"}
        assert dict(captured.live_rectangles) == {"Alice": Rect(600, 40, 330, 220)}
        assert dict(captured.retained)["Offline"].rect.x == 700
        assert captured.preview == r.reader.snapshot()
        r.layouts.transact(lambda p: p.update(excluded=[]))
        assert captured.preview["excluded"] == ["Bob"]
        # Capturing untouched defaults never writes them into working geometry.
        assert r.reader.get("layouts") == {}
    finally:
        r.host.release_primary_layout(lease)


def test_checked_inclusion_refreshes_primary_metadata_roster(batch_host):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    assert r.host._metadata_previewed == frozenset((client().session,))
    lease, captured = capture(r)
    try:
        _, result = apply(
            r, lease, captured, savedlayouts.SavedCharacter("Alice", False, None)
        )
        assert result.live == "applied"
        assert r.host._metadata_previewed == frozenset()
    finally:
        r.host.release_primary_layout(lease)
    lease, captured = capture(r)
    try:
        _, result = apply(
            r, lease, captured, savedlayouts.SavedCharacter("Alice", True, None)
        )
        assert result.live == "applied"
        assert r.host._metadata_previewed == frozenset((client().session,))
    finally:
        r.host.release_primary_layout(lease)


def test_capture_refuses_failed_native_read_and_active_gesture(batch_host, monkeypatch):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    monkeypatch.setattr(r.native, "GetWindowRect", lambda *args: False)
    with pytest.raises(RuntimeError, match="Alice"):
        capture(r)
    r.call(lambda: setattr(r.host._windows["Alice"], "_mode", "move"))
    try:
        with pytest.raises(RuntimeError, match="pending Preview"):
            capture(r)
    finally:
        r.call(lambda: setattr(r.host._windows["Alice"], "_mode", None))


@pytest.mark.parametrize("enabled", [False, True])
def test_offline_capture_and_apply_never_start_or_touch_native(batch_host, enabled):
    r = batch_host
    if enabled:
        r.runtime.set_companions(True, 1)
        r.wait_state(lambda s: s.companions == "active")
    r.layouts.transact(lambda p: p.update(seen=["Offline"]))
    lease, captured = capture(r)
    try:
        commit, result = apply(
            r,
            lease,
            captured,
            savedlayouts.SavedCharacter("Offline", False, Rect(400, 50, 320, 210)),
        )
        assert not r.host.runtime_enabled
        assert r.host.is_running is enabled
        assert captured.sessions == () and captured.live_rectangles == ()
        assert result.live == "deferred"
        assert r.host.layout_entries() == dict(commit.layouts)
    finally:
        r.host.release_primary_layout(lease)


def test_noop_persisted_apply_still_moves_divergent_live_without_changing_globals(
    batch_host,
):
    r = batch_host
    target = Rect(600, 40, 330, 220)
    r.layouts.transact(
        lambda p: p.update(
            layouts=layout.serialize({"Alice": Entry(target, True)}),
            locked=["Alice"],
            restore_preview_positions=False,
        )
    )
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    alice, bob = r.call(lambda: (r.host._windows["Alice"], r.host._windows["Bob"]))
    before = r.reader.snapshot()
    bob_rect = r.rectangles[bob.hwnd]
    assert r.rectangles[alice.hwnd] != target
    lease, captured = capture(r)
    try:
        commit, result = apply(
            r, lease, captured, savedlayouts.SavedCharacter("Alice", True, target)
        )
        assert result.live == "applied"
        assert r.rectangles[alice.hwnd] == target
        assert alice.locked and r.rectangles[bob.hwnd] == bob_rect
        assert r.reader.snapshot() == before
        assert dict(commit.layouts)["Alice"].rect == target
    finally:
        r.host.release_primary_layout(lease)


def test_restore_off_reenabled_member_uses_explicit_rect_now_but_not_on_later_arrival(
    batch_host,
):
    r = batch_host
    r.layouts.transact(
        lambda p: p.update(excluded=["Alice"], restore_preview_positions=False)
    )
    eve_on(r)
    roster(r, 2, client())
    assert r.call(lambda: not r.host._windows)
    target = Rect(600, 40, 330, 220)
    lease, captured = capture(r)
    try:
        _, result = apply(
            r, lease, captured, savedlayouts.SavedCharacter("Alice", True, target)
        )
        assert result.live == "applied"
        assert r.call(lambda: r.host._windows["Alice"].rect) == target
    finally:
        r.host.release_primary_layout(lease)
    roster(r, 3)
    roster(r, 4, client(serial=2))
    assert r.call(lambda: r.host._windows["Alice"].rect) != target
    assert r.reader.get("restore_preview_positions") is False


@pytest.mark.parametrize("recorded", [False, True])
def test_null_unchanged_visibility_checks_recorded_creation_only(
    batch_host, monkeypatch, recorded
):
    r = batch_host
    eve_on(r)
    monkeypatch.setattr(r.native, "CreateWindowExW", lambda *args: 0)
    roster(r, 2, client(), client("Bob", hwnd=17))
    lease, captured = capture(r)
    try:
        member = savedlayouts.SavedCharacter(
            "Alice" if recorded else "Offline", True, None
        )
        _, result = apply(r, lease, captured, member)
        assert result.live == ("incomplete" if recorded else "applied")
        if recorded:
            assert "Alice" in result.warning and "Bob" not in result.warning
    finally:
        r.host.release_primary_layout(lease)


@pytest.mark.parametrize("failure", ["move", "remove", "hotkey"])
def test_native_failure_is_incomplete_and_retains_commit(
    batch_host, monkeypatch, failure
):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    hwnd = r.call(lambda: r.host._windows["Alice"].hwnd)
    patch = monkeypatch.context()
    with patch as p:
        if failure == "move":
            p.setattr(r.native, "SetWindowPos", lambda *args: False)
        elif failure == "remove":
            p.setattr(r.native, "DestroyWindow", lambda *args: False)
        else:
            r.host.set_hotkeys({"cycle_next": "Ctrl+F1"})
            p.setattr(r.native, "RegisterHotKey", lambda *args: False)
        try:
            commit, result = apply(
                r,
                lease,
                captured,
                savedlayouts.SavedCharacter(
                    "Alice", failure != "remove", Rect(600, 40, 330, 220)
                ),
            )
            assert result.live == "incomplete" and result.warning
            assert r.host.layout_entries() == dict(commit.layouts)
            if failure == "remove":
                assert r.call(lambda: r.host._windows["Alice"].hwnd) == hwnd
        finally:
            r.host.release_primary_layout(lease)


def test_failed_batch_removal_stays_owned_through_later_discovery(
    batch_host, monkeypatch
):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    win = r.call(lambda: r.host._windows["Alice"])
    hwnd = win.hwnd
    with monkeypatch.context() as patch:
        patch.setattr(r.native, "DestroyWindow", lambda *args: False)
        try:
            _, result = apply(
                r, lease, captured, savedlayouts.SavedCharacter("Alice", False, None)
            )
            assert result.live == "incomplete"
        finally:
            r.host.release_primary_layout(lease)
        roster(r, 3, client())
        assert r.call(lambda: r.host._windows.get("Alice")) is win
        assert hwnd in r.native.windows and win.hwnd == hwnd
    roster(r, 4, client())
    assert r.call(lambda: not r.host._windows)
    assert hwnd not in r.native.windows


def test_monitor_rescue_never_changes_preferred_geometry(batch_host):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    target = Rect(-5000, 40, 330, 220)
    try:
        commit, result = apply(
            r, lease, captured, savedlayouts.SavedCharacter("Alice", True, target)
        )
        assert result.live == "applied"
        actual = r.call(lambda: r.host._windows["Alice"].native_rect())
        assert actual.x >= 0
        assert (
            dict(commit.layouts)["Alice"].rect
            == r.host.layout_entries()["Alice"].rect
            == target
        )
        assert r.reader.get("layouts")["Alice"]["x"] == -5000
    finally:
        r.host.release_primary_layout(lease)


def test_replacement_session_never_receives_explicit_geometry(batch_host):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    try:
        roster(r, 3, client(serial=2))
        before = r.call(lambda: r.host._windows["Alice"].native_rect())
        _, result = apply(
            r,
            lease,
            captured,
            savedlayouts.SavedCharacter("Alice", True, Rect(600, 40, 330, 220)),
        )
        assert result.live == "deferred"
        assert r.call(lambda: r.host._windows["Alice"].native_rect()) == before
    finally:
        r.host.release_primary_layout(lease)


@pytest.mark.parametrize("stop", [False, True])
def test_failed_post_retains_until_pump_or_off_and_no_late_delivery(
    batch_host, monkeypatch, stop
):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    target = Rect(600, 40, 330, 220)
    commit = r.layouts.transact(
        lambda p: savedlayouts.apply_snapshot(
            p,
            savedlayouts.SavedLayout(
                "one", "Chosen", (savedlayouts.SavedCharacter("Alice", True, target),)
            ),
        )
    )
    post = r.native.PostMessageW
    with parked(r):
        monkeypatch.setattr(
            r.native,
            "PostMessageW",
            lambda hwnd, msg, wp, lp: (
                0 if msg == win32.WM_APP_PRIMARY_COMPLETE else post(hwnd, msg, wp, lp)
            ),
        )
        future = r.host.apply_primary_layout(lease, captured, commit, {"Alice": target})
        assert not future.done() and r.host._layout_admission.owns(lease)
        if stop:
            r.runtime.set_eve(False, 2)
            assert future.result(5).live == "deferred"
            r.host.release_primary_layout(lease)
    try:
        result = future.result(5)
        assert result.live == ("deferred" if stop else "applied")
    finally:
        r.host.release_primary_layout(lease)
    assert r.host._layout_admission.wait_idle(5)


def test_batch_never_paints_an_unrecorded_member(batch_host, monkeypatch):
    r = batch_host
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    lease, captured = capture(r)
    bob = r.call(lambda: r.host._windows["Bob"])

    def unwanted(*args):
        raise AssertionError("Unrecorded Bob received native presentation")

    with monkeypatch.context() as patch:
        patch.setattr(bob, "set_focused", unwanted)
        patch.setattr(bob, "set_selected", unwanted)
        patch.setattr(bob, "set_hidden", unwanted)
        try:
            _, result = apply(
                r, lease, captured, savedlayouts.SavedCharacter("Alice", True, None)
            )
            assert result.live == "applied", result.warning
        finally:
            r.host.release_primary_layout(lease)


@pytest.mark.parametrize("edge", ["off", "close", "release"])
def test_executing_native_future_cannot_release_early(batch_host, monkeypatch, edge):
    r = batch_host
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    lease, captured = capture(r)
    target = Rect(600, 40, 330, 220)
    members = (
        savedlayouts.SavedCharacter("Alice", True, target),
        savedlayouts.SavedCharacter("Bob", True, target),
    )
    commit = r.layouts.transact(
        lambda p: savedlayouts.apply_snapshot(
            p, savedlayouts.SavedLayout("one", "Chosen", members)
        )
    )
    entered, release = Event(), Event()
    move = r.native.SetWindowPos
    delivered = []
    alice = r.call(lambda: r.host._windows["Alice"].hwnd)

    def blocked(hwnd, *args):
        assert r.host._lock.acquire(blocking=False)
        r.host._lock.release()
        delivered.append(hwnd)
        if hwnd == alice:
            entered.set()
            assert release.wait(5)
        return move(hwnd, *args)

    monkeypatch.setattr(r.native, "SetWindowPos", blocked)
    future = r.host.apply_primary_layout(
        lease, captured, commit, {m.name: m.rect for m in members}
    )
    assert entered.wait(5)
    try:
        if edge == "off":
            r.runtime.set_eve(False, 2)
        elif edge == "close":
            r.host.close_admission()
        r.host.release_primary_layout(lease)
        assert not future.done()
        assert r.host._layout_admission.owns(lease)
    finally:
        release.set()
    result = future.result(5)
    assert r.host._layout_admission.wait_idle(5)
    if edge != "release":
        assert result.live == "deferred"
        assert delivered == [alice]
    assert r.host.layout_entries() == dict(commit.layouts)


def test_release_queued_apply_keeps_committed_retained_authority(batch_host):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    target = Rect(600, 40, 330, 220)
    commit = r.layouts.transact(
        lambda p: savedlayouts.apply_snapshot(
            p,
            savedlayouts.SavedLayout(
                "one", "Chosen", (savedlayouts.SavedCharacter("Alice", True, target),)
            ),
        )
    )
    with parked(r):
        future = r.host.apply_primary_layout(lease, captured, commit, {"Alice": target})
        r.host.release_primary_layout(lease)
        assert future.result(5).live == "deferred"
        assert r.host.layout_entries() == dict(commit.layouts)
    assert r.call(lambda: r.host._windows["Alice"].native_rect()) != target


def test_discovery_during_commit_gap_does_not_hide_before_checked_apply(batch_host):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    try:
        commit = r.layouts.transact(lambda p: p["excluded"].append("Alice"))
        roster(r, 3, client())
        assert r.call(lambda: "Alice" in r.host._windows)
        result = r.host.apply_primary_layout(
            lease, captured, commit, {"Alice": None}
        ).result(5)
        assert result.live == "applied"
        assert r.call(lambda: not r.host._windows)
    finally:
        r.host.release_primary_layout(lease)


def test_revocation_during_capture_fences_the_next_owned_native_read(
    batch_host, monkeypatch
):
    r = batch_host
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    read = r.native.GetWindowRect
    reads = []

    def revoked(hwnd, pointer):
        reads.append(hwnd)
        result = read(hwnd, pointer)
        r.runtime.set_eve(False, 2)
        return result

    monkeypatch.setattr(r.native, "GetWindowRect", revoked)
    with pytest.raises(RuntimeError, match="sources changed"):
        capture(r)
    assert len(reads) == 1


def test_source_replacement_during_native_capture_refuses(batch_host, monkeypatch):
    r = batch_host
    eve_on(r)
    roster(r, 2, client())
    read = r.native.GetWindowRect

    def replaced(hwnd, pointer):
        result = read(hwnd, pointer)
        r.host.apply_roster(RosterSnapshot(3, (client(serial=2),)))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(r.native, "GetWindowRect", replaced)
        with pytest.raises(RuntimeError, match="sources changed"):
            capture(r)


def test_revoked_creation_with_failed_cleanup_remains_host_owned(
    batch_host, monkeypatch
):
    r = batch_host
    eve_on(r)
    create = r.native.CreateWindowExW
    destroy = r.native.DestroyWindow
    with monkeypatch.context() as patch:

        def revoked(*args):
            hwnd = create(*args)
            if args[2] == "wingman-preview":
                r.runtime.set_eve(False, 2)
            return hwnd

        patch.setattr(r.native, "CreateWindowExW", revoked)
        patch.setattr(
            r.native,
            "DestroyWindow",
            lambda hwnd: False if hwnd != 42 else destroy(hwnd),
        )
        roster(r, 2, client())
        owned = r.call(lambda: tuple(w.hwnd for w in r.host._windows.values()))
        assert len(owned) == 1
        assert owned[0] in r.native.windows
    r.call(lambda: None)


def test_replacement_during_create_never_binds_stale_batch_source(
    batch_host, monkeypatch
):
    r = batch_host
    r.layouts.transact(lambda p: p.update(excluded=["Alice"]))
    eve_on(r)
    roster(r, 2, client())
    lease, captured = capture(r)
    create = r.native.CreateWindowExW
    register = r.native.DwmRegisterThumbnail
    old_phase = [False]
    real_create = window.PreviewWindow.create

    def inspected_create(*args, **kwargs):
        old_phase[0] = True
        try:
            return real_create(*args, **kwargs)
        finally:
            old_phase[0] = False

    def replaced(*args):
        hwnd = create(*args)
        if args[2] == "wingman-preview":
            r.host.apply_roster(RosterSnapshot(3, (client(serial=2),)))
        return hwnd

    stale_binds = []

    def register_source(*args):
        if old_phase[0]:
            stale_binds.append(args[1])
        return register(*args)

    with monkeypatch.context() as patch:
        patch.setattr(window.PreviewWindow, "create", inspected_create)
        patch.setattr(r.native, "CreateWindowExW", replaced)
        patch.setattr(r.native, "DwmRegisterThumbnail", register_source)
        try:
            _, result = apply(
                r,
                lease,
                captured,
                savedlayouts.SavedCharacter("Alice", True, Rect(600, 40, 330, 220)),
            )
            assert result.live == "deferred"
            assert stale_binds == []
        finally:
            r.host.release_primary_layout(lease)


def test_failure_then_revocation_keeps_strongest_real_failure(batch_host, monkeypatch):
    r = batch_host
    eve_on(r)
    roster(r, 2, client(), client("Bob", hwnd=17))
    lease, captured = capture(r)
    alice = r.call(lambda: r.host._windows["Alice"].hwnd)

    def move(hwnd, *args):
        if hwnd != alice:
            r.runtime.set_eve(False, 2)
        return False

    monkeypatch.setattr(r.native, "SetWindowPos", move)
    try:
        _, result = apply(
            r,
            lease,
            captured,
            savedlayouts.SavedCharacter("Alice", True, Rect(600, 40, 330, 220)),
            savedlayouts.SavedCharacter("Bob", True, Rect(600, 40, 330, 220)),
        )
        assert result.live == "incomplete"
        assert "Alice" in result.warning and "Deferred" in result.warning
    finally:
        r.host.release_primary_layout(lease)
