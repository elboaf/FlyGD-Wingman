"""Recovery uses real family, catalog, normalized regions and native windows."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_companion_family import DEFINITION, TOKEN, spec
from tests.test_companion_sources import SourceOS
from tests.test_companion_window import WindowOS
from wingman.preview import companionwindow, win32
from wingman.preview.companionfamily import CompanionFamily
from wingman.preview.companions import CompanionCommand, region_from_pixels
from wingman.preview.layout import Rect
from wingman.preview.sources import SourceCatalog


class RecoveryOS(WindowOS):
    """Only external calls are doubled; distinct handles expose owner overlap."""

    def __init__(self):
        super().__init__()
        self.created = 0
        self.registered = 0
        self.iconic = False
        self.foreground = 0
        self.libs.kernel32.GetCurrentThreadId = lambda: 5

    def CreateWindowExW(self, ex, cls, label, style, x, y, w, h, *rest):
        assert not style & win32.WS_VISIBLE
        self.created += 1
        hwnd = 100 + self.created
        self.owned.add(hwnd)
        self.calls.append(("create", hwnd))
        return hwnd

    def DwmRegisterThumbnail(self, dest, source, pointer):
        assert dest in self.owned and source == 10
        self.registered += 1
        self.calls.append(("register", dest))
        if self.fail == "register":
            return 1
        pointer._obj.value = 55 + self.registered
        self.relationships.add(pointer._obj.value)
        return 0

    def IsIconic(self, hwnd):
        assert hwnd == 10
        return self.iconic

    def ShowWindowAsync(self, hwnd, mode):
        assert hwnd == 10 and mode == win32.SW_RESTORE
        self.calls.append(("restore", hwnd))
        return True

    def SetForegroundWindow(self, hwnd):
        assert hwnd == 10
        self.calls.append(("foreground", hwnd))
        self.foreground = hwnd
        return True

    def GetForegroundWindow(self):
        return self.foreground


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.setattr(companionwindow, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(win32, "enum_windows_proc_type", lambda: lambda fn: fn)
    os = RecoveryOS()
    source = SourceOS()
    events = []
    authority = dict(enabled=True, epoch=2)
    family = CompanionFamily(
        os.libs,
        SimpleNamespace(native_event=events.append),
        pump_epoch=1,
        authorized=lambda token, **kwargs: (
            authority["enabled"] and token.family_epoch == authority["epoch"]
        ),
        temporary=lambda: True,
        monitors=lambda: [Rect(0, 0, 1920, 1080)],
        catalog=SourceCatalog(source.libs, 99),
    )
    yield SimpleNamespace(
        family=family, os=os, source=source, events=events, authority=authority
    )
    os.fail = source.fail = None
    assert family.close_native()
    assert not os.owned and not os.relationships and not source.opened


def status(r):
    return next(e.payload[0] for e in reversed(r.events) if e.kind == "status")


def region_spec():
    # A valid 10% selection becomes only 10px wide/high at a 100x100 source.
    region = region_from_pixels(Rect(128, 72, 128, 72), (1280, 720))
    return spec(replace(DEFINITION, mode="region", region=region))


def test_small_region_recovers_when_same_source_grows(recovery):
    r = recovery
    r.source.size = (100, 100)
    r.family.reconcile((region_spec(),), 2)
    assert status(r)["status"] == "source-unavailable"
    assert not r.os.owned
    for _ in range(3):
        r.family.scan()
    assert not r.os.owned

    r.source.size = (1280, 720)
    r.family.scan()
    assert status(r)["status"] == "live"
    window = r.family.live[DEFINITION.id].window
    assert not window.hidden and window.source_rect == Rect(128, 72, 128, 72)
    props = r.os.props[-1]
    assert (
        props.rcSource.left,
        props.rcSource.top,
        props.rcSource.right,
        props.rcSource.bottom,
    ) == (128, 72, 256, 144)


@pytest.mark.parametrize("restart", ["size", "family", "availability"])
def test_unchanged_capture_failure_is_bounded_but_changed_episode_retries(
    recovery, restart
):
    r = recovery
    r.os.fail = "register"
    r.family.reconcile((spec(),), 2)
    assert r.os.registered == 1
    for _ in range(5):
        r.family.scan()
    assert r.os.registered == 1
    assert status(r)["status"] == "source-unavailable"

    if restart == "size":
        r.source.size = (1600, 900)
    elif restart == "family":
        r.authority.update(enabled=False, epoch=3)
        assert r.family.stop_live(3)
        r.family.scan()
        r.authority.update(enabled=True, epoch=4)
    else:
        r.source.windows[10]["visible"] = False
        r.family.scan()
        assert status(r)["status"] == "waiting"
        r.source.windows[10]["visible"] = True
    r.family.reconcile((spec(),), r.authority["epoch"])
    assert r.os.registered == 2
    for _ in range(5):
        r.family.scan()
    assert r.os.registered == 2

    # A later genuine family restart may recover, without replacing the family.
    r.os.fail = None
    r.authority["epoch"] += 1
    r.family.reconcile((spec(),), r.authority["epoch"])
    assert status(r)["status"] == "live"
    assert r.os.registered == 3


@pytest.mark.parametrize("failure", ["unregister", "destroy"])
def test_source_recovery_retries_failed_release_before_creating_replacement(
    recovery, failure
):
    r = recovery
    r.family.reconcile((spec(),), 2)
    old = r.family.live[DEFINITION.id].window
    hwnd = old.hwnd
    r.os.fail = failure
    r.source.windows[10]["visible"] = False
    r.family.scan()
    assert old.hidden and old.hwnd == hwnd
    assert status(r)["status"] == "stopping"

    r.source.windows[10]["visible"] = True
    attempts = sum(call[0] == failure for call in r.os.calls)
    r.family.scan()
    assert sum(call[0] == failure for call in r.os.calls) > attempts
    assert r.family.live[DEFINITION.id].window is old
    assert r.os.created == 1 and status(r)["status"] == "stopping"

    r.os.fail = None
    r.family.scan()
    assert old.hwnd is None
    assert r.family.live[DEFINITION.id].window is not old
    assert r.os.created == 2 and status(r)["status"] == "live"
    assert r.os.calls.index(("destroy", hwnd)) < r.os.calls.index(("create", 102))


def test_retirement_revokes_pending_and_new_activation_before_source_recovers(recovery):
    r = recovery
    r.family.reconcile((spec(),), 2)
    live = r.family.live[DEFINITION.id]
    r.os.iconic = True
    r.family.command(CompanionCommand("activate", TOKEN, live.revision))
    assert r.family.activation_pending
    assert ("restore", 10) in r.os.calls

    r.os.fail = "unregister"
    r.source.windows[10]["visible"] = False
    r.family.scan()
    assert not r.family.activation_pending
    assert live.window.hidden
    r.source.windows[10]["visible"] = True
    r.os.iconic = False
    r.family.tick_activation()
    r.family.command(CompanionCommand("activate", TOKEN, live.revision))
    assert not r.family.activation_pending
    assert not any(call[0] == "foreground" for call in r.os.calls)
    assert status(r)["status"] == "stopping" and status(r)["binding"] is None


def test_region_loss_cannot_overwrite_retirement_status(recovery):
    r = recovery
    r.family.reconcile((region_spec(),), 2)
    old = r.family.live[DEFINITION.id].window
    r.os.fail = "unregister"
    r.source.size = (100, 100)
    r.family.scan()
    assert old.hidden and status(r)["status"] == "stopping"
    assert status(r)["binding"] is None


@pytest.mark.parametrize("retry", ["stop", "scan", "final"])
def test_retirement_continues_when_family_authority_is_off(recovery, retry):
    r = recovery
    r.family.reconcile((spec(),), 2)
    old = r.family.live[DEFINITION.id].window
    r.os.fail = "unregister"
    r.authority.update(enabled=False, epoch=3)
    close = r.family.close_native if retry == "final" else lambda: r.family.stop_live(3)
    assert not close()
    assert old.hidden
    if retry != "final":
        assert status(r)["status"] == "stopping"
    r.os.fail = None
    if retry == "scan":
        r.family.scan()
    else:
        assert close()
    assert not r.family.live and old.hwnd is None
    assert r.os.created == 1
    if retry != "final":
        assert status(r)["status"] == "off"


def test_prepared_replacement_stays_hidden_until_retiring_owner_is_released(recovery):
    r = recovery
    r.family.reconcile((spec(),), 2)
    old = r.family.live[DEFINITION.id].window
    hwnd = old.hwnd
    token = replace(TOKEN, generation=2)
    r.family.command(CompanionCommand("prepare", token, (DEFINITION, old.binding)))
    assert r.events[-1].kind == "prepared"
    assert len(r.os.owned) == 2 and len(r.os.relationships) == 2
    r.os.fail = "unregister"
    r.family.command(CompanionCommand("promote", token, None))
    r.family.scan()
    assert r.family.live[DEFINITION.id].window is old and old.hidden
    assert r.family.temporary_busy and status(r)["status"] == "stopping"
    assert ("show", 102, win32.SW_SHOWNOACTIVATE) not in r.os.calls

    r.os.fail = None
    r.family.scan()
    replacement = r.family.live[DEFINITION.id].window
    assert replacement is not old and not replacement.hidden
    assert old.hwnd is None and not r.family.temporary_busy
    assert len(r.os.owned) == 1 and len(r.os.relationships) == 1
    assert status(r)["status"] == "live"
    assert r.os.calls.index(("destroy", hwnd)) < r.os.calls.index(
        ("show", 102, win32.SW_SHOWNOACTIVATE)
    )


def test_incomplete_scan_and_matching_title_churn_do_not_reset_capture_backoff(
    recovery,
):
    r = recovery
    definition = replace(
        DEFINITION, source=replace(DEFINITION.source, title_mode="contains")
    )
    r.os.fail = "register"
    r.family.reconcile((spec(definition),), 2)
    assert r.os.registered == 1
    for i in range(3):
        r.source.fail = "enumerate"
        r.family.scan()
        assert status(r)["status"] == "source-unavailable"
        r.source.fail = None
        r.source.windows[10]["title"] = f"Mapper — document {i}"
        r.family.scan()
    assert r.os.registered == 1 and not r.os.owned


def test_hidden_window_is_not_published_as_live(recovery):
    r = recovery
    r.family.reconcile((spec(),), 2)
    r.family.live[DEFINITION.id].window.set_hidden(True)
    r.family.scan()
    assert status(r)["status"] != "live" and status(r)["binding"] is None
