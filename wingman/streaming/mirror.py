"""wingman-mirror: the capture-visibility probe build of the rev-3 mirror.

The one unknown issue #312 rests on (see docs/combat-golive-design.md):
does Discord's game capture show DWM-composited thumbnail content, and
does its per-process pin land on a window that is created after
registration, sits at the bottom of the z-order, and is never focused?
The throwaway probe script answered "how would we test that"; this exe is
the thing under test wearing its real name -- a dedicated,
single-window ``wingman-mirror.exe`` that Discord's Registered Games can
register as the game (issue #315), which the earlier plan of registering
``python.exe`` could not isolate: every Python process on the box would
have become the "game".

Deliberately everything the rev-3 mirror will be (ticket #316 harvests
the ``Mirror`` logic half; ticket #317 adds the supervisor; #318 the
production packaging):

- one real top-level window with a caption, created at the bottom of the
  z-order, never activated (WM_MOUSEACTIVATE -> MA_NOACTIVATE), never
  minimized (SC_MINIMIZE swallowed);
- one DWM thumbnail via the house wrapper (wingman.preview.thumbnail),
  rebound on foreground changes to admitted source windows;
- sticky last client: non-source focus never blanks the mirror;
- source death releases the thumbnail (routine, per preview/);

and, only for the probe build, a console protocol that walks the
runbook's legs (docs/combat-golive-probe.md): arm focus-follow, park
off-screen, the style sweep, the one allowed minimize, target listing.
The keys match the probe script exactly so the runbook needs no second
vocabulary. Nothing here ships in the product yet: no settings, no
supervision, no bridge -- those land with their tickets.

Run from a checkout (smoke only -- register the built exe, not python):

    python -m wingman.streaming.mirror
"""

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
CLASS_NAME = "WingmanMirrorProbe"
WINDOW_TITLE = "Wingman mirror"
PHASE_LABELS = {0: "STATIC", 1: "FOLLOW", 3: "PARKED+FOLLOW"}


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


class WNDCLASSW(ctypes.Structure):
    """Local window-class struct (house pattern: each module defines it)."""

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


class GeoRect:
    """Geometry in the shape thumbnail.update() wants (x/y + edges)."""

    def __init__(self, rect):
        self.x, self.y = rect.left, rect.top
        self.right, self.bottom = rect.right, rect.bottom


class Mirror:
    """The single-window DWM mirror. Window/pump/thread mechanics live in
    main(); everything here is reachable with injected libs so ticket #316
    can unit-test the logic half on Linux (fake thumbnail libs, fake
    foreground events) exactly like the preview fake-lib tests."""

    def __init__(self, libs, source_substring, off_screen, size=MIRROR_SIZE_DEFAULT):
        self.libs = libs
        self.source_substring = source_substring
        self.off_screen = off_screen
        self.size = size
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
        self.say("mirror parked off the virtual-screen edge (composed, unseen)")

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
            self.say("!! DwmRegisterThumbnail FAILED (see log line above)")
            return
        self.thumb.update(self.client_rect())
        self.say(f"thumbnail live: {self.window_title(self.src_hwnd)!r} -> mirror")

    def client_rect(self):
        rect = wintypes.RECT()
        if not self.libs.user32.GetClientRect(self.mirror_hwnd, ctypes.byref(rect)):
            raise RuntimeError("GetClientRect failed on the mirror")
        return GeoRect(rect)

    # -- helpers ---------------------------------------------------------
    def window_title(self, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        self.libs.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def say(self, text):
        print(f"[{_stamp()}] {text}", flush=True)

    def _is_target(self, hwnd):
        if not hwnd:
            return False
        return self.source_substring.lower() in self.window_title(hwnd).lower()

    # -- wndproc ----------------------------------------------------------
    def _proc(self, hwnd, msg, wparam, lparam):
        libs = self.libs
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_SYSCOMMAND:
            if (wparam & 0xFFF0) == SC_MINIMIZE and not self.allow_minimize:
                self.say("minimize request SWALLOWED (spec: never minimize)")
                return 0
        elif msg == win32.WM_CLOSE:
            self.teardown()
            libs.user32.DestroyWindow(hwnd)
            return 0
        elif msg == win32.WM_DESTROY:
            libs.user32.PostQuitMessage(0)
            return 0
        elif msg == WM_ERASEBKGND:
            return 1
        elif msg == WM_APP_BASE + 0:  # foreground changed (from the hook)
            self.last_fg_hwnd = wparam
            self.last_fg_title = self.window_title(wparam)
            self.say(f"foreground: {self.last_fg_title!r}")
            if self.phase >= 1 and self._is_target(wparam) and wparam != self.src_hwnd:
                self.say("focus-follow: rebinding thumbnail")
                self.bind_source(wparam)
            return 0
        # Probe commands; anything else (including the messages Windows
        # pumps during CreateWindowExW, before the handle exists) must
        # reach DefWindowProcW -- swallowing them breaks window creation.
        handled = self._command(msg, hwnd)
        if handled is None:
            return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        return handled

    def _command(self, msg, hwnd):
        """The probe commands, posted as WM_APP messages from the input
        thread so every window mutation stays on the pump thread. Returns
        None for messages it does not own (the caller must then fall
        through to DefWindowProcW -- including the messages Windows pumps
        during CreateWindowExW, before the handle exists)."""
        libs = self.libs
        if msg == CMD_ARM_FOLLOW:
            self.phase = 1
            self.refresh_caption()
            self.say(
                "PHASE: focus-follow ARMED - switch between source "
                "windows; the thumbnail follows admitted targets"
            )
        elif msg == CMD_PARK:
            self.phase = max(self.phase, 3)
            self.park()
            self.refresh_caption()
        elif msg == CMD_MINIMIZE_TEST:
            self.allow_minimize = True
            self.say(
                "minimize-confirmation: allowing this one minimize "
                "- watch Discord go black/frozen"
            )
            libs.user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_MINIMIZE, 0)
        elif msg == CMD_TOGGLE_TOOLWINDOW:
            self.toolwindow = not self.toolwindow
            self.say(
                f"style sweep: WS_EX_TOOLWINDOW -> {self.toolwindow} (window will "
                "be recreated; re-pick the source in Discord if the pin moves)"
            )
            self.recreate()
        elif msg == CMD_TOGGLE_CAPTION:
            self.caption = not self.caption
            self.say(f"style sweep: caption -> {self.caption} (window recreated)")
            self.recreate()
        elif msg == CMD_REBIND:
            if self.last_fg_hwnd and self._is_target(self.last_fg_hwnd):
                self.bind_source(self.last_fg_hwnd)
            else:
                self.say("no admitted target focused; nothing to rebind to")
        elif msg == CMD_LIST:
            self.list_targets()
        elif msg == CMD_QUIT:
            libs.user32.PostMessageW(hwnd, win32.WM_CLOSE, 0, 0)
        else:
            return None
        return 0

    def recreate(self):
        src = self.src_hwnd
        self.destroy_mirror()
        self.create_mirror()
        if src:
            self.bind_source(src)

    def refresh_caption(self):
        label = PHASE_LABELS.get(self.phase, "?")
        if self.mirror_hwnd:
            self.libs.user32.SetWindowTextW(
                self.mirror_hwnd, f"{WINDOW_TITLE} [{label}]"
            )

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
            found.append((int(hwnd), self.window_title(hwnd)))
            return True

        self._enumerate(on_window)
        self.say("visible top-level windows (candidates for --src-title):")
        for hwnd, title in found[:40]:
            mark = "  <== current source" if hwnd == self.src_hwnd else ""
            print(f"    0x{hwnd:08x}  {title!r} {mark}", flush=True)

    def find_target(self):
        best = None
        found = []
        needle = self.source_substring.lower()

        def on_window(hwnd, _lparam):
            if not self.libs.user32.IsWindowVisible(hwnd):
                return True
            title = self.window_title(hwnd)
            if needle in title.lower():
                found.append((int(hwnd), title))
            return True

        self._enumerate(on_window)
        if found:
            best = found[0]
            self.say("source target: 0x{:08x} {!r}".format(*best))
        else:
            self.say(
                f"!! no visible window title contains {self.source_substring!r}; "
                "run 'l' to list candidates and restart with --src-title"
            )
        return best[0] if best else None

    def _enumerate(self, on_window):
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            on_window
        )
        self._keepalive.append(enum_proc)
        self.libs.user32.EnumWindows(enum_proc, 0)

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
            self.say("!! SetWinEventHook failed; focus-follow inert")

    def _on_foreground(self, hook, event, hwnd, obj, child, tid, ms):
        # Hook = arbitrary-thread ingress: record nothing here, hand off to
        # the pump thread (the same rule preview/host.py's hook follows).
        if self.mirror_hwnd and hwnd:
            self.libs.user32.PostMessageW(
                self.mirror_hwnd, WM_APP_BASE + 0, wintypes.WPARAM(hwnd), 0
            )

    # -- teardown ----------------------------------------------------------
    def teardown(self):
        if self.thumb is not None:
            self.thumb.close()
            self.thumb = None
        if self.hook:
            self.libs.user32.UnhookWinEvent(self.hook)
            self.hook = None


def banner(exe_path):
    line = "=" * 64
    print(line, flush=True)
    print("WINGMAN MIRROR - capture-visibility probe build (#312 / #315)", flush=True)
    print(line, flush=True)
    print("Register THIS exe in Discord -> Settings -> Registered Games:", flush=True)
    print(f"    {exe_path}", flush=True)
    print("Then stream it (Go Live -> the mirror entry) and follow", flush=True)
    print("docs/combat-golive-probe.md. Console commands, typed here:", flush=True)
    print("  2 = arm focus-follow   3 = park off-screen bottom", flush=True)
    print("  5 = minimize-confirmation test (watch Discord die)", flush=True)
    print("  t = toggle WS_EX_TOOLWINDOW   c = toggle caption", flush=True)
    print("  r = force rebind to focused target   l = list windows", flush=True)
    print("  q = quit", flush=True)
    print(line, flush=True)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    source_substring = "Notepad"
    off_screen = False
    quit_after = 0.0
    it = iter(args)
    for a in it:
        if a == "--src-title":
            source_substring = next(it)
        elif a == "--off-screen":
            off_screen = True
        elif a == "--quit-after":
            quit_after = float(next(it))

    libs = win32.bind()
    _bind_extras(libs)
    libs.user32.SetProcessDPIAware()

    mirror = Mirror(libs, source_substring, off_screen)

    proc = win32.wndproc_type()(mirror._proc)
    win32._KEEPALIVE.append(proc)
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = CLASS_NAME
    libs.user32.RegisterClassW(ctypes.byref(cls))

    # When frozen, sys.executable IS wingman-mirror.exe -- the path the
    # user registers. A dev run prints the interpreter and says so.
    exe_path = sys.executable
    banner(exe_path)
    if not getattr(sys, "frozen", False):
        mirror.say(
            "dev run (not the exe): register the built wingman-mirror.exe, "
            "not this interpreter -- python's image name is every Python "
            "process on the box"
        )

    mirror.create_mirror()
    mirror.install_hook()
    mirror.refresh_caption()

    src = mirror.find_target()
    if src:
        mirror.bind_source(src)
    mirror.list_targets()

    # Watchdog: periodic status line + iconic checks, on the pump thread.
    WM_TIMER_WATCH = 1

    def on_timer(_hwnd, _msg, _wparam, _lparam):
        iconic = bool(mirror.mirror_hwnd) and libs.user32.IsIconic(mirror.mirror_hwnd)
        src_iconic = bool(mirror.src_hwnd) and libs.user32.IsIconic(mirror.src_hwnd)
        mirror.say(
            f"status: phase={mirror.phase} fg={mirror.last_fg_title!r} "
            f"mirror_iconic={iconic} src_iconic={src_iconic}"
        )
        if iconic:
            mirror.say(
                "!! mirror MINIMIZED: per spec, its composed surface "
                "is gone - confirm Discord shows black/frozen"
            )
        if src_iconic:
            mirror.say("!! source MINIMIZED: thumbnail is a frozen frame")

    timer_cb = win32.wndproc_type()(on_timer)
    win32._KEEPALIVE.append(timer_cb)
    libs.user32.SetTimer(mirror.mirror_hwnd, WM_TIMER_WATCH, 5000, timer_cb)

    def post(cmd, note=None):
        if note:
            mirror.say(f"command: {cmd}")
        if mirror.mirror_hwnd:
            libs.user32.PostMessageW(mirror.mirror_hwnd, cmd, 0, 0)

    if quit_after > 0:
        # Smoke path: run the pump for N seconds, then quit -- no console
        # interaction needed (also what future CI can drive).
        threading.Timer(quit_after, lambda: post(CMD_QUIT)).start()

    def input_thread():
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == "2":
                post(CMD_ARM_FOLLOW, note=True)
            elif cmd == "3":
                post(CMD_PARK, note=True)
            elif cmd == "5":
                post(CMD_MINIMIZE_TEST, note=True)
            elif cmd == "t":
                post(CMD_TOGGLE_TOOLWINDOW, note=True)
            elif cmd == "c":
                post(CMD_TOGGLE_CAPTION, note=True)
            elif cmd == "r":
                post(CMD_REBIND, note=True)
            elif cmd == "l":
                post(CMD_LIST, note=True)
            elif cmd == "q":
                post(CMD_QUIT)
                return
            else:
                print(f"  unknown command {cmd!r} (2 3 5 t c r l q)", flush=True)

    if sys.stdin is not None and hasattr(sys.stdin, "readline"):
        threading.Thread(target=input_thread, daemon=True).start()

    msg = wintypes.MSG()
    lm = ctypes.byref(msg)
    while True:
        r = libs.user32.GetMessageW(lm, None, 0, 0)
        if r <= 0:
            break
        libs.user32.TranslateMessage(lm)
        libs.user32.DispatchMessageW(lm)

    mirror.teardown()
    mirror.say("mirror ended")


if __name__ == "__main__":
    main()
