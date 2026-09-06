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
    ],
    "gdi32": [
        "CreateDIBSection",
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
    ],
    "kernel32": ["GetModuleHandleW", "GetCurrentThreadId", "GetCurrentProcessId"],
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
        "SetCapture",
        "GetCapture",
        "CreatePopupMenu",
        "SetTimer",
        "SetWinEventHook",
        "SetThreadDpiAwarenessContext",
        "DispatchMessageW",
    ],
    "gdi32": ["CreateDIBSection", "CreateCompatibleDC", "SelectObject"],
    "kernel32": ["GetModuleHandleW"],
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


def test_crop_menu_and_capture_declarations_with_injected_libraries(monkeypatch):
    """Exercise bind on Linux without loading any DLL or touching its cache."""
    from ctypes import wintypes
    from types import SimpleNamespace

    class Library:
        def __getattr__(self, name):
            fn = SimpleNamespace(argtypes=None, restype=None)
            setattr(self, name, fn)
            return fn

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: Library(), raising=False)
    for name in ("wndproc_type", "winevent_proc_type", "monitor_enum_proc_type"):
        monkeypatch.setattr(win32, name, lambda: ctypes.c_void_p)
    user32 = win32.bind.__wrapped__().user32
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


def test_crop_message_and_menu_constants_match_native_declarations():
    assert win32.WM_CAPTURECHANGED == 0x0215
    assert win32.WM_CANCELMODE == 0x001F
    assert win32.TPM_NONOTIFY | win32.TPM_RETURNCMD == 0x0180
    assert win32.MF_STRING == 0
