"""A self-rescheduling timer loop: the successor to root.after().

Tk's event loop was doing more than UI. The watcher poll, the deferred
refresh during an upload, and the probe drain all rode on `root.after`, and
`webview.start()` carries none of it. This is the one mechanism that
replaces all three.

The guarantee carried over verbatim from `__main__.poll()` is its
`finally`: the loop re-arms whatever the body did. A poll tick that raises
looks identical to a quiet tick from the outside, and a loop that stopped
on the first raise would leave the tray icon looking healthy while the
watcher did nothing, forever, over an unreachable recording folder that
recovers on its own two minutes later.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, interval_s: float, fn, timer=threading.Timer) -> None:
        self._interval_s = interval_s
        self._fn = fn
        # Injected in tests so the suite neither sleeps nor depends on
        # timing; production always uses threading.Timer.
        self._timer_factory = timer
        self._lock = threading.Lock()
        self._timer = None
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._running:
                return  # Idempotent: a second start must not double the rate.
            self._running = True
        self._arm()

    def stop(self) -> None:
        """Stop the loop, including from inside the body it is running.

        `_running` is what makes the second case work: `_arm` consults it,
        so a stop() called from the body cannot be undone by the re-arm
        that follows the body's return.
        """
        with self._lock:
            self._running = False
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _arm(self) -> None:
        with self._lock:
            if not self._running:
                return
            timer = self._timer_factory(self._interval_s, self._tick)
            # Daemon, so a live timer cannot keep the process alive after
            # webview.start() returns and the tray icon has stopped --
            # otherwise Quit leaves an invisible process behind.
            timer.daemon = True
            self._timer = timer
        # Started outside the lock: threading.Timer.start() spawns a thread,
        # and holding the lock across it would let a tick that fires
        # immediately contend with the arming that produced it.
        timer.start()

    def _tick(self) -> None:
        try:
            self._fn()
        except Exception:
            # Logged rather than propagated: this runs on a timer thread
            # where the traceback would go to stderr, which is nowhere at
            # all in a windowed build.
            logger.warning("Scheduled task failed", exc_info=True)
        finally:
            self._arm()
