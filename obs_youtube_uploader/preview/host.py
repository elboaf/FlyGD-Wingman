"""The preview thread: its pump, its windows, and its lifecycle.

pywebview runs its GUI on a thread of its own and does NOT pump on the
thread that calls webview.start() -- measured, not assumed. A window
created on the main thread is therefore orphaned: nobody dispatches its
messages. So previews get their own thread with a real GetMessage loop,
which is also what RegisterHotKey and SetWinEventHook require.

Same shape as ui/scheduler.py, one level lower: that module's docstring
records the identical discovery about webview.start() carrying none of
the old event loop, and answers it with an owned loop.
"""
import ctypes
import logging
import threading

from . import discovery, geometry, layout, win32
from .window import PreviewWindow

logger = logging.getLogger(__name__)

SWEEP_MS = 700          # TriffView uses the same interval
SWEEP_TIMER_ID = 1
JOIN_TIMEOUT_S = 5.0
DEFAULT_SIZE = (320, 210)


def reconcile(current: set, desired: set):
    """(added, removed, kept) stable keys between two sweeps."""
    return (sorted(desired - current), sorted(current - desired),
            sorted(current & desired))


class PreviewHost:
    """Owns the preview thread. Public methods are callable from anywhere;
    anything touching an HWND is marshalled onto the thread."""

    def __init__(self, on_layout_changed, saved_layouts=None,
                 size=DEFAULT_SIZE, flush_layouts=None):
        self._on_layout_changed = on_layout_changed
        # Called during teardown, before any window is destroyed. Layout
        # writes are debounced, so without this a drag in the last second
        # before quitting is simply lost.
        self._flush_layouts = flush_layouts
        self._saved = dict(saved_layouts or {})
        self._size = size
        self._thread = None
        self._hwnd = None          # message-only window, see _run
        self._windows = {}
        self._hook = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return   # Idempotent: a second enable must not orphan a pump.
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="wingman-preview")
            self._thread.start()

    def stop(self, timeout: float = JOIN_TIMEOUT_S) -> None:
        """Idempotent, and safe when never started."""
        with self._lock:
            thread, self._thread = self._thread, None
        if thread is None:
            return
        if self._hwnd:
            libs = win32.bind()
            libs.user32.PostMessageW(self._hwnd, win32.WM_APP_SHUTDOWN, 0, 0)
        thread.join(timeout)
        if thread.is_alive():
            # A stop() that returns while the thread still owns HWNDs
            # produces a Wingman that vanishes from the tray and lingers
            # in Task Manager.
            logger.warning("Preview thread did not exit within %.1fs", timeout)

    def _layout_changed(self, stable_key, rect, locked) -> None:
        """Record the new rect locally, then pass it outward.

        Keeping _saved current matters within a single session: a client
        that disappears and comes back -- an EVE client restart, or a
        transient discovery miss -- is a new entry to the next sweep. If
        _saved still held only what was loaded at startup, that preview
        would be placed by default_stack and the position the user dragged
        it to would not return until the whole app was restarted.
        """
        self._saved[stable_key] = layout.Entry(rect, locked)
        self._on_layout_changed(stable_key, rect, locked)

    def request_sweep(self) -> None:
        """Ask for an immediate sweep. Safe from any thread."""
        if self._hwnd:
            win32.bind().user32.PostMessageW(self._hwnd,
                                             win32.WM_APP_SWEEP_NOW, 0, 0)

    # ---- everything below runs ON the preview thread -------------------

    def _run(self) -> None:
        from ctypes import wintypes
        libs = win32.bind()

        # First, before any window exists. Thread-local, so the process
        # keeps the PROCESS_SYSTEM_DPI_AWARE contract __main__.py:99-114
        # deliberately chose and ui/chrome.py:177-186 depends on. Verified
        # to isolate correctly on a 192-DPI monitor.
        prev = libs.user32.SetThreadDpiAwarenessContext(
            ctypes.c_void_p(win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
        logger.debug("Preview thread DPI override accepted: %s", bool(prev))

        self._hwnd = self._create_host_window(libs)
        if not self._hwnd:
            logger.error("Preview host window could not be created; "
                         "previews are disabled for this session")
            return

        self._sweep(libs)
        self._install_hook(libs)
        libs.user32.SetTimer(self._hwnd, ctypes.c_void_p(SWEEP_TIMER_ID),
                             SWEEP_MS, None)
        self._ready.set()

        msg = wintypes.MSG()
        while libs.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            libs.user32.TranslateMessage(ctypes.byref(msg))
            libs.user32.DispatchMessageW(ctypes.byref(msg))

    def _create_host_window(self, libs):
        """A message-only window that outlives every preview.

        Not optional: PostMessageW needs an HWND, and there is no preview
        to post to when zero clients are running -- which is the state at
        startup and after the last client quits. Without this, stop() has
        nothing to signal and blocks until its timeout on exactly the
        paths that matter most.
        """
        from ctypes import wintypes

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT),
                        ("lpfnWndProc", win32.wndproc_type()),
                        ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR)]

        proc = win32.wndproc_type()(self._host_proc)
        win32._KEEPALIVE.append(proc)
        cls = WNDCLASSW()
        cls.lpfnWndProc = proc
        cls.hInstance = libs.kernel32.GetModuleHandleW(None)
        cls.lpszClassName = "WingmanPreviewHost"
        libs.user32.RegisterClassW(ctypes.byref(cls))
        return libs.user32.CreateWindowExW(
            0, "WingmanPreviewHost", "wingman-preview-host", 0, 0, 0, 0, 0,
            wintypes.HWND(win32.HWND_MESSAGE), None, cls.hInstance, None)

    def _host_proc(self, hwnd, msg, wparam, lparam):
        libs = win32.bind()
        if msg == win32.WM_TIMER and wparam == SWEEP_TIMER_ID:
            self._sweep(libs)
            return 0
        if msg == win32.WM_APP_SWEEP_NOW:
            self._sweep(libs)
            return 0
        if msg == win32.WM_APP_SHUTDOWN:
            self._teardown(libs)
            return 0
        return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _install_hook(self, libs):
        """Foreground changes trigger a sweep, but never inline: the hook
        callback arrives on an arbitrary thread, and touching HWNDs from
        there is the thread-affinity violation that hangs."""
        def on_event(hook, event, hwnd, obj, child, tid, ms):
            self.request_sweep()

        cb = win32.winevent_proc_type()(on_event)
        win32._KEEPALIVE.append(cb)
        self._hook = libs.user32.SetWinEventHook(
            win32.EVENT_SYSTEM_FOREGROUND, win32.EVENT_SYSTEM_FOREGROUND,
            None, cb, 0, 0, win32.WINEVENT_OUTOFCONTEXT)
        if not self._hook:
            logger.warning("SetWinEventHook failed; previews will only "
                           "refresh on the %dms sweep", SWEEP_MS)

    def _sweep(self, libs) -> None:
        clients = {c.stable_key: c for c in discovery.list_clients()}
        discovery.flush_image_cache_periodically()
        added, removed, _kept = reconcile(set(self._windows), set(clients))

        for key in removed:
            self._windows.pop(key).close()

        for key in added:
            client = clients[key]
            entry = self._saved.get(key)
            rect = (entry.rect if entry
                    else geometry.default_stack(len(self._windows),
                                                self._screen(), self._size))
            win = PreviewWindow.create(
                libs, client, rect,
                on_activate=lambda c: None,
                on_rect_changed=self._layout_changed,
                neighbours=lambda k=key: [w.rect for k2, w
                                          in self._windows.items() if k2 != k],
                screen=self._screen,
                # Restored, not defaulted: a preview locked before the last
                # restart must come back locked, or the next drag reports
                # locked=False and erases the flag from settings.
                locked=bool(entry.locked) if entry else False)
            if win is not None:
                self._windows[key] = win

        if added or removed:
            logger.info("Preview sweep: +%s -%s (%d live)",
                        added, removed, len(self._windows))

    def _screen(self):
        """Virtual-desktop bounds, re-read each sweep.

        Not cached for the process: monitors get plugged in, unplugged,
        and rearranged while Wingman runs, and a stale origin puts new
        previews off-screen where they cannot be dragged back.
        """
        libs = win32.bind()
        return geometry.virtual_desktop(libs.user32.GetSystemMetrics)

    def _teardown(self, libs) -> None:
        """Ordered, and all of it on this thread."""
        # First, while the windows still exist and their rects are still
        # readable. Layout writes are debounced by a second, so quitting
        # right after a drag would otherwise discard it. settings.save()
        # is lock-serialised, so writing from this thread is safe.
        if self._flush_layouts is not None:
            try:
                self._flush_layouts()
            except Exception:
                # Teardown must complete. A settings file that cannot be
                # written is not a reason to leak HWNDs and a live pump.
                logger.exception("Could not flush preview layouts on shutdown")
        if self._hook:
            libs.user32.UnhookWinEvent(self._hook)   # 1. hook
            self._hook = None
        for win in list(self._windows.values()):
            win.close()                              # 2. thumbnails + windows
        self._windows.clear()
        if self._hwnd:
            libs.user32.KillTimer(self._hwnd, ctypes.c_void_p(SWEEP_TIMER_ID))
            libs.user32.DestroyWindow(self._hwnd)    # 3. host window
            self._hwnd = None
        libs.user32.PostQuitMessage(0)               # 4. end the pump
