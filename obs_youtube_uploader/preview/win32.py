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

SW_HIDE = 0
SW_SHOWNOACTIVATE = 8
SW_RESTORE = 9

# --- Window placement ---------------------------------------------------
# showCmd values. SW_SHOWMINIMIZED is declared for completeness and to
# make reads legible; it is deliberately never APPLIED -- restoring a
# client into a minimized window because that is how it was left gives the
# user a client that vanishes with no indication why.
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3

# Posts rather than sends. SetWindowPlacement against another process's
# window marshals to that window's owning thread and can stall while an
# EVE client is loading or hung; this is the documented escape.
WPF_ASYNCWINDOWPLACEMENT = 0x0004

# Set by Windows when a MINIMIZED window will restore to maximized. Without
# it, a client minimized from maximized reads back as windowed and comes
# back windowed.
WPF_RESTORETOMAXIMIZED = 0x0002

SPI_GETWORKAREA = 0x0030

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

# Host commands, marshalled in from other threads.
WM_APP_SHUTDOWN = WM_APP + 1
WM_APP_SWEEP_NOW = WM_APP + 2
WM_APP_REBIND = WM_APP + 3

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
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WINDOWPLACEMENT(ctypes.Structure):
    """rcNormalPosition is in WORKSPACE coordinates, not screen -- offset
    by the primary monitor's work-area origin. See placement.to_screen.

    `length` must be set before GetWindowPlacement; the call validates it.
    """
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT),
                ("showCmd", wintypes.UINT), ("ptMinPosition", POINT),
                ("ptMaxPosition", POINT),
                ("rcNormalPosition", wintypes.RECT)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD),
                ("rcDestination", wintypes.RECT),
                ("rcSource", wintypes.RECT),
                ("opacity", ctypes.c_ubyte),
                ("fVisible", wintypes.BOOL),
                ("fSourceClientAreaOnly", wintypes.BOOL)]


RECT = wintypes.RECT

# Every ctypes callback object ever handed to Windows, kept alive forever.
# A callback collected while Windows still holds its address takes the
# process down at the next message, and the crash lands nowhere near the
# code that created it -- the reason ui/chrome.py:117-121 does the same.
# Never pruned: an entry costs a pointer, and these live for the process.
_KEEPALIVE = []


@lru_cache(maxsize=1)
def wndproc_type():
    """WINFUNCTYPE does not exist off Windows, so build it on demand."""
    return ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                              WPARAM, LPARAM)


@lru_cache(maxsize=1)
def winevent_proc_type():
    return ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                              wintypes.HWND, wintypes.LONG, wintypes.LONG,
                              wintypes.DWORD, wintypes.DWORD)


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

    WNDPROC = wndproc_type()
    WINEVENTPROC = winevent_proc_type()
    HDC, HWND, HANDLE = wintypes.HDC, wintypes.HWND, wintypes.HANDLE
    UINT, DWORD, BOOL = wintypes.UINT, wintypes.DWORD, wintypes.BOOL

    d = [
        # --- window lifecycle
        (user32, "CreateWindowExW", HWND,
         [DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD, ctypes.c_int,
          ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, wintypes.HMENU,
          wintypes.HINSTANCE, ctypes.c_void_p]),
        (user32, "DestroyWindow", BOOL, [HWND]),
        (user32, "RegisterClassW", wintypes.ATOM, [ctypes.c_void_p]),
        (user32, "DefWindowProcW", LRESULT, [HWND, UINT, WPARAM, LPARAM]),
        (user32, "ShowWindow", BOOL, [HWND, ctypes.c_int]),
        (user32, "ShowWindowAsync", BOOL, [HWND, ctypes.c_int]),
        (user32, "SetWindowPos", BOOL,
         [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
          UINT]),
        (user32, "LoadCursorW", HANDLE, [wintypes.HINSTANCE, ctypes.c_wchar_p]),
        (user32, "GetClientRect", BOOL, [HWND, ctypes.POINTER(wintypes.RECT)]),
        (user32, "GetSystemMetrics", ctypes.c_int, [ctypes.c_int]),
        (user32, "InvalidateRect", BOOL,
         [HWND, ctypes.POINTER(wintypes.RECT), BOOL]),
        # --- layered rendering
        (user32, "UpdateLayeredWindow", BOOL,
         [HWND, HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE), HDC,
          ctypes.POINTER(POINT), wintypes.COLORREF,
          ctypes.POINTER(BLENDFUNCTION), DWORD]),
        (user32, "SetLayeredWindowAttributes", BOOL,
         [HWND, wintypes.COLORREF, ctypes.c_ubyte, DWORD]),
        (user32, "GetDC", HDC, [HWND]),
        (user32, "ReleaseDC", ctypes.c_int, [HWND, HDC]),
        # --- message pump
        (user32, "GetMessageW", ctypes.c_int,
         [ctypes.c_void_p, HWND, UINT, UINT]),
        (user32, "PeekMessageW", BOOL,
         [ctypes.c_void_p, HWND, UINT, UINT, UINT]),
        (user32, "TranslateMessage", BOOL, [ctypes.c_void_p]),
        (user32, "DispatchMessageW", LRESULT, [ctypes.c_void_p]),
        (user32, "PostMessageW", BOOL, [HWND, UINT, WPARAM, LPARAM]),
        (user32, "PostQuitMessage", None, [ctypes.c_int]),
        (user32, "SetTimer", ctypes.c_void_p,
         [HWND, ctypes.c_void_p, UINT, ctypes.c_void_p]),
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
        (user32, "GetWindowPlacement", BOOL,
         [HWND, ctypes.POINTER(WINDOWPLACEMENT)]),
        (user32, "SetWindowPlacement", BOOL,
         [HWND, ctypes.POINTER(WINDOWPLACEMENT)]),
        (user32, "SystemParametersInfoW", BOOL,
         [UINT, UINT, ctypes.c_void_p, UINT]),
        (user32, "GetWindowThreadProcessId", DWORD,
         [HWND, ctypes.POINTER(DWORD)]),
        # --- hook, hotkeys, DPI
        (user32, "SetWinEventHook", HANDLE,
         [UINT, UINT, wintypes.HMODULE, WINEVENTPROC, DWORD, DWORD, UINT]),
        (user32, "UnhookWinEvent", BOOL, [HANDLE]),
        (user32, "RegisterHotKey", BOOL, [HWND, ctypes.c_int, UINT, UINT]),
        (user32, "UnregisterHotKey", BOOL, [HWND, ctypes.c_int]),
        (user32, "SetThreadDpiAwarenessContext", ctypes.c_void_p,
         [ctypes.c_void_p]),
        # --- GDI. SelectObject and CreateDIBSection return pointer-sized
        # handles; leaving restype at c_int truncates them on 64-bit and the
        # next call raises OverflowError somewhere unrelated.
        (gdi32, "CreateDIBSection", wintypes.HBITMAP,
         [HDC, ctypes.POINTER(BITMAPINFO), UINT,
          ctypes.POINTER(ctypes.c_void_p), HANDLE, DWORD]),
        (gdi32, "CreateCompatibleDC", HDC, [HDC]),
        (gdi32, "SelectObject", wintypes.HGDIOBJ, [HDC, wintypes.HGDIOBJ]),
        (gdi32, "DeleteObject", BOOL, [wintypes.HGDIOBJ]),
        (gdi32, "DeleteDC", BOOL, [HDC]),
        # --- DWM
        (dwmapi, "DwmRegisterThumbnail", ctypes.c_long,
         [HWND, HWND, ctypes.POINTER(HANDLE)]),
        (dwmapi, "DwmUnregisterThumbnail", ctypes.c_long, [HANDLE]),
        (dwmapi, "DwmUpdateThumbnailProperties", ctypes.c_long,
         [HANDLE, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)]),
        (dwmapi, "DwmIsCompositionEnabled", ctypes.c_long,
         [ctypes.POINTER(BOOL)]),
        # --- kernel32
        (kernel32, "GetModuleHandleW", wintypes.HMODULE, [wintypes.LPCWSTR]),
        (kernel32, "GetCurrentThreadId", DWORD, []),
    ]
    for lib, name, restype, argtypes in d:
        fn = getattr(lib, name)
        fn.restype = restype
        fn.argtypes = argtypes

    return Libs(user32, gdi32, dwmapi, kernel32)
