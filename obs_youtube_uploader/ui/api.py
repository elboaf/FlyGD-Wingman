"""The js_api bridge: everything the page can call, everything Python pushes.

Two rules govern this module, and both are load-bearing.

**Methods only.** pywebview builds its JavaScript proxy by walking the
public attributes of this object. A public attribute holding a
`webview.Window` (or a `pystray.Icon`) sends that walk into the WinForms
native object, where `Rectangle.Empty` returns itself; it recurses until
`RecursionError` kills the process, roughly eight seconds after launch,
with nothing in the traceback naming the attribute responsible. Every
non-method attribute here is therefore underscore-prefixed, and
`test_api.py` asserts it rather than trusting anyone to remember.

**Workers never touch the page directly.** They call `_push`, which is the
successor to `UploaderWindow._ui` -- but semantic where `_ui` marshalled
widget method calls. `evaluate_js` is safe to call from any thread; there
is no UI thread to marshal onto.

`_window` is assigned by ui.window.create() after construction rather than
passed in: create_window() needs js_api before a window object exists.
"""
import datetime
import json
import logging
import queue
import threading
import uuid
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path

from .. import (bookmarks, combatlog, discord, durations, evewindows,
                library, obsconfig, paths, settings as settings_mod, stitch,
                uploader)
from . import copy as copy_mod
from .rows import RowSnapshot
from .scheduler import Scheduler

logger = logging.getLogger(__name__)

# 100ms, carried over from app.PROBE_DRAIN_MS: fast enough that durations
# appear to fill in live, slow enough that a folder of a hundred recordings
# is batched into a handful of drains rather than a hundred saves.
PROBE_DRAIN_S = 0.1

# Long enough for WebView2 to load the page and run app.js, short enough
# that a first-run user does not stare at an empty window wondering. The
# push is idempotent from the page's side, so an early one costs nothing
# beyond a logged drop.
FIRST_RUN_PUSH_S = 1.5

YOUTUBE_WATCH = "https://www.youtube.com/watch?v={video_id}"


def _folder_dialog_kind():
    """pywebview's folder-dialog constant, imported at call time.

    Kept behind a function for two reasons: webview is not installed on the
    Linux box these tests run on, and 6.x renamed this constant once
    already (FOLDER_DIALOG -> FileDialog.FOLDER), so exactly one line has
    to change if it moves again.
    """
    import webview
    return webview.FileDialog.FOLDER


def _open_file_dialog_kind():
    """pywebview's open-file-dialog constant, imported at call time.

    Same seam as _folder_dialog_kind above, for the same two reasons: the
    tests run on a box with no webview installed, and the constant has
    moved once already. Importing webview inline at the call site instead
    is what broke the import tests -- there was no seam left to patch.
    """
    import webview
    return webview.FileDialog.OPEN


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


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""
    job: UploadJob
    resume_index: int
    request: object | None


@dataclass
class AppState:
    """Everything the bridge needs that is not the page.

    recording_dir is None until first run completes. Every consumer must
    handle that rather than substituting a default: a fallback to the home
    directory would have list_rows() scan it for recordings.

    `settings` is REPLACED wholesale by save_settings rather than mutated,
    so anything holding the original dict goes stale -- which is why the
    poll loop and the bridge both read it through this object each time.
    """
    recording_dir: Path | None
    settings: dict
    ffmpeg_bin: str | None = None
    ffprobe_bin: str | None = None
    # None until ui.window.create() wires up the HotkeyEngine. Every bridge
    # method that touches it must handle that -- e.g. by no-op'ing rather
    # than crashing the bridge thread on an AttributeError.
    engine: object | None = None


class Api:
    """JS-callable methods only. Every other attribute underscore-prefixed."""

    def __init__(self, state: AppState, *,
                 id_factory=lambda: uuid.uuid4().hex,
                 rows=None, durations_file=None,
                 drain_interval_s=PROBE_DRAIN_S,
                 spawn=threading.Thread, probe=library.probe,
                 timer=threading.Timer, preview_host=None,
                 client_layouts=None):
        self._state = state
        self._window = None          # assigned by ui.window.create()
        # Injectable purely to make ids predictable in a test that needs to
        # assert on one; production never overrides it.
        self._id_factory = id_factory
        self._dialog_lock = threading.Lock()
        # request id -> [Event, answer]. An entry exists only while a worker
        # is parked on it.
        self._dialogs: dict[str, list] = {}

        # None off Windows and in most tests: the preview subsystem is
        # optional and every call site below tolerates its absence.
        self._preview_host = preview_host

        # None off Windows and in most tests, like _preview_host above.
        # Deliberately NOT gated on preview.enabled: this moves the EVE
        # client windows themselves and has nothing to do with previews
        # beyond sharing a tab.
        self._client_layouts = client_layouts

        self._rows = rows if rows is not None else RowSnapshot()
        self._durations_file = durations_file or paths.durations_file()
        self._cache = durations.load(self._durations_file)
        self._drain_interval_s = drain_interval_s
        self._spawn = spawn
        self._probe = probe
        self._timer = timer
        self._probe_queue: queue.Queue = queue.Queue()
        # Every list_rows() bumps this. A probe result carrying a stale
        # generation refers to rows that have since been replaced, and is
        # dropped rather than written into the current list.
        self._generation = 0
        self._drain: Scheduler | None = None

        self._upload_thread: threading.Thread | None = None
        self._delete_thread: threading.Thread | None = None
        self._retry_state: RetryState | None = None
        self._links: dict[str, str] = {}
        self._last_pct: float = 0.0
        self._watcher = None
        self._auth_thread: threading.Thread | None = None
        self._on_recording_dir_ready = None

    # ----- page -> Python -------------------------------------------------

    def dialog_response(self, request_id: str, ok: bool) -> None:
        """Release the worker parked on *request_id*.

        An unknown id is ignored rather than raising. The page can answer a
        dialog whose worker has already given up, and a page reload leaves
        the user free to click a button belonging to a previous run of the
        app -- neither is an error, and an exception raised here surfaces
        only as a rejected promise in a page nobody is debugging.
        """
        with self._dialog_lock:
            entry = self._dialogs.get(request_id)
        if entry is None:
            logger.debug("Dialog response for unknown request %s", request_id)
            return
        entry[1] = bool(ok)
        entry[0].set()

    def minimize(self) -> None:
        self._window.minimize()

    def close(self) -> None:
        """HIDE, never destroy. This is a tray application.

        The Tk window bound WM_DELETE_WINDOW to hide() for the same reason:
        the watcher must keep running after the user closes the window, and
        destroying it here would return from webview.start(), stop the tray
        icon, and end the process -- so closing the window would silently
        turn the watcher off.

        Only the tray's Quit destroys, and it calls window.destroy()
        directly rather than coming through this method.
        """
        self._window.hide()

    # ----- Python -> page -------------------------------------------------

    def _push(self, handler: str, payload) -> None:
        """Fire-and-forget one message at the page.

        The `handler &&` guard is not defensive padding: pushes can land
        before app.js has finished defining its handlers (the watcher
        scheduler and the OAuth worker both start early), and an undefined
        call is a ReferenceError raised inside a callback with no console
        attached in a windowed build.

        Failures are swallowed for the same reason `_ui` could not fail:
        this runs on upload and probe workers, and a window destroyed
        mid-upload must cost a status line, not the upload.
        """
        script = (f"window.{handler} && "
                  f"window.{handler}({json.dumps(payload)})")
        try:
            self._window.evaluate_js(script)
        except Exception:
            logger.debug("Push of %s failed", handler, exc_info=True)

    def _alert(self, kind: str, title: str, body: str) -> None:
        """Non-blocking message box: info, error, or warning."""
        self._push("onDialog", {"kind": kind, "title": title, "body": body,
                                "request_id": None})

    def _confirm(self, title: str, body: str) -> bool:
        """Ask the page a yes/no question and block until it answers.

        This blocks the CALLING thread, which must be a worker -- exactly as
        `messagebox.askyesno` blocked the Tk main thread it was called on.
        The difference is which thread pays: calling this from the thread
        that services `pywebview.api.*` would deadlock, because
        `dialog_response` could never be delivered.

        The Event is registered before the push, not after: `evaluate_js`
        can complete and the user can answer before this method resumes.
        """
        request_id = self._id_factory()
        event = threading.Event()
        entry = [event, False]
        with self._dialog_lock:
            self._dialogs[request_id] = entry
        try:
            self._push("onDialog", {"kind": "confirm", "title": title,
                                    "body": body, "request_id": request_id})
            event.wait()
            return bool(entry[1])
        finally:
            with self._dialog_lock:
                self._dialogs.pop(request_id, None)

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
        """
        if self._state.recording_dir is None:
            return
        self._generation += 1
        generation = self._generation
        self._stop_drain()

        rebuilt = self._rows.rebuild(self._state.recording_dir, preselect=preselect)
        ids = [row["id"] for row in rebuilt]
        infos = self._rows.resolve_many(ids)
        pending = durations.resolve(self._cache, infos)

        # Identity, not equality: VideoInfo is a plain dataclass, so two
        # recordings with the same size and mtime compare equal and an `in`
        # test over the pending list would probe the wrong row.
        outstanding = {id(info) for info in pending}

        # Re-apply cache hits into the snapshot BEFORE pushing. This is
        # rows.py's documented contract -- "rebuild() therefore produces
        # rows with durations unknown and the caller re-applies cache hits
        # through set_duration" -- and skipping it failed silently in a way
        # nothing else caught: rebuild() freezes `duration` into each Row
        # while it is still unknown, and rows() serialises those frozen
        # Rows, NOT the VideoInfos that resolve() mutates. A cache hit is
        # also absent from `pending`, so it never earns an onDuration push
        # either. The Length column therefore sat on the measuring glyph
        # forever for every already-probed recording -- after the first run,
        # all of them -- while the selection summary, computed in Python
        # straight off the infos, showed the real total. The Tk build did
        # not have this: it called resolve() before inserting any row.
        #
        # definitive=True: a cached entry is a probe result that already
        # survived that judgement when it was stored.
        for row_id, info in zip(ids, infos):
            if id(info) not in outstanding:
                self._rows.set_duration(row_id, info.duration, True)

        self._push("onRows", {"rows": self._rows.rows()})
        work = [(row_id, info) for row_id, info in zip(ids, infos)
                if id(info) in outstanding]
        if work:
            self._start_probe(work, generation)

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
            "summary": copy_mod.format_selection_summary(infos),
            "title_hint": copy_mod.format_title_hint(len(infos), bool(stitch)),
        }

    # ----- delete, open, copy ------------------------------------------------

    def delete_selected(self, ids) -> None:
        pairs = [(rid, info) for rid in ids
                 if (info := self._rows.resolve(rid)) is not None]
        if not pairs:
            self._alert("warning", "No Selection",
                        "Select at least one video to delete.")
            return
        # Same reason as _confirm_then_upload: _confirm blocks until the
        # page answers, and the page's answer arrives on the bridge thread
        # this method is running on.
        self._delete_thread = threading.Thread(
            target=self._delete_worker, args=(pairs,), daemon=True)
        self._delete_thread.start()

    def _delete_worker(self, pairs) -> None:
        infos = [info for _, info in pairs]
        names = "\n".join(f"  • {i.path.name}" for i in infos)
        if not self._confirm(
                "Confirm Delete",
                f"Permanently delete these files from disk?\n\n{names}"
                "\n\nThis cannot be undone."):
            return
        deleted, failures = library.delete([i.path for i in infos])
        # Forget only what actually went. A file that failed to delete still
        # exists, and dropping its seen-entry would make the watcher
        # announce it again as if it were new.
        failed_paths = {p for p, _ in failures}
        if self._watcher is not None:
            for info in infos:
                if info.path not in failed_paths:
                    self._watcher.forget(info.path)
        for row_id, _ in pairs:
            self._links.pop(row_id, None)
        self.list_rows()
        message = f"Deleted {deleted} file(s)."
        if failures:
            message += f" {len(failures)} failed."
        self._push("onStatus", {"text": message, "kind": "FG"})

    def copy_path(self, row_id: str) -> str:
        """Return the row's link for the page to put on the clipboard.

        The write itself is the page's job: with Tk gone there is no
        toolkit clipboard, and navigator.clipboard is right there. Returning
        it rather than pushing it keeps this a plain request/response, which
        is what a button press is.
        """
        url = self._links.get(row_id, "")
        if not url:
            return ""
        self._push("onStatus", {"text": "Link copied to clipboard",
                                "kind": "SUCCESS"})
        return url

    def open_path(self, row_id: str) -> None:
        url = self._links.get(row_id)
        if url:
            webbrowser.open(url)

    # ----- durations --------------------------------------------------------

    def _start_probe(self, work, generation: int) -> None:
        """Probe on a worker; apply results from a drain loop.

        The worker touches neither the snapshot nor the page: it pushes onto
        a queue that the drain reads. Pushing `onDuration` straight from the
        worker would be shorter, but it would also make the durations cache
        a structure written from two threads, and it would give up the
        batching that makes the per-tick save affordable.
        """
        def worker() -> None:
            try:
                for row_id, info in work:
                    if generation != self._generation:
                        break  # A newer list_rows owns the list now.
                    if info.probed:
                        continue  # Already resolved on demand.
                    duration, definitive = self._probe(info.path,
                                                       self._state.ffprobe_bin)
                    self._probe_queue.put(
                        (generation, row_id, info, duration, definitive))
            except Exception:
                # probe() swallows its own failures, so reaching here means
                # something unforeseen. Rows left unprobed sit on "…", and in
                # a windowed build stderr goes nowhere, so log it.
                logger.warning("Duration probe worker failed", exc_info=True)
            finally:
                # Always sent, including on early exit, so the drain loop
                # knows to stop rescheduling itself.
                self._probe_queue.put((generation, None, None, None, False))

        self._drain = Scheduler(
            self._drain_interval_s,
            lambda: self._drain_probes(generation),
            timer=self._timer,
        )
        self._spawn(target=worker, daemon=True).start()
        self._drain.start()

    def _drain_probes(self, generation: int) -> None:
        """Apply whatever the probe worker has finished since the last tick."""
        if generation != self._generation:
            self._stop_drain()  # Superseded; the newer list has its own loop.
            return
        done = False
        applied = 0
        while True:
            try:
                gen, row_id, info, duration, definitive = self._probe_queue.get_nowait()
            except queue.Empty:
                break
            if gen != self._generation:
                continue  # Straggler from a superseded refresh.
            if info is None:
                done = True
                continue
            if definitive:
                durations.remember(self._cache, info.path, info.size,
                                   info.mtime, duration)
            self._rows.set_duration(row_id, duration, definitive)
            self._push("onDuration", {"id": row_id, "duration": duration,
                                      "definitive": definitive})
            applied += 1
        # Per tick rather than once at the end: a cold scan of a large folder
        # takes a while, and a user who opens the window from the tray and
        # quits partway through would otherwise lose every duration measured
        # so far and start the whole scan again next launch.
        if applied:
            durations.save(self._durations_file, self._cache)
        if done:
            self._stop_drain()

    def _stop_drain(self) -> None:
        drain, self._drain = self._drain, None
        if drain is not None:
            drain.stop()

    # ----- upload -----------------------------------------------------------

    def _busy(self) -> bool:
        return self._upload_thread is not None and self._upload_thread.is_alive()

    def start_upload(self, title, description, stitch, logs, ids) -> None:
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
        pairs = [(rid, info) for rid in ids
                 if (info := self._rows.resolve(rid)) is not None]
        if not pairs:
            self._alert("warning", "No Selection",
                        "Select at least one video to upload.")
            return
        if stitch and len(pairs) < 2:
            self._alert("warning", "Stitch",
                        "Select at least two videos to stitch.")
            return
        if self._busy():
            self._alert("warning", "Busy", "An upload is already in progress.")
            return
        job = UploadJob(items=[i for _, i in pairs], ids=[r for r, _ in pairs],
                        title=title, description=description, stitch=bool(stitch),
                        privacy=privacy, category=category, logs=bool(logs))
        self._upload_thread = threading.Thread(
            target=self._confirm_then_upload, args=(job,), daemon=True)
        self._upload_thread.start()

    def _confirm_then_upload(self, job: UploadJob) -> None:
        # The confirm runs on the worker, not in start_upload, because
        # _confirm blocks until the page calls dialog_response -- and
        # start_upload is running on pywebview's bridge thread, which is
        # where that answer has to arrive. Asking there would deadlock the
        # bridge on itself. The busy guard is already set by the time this
        # dialog is up, which is also what we want.
        body = copy_mod.format_upload_confirm(
            job.items, job.title, job.privacy,
            self._state.settings.get("channel_title", ""), job.stitch, job.logs)
        if not self._confirm("Confirm Upload", body):
            return
        self._upload_worker(job)

    def _link(self, row_id: str, video_id: str) -> None:
        """Record and announce one uploaded row.

        _links is kept here as well as in the snapshot because the
        RowSnapshot contract is write-only for links, and open_path /
        copy_path need to read one back.
        """
        self._links[row_id] = YOUTUBE_WATCH.format(video_id=video_id)
        self._rows.set_link(row_id, video_id)
        self._push("onLink", {"id": row_id, "video_id": video_id})

    def _upload_done(self, job: UploadJob) -> None:
        self._retry_state = None
        self._push("onStatus", {"text": "Upload complete!", "kind": "SUCCESS"})
        self._push("onProgress", {"mode": "determinate", "pct": 100.0,
                                  "text": "", "kind": "SUCCESS"})
        self._push("onRetryAvailable", {"available": False})
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
                self._post_combat_logs(job)
            except Exception as exc:
                logger.warning("Combat log upload failed", exc_info=True)
                self._skip_logs(str(exc))

    def _upload_worker(self, job: UploadJob) -> None:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        index = job.start_index
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
                self._push("onProgress", {"mode": "indeterminate", "pct": 0.0,
                                          "text": "Stitching with FFmpeg…",
                                          "kind": "FG"})
                with stitch.stitched(sources, self._state.ffmpeg_bin,
                                     paths.tmp_dir()) as merged:
                    self._push("onProgress", {"mode": "determinate", "pct": 0.0,
                                              "text": "", "kind": "FG"})
                    vid = self._upload_one(youtube, MediaFileUpload, merged,
                                           job, 0, 1, close_media=True)
                for row_id in job.ids:
                    self._link(row_id, vid)
            else:
                total = len(job.items)
                for index in range(job.start_index, total):
                    vid = self._upload_one(youtube, MediaFileUpload,
                                           job.items[index].path, job, index, total)
                    self._link(job.ids[index], vid)
            self._upload_done(job)
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
            resumable = (exc.request is not None and not job.stitch
                         and exc.outcome is uploader.Outcome.RETRY)
            self._retry_state = RetryState(
                job=job,
                # On the stitch path `index` never advances past
                # job.start_index, so resume_index is not the failing item --
                # but it is never read there either, since `resumable` above
                # forces request=None for stitch failures.
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._alert("error", "Upload Failed", str(exc))
            self._push("onStatus", {"text": str(exc), "kind": "ERROR"})
            if exc.outcome is uploader.Outcome.RETRY:
                self._push("onRetryAvailable", {"available": True})
        except Exception as exc:
            self._retry_state = None
            # Covers a stitch failure too (StitchError isn't an
            # UploadFailed): if the bar was left indeterminate above, put it
            # back rather than leaving it animating behind the error.
            self._push("onProgress", {"mode": "determinate", "pct": 0.0,
                                      "text": "", "kind": "FG"})
            self._alert("error", "Upload Failed", str(exc))
            self._push("onStatus", {"text": f"Error: {exc}", "kind": "ERROR"})

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total,
                    close_media: bool = False) -> str:
        body = uploader.build_body(job.title, job.description, job.privacy,
                                   job.category, index, total)
        media = MediaFileUpload(str(path), chunksize=uploader.CHUNK_SIZE,
                                resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body,
                                          media_body=media)

        def on_progress(fraction: float) -> None:
            self._last_pct = ((index + fraction) / total) * 100
            self._push("onProgress", {
                "mode": "determinate", "pct": self._last_pct,
                "text": copy_mod.format_progress(index, total, fraction),
                "kind": "FG"})

        def on_retry(attempt: int, delay: float) -> None:
            # Carries the last percentage rather than zero: the upload has
            # not lost the ground it covered, and a bar snapping backwards
            # while the text says "retrying" reads as a restart.
            self._push("onProgress", {
                "mode": "determinate", "pct": self._last_pct,
                "text": f"Network problem — retrying in {delay:.0f}s "
                        f"(attempt {attempt})",
                "kind": "WARNING"})

        try:
            return uploader.upload(request, on_progress=on_progress,
                                   on_retry=on_retry,
                                   on_response=self._remember_channel)
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
        if (self._state.settings.get("channel_id") == channel_id
                and self._state.settings.get("channel_title") == channel_title):
            return
        self._state.settings["channel_id"] = channel_id
        self._state.settings["channel_title"] = channel_title
        try:
            settings_mod.save(self._state.settings)
        except OSError:
            # A settings file that cannot be written must not fail an
            # upload that succeeded.
            logger.exception("could not persist the destination channel")
        self._push("onChannel", {
            "channel_id": channel_id,
            "channel_title": channel_title,
            # Rendered here, not in the page: format_destination states the
            # "learned from the first upload" case in words, and that
            # explanation is copy with its own test, not a template.
            "destination": copy_mod.format_destination(
                channel_title, self._state.settings.get("privacy", "")),
        })
        # The Settings account line names the channel, and this is the
        # moment the channel becomes known. Without this it would read a
        # bare "Connected" for the rest of the session that learned it, and
        # only come good on the next launch. Safe to assert "connected"
        # here: we are on the success path of an upload that just
        # authenticated.
        self._push_auth("connected")

    def retry(self) -> None:
        state = self._retry_state
        if state is None:
            return
        # Disabled immediately, not by the worker: the click that got here
        # must not be repeatable while the resume is being set up.
        self._push("onRetryAvailable", {"available": False})
        self._upload_thread = threading.Thread(
            target=self._retry_worker, args=(state,), daemon=True)
        self._upload_thread.start()

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
                self._push("onProgress", {
                    "mode": "determinate", "pct": self._last_pct,
                    "text": copy_mod.format_progress(state.resume_index, total,
                                                     fraction),
                    "kind": "FG"})

            vid = uploader.upload(state.request, on_progress=on_progress)
            self._link(state.job.ids[state.resume_index], vid)
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
                state, request=exc.request if retryable else None)
            self._push("onStatus", {"text": str(exc), "kind": "ERROR"})
            if retryable:
                self._push("onRetryAvailable", {"available": True})
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            self._upload_worker(replace(state.job,
                                        start_index=state.resume_index + 1))
        else:
            self._upload_done(state.job)

    # ----- combat logs --------------------------------------------------------

    def _skip_logs(self, reason: str) -> None:
        """Report a log half that could not run, without unwinning the video.

        A status line rather than a dialog, and deliberately not an ERROR:
        the upload the user asked for DID happen, and a modal apologising
        for the half that did not would read as though the whole thing had
        failed. It replaces "Upload complete!" on the strip rather than
        following it, so the last thing said never overstates what was done.
        """
        self._push("onStatus", {
            "text": f"Upload complete — combat logs skipped: {reason}",
            "kind": "WARNING"})

    def _post_combat_logs(self, job: UploadJob) -> None:
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
        cfg = self._state.settings
        hook, error = discord.parse_webhook(cfg.get("discord_webhook"))
        if hook is None:
            self._skip_logs(f"{error} Set it up in Settings.")
            return

        gamelogs = cfg.get("gamelogs_dir")
        gamelogs_dir = Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()
        if gamelogs_dir is None or not gamelogs_dir.is_dir():
            self._skip_logs("your EVE Gamelogs folder was not found. "
                            "Set it in Settings.")
            return

        # Resolve any still-pending probe for THIS selection first: an
        # unprobed recording also leaves duration None, and refusing on that
        # would blame ffprobe for a probe that simply had not reached these
        # files yet.
        pairs = list(zip(job.ids, job.items))
        self._probe_now(pairs)
        missing = [i.path.name for _, i in pairs if i.duration is None]
        if missing:
            self._skip_logs(
                "no readable duration for " + ", ".join(missing)
                + ", so the time window cannot be worked out (this usually "
                  "means ffprobe is unavailable).")
            return

        # Union across the selection: earliest start to latest end, one
        # archive, matching how stitching treats a multi-selection.
        infos = [i for _, i in pairs]
        start_utc = min(
            datetime.datetime.fromtimestamp(i.mtime - i.duration,
                                            datetime.timezone.utc)
            for i in infos)
        end_utc = max(
            datetime.datetime.fromtimestamp(i.mtime, datetime.timezone.utc)
            for i in infos)

        self._combat_log_worker(hook, gamelogs_dir, start_utc, end_utc)

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
            self._push("onStatus", {
                "text": f"Reading recording lengths… ({index}/{total})",
                "kind": "FG"})
            duration, definitive = library.probe(info.path, self._state.ffprobe_bin)
            if definitive:
                durations.remember(self._cache, info.path, info.size,
                                   info.mtime, duration)
                measured += 1
            self._rows.set_duration(row_id, duration, definitive)
            self._push("onDuration", {"id": row_id, "duration": duration,
                                      "definitive": definitive})
        if measured:
            durations.save(self._durations_file, self._cache)

    def _combat_log_worker(self, hook, gamelogs_dir, start_utc, end_utc) -> None:
        """Collect, zip, and post the logs. Runs on the upload thread.

        No longer a thread target of its own: it is the tail of the upload
        the user confirmed, which is what keeps one busy guard covering both
        halves.
        """
        archive = None
        try:
            self._push("onStatus", {"text": "Collecting combat logs…", "kind": "FG"})
            selection = combatlog.select_logs(gamelogs_dir, start_utc, end_utc)
            if not selection.logs:
                self._alert("info", "No logs found", (
                    "No EVE logs overlap that window.\n\n"
                    f"Window (UTC): {start_utc:%Y-%m-%d %H:%M} to {end_utc:%H:%M}\n"
                    f"Folder: {gamelogs_dir}\n\n"
                    "EVE writes log timestamps in UTC, so this window is in "
                    "UTC too."))
                self._push("onStatus", {"text": "No combat logs found.",
                                        "kind": "FG"})
                return

            stamp = start_utc.strftime("%Y-%m-%d_%H-%M")
            out = paths.tmp_dir() / f"combatlogs-{stamp}.zip"
            self._push("onStatus", {"text": "Building archive…", "kind": "FG"})
            archive = combatlog.build_archive(selection, out, start_utc, end_utc)

            content = combatlog.summarize_archive(archive, start_utc, end_utc)
            self._push("onStatus", {"text": "Posting to Discord…", "kind": "FG"})
            result = discord.post_archive(hook, archive.path, content)

            if result.ok:
                # Only remove the archive once Discord has it.
                try:
                    archive.path.unlink()
                except OSError:
                    pass
                # Discord's own message does not mention the cap; append the
                # same drop note so the status line does not quietly
                # disagree with the content the user just sent.
                status_text = result.message
                note = combatlog.dropped_note(archive.dropped)
                if note:
                    status_text += f" ({note})"
                self._push("onStatus", {"text": status_text, "kind": "SUCCESS"})
            else:
                # Keep the archive: the window is fixed by the recording and
                # there is no UI for selecting fewer logs, so a user told
                # "too large" has no move available unless the file survives.
                self._alert("error", "Combat log upload failed", (
                    f"{result.message}\n\nThe archive was kept so you can "
                    f"upload it by hand:\n{archive.path}"))
                self._push("onStatus", {"text": result.message, "kind": "ERROR"})
        except Exception as exc:
            # post_archive never raises, but build_archive and
            # summarize_archive can -- and by then the archive may already be
            # on disk. Without this the user gets a bare str(exc) and the
            # "kept so you can upload it by hand" promise, which the failed
            # -post branch above makes, quietly does not hold on this path.
            detail = str(exc)
            if archive is not None and archive.path.exists():
                detail += ("\n\nThe archive was kept so you can upload it "
                           f"by hand:\n{archive.path}")
            self._alert("error", "Combat log upload failed", detail)
            self._push("onStatus", {"text": f"Error: {exc}", "kind": "ERROR"})

    # ----- settings and account ------------------------------------------

    def _settings_payload(self) -> dict:
        cfg = self._state.settings
        detected_rec = obsconfig.find_recording_dir()
        detected_logs = combatlog.find_gamelogs_dir()
        return {
            "settings": dict(cfg),
            # Top level, not inside `settings`: it is derived, not stored,
            # and nesting it invites the page to write it back on Save.
            "webhook_status": copy_mod.webhook_status(
                cfg.get("discord_webhook", "") or ""),
            "detected": {
                "recording": str(detected_rec) if detected_rec else "",
                "gamelogs": str(detected_logs) if detected_logs else "",
            },
            # Depends only on values Python owns (channel title and
            # privacy), so it is rendered here rather than templated in the
            # page -- format_destination is tested copy.
            "destination": copy_mod.format_destination(
                cfg.get("channel_title", ""), cfg.get("privacy", "")),
        }

    def get_settings(self) -> dict:
        """The settings payload, on request. The page asks; Python does not
        volunteer it at boot.

        This exists because nothing else could carry it safely. `list_rows`
        fires on every watcher tick, and pushing the whole settings dict
        from there would throw away every unsaved edit in an open Settings
        form -- the same reason `detect_folder` returns rather than pushes.
        A timer-deferred push at startup would be a guess at when the page
        is listening. So it is a read, matching what app.js already does
        for `list_rows` and settings.js for `auth_labels`.

        Returns the same shape `save_settings` pushes, so the page has one
        renderer for both.
        """
        return self._settings_payload()

    def save_settings(self, values: dict) -> bool:
        """Validate, persist, and make the change reach the running app.

        Returns False when the page should keep the form open with the
        user's edits intact.
        """
        category = str(values.get("category", "")).strip()
        if not category.isdigit():
            self._alert("warning", "Invalid category",
                        "Category ID must be a number, e.g. 20.")
            return False
        webhook_raw = str(values.get("discord_webhook", "") or "").strip()
        if webhook_raw:
            _, webhook_error = discord.parse_webhook(webhook_raw)
            if webhook_error:
                self._alert("warning", "Invalid webhook", webhook_error)
                return False
        rec_dir = Path(str(values.get("recording_dir", "")))
        if not rec_dir.is_dir():
            self._alert("warning", "Invalid folder", f"{rec_dir} is not a folder.")
            return False

        cfg = dict(self._state.settings)
        gamelogs = str(values.get("gamelogs_dir") or "").strip()
        cfg.update({
            "privacy": values.get("privacy"),
            "category": category,
            "notify_mode": values.get("notify_mode"),
            "recording_dir": str(rec_dir),
            "discord_webhook": webhook_raw,
            "gamelogs_dir": gamelogs or None,
        })
        try:
            settings_mod.save(cfg)
        except OSError as exc:
            # Bail out before touching in-memory state so state and disk
            # never diverge, and say so rather than failing silently -- the
            # page keeps the form open with the edits intact.
            self._alert("error", "Could not save settings",
                        f"Settings were not saved: {exc}")
            return False

        self._state.settings = settings_mod.load()
        self._state.recording_dir = rec_dir
        # The watcher is the reason this method is not just a file write.
        # It holds its own directory, so persisting the setting alone would
        # leave it polling the old folder forever. Guarded on a real change
        # because rebind() re-baselines `seen`.
        if self._watcher is not None and rec_dir != Path(self._watcher.directory):
            self._watcher.rebind(rec_dir)
        self._push("onSettings", self._settings_payload())
        self.list_rows()
        return True

    def pick_folder(self, which: str) -> str:
        """Native folder picker, seeded with what is configured now."""
        if which == "gamelogs":
            start = str(self._state.settings.get("gamelogs_dir") or "")
        else:
            # recording_dir is None on the first-run route by design, and
            # str(None) would hand create_file_dialog the literal "None".
            # pywebview happens to discard a path that does not exist, but
            # that is its implementation detail, not our intent.
            start = str(self._state.recording_dir or "")
        chosen = self._window.create_file_dialog(_folder_dialog_kind(),
                                                 directory=start)
        # create_file_dialog returns a sequence of paths, or None on cancel.
        if not chosen:
            return ""
        return str(chosen[0])

    def detect_folder(self, which: str, current: str = "") -> str:
        """Re-run detection for one folder and hand back the suggestion.

        Returned rather than pushed through onSettings, and Save is still
        required: the user sees exactly what changed and can decline it,
        and pushing the whole settings dict would throw away every other
        unsaved edit in the form.

        `current` is the field's live value, not the stored setting, so a
        detection that agrees with what the user has already typed is
        reported as agreement instead of silently rewriting the field.
        """
        if which == "gamelogs":
            found = combatlog.find_gamelogs_dir()
            if found is None:
                self._alert("info", "Gamelogs not found",
                            "Could not find an EVE Gamelogs folder under "
                            "Documents or OneDrive\\Documents. Use Browse… "
                            "to point at it.")
                return ""
            if str(found) == current:
                self._alert("info", "Gamelogs",
                            f"Already set to the detected folder:\n{found}")
                return ""
            return str(found)

        detected = obsconfig.find_recording_dir()
        if detected is None or not detected.is_dir():
            self._alert("info", "Detect recording folder",
                        "Could not read OBS's configuration to detect a "
                        "recording folder. Make sure OBS is installed and has "
                        "recorded at least once, then try again.")
            return ""
        if str(detected) == current:
            self._alert("info", "Detect recording folder",
                        f"Already set to the detected folder:\n{detected}")
            return ""
        return str(detected)

    def set_recording_dir(self, path: str) -> bool:
        """Accept the first-run folder choice: persist it and start watching.

        Returns False when the folder is unusable, so the page keeps the
        first-run screen up rather than dropping the user into an empty
        list with no explanation of why.

        _on_recording_dir_ready is assigned by __main__ and is what actually
        creates the Watcher and starts the poll loop; the bridge does not
        own either.
        """
        folder = Path(str(path or "").strip())
        if not folder.is_dir():
            self._alert("warning", "Invalid folder",
                        f"{folder} is not a folder.")
            return False
        # Save from a COPY and adopt only on success, exactly as
        # save_settings does. Mutating first and returning False on OSError
        # would leave the app believing it has a recording folder it never
        # persisted -- state and disk diverged, and the divergence survives
        # until the next launch reads the file back.
        cfg = dict(self._state.settings)
        cfg["recording_dir"] = str(folder)
        try:
            settings_mod.save(cfg)
        except OSError as exc:
            self._alert("error", "Could not save settings",
                        f"Settings were not saved: {exc}")
            return False
        self._state.settings = settings_mod.load()
        self._state.recording_dir = folder
        if self._on_recording_dir_ready is not None:
            self._on_recording_dir_ready(folder)
        self.list_rows()
        return True

    def auth_labels(self) -> dict:
        """The whole account-state table, for the page to render from.

        Returned rather than pushed because it never changes: the page asks
        once at load and then only needs the `state` each onAuthState
        carries. Keeping the strings here keeps them under test, and stops
        the page growing a second copy that drifts.
        """
        return {state: {"message": message, "label": label, "enabled": enabled}
                for state, (message, label, enabled)
                in copy_mod.AUTH_STATES.items()}

    def _push_eve_status(self) -> None:
        """Publish engine status to the page.

        Pushed regardless of which route is showing: the status bar is
        global chrome, and app.js deliberately never tells Python which
        route is active.
        """
        engine = self._state.engine
        if engine is None:
            return
        enabled = self._state.settings["eve_bookmarks"]["enabled"]
        status = engine.status(enabled=enabled)
        self._push("onEveStatus", {
            "state": status.state, "sig": status.sig, "root": status.root,
            "next_num": status.next_num, "next_alpha": status.next_alpha,
            "root_mode": status.root_mode,
            "failed_binds": status.failed_binds,
            # A failed start is otherwise invisible: this is the one
            # actionable thing the user can be told ("the engine is
            # missing, reinstall").
            "last_error": status.last_error,
        })

    # ---- EVE client previews ------------------------------------------

    def start_previews_if_enabled(self) -> None:
        """Start the preview thread only if the user asked for it.

        Called on launch. Lazy on purpose: enabling costs a thread, a
        700ms discovery sweep and a foreground hook, and a user who never
        previews EVE clients should pay none of it.
        """
        if self._preview_host is None:
            return
        if self._state.settings.get("preview", {}).get("enabled"):
            self._preview_host.start()

    def set_preview_enabled(self, enabled: bool) -> None:
        """Toggle previews and persist the choice.

        start() and stop() are both idempotent, so a double-click on the
        checkbox cannot orphan a second pump owning HWNDs that nothing
        will tear down.
        """
        enabled = bool(enabled)
        section = self._state.settings.setdefault("preview", {})
        if section.get("enabled") == enabled:
            # A no-op toggle rewrites the whole settings document for
            # nothing (settings.save projects every key), and the page can
            # emit one on re-render. PreviewHost.start/stop are idempotent
            # too, so this is belt and braces -- but the redundant write is
            # real.
            #
            # True, not None: this is a SUCCESS path. Returning None here
            # gave it exactly the failure the truthy return below exists to
            # prevent -- WM.send resolves to null on a bridge error, so the
            # page would read a no-op toggle as a failed call and revert
            # the checkbox.
            return True
        section["enabled"] = enabled
        try:
            settings_mod.save(self._state.settings)
        except OSError:
            # Same posture as the channel persist above: a settings file
            # that cannot be written must not block the feature itself.
            logger.exception("Could not persist the preview setting")
        if self._preview_host is not None:
            if enabled:
                self._preview_host.start()
            else:
                self._preview_host.stop()
        # Truthy on success: WM.send resolves to null on a bridge failure
        # and cannot otherwise distinguish that from a method that simply
        # returned None (settings.js:181 documents the same trap).
        return True

    def shutdown_previews(self) -> None:
        """Tear the preview thread down on the way out.

        Runs on every exit path, so like shutdown_engine() it must never
        be the thing that raises. A stop() that does not happen leaves a
        thread owning HWNDs and Wingman lingering in Task Manager after
        it has left the tray.
        """
        if self._preview_host is None:
            return
        try:
            self._preview_host.stop()
        except Exception:
            logger.exception("Preview host did not stop cleanly")

    # ---- EVE client window layouts -------------------------------------

    def start_client_layouts_if_enabled(self) -> None:
        """Arm the restore-on-appear watcher, if the user asked for it."""
        if self._client_layouts is None:
            return
        if self._state.settings.get("preview", {}).get(
                "restore_clients_on_launch"):
            self._client_layouts.start()

    def save_client_layout(self) -> dict:
        """Snapshot where every named client sits."""
        if self._client_layouts is None:
            return {"saved": 0, "persisted": True}
        return self._client_layouts.save_now()

    def restore_client_layout(self) -> dict:
        if self._client_layouts is None:
            return {"restored": 0, "skipped": 0}
        return self._client_layouts.restore_now()

    def set_restore_clients_on_launch(self, enabled) -> bool:
        """Toggle the watcher and persist the choice.

        Truthy on success for the reason settings.js:181 documents:
        WM.send resolves to null on a bridge failure and cannot otherwise
        tell that apart from a method that returned None.
        """
        enabled = bool(enabled)
        section = self._state.settings.setdefault("preview", {})
        if section.get("restore_clients_on_launch") != enabled:
            def mutate(doc):
                doc.setdefault("preview", {})[
                    "restore_clients_on_launch"] = enabled
            try:
                # Through settings.update, not save(): the read must
                # happen inside _SAVE_LOCK or a concurrent writer is
                # reverted. update applies mutate before writing, so the
                # in-memory document is updated even when the disk write
                # fails -- same as the previous behaviour.
                settings_mod.update(lambda: self._state.settings, mutate)
            except OSError:
                # Same posture as set_preview_enabled: a settings file
                # that cannot be written must not block the feature.
                logger.exception(
                    "Could not persist the client-restore setting")
        if self._client_layouts is not None:
            if enabled:
                self._client_layouts.start()
            else:
                self._client_layouts.stop()
        return True

    def shutdown_client_layouts(self) -> None:
        """Runs on every exit path, so like shutdown_previews it must
        never be the thing that raises."""
        if self._client_layouts is None:
            return
        try:
            self._client_layouts.stop()
        except Exception:
            logger.exception("Client layout watcher did not stop cleanly")

    def _push_first_run_when_ready(self) -> None:
        """Tell the page to show its first-run route, once it can hear it.

        Deferred onto a short timer rather than pushed immediately: this is
        called before webview.start(), so app.js has not registered its
        handlers and _push would log the message and drop it. The page asks
        for state on load, but there is no state to ask for here -- an
        unconfigured folder is exactly the case list_rows() returns silently
        on -- so this is the one thing Python must volunteer.
        """
        timer = self._timer(FIRST_RUN_PUSH_S, lambda: self._push("onFirstRun", {}))
        timer.daemon = True
        timer.start()

    def _push_auth(self, state: str, message: str | None = None) -> None:
        # Read live from settings rather than snapshotted: the channel is
        # learned from the first upload response, so a title captured at
        # construction would be empty for the whole of the session that
        # actually learned it.
        if message is None:
            message = copy_mod.account_line(
                state, self._state.settings.get("channel_title", "") or "")
        self._push("onAuthState", {"state": state, "message": message})

    def _auth_busy(self) -> bool:
        return self._auth_thread is not None and self._auth_thread.is_alive()

    def refresh_auth(self) -> None:
        """Resolve the stored credentials without blocking the bridge.

        load_credentials lazily imports google.oauth2, which drags in
        google.auth, requests and cryptography. Off a PyInstaller build's
        disk that is a visible pause, so it runs on a worker and the page
        holds the transient state until the answer lands. There is no
        polling loop: the worker pushes the result itself.
        """
        if self._auth_busy():
            return
        self._push_auth("connecting", "Checking…")
        self._auth_thread = threading.Thread(target=self._auth_check_worker,
                                             daemon=True)
        self._auth_thread.start()

    def _auth_check_worker(self) -> None:
        try:
            creds = uploader.load_credentials(paths.token_file())
            connected = creds is not None and not uploader.needs_reauth(creds)
        except Exception:
            # An unreadable token is indistinguishable from not being
            # connected, and leaving the control mid-check forever is the
            # one outcome that helps nobody.
            connected = False
        self._push_auth("connected" if connected else "disconnected")

    def connect_google(self) -> None:
        """Run OAuth off the bridge thread; it blocks on a browser round-trip.

        The guard is here as well as in the page's disabled button: two
        concurrent flows would fight over the loopback redirect port.
        """
        if self._auth_busy():
            return
        self._push_auth("connecting")
        self._auth_thread = threading.Thread(target=self._auth_worker, daemon=True)
        self._auth_thread.start()

    def _auth_worker(self) -> None:
        try:
            creds = uploader.run_oauth_flow()
            uploader.save_credentials(creds, paths.token_file())
        except Exception as exc:
            self._alert("error", "Connection failed", str(exc))
            self._push_auth("disconnected")
            return
        self._push_auth("connected")

    # ---- EVE bookmarks ------------------------------------------------

    def get_bookmarks(self) -> dict:
        """Everything the Bookmarks route renders, in one call."""
        section = self._state.settings["eve_bookmarks"]
        engine = self._state.engine
        status = (engine.status(enabled=section["enabled"])
                  if engine is not None else None)
        return {
            "settings": section,
            "labels": bookmarks.BIND_LABELS,
            "order": list(bookmarks.BIND_IDS),
            "windows": evewindows.list_eve_windows(),
            "collisions": bookmarks.collisions(section["keybinds"]),
            # Human labels for the bound keys. Computed here rather than in
            # the page, which is the entire reason to_ahk returns a display
            # string: the page holds no mapping table and cannot drift from
            # this one. Without this the UI would show raw "^+s".
            "displays": {bid: bookmarks.parse_ahk(value)["display"]
                         for bid, value in section["keybinds"].items()
                         if value},
            "engine": {
                "state": status.state if status else "off",
                "root_mode": status.root_mode if status else "",
                # Surfaces a failed start straight away. Without this the
                # toggle reads "on" while nothing is running, and the reason
                # never reaches the user at all.
                "last_error": status.last_error if status else None,
            },
        }

    def save_bookmarks(self, section) -> dict:
        """Persist the section, regenerate the INI, and match the engine to
        the enabled flag.

        The payload arrives from the page and lands in a file that registers
        keyboard hooks, so it is re-validated here rather than trusted.

        The returned payload carries a `saved` flag. Both failure paths
        below return the same shape as success, so without it a caller
        cannot tell a completed write from a refused one -- which is how
        import came to report "Import complete" over a settings file it had
        failed to write. The page ignores the key; only callers that make a
        success claim of their own need it.
        """
        if not isinstance(section, dict):
            logger.error("Refusing a non-dict bookmarks payload")
            return {**self.get_bookmarks(), "saved": False}

        merged = dict(self._state.settings)
        merged["eve_bookmarks"] = settings_mod.validated_eve(section)
        try:
            settings_mod.save(merged)
        except OSError as exc:
            # Same contract as save_settings: bail before touching in-memory
            # state so state and disk never diverge, and say why rather than
            # letting the exception escape.
            self._alert("error", "Could not save settings",
                        f"Bookmark settings were not saved: {exc}")
            return {**self.get_bookmarks(), "saved": False}

        self._state.settings = settings_mod.load()
        clean = self._state.settings["eve_bookmarks"]

        engine = self._state.engine
        if engine is not None:
            engine.apply(clean)
            if clean["enabled"] and not engine.is_running():
                engine.start()
                engine.sync_sequence()
            elif not clean["enabled"] and engine.is_running():
                engine.stop()
        return {**self.get_bookmarks(), "saved": True}

    def capture_bind(self, parts) -> dict:
        return bookmarks.to_ahk(parts if isinstance(parts, dict) else {})

    def reset_binds(self) -> dict:
        """Apply the recommended set, overwriting every bind.

        The standalone GUI's Reset Defaults button (111unified.ahk:319),
        which the port dropped. Overwrite rather than fill-blanks: a reset
        whose effect depends on hidden state is not a reset, and the user
        reaches this through a confirmation in the page.
        """
        section = dict(self._state.settings["eve_bookmarks"])
        section["keybinds"] = dict(bookmarks.RECOMMENDED_BINDS)
        return self.save_bookmarks(section)

    def parse_bind(self, text) -> dict:
        return bookmarks.parse_ahk(text if isinstance(text, str) else "")

    def eve_command(self, name, argument="") -> bool:
        engine = self._state.engine
        if engine is None:
            return False
        return bool(engine.send_command(str(name), str(argument or "")))

    def import_bookmarks(self) -> dict:
        """Import a standalone helper INI chosen by the user.

        The standalone script wrote its INI relative to its working
        directory, so there is no path worth probing -- the user points at
        it.
        """
        chosen = self._window.create_file_dialog(
            _open_file_dialog_kind(), directory="")
        if not chosen:
            return {"ok": False, "discarded": [], "notes": []}
        try:
            # Read as BYTES and sniff the BOM. AutoHotkey's IniWrite emits
            # UTF-16 LE on a Unicode build, which is what the real file in
            # the wild actually is; decoding that as UTF-8 leaves a NUL
            # after every character, so every section header failed the
            # parser's "]" test and the whole file imported as nothing --
            # which was then saved over the user's real settings while the
            # dialog reported success.
            raw = Path(chosen[0]).read_bytes()
        except OSError as exc:
            return {"ok": False, "discarded": [],
                    "notes": [f"Could not read that file: {exc}"]}

        result = bookmarks.import_legacy_ini(bookmarks.decode_ini_bytes(raw))
        if not result["parsed"]:
            # No sections at all. Indistinguishable from an empty config by
            # content, so it is treated as the failure it almost certainly
            # is: saving here would wipe the settings the import exists to
            # preserve.
            return {"ok": False, "discarded": [], "notes": [
                "That file does not look like a bookmark helper INI - no "
                "settings were found in it, so nothing was changed."]}
        # Import never enables the engine: reading someone's old settings is
        # not consent to start a keyboard hook.
        result["section"]["enabled"] = \
            self._state.settings["eve_bookmarks"]["enabled"]
        if not self.save_bookmarks(result["section"])["saved"]:
            # Deliberately no note: save_bookmarks has already raised its own
            # "Could not save settings" dialog naming the reason, and the
            # page only alerts on a failure that carries one. Returning a
            # second message here would put two dialogs on screen for one
            # failure -- and returning ok=True would put a contradictory
            # "Import complete" beside the error, which is the bug this
            # flag exists to close.
            return {"ok": False, "discarded": [], "notes": []}
        return {"ok": True, "discarded": result["discarded"],
                "notes": result["notes"]}

    def alert_import(self, body: str) -> None:
        """Report what an import changed. Uses the existing dialog layer."""
        self._alert("info", "Import complete", str(body))

    def alert_bookmarks(self, body: str) -> None:
        """Generic Bookmarks-route alert for anything that is not an import
        summary -- a rejected typed hotkey, a refused engine command, or a
        failed import's reason. `alert_import` keeps its own "Import
        complete" title for a completed (if partial) import; that title
        would be misleading for these.
        """
        self._alert("info", "Bookmarks", str(body))
