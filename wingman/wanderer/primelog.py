"""The debug branch's prime-staging trace: append-one-JSON-line per event.

Built once per launch by `enable()`, then handed to the Wanderer controller
as `prime_log`. The wire record is logged in full; credentials are never
passed to the sink, so nothing secret can reach the file. Every write is
best-effort: a broken log must never disturb staging (ADR 0001 holds even
in a debug build).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

LOG_NAME = "wanderer_prime_debug.log"


def enable() -> Sink | None:
    """Open the log under the state dir's logs/, or None when that fails."""
    from .. import paths

    try:
        directory = paths.log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return Sink(directory)
    except OSError:
        return None


class Sink:
    """Append-and-flush JSON lines; quiet forever after the first failure."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / LOG_NAME
        self._lock = threading.Lock()
        self._broken = False

    def write(self, event: str, **fields) -> None:
        with self._lock:
            if self._broken:
                return
            record = {"ts": time.time(), "event": event, **fields}
            try:
                with open(self._path, "a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(record, ensure_ascii=False, default=str) + "\n"
                    )
                    handle.flush()
            except OSError:
                self._broken = True
