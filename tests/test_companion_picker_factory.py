"""Real picker/family ownership when native creation re-enters cancellation."""

from ctypes import wintypes
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_companion_family import BINDING, TOKEN, Catalog
from tests.test_preview_croppicker import CLIENT, MONITOR, Native
from wingman.preview import regionpicker, win32
from wingman.preview.companionfamily import CompanionFamily
from wingman.preview.companions import CompanionCommand, PickerRequest


@pytest.fixture
def native(monkeypatch):
    native = Native()
    monkeypatch.setattr(regionpicker, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(regionpicker, "_PICKERS", {})
    monkeypatch.setattr(regionpicker.layered, "push", native.push)
    unregister = native.DwmUnregisterThumbnail
    yield native
    # A regression can lose the family reference. Still release the test's
    # native doubles rather than contaminating subsequent crop tests.
    native.DwmUnregisterThumbnail = unregister
    for picker in tuple(regionpicker._PICKERS.values()):
        picker.cancel("test-finished")
        picker.process_dialog_message(wintypes.MSG())
    native.assert_closed()
    assert not regionpicker._PICKERS


@pytest.mark.parametrize(
    "phase", ["picker-show", "overlay-show", "foreground", "focus"]
)
def test_family_retains_picker_after_synchronous_creation_failure_until_release(
    native, monkeypatch, phase
):
    binding = replace(BINDING, hwnd=CLIENT.hwnd)
    catalog = Catalog()
    catalog.rows = (binding,)
    events = []
    family = CompanionFamily(
        native.lib,
        SimpleNamespace(native_event=events.append),
        pump_epoch=1,
        authorized=lambda token, **kwargs: token == TOKEN,
        temporary=lambda: True,
        monitors=lambda: [MONITOR],
        catalog=catalog,
    )
    unregister = native.DwmUnregisterThumbnail
    monkeypatch.setattr(native, "DwmUnregisterThumbnail", lambda handle: 1)
    method = {
        "picker-show": "ShowWindow",
        "overlay-show": "ShowWindow",
        "foreground": "SetForegroundWindow",
        "focus": "SetFocus",
    }[phase]
    original = getattr(native, method)

    def fail_layout(hwnd, *args):
        result = original(hwnd, *args)
        if method != "ShowWindow" or phase == native.windows[hwnd] + "-show":
            native.fail = "update"
            picker = next(iter(regionpicker._PICKERS.values()))
            picker._on_message(win32.WM_SIZE, 0, 0)
        return result

    monkeypatch.setattr(native, method, fail_layout)
    family.command(
        CompanionCommand("pick-region", TOKEN, PickerRequest(binding, "Choose region"))
    )

    assert native.windows and native.thumbnails
    assert family.temporary_busy
    assert events == []  # Neither failure nor closed may falsely certify release.
    assert not family.process_dialog_message(wintypes.MSG())
    assert family.temporary_busy and events == []
    assert not family.close_native()
    assert family.temporary_busy and events == []

    monkeypatch.setattr(native, "DwmUnregisterThumbnail", unregister)
    assert family.close_native()
    native.assert_closed()
    assert not regionpicker._PICKERS
    assert not family.temporary_busy
    assert [(event.kind, event.token) for event in events] == [("closed", TOKEN)]
    assert family.close_native()
    assert not family.process_dialog_message(wintypes.MSG())
    assert len(events) == 1


@pytest.mark.parametrize("phase", ["font", "layout"])
@pytest.mark.parametrize("blocked_cleanup", [False, True])
def test_cancel_during_creation_stops_before_layout_or_thread_timer(
    native, monkeypatch, phase, blocked_cleanup
):
    binding = replace(BINDING, hwnd=CLIENT.hwnd)
    cancelled, confirmed = [], []
    unregister = native.DwmUnregisterThumbnail
    if blocked_cleanup:
        monkeypatch.setattr(native, "DwmUnregisterThumbnail", lambda handle: 1)
    read_size = native.GetClientRect
    source_reads = 0

    def get_size(hwnd, pointer):
        nonlocal source_reads
        assert hwnd is not None, "creation read a destroyed picker"
        if hwnd == CLIENT.hwnd:
            source_reads += 1
            if phase == "layout" and source_reads == 2:
                native.source_size = (1000, 800)
        return read_size(hwnd, pointer)

    monkeypatch.setattr(native, "GetClientRect", get_size)
    if phase == "font":
        send = native.SendDlgItemMessageW

        def cancel_during_font(*args):
            result = send(*args)
            next(iter(regionpicker._PICKERS.values())).cancel("creation cancelled")
            return result

        monkeypatch.setattr(native, "SendDlgItemMessageW", cancel_during_font)

    picker = regionpicker.RegionPicker.create(
        native.lib,
        binding,
        MONITOR,
        caption="Choose region",
        on_confirm=lambda *args: confirmed.append(args),
        on_cancel=cancelled.append,
    )

    assert not confirmed
    assert not any(event[0] == "timer" for event in native.events)
    assert not any(event[0] == "show" for event in native.events)
    if blocked_cleanup:
        assert picker is not None and not cancelled
        assert native.windows and native.thumbnails
        monkeypatch.setattr(native, "DwmUnregisterThumbnail", unregister)
        assert not picker.process_dialog_message(wintypes.MSG())
    else:
        assert picker is None
    assert len(cancelled) == 1
    native.assert_closed()
    assert not regionpicker._PICKERS
