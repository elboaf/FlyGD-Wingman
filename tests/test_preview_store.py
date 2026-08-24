"""The preview thread must never call settings.save() itself: it rewrites
the whole projected document (settings.py:145-149), and there are already
two writers without previews -- ui/api.py persists the channel from an
upload worker thread, deliberately. This store is the merge boundary."""
from obs_youtube_uploader.preview.store import LayoutStore
from obs_youtube_uploader.preview.layout import Entry
from obs_youtube_uploader.preview.geometry import Rect


class FakeTimer:
    """Runs nothing until fire() is called, so debouncing is testable
    without sleeping -- the scheduler.py injection pattern."""

    def __init__(self, interval, fn):
        self.fn, self.cancelled = fn, False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.fn()


def _store(saves, stored=None):
    timers = []

    def timer(interval, fn):
        t = FakeTimer(interval, fn)
        timers.append(t)
        return t

    live = stored if stored is not None else {"preview": {"layouts": {}}}
    s = LayoutStore(save_settings=saves.append,
                    read_settings=lambda: live, timer=timer)
    return s, timers, live


def test_a_drag_does_not_write_once_per_pixel():
    """Dragging emits a rect per mouse-move. Writing each one would
    rewrite the settings file dozens of times a second."""
    saves = []
    s, timers, _ = _store(saves)
    for x in range(20):
        s.record("Pilot", Entry(Rect(x, 0, 320, 210)))
    assert saves == []
    timers[-1].fire()
    assert len(saves) == 1


def test_the_last_position_is_the_one_written():
    saves = []
    s, timers, _ = _store(saves)
    s.record("Pilot", Entry(Rect(1, 0, 320, 210)))
    s.record("Pilot", Entry(Rect(9, 0, 320, 210)))
    timers[-1].fire()
    assert saves[0]["preview"]["layouts"]["Pilot"]["x"] == 9


def test_flush_writes_immediately_for_shutdown():
    saves = []
    s, _, _ = _store(saves)
    s.record("Pilot", Entry(Rect(1, 2, 320, 210)))
    s.flush()
    assert len(saves) == 1


def test_layouts_for_clients_not_running_are_preserved():
    """THE bug this store exists to avoid. You multibox thirty characters
    and log in two. If the write replaces `layouts` with only what was
    seen this session, the other twenty-eight lose their saved positions
    -- and the user finds out weeks later, once, with no way back."""
    saves = []
    stored = {"preview": {"layouts": {
        "Absent Pilot": {"x": 7, "y": 7, "w": 320, "h": 210,
                         "locked": False}}}}
    s, timers, _ = _store(saves, stored)
    s.record("Present Pilot", Entry(Rect(1, 2, 320, 210)))
    timers[-1].fire()
    written = saves[0]["preview"]["layouts"]
    assert set(written) == {"Absent Pilot", "Present Pilot"}
    assert written["Absent Pilot"]["x"] == 7


def test_reads_settings_at_write_time_not_at_construction():
    """settings.save() projects the WHOLE document, so saving from a
    snapshot taken earlier writes back stale values for every unrelated
    key -- including ones another thread changed in between."""
    saves = []
    live = {"preview": {"layouts": {}}, "channel_title": "before"}
    s, timers, _ = _store(saves, live)
    s.record("Pilot", Entry(Rect(1, 2, 320, 210)))
    live["channel_title"] = "changed by another thread"
    timers[-1].fire()
    assert saves[0]["channel_title"] == "changed by another thread"


def test_flush_with_nothing_pending_does_not_write():
    """Shutdown always flushes. It must not rewrite the file for a session
    where no preview ever moved."""
    saves = []
    s, _, _ = _store(saves)
    s.flush()
    assert saves == []
