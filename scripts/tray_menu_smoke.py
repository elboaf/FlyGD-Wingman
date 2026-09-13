"""Interactive Windows tray DPI regression smoke — briefly moves the cursor.

Use a scaled primary and an anchor well inside its work area; --secondary X Y
adds a blank WebView on a 100% secondary. Requires pystray==0.19.5, Pillow,
pywebview==6.2.1 and WebView2. No Wingman runtime/settings; keep hands off the mouse.
"""

import argparse
import ctypes
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes as w
from pathlib import Path


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchor", type=int, nargs=2, required=True, metavar=("X", "Y")
    )
    parser.add_argument("--secondary", type=int, nargs=2, metavar=("X", "Y"))
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if sys.platform != "win32":
        parser.error("Run with a Windows Python interpreter")
    u = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    for name, arguments, result in [
        ("SetThreadDpiAwarenessContext", [w.HANDLE], w.HANDLE),
        ("GetThreadDpiAwarenessContext", [], w.HANDLE),
        ("GetWindowDpiAwarenessContext", [w.HWND], w.HANDLE),
        ("GetAwarenessFromDpiAwarenessContext", [w.HANDLE], ctypes.c_int),
        ("AreDpiAwarenessContextsEqual", [w.HANDLE, w.HANDLE], w.BOOL),
        ("EnumWindows", [enum_proc, w.LPARAM], w.BOOL),
        ("GetWindowRect", [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
        ("GetClassNameW", [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetWindowThreadProcessId", [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
        ("GetDpiForWindow", [w.HWND], w.UINT),
        ("IsWindow", [w.HWND], w.BOOL),
        ("SetPhysicalCursorPos", [ctypes.c_int, ctypes.c_int], w.BOOL),
        ("PostMessageW", [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
    ]:
        function = getattr(u, name)
        function.argtypes, function.restype = arguments, result

    def checked(name, *arguments):
        value = getattr(u, name)(*arguments)
        if not value:
            raise OSError(ctypes.get_last_error(), f"{name} failed")
        return value

    # Match application startup, before WinForms changes the process's DPI mix.
    shcore = ctypes.WinDLL("shcore")
    shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
    shcore.SetProcessDpiAwareness.restype = ctypes.c_long
    require(shcore.SetProcessDpiAwareness(1) == 0, "Cannot set process SYSTEM_AWARE")
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import webview
    from PIL import Image
    from pystray import Menu, MenuItem
    from pystray import _win32 as backend

    from wingman.ui import tray

    errors = []
    returned, stopping, finished = (threading.Event() for _ in range(3))
    awareness = u.GetAwarenessFromDpiAwarenessContext
    context = u.GetThreadDpiAwarenessContext
    equal = u.AreDpiAwarenessContextsEqual
    native = backend.win32

    def report(message):
        print(message, flush=True)

    def record(error):
        errors.append(error)
        traceback.print_exception(error)

    def attempt(action):
        try:
            return action()
        except BaseException as error:  # noqa: BLE001 — transport thread/native failures.
            record(error)
            return None

    def wait_for(predicate, label, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            require(not errors and not stopping.is_set(), f"Aborted: {label}")
            if value := predicate():
                return value
            time.sleep(0.03)
        raise TimeoutError(label)

    def owners():
        values = [
            awareness(checked("GetWindowDpiAwarenessContext", hwnd))
            for hwnd in (icon._hwnd, icon._menu_hwnd)
        ]
        require(values == [1, 1], f"Tray owners are not SYSTEM_AWARE: {values}")
        return values

    icon_type = tray.windows_icon_class(backend.Icon, native)
    image = Image.new("RGB", (16, 16), "navy")
    menu = Menu(MenuItem("Open Wingman", lambda: None), MenuItem("Quit", lambda: None))
    icon = icon_type("tray-smoke", image, "Tray DPI smoke", menu)
    notification = icon._message_handlers[native.WM_NOTIFY]

    def on_notify(wparam, lparam):
        # Instrument real right-click dispatch; never override DPI or the cursor.
        if lparam != native.WM_RBUTTONUP:
            return notification(wparam, lparam)
        before = context()
        require(awareness(before) == 1, "Caller is not SYSTEM_AWARE")
        try:
            return notification(wparam, lparam)
        finally:
            require(equal(before, context()), "Caller context leaked")
            report(f"Caller restored; owners={owners()} (SYSTEM_AWARE)")
            returned.set()

    icon._message_handlers[native.WM_NOTIFY] = lambda wp, lp: attempt(
        lambda: on_notify(wp, lp)
    )

    blank = dict(html="<body></body>", width=250, height=100)
    windows = [webview.create_window("Tray DPI smoke", **blank)]
    if args.secondary:
        x, y = args.secondary
        windows.append(webview.create_window("Tray secondary", x=x, y=y, **blank))
    original_cursor = tray.physical_cursor_position()

    def popups():
        rows = []

        def inspect(hwnd):
            pid, name = w.DWORD(), ctypes.create_unicode_buffer(256)
            # A foreign HWND can disappear during desktop enumeration.
            if not u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
                return
            if pid.value != os.getpid():
                return
            checked("GetClassNameW", hwnd, name, len(name))
            if name.value == "#32768":
                rect = w.RECT()
                checked("GetWindowRect", hwnd, ctypes.byref(rect))
                bounds = (rect.left, rect.top, rect.right, rect.bottom)
                rows.append((bounds, checked("GetDpiForWindow", hwnd)))

        @enum_proc
        def visit(hwnd, _):
            attempt(lambda: inspect(hwnd))
            return not errors

        checked("EnumWindows", visit, 0)
        return rows

    def dismiss():
        for hwnd in (icon._menu_hwnd, icon._hwnd):
            if hwnd and u.IsWindow(hwnd):
                checked("PostMessageW", hwnd, 0x001F, 0, 0)  # WM_CANCELMODE

    def cleanup():
        attempt(dismiss)
        attempt(lambda: checked("SetPhysicalCursorPos", *original_cursor))
        attempt(icon.stop)
        for window in reversed(windows):
            if window.events.shown.is_set() and not window.events.closed.is_set():
                attempt(window.destroy)

    def observe():
        previous = None
        try:
            previous = checked("SetThreadDpiAwarenessContext", w.HANDLE(-4))
            require(equal(context(), w.HANDLE(-4)), "Observer is not PMv2")
            for window in windows:
                wait_for(window.events.shown.is_set, "WebView shown", 15)
                wait_for(window.events.loaded.is_set, "WebView loaded", 15)
            for iteration in range(1, args.repeat + 1):
                report(f"Pass {iteration}: owners={owners()}, anchor={args.anchor}")
                require(not popups(), "Unexpected pre-existing popup")
                checked("SetPhysicalCursorPos", *args.anchor)
                cursor = tray.physical_cursor_position()
                require(cursor == tuple(args.anchor), "Cursor anchor not reached")
                returned.clear()
                message, click = native.WM_NOTIFY, native.WM_RBUTTONUP
                checked("PostMessageW", icon._hwnd, message, 0, click)
                try:
                    wait_for(popups, "Native popup", 3)
                    time.sleep(0.2)  # Let the native menu's opening animation settle.
                    rows = popups()
                    report(f"Physical popup ((left, top, right, bottom), dpi): {rows}")
                    owners()
                    require(len(rows) == 1, "Expected exactly one own-PID popup")
                    right, bottom = rows[0][0][2:]
                    x, y = args.anchor
                    error = max(abs(right - x), abs(bottom - y))
                    require(error <= 2, "Popup missed physical anchor (>2px)")
                finally:
                    dismiss()
                wait_for(returned.is_set, "Notification return", 3)
                wait_for(lambda: not popups(), "Popup dismissal", 3)
        finally:
            cleanup()
            if previous is not None:
                checked("SetThreadDpiAwarenessContext", previous)

    def watchdog():
        if not finished.wait(60 + 10 * args.repeat):
            report("FAIL: native timeout; terminating only this probe")
            attempt(dismiss)
            attempt(lambda: checked("SetPhysicalCursorPos", *original_cursor))
            os._exit(1)  # Releases only this process's native windows/threads.

    threading.excepthook = lambda event: record(event.exc_value)
    pump = threading.Thread(target=lambda: attempt(icon.run), name="tray-pump")
    observer = threading.Thread(target=lambda: attempt(observe), name="PMv2-observer")
    timer = threading.Thread(target=watchdog, name="smoke-watchdog")
    timer.start()
    try:
        pump.start()
        wait_for(lambda: icon.visible, "Tray startup")
        owners()
        observer.start()
        webview.start(gui="edgechromium")
    finally:
        stopping.set()
        if observer.ident is None:
            cleanup()
        for worker in (observer, pump):
            if worker.ident is not None:
                worker.join(12)
        excluded = (threading.current_thread(), timer)
        # WinForms leaves daemon DummyThread markers for native threads;
        # those do not keep Python alive. Our owners must still be joined.
        remaining = [
            t.name
            for t in threading.enumerate()
            if t not in excluded and (t in (observer, pump) or not t.daemon)
        ]
        if remaining:
            report(f"FAIL: threads survived cleanup: {remaining}")
            attempt(lambda: checked("SetPhysicalCursorPos", *original_cursor))
            os._exit(1)
        finished.set()
        timer.join(2)
    require(not errors, f"Smoke failed with {len(errors)} error(s); see tracebacks")
    report("PASS: physical anchors, SYSTEM_AWARE owners and caller restoration")


if __name__ == "__main__":
    main()
