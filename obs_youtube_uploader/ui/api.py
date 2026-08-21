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
import json
import logging
import queue
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .. import durations, library, paths
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


class Api:
    """JS-callable methods only. Every other attribute underscore-prefixed."""

    def __init__(self, state: AppState, *,
                 id_factory=lambda: uuid.uuid4().hex,
                 rows=None, durations_file=None,
                 drain_interval_s=PROBE_DRAIN_S,
                 spawn=threading.Thread, probe=library.probe,
                 timer=threading.Timer):
        self._state = state
        self._window = None          # assigned by ui.window.create()
        # Injectable purely to make ids predictable in a test that needs to
        # assert on one; production never overrides it.
        self._id_factory = id_factory
        self._dialog_lock = threading.Lock()
        # request id -> [Event, answer]. An entry exists only while a worker
        # is parked on it.
        self._dialogs: dict[str, list] = {}

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
        # After the resolve, not after the rebuild: resolve() fills cache
        # hits into the very VideoInfo objects the snapshot renders from, so
        # rows() now reports them and the page never flashes "…" on a
        # duration that was already known.
        self._push("onRows", {"rows": self._rows.rows()})

        # Identity, not equality: VideoInfo is a plain dataclass, so two
        # recordings with the same size and mtime compare equal and an `in`
        # test over the pending list would probe the wrong row.
        outstanding = {id(info) for info in pending}
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
