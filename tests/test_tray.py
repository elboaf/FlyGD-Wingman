"""Windows tray-menu placement at the native pystray boundary."""

import sys
from types import SimpleNamespace

import pytest

from wingman.ui import tray


class FakeWin32:
    WM_RBUTTONUP = 0x0205
    TPM_RIGHTALIGN = 0x0008
    TPM_BOTTOMALIGN = 0x0020
    TPM_RETURNCMD = 0x0100

    def __init__(self, *, logical_cursor=(1733, 1056), command=0):
        self.logical_cursor = logical_cursor
        self.command = command
        self.calls = []

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("foreground", hwnd))
        return True

    def GetCursorPos(self, point):
        point._obj.x, point._obj.y = self.logical_cursor
        self.calls.append(("logical-cursor", self.logical_cursor))
        return True

    def TrackPopupMenuEx(self, menu, flags, x, y, owner, params):
        self.calls.append(("popup", menu, flags, x, y, owner, params))
        return self.command


def _icon(callback=lambda _icon: None):
    return SimpleNamespace(
        _hwnd=0x101,
        _menu_hwnd=0x202,
        _menu_handle=(0x303, [callback]),
    )


def test_right_click_uses_physical_cursor_coordinates_for_native_popup():
    """Catches a regression to DPI-virtualized GetCursorPos coordinates."""
    win32 = FakeWin32(logical_cursor=(1733, 1056))

    tray.show_windows_menu(_icon(), win32=win32, physical_cursor=lambda: (3466, 2112))

    popup = next(call for call in win32.calls if call[0] == "popup")
    assert popup[3:5] == (3466, 2112)
    assert not any(call[0] == "logical-cursor" for call in win32.calls)


def test_physical_cursor_failure_falls_back_to_pystray_cursor_lookup():
    """A missing native API must leave the tray menu usable."""
    win32 = FakeWin32(logical_cursor=(-120, 940))

    tray.show_windows_menu(
        _icon(),
        win32=win32,
        physical_cursor=lambda: (_ for _ in ()).throw(OSError("unavailable")),
    )

    popup = next(call for call in win32.calls if call[0] == "popup")
    assert popup[3:5] == (-120, 940)


def test_selected_menu_command_dispatches_through_pystray_descriptor():
    """Changing placement must not change pystray's command dispatch."""
    selected = []
    icon = _icon(lambda received: selected.append(received))
    win32 = FakeWin32(command=1)

    tray.show_windows_menu(icon, win32=win32, physical_cursor=lambda: (10, 20))

    assert selected == [icon]


def test_cancelled_menu_dispatches_no_command():
    selected = []
    win32 = FakeWin32(command=0)

    tray.show_windows_menu(
        _icon(lambda received: selected.append(received)),
        win32=win32,
        physical_cursor=lambda: (10, 20),
    )

    assert selected == []


def test_invalid_positive_command_preserves_pystrays_logged_error_path():
    win32 = FakeWin32(command=2)

    with pytest.raises(IndexError):
        tray.show_windows_menu(_icon(), win32=win32, physical_cursor=lambda: (10, 20))


def test_physical_cursor_reader_bypasses_dpi_virtualization():
    class User32:
        def GetPhysicalCursorPos(self, point):
            point._obj.x, point._obj.y = 3466, 2112
            return True

    assert tray.physical_cursor_position(user32=User32()) == (3466, 2112)


def test_physical_cursor_reader_reports_native_failure():
    class User32:
        def GetPhysicalCursorPos(self, _point):
            return False

    with pytest.raises(OSError):
        tray.physical_cursor_position(user32=User32())


@pytest.mark.skipif(sys.platform != "win32", reason="pystray Windows backend")
def test_adapter_loads_against_the_pinned_pystray_windows_backend():
    from pystray import _win32 as backend

    icon_type = tray.windows_icon_class(backend.Icon, backend.win32)

    assert issubclass(icon_type, backend.Icon)
    assert backend.win32.WM_RBUTTONUP == 0x0205


def test_windows_icon_override_changes_only_right_click(monkeypatch):
    win32 = FakeWin32(command=0)
    delegated = []

    class BaseIcon:
        def _on_notify(self, wparam, lparam):
            delegated.append((wparam, lparam))
            return "base"

    icon_type = tray.windows_icon_class(BaseIcon, win32)
    icon = icon_type()
    icon._hwnd = 0x101
    icon._menu_hwnd = 0x202
    icon._menu_handle = (0x303, [])
    monkeypatch.setattr(tray, "physical_cursor_position", lambda: (10, 20))

    assert icon._on_notify(7, 0x0202) == "base"
    assert icon._on_notify(7, win32.WM_RBUTTONUP) is None
    assert delegated == [(7, 0x0202)]
    assert any(call[0] == "popup" for call in win32.calls)
