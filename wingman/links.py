"""Persistent record of which recordings have already been uploaded.

The Link column answers one question -- *did I already upload this fight?*
-- and until round 5 it could only answer it for uploads made since the
last launch: ``RowSnapshot._links`` is in-memory, so every fresh start
showed an empty column for recordings that were on YouTube. The normal case
was the broken one.

THE KEY IS ``(size, mtime)``, NOT THE PATH, and here that is a correctness
rule rather than a freshness one. ``durations`` keys the same way so that a
recording still being written -- same path, growing size -- cannot serve a
stale duration, and a wrong duration is cosmetic. A wrong LINK opens
somebody else's video, or a different fight of the user's own: OBS reuses
filenames, and a re-recording at a path that once held an uploaded fight
would inherit its link under a path key. Under this key it cannot, because
the new file's size and mtime differ. Same identity ``watcher.SeenEntry``
uses, for a third reason.

NOTHING PRUNES THIS FILE, and that is the one place it deliberately parts
company with ``durations``. ``durations.prune`` drops every entry outside
the folder just scanned, so changing the recording folder in Settings
discards the old folder's durations -- which costs a re-probe, and re-probes
are what that module exists to avoid paying twice, not something it cannot
pay at all. The same rule here would silently destroy the answer this file
exists to give, permanently, for a folder the user might switch back to.
An orphaned entry costs nothing instead: rows are built from the recording
folder, so an entry for a file that is no longer listed is never looked up.
Growth is bounded by uploads actually performed -- one short JSON object
each, a handful per session -- not by recordings scanned.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from . import atomicio

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinkEntry:
    size: int
    mtime: float
    url: str


def load(path: Path) -> dict[str, LinkEntry]:
    """Read the store, degrading to empty rather than raising.

    A missing, unreadable or corrupt store is not an error: it costs the
    Link column and nothing else, and the app must still open. Individual
    malformed entries are skipped rather than discarding the file, so one
    bad record cannot cost every other link -- and unlike a duration, a
    link cannot be recomputed by re-running anything.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, LinkEntry] = {}
    for key, value in raw.items():
        try:
            url = value["url"]
            # A non-string url is a malformed entry, not a link to nothing:
            # the page would render it into an anchor. str() would happily
            # turn None into "None", so the type is checked instead.
            if not isinstance(url, str) or not url:
                continue
            out[key] = LinkEntry(
                size=int(value["size"]), mtime=float(value["mtime"]), url=url
            )
        except (TypeError, KeyError, ValueError):
            continue
    return out


def save(path: Path, store: dict[str, LinkEntry]) -> None:
    """Persist the store, treating failure as "no links next launch".

    Never raises: this is called the moment an upload succeeds, and a
    read-only or full disk must not turn a finished upload into a crash.

    Through atomicio rather than write_text, which is where this parts
    company with durations.save a second time. write_text truncates before
    it writes, so a crash, a power cut or a tray Quit landing inside that
    window leaves a half-written file -- and load() reads a half-written
    file as an empty one, which here means EVERY link is gone, not just the
    one being added. durations pays the same risk for a re-probe;
    eveskills/controller.py already takes this route for the same reason,
    that the file holds something nothing can rebuild.
    """
    try:
        payload = {
            key: {"size": e.size, "mtime": e.mtime, "url": e.url}
            for key, e in store.items()
        }
        atomicio.write_atomic(Path(path), json.dumps(payload))
    except OSError:
        logger.warning("Could not persist upload links to %s", path, exc_info=True)


def lookup(
    store: dict[str, LinkEntry], video_path: Path, size: int, mtime: float
) -> str | None:
    """The link for this exact version of the file, or None.

    No ``(hit, value)`` pair, unlike ``durations.lookup``: there is no
    stored "uploaded, but to no URL" state to tell apart from "not
    uploaded", because remember() refuses an empty url.
    """
    entry = store.get(str(video_path))
    if entry is None or entry.size != size or entry.mtime != mtime:
        return None
    return entry.url


def remember(
    store: dict[str, LinkEntry], video_path: Path, size: int, mtime: float, url: str
) -> None:
    """Record a finished upload. An empty url is ignored.

    The guard is not defensive tidiness: a stored empty string would render
    as a Link cell that looks populated and goes nowhere, which is worse
    than the column being blank.
    """
    if not url:
        return
    store[str(video_path)] = LinkEntry(size=size, mtime=mtime, url=url)


def rename(store: dict[str, LinkEntry], old_path, new_path) -> None:
    """Follow a renamed recording, carrying its link with it.

    A rename changes the key and nothing else -- size and mtime are
    untouched by ``MoveFileExW`` -- so this is a key move with the entry
    preserved, NOT a re-remember. Re-remembering would need the caller to
    re-stat the file, and a stat that disagreed by a byte would silently
    drop the link instead of moving it.

    Missing source is a no-op: most recordings have never been uploaded,
    and inventing an entry here would draw a Link glyph for a video that
    does not exist.

    An entry already at the destination is OVERWRITTEN. Nothing prunes this
    file (see the module docstring), so an orphan for a long-deleted file
    can be sitting on the name the user just chose. It is very unlikely to
    match -- ``lookup`` validates ``(size, mtime)``, which must agree to
    the byte and the timestamp -- but "unlikely" is not "never": two
    recordings CAN share both, which is why ui/api.py zips ids to infos
    rather than looking a row up by its identity. Leaving the orphan would
    keep a stale URL keyed to a live name, the one thing this module is
    careful never to do.
    """
    entry = store.pop(str(old_path), None)
    if entry is None:
        return
    store[str(new_path)] = entry
