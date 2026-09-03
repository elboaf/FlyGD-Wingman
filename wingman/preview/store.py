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
        # Orders settings writes without making record() wait for disk. In
        # particular, an old debounce that has already woken cannot land
        # after replace() and silently undo the explicit operation.
        self._write_lock = threading.Lock()

    def record(self, stable_key: str, entry) -> None:
        """Note a preview's new position. Safe from the preview thread."""
        with self._lock:
            self._pending[stable_key] = entry
            if self._timer is not None:
                self._timer.cancel()
            timer = self._timer_factory(self._debounce_s, self._write)
            self._timer = timer
        timer.start()

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
            timer = self._timer_factory(self._debounce_s, self._write)
            self._timer = timer
        timer.start()

    def flush(self) -> None:
        """Write now. The host calls this during shutdown, before windows
        are destroyed, or the last drag is lost to the debounce."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._write()

    def _protected(self, section) -> set:
        """Names `seen` must not evict, whatever the cap.

        Two kinds, for one reason: a per-character setting whose subject
        has dropped off the roster is a setting with no row to change it
        from. A bound character would leave a chord the bind list cannot
        show; an opted-out one would leave a preview turned off with
        nothing on the page to turn it back on -- and that one cannot even
        be reversed by logging in, because the whole point is that the
        client no longer produces a preview.

        A third kind: a character mapped in hotkeys.group_by_character has
        a persisted group assignment.  Without a row the assignment select
        never renders, leaving the character silently locked into (or out
        of) a named group with no UI to clear it.
        """
        hotkeys = section.get("hotkeys") or {}
        return (
            set(hotkeys.get("characters") or {})
            | set(section.get("excluded") or [])
            | set(hotkeys.get("group_by_character") or {})
        )

    def replace(self, stable_key: str, entry) -> bool:
        """Persist one explicit layout, superseding an older pending delta.

        Unlike record(), this is a user-facing commit and returns only after
        the settings transaction has completed. Other characters already in
        the debounce remain pending and retain a timer of their own.
        """
        with self._write_lock:
            with self._lock:
                superseded = self._pending.pop(stable_key, None)
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
                timer = None
                if self._pending or self._pending_names:
                    timer = self._timer_factory(self._debounce_s, self._write)
                    self._timer = timer
            try:
                with self._update_settings() as live:
                    section = live.setdefault("preview", {})
                    layouts = dict(section.setdefault("layouts", {}))
                    layouts.update(layout.serialize({stable_key: entry}))
                    section["layouts"] = layouts
            except OSError:
                logger.exception("Could not replace preview layout for %s", stable_key)
                with self._lock:
                    if superseded is not None:
                        self._pending.setdefault(stable_key, superseded)
                    if self._timer is not None:
                        self._timer.cancel()
                    timer = self._timer_factory(self._debounce_s, self._write)
                    self._timer = timer
                timer.start()
                return False
        if timer is not None:
            timer.start()
        return True

    def clear(self) -> None:
        """Discard every saved layout. The one wholesale write this class allows.

        Pending LAYOUT deltas are dropped: they describe positions being
        erased anyway, and a debounce firing after the clear would resurrect
        exactly one preview's old position, intermittently.

        Pending NAMES are kept and written here. record_character shares this
        single timer deliberately (see its docstring), so cancelling without
        draining them would silently lose a character discovered moments
        before the reset -- and with it any binding whose row that character
        is the only reason to show.
        """
        with self._write_lock:
            with self._lock:
                self._pending = {}
                names, self._pending_names = list(self._pending_names), []
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
            try:
                with self._update_settings() as live:
                    section = live.setdefault("preview", {})
                    section["layouts"] = {}
                    for name in names:
                        section["seen"] = roster.touch(
                            section.get("seen", []),
                            name,
                            protected=self._protected(section),
                        )
            except OSError:
                logger.exception("Could not clear preview layouts")

    def _write(self) -> None:
        with self._write_lock:
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
                        # Bound and opted-out characters are protected: see
                        # _protected above for why each would otherwise leave a
                        # setting with no row to change it from.
                        section["seen"] = roster.touch(
                            section.get("seen", []),
                            name,
                            protected=self._protected(section),
                        )
            except OSError:
                # A settings file that cannot be written must not take the
                # preview thread down -- same posture as ui/api.py's channel
                # persist, which swallows OSError for the same reason.
                logger.exception("Could not persist preview state")
