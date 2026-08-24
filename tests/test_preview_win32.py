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
import sys

import pytest

from obs_youtube_uploader.preview import win32

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="binds user32/gdi32/dwmapi")

REQUIRED = {
    "user32": ["CreateWindowExW", "DestroyWindow", "DefWindowProcW",
               "RegisterClassW", "ShowWindow", "SetWindowPos",
               "UpdateLayeredWindow", "SetLayeredWindowAttributes",
               "GetMessageW", "DispatchMessageW", "TranslateMessage",
               "PostMessageW", "PostQuitMessage", "GetDC", "ReleaseDC",
               "GetClientRect", "InvalidateRect", "LoadCursorW",
               "SetCapture", "ReleaseCapture", "GetCursorPos",
               "SetForegroundWindow", "GetForegroundWindow",
               "AttachThreadInput", "IsIconic", "ShowWindowAsync",
               "GetWindowThreadProcessId", "SetTimer", "KillTimer",
               "SetWinEventHook", "UnhookWinEvent",
               "RegisterHotKey", "UnregisterHotKey",
               "SetThreadDpiAwarenessContext"],
    "gdi32": ["CreateDIBSection", "CreateCompatibleDC", "SelectObject",
              "DeleteObject", "DeleteDC"],
    "dwmapi": ["DwmRegisterThumbnail", "DwmUnregisterThumbnail",
               "DwmUpdateThumbnailProperties", "DwmIsCompositionEnabled"],
    "kernel32": ["GetModuleHandleW", "GetCurrentThreadId"],
}


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


def test_bind_is_cached_so_declarations_are_applied_once():
    assert win32.bind() is win32.bind()
