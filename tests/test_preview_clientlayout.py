"""Save/restore orchestration for EVE client windows.

Every Win32 collaborator is injected, following discovery.list_clients'
enumerator/pids/image_name pattern, so the logic worth testing runs on
ubuntu-latest. Nothing here imports ctypes.
"""
import contextlib
import threading

import pytest

from obs_youtube_uploader.preview.clientlayout import ClientLayoutManager
from obs_youtube_uploader.preview.geometry import Rect
from obs_youtube_uploader.preview.placement import Placement

SCREEN = Rect(0, 0, 1920, 1080)


class FakeClient:
    def __init__(self, key, hwnd):
        self.stable_key, self.hwnd = key, hwnd


def client(key, hwnd=1):
    return FakeClient(key, hwnd)


class Harness:
    """Collects everything the manager was given and everything it did."""

    def __init__(self, clients=(), saved=None, placements=None,
                 apply_ok=True, raise_on_save=None):
        self.clients = list(clients)
        self.doc = {"preview": {"client_layouts": dict(saved or {})}}
        self.placements = dict(placements or {})
        self.apply_ok = apply_ok
        self.raise_on_save = raise_on_save
        self.applied = []
        self.writes = 0
        self.dpi_depth = 0
        self.reads_inside_dpi = []

    # --- injected collaborators
    def list_clients(self):
        return list(self.clients)

    def read_settings(self):
        return self.doc

    def update_settings(self, read, mutate):
        if self.raise_on_save is not None:
            raise self.raise_on_save
        doc = read()
        mutate(doc)
        self.writes += 1

    def read_placement(self, hwnd, origin):
        self.reads_inside_dpi.append(self.dpi_depth > 0)
        return self.placements.get(hwnd)

    def apply_placement(self, hwnd, placement, origin):
        self.applied.append((hwnd, placement))
        return self.apply_ok

    def work_area_origin(self):
        return (0, 0)

    def screen(self):
        return SCREEN

    @contextlib.contextmanager
    def dpi_context(self):
        self.dpi_depth += 1
        try:
            yield True
        finally:
            self.dpi_depth -= 1

    def manager(self, **kw):
        return ClientLayoutManager(
            read_settings=self.read_settings,
            update_settings=self.update_settings,
            list_clients=self.list_clients,
            read_placement=self.read_placement,
            apply_placement=self.apply_placement,
            work_area_origin=self.work_area_origin,
            screen=self.screen, dpi_context=self.dpi_context, **kw)


def entry(x, y, w, h, maximized=False):
    return {"x": x, "y": y, "w": w, "h": h, "maximized": maximized}


# ---- save ---------------------------------------------------------------

def test_save_stores_every_named_client():
    h = Harness(clients=[client("Pilot One", 1), client("Pilot Two", 2)],
                placements={1: Placement(Rect(0, 0, 800, 600)),
                            2: Placement(Rect(10, 10, 800, 600), True)})
    assert h.manager().save_now() == {"saved": 2, "persisted": True}
    stored = h.doc["preview"]["client_layouts"]
    assert set(stored) == {"Pilot One", "Pilot Two"}
    assert stored["Pilot Two"]["maximized"] is True


def test_save_excludes_a_client_at_character_select():
    """hwnd: keys are an address reused across processes. Persisting one
    hands that position to whoever next sits at that screen."""
    h = Harness(clients=[client("hwnd:0xdead", 1)],
                placements={1: Placement(Rect(0, 0, 800, 600))})
    assert h.manager().save_now()["saved"] == 0
    assert h.doc["preview"]["client_layouts"] == {}


def test_save_merges_per_key_and_keeps_absent_characters():
    """Replacing the section with only what is running deletes the saved
    position of every client that happened to be closed -- which is most
    of them, most of the time."""
    h = Harness(clients=[client("Running", 1)],
                saved={"Closed": entry(5, 5, 100, 100)},
                placements={1: Placement(Rect(0, 0, 800, 600))})
    h.manager().save_now()
    assert set(h.doc["preview"]["client_layouts"]) == {"Closed", "Running"}


def test_save_skips_a_client_whose_placement_cannot_be_read():
    h = Harness(clients=[client("Good", 1), client("Unreadable", 2)],
                placements={1: Placement(Rect(0, 0, 800, 600))})
    assert h.manager().save_now()["saved"] == 1


def test_save_reads_placements_inside_the_dpi_scope():
    """Outside it, rects are virtualized to system DPI and disagree with
    whatever a restore later reads."""
    h = Harness(clients=[client("Pilot", 1)],
                placements={1: Placement(Rect(0, 0, 800, 600))})
    h.manager().save_now()
    assert h.reads_inside_dpi == [True]


def test_save_reports_a_failed_write_rather_than_a_false_success():
    """Saying "Saved 5 positions" after the write failed is a lie the user
    discovers at their next restart."""
    h = Harness(clients=[client("Pilot", 1)],
                placements={1: Placement(Rect(0, 0, 800, 600))},
                raise_on_save=OSError("disk full"))
    assert h.manager().save_now() == {"saved": 1, "persisted": False}


def test_save_does_not_write_when_it_found_nothing():
    h = Harness(clients=[])
    assert h.manager().save_now() == {"saved": 0, "persisted": True}
    assert h.writes == 0


# ---- restore ------------------------------------------------------------

def test_restore_moves_a_client_with_a_saved_position():
    h = Harness(clients=[client("Pilot", 7)],
                saved={"Pilot": entry(100, 200, 800, 600)})
    assert h.manager().restore_now() == {"restored": 1, "skipped": 0}
    hwnd, p = h.applied[0]
    assert hwnd == 7 and p == Placement(Rect(100, 200, 800, 600), False)


def test_restore_ignores_a_client_with_no_saved_position():
    """Not a skip -- there is nothing to do and nothing went wrong."""
    h = Harness(clients=[client("Stranger", 1)])
    assert h.manager().restore_now() == {"restored": 0, "skipped": 0}
    assert h.applied == []


def test_restore_skips_an_unreachable_rect():
    """A saved rect on a monitor since unplugged would put a client where
    the user cannot see or reach it."""
    h = Harness(clients=[client("Pilot", 1)],
                saved={"Pilot": entry(5000, 200, 800, 600)})
    assert h.manager().restore_now() == {"restored": 0, "skipped": 1}
    assert h.applied == []


def test_restore_excludes_a_client_at_character_select():
    h = Harness(clients=[client("hwnd:0xdead", 1)],
                saved={"hwnd:0xdead": entry(100, 200, 800, 600)})
    assert h.manager().restore_now() == {"restored": 0, "skipped": 0}
    assert h.applied == []


def test_restore_counts_a_failed_apply_as_skipped():
    h = Harness(clients=[client("Pilot", 1)],
                saved={"Pilot": entry(100, 200, 800, 600)}, apply_ok=False)
    assert h.manager().restore_now() == {"restored": 0, "skipped": 1}


def test_restore_carries_maximized_through():
    h = Harness(clients=[client("Pilot", 1)],
                saved={"Pilot": entry(100, 200, 800, 600, maximized=True)})
    h.manager().restore_now()
    assert h.applied[0][1].maximized is True


def test_batches_are_serialised_by_the_manager_lock():
    """The watcher thread and both buttons mutate the same state."""
    h = Harness(clients=[client("Pilot", 1)],
                saved={"Pilot": entry(100, 200, 800, 600)})
    m = h.manager()
    assert isinstance(m._lock, type(threading.Lock()))
    with m._lock:
        assert not m._lock.acquire(blocking=False)
