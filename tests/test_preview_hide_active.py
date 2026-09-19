"""Actual primary/label show calls and pump policy, with OS boundaries recorded."""

from types import SimpleNamespace

import pytest

from tests.test_preview_cropcontroller import client
from tests.test_preview_window import _OverlayLibs
from wingman.preview import host, visibility, win32, window
from wingman.preview.geometry import Rect
from wingman.telemetry.model import RosterClient, RosterSnapshot


@pytest.mark.parametrize(
    "global_hidden,enabled,foreground,source,want",
    [
        (False, False, 16, 16, False),
        (False, True, 16, 16, True),
        (False, True, 16, 32, False),
        (False, True, 32, 32, True),
        (False, True, 99, 16, False),
        (False, True, 0, 0, False),
        (False, True, None, 16, False),
        (True, False, 16, 16, True),
        (True, True, 99, 16, True),
    ],
)
def test_source_mask_composes_without_nominating_unknown_foreground(
    global_hidden, enabled, foreground, source, want
):
    assert (
        visibility.should_hide_source(
            global_hidden=global_hidden,
            hide_active=enabled,
            foreground=foreground,
            source_hwnd=source,
        )
        is want
    )


@pytest.mark.parametrize(
    "global_hidden,enabled,foreground,source,want",
    [
        # Shell-cloaked source hides ahead of every focus clause, whichever
        # way they would otherwise decide (#264).
        (False, False, 16, 16, True),
        (False, True, 16, 16, True),
        (False, True, 99, 16, True),
        (True, False, 16, 16, True),
    ],
)
def test_desktop_away_source_hides_regardless_of_focus_clauses(
    global_hidden, enabled, foreground, source, want
):
    assert (
        visibility.should_hide_source(
            global_hidden=global_hidden,
            hide_active=enabled,
            foreground=foreground,
            source_hwnd=source,
            source_cloaked=True,
        )
        is want
    )


def test_uncloaked_source_defaults_to_false_without_the_keyword():
    assert not visibility.should_hide_source(
        global_hidden=False, hide_active=True, foreground=99, source_hwnd=16
    )


@pytest.fixture
def primary_host(monkeypatch):
    libs = _OverlayLibs()
    state = {"active": True, "lost": False, "foreground": 16, "pid": 9}
    shows, pid_queries = [], []
    libs.user32.ShowWindow = lambda hwnd, command: shows.append((hwnd, command))
    libs.user32.GetForegroundWindow = lambda: state["foreground"]
    libs.user32.GetClientRect = lambda *args: False
    libs.kernel32.GetCurrentProcessId = lambda: 42

    def pid(hwnd, pointer):
        pid_queries.append(hwnd)
        pointer._obj.value = state["pid"]
        return 1

    libs.user32.GetWindowThreadProcessId = pid
    monkeypatch.setattr(window, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(window.layered, "push", lambda *args: None)
    monkeypatch.setattr(
        window.Thumbnail,
        "register",
        lambda *args: SimpleNamespace(
            update=lambda *args, **kwargs: None, close=lambda: None
        ),
    )
    h = host.PreviewHost(
        on_layout_changed=lambda *args: None,
        hide_on_lost_focus=lambda: state["lost"],
        hide_active_preview=lambda: state["active"],
    )
    monkeypatch.setattr(h, "_monitors", lambda: [Rect(0, 0, 1920, 1080)])
    monkeypatch.setattr(h, "_screen", lambda: Rect(0, 0, 1920, 1080))

    def roster(generation, *clients):
        h.apply_roster(RosterSnapshot(generation, clients))
        h._apply_pending_roster(libs)

    yield SimpleNamespace(
        host=h,
        libs=libs,
        state=state,
        shows=shows,
        pid_queries=pid_queries,
        roster=roster,
    )
    for w in h._windows.values():
        w.close()


def test_active_primary_and_label_never_show_at_birth_and_switch_without_global_change(
    primary_host,
):
    r = primary_host
    r.roster(1, client(), client("Bob", hwnd=32))
    a, b = r.host._windows["Alice"], r.host._windows["Bob"]
    assert (a.hwnd, win32.SW_SHOWNOACTIVATE) not in r.shows
    assert (a._label_hwnd, win32.SW_SHOWNOACTIVATE) not in r.shows
    assert (b.hwnd, win32.SW_SHOWNOACTIVATE) in r.shows
    assert (b._label_hwnd, win32.SW_SHOWNOACTIVATE) in r.shows
    r.shows.clear()
    r.state["foreground"] = 32
    r.host._apply_selection(r.libs)
    assert (a.hwnd, win32.SW_SHOWNOACTIVATE) in r.shows
    assert (a._label_hwnd, win32.SW_SHOWNOACTIVATE) in r.shows
    assert (b.hwnd, win32.SW_HIDE) in r.shows
    assert (b._label_hwnd, win32.SW_HIDE) in r.shows
    assert r.pid_queries == []  # no ownership probe with lost-focus hiding off
    assert set(r.host._clients) == {"Alice", "Bob"}
    assert set(r.host._windows) == {"Alice", "Bob"}


@pytest.mark.parametrize(
    "active,lost,observed,fallback,pid,alice_hidden,bob_hidden",
    [
        (True, False, 32, 16, 9, False, True),
        (True, False, 0, 32, 9, False, True),
        (True, False, 0, 0, 9, False, False),
        (False, False, 32, 16, 9, False, False),
        (True, True, 32, 16, 9, False, True),
        (True, True, 99, 99, 9, True, True),
        (True, True, 99, 99, 42, False, False),
    ],
    ids=[
        "latest-nonzero",
        "zero-falls-back",
        "zero-unresolved",
        "option-off",
        "lost-focus-client",
        "lost-focus-stranger",
        "lost-focus-wingman",
    ],
)
def test_foreground_hook_during_selection_paint_controls_initial_native_shows(
    primary_host,
    monkeypatch,
    active,
    lost,
    observed,
    fallback,
    pid,
    alice_hidden,
    bob_hidden,
):
    r = primary_host
    r.state.update(active=active, lost=lost, foreground=fallback, pid=pid)
    callbacks, delivered = [], []
    # Only the Windows ABI/registration is replaced; invoke the actual installed
    # host callback from the native paint seam inside production set_selected.
    monkeypatch.setattr(win32, "winevent_proc_type", lambda: lambda cb: cb)
    monkeypatch.setattr(win32, "_KEEPALIVE", [])
    monkeypatch.setattr(
        r.libs.user32,
        "SetWinEventHook",
        lambda *args: callbacks.append(args[3]) or 99,
        raising=False,
    )
    r.host._install_hook(r.libs)
    callback = callbacks[0]
    callback(99, win32.EVENT_SYSTEM_FOREGROUND, 16, 0, 0, 0, 0)

    def paint(_libs, hwnd, *_args):
        alice = r.host._windows.get("Alice")
        if (
            alice is not None
            and hwnd == alice.hwnd
            and alice.selected
            and not delivered
        ):
            delivered.append(observed)
            callback(99, win32.EVENT_SYSTEM_FOREGROUND, observed, 0, 0, 0, 0)

    monkeypatch.setattr(window.layered, "push", paint)
    r.roster(1, client(), client("Bob", hwnd=32))
    assert delivered == [observed]
    assert r.host._foreground == observed
    for name, hidden in (("Bob", bob_hidden), ("Alice", alice_hidden)):
        preview = r.host._windows[name]
        shows = {hwnd for hwnd, mode in r.shows if mode == win32.SW_SHOWNOACTIVATE}
        expected = set() if hidden else {preview.hwnd, preview._label_hwnd}
        assert shows & {preview.hwnd, preview._label_hwnd} == expected
        assert preview.hidden is hidden
    # Visibility gets a fresh observation, not a second selection/alert pass.
    assert r.host._selected_key == r.host._focused_key == "Alice"
    assert r.host._windows["Alice"].focused
    assert not r.host._windows["Bob"].focused
    if not lost:
        assert r.pid_queries == []


def test_off_during_visibility_delivery_fences_later_primary_reveals(
    primary_host, monkeypatch
):
    r = primary_host
    r.roster(1, client(), client("Bob", hwnd=32))
    for w in r.host._windows.values():
        w.set_hidden(True)
    r.state["active"] = False
    shown = []

    def show(hwnd, mode):
        shown.append((hwnd, mode))
        r.host._eve_admitted = False
        r.host._eve_epoch += 1

    monkeypatch.setattr(r.libs.user32, "ShowWindow", show)
    second = r.host._windows["Bob"]
    r.host._foreground = 16
    r.host._apply_visibility(r.libs)
    assert (second.hwnd, win32.SW_SHOWNOACTIVATE) not in shown
    assert len(shown) == 1  # first primary show revoked authority before its label


def test_default_off_explicitly_reveals_prepared_primary_and_label(primary_host):
    r = primary_host
    r.state["active"] = False
    r.roster(1, client())
    w = r.host._windows["Alice"]
    assert r.shows.count((w.hwnd, win32.SW_SHOWNOACTIVATE)) == 1
    assert r.shows.count((w._label_hwnd, win32.SW_SHOWNOACTIVATE)) == 1


def test_hidden_primary_stays_hidden_through_metadata_labels_and_restyle(primary_host):
    r = primary_host
    r.roster(1, client())
    w = r.host._windows["Alice"]
    r.shows.clear()
    w.set_system_name("HOME")
    w.set_labels(False)
    w.set_labels(True)
    w.set_focused(True)
    w.set_selected(True)
    w.redraw(force=True)
    r.host._restyle(r.libs)
    assert not any(mode == win32.SW_SHOWNOACTIVATE for _, mode in r.shows)
    r.state["active"] = False
    r.host._restyle(r.libs)
    assert (w.hwnd, win32.SW_SHOWNOACTIVATE) in r.shows
    assert (w._label_hwnd, win32.SW_SHOWNOACTIVATE) in r.shows


@pytest.mark.parametrize(
    "lost,foreground,pid,want",
    [
        (False, 99, 9, False),
        (True, 99, 9, True),
        (True, 99, 42, False),
        (False, 0, 9, False),
        (True, 0, 9, True),
    ],
)
def test_actual_foreground_not_sticky_selection_controls_composition(
    primary_host, lost, foreground, pid, want
):
    r = primary_host
    r.roster(1, client())
    r.state.update(lost=lost, foreground=foreground, pid=pid)
    r.host._apply_selection(r.libs)
    assert r.host._selected_key == "Alice"
    assert r.host._focused_key is None
    assert r.host._windows["Alice"].hidden is want


def test_logout_anonymous_and_replacement_use_current_source(primary_host):
    r = primary_host
    r.roster(1, client())
    old = r.host._windows["Alice"]
    r.roster(2, RosterClient(16, 101, "EVE", None, None))
    assert old.hwnd is None
    anonymous = next(iter(r.host._windows.values()))
    assert anonymous.hidden
    assert (anonymous.hwnd, win32.SW_SHOWNOACTIVATE) not in r.shows
    r.roster(3, client(serial=2, hwnd=32))
    assert anonymous.hwnd is None
    assert not r.host._windows["Alice"].hidden


def _dwmapi(cloaked_by_hwnd):
    """Stub dwmapi: reports the mapped cloak value, fails for unmapped HWNDs."""

    def probe(hwnd, attribute, pointer, size):
        value = cloaked_by_hwnd.get(hwnd)
        if value is None:
            return 1
        pointer._obj.value = value
        return 0

    return SimpleNamespace(DwmGetWindowAttribute=probe)


def test_shell_cloaked_source_hides_preview_and_return_reveals_beside_source(
    primary_host,
):
    # The #264 repro with both hide options off: switching desktop spaces
    # shell-cloaks the source, and the mirror must not follow it.
    r = primary_host
    r.roster(1, client(), client("Bob", hwnd=32))
    r.state.update(active=False, lost=False)
    r.libs.dwmapi = _dwmapi({32: 2})  # DWM_CLOAKED_SHELL on Bob's source only
    r.host._apply_visibility(r.libs)
    bob, alice = r.host._windows["Bob"], r.host._windows["Alice"]
    assert bob.hidden
    assert (bob.hwnd, win32.SW_HIDE) in r.shows
    assert not alice.hidden
    r.shows.clear()
    # Back on the source's desktop: the next sweep re-shows beside it.
    r.libs.dwmapi = _dwmapi({})
    r.host._apply_visibility(r.libs)
    assert not bob.hidden
    assert (bob.hwnd, win32.SW_SHOWNOACTIVATE) in r.shows


@pytest.mark.parametrize("cloak", [None, 1], ids=["probe-fails", "app-cloak"])
def test_non_shell_cloak_never_hides_the_mirror(primary_host, cloak):
    # A failed probe degrades to shown, and DWM_CLOAKED_APP (UWP suspend) is
    # not "on another desktop". Today's behavior, preserved.
    r = primary_host
    r.roster(1, client())
    r.state.update(active=False, lost=False)
    mapped = {} if cloak is None else {16: cloak}
    r.libs.dwmapi = _dwmapi(mapped)
    r.host._apply_visibility(r.libs)
    assert not r.host._windows["Alice"].hidden


def test_sweep_without_dwmapi_binding_hides_nothing_new(primary_host):
    # Partial libs (tests, and any future binding loss) take the pre-#264 path.
    r = primary_host
    r.roster(1, client())
    r.state.update(active=False, lost=False)
    r.host._apply_visibility(r.libs)
    assert not r.host._windows["Alice"].hidden
