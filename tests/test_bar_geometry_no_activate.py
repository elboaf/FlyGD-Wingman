"""Bar geometry must not take the OS foreground (issue #262).

pywebview's resize()/move() are SetWindowPos(HWND_TOP, ..., SWP_SHOWWINDOW)
-- no SWP_NOZORDER, no SWP_NOACTIVATE -- so every fit or fleet update made
the bar the foreground window, stealing focus from the active application
once per poll tick. Both bars now go through chrome.set_window_geometry,
which pins the flags that must never be dropped: NOZORDER and NOACTIVATE.
"""

import sys
from types import SimpleNamespace

from wingman.ui import chrome, fleetbar, sigbar


class FakeHandle:
    def __init__(self, value=0x4A4):
        self._value = value

    def ToInt64(self):
        return self._value

    def ToInt32(self):
        return self._value


def _win32_scaffold(monkeypatch, scale=1.5):
    """Patch the win32 seams the helpers use; returns the recorded calls."""
    calls = []
    user32 = SimpleNamespace(
        SetWindowPos=lambda hwnd, after, x, y, w, h, flags: (
            calls.append(
                {
                    "hwnd": hwnd,
                    "after": after,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "flags": flags,
                }
            )
            or 1
        )
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        chrome,
        "_win32",
        lambda: (user32, None, None, None, None, __import__("ctypes").wintypes),
    )
    monkeypatch.setattr(chrome, "_scale_for", lambda user32, hwnd: scale)
    return calls


class _HwndWindow:
    """Just enough native for the helpers' HWND reads."""

    def __init__(self):
        self.native = SimpleNamespace(Handle=FakeHandle())
        self.resized = []
        self.moved = []
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

    def resize(self, width, height):
        self.resized.append((width, height))

    def move(self, x, y):
        self.moved.append((x, y))


def test_set_window_geometry_flags_never_activate_or_reorder():
    calls = []
    user32 = SimpleNamespace(
        SetWindowPos=lambda hwnd, after, x, y, w, h, flags: calls.append(flags) or 1
    )
    chrome.set_window_geometry(user32, 123, 10, 20, 300, 40, 1.0)
    flags = calls[0]
    assert flags & chrome.SWP_NOZORDER
    assert flags & chrome.SWP_NOACTIVATE
    assert flags & chrome.SWP_SHOWWINDOW


def test_set_window_geometry_partial_axes_add_nomove_or_nosize():
    calls = []
    user32 = SimpleNamespace(
        SetWindowPos=lambda hwnd, after, x, y, w, h, flags: calls.append(flags) or 1
    )
    chrome.set_window_geometry(user32, 123, None, None, 300, 40, 1.0)
    assert calls[0] & chrome.SWP_NOMOVE
    assert not calls[0] & chrome.SWP_NOSIZE
    chrome.set_window_geometry(user32, 123, 10, 20, None, None, 1.0)
    assert calls[1] & chrome.SWP_NOSIZE
    assert not calls[1] & chrome.SWP_NOMOVE


def test_sig_bar_fit_uses_native_path_without_activation(monkeypatch):
    calls = _win32_scaffold(monkeypatch, scale=1.5)
    bar = _HwndWindow()

    sigbar.resize_bar(bar, 300, 40)

    assert bar.resized == []  # pywebview's activating resize never called
    assert len(calls) == 1
    # SWP_SHOWWINDOW (64) alone is the pywebview shape; the fix is the two
    # added flags, so assert the exact word to catch a regression to it.
    # x/y are left alone on a fit, so the flags carry NOMOVE too; the exact
    # word catches a regression to pywebview's bare SWP_SHOWWINDOW (64).
    assert calls[0]["flags"] == (
        chrome.SWP_NOZORDER
        | chrome.SWP_NOACTIVATE
        | chrome.SWP_SHOWWINDOW
        | chrome.SWP_NOMOVE
    )
    assert calls[0]["w"] == 450 and calls[0]["h"] == 60  # physical, scaled


def test_sig_bar_fit_falls_back_without_a_handle(monkeypatch):
    _win32_scaffold(monkeypatch)
    bar = _HwndWindow()
    bar.native = None

    sigbar.resize_bar(bar, 300, 40)

    assert bar.resized == [(300, 40)]


def test_sig_bar_fit_off_windows_keeps_pywebview_call(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    bar = _HwndWindow()

    sigbar.resize_bar(bar, 300, 40)

    assert bar.resized == [(300, 40)]


def test_fleet_bar_geometry_uses_one_native_call(monkeypatch):
    calls = _win32_scaffold(monkeypatch, scale=2.0)
    bar = _HwndWindow()

    fleetbar.apply_geometry(bar, 15, 25, 300, 90)

    assert bar.resized == [] and bar.moved == []
    assert len(calls) == 1
    assert calls[0]["flags"] == (
        chrome.SWP_NOZORDER | chrome.SWP_NOACTIVATE | chrome.SWP_SHOWWINDOW
    )
    assert (calls[0]["x"], calls[0]["y"]) == (30, 50)
    assert (calls[0]["w"], calls[0]["h"]) == (600, 180)


def test_fleet_bar_unchanged_geometry_sends_no_size_or_move(monkeypatch):
    calls = _win32_scaffold(monkeypatch)
    bar = _HwndWindow()

    fleetbar.apply_geometry(bar, 0, 0, 0, 0)  # matches the double's defaults

    assert calls[0]["flags"] & chrome.SWP_NOMOVE
    assert calls[0]["flags"] & chrome.SWP_NOSIZE


def test_fleet_bar_geometry_falls_back_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    bar = _HwndWindow()

    fleetbar.apply_geometry(bar, 15, 25, 300, 90)

    assert bar.resized == [(300, 90)]
    assert bar.moved == [(15, 25)]
