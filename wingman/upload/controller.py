"""Uploader runtime ownership: the recording list, uploads, retries and log posts.

Every lock, cache, worker handle and queue the Uploader route runs on lives
here. Named ports keep the page, the dialogs and the status strip outside
this module without exposing bridge transport: nothing here knows a handler
name, holds a window, or can push. The work gate is SHARED with the app
updater and Quit, which still live in `ui/api.py`; see `upload.gate`.

`state` is the bridge's AppState, shared by reference and read live:
`recording_dir` is rebound by Settings' folder commit and `settings` is
mutated in place, so nothing here may copy either at construction.
"""

import contextlib
import datetime
import logging
import os
import queue
import sys
import threading
import weakref
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .. import combatlog, discord, durations, library, links, paths, stitch, uploader
from .. import settings as settings_mod
from .gate import WorkGate

logger = logging.getLogger(__name__)


# 100ms, carried over from app.PROBE_DRAIN_MS: fast enough that durations
# appear to fill in live, slow enough that a folder of a hundred recordings
# is batched into a handful of drains rather than a hundred saves.
PROBE_DRAIN_S = 0.1


def _close_media(media) -> None:
    """Release the file handle a MediaFileUpload holds, best effort.

    MediaFileUpload closes its descriptor only in `__del__`, so anything
    that needs the file released *now* -- to unlink a stitched temporary,
    or to stop blocking a rename of the user's own recording on Windows --
    has to close it explicitly. Tolerates None and objects without a
    stream so callers can hand it whatever they have.
    """
    stream = getattr(media, "stream", None)
    if stream is None:
        return
    try:
        stream().close()
    except Exception:
        logger.warning("Could not close upload stream", exc_info=True)


def folder_note(folder: Path, suppressed: int) -> str:
    """What just happened to the recording folder, with the real number.

    Round 3's B11: the two fields with a data-loss history said nothing
    about how they commit. The answer settled on was not a confirm and not
    an Apply button -- Browse and Detect rebind in one click and would
    bypass both -- but a report, written after the commit, where the count
    is knowable.

    The cost is deliberately stated as what it is and no worse. Those
    recordings are not announced and arrive unticked, but they are still
    listed: list_rows() rebuilds from the folder and only the watcher's
    poll result is preselected (__main__.py's poll_tick). Calling it data
    loss would be the same overstatement DESIGN.md carried for a release.

    Zero says nothing about announcements, because there was nothing to
    suppress and a "0 recordings were not announced" is a sentence the
    reader has to parse twice to learn nothing.
    """
    where = f"Now watching {folder}."
    if suppressed == 0:
        return where
    # Singular by hand rather than a pluralise helper: this is the only
    # counted noun on the Settings route, and copy.py's number formatting
    # is another lane's region.
    if suppressed == 1:
        return f"{where} 1 recording already there was not announced."
    return f"{where} {suppressed} recordings already there were not announced."


@dataclass(frozen=True)
class LogTarget:
    """Where a combat-log post would go, or why it cannot go anywhere.

    Resolving this was inline in `_post_combat_logs` until the Uploader
    grew a standalone `Post the last hour`. Two callers needing the same
    three answers -- parse the webhook, tell absent from unusable, find the
    Gamelogs folder -- is exactly the shape that drifts when it is written
    twice, and one of the two copies would be the one a user reads.

    `problem` is a CLAUSE, not a sentence, because the two callers frame it
    differently: "Combat logs skipped: ..." after an upload that succeeded,
    "Combat logs not posted: ..." when the post was the whole action.

    `configured` is the one case the callers must disagree about. No
    webhook at all is a fact about the INSTALL rather than a failure: the
    upload tail stays silent (a WARNING strip on every upload forever is
    the recurring-failure pattern `format_upload_confirm`'s docstring
    records, and the panel states the fact instead), while a standalone
    post has to say it -- the user asked for exactly this, and nothing else
    would answer them.
    """

    hook: object | None
    gamelogs_dir: Path | None
    problem: str
    configured: bool


# The standalone post's window. One hour, ending at the click: it is not
# derived from any recording, which is the whole point of the control --
# the fight that was not recorded, or was recorded and is not worth
# uploading. combatlog.WINDOW_PADDING widens what actually gets selected by
# five minutes each side, as it does for the upload tail.
RECENT_LOG_WINDOW = datetime.timedelta(hours=1)


@dataclass
class UploadJob:
    """Every value the upload worker needs, captured before dispatch.

    `ids` runs parallel to `items` so a finished upload can be linked back
    to the row the page is showing without the worker re-resolving an id
    against a snapshot that may have been rebuilt underneath it.

    `start_index` lets a retry resume partway through without renumbering
    the "(2/3)" title suffixes: the worker skips earlier indices but still
    computes totals from the full list.
    """

    items: list
    ids: list[str]
    title: str
    description: str
    stitch: bool
    privacy: str
    category: str
    # Carried on the job rather than read from settings at post time so a
    # Retry posts logs exactly as the confirmed upload promised, even if the
    # user has since unchecked the box.
    logs: bool = False
    start_index: int = 0


def _upload_summary(job: UploadJob) -> str:
    """What the strip says when the video half has succeeded.

    Round 3's finding 13: the old line was "Upload complete!", which the
    combat-log tail then overwrote outright, so the terminal feedback for
    the primary action read "Posted combatlogs-....zip (15 KB)." -- the
    words *uploaded*, the video's title and *YouTube* appeared nowhere,
    and the only other change on screen was a 14px grey arrow in the
    narrowest column. The task completed and the interface did not say so.

    Deliberately built the same way format_upload_confirm builds its
    `Title:` line -- through uploader.build_body -- so the name on the
    strip is the name that is actually on YouTube, numbering included, and
    not the raw field. Same branch, too: stitching collapses a batch into
    one video, so it takes the single-title form.

    No period. Callers that have a second half to report append their own
    sentence (see _skip_logs), which keeps the primary action first in
    every variant instead of behind the side-effect.
    """
    count = 1 if job.stitch else len(job.items)
    if count == 1:
        shown = uploader.build_body(job.title, "", job.privacy, "", 0, 1)["snippet"][
            "title"
        ]
        return f'Uploaded "{shown}" to YouTube'
    # The noun is "recordings", matching the confirm the user just read.
    # The titles are numbered per item, so there is no one name to give.
    return f"Uploaded {count} recordings to YouTube"


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""

    job: UploadJob
    resume_index: int
    request: object | None


@dataclass(frozen=True)
class UploaderPorts:
    """Named effects only; spawn returns an unstarted worker handle.

    UI collaborators are resolved by composition adapters at invocation
    time -- `watcher` in particular, because __main__ assigns it to the Api
    after construction and the tests replace `_alert`/`_confirm`/`_push` on
    the instance. No port is called during construction, and none exposes
    an arbitrary page handler name: each `publish_*` is one literal push
    on the bridge side, which is what keeps every handler name visible to
    test_bridge_contract.py's lexical sweep of ui/api.py.

    `status` and `progress` carry the strip's `busy` flag through unchanged
    (see the note above `Api._status`); `confirm` blocks the calling worker
    until the page answers, exactly as `Api._confirm` does.

    The `format_*` ports are ui/copy.py's tested strings. Injected rather
    than imported so this module stays free of `ui`, the same way
    ProfilesPorts carries `format_copy_confirm`.
    """

    publish_rows: Callable[[dict], None]
    publish_log_post_running: Callable[[dict], None]
    publish_row_renamed: Callable[[dict], None]
    publish_duration: Callable[[dict], None]
    publish_link: Callable[[dict], None]
    publish_cancel_available: Callable[[dict], None]
    publish_retry_available: Callable[[dict], None]
    publish_upload_done: Callable[[dict], None]
    publish_channel: Callable[[dict], None]
    publish_auth: Callable[[str], None]
    status: Callable[..., None]
    progress: Callable[..., None]
    alert: Callable[[str, str, str], None]
    confirm: Callable[..., bool]
    spawn: Callable[..., threading.Thread]
    watcher: Callable[[], object | None]
    update_preparing: Callable[..., None]
    format_selection_summary: Callable[..., str]
    format_title_hint: Callable[..., str]
    format_upload_confirm: Callable[..., str]
    format_progress: Callable[..., str]
    format_upload_cancelled: Callable[..., str]
    format_destination: Callable[..., str]


class _ProbeRun:
    """A queue and timer that cannot be rebound underneath their callbacks."""

    def __init__(self, generation):
        self.generation = generation
        self.results = queue.Queue()
        self.cancelled = threading.Event()
        self.scheduler = None
        self._lock = threading.Lock()

    def start(self):
        # No controller/row locks here. This lock only orders start against
        # stop: Scheduler.stop alone cannot prevent a later start rearming it.
        with self._lock:
            if not self.cancelled.is_set():
                self.scheduler.start()

    def stop(self):
        self.cancelled.set()
        with self._lock:
            if self.scheduler is not None:
                self.scheduler.stop()


class UploaderController:
    """One owner of the Uploader route's runtime.

    Rows, the durations cache, the link store, the probe drain, the upload
    worker and its retry state, and the standalone combat-log post. The
    bridge (`ui/api.py`) keeps one-line facades that delegate here by name;
    `__main__` reaches `busy()` through `Api._busy` for the watcher tick.
    """

    def __init__(
        self,
        state,
        *,
        gate: WorkGate,
        ports: UploaderPorts,
        rows,
        scheduler,
        durations_file=None,
        links_file=None,
        drain_interval_s=PROBE_DRAIN_S,
        probe=library.probe,
        timer=threading.Timer,
    ):
        self._state = state
        self._ports = ports
        self._rows = rows
        self._scheduler = scheduler
        self._durations_file = durations_file or paths.durations_file()
        self._cache = durations.load(self._durations_file)
        self._links_file = links_file or paths.links_file()
        self._link_store = links.load(self._links_file)
        self._link_store_lock = threading.Lock()
        # A late upload may hold a VideoInfo from before a refresh AND rename.
        # Track accepted objects weakly so rename can repoint those captures
        # without retaining old scans. Historical path aliases are unsafe:
        # different files can later reuse a name with identical size/mtime.
        self._listed_infos: weakref.WeakValueDictionary[int, library.VideoInfo] = (
            weakref.WeakValueDictionary()
        )
        self._drain_interval_s = drain_interval_s
        self._probe = probe
        self._timer = timer
        # Order: publication -> link store -> brief state/RowSnapshot operations;
        # cache operations also sit beneath publication. Never acquire
        # publication while holding any of those locks. _link persists under
        # store alone, RELEASES it, then enters publication. Store never spans
        # WebView; rename holds it across filesystem/key/VideoInfo identity moves.
        # Publication covers acceptance + mutation + delivery, not just the
        # final push. WebView may block this gate, but never state/row reads,
        # filesystem scans or successful-upload persistence. Workers/probes
        # start outside both controller gates.
        self._publication_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._generation = 0
        self._rename_revision = 0
        self._probe_run = None

        # The claim exists before a worker handle and survives through its
        # target's finally. Thread liveness has a pre-start gap and therefore
        # cannot arbitrate concurrent pywebview bridge calls.
        #
        # Injected, never constructed: the updater and Quit claim against
        # this same object from ui/api.py (see WorkGate's docstring).
        self._work_gate = gate
        self._upload_thread: threading.Thread | None = None
        self._delete_thread: threading.Thread | None = None
        # The standalone combat-log post, and Play. Separate handles rather
        # than one "work" slot because each answers a different question:
        # busy() (an upload, which a list rebuild would damage and Quit
        # must ask about) is deliberately NOT widened to cover a log post,
        # and Play is fire-and-forget with nothing to guard at all.
        self._logs_thread: threading.Thread | None = None
        self._play_thread: threading.Thread | None = None
        # The log post has its own claimed flag rather than sharing the
        # upload/update/Quit gate: its shorter lifecycle deliberately does
        # not defer polling or require Quit confirmation. It still cannot
        # use thread liveness because pywebview bridge calls are concurrent
        # and a newly constructed thread is not alive before start().
        self._logs_lock = threading.Lock()
        self._logs_running = False
        self._retry_state: RetryState | None = None
        self._links: dict[str, str] = {}
        self._last_pct: float = 0.0
        # D5's stop signal. An Event rather than a bool because it is set on
        # the UI thread (cancel_upload, a bridge method) and read on the
        # upload thread once per 4 MiB chunk, and because `.is_set` is
        # exactly the zero-argument predicate uploader.upload wants -- no
        # lambda closing over self on a worker.
        self._cancel = threading.Event()

    def last_pct(self) -> float:
        """The running upload's last reported percentage, for the quit confirm.

        Read by `Api._claim_quit`, which stays on the bridge because it owns
        the window it must raise and the bounded dialog it must ask. Reset
        per job in `_upload_worker`, never here.
        """
        return self._last_pct

    # ----- rows and durations ----------------------------------------------

    def list_rows(self, preselect: set | None = None) -> None:
        """Rebuild the list and push it, then fill durations in behind it.

        Successor to UploaderWindow.refresh(). Rows are drawn from a plain
        stat and pushed immediately; durations come from the cache where
        they can and a background probe where they cannot. The version this
        replaces once ran one synchronous ffprobe per file before the window
        appeared, which froze the app for seconds on every launch, tray
        open, settings save, and delete.

        *preselect* is a set of Path, not of strings -- it comes straight
        from the watcher's poll result.

        Returns without pushing when no recording folder is configured yet.
        That is first run, and the page is showing its own route for it; a
        push of an empty list here would replace that screen with an empty
        uploader and no explanation.

        Unless the user SKIPPED first run, in which case the empty push is
        the whole point. #list-empty starts hidden in markup and is only
        ever unhidden by list.js's render(), which runs on this push -- so
        without it a skipped install lands on a list with no rows, no empty
        state and no explanation, which is precisely the inert screen
        DESIGN.md warns reads as a broken one.
        """
        with self._state_lock:
            self._generation += 1
            generation = self._generation
            folder = self._state.recording_dir
            revision = self._rename_revision
            previous, self._probe_run = self._probe_run, None
        if previous is not None:
            previous.stop()

        while True:
            candidate = self._rows.scan(folder) if folder is not None else []
            with self._publication_lock:
                with self._state_lock:
                    if (
                        generation != self._generation
                        or folder != self._state.recording_dir
                    ):
                        return
                    if revision != self._rename_revision:
                        # A successful rename may have happened after stat.
                        # Retry this scan, but never resurrect its old path.
                        revision = self._rename_revision
                        continue
                if folder is None:
                    if self._state.settings.get("first_run_skipped"):
                        self._ports.publish_rows({"rows": []})
                    return
                work = self._install_scan(candidate, preselect)
                break
        if work:
            self._start_probe(work, generation)

    def _install_scan(self, infos, preselect):
        """Accept/install/publish under the publication gate, with no scan I/O."""
        # Hydrate BEFORE freezing the Rows. Hydrating only the VideoInfos
        # once left the Length cells measuring forever on warm-cache starts:
        # cached recordings never receive a later onDuration to repair them.
        pending = durations.resolve(self._cache, infos)
        # Authoritative in both directions: a miss must clear the old path
        # link when a different recording reuses its name (size/mtime differ).
        with self._link_store_lock:
            for info in infos:
                self._listed_infos[id(info)] = info
            restored = {
                info.path: links.lookup(
                    self._link_store, info.path, info.size, info.mtime
                )
                for info in infos
            }
        rebuilt = self._rows.install(infos, preselect=preselect, link_urls=restored)
        # rebuild() mints new ids, so every key already in _links is dead --
        # rows.py's whole contract is that a stale id resolves to nothing.
        # Replaced rather than left, because every installation re-adds a
        # key per linked row on EVERY refresh (launch, tray open, settings
        # save, delete, watcher find) and this map would otherwise grow
        # without bound across a long session, holding ids nothing can reach.
        ids = [row["id"] for row in rebuilt]
        with self._state_lock:
            self._links = {
                rid: restored[info.path]
                for rid, info in zip(ids, infos)
                if restored[info.path]
            }

        # Identity, not equality: VideoInfo is a plain dataclass, so two
        # recordings with the same size and mtime compare equal and an `in`
        # test over the pending list would probe the wrong row.
        outstanding = {id(info) for info in pending}

        # BOTH link maps are filled before delivery: the snapshot renders
        # the cell; _links lets copy_path/open_path act on that same answer.
        self._ports.publish_rows({"rows": self._rows.rows()})
        # Restated on every rebuild, and this is the ONLY thing that can
        # repair it. A disarming push lost into a hidden window (which
        # _push swallows, by design) leaves the page drawing the button as
        # disabled, and a disabled button takes neither a click nor a
        # keypress -- so it cannot ask for its own repair. A rebuild is
        # what a watcher announcement, a delete and a folder change all
        # produce, so the wrong state cannot outlive the next recording.
        self._ports.publish_log_post_running({"running": self.logs_busy()})
        return [
            (row_id, info)
            for row_id, info in zip(ids, infos)
            if id(info) in outstanding
        ]

    def panel_text(self, ids: list[str], stitch: bool) -> dict:
        """Both selection-dependent strings, for the page to render.

        Selection and the stitch checkbox are client state and never cross
        the bridge, so the page asks for these strings on every change
        rather than reimplementing them in JavaScript. That keeps one
        tested implementation of each: format_selection_summary, whose two
        asymmetries ("+" when a probe is outstanding, never a partial
        marker on size) are subtle enough that a second copy would drift
        within a release; and format_title_hint, which discloses that
        build_body numbers a batch -- a disclosure added deliberately in
        2.2.0 after users got ten differently-named public videos.

        Returned together because both change on the same events, so one
        round trip serves both.

        Unknown ids are dropped by resolve_many, so a stale page produces a
        smaller honest summary rather than a wrong one.
        """
        infos = self._rows.resolve_many(ids)
        return {
            "summary": self._ports.format_selection_summary(infos),
            "title_hint": self._ports.format_title_hint(len(infos), bool(stitch)),
        }

    # ----- delete, open, copy ------------------------------------------------

    def delete_selected(self, ids) -> None:
        pairs = [
            (rid, info) for rid in ids if (info := self._rows.resolve(rid)) is not None
        ]
        if not pairs:
            self._ports.alert(
                "warning", "No Selection", "Select at least one video to delete."
            )
            return
        # Same reason as _confirm_then_upload: _confirm blocks until the
        # page answers, and the page's answer arrives on the bridge thread
        # this method is running on.
        self._delete_thread = threading.Thread(
            target=self._delete_worker, args=(pairs,), daemon=True
        )
        self._delete_thread.start()

    def _delete_worker(self, pairs) -> None:
        infos = [info for _, info in pairs]
        names = "\n".join(f"  • {i.path.name}" for i in infos)
        if not self._ports.confirm(
            "Confirm Delete",
            f"Permanently delete these files from disk?\n\n{names}"
            "\n\nThis cannot be undone.",
            destructive=True,
            confirm_label=f"Delete {len(infos)} {'file' if len(infos) == 1 else 'files'}",
        ):
            return
        deleted, failures = library.delete([i.path for i in infos])
        # Forget only what actually went. A file that failed to delete still
        # exists, and dropping its seen-entry would make the watcher
        # announce it again as if it were new.
        failed_paths = {p for p, _ in failures}
        watcher = self._ports.watcher()
        if watcher is not None:
            for info in infos:
                if info.path not in failed_paths:
                    watcher.forget(info.path)
        with self._state_lock:
            for row_id, _ in pairs:
                self._links.pop(row_id, None)
        self.list_rows()
        message = f"Deleted {deleted} file(s)."
        if failures:
            message += f" {len(failures)} failed."
        self._ports.status(message)

    def copy_path(self, row_id: str) -> str:
        """Return the row's link for the page to put on the clipboard.

        The write itself is the page's job: with Tk gone there is no
        toolkit clipboard, and navigator.clipboard is right there. Returning
        it rather than pushing it keeps this a plain request/response, which
        is what a button press is.
        """
        with self._state_lock:
            url = self._links.get(row_id, "")
        if not url:
            return ""
        self._ports.status("Link copied to clipboard", "SUCCESS")
        return url

    def open_path(self, row_id: str) -> None:
        with self._state_lock:
            url = self._links.get(row_id)
        if url:
            webbrowser.open(url)

    def play_recording(self, row_id: str) -> None:
        """Open one recording in the Windows default player.

        The Uploader is the screen about a folder's contents, and until
        `Open folder` landed every affordance on it acted on the YouTube
        link rather than on the file (`open_path` resolves a row to a URL,
        despite the name). "Is this the fight I think it is" is answered by
        watching two seconds of it, and answering it meant leaving the app.

        Never disabled, and that follows `WM.setEnabled`'s rule rather than
        excepting it: whether the file exists is a fact about the disk that
        goes stale, and the page cannot know it -- the row payload carries
        no such field, and adding one would be worse, because `rebuild()`
        only ever emits rows for files that existed at scan time, so it
        would read `true` for every row forever. The app does NOT already
        know this cannot be carried out, so it runs and reports.

        On a worker because `os.startfile` blocks while the shell resolves
        an association -- seconds on a slow handler or a disconnected share
        -- and the bridge thread has to keep painting.
        """
        info = self._rows.resolve(row_id)
        if info is None:
            # A stale id means "do nothing" everywhere else, silently. Here
            # the row is still on screen under the user's pointer, so
            # silence would read as a dead menu item.
            self._ports.status(
                "That list is out of date. Refresh and try again.", "WARNING"
            )
            return
        self._play_thread = self._ports.spawn(
            target=self._play_worker, args=(info.path,), daemon=True
        )
        self._play_thread.start()

    def _play_worker(self, path: Path) -> None:
        """Hand one path to the shell, reporting on the strip.

        A player holding a handle on a still-growing recording is a real
        and accepted consequence: `watcher.file_is_closed` will read that
        handle as "still being written" and defer the announcement of a
        not-yet-seen recording by a poll or two. Watching a file mid-write
        is exactly what this control is for, so the cost is named rather
        than designed out.
        """
        if not path.exists():
            self._ports.status(
                f"That recording is no longer there: {path.name}", "WARNING"
            )
            return
        try:
            # Same posture as open_recording_dir: os.startfile exists only
            # on Windows, so it is reached through an attribute lookup
            # behind the platform check rather than at import. Off Windows
            # this is a no-op that reports nothing -- a dev box has no shell
            # to ask, and the file is there.
            if sys.platform == "win32":
                os.startfile(str(path))
        except OSError:
            logger.exception("Could not play %s", path)
            self._ports.status(f"That file could not be opened: {path.name}", "WARNING")

    def rename_recording(self, row_id: str, stem: str) -> dict:
        """Rename one recording on disk, keeping its extension.

        Returns `{ok, error}` for the page to render rather than pushing a
        status line: the page owns the dialog this answers (`WM.prompt` --
        `_confirm` would deadlock the bridge thread it is called on), and a
        refusal re-opens that dialog with the typed text still in it, so a
        typo does not cost the whole name.

        Runs on the BRIDGE THREAD deliberately, but not because that makes
        it exclusive: `poll_tick` runs on the Scheduler's thread, so a poll
        CAN scan in the middle of this. There is no dialog to park on:
        the page has already answered the prompt.

        The publication gate orders resolve, rename and repaint against
        scan installation and incremental updates. Scans still run freely;
        successful rename advances their revision so a pre-rename stat is
        retried rather than restoring the old name.
        """
        with self._publication_lock:
            return self._rename_recording(row_id, stem)

    def _rename_recording(self, row_id: str, stem: str) -> dict:
        # First, and not for tidiness. The uploader reads a source path at
        # the moment it opens it: on the plain path _upload_one is handed
        # job.items[index].path per item, and _link persists against the
        # same VideoInfo afterwards. Renaming underneath that is a race
        # with no good outcome -- an item not yet started uploads under
        # whichever name won, and an item already open fails the rename
        # with a sharing violation the user reads as "that file could not
        # be renamed" while an upload they can see is running fine.
        # Refusing for the duration is one predicate and one sentence, and
        # it covers the stitched path too, where the open handle is on the
        # merged temporary rather than on the sources -- so Windows would
        # otherwise allow the rename outright.
        if self.busy():
            return {
                "ok": False,
                "error": (
                    "That upload is still running. It records the YouTube link "
                    "against the current name, so renaming now would lose it."
                ),
            }

        info = self._rows.resolve(row_id)
        if info is None:
            # NOT "that recording is gone". A watcher poll landing while the
            # prompt was open re-mints every id (list_rows), and the file is
            # sitting on screen in front of the user. Two states, two
            # sentences.
            return {
                "ok": False,
                "error": "The list refreshed while that dialog was open. Try again.",
            }

        problem = library.rename_problem(stem)
        if problem is not None:
            return {"ok": False, "error": problem}

        old_path = info.path
        if not old_path.exists():
            return {
                "ok": False,
                "error": f"That recording is no longer there: {old_path.name}",
            }

        new_path = old_path.with_name(stem.strip() + old_path.suffix)
        if new_path == old_path:
            return {"ok": True, "error": ""}

        # normcase rather than a bare exists(): on a case-insensitive
        # filesystem fight.mkv IS its own destination, so an existence check
        # alone refuses `fight` -> `Fight` as a clash with itself -- the
        # rename a user is most likely to want. samefile() is not used
        # because it raises FileNotFoundError in the normal case, where the
        # destination does not exist yet.
        same_file = os.path.normcase(str(new_path)) == os.path.normcase(str(old_path))
        if not same_file and new_path.exists():
            return {"ok": False, "error": f"{new_path.name} is already in that folder."}

        # _link does not need publication to persist. Exclude it from the
        # WHOLE identity transition, not just rename+save: otherwise it could
        # re-add the old key after it moved but before info.path changed.
        with self._link_store_lock:
            try:
                # Path.rename, NEVER os.replace. os.replace is MoveFileExW with
                # MOVEFILE_REPLACE_EXISTING, which silently destroys the file at
                # the destination -- another recording. The check above exists
                # only to produce a better sentence than the exception would;
                # this call is what actually protects the data.
                old_path.rename(new_path)
            except OSError as exc:
                logger.warning("Could not rename %s", old_path, exc_info=True)
                return {"ok": False, "error": f"That file could not be renamed: {exc}"}

            with self._state_lock:
                self._rename_revision += 1
            # Only after the filesystem rename succeeded. Links cannot be
            # recomputed, so key movement and the captured/current path update
            # must be indivisible to a late successful-upload transaction.
            links.rename(self._link_store, old_path, new_path)
            links.save(self._links_file, self._link_store)
            self._rows.rename(row_id, new_path)
            # The current row moved under its own lock. Repoint older accepted
            # objects still held by uploads/probes as part of this same store
            # transaction. A new recording later discovered at old_path is a
            # new object and cannot inherit this move, even with equal metadata.
            for captured in list(self._listed_infos.values()):
                if (
                    captured.path == old_path
                    and captured.size == info.size
                    and captured.mtime == info.mtime
                ):
                    captured.path = new_path

        # The watcher is the one that fails quietly: its seen-set is keyed
        # by path, so without this the next poll finds a settled, closed,
        # unknown file and announces it as a newly finished recording --
        # preselected, ready to upload, for the second time. No store lock is
        # needed by the watcher or the duration cache; publication still orders
        # this tail against scan installation and incremental row updates.
        watcher = self._ports.watcher()
        if watcher is not None:
            watcher.rename(old_path, new_path)
        # Cheap rather than critical: a lost duration costs one ffprobe.
        durations.rename(self._cache, old_path, new_path)
        durations.save(self._durations_file, self._cache)

        # A targeted repaint, not list_rows(). A rebuild re-mints every id
        # and the page's selection, focus ring and sort position go with
        # them -- and a rename is an incidental action on one row, unlike
        # the delete that is the only other refresh to clear a selection.
        self._ports.publish_row_renamed({"id": row_id, "name": new_path.name})
        return {"ok": True, "error": ""}

    def open_recording_dir(self) -> bool:
        """Open the watched folder in the shell.

        The Uploader is the screen about that folder's contents and had no
        way to reach it: the only file affordances were double-click and a
        context menu, and both act on the YouTube link rather than the file
        (open_path above resolves a row to a URL, despite the name). A
        recording that is missing, mid-write, or not what OBS was supposed
        to produce is inspected outside Wingman, so the reflex is to open
        the folder.

        Reported on the status strip rather than through a dialog. Nothing
        is destroyed and nothing is half-done if this fails, and a modal
        for a button that merely did not open a window is the shape
        _skip_logs already rejects.
        """
        folder = self._state.recording_dir
        if folder is None:
            self._ports.status(
                "No recording folder is set. Choose one in Settings.", "WARNING"
            )
            return False
        if not Path(folder).is_dir():
            # The same case __main__ treats as first run at launch: a
            # folder that was configured and has since gone. Naming it
            # beats "an error occurred", per PRODUCT.md's tone rule.
            self._ports.status(f"That folder is gone: {folder}", "WARNING")
            return False
        try:
            # os.startfile exists only on Windows, so it is reached through
            # an attribute lookup behind the platform check rather than at
            # import -- the same posture eveskills.controller's
            # _default_open_folder and __main__.set_dpi_awareness take. Off
            # Windows this is a no-op: a dev box has no shell to ask.
            if sys.platform == "win32":
                os.startfile(str(folder))
        except OSError:
            logger.exception("Could not open the recording folder")
            self._ports.status("That folder could not be opened.", "WARNING")
            return False
        return True

    # ----- durations --------------------------------------------------------

    def _start_probe(self, work, generation: int) -> None:
        """Probe on a worker; apply results from a drain loop.

        The worker touches neither the snapshot nor the page: it pushes onto
        a queue that the drain reads. Pushing `onDuration` straight from the
        worker would be shorter, but it would also make the durations cache
        a structure written from two threads, and it would give up the
        batching that makes the per-tick save affordable.
        """

        run = _ProbeRun(generation)
        run.scheduler = self._scheduler(
            self._drain_interval_s,
            lambda: self._drain_probes(run),
            timer=self._timer,
        )
        with self._state_lock:
            if generation != self._generation:
                return
            self._probe_run = run

        def worker() -> None:
            try:
                for row_id, info in work:
                    if run.cancelled.is_set():
                        break  # A newer list_rows owns the list now.
                    if info.probed:
                        continue  # Already resolved on demand.
                    duration, definitive = self._probe(
                        info.path, self._state.ffprobe_bin
                    )
                    run.results.put((row_id, info, duration, definitive))
            except Exception:
                # probe() swallows its own failures, so reaching here means
                # something unforeseen. Rows left unprobed sit on "…", and in
                # a windowed build stderr goes nowhere, so log it.
                logger.warning("Duration probe worker failed", exc_info=True)
            finally:
                # Always sent, including on early exit, so the drain loop
                # knows to stop rescheduling itself.
                run.results.put((None, None, None, False))

        try:
            # In tests start() can run the whole probe inline. Neither gate
            # may be held here: a slow probe must not serialize refreshes.
            self._ports.spawn(target=worker, daemon=True).start()
            run.start()
        except Exception:
            self._stop_drain(run)
            raise

    def _current_run(self, run) -> bool:
        with self._state_lock:
            return self._probe_run is run and run.generation == self._generation

    def _drain_probes(self, run: _ProbeRun) -> None:
        """Drain only this run, revalidating ownership after every queue read."""
        if not self._current_run(run):
            self._stop_drain(run)
            return
        done = False
        applied = 0
        try:
            while True:
                try:
                    row_id, info, duration, definitive = run.results.get_nowait()
                except queue.Empty:
                    break
                with self._publication_lock:
                    if not self._current_run(run):
                        done = True
                        break
                    if info is None:
                        done = True
                        break
                    if self._apply_duration(row_id, duration, definitive, info):
                        applied += 1
        finally:
            # Per tick, including a tick superseded after applying a result:
            # quitting during a long scan must not lose completed measurements.
            if applied:
                durations.save(self._durations_file, self._cache)
            if done or not self._current_run(run):
                self._stop_drain(run)

    def _stop_drain(self, run: _ProbeRun) -> None:
        with self._state_lock:
            if self._probe_run is run:
                self._probe_run = None
        run.stop()

    def _apply_duration(self, row_id, duration, definitive, info=None) -> bool:
        """Record/publish under the publication gate; return whether accepted.

        One helper for both probe paths -- the background drain and the
        synchronous pre-upload sweep -- because they pushed the same
        message and only one of them would ever have been fixed. What goes
        over the bridge is RowSnapshot's rendered string, never the float
        that was passed in: U1 found the float reaching the Length column
        on a cold duration cache, where it rendered as `3789.0` and broke
        the column's sort (list.js parses the cell back out, and its regex
        is written for `5:30`). A warm cache hid it, because the initial
        row payload has always carried the string.

        A declined update pushes nothing: set_duration returns None when
        the row is gone or already answered definitively, and pushing over
        that would put a superseded answer on screen while Python holds
        the good one.
        Declined answers must not poison the cache either. The drain passes
        its captured info so acceptance can govern caching as well as delivery.
        """
        rendered = self._rows.set_duration(row_id, duration, definitive)
        if rendered is None:
            return False
        if definitive and info is not None:
            durations.remember(self._cache, info.path, info.size, info.mtime, duration)
        self._ports.publish_duration(
            {"id": row_id, "duration": rendered, "definitive": definitive},
        )
        return True

    # ----- upload -----------------------------------------------------------

    def busy(self) -> bool:
        """Is a VIDEO UPLOAD running?

        Deliberately not widened to cover the standalone combat-log post,
        and that is a decision rather than an omission. Three callers write
        three different sentences from this one predicate, and each would
        become false for a log post:

        - `_claim_quit` renders `format_quit_confirm(_last_pct)` when its
          atomic claim reports an upload. That says "An upload is N% complete" --
          during a log post there is no upload and `_last_pct` is a stale
          number from a previous job. A log post is seconds long and loses a
          Discord post, not a
          multi-gigabyte transfer, so Quit does not ask about it at all.
        - `start_upload` says "An upload is already in progress", which a
          log post is not. It refuses on `_logs_busy` separately, in its own
          words.
        - `__main__.poll_tick` defers a list rebuild because one would drop
          the links and progress of a running upload. A log post touches no
          rows, so deferring for it would make the list go stale for
          nothing.
        """
        return self._work_gate.upload_claimed()

    def logs_busy(self) -> bool:
        """Is a standalone combat-log post claimed or running?

        Its own predicate for the reason above: the two kinds of work
        exclude each other and nothing else about them is the same. Reads
        the claimed flag rather than a thread's liveness -- see the note
        beside `_logs_lock`.

        "Exclude each other" is intent, not an atomic transition: this and
        `_busy()` are read separately by two check-then-act callers. The work
        gate deliberately serializes upload, updater handoff, and Quit only;
        standalone log-post separation remains unchanged.
        """
        with self._logs_lock:
            return self._logs_running

    def start_upload(self, title, description, stitch, ids) -> None:
        # No `logs` parameter. Uploader 8: the checkbox had no true second
        # state -- "there is no scenario where I don't want to upload logs
        # also" -- so the choice moved out of one click from Upload and
        # into whether a webhook is configured at all, which is the fact
        # that actually decides it. PRODUCT.md backs an opinionated default
        # here ("does not have to be neutral"), and a fork that wants logs
        # off belongs in settings.py, not on the panel.
        #
        # S3 left the parameter accepted-and-ignored so the page could keep
        # calling with five arguments until this lane removed the control.
        # The control is gone (index.html #route-main), so the parameter
        # goes with it, in the same commit -- the two are one change and a
        # signature that outlives its caller is a trap for the next reader.
        # privacy and category are NOT parameters. They are settings, and
        # the settings are Python's -- as they were in the Tk build, which
        # read self.state.settings at dispatch time. A page that holds its
        # own copy is a page that can publish with a stale one: the first
        # build of this bridge defaulted to `unlisted` until Settings was
        # saved in that session, so a user set to `private` got an
        # unlisted video on the app's one irreversible action.
        cfg = self._state.settings
        privacy = cfg.get("privacy", "unlisted")
        category = str(cfg.get("category", "20"))
        # Resolved one id at a time rather than through resolve_many so ids
        # and infos stay index-aligned when the page sends an id the
        # snapshot no longer knows (a stale page after a refresh).
        pairs = [
            (rid, info) for rid in ids if (info := self._rows.resolve(rid)) is not None
        ]
        if not pairs:
            self._ports.alert(
                "warning", "No Selection", "Select at least one video to upload."
            )
            return
        if stitch and len(pairs) < 2:
            self._ports.alert(
                "warning", "Stitch", "Select at least two videos to stitch."
            )
            return
        if self.logs_busy():
            # Its own sentence. Reusing the line above would say an upload
            # is running when none is, on the one screen where the user can
            # see that nothing is uploading.
            self._ports.alert(
                "warning",
                "Busy",
                "Combat logs are being posted. Try again in a moment.",
            )
            return
        job = UploadJob(
            items=[i for _, i in pairs],
            ids=[r for r, _ in pairs],
            title=title,
            description=description,
            stitch=bool(stitch),
            privacy=privacy,
            category=category,
            # Unconditional now. The webhook predicate downstream is what
            # gates the post, and it is read live in both places that need
            # it (the confirm, and _post_combat_logs) rather than
            # snapshotted here -- Settings is reachable between them.
            logs=True,
        )
        claim = self._work_gate.claim_upload()
        if not claim:
            if claim.reason == "upload":
                self._ports.alert(
                    "warning", "Busy", "An upload is already in progress."
                )
            else:
                self._ports.update_preparing(show_window=False)
            return
        try:
            # Cleared per dispatch, not per process: a stop answered by the
            # PREVIOUS job would otherwise abort this one before its first chunk
            # and report "Stopped. Nothing was uploaded." for a job the user
            # just started. Retry clears it for the same reason.
            self._cancel.clear()
            self._upload_thread = threading.Thread(
                target=self._run_claimed_upload,
                args=(self._confirm_then_upload, job),
                daemon=True,
            )
            self._upload_thread.start()
        except Exception:
            self._upload_thread = None
            self._work_gate.release_upload()
            raise

    def _run_claimed_upload(self, target, *args) -> None:
        try:
            target(*args)
        finally:
            self._work_gate.release_upload()

    def _confirm_then_upload(self, job: UploadJob) -> None:
        # The confirm runs on the worker, not in start_upload, because
        # _confirm blocks until the page calls dialog_response -- and
        # start_upload is running on pywebview's bridge thread, which is
        # where that answer has to arrive. Asking there would deadlock the
        # bridge on itself. The busy guard is already set by the time this
        # dialog is up, which is also what we want.
        body = self._ports.format_upload_confirm(
            job.items,
            job.title,
            job.privacy,
            self._state.settings.get("channel_title", ""),
            job.stitch,
            # Read here rather than snapshotted onto the job: the confirm
            # has to describe the webhook _post_combat_logs will find when
            # it runs, and Settings is reachable between the two.
            self._state.settings.get("discord_webhook", "") or "",
        )
        if not self._ports.confirm("Confirm Upload", body):
            return
        self._upload_worker(job)

    def _link(self, row_id: str, video_id: str, info) -> None:
        """Record and announce one uploaded row.

        _links is kept here as well as in the snapshot because the
        RowSnapshot contract is write-only for links, and open_path /
        copy_path need to read one back.

        The push carries the finished URL rather than the video id. That is
        round 5's link-state: with a bare id the page had no choice but to
        build a watch URL of its own, which made web/list.js the third
        writer of a string uploader.watch_url already owned.

        *info* is the VideoInfo the job captured, NOT one resolved from
        row_id here. UploadJob's own docstring says why: "`ids` runs
        parallel to `items` so a finished upload can be linked back to the
        row the page is showing without the worker re-resolving an id
        against a snapshot that may have been rebuilt underneath it." The
        first draft of this method resolved anyway, and a refresh landing
        mid-upload -- the watcher finding a new recording is enough -- made
        resolve() return None and the link was never persisted at all.

        Persisted here rather than at the end of the job, and saved on every
        link rather than once: a batch that dies halfway -- crash, power
        cut, a kill from the tray -- must not lose the record of the videos
        that DID publish. There is no way to recover one of those from
        inside the app afterwards.
        """
        url = uploader.watch_url(video_id)
        # Evidence belongs to the upload, not its row or a responsive page.
        # Never wait for publication while holding this persistence lock.
        with self._link_store_lock:
            links.remember(self._link_store, info.path, info.size, info.mtime, url)
            links.save(self._links_file, self._link_store)
        with self._publication_lock:
            current = self._rows.resolve(row_id)
            if current is None:
                return
            with self._link_store_lock:
                if (
                    links.lookup(
                        self._link_store, current.path, current.size, current.mtime
                    )
                    != url
                ):
                    # Another completion saved/published while this one waited.
                    # Do not regress its row to an older successful upload URL.
                    return
            with self._state_lock:
                self._links[row_id] = url
            self._rows.set_link(row_id, url)
            self._ports.publish_link({"id": row_id, "url": url})

    def _upload_done(self, job: UploadJob) -> None:
        self._retry_state = None
        # Disarmed HERE and not left to _upload_worker's finally: the video
        # half is over, but the combat-log half below still runs on this
        # thread and can take seconds. The finally is several frames away,
        # so a Cancel left armed across the log post would be a live button
        # with nothing polling its flag -- a click that does nothing, which
        # is the state D5 exists to remove rather than relocate.
        self._ports.publish_cancel_available({"available": False})
        summary = _upload_summary(job)
        # Explicit False on both: this runs ON the upload thread, so
        # _busy() is still true here and the default would refuse to settle
        # the very line that says the job is over.
        self._ports.status(f"{summary}.", "SUCCESS", busy=False)
        self._ports.progress(100.0, kind="SUCCESS", busy=False)
        self._ports.publish_retry_available({"available": False})
        # Round 3's finding 5, panel half. A SEMANTIC event -- the job
        # finished -- not an instruction: the page decides that this means
        # dropping the selection, because selection is client state and
        # never crosses this bridge. Pushed here rather than from the two
        # call sites so the resume tail reports completion the same way a
        # plain job does.
        self._ports.publish_upload_done({})
        # The single point at which the video half is known to have
        # succeeded -- both the plain worker and the resume tail arrive
        # here -- so it is where the log half hangs. Retry therefore posts
        # the logs the confirmed job promised, rather than dropping them
        # because the first attempt failed.
        if job.logs:
            # Guarded, because this runs INSIDE _upload_worker's try: without
            # it, anything raised before _combat_log_worker's own handler --
            # a probe blowing up, an unreadable mtime -- lands in the except
            # for a FAILED UPLOAD and is reported as one. The video is public
            # and linked by now, so that message would send the user to
            # re-upload something already on their channel.
            try:
                self._post_combat_logs(job, summary)
            except Exception as exc:
                logger.warning("Combat log upload failed", exc_info=True)
                self._skip_logs(summary, str(exc))

    def _upload_worker(self, job: UploadJob) -> None:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        index = job.start_index
        # Reset per job, not per process. `_last_pct` is only ever written
        # by a progress callback, so without this a job carries the PREVIOUS
        # job's number until its first chunk lands -- reaching on_retry's
        # bar, and the quit confirm, both of which state it as fact. Not
        # reset on the resume path: there the last value belongs to the same
        # job and is still true.
        self._last_pct = 0.0
        try:
            creds = uploader.load_credentials(paths.token_file())
            if uploader.needs_reauth(creds):
                creds = uploader.run_oauth_flow()
            elif not creds.valid:
                creds = uploader.refresh_credentials(creds)
            uploader.save_credentials(creds, paths.token_file())
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            if job.stitch:
                ordered = stitch.order_for_stitch(job.items)
                sources = [i.path for i in ordered]
                # A stream copy runs at disk speed, but a multi-gigabyte
                # join is still seconds of no other signal to the user, and
                # ffmpeg reports no progress this code can read. The bar
                # says "working" rather than inventing a percentage.
                # The neutral kind is set with the text for the same reason
                # on_progress does it: start_upload writes no status before
                # dispatching, so a red error from the previous attempt
                # would otherwise survive into this message.
                self._ports.progress(
                    0.0, "Stitching with FFmpeg…", mode="indeterminate", busy=True
                )
                with stitch.stitched(
                    sources, self._state.ffmpeg_bin, paths.tmp_dir()
                ) as merged:
                    self._ports.progress(0.0, busy=True)
                    # Armed HERE, inside the context manager and after the
                    # join, not at the top of the branch: D5 scopes cancel
                    # to the upload phase only. stitch.stitched() runs a
                    # bundled ffmpeg with no interruption seam, and a
                    # Cancel that did nothing for the minutes a join takes
                    # is worse than no Cancel at all.
                    self._ports.publish_cancel_available({"available": True})
                    vid = self._upload_one(
                        youtube, MediaFileUpload, merged, job, 0, 1, close_media=True
                    )
                # Every source recording gets the stitched video's URL,
                # each persisted against its own file identity.
                for row_id, item in zip(job.ids, job.items):
                    self._link(row_id, vid, item)
            else:
                total = len(job.items)
                self._ports.publish_cancel_available({"available": True})
                for index in range(job.start_index, total):
                    vid = self._upload_one(
                        youtube,
                        MediaFileUpload,
                        job.items[index].path,
                        job,
                        index,
                        total,
                    )
                    self._link(job.ids[index], vid, job.items[index])
            self._upload_done(job)
        except uploader.UploadCancelled:
            # `index` is the item that was interrupted, so items 0..index-1
            # finished and were _link()ed -- on the plain path those videos
            # are public on the channel right now, which is exactly what
            # format_upload_cancelled refuses to let the message hide. The
            # stitch path never advances `index`, and it is one video, so it
            # reports the zero case.
            done = 0 if job.stitch else index
            text = self._ports.format_upload_cancelled(done, len(job.items))
            # No _retry_state and no onRetryAvailable, per D5: Retry exists
            # to recover from a failure, and a stop is not one. Offering it
            # here would also re-arm the slot the Cancel button was just
            # occupying.
            self._retry_state = None
            # Not ERROR: the user asked for this. The bar keeps the ground
            # the job actually covered rather than resetting to 0, which
            # would contradict a sentence saying two of four are up.
            self._ports.status(text, "WARNING", busy=False)
            self._ports.progress(self._last_pct, kind="WARNING", busy=False)
        except uploader.UploadFailed as exc:
            # Stitched failures cannot resume: the context manager has
            # already deleted the merged file the session points at, which
            # is the correct trade for never leaking multi-GB temporaries.
            # Retry re-stitches instead.
            # Gated on RETRY as well, not just on the stitch path: only a
            # RETRY outcome enables Retry, so for anything else the
            # retained request is unreachable -- and it keeps the
            # MediaFileUpload, and with it an open handle on the user's own
            # recording, alive until the next failure replaces this state.
            # On Windows that blocks renaming or deleting that file.
            resumable = (
                exc.request is not None
                and not job.stitch
                and exc.outcome is uploader.Outcome.RETRY
            )
            self._retry_state = RetryState(
                job=job,
                # On the stitch path `index` never advances past
                # job.start_index, so resume_index is not the failing item --
                # but it is never read there either, since `resumable` above
                # forces request=None for stitch failures.
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._ports.alert("error", "Upload Failed", str(exc))
            self._ports.status(str(exc), "ERROR", busy=False)
            if exc.outcome is uploader.Outcome.RETRY:
                self._ports.publish_retry_available({"available": True})
        except Exception as exc:  # noqa: BLE001 - reported to the user, never raised
            self._retry_state = None
            # Covers a stitch failure too (StitchError isn't an
            # UploadFailed): if the bar was left indeterminate above, put it
            # back rather than leaving it animating behind the error.
            self._ports.progress(0.0, busy=False)
            self._ports.alert("error", "Upload Failed", str(exc))
            self._ports.status(f"Error: {exc}", "ERROR", busy=False)
        finally:
            # Every exit, including the success one: the slot is shared with
            # Retry and the two are never live at once, so a Cancel left
            # armed would sit beside the Retry a failure just enabled.
            self._ports.publish_cancel_available({"available": False})

    def _upload_one(
        self,
        youtube,
        MediaFileUpload,
        path,
        job,
        index,
        total,
        close_media: bool = False,
    ) -> str:
        body = uploader.build_body(
            job.title, job.description, job.privacy, job.category, index, total
        )
        media = MediaFileUpload(
            str(path), chunksize=uploader.CHUNK_SIZE, resumable=True
        )
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        def on_progress(fraction: float) -> None:
            self._last_pct = ((index + fraction) / total) * 100
            self._ports.progress(
                self._last_pct,
                self._ports.format_progress(index, total, fraction),
                busy=True,
            )

        def on_retry(attempt: int, delay: float) -> None:
            # Carries the last percentage rather than zero: the upload has
            # not lost the ground it covered, and a bar snapping backwards
            # while the text says "retrying" reads as a restart.
            self._ports.progress(
                self._last_pct,
                f"Network problem — retrying in {delay:.0f}s (attempt {attempt})",
                "WARNING",
                busy=True,
            )

        try:
            return uploader.upload(
                request,
                on_progress=on_progress,
                on_retry=on_retry,
                on_response=self._remember_channel,
                should_cancel=self._cancel.is_set,
            )
        finally:
            if close_media:
                # The caller is about to delete `path`, and Windows refuses
                # to unlink a file that still has an open handle. Off for
                # the plain path on purpose: UploadFailed hands the
                # resumable request to Retry, which resumes by reading from
                # this very stream.
                _close_media(media)

    def _remember_channel(self, response) -> None:
        """Learn the destination channel from a successful insert response.

        This is the only channel information the app can get: SCOPES holds
        youtube.upload alone, and channels.list needs a second scope, which
        would sign every existing user out.

        The settings write stays on this worker thread deliberately: it is
        a short plain-file write, and persisting here means the channel
        survives a crash before the next clean exit.

        Silent when the response carries no channel: the video uploaded
        fine, and a warning about a missing display field would be noise
        attached to a success.
        """
        channel_id, channel_title = uploader.channel_of(response)
        if not channel_title:
            return
        if (
            self._state.settings.get("channel_id") == channel_id
            and self._state.settings.get("channel_title") == channel_title
        ):
            return
        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg["channel_id"] = channel_id
                cfg["channel_title"] = channel_title
        except OSError:
            # A settings file that cannot be written must not fail an
            # upload that succeeded.
            logger.exception("could not persist the destination channel")
        self._ports.publish_channel(
            {
                "channel_id": channel_id,
                "channel_title": channel_title,
                # Rendered here, not in the page: format_destination states the
                # "learned from the first upload" case in words, and that
                # explanation is copy with its own test, not a template.
                "destination": self._ports.format_destination(
                    channel_title, self._state.settings.get("privacy", "")
                ),
            },
        )
        # The Settings account line names the channel, and this is the
        # moment the channel becomes known. Without this it would read a
        # bare "Connected" for the rest of the session that learned it, and
        # only come good on the next launch. Safe to assert "connected"
        # here: we are on the success path of an upload that just
        # authenticated.
        self._ports.publish_auth("connected")

    def cancel_upload(self) -> None:
        """Ask the upload thread to stop after the chunk it is sending.

        Sets a flag and returns: the bridge thread must not block, and the
        worker is the only thread that may touch the strip, _retry_state or
        the row links. Everything the user sees about the stop is composed
        where the stop is noticed (_upload_worker's UploadCancelled branch).

        Idempotent and safe when nothing is running -- the flag is cleared
        at every dispatch, so a set left behind by a click that raced the
        end of a job cannot reach the next one.

        No confirm. The action is not destructive: it stops something the
        user started, the videos already up are named in the message, and a
        dialog asking "are you sure you want to stop?" over a running
        transfer is the modal PRODUCT.md's "state cost before an
        irreversible action" rule is not about.
        """
        self._cancel.set()

    def retry(self) -> None:
        state = self._retry_state
        if state is None:
            return
        claim = self._work_gate.claim_upload()
        if not claim:
            self._ports.publish_retry_available({"available": False})
            if claim.reason == "upload":
                self._ports.alert(
                    "warning", "Busy", "An upload is already in progress."
                )
            else:
                self._ports.update_preparing(show_window=False)
            return
        try:
            # Disabled immediately, not by the worker: the click that got here
            # must not be repeatable while the resume is being set up.
            self._ports.publish_retry_available({"available": False})
            self._cancel.clear()
            self._upload_thread = threading.Thread(
                target=self._run_claimed_upload,
                args=(self._retry_worker, state),
                daemon=True,
            )
            self._upload_thread.start()
        except Exception:
            self._upload_thread = None
            self._work_gate.release_upload()
            raise

    def _retry_worker(self, state: RetryState) -> None:
        """Resume the interrupted upload, then finish the rest of the job."""
        if state.request is None:
            # Stitched, or no session to resume: redo the whole job. No
            # second confirm -- the user already approved this exact job,
            # and Retry is an explicit request to run it again.
            self._upload_worker(replace(state.job, start_index=0))
            return
        try:
            total = len(state.job.items)

            def on_progress(fraction: float) -> None:
                self._last_pct = ((state.resume_index + fraction) / total) * 100
                self._ports.progress(
                    self._last_pct,
                    self._ports.format_progress(state.resume_index, total, fraction),
                    busy=True,
                )

            # Armed for the resumed file too, not just for the tail that
            # _upload_worker picks up below. Without it the button would be
            # absent for one file and then appear part-way through the same
            # job, which is a control blinking in and out under the pointer
            # -- the hazard index.html's stitch note already records for
            # this screen.
            self._ports.publish_cancel_available({"available": True})
            vid = uploader.upload(
                state.request,
                on_progress=on_progress,
                should_cancel=self._cancel.is_set,
            )
            self._link(
                state.job.ids[state.resume_index],
                vid,
                state.job.items[state.resume_index],
            )
        except uploader.UploadCancelled:
            # Everything before resume_index finished on the earlier
            # attempt and is on the channel, so the count is about the job,
            # not about this resume. Retry is deliberately NOT re-offered:
            # a stop is not a failure (D5).
            self._retry_state = None
            self._ports.status(
                self._ports.format_upload_cancelled(
                    state.resume_index, len(state.job.items)
                ),
                "WARNING",
                busy=False,
            )
            self._ports.progress(self._last_pct, kind="WARNING", busy=False)
            self._ports.publish_cancel_available({"available": False})
            return
        except uploader.UploadFailed as exc:
            # Same gate as _upload_worker, for the same two reasons: only a
            # RETRY outcome re-enables Retry, so keeping the request for any
            # other outcome retains something unreachable -- and that
            # something owns an open handle on the user's own recording,
            # which blocks renaming or deleting it on Windows. Dropping the
            # reference is not enough on its own: closing is left to
            # MediaFileUpload.__del__, whose timing is exactly what made the
            # stitched temp file survive in the first place.
            retryable = exc.outcome is uploader.Outcome.RETRY
            if not retryable:
                _close_media(getattr(exc.request, "resumable", None))
            self._retry_state = replace(
                state, request=exc.request if retryable else None
            )
            self._ports.status(str(exc), "ERROR", busy=False)
            self._ports.publish_cancel_available({"available": False})
            if retryable:
                self._ports.publish_retry_available({"available": True})
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            # _upload_worker arms and disarms the control itself, in its own
            # finally, so this hands the slot straight over rather than
            # disarming between the two halves of one job.
            self._upload_worker(replace(state.job, start_index=state.resume_index + 1))
        else:
            self._upload_done(state.job)
            self._ports.publish_cancel_available({"available": False})

    # ----- combat logs --------------------------------------------------------

    def _log_target(self) -> LogTarget:
        """Resolve the webhook and the Gamelogs folder, or say what is wrong.

        Read live rather than snapshotted, for the reason `start_upload`
        records about `job.logs`: Settings is reachable between a dispatch
        and the post, so the answer has to describe what the post will
        actually find.

        Reports, never acts. Both clauses are handed back for the caller to
        frame, because the same fact reads differently after a successful
        upload than it does on its own.
        """
        cfg = self._state.settings
        raw = cfg.get("discord_webhook") or ""
        configured = bool(raw.strip())
        hook, error = discord.parse_webhook(raw)
        if hook is None:
            problem = (
                f"{error} Set it up in Settings."
                if configured
                else "no Discord webhook is configured. Set one in Settings."
            )
            return LogTarget(None, None, problem, configured)

        gamelogs = cfg.get("gamelogs_dir")
        gamelogs_dir = Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()
        if gamelogs_dir is None or not gamelogs_dir.is_dir():
            return LogTarget(
                None,
                None,
                "your EVE Gamelogs folder was not found. Set it in Settings.",
                configured,
            )
        return LogTarget(hook, gamelogs_dir, "", configured)

    def post_recent_logs(self) -> None:
        """Post the last hour's combat logs to Discord. No video involved.

        Combat logs are otherwise the TAIL of an upload, so the only way to
        send them was to publish a video -- and the case this exists for is
        the fight that was not recorded, or was recorded and is not worth
        uploading. It also keeps PRODUCT.md's independence rule whole: no
        Google account is touched here.

        The window is wall-clock and owes nothing to the list, so none of
        `_post_combat_logs`'s selection machinery applies: no ids, no
        `_probe_now`, and no "the time window cannot be worked out".

        Refusals are reported on the strip rather than gating the button.
        The page CANNOT be relied on to hold a current answer to "is a
        webhook configured": nothing pushes a settings payload, and the
        only refresh is `list.js`'s own `get_settings` call, which it makes
        at load and then only when the list comes back EMPTY. A user who
        configures a webhook with recordings on screen never triggers it,
        so a control disabled on that fact would stay dead until the next
        launch -- which is what `WM.setEnabled`'s rule forbids. The button
        is live and Python says why, the posture `Open folder` and `Delete
        selected` already take.

        Every exit re-states the running flag, and `list_rows` re-states it
        too. That is a defence against a lost push: `_push` swallows every
        `evaluate_js` failure, and a push into a HIDDEN window is swallowed
        outright -- this is a tray app whose window is routinely closed
        mid-work -- so a disarm can go missing and leave the button drawn
        as disabled. The repair CANNOT come from the button itself, because
        a disabled button takes neither a click nor a keypress. It comes
        from the next list rebuild, which a watcher announcement, a delete
        or a folder change all produce.
        """
        if self.logs_busy():
            self._ports.publish_log_post_running({"running": True})
            self._ports.status("Combat logs are already being posted.", "WARNING")
            return
        if self.busy():
            self._ports.publish_log_post_running({"running": False})
            self._ports.status(
                "An upload is running. Post the logs when it finishes.", "WARNING"
            )
            return

        target = self._log_target()
        if target.hook is None or target.gamelogs_dir is None:
            self._ports.publish_log_post_running({"running": False})
            # "not posted", never "skipped": nothing else ran, so there is no
            # successful half for this to be a footnote to.
            self._ports.status(f"Combat logs not posted: {target.problem}", "WARNING")
            return

        self._ports.publish_log_post_running({"running": True})
        # Claimed under the lock, and the claim is what makes this safe:
        # pywebview serves each bridge call on its own thread, and a guard
        # written against thread.is_alive() would answer False for the
        # handle assigned a microsecond ago and let a second post through.
        with self._logs_lock:
            if self._logs_running:
                return
            self._logs_running = True
        try:
            self._logs_thread = self._ports.spawn(
                target=self._recent_logs_worker,
                args=(target.hook, target.gamelogs_dir),
                daemon=True,
            )
            self._logs_thread.start()
        except RuntimeError:
            # A claim taken and never released is the worst outcome this
            # method has: nothing else clears it, so the button would
            # refuse for the rest of the process. "can't start new thread"
            # is rare, and it is exactly the failure that would latch it.
            logger.exception("Could not start the combat-log post")
            with self._logs_lock:
                self._logs_running = False
            self._ports.publish_log_post_running({"running": False})
            self._ports.status("Combat logs not posted: it could not start.", "WARNING")

    def _recent_logs_worker(self, hook, gamelogs_dir) -> None:
        """The standalone post, on its own thread.

        The clock is read HERE rather than in the bridge method so that one
        function decides the window and it is the one that builds the
        archive. The hour therefore ends when the work starts rather than
        when the click landed; thread scheduling puts no bound on that gap,
        and combatlog.WINDOW_PADDING widens the selection by five minutes
        each side anyway, so no fight sits near enough to the edge for the
        difference to decide whether it is included.
        """
        try:
            end_utc = datetime.datetime.now(datetime.UTC)
            start_utc = end_utc - RECENT_LOG_WINDOW
            self._combat_log_worker(hook, gamelogs_dir, start_utc, end_utc, None)
        finally:
            # A finally at the outermost frame. _combat_log_worker swallows
            # its own failures, so this is belt and braces -- and it is the
            # brace that matters, because the alternative is a post nothing
            # can start again and a button that is dead for the session.
            with self._logs_lock:
                self._logs_running = False
            self._ports.publish_log_post_running({"running": False})

    def _skip_logs(self, summary: str, reason: str) -> None:
        """Report a log half that could not run, without unwinning the video.

        A status line rather than a dialog, and deliberately not an ERROR:
        the upload the user asked for DID happen, and a modal apologising
        for the half that did not would read as though the whole thing had
        failed. It replaces the success line on the strip rather than
        following it, so the last thing said never overstates what was done.

        `summary` is _upload_summary's sentence, threaded down rather than
        parked on self: the strip's terminal line has to name the upload
        first and the side-effect second (round 3's finding 13), and the
        upload is the caller's fact, not this method's.
        """
        self._ports.status(
            f"{summary}. Combat logs skipped: {reason}", "WARNING", busy=False
        )

    def _post_combat_logs(self, job: UploadJob, summary: str) -> None:
        """The log half of a combined upload. Best-effort, by design.

        Every refusal here was a blocking warning dialog when this ran from
        its own button, and had to stop being one when the button merged:
        the video is already on YouTube by the time this runs, so a missing
        Discord webhook can no longer be allowed to mean "nothing was
        uploaded". Genuine post FAILURES still alert, in _combat_log_worker
        -- those leave an archive on disk the user needs to be told about.

        Runs on the upload worker thread, not the bridge thread, so the
        window keeps painting through the probe below.
        """
        target = self._log_target()
        if target.hook is None or target.gamelogs_dir is None:
            if not target.configured:
                # NOT configured is not the same as configured-and-broken,
                # and since Uploader 8 removed the checkbox the difference
                # decides whether saying anything is honest. Nobody asked
                # for logs on this run -- logs are unconditional now -- so
                # reporting them as "skipped" would put a WARNING strip on
                # every upload a webhook-less install ever performs. That
                # is precisely the failure format_upload_confirm's
                # docstring records: a strip "reading like a recurring
                # failure rather than an unconfigured option".
                #
                # The no-webhook case is a fact about the install, and it
                # belongs on the panel where it is true all the time, not
                # on the strip once per upload. R1 renders it there.
                #
                # `post_recent_logs` takes the opposite decision on this
                # same LogTarget, and both are right: there the post is the
                # whole action, so silence would leave a click that did
                # nothing and said nothing.
                return
            # Configured and unusable IS worth a strip: the user set
            # something, it does not parse, and nothing else will say so.
            # Same for a Gamelogs folder that cannot be found.
            self._skip_logs(summary, target.problem)
            return
        gamelogs_dir = target.gamelogs_dir

        # Resolve any still-pending probe for THIS selection first: an
        # unprobed recording also leaves duration None, and refusing on that
        # would blame ffprobe for a probe that simply had not reached these
        # files yet.
        pairs = list(zip(job.ids, job.items))
        self._probe_now(pairs)
        missing = [i.path.name for _, i in pairs if i.duration is None]
        if missing:
            self._skip_logs(
                summary,
                "no readable duration for "
                + ", ".join(missing)
                + ", so the time window cannot be worked out (this usually "
                "means ffprobe is unavailable).",
            )
            return

        # Union across the selection: earliest start to latest end, one
        # archive, matching how stitching treats a multi-selection.
        infos = [i for _, i in pairs]
        start_utc = min(
            datetime.datetime.fromtimestamp(i.mtime - i.duration, datetime.UTC)
            for i in infos
        )
        end_utc = max(
            datetime.datetime.fromtimestamp(i.mtime, datetime.UTC) for i in infos
        )

        self._combat_log_worker(target.hook, gamelogs_dir, start_utc, end_utc, summary)

    def _probe_now(self, pairs) -> None:
        """Resolve a selection's durations synchronously, in place.

        Called from the log half, which cannot work out a time window
        without the answer. Blocking here is fine and blocking in the Tk
        version was not: this runs on the upload worker thread, so the
        window keeps painting and the progress line below is genuinely live
        rather than a repaint forced between two frozen frames. (It ran on
        pywebview's bridge thread when combat logs had their own button --
        also off the UI thread, and equally safe.)

        A definitive result is REMEMBERED and the cache saved, exactly as
        _apply_duration did. Setting the in-memory flag alone would stop the
        background walker re-probing this row for the rest of the session
        and then lose the measurement at exit, so the file is re-probed on
        every launch -- precisely the cost the cache exists to avoid.
        """
        unprobed = [(rid, info) for rid, info in pairs if not info.probed]
        if not unprobed:
            return
        total = len(unprobed)
        measured = 0
        for index, (row_id, info) in enumerate(unprobed, start=1):
            self._ports.status(
                f"Reading recording lengths… ({index}/{total})", busy=True
            )
            duration, definitive = library.probe(info.path, self._state.ffprobe_bin)
            with self._publication_lock:
                # A background answer may have become definitive while this
                # synchronous probe was away. It wins in RAM AND on disk.
                if info.probed and info.answered:
                    continue
                if definitive:
                    durations.remember(
                        self._cache, info.path, info.size, info.mtime, duration
                    )
                    measured += 1
                self._apply_duration(row_id, duration, definitive)
        if measured:
            durations.save(self._durations_file, self._cache)

    def _combat_log_worker(
        self, hook, gamelogs_dir, start_utc, end_utc, summary: str | None
    ) -> None:
        """Collect, zip, and post the logs. Runs on the upload thread.

        No longer a thread target of its own: it is the tail of the upload
        the user confirmed, which is what keeps one busy guard covering both
        halves. `post_recent_logs` is the exception and passes summary=None.

        Every line this leaves BEHIND leads with `summary`, the sentence
        naming the upload that succeeded. Round 3's finding 13 caught the
        version that did not: the last thing the strip said after a
        successful upload was "Posted combatlogs-....zip (15 KB)." -- the
        secondary side-effect standing in for the primary action. The
        in-flight lines below do not, because they are not terminal: they
        are replaced within seconds by one that is.

        `summary` is None when the post IS the primary action, and then the
        terminal lines stand alone. That does not weaken finding 13, it
        satisfies it: the rule is that the primary action is said first,
        and here there is no upload to name -- leading with one would be
        reporting something that never happened.
        """

        def terminal(sentence: str) -> str:
            return f"{summary}. {sentence}" if summary else sentence

        archive = None
        try:
            self._ports.status("Collecting combat logs…", busy=True)
            selection = combatlog.select_logs(gamelogs_dir, start_utc, end_utc)
            if not selection.logs:
                self._ports.alert(
                    "info",
                    "No logs found",
                    (
                        "No EVE logs overlap that window.\n\n"
                        f"Window (UTC): {start_utc:%Y-%m-%d %H:%M} to {end_utc:%H:%M}\n"
                        f"Folder: {gamelogs_dir}\n\n"
                        "EVE writes log timestamps in UTC, so this window is in "
                        "UTC too."
                    ),
                )
                # SUCCESS, where the bare "No combat logs found." was
                # neutral: the sentence now leads with an upload that did
                # work, and leaving it FG would repaint a success grey.
                self._ports.status(
                    terminal("No combat logs found."), "SUCCESS", busy=False
                )
                return

            stamp = start_utc.strftime("%Y-%m-%d_%H-%M")
            out = paths.tmp_dir() / f"combatlogs-{stamp}.zip"
            self._ports.status("Building archive…", busy=True)
            archive = combatlog.build_archive(selection, out, start_utc, end_utc)

            content = combatlog.summarize_archive(archive, start_utc, end_utc)
            self._ports.status("Posting to Discord…", busy=True)
            result = discord.post_archive(hook, archive.path, content)

            if result.ok:
                # Only remove the archive once Discord has it.
                with contextlib.suppress(OSError):
                    archive.path.unlink()
                # Discord's own message does not mention the cap; append the
                # same drop note so the status line does not quietly
                # disagree with the content the user just sent.
                status_text = result.message
                note = combatlog.dropped_note(archive.dropped)
                if note:
                    status_text += f" ({note})"
                self._ports.status(terminal(status_text), "SUCCESS", busy=False)
            else:
                # Keep the archive: the window is fixed by the recording and
                # there is no UI for selecting fewer logs, so a user told
                # "too large" has no move available unless the file survives.
                self._ports.alert(
                    "error",
                    "Combat log upload failed",
                    (
                        f"{result.message}\n\nThe archive was kept so you can "
                        f"upload it by hand:\n{archive.path}"
                    ),
                )
                # Still ERROR, unlike _skip_logs' WARNING: this half was
                # attempted and failed with an archive left on disk for the
                # user to act on, which is a different thing from a half
                # that never ran. The upload still gets said first.
                self._ports.status(terminal(result.message), "ERROR", busy=False)
        except Exception as exc:  # noqa: BLE001 - reported, and the archive is kept on disk
            # post_archive never raises, but build_archive and
            # summarize_archive can -- and by then the archive may already be
            # on disk. Without this the user gets a bare str(exc) and the
            # "kept so you can upload it by hand" promise, which the failed
            # -post branch above makes, quietly does not hold on this path.
            detail = str(exc)
            if archive is not None and archive.path.exists():
                detail += (
                    "\n\nThe archive was kept so you can upload it "
                    f"by hand:\n{archive.path}"
                )
            self._ports.alert("error", "Combat log upload failed", detail)
            self._ports.status(terminal(f"Error: {exc}"), "ERROR", busy=False)
