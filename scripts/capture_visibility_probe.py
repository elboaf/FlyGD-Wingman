"""Capture-visibility probe for #312 (combat Go Live, rev 3).

Decides the one unknown the spec rests on: does Discord's game capture see
DWM-composited thumbnail content, and does its per-process pin land on a
window that is created after registration, sits at the bottom of the
z-order, and is never focused?

Run THIS PROCESS on the streaming box (the box that runs Discord), with
EVE clients and Discord signed in:

    python scripts/capture_visibility_probe.py

Follow docs/combat-golive-probe.md. It has you add this script's python.exe
to Discord's Registered Games, start a stream at the mirror, and walk the
phases; the console prints a timestamped evidence trail to paste into #312.

The mirror is deliberately everything the spec's rev-3 mirror will be: a
real top-level window with a caption, created at the bottom of the z-order,
never activated (WM_MOUSEACTIVATE -> MA_NOACTIVATE), never minimized
(SC_MINIMIZE swallowed) unless you explicitly run the minimize-confirmation
step. The thumbnail is the house wrapper: wingman.preview.thumbnail.

Throwaway tool: nothing here ships, imports no product state, and touches
no EVE window beyond a DWM thumbnail (read-only, like every preview).
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wingman.preview import thumbnail, win32

# --- Constants the preview subsystem never needed -----------------------
WM_SYSCOMMAND = 0x0112
WM_MOUSEACTIVATE = 0x0021
WM_ERASEBKGND = 0x0014
WM_APP_BASE = 0x8000
SC_MINIMIZE = 0xF020
MA_NOACTIVATE = 3
HWND_BOTTOM = 1  # win32.py only needed HWND_TOPMOST / HWND_MESSAGE so far
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0

# Probe-local commands, posted from the input thread into the pump thread.
CMD_ARM_FOLLOW = WM_APP_BASE + 1
CMD_PARK = WM_APP_BASE + 2
CMD_MINIMIZE_TEST = WM_APP_BASE + 3
CMD_TOGGLE_TOOLWINDOW = WM_APP_BASE + 4
CMD_TOGGLE_CAPTION = WM_APP_BASE + 5
CMD_REBIND = WM_APP_BASE + 6
CMD_LIST = WM_APP_BASE + 7
CMD_QUIT = WM_APP_BASE + 8

MIRROR_SIZE_DEFAULT = (800, 600)
CLASS_NAME = "WingmanCaptureProbe"


def _stamp():
    return time.strftime("%H:%M:%S")


def _declare(libs, fn, restype, argtypes):
    """Idempotent local argtypes/restype declaration (see win32.py docstring:
    an undeclared call marshals handles as 32-bit ints and fails far away
    from the cause)."""
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


def _bind_extras(libs):
    _declare(
        libs,
        libs.user32.PostMessageW,
        wintypes.BOOL,
        [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
    )
    _declare(
        libs,
        libs.user32.SetWindowTextW,
        wintypes.BOOL,
        [wintypes.HWND, wintypes.LPCWSTR],
    )
    _declare(
        libs, libs.user32.GetWindowLongW, ctypes.c_long, [wintypes.HWND, ctypes.c_int]
    )
    _declare(
        libs,
        libs.user32.SetWindowLongW,
        ctypes.c_long,
        [wintypes.HWND, ctypes.c_int, ctypes.c_long],
    )
    _declare(libs, libs.user32.SetProcessDPIAware, wintypes.BOOL, [])
    _declare(libs, libs.user32.UnhookWinEvent, wintypes.BOOL, [wintypes.HANDLE])
    _declare(libs, libs.kernel32.GetModuleHandleW, wintypes.HMODULE, [wintypes.LPCWSTR])


# --- Local window-class struct (house pattern: each module defines it) ---
class WNDCLASSW(ctypes.Structure):
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


class Probe:
    def __init__(self, libs, src_title_sub, off_screen):
        self.libs = libs
        self.src_title_sub = src_title_sub
        self.off_screen = off_screen
        self.mirror_hwnd = None
        self.thumb = None
        self.src_hwnd = None
        self.phase = 0  # 0 static, 1 focus-follow armed, 3 parked
        self.allow_minimize = False
        self.toolwindow = False
        self.caption = True
        self.hook = None
        self.last_fg_hwnd = None
        self.last_fg_title = "?"
        self._keepalive = []

    # -- window ----------------------------------------------------------
    def create_mirror(self):
        style = win32.WS_CAPTION | win32.WS_SYSMENU
        ex_style = win32.WS_EX_TOOLWINDOW if self.toolwindow else 0
        self.mirror_hwnd = self.libs.user32.CreateWindowExW(
            ex_style,
            CLASS_NAME,
            "Wingman capture probe",
            style,
            50,
            50,
            MIRROR_SIZE_DEFAULT[0],
            MIRROR_SIZE_DEFAULT[1],
            None,
            None,
            self.libs.kernel32.GetModuleHandleW(None),
            None,
        )
        if not self.mirror_hwnd:
            raise RuntimeError(f"CreateWindowExW failed: {ctypes.get_last_error()!r}")
        # Bottom of the z-order before first show; show without activating.
        self.libs.user32.SetWindowPos(
            self.mirror_hwnd,
            wintypes.HWND(HWND_BOTTOM),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        self.libs.user32.ShowWindow(self.mirror_hwnd, win32.SW_SHOWNOACTIVATE)
        if self.off_screen:
            self.park()

    def destroy_mirror(self):
        if self.mirror_hwnd:
            self.libs.user32.DestroyWindow(self.mirror_hwnd)
            self.mirror_hwnd = None

    def park(self):
        # Fully off the virtual desktop edge: composed, never seen.
        x = self.libs.user32.GetSystemMetrics(win32.SM_XVIRTUALSCREEN)
        w = self.libs.user32.GetSystemMetrics(win32.SM_CXVIRTUALSCREEN)
        self.libs.user32.SetWindowPos(
            self.mirror_hwnd,
            None,
            x + w + 40,
            100,
            0,
            0,
            SWP_NOSIZE | SWP_NOACTIVATE,
        )
        self._say("mirror parked off the virtual-screen edge (composed, unseen)")

    # -- thumbnail -------------------------------------------------------
    def bind_source(self, src_hwnd):
        if self.thumb is not None:
            self.thumb.close()
            self.thumb = None
        self.src_hwnd = int(src_hwnd)
        self.thumb = thumbnail.Thumbnail.register(
            self.libs, self.mirror_hwnd, self.src_hwnd
        )
        if self.thumb is None:
            self._say("!! DwmRegisterThumbnail FAILED (see log line above)")
            return
        rect = self._client_rect()
        self.thumb.update(rect)
        title = self._title(self.src_hwnd)
        self._say(f"thumbnail live: '{title}' -> mirror")

    def _client_rect(self):
        """Geometry in the shape thumbnail.update() wants (x/y + edges)."""
        rect = wintypes.RECT()
        if not self.libs.user32.GetClientRect(self.mirror_hwnd, ctypes.byref(rect)):
            raise RuntimeError("GetClientRect failed on the mirror")

        class GeoRect:
            x, y = rect.left, rect.top
            right, bottom = rect.right, rect.bottom

        return GeoRect()

    # -- helpers ---------------------------------------------------------
    def _title(self, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        self.libs.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def _say(self, text):
        print(f"[{_stamp()}] {text}", flush=True)

    # -- wndproc ----------------------------------------------------------
    def _proc(self, hwnd, msg, wparam, lparam):
        libs = self.libs
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_SYSCOMMAND:
            if (wparam & 0xFFF0) == SC_MINIMIZE and not self.allow_minimize:
                self._say("minimize request SWALLOWED (spec: never minimize)")
                return 0
        elif msg == win32.WM_CLOSE:
            self._teardown()
            libs.user32.DestroyWindow(hwnd)
            return 0
        elif msg == win32.WM_DESTROY:
            libs.user32.PostQuitMessage(0)
            return 0
        elif msg == WM_ERASEBKGND:
            return 1
        elif msg == WM_APP_BASE + 0:  # foreground changed (from the hook)
            self.last_fg_hwnd = wparam
            self.last_fg_title = self._title(wparam)
            self._say(f"foreground: '{self.last_fg_title}'")
            if self.phase >= 1 and self._is_target(wparam) and wparam != self.src_hwnd:
                self._say("focus-follow: rebinding thumbnail")
                self.bind_source(wparam)
            return 0
        elif msg == CMD_ARM_FOLLOW:
            self.phase = 1
            self._set_caption()
            self._say(
                "PHASE: focus-follow ARMED - switch between EVE "
                "clients; the thumbnail follows admitted targets"
            )
            return 0
        elif msg == CMD_PARK:
            self.phase = max(self.phase, 3)
            self.park()
            self._set_caption()
            return 0
        elif msg == CMD_MINIMIZE_TEST:
            self.allow_minimize = True
            self._say(
                "minimize-confirmation: allowing this one minimize "
                "- watch Discord go black/frozen"
            )
            libs.user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_MINIMIZE, 0)
            return 0
        elif msg == CMD_TOGGLE_TOOLWINDOW:
            self.toolwindow = not self.toolwindow
            self._say(
                f"style sweep: WS_EX_TOOLWINDOW -> {self.toolwindow} (window will be "
                "recreated; re-pick the source in Discord if the pin "
                "moves)"
            )
            self._recreate()
            return 0
        elif msg == CMD_TOGGLE_CAPTION:
            self.caption = not self.caption
            self._say(
                f"style sweep: caption -> {self.caption} (window will be recreated)"
            )
            self._recreate()
            return 0
        elif msg == CMD_REBIND:
            if self.last_fg_hwnd and self._is_target(self.last_fg_hwnd):
                self.bind_source(self.last_fg_hwnd)
            else:
                self._say("no admitted target focused; nothing to rebind to")
            return 0
        elif msg == CMD_LIST:
            self.list_targets()
            return 0
        elif msg == CMD_QUIT:
            libs.user32.PostMessageW(hwnd, win32.WM_CLOSE, 0, 0)
            return 0
        return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _recreate(self):
        src = self.src_hwnd
        self.destroy_mirror()
        self.create_mirror()
        if src:
            self.bind_source(src)

    def _set_caption(self):
        label = {0: "STATIC", 1: "FOLLOW", 3: "PARKED+FOLLOW"}[self.phase]
        if self.mirror_hwnd:
            self.libs.user32.SetWindowTextW(
                self.mirror_hwnd, f"Wingman capture probe [{label}]"
            )

    def _is_target(self, hwnd):
        if not hwnd:
            return False
        return self.src_title_sub.lower() in self._title(hwnd).lower()

    # -- enumeration ------------------------------------------------------
    def list_targets(self):
        found = []

        def on_window(hwnd, _lparam):
            if not self.libs.user32.IsWindowVisible(hwnd):
                return True
            attr = wintypes.DWORD()
            hr = self.libs.dwmapi.DwmGetWindowAttribute(
                hwnd, win32.DWMWA_CLOAKED, ctypes.byref(attr), ctypes.sizeof(attr)
            )
            if hr == 0 and attr.value:
                return True
            title = self._title(hwnd)
            found.append((int(hwnd), title))
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            on_window
        )
        self._keepalive.append(enum_proc)
        self.libs.user32.EnumWindows(enum_proc, 0)
        self._say("visible top-level windows (candidates for --src-title):")
        for hwnd, title in found[:40]:
            mark = "  <== current source" if hwnd == self.src_hwnd else ""
            print(f"    0x{hwnd:08x}  {title!r} {mark}", flush=True)

    def find_target(self):
        best = None
        found = []

        def on_window(hwnd, _lparam):
            if not self.libs.user32.IsWindowVisible(hwnd):
                return True
            title = self._title(hwnd)
            if self.src_title_sub.lower() in title.lower():
                found.append((int(hwnd), title))
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            on_window
        )
        self._keepalive.append(enum_proc)
        self.libs.user32.EnumWindows(enum_proc, 0)
        if found:
            best = found[0]
            self._say("source target: 0x{:08x} {!r}".format(*best))
        else:
            self._say(
                f"!! no visible window title contains {self.src_title_sub!r}; run 'l' to "
                "list candidates and restart with --src-title"
            )
        return best[0] if best else None

    # -- hook --------------------------------------------------------------
    def install_hook(self):
        cb = win32.winevent_proc_type()(self._on_foreground)
        self._keepalive.append(cb)
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
            self._say("!! SetWinEventHook failed; focus-follow inert")

    def _on_foreground(self, hook, event, hwnd, obj, child, tid, ms):
        # Hook = arbitrary-thread ingress: record nothing here, hand off to
        # the pump thread (the same rule preview/host.py's hook follows).
        if self.mirror_hwnd and hwnd:
            self.libs.user32.PostMessageW(
                self.mirror_hwnd, WM_APP_BASE + 0, wintypes.WPARAM(hwnd), 0
            )

    # -- teardown ----------------------------------------------------------
    def _teardown(self):
        if self.thumb is not None:
            self.thumb.close()
            self.thumb = None
        if self.hook:
            self.libs.user32.UnhookWinEvent(self.hook)
            self.hook = None


def main():
    args = sys.argv[1:]
    src_title_sub = "Notepad"
    off_screen = False
    it = iter(args)
    for a in it:
        if a == "--src-title":
            src_title_sub = next(it)
        elif a == "--off-screen":
            off_screen = True

    libs = win32.bind()
    _bind_extras(libs)
    libs.user32.SetProcessDPIAware()

    probe = Probe(libs, src_title_sub, off_screen)

    proc = win32.wndproc_type()(probe._proc)
    win32._KEEPALIVE.append(proc)
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = CLASS_NAME
    libs.user32.RegisterClassW(ctypes.byref(cls))

    print("=" * 64, flush=True)
    print("WINGMAN CAPTURE-VISIBILITY PROBE  (#312, rev 3)", flush=True)
    print("=" * 64, flush=True)
    print(
        "Register THIS exe in Discord -> Settings -> Registered Games:",
    )
    print(f"    {sys.executable}", flush=True)
    print(
        "Then stream it (Go Live -> the probe entry) and follow",
    )
    print(
        "docs/combat-golive-probe.md. Console commands, typed here:",
    )
    print(
        "  2 = arm focus-follow   3 = park off-screen bottom",
    )
    print(
        "  5 = minimize-confirmation test (watch Discord die)",
    )
    print(
        "  t = toggle WS_EX_TOOLWINDOW   c = toggle caption",
    )
    print(
        "  r = force rebind to focused target   l = list windows",
    )
    print("  q = quit", flush=True)
    print("=" * 64, flush=True)

    probe.create_mirror()
    probe.install_hook()
    probe._set_caption()

    src = probe.find_target()
    if src:
        probe.bind_source(src)
    probe.list_targets()

    # Watchdog: periodic status line + iconic checks, on the pump thread.
    WM_TIMER_WATCH = 1

    def on_timer(_hwnd, _msg, _wparam, _lparam):
        iconic = bool(probe.mirror_hwnd) and libs.user32.IsIconic(probe.mirror_hwnd)
        src_iconic = bool(probe.src_hwnd) and libs.user32.IsIconic(probe.src_hwnd)
        phase = probe.phase
        fg = probe.last_fg_title
        probe._say(
            f"status: phase={phase} fg={fg!r} mirror_iconic={iconic} "
            f"src_iconic={src_iconic}"
        )
        if iconic:
            probe._say(
                "!! mirror MINIMIZED: per spec, its composed surface "
                "is gone - confirm Discord shows black/frozen"
            )
        if src_iconic:
            probe._say("!! source MINIMIZED: thumbnail is a frozen frame")

    timer_cb = win32.wndproc_type()(on_timer)
    win32._KEEPALIVE.append(timer_cb)
    libs.user32.SetTimer(probe.mirror_hwnd, WM_TIMER_WATCH, 5000, timer_cb)

    def input_thread():
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == "2":
                probe._say("command: 2")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_ARM_FOLLOW, 0, 0)
            elif cmd == "3":
                probe._say("command: 3")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_PARK, 0, 0)
            elif cmd == "5":
                probe._say("command: 5")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_MINIMIZE_TEST, 0, 0)
            elif cmd == "t":
                probe._say("command: t")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_TOGGLE_TOOLWINDOW, 0, 0)
            elif cmd == "c":
                probe._say("command: c")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_TOGGLE_CAPTION, 0, 0)
            elif cmd == "r":
                probe._say("command: r")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_REBIND, 0, 0)
            elif cmd == "l":
                probe._say("command: l")
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_LIST, 0, 0)
            elif cmd == "q":
                libs.user32.PostMessageW(probe.mirror_hwnd, CMD_QUIT, 0, 0)
                return
            else:
                print(f"  unknown command {cmd!r} (2 3 5 t c r l q)", flush=True)

    import threading

    threading.Thread(target=input_thread, daemon=True).start()

    msg = wintypes.MSG()
    lm = ctypes.byref(msg)
    while True:
        r = libs.user32.GetMessageW(lm, None, 0, 0)
        if r <= 0:
            break
        libs.user32.TranslateMessage(lm)
        libs.user32.DispatchMessageW(lm)

    probe._teardown()
    print(f"[{_stamp()}] probe ended", flush=True)


if __name__ == "__main__":
    main()
