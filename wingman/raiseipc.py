"""Second-launch raises the first instance's window (#257).

The single-instance mutex used to be the end of the story: a second launch
exited silently because the tray icon was "already visible". Issue #257
overturned that — launching from a pinned taskbar icon is how users expect
to get the window back, and the tray is not that.

This is the lightest IPC that crosses the process boundary: one named
auto-reset event. The first instance creates it alongside the mutex and a
daemon thread waits on it forever; a second instance, finding the mutex
taken, sets the event and exits. The waiter then does exactly what the
tray's Open item does — no new interaction with the page, the window or any
worker is invented here.

The raw HANDLE is an int Python never closes, same as the mutex handles in
__main__: the event and the waiter must live for the process's entire
lifetime, and the OS reclaims both on exit. CloseHandle here would be the
bug, not the fix.

Every Win32 call degrades deliberately off-Windows (create/signal do
nothing, the waiter never starts): development and the Linux test runs use
the pure seams — `_wait_for_signal` is monkeypatched in tests, and
`signal_raise` returning False is the "no first instance" answer.
"""

import logging
import sys
import threading

logger = logging.getLogger(__name__)

# Global namespace to match MUTEX_NAME: same reach, same reasoning.
RAISE_EVENT_NAME = "Global\\FlyGDWingmanRaiseWindow"

EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
INFINITE = 0xFFFFFFFF


def create_raise_event() -> int | None:
    """First instance: create the auto-reset raise event; None if it cannot.

    Auto-reset (the second CreateEventW argument False) matters: a burst of
    double-launches leaves at most one pending raise instead of a queue of
    them replaying show() later.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateEventW(None, False, False, RAISE_EVENT_NAME)
    except OSError:
        logger.warning("Could not create the raise event.", exc_info=True)
        return None
    if not handle:
        logger.warning("CreateEventW returned no handle for the raise event.")
        return None
    return handle


def signal_raise() -> bool:
    """Second instance: ask the first one to raise its window. True if sent.

    Best-effort by contract: a False return means the first instance is
    older than this feature (or the event was denied), and the caller falls
    through to the old silent exit. Signalling must never be able to fail a
    launch that would otherwise work.
    """
    if sys.platform != "win32":
        return False
    import ctypes

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, RAISE_EVENT_NAME)
        if not handle:
            return False
        try:
            return bool(kernel32.SetEvent(handle))
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        logger.debug("Could not signal the raise event.", exc_info=True)
        return False


def _wait_for_signal(handle: int) -> bool:
    """Block until the event is signalled. True to dispatch, False to stop.

    WAIT_FAILED (a dead handle, which only shutdown can produce) stops the
    loop; returning True forever on failure would spin the thread hot.
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32
    return kernel32.WaitForSingleObject(handle, INFINITE) == WAIT_OBJECT_0


def start_waiter(handle: int | None, on_raise) -> threading.Thread | None:
    """Run *on_raise* once per signal, on this daemon thread, forever.

    *on_raise* is the tray's on_open, chosen because it is already proven
    safe from a non-main thread and already None-guards the not-yet-created
    window. Its exceptions are swallowed at DEBUG: a raise racing quit (a
    show() on a window being destroyed) must not kill a thread whose death
    would be invisible, and must never reach the app's teardown paths.
    """
    if handle is None:
        return None

    def run():
        while _wait_for_signal(handle):
            try:
                on_raise()
            except Exception:
                logger.debug("Raise handler failed", exc_info=True)

    thread = threading.Thread(target=run, daemon=True, name="raise-waiter")
    thread.start()
    return thread
