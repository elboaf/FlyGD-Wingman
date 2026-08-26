"""What a recording looks like once it has crossed to the page, and how it
gets resolved back.

The Tk window addressed rows by their filesystem path -- the Treeview iid
was str(info.path) -- and got a safety property for free along the way:
_delete_selected operated on _chosen(), which could only ever hold objects
from the list currently on screen. Handing paths to a web page loses that.
Not because the page is hostile (it is local, bundled in the installer,
loads no remote content, and is exactly as trusted as the Python) but
because it goes stale: a page holding a path it read before a refresh will
happily ask to delete it afterwards, and by then the path may mean a
different recording, or a file the app never listed at all.

So ids are opaque, minted per row, and never reused. An id from a previous
snapshot resolves to None, which turns "act on the wrong file" into "do
nothing" -- the only acceptable outcome for a delete.

This module owns no cache. durations.resolve needs the cache dict, and the
caller has it; rebuild() therefore produces rows with durations unknown and
the caller re-applies cache hits through set_duration.
"""

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from .. import library


@dataclass(frozen=True)
class Row:
    """One list row, as the page sees it.

    Every field is already rendered. Date suppression, size units, and the
    "…"/"?" duration glyphs are decisions library.VideoInfo owns, and a
    second implementation in JS would drift from it -- tooltip's help table
    is keyed on those exact strings, so a drift there orphans the tooltips
    silently.

    Frozen because rows are replaced rather than edited: an in-place update
    that misses the stored copy leaves the page showing one thing while
    resolve() answers with another.
    """

    id: str
    name: str
    date: str
    size: str
    duration: str
    link: str | None
    preselected: bool


class RowSnapshot:
    """The backend's authoritative view of the list the page is showing."""

    def __init__(self) -> None:
        self._rows: list[Row] = []
        self._infos: dict[str, library.VideoInfo] = {}
        # Keyed by path, not by row id, precisely so links outlive a
        # rebuild -- ids do not. refresh() fires the instant an upload
        # finishes, and clearing links there is what made the glyph appear
        # and vanish a moment later.
        self._links: dict[Path, str] = {}
        self._definitive: set[str] = set()
        # Monotonic for the life of the snapshot, never reset by rebuild.
        # Restarting it per rebuild would recycle "r1" onto a different
        # recording, which is the entire failure this design prevents.
        self._minted = 0

    def _mint(self) -> str:
        self._minted += 1
        return f"r{self._minted}"

    def rebuild(self, directory, preselect: set | None = None) -> list[dict]:
        """Rediscover *directory* and mint a fresh row for every recording.

        Paths in *preselect* start checked; that is the watcher's channel
        for "finish a fight, open the window, hit Upload" with no clicking.
        A preselected path that has since been deleted is simply absent
        rather than an error -- the watcher fires on a path a delete can
        beat to the refresh.
        """
        preselect = preselect or set()
        infos: list[library.VideoInfo] = []
        for path in library.discover(Path(directory)):
            try:
                infos.append(library.stat_info(path))
            except OSError:
                # Vanished between discover() and stat. discover() already
                # tolerates this race; letting it out here would turn one
                # unlucky delete into an empty list for the whole folder.
                continue

        live = {info.path for info in infos}
        self._links = {path: url for path, url in self._links.items() if path in live}
        self._infos = {}
        self._definitive = set()
        self._rows = []
        for info in infos:
            row_id = self._mint()
            self._infos[row_id] = info
            self._rows.append(
                Row(
                    id=row_id,
                    name=info.path.name,
                    date=info.date_str,
                    size=info.size_str,
                    duration=info.duration_str,
                    link=self._links.get(info.path),
                    preselected=info.path in preselect,
                )
            )
        return self.rows()

    def rows(self) -> list[dict]:
        """The rows as plain dicts. pywebview serialises what it is handed,
        and a dataclass does not survive that trip."""
        return [dataclasses.asdict(row) for row in self._rows]

    def resolve(self, row_id: str):
        """The VideoInfo behind *row_id*, or None if this snapshot has never
        heard of it. None is the answer for every stale id, and callers must
        treat it as "do nothing", never as "not found, try harder"."""
        return self._infos.get(row_id)

    def resolve_many(self, ids: list[str]) -> list[library.VideoInfo]:
        """Every known id in *ids*, in snapshot order, unknown ones dropped.

        Snapshot order rather than argument order because uploader.build_body
        numbers a batch "(n/total)" in the order it is handed the files. The
        numbering the user sees in the upload confirmation has to match the
        list they were looking at, not whatever order the page's selection
        set happened to iterate in.
        """
        wanted = set(ids)
        return [self._infos[row.id] for row in self._rows if row.id in wanted]

    def set_link(self, row_id: str, url: str | None) -> None:
        """Record a finished upload against its row. Unknown id: no-op.

        The no-op matters -- an upload can finish against a row that was
        deleted or rebuilt out from under it mid-flight.

        Takes the finished URL rather than a video id, and that is the
        point rather than a convenience: this method used to build the watch
        URL with an f-string of its own, which was the second of three
        copies. uploader.watch_url is the one that survived.

        None CLEARS the link, and that is load-bearing rather than
        permissive. This map is keyed by PATH and survives rebuild on
        purpose -- it is what keeps a link through the refresh an upload
        itself triggers -- so a file re-recorded at a path uploaded earlier
        in the same session would otherwise inherit the previous
        recording's video. Api.list_rows is what passes the None: it reads
        the persisted store, which is keyed on (size, mtime) and therefore
        knows the difference.
        """
        info = self._infos.get(row_id)
        if info is None:
            return
        self._links[info.path] = url
        self._replace(row_id, link=url)

    def set_duration(
        self, row_id: str, duration: float | None, definitive: bool
    ) -> str | None:
        """Record one probe result. Returns the CELL TEXT, or None if the
        update was declined (unknown id, or a row already answered
        definitively).

        The return value is the whole point of the signature: U1 shipped
        for four rounds because api.py pushed the raw float it had passed
        IN rather than the string this method renders, so a cold duration
        cache filled the Length column with `3789.0` while a warm one --
        which fills the column from rebuild()'s initial payload -- read
        `1:03:09`. list.js parses that column back out to sort it, so the
        float also broke the sort. Handing back the rendered string leaves
        exactly one place that decides what the cell says.

        Returning None on a declined update is the other half: the
        supersede rule below is defeated if the caller pushes anyway, and
        it used to be -- a late no-verdict probe left Python holding
        "5:30" and the page showing "?".

        *definitive* is library.probe's verdict flag, and it decides whether
        this answer can be superseded. A probe that never got a verdict --
        no ffprobe configured, launch failure, timeout -- is displayed (the
        row must stop reading "measuring") but stays open to a later real
        answer. A definitive one is final.

        That is the race app._apply_duration guarded, generalised: a
        synchronous probe resolves a row, then the background worker's
        timeout lands for the same row. Letting the timeout win would
        replace a good duration with an unreadable one, and the caller
        would then cache it under a (size, mtime) key that never changes
        again -- pinning that recording to "?" forever and blocking its
        combat-log upload with a message blaming ffprobe.
        """
        info = self._infos.get(row_id)
        if info is None or row_id in self._definitive:
            return None
        info.duration = duration
        info.probed = True
        # The flag reaches the CELL, not just this class's supersede rule.
        # It used to stop here: every no-verdict probe rendered as "?", so
        # an install with no ffprobe at all told the user, once per row,
        # that ffprobe could not open that particular file. See
        # library.VideoInfo.answered.
        info.answered = definitive
        if definitive:
            self._definitive.add(row_id)
        self._replace(row_id, duration=info.duration_str)
        return info.duration_str

    def _replace(self, row_id: str, **changes) -> None:
        for index, row in enumerate(self._rows):
            if row.id == row_id:
                self._rows[index] = dataclasses.replace(row, **changes)
                return
