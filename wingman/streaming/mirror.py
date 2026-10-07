"""The streamable window: a focus-following DWM mirror (issue #316).

One real top-level window that shows, via one DWM thumbnail, the currently
focused EVE client, so Discord -- pinning one window per registered
process -- has exactly one game-like window to pin and its content follows
whoever is flying. Harvested from the probe build this module carried for
issue #315: the probe console (input thread, banner, style sweep, the one
minimize test, off-desktop parking) is gone; the field-proven core it
tested is what ships. The probe itself lives on, unworn, as
``scripts/capture_visibility_probe.py``, and its findings are recorded on
#312: cloak-primary parking streams live, covered on-desktop is the
fallback, off-desktop parking freezes the composed surface, a minimized
mirror pauses the stream, and the mirror must be borderless and shaped to
its source or the stream carries letterbox bars.

Window mechanics (spec: docs/combat-golive-design.md, Part II):

- created at the bottom of the z-order (``HWND_BOTTOM`` before first
  show), shown without activating, ``WM_MOUSEACTIVATE`` answers
  ``MA_NOACTIVATE`` -- the pilot must never lose focus mid-fight to a
  mirror;
- never minimizes: ``WS_MINIMIZEBOX`` stripped at creation and
  ``SC_MINIMIZE`` swallowed in ``WM_SYSCOMMAND`` (a minimized window stops
  compositing and the stream pauses -- field-proven on #315);
- borderless (``WS_POPUP``) and resized to the bound source's outer rect
  on every bind and rebind -- the user rejected letterboxing;
- parked by cloak by default (``DWMWA_CLOAK``: DWM keeps compositing the
  window's surface but does not show it -- the mechanism Windows uses for
  virtual desktops; probe-proven to stream). A failed cloak falls back to
  the covered on-desktop park, bottom-left behind every window, which the
  probe also proved streams. ``park_mode`` says which one is in effect so
  the Streaming card (#317) never has to guess.

Content: one thumbnail binding via the house wrapper
(``wingman.preview.thumbnail``), unregistered and re-registered at the new
admitted client when the foreground changes (DWM has no retarget call).
Admission is the house rule (``bookmarks.is_engine_window_title``), not a
substring: on desktop/browser focus the mirror keeps the last client --
never blanks the fleet's view, never mirrors non-EVE content. Source death
releases the thumbnail (routine; ``thumbnail.py`` already treats it so)
and keeps the hwnd, so the next admitted foreground rebinds; the fleet
sees a frozen last frame until then, which the spec accepts.

This module is both the mirror exe's entry point (``main()``, packaged by
``packaging/mirror.spec``) and the unit-tested seam: ``Mirror`` is fully
reachable with injected libs, the way ``tests/test_streaming_mirror.py``
drives it on Linux. Process concerns -- spawn, Job object, status file,
orphan recovery -- are the supervisor's (#317), not this file's.
"""

import ctypes
import logging
import sys
from collections import namedtuple
from ctypes import wintypes

from wingman.preview import thumbnail, win32

logger = logging.getLogger(__name__)

# --- Constants the preview subsystem never needed -------------------------
# Self-owned here; values per the platform SDK. WM_SYSCOMMAND/SC_MINIMIZE
# deliberately stay local: tests/test_preview_wiring.py pins those names
# OUT of preview/win32.py, so they must not be imported from there.
WM_SYSCOMMAND = 0x0112
WM_APP_BASE = 0x8000
SC_MINIMIZE = 0xF020
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
DWMWA_CLOAK = 13  # render-but-don't-show (the virtual-desktop mechanism)
GWL_STYLE = -16
WS_MINIMIZEBOX = 0x00020000

# Re-exported from the house surface so callers (and tests) read one
# vocabulary from this module.
EVENT_SYSTEM_FOREGROUND = win32.EVENT_SYSTEM_FOREGROUND
WINEVENT_OUTOFCONTEXT = win32.WINEVENT_OUTOFCONTEXT
WM_MOUSEACTIVATE = win32.WM_MOUSEACTIVATE
MA_NOACTIVATE = win32.MA_NOACTIVATE
WM_ERASEBKGND = win32.WM_ERASEBKGND
WM_CLOSE = win32.WM_CLOSE
WS_POPUP = win32.WS_POPUP
WS_EX_TOOLWINDOW = win32.WS_EX_TOOLWINDOW
SW_SHOWNOACTIVATE = win32.SW_SHOWNOACTIVATE
SM_XVIRTUALSCREEN = win32.SM_XVIRTUALSCREEN
SM_YVIRTUALSCREEN = win32.SM_YVIRTUALSCREEN
SM_CXVIRTUALSCREEN = win32.SM_CXVIRTUALSCREEN
SM_CYVIRTUALSCREEN = win32.SM_CYVIRTUALSCREEN

# Foreground changes arrive as this WM_APP message, posted by the WinEvent
# hook onto the pump thread -- hook = arbitrary-thread ingress, the same
# rule preview/host.py's hook follows: record and defer, no work in the
# callback.
MSG_FOREGROUND = WM_APP_BASE + 0

MIRROR_SIZE_DEFAULT = (800, 600)
CLASS_NAME = "WingmanMirror"
WINDOW_TITLE = "Wingman mirror"


def _declare(fn, restype, argtypes):
    """Idempotent local argtypes/restype declaration (see win32.py's
    docstring: an undeclared call marshals handles as 32-bit ints and
    fails far away from the cause)."""
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


def _bind_extras(libs):
    """Declarations this module needs that preview's bind() doesn't
    already carry. Must run before the first call, not at import."""
    _declare(libs.user32.SetProcessDPIAware, wintypes.BOOL, [])
    _declare(
        libs.user32.GetWindowLongW,
        ctypes.c_long,
        [wintypes.HWND, ctypes.c_int],
    )
    _declare(
        libs.user32.SetWindowLongW,
        ctypes.c_long,
        [wintypes.HWND, ctypes.c_int, ctypes.c_long],
    )
    _declare(
        libs.dwmapi.DwmSetWindowAttribute,
        ctypes.c_long,  # HRESULT
        [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD],
    )


def _window_class():
    """The window-class struct, built lazily: its _fields_ evaluates
    ``win32.wndproc_type()``, and WINFUNCTYPE does not exist off Windows
    (see win32.py's docstring). A module-scope definition would make the
    import -- and with it every fake-lib unit test -- Linux-dead. Same
    shape as preview/host.py, which defines its class inside bind()."""

    class WNDCLASSW(ctypes.Structure):
        """Local window-class struct (house pattern: each module defines
        it, lazily for the reason above)."""

        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", win32.wndproc_type()),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    return WNDCLASSW


class GeoRect(namedtuple("GeoRect", "x y right bottom")):
    """Geometry in the shape thumbnail.update() wants (x/y + edges).
    A tuple, because a rect that compares equal to its values makes test
    assertions (and failure messages) read as the numbers themselves."""


class Mirror:
    """The single-window DWM mirror: window mechanics, cloak-primary
    parking, and the bind/rebind/release lifecycle, all reachable with
    injected libs so the logic half unit-tests on Linux exactly like the
    preview fake-lib tests."""

    def __init__(self, libs, sources=("EVE - ",), size=MIRROR_SIZE_DEFAULT):
        self.libs = libs
        # sources exists so a test or future caller can widen admission,
        # but the default must stay the house prefix: is_engine_window_title
        # is the single rule for what counts as an EVE client window, and
        # the mirror must never mirror what the rest of Wingman refuses.
        self.sources = tuple(sources)
        self.size = size
        self.mirror_hwnd = None
        self.thumb = None
        self.src_hwnd = None
        self.park_mode = "cloak"  # "cloak" | "visible"; set_cloak keeps honest
        self.cloaked = False
        self.hook = None

    # -- admission ---------------------------------------------------------
    def admitted(self, title):
        """The house rule: exactly the titles the engine and every other
        EVE list already accept (``EVE - `` prefix, no ``=`` -- see
        bookmarks.is_engine_window_title, which this mirrors deliberately:
        bookmarks is pure keybind/INI logic and must not gain streaming
        imports, so the parity test below pins the two together instead)."""
        return bool(title) and title.startswith(self.sources) and "=" not in title

    def window_title(self, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        self.libs.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    # -- window -------------------------------------------------------------
    def create_mirror(self):
        # Borderless, always: the mirror is resized to the bound source's
        # outer rect on every bind (field finding, #315: a fixed-size or
        # captioned mirror letterboxes -- Discord streams the white bars).
        # TOOLWINDOW (field finding, 2026-10-07): without it the shell
        # gives a visible top-level window a taskbar button, and raw
        # DWMWA_CLOAK hides the pixels but not the button -- the user
        # saw the mirror's icon sitting in the bar. A tool window has no
        # taskbar button and no alt-tab entry; Discord pins the process's
        # one streamable window either way (the pin is per-process).
        style = win32.WS_POPUP
        self.mirror_hwnd = self.libs.user32.CreateWindowExW(
            win32.WS_EX_TOOLWINDOW,
            CLASS_NAME,
            WINDOW_TITLE,
            style,
            50,
            50,
            self.size[0],
            self.size[1],
            None,
            None,
            self.libs.kernel32.GetModuleHandleW(None),
            None,
        )
        if not self.mirror_hwnd:
            raise RuntimeError(f"CreateWindowExW failed: {ctypes.get_last_error()!r}")
        self.refresh_style()
        # Bottom of the z-order before first show; show without activating.
        self.libs.user32.SetWindowPos(
            self.mirror_hwnd,
            HWND_BOTTOM,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        self.libs.user32.ShowWindow(self.mirror_hwnd, win32.SW_SHOWNOACTIVATE)
        if not self.set_cloak(True):
            # Cloak refused (rare): the covered on-desktop park is the
            # proven fallback -- never off-desktop, it freezes the stream.
            self.park()

    def destroy_mirror(self):
        if self.mirror_hwnd:
            self.libs.user32.DestroyWindow(self.mirror_hwnd)
            self.mirror_hwnd = None

    def refresh_style(self):
        """Strip WS_MINIMIZEBOX: belt to WM_SYSCOMMAND's braces. A
        minimized mirror stops compositing and the stream pauses."""
        if not self.mirror_hwnd:
            return
        style = self.libs.user32.GetWindowLongW(self.mirror_hwnd, GWL_STYLE)
        self.libs.user32.SetWindowLongW(
            self.mirror_hwnd, GWL_STYLE, style & ~WS_MINIMIZEBOX
        )

    # -- parking -------------------------------------------------------------
    def set_cloak(self, cloaked):
        """DWMWA_CLOAK: DWM keeps compositing the window's surface but does
        not show it -- the mechanism Windows uses for virtual desktops.
        Probe-proven (#315) to keep streaming under Discord's game capture.
        Returns True when the cloak took; park_mode tracks reality either
        way, so nothing downstream ever believes a mirror is hidden when
        it is on the desktop."""
        if not self.mirror_hwnd:
            return False
        val = wintypes.BOOL(1 if cloaked else 0)
        hr = self.libs.dwmapi.DwmSetWindowAttribute(
            self.mirror_hwnd,
            DWMWA_CLOAK,
            ctypes.byref(val),
            ctypes.sizeof(val),
        )
        self.cloaked = bool(cloaked and hr == 0)
        self.park_mode = "cloak" if self.cloaked else "visible"
        return self.cloaked

    def park(self):
        """The fallback park: on the desktop (never off the edge -- the
        composed surface freezes out there, field-proven), bottom-left of
        the virtual screen, at the bottom of the z-order, behind
        everything. Covered-but-composited streams; the probe proved it."""
        if not self.mirror_hwnd:
            return
        x = self.libs.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = self.libs.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        h = self.libs.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        self.libs.user32.SetWindowPos(
            self.mirror_hwnd,
            HWND_BOTTOM,
            x,
            max(0, y + h - self.size[1]),
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE,
        )

    # -- thumbnail --------------------------------------------------------
    def bind_source(self, src_hwnd):
        """Bind the thumbnail to src_hwnd (no return value: a failed
        registration is logged by thumbnail.py, not raised -- a source
        that vanished between the foreground event and this call is
        routine). Records the admitted choice before registering so the
        sticky-last-client semantics never depend on DWM's mood."""
        if not (self.mirror_hwnd and src_hwnd):
            return
        self.release_thumbnail()
        self.src_hwnd = int(src_hwnd)
        self.match_source_rect()
        self.thumb = thumbnail.Thumbnail.register(
            self.libs, self.mirror_hwnd, self.src_hwnd
        )
        if self.thumb is not None:
            self.thumb.update(self.client_rect())

    def release_thumbnail(self):
        """Idempotent release; the hwnd stays -- the next admitted
        foreground rebinds, and the frozen last frame in between is the
        spec-accepted behavior for a dead source."""
        if self.thumb is not None:
            self.thumb.close()
            self.thumb = None

    def on_source_gone(self):
        self.release_thumbnail()

    def match_source_rect(self):
        """Size and place the mirror exactly over the source window's
        outer rect (field finding: a fixed-size mirror letterboxes --
        Discord streams the white bars). Borderless + same rect +
        borderless thumbnail dest = the stream sees the game, full frame.
        Re-anchored at HWND_BOTTOM: re-shaping must not raise the window."""
        if not (self.mirror_hwnd and self.src_hwnd):
            return
        src = wintypes.RECT()
        # Plain ints, not wintypes.HWND(...) wrappers: declared argtypes
        # marshal (thumbnail.py's pattern), and int handles keep the
        # logic comparable across fake and real libs.
        if not self.libs.user32.GetWindowRect(self.src_hwnd, ctypes.byref(src)):
            return
        w = max(1, src.right - src.left)
        h = max(1, src.bottom - src.top)
        self.libs.user32.SetWindowPos(
            self.mirror_hwnd,
            HWND_BOTTOM,
            src.left,
            src.top,
            w,
            h,
            SWP_NOACTIVATE,
        )

    def client_rect(self):
        """Destination rect for the thumbnail: the mirror's whole client
        area. With source-shape matching the mirror is borderless and
        sized to the source's outer rect, so client == source shape and a
        full-client destination is exactly full-frame -- no letterbox, no
        fit math (the probe's aspect-fit path died with the captioned
        probe build; it is recoverable from scripts/capture_visibility_probe.py
        if a captioned variant ever returns)."""
        rect = wintypes.RECT()
        if not self.libs.user32.GetClientRect(self.mirror_hwnd, ctypes.byref(rect)):
            raise RuntimeError("GetClientRect failed on the mirror")
        return GeoRect(rect.left, rect.top, rect.right, rect.bottom)

    # -- foreground -----------------------------------------------------
    def on_foreground(self, hwnd):
        """The pump-thread foreground consumer. Admitted client: rebind
        (DWM has no retarget). Anything else: sticky last client -- no
        unregister, no blank, never non-EVE content."""
        if not self.mirror_hwnd or not hwnd:
            return
        if hwnd == self.src_hwnd or not self.admitted(self.window_title(hwnd)):
            return
        self.bind_source(hwnd)

    def install_hook(self):
        """EVENT_SYSTEM_FOREGROUND on this thread (the pump thread the
        caller owns); the callback only posts -- see MSG_FOREGROUND. The
        callback object goes into the house ``win32._KEEPALIVE``: every
        callback handed to Windows lives in that one list (the instance
        alone must not be the keeper -- the pump's global wndproc
        references it, but the discipline is one list, not two)."""
        cb = win32.winevent_proc_type()(self._on_foreground)
        win32._KEEPALIVE.append(cb)
        self.hook = self.libs.user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            cb,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )
        if not self.hook:
            logger.warning("SetWinEventHook failed; the mirror cannot follow focus")

    def _on_foreground(self, hook, event, hwnd, obj, child, tid, ms):
        # Hook = arbitrary-thread ingress: record nothing here, hand off
        # to the pump thread (the same rule preview/host.py's hook follows).
        if self.mirror_hwnd and hwnd:
            self.libs.user32.PostMessageW(
                self.mirror_hwnd, MSG_FOREGROUND, wintypes.WPARAM(hwnd), 0
            )

    # -- wndproc ----------------------------------------------------------
    def handle_message(self, hwnd, msg, wparam, lparam):
        """The window procedure, as a plain method: every branch here is
        unit-testable with fake libs, and the pump wraps it in the ctypes
        callback. Anything not claimed below MUST fall through to
        DefWindowProcW -- the messages Windows pumps during
        CreateWindowExW, before the handle exists, break window creation
        if swallowed (probe lesson, cost a day)."""
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_SYSCOMMAND:
            if (wparam & 0xFFF0) == SC_MINIMIZE:
                logger.info("Minimize request swallowed (the mirror never minimizes).")
                return 0
        elif msg == win32.WM_CLOSE:
            self.release_thumbnail()
            self.libs.user32.DestroyWindow(hwnd)
            return 0
        elif msg == win32.WM_DESTROY:
            self.libs.user32.PostQuitMessage(0)
            return 0
        elif msg == WM_ERASEBKGND:
            return 1
        elif msg == MSG_FOREGROUND:
            self.on_foreground(wparam)
            return 0
        return self.libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # -- teardown ---------------------------------------------------------
    def teardown(self):
        self.release_thumbnail()
        if self.hook:
            self.libs.user32.UnhookWinEvent(self.hook)
            self.hook = None


def main(argv=None):
    """The wingman-mirror.exe entry: one window, one hook, one pump.
    Deliberately short -- process lifetime is the supervisor's (#317);
    this only has to stand up the window and follow focus until killed."""
    libs = win32.bind()
    _bind_extras(libs)
    libs.user32.SetProcessDPIAware()

    mirror = Mirror(libs)

    proc = win32.wndproc_type()(mirror.handle_message)
    win32._KEEPALIVE.append(proc)
    cls = _window_class()()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = CLASS_NAME
    libs.user32.RegisterClassW(ctypes.byref(cls))

    mirror.create_mirror()
    mirror.install_hook()

    msg = wintypes.MSG()
    lm = ctypes.byref(msg)
    while True:
        r = libs.user32.GetMessageW(lm, None, 0, 0)
        if r <= 0:
            break
        libs.user32.TranslateMessage(lm)
        libs.user32.DispatchMessageW(lm)

    mirror.teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
