"""The replacement for root.after()'s self-rescheduling poll loop.

Tk's event loop is gone, and pywebview has no equivalent of `after`. The
watcher poll, the deferred-refresh flag, and the probe drain all rode on it.
The guarantee that has to survive the move is the one __main__.poll()
expressed as a try/finally: the loop reschedules itself no matter what the
body did, because a poll_once() error must not permanently and silently
kill the watcher.

Timers are injected so these tests are instant and deterministic -- nothing
here sleeps, and a real threading.Timer would make the always-reschedule
assertions timing-dependent, which is the one property they must not have.
"""

import threading

from wingman.ui.scheduler import Scheduler


class FakeTimer:
    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.cancelled = False
        self.started = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class FakeClock:
    """Hands out FakeTimers and lets a test fire the armed one."""

    def __init__(self):
        self.timers: list[FakeTimer] = []

    def timer(self, interval, fn):
        made = FakeTimer(interval, fn)
        self.timers.append(made)
        return made

    def fire(self):
        armed = self.timers[-1]
        assert not armed.cancelled, "fired a cancelled timer"
        armed.fn()


def test_start_arms_a_timer_without_running_the_body():
    clock = FakeClock()
    calls = []
    Scheduler(3.0, lambda: calls.append(1), timer=clock.timer).start()

    assert calls == []
    assert len(clock.timers) == 1
    assert clock.timers[0].interval == 3.0
    assert clock.timers[0].started


def test_timers_are_daemon_threads():
    # A live non-daemon timer keeps the process alive after webview.start()
    # returns, so the app would sit invisible in Task Manager after Quit.
    clock = FakeClock()
    Scheduler(3.0, lambda: None, timer=clock.timer).start()

    assert clock.timers[0].daemon is True


def test_each_tick_runs_the_body_and_rearms():
    clock = FakeClock()
    calls = []
    Scheduler(3.0, lambda: calls.append(1), timer=clock.timer).start()

    clock.fire()
    clock.fire()

    assert calls == [1, 1]
    assert len(clock.timers) == 3  # initial + one re-arm per tick


def test_a_raising_body_never_stops_the_loop():
    """__main__.poll()'s try/finally, preserved.

    This is the whole reason the class exists rather than a bare recursive
    Timer: an unreachable recording folder raises out of poll_once() every
    single tick, and the loop has to keep going so the watcher recovers by
    itself when the drive comes back.
    """
    clock = FakeClock()
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("network drive vanished")

    Scheduler(3.0, boom, timer=clock.timer).start()
    for _ in range(3):
        clock.fire()

    assert calls == [1, 1, 1]
    assert not clock.timers[-1].cancelled


def test_stop_cancels_the_armed_timer_and_prevents_rearming():
    clock = FakeClock()
    calls = []
    sched = Scheduler(3.0, lambda: calls.append(1), timer=clock.timer)
    sched.start()

    sched.stop()

    assert clock.timers[-1].cancelled
    assert len(clock.timers) == 1
    assert calls == []


def test_stop_from_inside_the_body_does_not_rearm():
    """The probe drain stops itself the tick it sees its sentinel.

    Naive rescheduling in a `finally` re-arms after that stop() and the loop
    outlives the work it was created for -- one leaked timer per refresh.
    """
    clock = FakeClock()
    sched = None
    calls = []

    def body():
        calls.append(1)
        sched.stop()

    sched = Scheduler(0.1, body, timer=clock.timer)
    sched.start()
    clock.fire()

    assert calls == [1]
    assert len(clock.timers) == 1, "re-armed after stop()"


def test_start_is_idempotent():
    # list_rows() can be re-entered by a watcher tick landing on a manual
    # refresh; a second start must not leave two loops running at double rate.
    clock = FakeClock()
    sched = Scheduler(3.0, lambda: None, timer=clock.timer)
    sched.start()
    sched.start()

    assert len(clock.timers) == 1


def test_stop_before_start_is_harmless():
    Scheduler(3.0, lambda: None, timer=FakeClock().timer).stop()


def test_default_timer_is_threading_timer():
    # The injection point exists for tests; production must not have to
    # remember to pass a real timer.
    sched = Scheduler(0.01, lambda: None)
    assert sched._timer_factory is threading.Timer
