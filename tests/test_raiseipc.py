"""The raise-event seam between first and second instances (#257).

The Win32 calls themselves are kernel one-liners; what is worth pinning is
the contract around them: off-Windows everything degrades to no-ops, the
waiter dies on a failed wait instead of spinning hot, and one handler
exception never retires the thread -- a raise racing quit would otherwise
silently end the very thread every later second launch depends on.
"""

import threading

from wingman import raiseipc


def test_off_windows_creating_and_signalling_do_nothing(monkeypatch):
    monkeypatch.setattr(raiseipc.sys, "platform", "linux")
    assert raiseipc.create_raise_event() is None
    assert raiseipc.signal_raise() is False


def test_the_waiter_never_starts_without_an_event():
    assert raiseipc.start_waiter(None, lambda: None) is None


def test_the_waiter_dispatches_once_per_signal(monkeypatch):
    waits = iter([True, True, False])
    monkeypatch.setattr(raiseipc, "_wait_for_signal", lambda handle: next(waits))
    raises = []
    done = threading.Event()

    def on_raise():
        raises.append(4242)
        if len(raises) == 2:
            done.set()

    thread = raiseipc.start_waiter(4242, on_raise)
    assert done.wait(5)
    thread.join(5)
    assert not thread.is_alive(), "waiter did not stop when the wait failed"
    assert raises == [4242, 4242]


def test_one_failed_handler_does_not_retire_the_waiter(monkeypatch):
    waits = iter([True, True, False])
    monkeypatch.setattr(raiseipc, "_wait_for_signal", lambda handle: next(waits))
    attempted = []

    def on_raise():
        attempted.append(True)
        if len(attempted) == 1:
            raise RuntimeError("show() on a window being destroyed")

    thread = raiseipc.start_waiter(4242, on_raise)
    thread.join(5)
    assert not thread.is_alive(), "waiter stopped after one handler exception"
    assert len(attempted) == 2


def test_a_failed_wait_stops_the_waiter(monkeypatch):
    monkeypatch.setattr(raiseipc, "_wait_for_signal", lambda handle: False)

    def on_raise():  # pragma: no cover - must never run
        raise AssertionError("dispatched on a failed wait")

    thread = raiseipc.start_waiter(4242, on_raise)
    thread.join(5)
    assert not thread.is_alive()
