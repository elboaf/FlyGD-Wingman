"""Persistent cache of ffprobe durations, keyed on file identity.

Probing is by far the most expensive thing the video list does: one
``ffprobe`` process per recording, and ``UploaderWindow.refresh()`` runs on
app launch, on every tray open, after every settings save, after a delete,
and whenever the watcher finds new recordings. Without a cache a folder of
N recordings pays N process spawns every single time, on the Tk main
thread, with the window frozen for the duration.

The key is ``(size, mtime)`` rather than the path alone, so a recording
that is still being written -- same path, growing size -- can never serve a
stale duration. That is the same identity ``watcher.SeenEntry`` uses, for
the same reason.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    size: int
    mtime: float
    duration: float | None


def load(path: Path) -> dict[str, CacheEntry]:
    """Read the cache, degrading to empty rather than raising.

    A missing, unreadable, or corrupt cache is not an error: it just means
    everything gets probed once more. Individual malformed entries are
    skipped instead of discarding the whole file, so one bad record cannot
    cost the user a full re-probe of the entire folder.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, CacheEntry] = {}
    for key, value in raw.items():
        try:
            duration = value["duration"]
            # None is a legitimate stored value -- see remember() -- so it
            # must survive the float() coercion applied to real durations.
            out[key] = CacheEntry(
                size=int(value["size"]),
                mtime=float(value["mtime"]),
                duration=None if duration is None else float(duration),
            )
        except (TypeError, KeyError, ValueError):
            continue
    return out


def save(path: Path, cache: dict[str, CacheEntry]) -> None:
    """Persist the cache, treating failure as "no cache this run".

    Never raises: this is called from a refresh, and a read-only or full
    disk must cost the user speed, not a crashed window. Losing the write
    only means the next launch re-probes.
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {"size": e.size, "mtime": e.mtime, "duration": e.duration}
            for key, e in cache.items()
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.warning("Could not persist duration cache to %s", path, exc_info=True)


def lookup(cache: dict[str, CacheEntry], video_path: Path,
           size: int, mtime: float) -> tuple[bool, float | None]:
    """Return ``(hit, duration)`` for this exact version of the file.

    The boolean is not redundant with the duration: ``(True, None)`` means
    ffprobe ran on this file and could not read a duration, while
    ``(False, None)`` means it has not been probed yet. Collapsing the two
    is what would make the combat-log upload tell a user that ffprobe is
    unavailable when it is merely still working.
    """
    entry = cache.get(str(video_path))
    if entry is None or entry.size != size or entry.mtime != mtime:
        return False, None
    return True, entry.duration


def remember(cache: dict[str, CacheEntry], video_path: Path,
             size: int, mtime: float, duration: float | None) -> None:
    """Record a probe result, including a definitive failure.

    Storing ``None`` is deliberate but narrow. A file ffprobe ran on and
    could not read (truncated, corrupt, a codec it does not know) would
    otherwise cost a fresh subprocess on every refresh, forever. Only pass
    a None that ``library.probe`` reported as definitive: a probe that
    never ran (no binary, launch failure, timeout) must not be recorded,
    because the (size, mtime) key never changes again for a finished
    recording and the bad answer would outlive whatever caused it.
    """
    cache[str(video_path)] = CacheEntry(size=size, mtime=mtime, duration=duration)


def resolve(cache: dict[str, CacheEntry], infos: list) -> list:
    """Fill in cached durations; return the entries still needing a probe.

    Mutates each hit in place (``duration`` and ``probed``) so the caller
    can render the list immediately and hand only the returned remainder to
    a background worker.
    """
    pending = []
    for info in infos:
        hit, duration = lookup(cache, info.path, info.size, info.mtime)
        if hit:
            info.duration = duration
            info.probed = True
        else:
            pending.append(info)
    return pending


def prune(cache: dict[str, CacheEntry], live_paths) -> int:
    """Keep only entries in *live_paths*. Returns how many were dropped.

    Note this is membership in the list just scanned, NOT existence on
    disk: an entry for a file that still exists somewhere else is dropped
    too. That is deliberate -- the caller passes the recordings it just
    discovered, so pruning costs no extra stat calls, which matters on a
    path that runs on every refresh. The one visible consequence is that
    changing the recording folder in Settings discards the old folder's
    durations, so switching back re-probes it once.

    Callers must not pass an empty list drawn from a scan that may have
    failed: ``library.discover`` returns [] both for an empty folder and
    for an unreachable one, and wiping the whole cache because a network
    drive blipped is exactly the re-probe this module exists to avoid.
    See app.refresh, which skips the prune entirely in that case.

    ``watcher.prune`` is the same idea for seen.json but does test
    ``Path.exists()`` per entry; it can afford to, running once at startup
    rather than on every refresh.
    """
    live = {str(p) for p in live_paths}
    gone = [k for k in cache if k not in live]
    for key in gone:
        del cache[key]
    return len(gone)
