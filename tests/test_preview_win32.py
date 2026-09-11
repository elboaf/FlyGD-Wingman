"""The declaration guard.

Undeclared ctypes functions marshal pointer-sized values as 32-bit ints.
The failure is a truncated handle or an OverflowError raised *inside* a
callback, where it is reported via sys.unraisablehook and lost. Both
evewindows.py:36-44 and ui/chrome.py:123-131 document this; design
probing hit it twice, on DefWindowProcW and on SelectObject. A test that
enumerates the declarations is cheaper than finding it again.

Skipped on platform, NOT via importorskip. The module imports fine on
Linux by design (structs and constants at import time, DLLs only inside
bind()), so importorskip would not skip -- the test would run and fail in
CI on the bind() call.
"""

import ctypes
import sys

import pytest

from wingman.preview import win32

native_only = pytest.mark.skipif(
    sys.platform != "win32", reason="binds user32/gdi32/dwmapi"
)

REQUIRED = {
    "user32": [
        "CreateWindowExW",
        "DestroyWindow",
        "DefWindowProcW",
        "RegisterClassW",
        "ShowWindow",
        "SetWindowPos",
        "UpdateLayeredWindow",
        "SetLayeredWindowAttributes",
        "GetMessageW",
        "DispatchMessageW",
        "TranslateMessage",
        "PostMessageW",
        "PostQuitMessage",
        "GetDC",
        "ReleaseDC",
        "GetClientRect",
        "ClientToScreen",
        "ScreenToClient",
        "FillRect",
        "DrawTextW",
        "GetDpiForWindow",
        "AdjustWindowRectExForDpi",
        "MonitorFromWindow",
        "IsDialogMessageW",
        "SendDlgItemMessageW",
        "GetFocus",
        "EnableWindow",
        "SetWindowTextW",
        "InvalidateRect",
        "LoadCursorW",
        "SetCapture",
        "GetCapture",
        "ReleaseCapture",
        "CreatePopupMenu",
        "AppendMenuW",
        "TrackPopupMenuEx",
        "DestroyMenu",
        "GetCursorPos",
        "SetForegroundWindow",
        "SetFocus",
        "GetForegroundWindow",
        "AttachThreadInput",
        "IsIconic",
        "ShowWindowAsync",
        "GetWindowThreadProcessId",
        "SetTimer",
        "KillTimer",
        "SetWinEventHook",
        "UnhookWinEvent",
        "RegisterHotKey",
        "UnregisterHotKey",
        "SetThreadDpiAwarenessContext",
        "EnumDisplayMonitors",
        "GetMonitorInfoW",
        "EnumWindows",
        "IsWindow",
        "IsWindowVisible",
        "IsHungAppWindow",
        "GetWindowTextW",
        "GetClassNameW",
        "GetWindowDisplayAffinity",
    ],
    "gdi32": [
        "CreateDIBSection",
        "CreateFontW",
        "GetStockObject",
        "SetDCBrushColor",
        "SetTextColor",
        "SetBkColor",
        "SetBkMode",
        "SaveDC",
        "RestoreDC",
        "CreateCompatibleDC",
        "SelectObject",
        "DeleteObject",
        "DeleteDC",
    ],
    "dwmapi": [
        "DwmRegisterThumbnail",
        "DwmUnregisterThumbnail",
        "DwmUpdateThumbnailProperties",
        "DwmIsCompositionEnabled",
        "DwmGetWindowAttribute",
    ],
    "kernel32": [
        "GetModuleHandleW",
        "GetCurrentThreadId",
        "GetCurrentProcessId",
        "OpenProcess",
        "QueryFullProcessImageNameW",
        "GetProcessTimes",
        "CloseHandle",
    ],
}


# Functions whose RETURN value is pointer-sized. ctypes defaults restype
# to c_int, which truncates these on 64-bit Windows -- and that is the half
# that actually bit during design probing, twice: SelectObject and
# CreateDIBSection both hand back handles, and DefWindowProcW an LRESULT.
# Checking argtypes alone would have caught neither.
POINTER_SIZED_RETURNS = {
    "user32": [
        "CreateWindowExW",
        "DefWindowProcW",
        "GetDC",
        "GetForegroundWindow",
        "SetFocus",
        "GetFocus",
        "SendDlgItemMessageW",
        "MonitorFromWindow",
        "SetCapture",
        "GetCapture",
        "CreatePopupMenu",
        "SetTimer",
        "SetWinEventHook",
        "SetThreadDpiAwarenessContext",
        "DispatchMessageW",
    ],
    "gdi32": [
        "CreateDIBSection",
        "CreateCompatibleDC",
        "SelectObject",
        "CreateFontW",
        "GetStockObject",
    ],
    "kernel32": ["GetModuleHandleW", "OpenProcess"],
}

# Anything at least as wide as a pointer is acceptable; the failure being
# guarded against is specifically the c_int default.
_WIDE = (ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_size_t)


@native_only
def test_every_used_function_is_declared():
    libs = win32.bind()
    missing = []
    for lib_name, funcs in REQUIRED.items():
        lib = getattr(libs, lib_name)
        for fn in funcs:
            f = getattr(lib, fn, None)
            if f is None:
                missing.append(f"{lib_name}.{fn} absent")
            elif f.argtypes is None:
                missing.append(f"{lib_name}.{fn} has no argtypes")
    assert not missing, "\n".join(missing)


@native_only
def test_pointer_sized_returns_are_not_left_at_the_c_int_default():
    """The other half of the guard.

    A missing restype does not raise: the call succeeds and hands back a
    truncated handle, which fails later somewhere unrelated. That is
    exactly how it presented during probing.
    """
    libs = win32.bind()
    bad = []
    for lib_name, funcs in POINTER_SIZED_RETURNS.items():
        lib = getattr(libs, lib_name)
        for fn in funcs:
            restype = getattr(lib, fn).restype
            if restype is ctypes.c_int or restype is None:
                bad.append(f"{lib_name}.{fn} restype is {restype!r}")
            elif not (
                restype in _WIDE
                or ctypes.sizeof(restype) >= ctypes.sizeof(ctypes.c_void_p)
            ):
                bad.append(f"{lib_name}.{fn} restype {restype!r} is too narrow")
    assert not bad, "\n".join(bad)


@native_only
def test_bind_is_cached_so_declarations_are_applied_once():
    assert win32.bind() is win32.bind()


@pytest.fixture
def injected_libraries(monkeypatch):
    """Exercise bind on Linux without loading any DLL or touching its cache."""
    from types import SimpleNamespace

    class Library:
        def __getattr__(self, name):
            fn = SimpleNamespace(argtypes=None, restype=None)
            setattr(self, name, fn)
            return fn

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: Library(), raising=False)
    for name in (
        "wndproc_type",
        "winevent_proc_type",
        "monitor_enum_proc_type",
        "enum_windows_proc_type",
    ):
        monkeypatch.setattr(win32, name, lambda: ctypes.c_void_p)
    return win32.bind.__wrapped__()


def test_crop_menu_and_capture_declarations_with_injected_libraries(injected_libraries):
    from ctypes import wintypes

    user32 = injected_libraries.user32
    signatures = {
        "GetCapture": (wintypes.HWND, []),
        "CreatePopupMenu": (wintypes.HMENU, []),
        "DestroyMenu": (wintypes.BOOL, [wintypes.HMENU]),
        "AppendMenuW": (
            wintypes.BOOL,
            [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR],
        ),
        "TrackPopupMenuEx": (
            wintypes.BOOL,
            [
                wintypes.HMENU,
                wintypes.UINT,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.HWND,
                ctypes.c_void_p,
            ],
        ),
    }
    for name, (result, args) in signatures.items():
        fn = getattr(user32, name)
        assert fn.restype is result, name
        assert fn.argtypes == args, name
    assert user32.TrackPopupMenuEx.restype(257).value == 257


def test_picker_declarations_with_injected_libraries(injected_libraries):
    from ctypes import wintypes

    libs = injected_libraries
    H, B, U, D = wintypes.HWND, wintypes.BOOL, wintypes.UINT, wintypes.DWORD
    signatures = {
        "ClientToScreen": (B, [H, ctypes.POINTER(win32.POINT)]),
        "ScreenToClient": (B, [H, ctypes.POINTER(win32.POINT)]),
        "FillRect": (
            ctypes.c_int,
            [wintypes.HDC, ctypes.POINTER(win32.RECT), wintypes.HBRUSH],
        ),
        "DrawTextW": (
            ctypes.c_int,
            [
                wintypes.HDC,
                wintypes.LPCWSTR,
                ctypes.c_int,
                ctypes.POINTER(win32.RECT),
                U,
            ],
        ),
        "GetDpiForWindow": (U, [H]),
        "AdjustWindowRectExForDpi": (B, [ctypes.POINTER(win32.RECT), D, B, D, U]),
        "MonitorFromWindow": (wintypes.HMONITOR, [H, D]),
        "IsDialogMessageW": (B, [H, ctypes.POINTER(wintypes.MSG)]),
        "SendDlgItemMessageW": (
            win32.LRESULT,
            [H, ctypes.c_int, U, win32.WPARAM, win32.LPARAM],
        ),
        "GetFocus": (H, []),
        "EnableWindow": (B, [H, B]),
        "SetWindowTextW": (B, [H, wintypes.LPCWSTR]),
    }
    for name, (result, args) in signatures.items():
        fn = getattr(libs.user32, name)
        assert fn.restype is result, name
        assert fn.argtypes == args, name
    for name in ("SetDCBrushColor", "SetTextColor", "SetBkColor"):
        fn = getattr(libs.gdi32, name)
        assert fn.restype is wintypes.COLORREF
        assert fn.argtypes == [wintypes.HDC, wintypes.COLORREF]
    for name, result, args in (
        ("SetBkMode", ctypes.c_int, [wintypes.HDC, ctypes.c_int]),
        ("SaveDC", ctypes.c_int, [wintypes.HDC]),
        ("RestoreDC", B, [wintypes.HDC, ctypes.c_int]),
    ):
        fn = getattr(libs.gdi32, name)
        assert fn.restype is result
        assert fn.argtypes == args
    assert libs.gdi32.CreateFontW.restype is wintypes.HFONT
    assert libs.gdi32.CreateFontW.argtypes == [ctypes.c_int] * 5 + [D] * 8 + [
        wintypes.LPCWSTR
    ]
    assert libs.gdi32.GetStockObject.restype is wintypes.HGDIOBJ
    assert libs.gdi32.GetStockObject.argtypes == [ctypes.c_int]
    assert ctypes.sizeof(libs.user32.SendDlgItemMessageW.restype) == ctypes.sizeof(
        ctypes.c_void_p
    )


def test_source_query_declarations_with_injected_libraries(injected_libraries):
    from ctypes import wintypes

    libs = injected_libraries
    H, B, D = wintypes.HWND, wintypes.BOOL, wintypes.DWORD
    signatures = {
        "user32": {
            "EnumWindows": (B, [ctypes.c_void_p, win32.LPARAM]),
            "IsWindow": (B, [H]),
            "IsWindowVisible": (B, [H]),
            "IsHungAppWindow": (B, [H]),
            "GetWindowThreadProcessId": (D, [H, ctypes.POINTER(D)]),
            "GetWindowTextW": (ctypes.c_int, [H, wintypes.LPWSTR, ctypes.c_int]),
            "GetClassNameW": (ctypes.c_int, [H, wintypes.LPWSTR, ctypes.c_int]),
            "GetWindowDisplayAffinity": (B, [H, ctypes.POINTER(D)]),
        },
        "dwmapi": {
            "DwmGetWindowAttribute": (ctypes.c_long, [H, D, ctypes.c_void_p, D]),
        },
        "kernel32": {
            "OpenProcess": (wintypes.HANDLE, [D, B, D]),
            "QueryFullProcessImageNameW": (
                B,
                [wintypes.HANDLE, D, wintypes.LPWSTR, ctypes.POINTER(D)],
            ),
            "GetProcessTimes": (
                B,
                [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4,
            ),
            "CloseHandle": (B, [wintypes.HANDLE]),
        },
    }
    for library, functions in signatures.items():
        for name, (result, args) in functions.items():
            fn = getattr(getattr(libs, library), name)
            assert fn.restype is result, name
            assert fn.argtypes == args, name
    assert ctypes.sizeof(libs.kernel32.OpenProcess.restype) == ctypes.sizeof(
        ctypes.c_void_p
    )
    assert ctypes.sizeof(libs.user32.EnumWindows.argtypes[1]) == ctypes.sizeof(
        ctypes.c_void_p
    )


def test_source_enumeration_callback_preserves_pointer_sized_hwnd_and_context(
    monkeypatch,
):
    from ctypes import wintypes

    # Substitute only the platform calling-convention constructor; exercise the
    # production callback declaration without changing its process-wide cache.
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    callback_type = win32.enum_windows_proc_type.__wrapped__()
    assert callback_type._restype_ is wintypes.BOOL
    assert callback_type._argtypes_ == (wintypes.HWND, win32.LPARAM)
    value = 1 << (ctypes.sizeof(ctypes.c_void_p) * 8 - 2)
    received = []
    callback = callback_type(
        lambda hwnd, context: received.append((hwnd, context)) or 1
    )
    assert callback(value, value) == 1
    assert received == [(value, value)]


def test_picker_drawitem_struct_retains_pointer_sized_handles_and_item_data():
    from ctypes import wintypes

    fields = dict(win32.DRAWITEMSTRUCT._fields_)
    assert fields == {
        "CtlType": wintypes.UINT,
        "CtlID": wintypes.UINT,
        "itemID": wintypes.UINT,
        "itemAction": wintypes.UINT,
        "itemState": wintypes.UINT,
        "hwndItem": wintypes.HWND,
        "hDC": wintypes.HDC,
        "rcItem": win32.RECT,
        "itemData": ctypes.c_size_t,
    }
    value = 1 << (ctypes.sizeof(ctypes.c_void_p) * 8 - 2)
    item = win32.DRAWITEMSTRUCT()
    item.hwndItem = item.hDC = item.itemData = value
    assert item.hwndItem == item.hDC == item.itemData == value
    if sys.platform == "win32":
        assert ctypes.sizeof(item) == (
            64 if ctypes.sizeof(ctypes.c_void_p) == 8 else 48
        )


def test_crop_message_and_menu_constants_match_native_declarations():
    assert win32.WM_CAPTURECHANGED == 0x0215
    assert win32.WM_CANCELMODE == 0x001F
    assert win32.TPM_NONOTIFY | win32.TPM_RETURNCMD == 0x0180
    assert win32.MF_STRING == 0
