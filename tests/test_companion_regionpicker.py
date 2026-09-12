"""The generic picker consumes source identity, not EVE roster policy."""

from tests.test_preview_croppicker import CLIENT, MONITOR, Native
from wingman.preview import win32


def test_generic_picker_returns_binding_and_cleans_owned_bundle(monkeypatch):
    from wingman.preview import regionpicker
    from wingman.preview.companions import SourceBinding

    native = Native()
    monkeypatch.setattr(regionpicker, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(regionpicker.layered, "push", native.push)
    binding = SourceBinding(
        CLIENT.hwnd, 22, 100, r"c:\tools\mapper.exe", "Mapper", "Map", (1280, 720)
    )
    results, cancelled = [], []
    picker = regionpicker.RegionPicker.create(
        native.lib,
        binding,
        MONITOR,
        caption="Choose map region",
        on_confirm=lambda *args: results.append(args),
        on_cancel=cancelled.append,
    )
    assert picker is not None
    assert any(row[2] == "Choose map region" for row in native.created)
    picker._on_message(win32.WM_COMMAND, 100, 0)
    assert len(results) == 1 and results[0][0] == binding
    assert results[0][2] == (1280, 720)
    assert not native.windows and not native.thumbnails and not native.fonts
    assert not cancelled


def test_companion_source_resize_cancels_inflight_selection(monkeypatch):
    from wingman.preview import regionpicker
    from wingman.preview.companions import SourceBinding

    native = Native()
    monkeypatch.setattr(regionpicker, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(regionpicker.layered, "push", native.push)
    binding = SourceBinding(
        CLIENT.hwnd, 22, 100, r"c:\tools\mapper.exe", "Mapper", "Map", (1280, 720)
    )
    results, cancelled = [], []
    picker = regionpicker.RegionPicker.create(
        native.lib,
        binding,
        MONITOR,
        caption="Choose region",
        on_confirm=lambda *args: results.append(args),
        on_cancel=cancelled.append,
    )
    native.source_size = (1000, 800)
    picker._on_message(win32.WM_TIMER, 1, 0)
    assert len(cancelled) == 1 and not results
    assert not native.windows and not native.thumbnails


def test_picker_retains_failed_thumbnail_cleanup_and_defers_terminal_callback(
    monkeypatch,
):
    from wingman.preview import regionpicker
    from wingman.preview.companions import SourceBinding

    native = Native()
    monkeypatch.setattr(regionpicker, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(regionpicker.layered, "push", native.push)
    binding = SourceBinding(
        CLIENT.hwnd, 22, 100, r"c:\\tools\\mapper.exe", "Mapper", "Map", (1280, 720)
    )
    cancelled = []
    picker = regionpicker.RegionPicker.create(
        native.lib,
        binding,
        MONITOR,
        caption="Choose region",
        on_confirm=lambda *args: None,
        on_cancel=cancelled.append,
    )
    unregister = native.DwmUnregisterThumbnail
    monkeypatch.setattr(native, "DwmUnregisterThumbnail", lambda handle: 1)
    picker.cancel("cancelled")
    assert not cancelled and native.thumbnails
    assert picker.hwnd is not None
    monkeypatch.setattr(native, "DwmUnregisterThumbnail", unregister)
    from ctypes import wintypes

    picker.process_dialog_message(wintypes.MSG())
    assert cancelled == ["cancelled"]
    assert not native.windows and not native.thumbnails


def test_picker_retains_failed_destination_cleanup(monkeypatch):
    from wingman.preview import regionpicker
    from wingman.preview.companions import SourceBinding

    native = Native()
    monkeypatch.setattr(regionpicker, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(regionpicker.layered, "push", native.push)
    binding = SourceBinding(
        CLIENT.hwnd, 22, 100, r"c:\\tools\\mapper.exe", "Mapper", "Map", (1280, 720)
    )
    cancelled = []
    picker = regionpicker.RegionPicker.create(
        native.lib,
        binding,
        MONITOR,
        caption="Choose region",
        on_confirm=lambda *args: None,
        on_cancel=cancelled.append,
    )
    destroy = native.DestroyWindow
    monkeypatch.setattr(native, "DestroyWindow", lambda hwnd: False)
    monkeypatch.setattr(
        native, "IsWindow", lambda hwnd: hwnd in native.windows, raising=False
    )
    picker.cancel("cancelled")
    assert not cancelled and native.windows
    monkeypatch.setattr(native, "DestroyWindow", destroy)
    from ctypes import wintypes

    picker.process_dialog_message(wintypes.MSG())
    assert cancelled == ["cancelled"] and not native.windows
