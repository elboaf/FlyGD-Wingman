"""Debounced, merging writer for preview layouts.

The preview thread owns layout state in memory but never touches the
settings file. It records deltas here; this class merges them into the
live settings dict and calls the injected saver.

Two rules the tests pin, both of which a naive implementation breaks:

  * Merge per key, never wholesale. Replacing `preview.layouts` with only
    the previews seen this session deletes the saved position of every
    client that happened not to be running -- which is most of them, most
    of the time.
  * Read the settings document at write time, never from a snapshot.
    settings.save() projects the complete document, so an older snapshot
    writes back stale values for unrelated keys that other threads own.
"""
import logging
import threading

from . import layout

logger = logging.getLogger(__name__)

DEBOUNCE_S = 1.0


class LayoutStore:
    def __init__(self, save_settings, read_settings, debounce_s=DEBOUNCE_S,
                 timer=threading.Timer):
        self._save_settings = save_settings
        self._read_settings = read_settings
        self._debounce_s = debounce_s
        self._timer_factory = timer
        self._pending = {}
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
            self._timer = None
        if not pending:
            return
        try:
            live = self._read_settings()
            section = live.setdefault("preview", {})
            layouts = dict(section.setdefault("layouts", {}))
            layouts.update(layout.serialize(pending))   # per-key merge
            section["layouts"] = layouts
            self._save_settings(live)
        except OSError:
            # A settings file that cannot be written must not take the
            # preview thread down -- same posture as ui/api.py's channel
            # persist, which swallows OSError for the same reason.
            logger.exception("Could not persist preview layouts")
