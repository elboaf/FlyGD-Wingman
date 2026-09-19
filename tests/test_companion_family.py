"""Pump policy against native doubles: real selection/rebind ownership decisions."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from wingman.preview.companions import (
    CompanionCommand,
    CompanionDefinition,
    CompanionRegion,
    CompanionSpec,
    CompanionToken,
    PickerRequest,
    SourceBinding,
    SourceDescriptor,
)
from wingman.preview.layout import Rect
from wingman.preview.runtime import SelectionLease

BINDING = SourceBinding(
    10, 20, 42, r"c:\tools\browser.exe", "Browser", "Mapper", (1280, 720)
)
DEFINITION = CompanionDefinition(
    1,
    "11111111111141118111111111111111",
    "Map",
    True,
    "whole",
    SourceDescriptor(
        BINDING.executable_path, "browser.exe", "Browser", "Mapper", "exact", "Mapper"
    ),
    Rect(50, 60, 320, 180),
    None,
)
TOKEN = CompanionToken(1, DEFINITION.id, 1, 2, 1, SelectionLease(1, 1))


class Catalog:
    def __init__(self):
        self.rows = (BINDING,)
        self.failure = False

    def enumerate(self):
        from wingman.preview.sources import SourceUnavailable

        if self.failure:
            raise SourceUnavailable("Scan incomplete")
        return self.rows

    def verify(self, binding):
        return next(
            (
                b
                for b in self.rows
                if (b.hwnd, b.pid, b.process_created, b.executable_path, b.window_class)
                == (
                    binding.hwnd,
                    binding.pid,
                    binding.process_created,
                    binding.executable_path,
                    binding.window_class,
                )
            ),
            None,
        )

    def close(self):
        return True


class Window:
    def __init__(self, binding, rect, source, callbacks):
        self.binding, self.rect, self.source_rect = binding, rect, source
        self.callbacks = callbacks
        self.hidden = True
        self.active = False
        self.selection_color = "#00c8dc"
        self.failed = None
        self.hwnd = 100
        self.close_ok = True
        self.closed = False

    def close(self):
        if self.close_ok:
            self.closed = True
            self.hwnd = None
        return self.close_ok

    def set_hidden(self, hidden, *, authorized=None):
        if hidden or authorized is None or authorized():
            self.hidden = hidden

    def set_active(self, active):
        self.active = active

    def move(self, rect):
        self.rect = rect

    def set_source_rect(self, rect):
        self.source_rect = rect


@pytest.fixture
def family():
    from wingman.preview.companionfamily import CompanionFamily

    events, windows = [], []
    catalog = Catalog()
    authority = dict(live=True, lease=True, epoch=2)
    temporary = dict(available=True)

    def authorized(token, *, promotion=False):
        return (token is None or token.pump_epoch == 1) and (
            authority["live"]
            and (token is None or token.family_epoch == authority["epoch"])
            if promotion or token is None or token.selection_lease is None
            else authority["lease"]
        )

    def create(libs, binding, rect, source, **callbacks):
        window = Window(binding, rect, source, callbacks)
        windows.append(window)
        return window

    instance = CompanionFamily(
        SimpleNamespace(),
        SimpleNamespace(native_event=events.append),
        pump_epoch=1,
        authorized=authorized,
        temporary=lambda: temporary["available"],
        monitors=lambda: [Rect(0, 0, 1920, 1080)],
        catalog=catalog,
        create_window=create,
    )
    return instance, events, windows, catalog, authority, temporary


def spec(definition=DEFINITION, generation=1, revision=0):
    return CompanionSpec(definition, generation, revision)


def test_zero_one_many_matching_and_verified_binding_retention(family):
    native, events, windows, catalog, _, _ = family
    catalog.rows = ()
    native.reconcile((spec(),), 2)
    assert events[-1].payload[0]["status"] == "waiting"
    second = replace(BINDING, hwnd=11)
    catalog.rows = (BINDING, second)
    native.scan()
    assert events[-1].payload[0]["status"] == "needs-selection" and not windows
    catalog.rows = (BINDING,)
    native.scan()
    assert len(windows) == 1 and not windows[0].hidden
    catalog.rows = (replace(BINDING, title="A changed title"), second)
    native.scan()
    assert len(windows) == 1 and not windows[0].closed
    assert events[-1].payload[0]["status"] == "live"
    catalog.rows = (replace(BINDING, process_created=43), second)
    native.scan()
    assert windows[0].closed
    assert events[-1].payload[0]["status"] == "needs-selection"


def test_prepare_hidden_then_promote_and_ack_only_after_persist_command(family):
    native, events, windows, _, _, _ = family
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    assert windows[0].hidden and events[-1].kind == "prepared"
    native.command(CompanionCommand("promote", TOKEN, None))
    assert not windows[0].hidden and events[-1].kind == "closed"


def test_reselection_failure_preserves_old_window_and_definition(family):
    native, events, windows, _, _, _ = family
    native.reconcile((spec(),), 2)
    old = windows[0]
    token = replace(TOKEN, generation=2)
    native.command(CompanionCommand("prepare", token, (DEFINITION, BINDING)))
    assert not old.closed and windows[1].hidden
    native.command(CompanionCommand("discard", token, None))
    assert not old.closed and windows[1].closed and events[-1].kind == "closed"


def test_live_lease_master_off_prepares_but_never_promotes(family):
    native, events, windows, _, authority, _ = family
    authority["live"] = False
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    assert events[-1].kind == "prepared"
    assert native.stop_live(3)
    assert not windows[0].closed
    native.command(CompanionCommand("promote", TOKEN, None))
    assert windows[0].closed and windows[0].hidden
    assert events[-1].kind == "closed"


def test_off_on_does_not_retag_old_promotion(family):
    native, _, windows, _, authority, _ = family
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    authority["epoch"] = 4
    native.command(CompanionCommand("promote", TOKEN, None))
    assert windows[0].closed and windows[0].hidden


def test_failed_cleanup_retains_temporary_slot_and_delays_ack(family):
    native, events, windows, _, _, _ = family
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    windows[0].close_ok = False
    native.command(CompanionCommand("discard", TOKEN, None))
    assert native.temporary_busy and events[-1].kind == "prepared"
    assert not native.close_native()
    windows[0].close_ok = True
    assert native.close_native()
    assert events[-1].kind == "closed"


def test_region_prepare_rejects_size_change_and_changed_identity(family):
    native, events, windows, catalog, _, _ = family
    region = CompanionRegion(0.1, 0.1, 0.5, 0.5, 1280, 720)
    definition = replace(DEFINITION, mode="region", region=region)
    catalog.rows = (replace(BINDING, client_size=(1400, 800)),)
    native.command(CompanionCommand("prepare", TOKEN, (definition, BINDING)))
    assert events[-1].kind == "failed" and not windows
    catalog.rows = (replace(BINDING, pid=99),)
    native.command(
        CompanionCommand(
            "prepare", replace(TOKEN, operation_id=2), (DEFINITION, BINDING)
        )
    )
    assert events[-1].kind == "failed" and not windows


def test_companion_selection_refuses_shared_eve_temporary(family):
    native, events, windows, _, _, temporary = family
    temporary["available"] = False
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    assert events[-1].kind == "failed" and not windows
    assert "selection" in events[-1].payload.lower()


def test_region_handoff_releases_picker_before_candidate(family):
    native, events, windows, _, _, _ = family
    picker_callbacks = {}
    native._create_picker = lambda *args, **callbacks: (
        picker_callbacks.update(callbacks)
        or SimpleNamespace(process_dialog_message=lambda msg: False)
    )
    native.command(
        CompanionCommand("pick-region", TOKEN, PickerRequest(BINDING, "Select region"))
    )
    assert native.temporary_busy and not windows
    picker_callbacks["on_confirm"](BINDING, Rect(100, 100, 400, 300), (1280, 720))
    event = events[-1]
    assert event.kind == "region-selected" and native.temporary_busy
    definition = replace(DEFINITION, mode="region", region=event.payload.region)
    native.command(CompanionCommand("prepare", TOKEN, (definition, BINDING)))
    assert len(windows) == 1 and windows[0].source_rect == Rect(100, 100, 400, 300)


def test_old_window_geometry_after_swap_cannot_authorize_new_generation(family):
    native, events, windows, _, _, _ = family
    native.reconcile((spec(),), 2)
    old = windows[0]
    old.callbacks["on_geometry"](Rect(1, 2, 320, 180))
    assert events[-1].kind == "geometry" and events[-1].payload.generation == 1
    token = replace(TOKEN, generation=2)
    native.command(CompanionCommand("prepare", token, (DEFINITION, BINDING)))
    native.command(CompanionCommand("promote", token, None))
    count = len(events)
    old.callbacks["on_geometry"](Rect(3, 4, 320, 180))
    assert len(events) == count


def test_enable_cap_never_allocates_ninth_live_relationship(family):
    native, _, windows, _, _, _ = family
    specs = tuple(spec(replace(DEFINITION, id=f"{i:032x}")) for i in range(9))
    native.reconcile(specs, 2)
    assert len(windows) == 8


def test_incomplete_scan_does_not_auto_bind(family):
    native, events, windows, catalog, _, _ = family
    catalog.failure = True
    native.reconcile((spec(),), 2)
    assert not windows and events[-1].payload[0]["status"] == "source-unavailable"


@pytest.mark.parametrize("show_ok", [True, False])
def test_promotion_retires_scan_fault_only_after_successful_show(family, show_ok):
    native, events, windows, catalog, _, _ = family
    catalog.failure = True
    native.reconcile((spec(),), 2)
    assert events[-1].payload[0]["status"] == "source-unavailable"
    catalog.failure = False
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    if not show_ok:
        windows[-1].set_hidden = lambda *args, **kwargs: None
    native.command(CompanionCommand("promote", TOKEN, None))
    status = next(
        event.payload[0] for event in reversed(events) if event.kind == "status"
    )
    if show_ok:
        assert status["status"] == "live" and status["error"] is None
        assert status["binding"] == BINDING
    else:
        assert status["status"] == "source-unavailable"
        assert status["error"] and status["binding"] is None


def test_prepared_source_loss_cancels_before_worker_save_admission(family):
    native, events, windows, catalog, _, _ = family
    native.command(CompanionCommand("prepare", TOKEN, (DEFINITION, BINDING)))
    catalog.rows = ()
    native.scan()
    assert windows[0].closed
    assert any(event.kind == "failed" and event.token == TOKEN for event in events)


def test_failed_live_cleanup_reports_stopping_not_live(family):
    native, events, windows, catalog, _, _ = family
    native.reconcile((spec(),), 2)
    windows[0].close_ok = False
    catalog.rows = ()
    native.scan()
    assert events[-1].payload[0]["status"] == "stopping"
    assert events[-1].payload[0]["binding"] is None


def test_activation_rechecks_identity_and_only_restores_foregrounds_source(family):
    native, events, windows, catalog, _, _ = family
    calls = []
    iconic = [True]
    foreground = [0]

    def foreground_window(hwnd):
        calls.append(("foreground", hwnd))
        foreground[0] = hwnd

    native._libs = SimpleNamespace(
        user32=SimpleNamespace(
            IsIconic=lambda hwnd: iconic[0],
            ShowWindowAsync=lambda hwnd, mode: calls.append(("restore", hwnd, mode)),
            SetForegroundWindow=foreground_window,
            GetForegroundWindow=lambda: foreground[0],
        ),
        kernel32=SimpleNamespace(),
    )
    native.reconcile((spec(),), 2)
    windows[0].callbacks["on_activate"]()
    assert calls == [("restore", 10, 9)]
    iconic[0] = False
    native.tick_activation()
    assert calls == [("restore", 10, 9), ("foreground", 10)]
    # Already foreground: the whole sequence is a no-op. A redundant
    # SetForegroundWindow perturbs focus into a transient that dropped
    # the ring on the second click (#258 polish follow-up).
    windows[0].callbacks["on_activate"]()
    assert calls == [("restore", 10, 9), ("foreground", 10)]
    assert not native.activation_pending
    catalog.rows = (replace(BINDING, process_created=43),)
    foreground[0] = 0  # back to unknown, so the click runs the sequence
    windows[0].callbacks["on_activate"]()
    assert len(calls) == 2  # re-verify fails before any foreground attempt
    assert events[-1].payload[0]["status"] == "source-unavailable"


def test_refused_activation_balances_thread_attachment_without_focus_or_input(family):
    native, events, windows, _, _, _ = family
    attached = []
    user = SimpleNamespace(
        IsIconic=lambda hwnd: False,
        SetForegroundWindow=lambda hwnd: False,
        GetForegroundWindow=lambda: 99,
        GetWindowThreadProcessId=lambda hwnd, pid: 20,
        AttachThreadInput=lambda source, target, value: (
            attached.append((source, target, value)) or True
        ),
    )
    native._libs = SimpleNamespace(
        user32=user, kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 5)
    )
    native.reconcile((spec(),), 2)
    windows[0].callbacks["on_activate"]()
    for _ in range(30):
        native.tick_activation()
    assert len(attached) == 50
    assert attached[::2] == [(5, 20, True)] * 25
    assert attached[1::2] == [(5, 20, False)] * 25
    assert events[-1].payload[0]["status"] == "source-unavailable"


def test_discard_picker_acknowledges_once_after_synchronous_cleanup(family):
    native, events, _, _, _, _ = family
    native._create_picker = lambda *args, **callbacks: SimpleNamespace(
        cancel=lambda reason: callbacks["on_cancel"](reason)
    )
    native.command(
        CompanionCommand("pick-region", TOKEN, PickerRequest(BINDING, "Select region"))
    )
    native.command(CompanionCommand("discard", TOKEN, None))
    assert [event.kind for event in events] == ["closed"]


def _live_companion(native, windows):
    native.reconcile((spec(),), 2)
    assert len(windows) == 1 and not windows[0].hidden
    return windows[0]


def test_lost_focus_hides_and_restores_live_companions(family):
    """#258: the companion must follow the same hide-on-lost-focus decision
    its EVE previews already obeyed, in both directions."""
    native, _, windows, _, _, _ = family
    window = _live_companion(native, windows)

    native.apply_lost_focus_hidden(True, False, 0)
    assert window.hidden
    native.apply_lost_focus_hidden(False, False, 0)
    assert not window.hidden


def test_hide_active_hides_a_companion_over_its_own_source_only(family):
    native, _, windows, _, _, _ = family
    window = _live_companion(native, windows)

    native.apply_lost_focus_hidden(False, True, 999)
    assert not window.hidden
    native.apply_lost_focus_hidden(False, True, BINDING.hwnd)
    assert window.hidden
    native.apply_lost_focus_hidden(False, True, 999)
    assert not window.hidden


def test_lost_focus_unhide_requires_live_authority(family):
    native, _, windows, _, authority, _ = family
    window = _live_companion(native, windows)
    native.apply_lost_focus_hidden(True, False, 0)
    assert window.hidden

    authority["live"] = False
    native.apply_lost_focus_hidden(False, False, 0)
    assert window.hidden


def test_lost_focus_leaves_retiring_windows_alone(family):
    native, _, windows, _, _, _ = family
    _live_companion(native, windows)
    calls = []
    windows[0].set_hidden = lambda *args, **kwargs: calls.append(args)
    native.live[DEFINITION.id].retiring = True

    native.apply_lost_focus_hidden(True, False, 0)

    assert calls == []


def test_show_on_focus_sources_respects_the_tick_and_skips_retiring(family):
    """#258 follow-up: only ticked, still-live companions nominate their
    source window to spare the wall from the lost-focus mask."""
    from dataclasses import replace as dc_replace

    native, _, _, _, _, _ = family
    native.reconcile((spec(),), 2)
    assert native.show_on_focus_sources() == (BINDING.hwnd,)
    native.live[DEFINITION.id].spec = dc_replace(
        native.live[DEFINITION.id].spec,
        definition=dc_replace(DEFINITION, show_on_focus=False),
    )
    assert native.show_on_focus_sources() == ()
    native.live[DEFINITION.id].spec = dc_replace(
        native.live[DEFINITION.id].spec, definition=DEFINITION
    )
    native.live[DEFINITION.id].retiring = True
    assert native.show_on_focus_sources() == ()


def test_lost_focus_marks_only_the_source_foreground_companion_active(family):
    """#258 polish: the ring rides the visibility sweep -- active exactly
    while this companion's source window holds the foreground, and never
    while the window itself is hidden by the hide-active clause."""
    native, _, windows, _, _, _ = family
    window = _live_companion(native, windows)

    native.apply_lost_focus_hidden(False, False, 999)
    assert not window.active
    native.apply_lost_focus_hidden(False, False, BINDING.hwnd)
    assert window.active
    native.apply_lost_focus_hidden(False, True, BINDING.hwnd)
    assert window.hidden and not window.active
    native.apply_lost_focus_hidden(False, False, 0)
    assert not window.active


def test_ring_colour_is_reread_from_the_seam_per_sweep(family):
    native, _, windows, _, _, _ = family
    window = _live_companion(native, windows)
    native._ring_color = lambda: "#abcdef"

    native.apply_lost_focus_hidden(False, False, 999)

    assert window.selection_color == "#abcdef"


def test_ring_latches_through_an_unknown_foreground(family):
    """#258 polish follow-up: a foreground of 0 -- secure desktop, a window
    being destroyed, a transient mid-activation read -- must not clear the
    ring, because nothing restores it until an unrelated foreground change
    happens by. Only another real window moves it."""
    native, _, windows, _, _, _ = family
    window = _live_companion(native, windows)

    native.apply_lost_focus_hidden(False, False, BINDING.hwnd)
    assert window.active
    native.apply_lost_focus_hidden(False, False, 0)
    assert window.active
    native.apply_lost_focus_hidden(False, False, 999)
    assert not window.active


def test_ring_active_reports_live_source_and_skips_retiring(family):
    native, _, windows, _, _, _ = family
    _live_companion(native, windows)

    assert native.ring_active(BINDING.hwnd)
    assert not native.ring_active(999)
    assert not native.ring_active(0)
    native.live[DEFINITION.id].retiring = True
    assert not native.ring_active(BINDING.hwnd)
