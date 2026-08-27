"""The preview thread must never call settings.save() itself: it rewrites
the whole projected document (settings.py:281-285), and there are already
two writers without previews -- ui/api.py persists the channel from an
upload worker thread, deliberately. This store is the merge boundary."""

import contextlib
import copy

from wingman.preview import layout
from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry
from wingman.preview.store import LayoutStore


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


class _ImmediateTimer:
    """Fires on start() instead of after a delay, so debounce does not make
    the test sleep."""

    def __init__(self, delay, fn):
        self._fn = fn

    def start(self):
        self._fn()

    def cancel(self):
        pass


def _store(saves, stored=None):
    """update_settings= is a zero-arg context-manager factory now, not a
    save_settings/read_settings pair. `saves` still collects one snapshot
    per completed write -- taken after the `with` body runs, so it reflects
    whatever the block (or a concurrent mutation of `live`) left behind --
    to keep the existing per-write assertions unchanged."""
    timers = []

    def timer(interval, fn):
        t = FakeTimer(interval, fn)
        timers.append(t)
        return t

    live = stored if stored is not None else {"preview": {"layouts": {}}}

    @contextlib.contextmanager
    def update_settings():
        yield live
        saves.append(copy.deepcopy(live))

    s = LayoutStore(update_settings=update_settings, timer=timer)
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
    stored = {
        "preview": {
            "layouts": {
                "Absent Pilot": {"x": 7, "y": 7, "w": 320, "h": 210, "locked": False}
            }
        }
    }
    s, timers, _ = _store(saves, stored)
    s.record("Present Pilot", Entry(Rect(1, 2, 320, 210)))
    timers[-1].fire()
    written = saves[0]["preview"]["layouts"]
    assert set(written) == {"Absent Pilot", "Present Pilot"}
    assert written["Absent Pilot"]["x"] == 7


def test_reads_settings_at_write_time_not_at_construction():
    """settings.update() re-yields the LIVE dict at write time, so saving
    from a snapshot taken earlier would write back stale values for every
    unrelated key -- including ones another thread changed in between."""
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


def test_write_goes_through_one_atomic_transaction():
    """The store must not read settings, mutate, and save as three steps:
    another writer can land between the read and the save and lose one
    side's keys entirely."""
    live = {"preview": {"layouts": {}}}
    opened = []

    @contextlib.contextmanager
    def fake_update():
        opened.append("enter")
        yield live
        opened.append("exit")

    store = LayoutStore(update_settings=fake_update, timer=_ImmediateTimer)
    store.record("Scout Alt", layout.Entry(Rect(1, 2, 3, 4), False))
    store.flush()

    assert opened == ["enter", "exit"]
    assert live["preview"]["layouts"]["Scout Alt"] == {
        "x": 1,
        "y": 2,
        "w": 3,
        "h": 4,
        "locked": False,
    }


def _updater(live, log=None):
    import contextlib

    @contextlib.contextmanager
    def fake_update():
        if log is not None:
            log.append("enter")
        yield live
        if log is not None:
            log.append("exit")

    return fake_update


def test_record_character_moves_a_seen_name_to_the_front():
    live = {"preview": {"seen": ["Bravo", "Alice"]}}
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("Alice")
    store.flush()
    assert live["preview"]["seen"] == ["Alice", "Bravo"]


def test_record_character_never_persists_a_character_select_client():
    live = {"preview": {"seen": []}}
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("hwnd:0x1234")
    store.flush()
    assert live["preview"]["seen"] == []


def test_a_bound_character_is_protected_from_eviction():
    live = {
        "preview": {
            "seen": [f"C{i}" for i in range(64)],
            "hotkeys": {"characters": {"C63": "Ctrl+F1"}},
        }
    }
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("New")
    store.flush()
    assert "C63" in live["preview"]["seen"]


def test_an_opted_out_character_is_protected_from_eviction():
    """Exactly the hazard the bound-character protection above exists for,
    on the other per-character setting that has no layouts entry.

    A character in preview.excluded with no keybind is the one who most
    needs their row: the row is the only place to turn their preview back
    on. Evicting them from `seen` while they are logged off leaves the
    opt-out in force with nothing on the page to reverse it -- the setting
    outlives the row that owns it, which is the same shape as a chord the
    bind list cannot show.
    """
    live = {
        "preview": {
            "seen": [f"C{i}" for i in range(64)],
            "hotkeys": {"characters": {}},
            "excluded": ["C63"],
        }
    }
    store = LayoutStore(update_settings=_updater(live), timer=_ImmediateTimer)
    store.record_character("New")
    store.flush()
    assert "C63" in live["preview"]["seen"]


def test_layout_and_roster_writes_share_one_transaction():
    """A drag and a discovery landing together must not open the settings
    document twice.

    Uses FakeTimer, not _ImmediateTimer: _ImmediateTimer fires synchronously
    on start(), so record() and record_character() would each open their own
    transaction before the other call ever lands -- exactly the double-open
    this test exists to catch. FakeTimer defers (start() is a no-op) and
    flush() calls _write() directly, so both pending kinds land together."""
    live = {"preview": {"layouts": {}, "seen": []}}
    opened = []
    store = LayoutStore(update_settings=_updater(live, opened), timer=FakeTimer)
    store.record("Alice", layout.Entry(Rect(1, 2, 3, 4), False))
    store.record_character("Alice")
    store.flush()
    assert opened.count("enter") == 1
    assert live["preview"]["seen"] == ["Alice"]
    assert "Alice" in live["preview"]["layouts"]


def test_clear_empties_every_saved_layout():
    live = {"preview": {"layouts": {"Alice": {"x": 1, "y": 2, "w": 3, "h": 4}}}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.clear()
    assert live["preview"]["layouts"] == {}


def test_clear_drops_a_pending_layout_write():
    """A drag that ended under a second ago has an unwritten entry. If the
    debounce fires after the clear it resurrects exactly one preview's old
    position -- intermittently, which is the worst way for this to fail."""
    live = {"preview": {"layouts": {}}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.record("Alice", Entry(Rect(1, 2, 3, 4)))
    timer = store._timer
    store.clear()
    assert timer.cancelled
    assert live["preview"]["layouts"] == {}


def test_clear_keeps_a_pending_roster_name():
    """record_character shares this one timer deliberately, so cancelling
    without draining it silently loses a character discovered moments
    before the reset -- and any binding whose row it is the reason for."""
    live = {"preview": {"layouts": {}, "seen": []}}
    store = LayoutStore(_updater(live), timer=FakeTimer)
    store.record_character("Bob")
    store.clear()
    assert live["preview"]["seen"] == ["Bob"]
