"""Save and restore where the EVE client windows themselves sit.

Distinct from layout.py + store.py, which persist where the preview TILES
sit. Those are dragged continuously and need a debounced writer; these are
snapshotted on a button press and do not.

Independent of preview.enabled on purpose: no preview thread, no 700ms
sweep, no DWM. The watcher is this module's own Scheduler, which is what
lets host.py stay untouched and the feature work with previews off.

Every Win32 collaborator is a constructor parameter -- the discipline
discovery.list_clients sets with enumerator/pids/image_name -- so the
orchestration, which is where the interesting bugs live, runs on
ubuntu-latest.
"""
import logging
import threading

from ..ui.scheduler import Scheduler
from . import placement as placement_mod

logger = logging.getLogger(__name__)

INTERVAL_S = 2.0

# Two consecutive NON-EMPTY sweeps before a key is forgotten. See _prune.
PRUNE_AFTER_MISSES = 2

# Clients at character select. Their stable_key is an address reused
# across processes, so a position saved against one would be handed to
# whoever next sits at that screen.
ANONYMOUS_PREFIX = "hwnd:"


class ClientLayoutManager:
    def __init__(self, *, read_settings, update_settings, list_clients,
                 read_placement, apply_placement, work_area_origin,
                 screen, dpi_context, interval_s=INTERVAL_S,
                 timer=threading.Timer):
        self._read_settings = read_settings
        self._update_settings = update_settings
        self._list_clients = list_clients
        self._read_placement = read_placement
        self._apply_placement = apply_placement
        self._work_area_origin = work_area_origin
        self._screen = screen
        self._dpi_context = dpi_context
        # Three callers enter this object: the watcher's timer thread and
        # the two buttons, arriving on pywebview's thread. They mutate the
        # same place-once record and issue the same Win32 calls. Batches
        # are short and rare, so serialising them costs nothing.
        self._lock = threading.Lock()
        self._placed = set()
        self._misses = {}
        self._scheduler = Scheduler(interval_s, self._tick, timer=timer)

    # ---- public ---------------------------------------------------------

    def save_now(self) -> dict:
        with self._lock:
            return self._save()

    def restore_now(self) -> dict:
        """Deliberately ignores the place-once record: this is the one way
        to re-place a client without restarting it, and the recovery path
        when the watcher is off or has already run."""
        with self._lock:
            clients = self._named()
            result = self._restore(clients, list(clients))
            self._placed |= set(clients)
            return result

    def start(self, seed_placed: bool = False) -> None:
        """Arm the watcher.

        `seed_placed` marks everything currently running as already
        placed, so the first tick moves nothing. That is what the toggle
        wants: the label describes clients that LAUNCH, and yanking a
        window the user positioned by hand is the failure place-once
        exists to prevent, arriving through a side door. restore_now()
        stays the way to re-place on demand.

        The launch path leaves it False -- there, placing what is already
        running is the feature.
        """
        if seed_placed:
            with self._lock:
                self._placed |= set(self._named())
        self._scheduler.start()

    def stop(self) -> None:
        self._scheduler.stop()

    # ---- internals ------------------------------------------------------

    def _named(self) -> dict:
        return {c.stable_key: c for c in self._list_clients()
                if not c.stable_key.startswith(ANONYMOUS_PREFIX)}

    def _saved(self) -> dict:
        section = self._read_settings().get("preview", {})
        return placement_mod.deserialize(section.get("client_layouts"))

    def _save(self) -> dict:
        found = {}
        failed = 0
        with self._dpi_context():
            origin = self._work_area_origin()
            for key, c in self._named().items():
                p = self._read_placement(c.hwnd, origin)
                if p is None:
                    logger.warning("Could not read placement for %s", key)
                    # Counted, not just logged: saved: 0 alone cannot tell
                    # the page whether nothing was running or nothing could
                    # be read, and those need different messages.
                    failed += 1
                    continue
                found[key] = p
        if not found:
            return {"saved": 0, "persisted": True, "failed": failed}
        persisted = self._persist(found)
        logger.info("Saved %d client window positions", len(found))
        return {"saved": len(found), "persisted": persisted,
                "failed": failed}

    def _persist(self, found) -> bool:
        def mutate(doc):
            section = doc.setdefault("preview", {})
            layouts = dict(section.get("client_layouts") or {})
            # Per key, never wholesale: replacing the section with only
            # what is running deletes the saved position of every client
            # that happened to be closed.
            layouts.update(placement_mod.serialize(found))
            section["client_layouts"] = layouts

        try:
            # Through settings.update, not save(): the read must happen
            # inside _SAVE_LOCK or a concurrent writer is reverted.
            #
            # settings.update() is a context manager over the LIVE dict,
            # not a (read, mutate) callback pair -- calling it with two
            # positional args builds a generator and discards it unentered,
            # so mutate() never runs and nothing is ever saved (silently:
            # no exception, "persisted": True). self._read_settings() is
            # called here, outside the lock, because it returns that live
            # dict by reference and its identity is stable for the
            # process -- there is no stale-snapshot window for the lock
            # to need to cover.
            with self._update_settings(self._read_settings()) as doc:
                mutate(doc)
        except OSError:
            # Logged, not raised -- a settings file that cannot be written
            # must not take the feature down. But NOT swallowed either:
            # the caller reports the failure to the user.
            logger.exception("Could not persist client window layouts")
            return False
        return True

    def _restore(self, clients, keys) -> dict:
        saved = self._saved()
        restored = skipped = 0
        with self._dpi_context():
            # GetSystemMetrics(SM_*VIRTUALSCREEN) is DPI-virtualized to the
            # calling thread's awareness context, exactly like a window
            # rect. Read outside this scope it comes back in system-DPI
            # units, run under the process default -- while every rect it
            # is compared against below was read inside PMv2, in physical
            # pixels. Comparing the two would silently skip clients on a
            # non-system-DPI monitor as "off-screen".
            screen = self._screen()
            origin = self._work_area_origin()
            for key in keys:
                p = saved.get(key)
                if p is None:
                    continue      # Nothing saved; nothing went wrong.
                if not placement_mod.is_reachable(p.rect, screen):
                    logger.warning(
                        "Not restoring %s: saved rect %s is not reachable on "
                        "the current desktop %s", key, p.rect, screen)
                    skipped += 1
                    continue
                if self._apply_placement(clients[key].hwnd, p, origin):
                    logger.info("Restored %s to %s", key, p.rect)
                    restored += 1
                else:
                    logger.warning("Could not place %s", key)
                    skipped += 1
        return {"restored": restored, "skipped": skipped}

    def _tick(self) -> None:
        with self._lock:
            clients = self._named()
            if clients:
                self._prune(set(clients))
            # An EMPTY result prunes nothing. A failed EnumWindows returns
            # [] (discovery.py:52-56) and is indistinguishable from "no
            # clients running"; the safe reading is the first.
            fresh = [k for k in clients if k not in self._placed]
            if not fresh:
                return
            self._restore(clients, fresh)
            # Marked placed even when nothing was saved for them, so they
            # are not re-examined every tick. Saving a position while a
            # client runs therefore takes effect at its next launch --
            # correct, since the alternative is a save button that moves
            # the window it just measured.
            self._placed |= set(fresh)

    def _prune(self, present: set) -> None:
        """Forget a key only after two consecutive non-empty misses.

        One absence does not prove a client exited: discovery omits a
        client when its PID or image-name lookup raises
        (discovery.py:62-68). Pruning immediately would let a transient
        miss re-place a running client the user has since dragged -- which
        is exactly the undraggable window place-once exists to prevent,
        arriving through a side door.
        """
        for key in list(self._placed):
            if key in present:
                self._misses.pop(key, None)
                continue
            self._misses[key] = self._misses.get(key, 0) + 1
            if self._misses[key] >= PRUNE_AFTER_MISSES:
                self._placed.discard(key)
                del self._misses[key]
