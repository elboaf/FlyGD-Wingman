"""ctypes declaration surface for the preview subsystem.

Imports cleanly on Linux, which is a hard requirement (see evewindows.py:1-14
for the established pattern). That constrains the layout: `ctypes.wintypes`
and Structure definitions are fine off-Windows, but `ctypes.WINFUNCTYPE`,
`ctypes.WinDLL`, and `ctypes.windll` do not exist there. So structs and
constants live at module scope, while the callback type and every library
binding are built lazily inside functions.

EVERY function below gets argtypes and restype. That is not decoration.
Undeclared, ctypes marshals a pointer-sized value as a 32-bit int; the
result is a truncated handle, or an OverflowError raised inside a callback
where sys.unraisablehook swallows it and Windows reads the falsy return as
"stop". Design probing hit this twice -- on DefWindowProcW and again on
SelectObject -- and both times the symptom appeared nowhere near the cause.
"""

import ctypes
from ctypes import wintypes
from functools import lru_cache
from typing import NamedTuple

# --- Window styles ------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
# The name overlay only. Hit-testing on a layered window with this style
# skips the window entirely -- exactly what a label riding above the
# video wants, so every mouse gesture passes through it to the preview.
WS_EX_TRANSPARENT = 0x00000020

SW_HIDE = 0
SW_SHOWNOACTIVATE = 8
SW_RESTORE = 9

HWND_MESSAGE = -3
HWND_TOPMOST = -1

# --- Messages -----------------------------------------------------------
WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
WM_APP = 0x8000

# WM_SYSCOMMAND/SC_MINIMIZE only change a window's SHOW STATE -- the same
# transition the taskbar button and Alt-Tab already send. That is the whole
# reason this pair may reach a live EVE client while the placement surface
# a few sections down (see the removed-forever list, and
# tests/test_preview_wiring.py::
# test_the_client_placement_win32_surface_is_not_declared) may not: SetWindow-
# Placement/SetWindowPos change POSITION or SIZE, which EVE reads as a
# resolution change and rewrites its own config over -- the 2026-08-24
# incident that destroyed three characters' settings. Minimizing cannot alter
# a resolution. Do not add this pair's constants to that guard test's list.
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = 0xF020

# SMTO_ABORTIFHUNG: used with SendMessageTimeoutW below so a hung/loading
# client can't stall the send.
SMTO_ABORTIFHUNG = 0x0002

# SystemParametersInfo actions for the minimize/restore animation. The
# switch turns it off for its own duration and puts it back (host.py,
# _animation_off): a minimize plus a restore is ~200-250ms of window-zoom
# with it on, which is the bulk of the visible lag between clicking a
# preview and seeing the client -- EVE-O Preview does the same, and
# defaults to it (ThumbnailConfiguration.WindowsAnimationStyle). fWinIni
# is always 0 so the user's own preference is never written to the
# registry; it is only the live value that is toggled.
SPI_GETANIMATION = 0x0048
SPI_SETANIMATION = 0x0049

# Host commands, marshalled in from other threads.
WM_APP_SHUTDOWN = WM_APP + 1
WM_APP_SWEEP_NOW = WM_APP + 2
WM_APP_REBIND = WM_APP + 3
WM_APP_ALERT = WM_APP + 4
WM_APP_RESTYLE = WM_APP + 5
WM_APP_RESET_LAYOUTS = WM_APP + 6
WM_APP_RESIZE_ONE = WM_APP + 7
WM_APP_RESIZE_ALL = WM_APP + 8
WM_APP_APPLY_LAYOUTS = WM_APP + 9

# --- Layered windows ----------------------------------------------------
ULW_ALPHA = 0x02
LWA_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

# --- DWM thumbnails -----------------------------------------------------
DWM_TNP_RECTDESTINATION = 0x01
DWM_TNP_RECTSOURCE = 0x02
DWM_TNP_OPACITY = 0x04
DWM_TNP_VISIBLE = 0x08
DWM_TNP_SOURCECLIENTAREAONLY = 0x10

# --- WinEvent hooks -----------------------------------------------------
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

# --- DPI ----------------------------------------------------------------
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

# --- Virtual desktop metrics -------------------------------------------
# The union of every monitor, in physical pixels. Origin can be NEGATIVE:
# a monitor placed left of or above the primary starts below zero, which
# is why previews are stored in absolute virtual-desktop coordinates
# rather than anything primary-relative.
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# --- Process access -----------------------------------------------------
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", wintypes.RECT),
        ("rcSource", wintypes.RECT),
        ("opacity", ctypes.c_ubyte),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]


RECT = wintypes.RECT


class ANIMATIONINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("iMinAnimate", ctypes.c_int),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


# Every ctypes callback object ever handed to Windows, kept alive forever.
# A callback collected while Windows still holds its address takes the
# process down at the next message, and the crash lands nowhere near the
# code that created it -- the reason ui/chrome.py:117-121 does the same.
# Never pruned: an entry costs a pointer, and these live for the process.
_KEEPALIVE = []


@lru_cache(maxsize=1)
def wndproc_type():
    """WINFUNCTYPE does not exist off Windows, so build it on demand."""
    return ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)


@lru_cache(maxsize=1)
def winevent_proc_type():
    return ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )


@lru_cache(maxsize=1)
def monitor_enum_proc_type():
    return ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        LPARAM,
    )


class Libs(NamedTuple):
    user32: object
    gdi32: object
    dwmapi: object
    kernel32: object


@lru_cache(maxsize=1)
def bind() -> Libs:
    """Load the libraries and declare every function the subsystem calls.

    Cached: the declarations are global mutations of shared function
    objects, and applying them repeatedly is wasted work at best.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Called for its side effect only: wndproc_type() is @lru_cache'd, so this
    # forces the WNDPROC ctypes function-pointer *type* to be built (and any
    # failure to surface) at bind() time rather than lazily at first window
    # creation. This is the type, not a bound callback instance -- the actual
    # per-window callbacks that must outlive their window are built and kept
    # alive separately, via win32._KEEPALIVE (see host.py and window.py).
    wndproc_type()
    WINEVENTPROC = winevent_proc_type()
    MONITORENUMPROC = monitor_enum_proc_type()
    HDC, HWND, HANDLE = wintypes.HDC, wintypes.HWND, wintypes.HANDLE
    UINT, DWORD, BOOL = wintypes.UINT, wintypes.DWORD, wintypes.BOOL

    d = [
        # --- window lifecycle
        (
            user32,
            "CreateWindowExW",
            HWND,
            [
                DWORD,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                DWORD,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                HWND,
                wintypes.HMENU,
                wintypes.HINSTANCE,
                ctypes.c_void_p,
            ],
        ),
        (user32, "DestroyWindow", BOOL, [HWND]),
        (user32, "RegisterClassW", wintypes.ATOM, [ctypes.c_void_p]),
        (user32, "DefWindowProcW", LRESULT, [HWND, UINT, WPARAM, LPARAM]),
        (user32, "ShowWindow", BOOL, [HWND, ctypes.c_int]),
        (user32, "ShowWindowAsync", BOOL, [HWND, ctypes.c_int]),
        (
            user32,
            "SetWindowPos",
            BOOL,
            [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT],
        ),
        (user32, "LoadCursorW", HANDLE, [wintypes.HINSTANCE, ctypes.c_wchar_p]),
        (user32, "GetClientRect", BOOL, [HWND, ctypes.POINTER(wintypes.RECT)]),
        (user32, "GetSystemMetrics", ctypes.c_int, [ctypes.c_int]),
        # Monitor geometry. GetSystemMetrics(SM_*VIRTUALSCREEN) gives only
        # the bounding rectangle; these two give the actual displays, which
        # is what placement has to be clamped against.
        (
            user32,
            "EnumDisplayMonitors",
            BOOL,
            [HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, LPARAM],
        ),
        (
            user32,
            "GetMonitorInfoW",
            BOOL,
            [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)],
        ),
        (user32, "InvalidateRect", BOOL, [HWND, ctypes.POINTER(wintypes.RECT), BOOL]),
        # --- layered rendering
        (
            user32,
            "UpdateLayeredWindow",
            BOOL,
            [
                HWND,
                HDC,
                ctypes.POINTER(POINT),
                ctypes.POINTER(SIZE),
                HDC,
                ctypes.POINTER(POINT),
                wintypes.COLORREF,
                ctypes.POINTER(BLENDFUNCTION),
                DWORD,
            ],
        ),
        (
            user32,
            "SetLayeredWindowAttributes",
            BOOL,
            [HWND, wintypes.COLORREF, ctypes.c_ubyte, DWORD],
        ),
        (user32, "GetDC", HDC, [HWND]),
        (user32, "ReleaseDC", ctypes.c_int, [HWND, HDC]),
        # --- message pump
        (user32, "GetMessageW", ctypes.c_int, [ctypes.c_void_p, HWND, UINT, UINT]),
        (user32, "PeekMessageW", BOOL, [ctypes.c_void_p, HWND, UINT, UINT, UINT]),
        (user32, "TranslateMessage", BOOL, [ctypes.c_void_p]),
        (user32, "DispatchMessageW", LRESULT, [ctypes.c_void_p]),
        (user32, "PostMessageW", BOOL, [HWND, UINT, WPARAM, LPARAM]),
        # SendMessageTimeoutW, not the bare SendMessageW, sends WM_SYSCOMMAND/
        # SC_MINIMIZE to a client window (see the minimize constants above).
        # PostMessageW doesn't block, but it also gives no ordering against
        # the SetForegroundWindow re-activation that follows a minimize --
        # the minimize is delivered through the client's own message queue
        # while SetForegroundWindow is a direct call on Wingman's thread, so
        # nothing here guarantees the client finishes minimizing first.
        # Bare SendMessageW would fix the ordering but blocks the calling
        # thread until the target's queue processes the message; a hung or
        # still-loading EVE client would then stall the preview thread
        # indefinitely, along with the hotkey dispatch, alert pump and sweep
        # that share it. SendMessageTimeoutW + SMTO_ABORTIFHUNG gets the
        # ordering without the unbounded stall. SendMessageW is intentionally
        # never bound here -- see the assertion in test_preview_wiring.py.
        (
            user32,
            "SendMessageTimeoutW",
            LRESULT,
            [
                HWND,
                UINT,
                WPARAM,
                LPARAM,
                UINT,
                UINT,
                ctypes.POINTER(WPARAM),
            ],
        ),
        (user32, "PostQuitMessage", None, [ctypes.c_int]),
        (
            user32,
            "SetTimer",
            ctypes.c_void_p,
            [HWND, ctypes.c_void_p, UINT, ctypes.c_void_p],
        ),
        (user32, "KillTimer", BOOL, [HWND, ctypes.c_void_p]),
        # --- mouse capture
        (user32, "SetCapture", HWND, [HWND]),
        (user32, "ReleaseCapture", BOOL, []),
        (user32, "GetCursorPos", BOOL, [ctypes.POINTER(POINT)]),
        # --- focus
        (user32, "SetForegroundWindow", BOOL, [HWND]),
        (user32, "GetForegroundWindow", HWND, []),
        (user32, "AttachThreadInput", BOOL, [DWORD, DWORD, BOOL]),
        (user32, "IsIconic", BOOL, [HWND]),
        (user32, "GetWindowThreadProcessId", DWORD, [HWND, ctypes.POINTER(DWORD)]),
        # The two animation actions only (see the constants). The pvParam is
        # declared void* rather than POINTER(ANIMATIONINFO) because the
        # function is generic; the host passes byref(ANIMATIONINFO).
        (
            user32,
            "SystemParametersInfoW",
            BOOL,
            [UINT, UINT, ctypes.c_void_p, UINT],
        ),
        # --- hook, hotkeys, DPI
        (
            user32,
            "SetWinEventHook",
            HANDLE,
            [UINT, UINT, wintypes.HMODULE, WINEVENTPROC, DWORD, DWORD, UINT],
        ),
        (user32, "UnhookWinEvent", BOOL, [HANDLE]),
        (user32, "RegisterHotKey", BOOL, [HWND, ctypes.c_int, UINT, UINT]),
        (user32, "UnregisterHotKey", BOOL, [HWND, ctypes.c_int]),
        (user32, "SetThreadDpiAwarenessContext", ctypes.c_void_p, [ctypes.c_void_p]),
        # --- GDI. SelectObject and CreateDIBSection return pointer-sized
        # handles; leaving restype at c_int truncates them on 64-bit and the
        # next call raises OverflowError somewhere unrelated.
        (
            gdi32,
            "CreateDIBSection",
            wintypes.HBITMAP,
            [
                HDC,
                ctypes.POINTER(BITMAPINFO),
                UINT,
                ctypes.POINTER(ctypes.c_void_p),
                HANDLE,
                DWORD,
            ],
        ),
        (gdi32, "CreateCompatibleDC", HDC, [HDC]),
        (gdi32, "SelectObject", wintypes.HGDIOBJ, [HDC, wintypes.HGDIOBJ]),
        (gdi32, "DeleteObject", BOOL, [wintypes.HGDIOBJ]),
        (gdi32, "DeleteDC", BOOL, [HDC]),
        # --- DWM
        (
            dwmapi,
            "DwmRegisterThumbnail",
            ctypes.c_long,
            [HWND, HWND, ctypes.POINTER(HANDLE)],
        ),
        (dwmapi, "DwmUnregisterThumbnail", ctypes.c_long, [HANDLE]),
        (
            dwmapi,
            "DwmUpdateThumbnailProperties",
            ctypes.c_long,
            [HANDLE, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)],
        ),
        (dwmapi, "DwmIsCompositionEnabled", ctypes.c_long, [ctypes.POINTER(BOOL)]),
        # --- kernel32
        (kernel32, "GetModuleHandleW", wintypes.HMODULE, [wintypes.LPCWSTR]),
        (kernel32, "GetCurrentThreadId", DWORD, []),
        # Read by PreviewHost._foreground_is_ours, which resolves "is the
        # foreground one of our own windows" by process rather than by
        # handle -- the main window does not exist when the host is built.
        (kernel32, "GetCurrentProcessId", DWORD, []),
    ]
    for lib, name, restype, argtypes in d:
        fn = getattr(lib, name)
        fn.restype = restype
        fn.argtypes = argtypes

    return Libs(user32, gdi32, dwmapi, kernel32)
