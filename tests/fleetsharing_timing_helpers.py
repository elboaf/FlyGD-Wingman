"""Test-only consumer ticket; this is not producer authority or identity proof."""

import threading


class FakePublicationSource:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self._lock = threading.Lock()
        self._current = True

    @property
    def snapshot(self):
        return self._snapshot

    def revoke(self):
        with self._lock:
            self._current = False

    def is_current(self):
        with self._lock:
            return self._current

    def admit_start(self, validate):
        with self._lock:
            if not self._current:
                return False
            validate()
            return True
