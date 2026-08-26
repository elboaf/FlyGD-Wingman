"""A surviving engine holds a global keyboard hook with no UI to disable it,
so shutdown must stop it on every exit path."""

from wingman import __main__ as main_mod


class Recorder:
    def __init__(self, enabled):
        self.enabled = enabled
        self.started = 0
        self.stopped = 0
        self.recovered = 0

    def start(self):
        self.started += 1
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1

    def apply(self, section):
        pass

    def is_running(self):
        return self.started > self.stopped

    def recover_orphan(self):
        self.recovered += 1


def test_engine_is_not_started_when_disabled():
    engine = Recorder(enabled=False)
    main_mod.start_engine_if_enabled(engine, {"enabled": False})
    assert engine.started == 0


def test_engine_starts_when_enabled():
    engine = Recorder(enabled=True)
    main_mod.start_engine_if_enabled(engine, {"enabled": True})
    assert engine.started == 1


def test_shutdown_stops_a_running_engine():
    engine = Recorder(enabled=True)
    main_mod.start_engine_if_enabled(engine, {"enabled": True})
    main_mod.shutdown_engine(engine)
    assert engine.stopped == 1


def test_shutdown_is_safe_with_no_engine():
    main_mod.shutdown_engine(None)


def test_shutdown_survives_an_engine_that_raises():
    """Shutdown must not be blocked by the thing it is cleaning up."""

    class Angry(Recorder):
        def stop(self, timeout=5.0):
            raise OSError("nope")

    main_mod.shutdown_engine(Angry(enabled=True))


def test_orphans_are_reclaimed_even_when_the_feature_is_disabled():
    """The gap this closes: stop() clears the pid record even when it could
    not confirm death, and recover_orphan() otherwise runs only from
    start(), which runs only when enabled. So a hung engine survives
    indefinitely once the user turns the feature off -- a global keyboard
    hook with nothing left able to reclaim it. Each choice is defensible
    alone; together they leave a hole."""
    engine = Recorder(enabled=False)
    main_mod.reclaim_orphaned_engine(engine)
    assert engine.recovered == 1


def test_reclamation_failure_does_not_block_startup():
    class Angry(Recorder):
        def recover_orphan(self):
            raise OSError("nope")

    main_mod.reclaim_orphaned_engine(Angry(enabled=False))


def test_reclamation_is_safe_with_no_engine():
    main_mod.reclaim_orphaned_engine(None)
