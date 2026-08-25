"""Debounced, merging writer for preview layouts.

The preview thread owns layout state in memory but never touches the
settings file. It records deltas here; this class merges them into the
live settings dict and calls the injected saver.

Two rules the tests pin, both of which a naive implementation breaks:

  * Merge per key, never wholesale. Replacing `preview.layouts` with only
    the previews seen this session deletes the saved position of every
    client that happened not to be running -- which is most of them, most
    of the time.
  * Write inside settings.update(), never as a read-then-save pair. The
    document is projected complete from DEFAULTS, so a writer interleaving
    between another writer's read and its save reverts keys it never
    touched.
"""

import logging
import threading

from . import layout, roster

logger = logging.getLogger(__name__)

DEBOUNCE_S = 1.0


class LayoutStore:
    def __init__(self, update_settings, debounce_s=DEBOUNCE_S, timer=threading.Timer):
        # One context manager, not a read/save pair. The pair could not be
        # made atomic by the caller: another writer lands between them and
        # reverts whatever this one did not re-read.
        self._update_settings = update_settings
        self._debounce_s = debounce_s
        self._timer_factory = timer
        self._pending = {}
        self._pending_names = []
        self._timer = None
        self._lock = threading.Lock()

    def record(self, stable_key: str, entry) -> None:
        """Note a preview's new position. Safe from the preview thread."""
        with self._lock:
            self._pending[stable_key] = entry
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._timer_factory(self._debounce_s, self._write)
        self._timer.start()

    def record_character(self, name: str) -> None:
        """Note that *name* was seen. Safe from the preview thread.

        Shares the layout debounce rather than adding a second one: a sweep
        that discovers a client often coincides with a layout write, and two
        timers would open the settings document twice for one event.
        """
        with self._lock:
            if name in self._pending_names:
                return
            self._pending_names.append(name)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self._timer_factory(self._debounce_s, self._write)
        self._timer.start()

    def flush(self) -> None:
        """Write now. The host calls this during shutdown, before windows
        are destroyed, or the last drag is lost to the debounce."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._write()

    def _write(self) -> None:
        with self._lock:
            pending, self._pending = dict(self._pending), {}
            names, self._pending_names = list(self._pending_names), []
            self._timer = None
        if not pending and not names:
            return
        try:
            with self._update_settings() as live:
                section = live.setdefault("preview", {})
                if pending:
                    layouts = dict(section.setdefault("layouts", {}))
                    layouts.update(layout.serialize(pending))  # per-key merge
                    section["layouts"] = layouts
                for name in names:
                    # Bound characters are protected: evicting one would
                    # leave a chord the bind list has no row to show.
                    bound = set(section.get("hotkeys", {}).get("characters", {}))
                    section["seen"] = roster.touch(
                        section.get("seen", []), name, protected=bound
                    )
        except OSError:
            # A settings file that cannot be written must not take the
            # preview thread down -- same posture as ui/api.py's channel
            # persist, which swallows OSError for the same reason.
            logger.exception("Could not persist preview state")
