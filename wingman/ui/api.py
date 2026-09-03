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

import contextlib
import copy
import datetime
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path

from .. import __version__ as _version
from .. import (
    autostart,
    bookmarks,
    combatlog,
    discord,
    durations,
    evewindows,
    fightrecorder,
    library,
    links,
    obsconfig,
    paths,
    stitch,
    uploader,
)
from .. import settings as settings_mod
from .. import updates as updates_mod
from ..alerts import patterns as alert_patterns
from ..alerts import service as alert_service
from ..evesettings import backup as evesettings_backup
from ..evesettings import characters as evesettings_characters
from ..evesettings import codec as evesettings_codec
from ..evesettings import formations as evesettings_formations
from ..evesettings import identity as evesettings_identity
from ..evesettings import names as evesettings_names
from ..evesettings import ops as evesettings_ops
from ..evesettings import profilecopy as evesettings_profilecopy
from ..evesettings import selective as evesettings_selective
from ..evesettings import tree as evesettings_tree
from ..preview import geometry as preview_geometry
from ..preview import gestures as preview_gestures
from ..preview import host as preview_host_mod
from ..preview import layout as preview_layout
from ..preview import window as preview_window
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

# The EVE Settings workers hold the mutation lock across their
# confirmation prompt (by design -- a queued operation would describe state
# that has since changed), so their wait needs a floor under it. Generous
# for a human answering a dialog; the case it bounds is a push that never
# reached the page, which _push swallows silently.
EVE_CONFIRM_TIMEOUT_S = 300.0

# Much shorter than EVE_CONFIRM_TIMEOUT_S, and for the opposite reason. That
# one bounds a worker holding a lock; this one bounds the PYSTRAY thread,
# which services the whole tray menu -- so a page that never answers takes
# the tray with it until this expires. Long enough to read two sentences
# and click, short enough that a wedged page does not make Quit look broken.
QUIT_CONFIRM_TIMEOUT_S = 60.0

# set_alert_event's writable fields. Kept as a set to check against rather
# than duplicated per-field range checks -- settings.validated_alerts owns
# the ranges (cooldown_s/pulses clamping, color/sound/flash_rate
# validation) and this is the only other place event shape is named.
#
# No `duration_ms`: it is derived from pulses x flash_rate at the one site
# that arms a ring (preview/window.py), so there is nothing here to write.
_ALERT_EVENT_FIELDS = frozenset(
    {"enabled", "cooldown_s", "pulses", "flash_rate", "color", "sound"}
)


def _folder_dialog_kind():
    """pywebview's folder-dialog constant, imported at call time.

    Kept behind a function for two reasons: webview is not installed on the
    Linux box these tests run on, and 6.x renamed this constant once
    already (FOLDER_DIALOG -> FileDialog.FOLDER), so exactly one line has
    to change if it moves again.
    """
    import webview

    return webview.FileDialog.FOLDER


def _eve_same_path(candidate: Path | None, requested) -> bool:
    """Whether *candidate* IS the path the caller named, not a fallback
    discover() supplied for it.

    discover() falls back to the first server/profile it finds when a
    requested token matches nothing on disk, so comparing the requested
    token against the RESULT can't tell a genuine selection from a
    fabricated one that happened to land on the default. Two-way
    containment (rather than a lexical `==`) is what tree.py's own
    equality-through-is_under idiom uses, and it is what makes this call
    resilient to a trailing separator or an unresolved symlink either
    side names the same directory with.
    """
    if candidate is None:
        return False
    return evesettings_tree.is_under(
        candidate, requested
    ) and evesettings_tree.is_under(requested, candidate)


def _open_file_dialog_kind():
    """pywebview's open-file-dialog constant, imported at call time.

    Same seam as _folder_dialog_kind above, for the same two reasons: the
    tests run on a box with no webview installed, and the constant has
    moved once already. Importing webview inline at the call site instead
    is what broke the import tests -- there was no seam left to patch.
    """
    import webview

    return webview.FileDialog.OPEN


def _with_fetch_labels(payload: dict) -> dict:
    """Add a rendered `fetched_label` beside each character's fetched_utc.

    Skills 8: the Skills route rendered its fetch time with the page's own
    toLocaleString ("8/25/2026, 12:12:28 AM") while the Uploader rendered
    the same class of fact as "5h ago". Two time vocabularies in one app,
    and the Skills one carried seconds precision on a value where seconds
    cannot matter.

    Added HERE rather than in eveskills.controller, which builds the
    payload: controller.py is the only writer of the skills state document
    and this is presentation, not state. The label is derived on every read
    and never persisted -- a stored one would be wrong within the hour,
    which is exactly the property that makes a relative time useful.

    `fetched_utc` stays untouched beside it. skills.js reads the raw value
    for its own staleness logic, so removing it would break the freshness
    badge; this only gives the page a string it no longer has to invent.

    Copied shallowly per character so the controller's own dicts are not
    mutated -- state_payload may hand back structures the document still
    references, and a presentation key written into those would be one
    save away from being persisted after all.
    """
    characters = payload.get("characters")
    if not isinstance(characters, list):
        return payload
    out = dict(payload)
    out["characters"] = [
        {**ch, "fetched_label": copy_mod.format_fetched(ch.get("fetched_utc", ""))}
        if isinstance(ch, dict)
        else ch
        for ch in characters
    ]
    return out


def _empty_skills_state() -> dict:
    """The state payload when there is no controller at all.

    Same keys as the real one so skills.js has exactly one renderer. A
    payload that drops fields when the subsystem is absent means every
    access in the page needs a guard, and the one that gets forgotten
    throws inside a click handler with no console attached.
    """
    return {
        "auth_configured": False,
        "auth_in_progress": False,
        "refresh_in_flight": False,
        "selected_plan_name": "",
        "selected_group": "",
        "groups": [],
        "plans": [],
        "characters": [],
        "plan_issues": [],
        "warnings": ["The EVE skills subsystem is unavailable."],
        "plans_updated_utc": "",
    }


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


def _folder_note(folder: Path, suppressed: int) -> str:
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
class _EveContext:
    """The Profiles selection a resolver pass may speak for.

    Canonical paths -- realpath plus platform case folding, the same
    identity rule evesettings.tree containment uses -- because a pass that
    started on one selection must not clean or repaint another that merely
    spells its folder differently.

    `datasource` is ESI's, and it is empty for anything but a server this
    process could positively identify as Tranquility. Empty therefore means
    "no authoritative status source": no deletion verdict may be recorded
    against it, none may be read for it, and no account identity metadata
    -- which this product interprets as Tranquility's -- may be applied.
    """

    root: str = ""
    server: str = ""
    profile: str = ""
    datasource: str = ""

    @property
    def trusted(self) -> bool:
        return bool(self.datasource)


# What a context had already published: (id, name) pairs and deleted ids.
_EVE_NO_FACTS: tuple[frozenset, frozenset] = (frozenset(), frozenset())


@dataclass(frozen=True)
class _EveCandidate:
    """One offered account/character pair, and what authorized it.

    `generation` is the identification generation the observation behind
    this offer was made under. It travels WITH the pair rather than beside
    it so a publication cannot half-happen: an offer that outlives its
    generation -- cancelled, superseded, or invalidated by a learned
    deletion -- is recognizable as stale by the value it carries, both here
    and on the page one round trip later.
    """

    generation: int
    account_id: str
    character_ids: tuple[str, ...]


# Saved account names and links carry no datasource, so this product reads
# them as Tranquility's. Elsewhere they are not applied and not editable --
# a migration would be disproportionate for a feature used off Tranquility
# about never, and a Tranquility verdict must not rewrite another shard.
_EVE_IDENTITY_UNAVAILABLE = (
    "Account identity is available only for Tranquility profiles."
)
_EVE_CHARACTER_DELETED = "That character no longer exists."
_EVE_CLEANUP_FAILED = "Could not remove deleted character links."


@dataclass
class AppState:
    """Everything the bridge needs that is not the page.

    recording_dir is None until first run completes. Every consumer must
    handle that rather than substituting a default: a fallback to the home
    directory would have list_rows() scan it for recordings.

    `settings` is MUTATED IN PLACE, never rebound. It used to be replaced
    wholesale on every write, which meant anything holding the original
    dict went stale -- preview/store.py's LayoutStore captures exactly such
    a reference and writes through it later, and a write it made against
    the orphaned object was then overwritten by the next save. Every writer
    now goes through settings.update, which normalises in place under the
    save lock. Do not reintroduce an assignment to this attribute.
    """

    recording_dir: Path | None
    settings: dict
    ffmpeg_bin: str | None = None
    ffprobe_bin: str | None = None
    # None until ui.window.create() wires up the HotkeyEngine. Every bridge
    # method that touches it must handle that -- e.g. by no-op'ing rather
    # than crashing the bridge thread on an AttributeError.
    engine: object | None = None


@dataclass(frozen=True)
class _ClaimResult:
    """One locked claim decision, including why a caller was refused."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


class _WorkGate:
    """Atomically arbitrate uploads, updater handoff, and process shutdown.

    The lock protects state transitions only. Prompts, page pushes, I/O, worker
    creation, and shutdown all happen after it has been released so no external
    operation can park every claimant behind it.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._upload = False
        self._handoff = ""
        self._quitting = False

    def claim_upload(self) -> _ClaimResult:
        with self._lock:
            if self._handoff:
                return _ClaimResult(False, "handoff")
            if self._quitting:
                return _ClaimResult(False, "quitting")
            if self._upload:
                return _ClaimResult(False, "upload")
            self._upload = True
            return _ClaimResult(True)

    def upload_claimed(self) -> bool:
        with self._lock:
            return self._upload

    def release_upload(self) -> None:
        with self._lock:
            self._upload = False

    def claim_handoff(self, phase: str) -> _ClaimResult:
        with self._lock:
            if self._upload:
                return _ClaimResult(False, "upload")
            if self._quitting:
                return _ClaimResult(False, "quitting")
            # The updater's own runtime lock excludes a second installer.
            # Reusing this transition lets that owner advance the phase
            # without releasing the claim between revalidation and launch.
            self._handoff = phase
            return _ClaimResult(True)

    def release_handoff(self) -> None:
        with self._lock:
            self._handoff = ""

    def handoff_phase(self) -> str:
        with self._lock:
            return self._handoff

    def claim_quit(self, *, force_upload: bool) -> _ClaimResult:
        with self._lock:
            if self._handoff:
                return _ClaimResult(False, "handoff")
            if self._quitting:
                return _ClaimResult(False, "quitting")
            if self._upload and not force_upload:
                return _ClaimResult(False, "upload")
            self._quitting = True
            return _ClaimResult(True)

    def begin_update_shutdown(self) -> bool:
        with self._lock:
            if not self._handoff:
                return False
            self._quitting = True
            return True


@dataclass
class _UpdateRuntime:
    state: str = "idle"
    release: updates_mod.ReleaseInfo | None = None
    staged: Path | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str = ""
    automatic_failure: bool = False
    worker: threading.Thread | None = None


class Api:
    """JS-callable methods only. Every other attribute underscore-prefixed."""

    def __init__(
        self,
        state: AppState,
        *,
        id_factory=lambda: uuid.uuid4().hex,
        rows=None,
        durations_file=None,
        links_file=None,
        drain_interval_s=PROBE_DRAIN_S,
        spawn=threading.Thread,
        probe=library.probe,
        timer=threading.Timer,
        preview_host=None,
        skills=None,
        alerts=None,
        update_service=updates_mod,
        update_spawn=threading.Thread,
        is_frozen=lambda: bool(getattr(sys, "frozen", False)),
    ):
        self._state = state
        self._window = None  # assigned by ui.window.create()
        # Assigned by ui.sigbar.create(), same underscore-only rule as
        # _window above: a public attribute here reaches the js_api proxy
        # walk and the same RecursionError follows.
        self._sigbar_window = None
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

        # One mutation at a time. A per-mutation worker says nothing about
        # how many may exist at once, and _confirm() parks each one
        # independently -- so two operations approved moments apart could
        # otherwise interleave over the same files.
        self._eve_mutation = threading.Lock()
        # Identification state is reached by the bridge thread (start,
        # check, confirm, cancel) and by the resolver worker (a learned
        # deletion invalidates the offer it names). Its own lock, held only
        # to read, clear, or compare-and-publish the three fields below --
        # never across discovery, an ESI call, a settings write or a
        # dialog. LOCK ORDER IS FIXED: _eve_mutation may be taken before
        # this one, NEVER after, so cleanup (which owns _eve_mutation) and
        # a cancellation (which must never wait for it) cannot deadlock.
        self._eve_identification_lock = threading.Lock()
        # Monotonic for the process. Every invalidation -- cancel, restart,
        # selection change, learned deletion -- claims a new number, which
        # is what makes "this answer was computed before that event"
        # decidable here and on the page.
        self._eve_identification_generation = 0
        # A snapshot exists only during an explicit identification pass.
        # Timestamps are evidence for that pass, never durable identity.
        self._eve_identification = None
        # The latest observed account and the characters it offered. This is
        # ephemeral authorization for confirmation, not persisted identity.
        self._eve_identification_candidate: _EveCandidate | None = None
        # Process-lifetime memo. Names are cosmetic and free to re-fetch.
        self._eve_names = evesettings_names.NameCache()
        # (datasource, character id) pairs ESI explicitly reported as
        # deleted. Monotonic for the process and NEVER persisted: a launch
        # that cannot reach ESI must not inherit a blacklist from an
        # obsolete answer, and every launch revalidates when Profiles opens.
        # "Active" is deliberately not cached here -- see the resolver.
        self._eve_deleted: set[tuple[str, int]] = set()
        # What each canonical context last PUBLISHED. Remote facts are
        # global; applying them to a selection is not, so a trailing pass
        # can push what a superseded pass merely learned, and a pass that
        # changes nothing for its own context stays silent.
        self._eve_applied: dict[_EveContext, tuple[frozenset, frozenset]] = {}
        # Single-flight with one coalesced trailing pass. Held only to read
        # and write the two flags below -- never across a network call, a
        # settings write, or a spawn.
        self._eve_resolve_lock = threading.Lock()
        self._eve_resolve_running = False
        self._eve_resolve_pending = False
        # Last known answer for the advisory "EVE running" pill, or None
        # for "nobody has looked yet". None rather than False because the
        # pill is the ONLY warning before a copy, and False is the
        # reassuring guess: the probe is off the bridge thread precisely
        # because its first, uncached pass is slow, so a fabricated
        # "EVE closed" would be on screen for exactly as long as it takes
        # to be wrong about. The page renders the third state as
        # "Checking...". Read on the bridge thread, written by the probe;
        # a plain assignment, so no lock is needed for coherence.
        self._eve_running = None
        # One probe at a time. eve_settings_state() fires one on every
        # call -- route open, and after every mutation -- so two easily
        # overlap, and a slow probe finishing after a fast one would
        # otherwise publish the OLDER observation and leave it cached.
        self._eve_probe = threading.Lock()

        # None off the happy path -- when the subsystem failed to build, and
        # in most tests. Every call site below tolerates its absence and
        # returns a safe value, which is what lets the page render the route
        # without probing for a capability first.
        self._skills = skills

        # None off the happy path -- pre-Windows-check, off Linux in tests,
        # and when the gamelogs feature is otherwise unavailable. Every
        # call site below tolerates its absence: reconcile() is the only
        # method ever invoked on it, and every one of the alert bridge
        # methods below guards on it first.
        self._alerts = alerts

        self._rows = rows if rows is not None else RowSnapshot()
        self._durations_file = durations_file or paths.durations_file()
        self._cache = durations.load(self._durations_file)
        self._links_file = links_file or paths.links_file()
        self._link_store = links.load(self._links_file)
        self._drain_interval_s = drain_interval_s
        self._spawn = spawn
        self._probe = probe
        self._timer = timer
        self._update_service = update_service
        self._update_spawn = update_spawn
        self._is_frozen = is_frozen
        # Assigned by main() once its idempotent window teardown exists.
        # Tests and partial construction leave it unset; a successful native
        # launch still closes its process handle and owns the work gate.
        self._request_shutdown = None
        self._probe_queue: queue.Queue = queue.Queue()
        # Every list_rows() bumps this. A probe result carrying a stale
        # generation refers to rows that have since been replaced, and is
        # dropped rather than written into the current list.
        self._generation = 0
        self._drain: Scheduler | None = None

        # The claim exists before a worker handle and survives through its
        # target's finally. Thread liveness has a pre-start gap and therefore
        # cannot arbitrate concurrent pywebview bridge calls.
        self._work_gate = _WorkGate()
        self._update_lock = threading.Lock()
        self._update = _UpdateRuntime()
        self._upload_thread: threading.Thread | None = None
        self._delete_thread: threading.Thread | None = None
        # The standalone combat-log post, and Play. Separate handles rather
        # than one "work" slot because each answers a different question:
        # _busy() (an upload, which a list rebuild would damage and Quit
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
        self._watcher = None
        self._auth_thread: threading.Thread | None = None
        self._on_recording_dir_ready = None
        # Serializes all preview hotkey persistence and host delivery.
        # Every write to preview.hotkeys -- set_preview_binds and all group
        # operations -- must acquire this lock before entering
        # settings_mod.update and must hold it through the host.set_hotkeys
        # call that follows. That makes the per-call sequence (persist then
        # deliver) atomic with respect to every other such call, so two
        # concurrent mutations cannot reorder their host deliveries past their
        # persist order.
        self._preview_hotkey_lock = threading.Lock()

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
        script = f"window.{handler} && window.{handler}({json.dumps(payload)})"
        try:
            self._window.evaluate_js(script)
        except Exception:
            logger.debug("Push of %s failed", handler, exc_info=True)
        # The floating sig bar is a second page fed from the same pushes --
        # one timer, one reader of the engine's status file, two renderers.
        # Its failures cost the same nothing the main window's do.
        if self._sigbar_window is not None:
            try:
                self._sigbar_window.evaluate_js(script)
            except Exception:
                logger.debug("Sig bar push of %s failed", handler, exc_info=True)

    def _push_skills(self, handler: str, payload) -> None:
        """The skills subsystem's push, with presentation labels added.

        D3/S6. `_with_fetch_labels` was applied by the `skills_state`
        METHOD and nowhere else, while eveskills.controller pushed
        `state_payload()` raw. skills.js asks for state on first entry only
        (it says so at skills.js:76-79 -- after that every mutation
        pushes), and both payloads land in the same renderer, so the first
        render of the route was labelled and EVERY render after it was not.
        The page's own fallback then printed "Never fetched" for every
        character however recently fetched, beside queue timing drawn from
        the same payload -- which is the contradiction the maintainer
        reported.

        This is the failure class CLAUDE.md warns about and it is why the
        fix is here: a missing KEY crossing the bridge is a silent no-op,
        test_bridge_contract.py checks handler names rather than payload
        shape, and nothing in the suite renders the page.

        Label-building deliberately stays in ui/ rather than moving into
        controller.state_payload -- _with_fetch_labels' own docstring gives
        the reason (the controller is the only writer of the skills
        document, the label is presentation, and state_payload may hand
        back structures the document still references, so a key written
        there is one save away from being persisted). Wrapping the push
        callback keeps that boundary and closes the gap it created.

        Passed to the controller as this bound method, so onSkillsProgress
        and any later event go through unchanged -- a name resolved lazily
        in a lambda is what tests/test_skills_wiring.py forbids.
        """
        if handler == "onSkills":
            payload = _with_fetch_labels(payload)
        self._push(handler, payload)

    # The status strip is global chrome: it is the same strip on every
    # route, and app.js deliberately never tells Python which route is
    # showing. So the page cannot work out on its own whether what the
    # strip holds is still true -- and round 3's finding 14 caught exactly
    # that: a green "Posted combatlogs-...zip (15 KB)." and a bar at 100%
    # still on screen in a capture of a DIFFERENT folder with zero
    # recordings, and again on the Profiles and Skills routes. The
    # completion state of one upload outlived everything it was about.
    #
    # `busy` is the missing fact, and only Python has it: True means the
    # strip is describing something that is STILL RUNNING, False means it
    # is describing a result. The page clears a settled strip when the
    # route changes and never clears a busy one -- during an upload the
    # strip is the only feedback there is (finding 12), so it has to
    # survive a user wandering off to Skills and back.
    #
    # Every strip push goes through these two, so a new one cannot forget
    # the flag and silently inherit "settled". test_api_upload.py walks this
    # module's AST and asserts that the only _push calls naming onStatus or
    # onProgress are the two below.
    #
    # The DEFAULT is `None`, not False, and that is load-bearing. The strip
    # is one shared surface and the upload is not its only writer: Delete,
    # Copy link, Open folder and the whole Profiles half are reachable while
    # an upload runs, and each of them ends on a line of its own. Written as
    # a plain False those lines would settle the strip on behalf of an
    # upload that is still going, and the next route change would blank it.
    # Harmless mid-transfer, where the next chunk repaints within a second;
    # NOT harmless mid-stitch, which reports no progress this code can read
    # and can go minutes with nothing to repaint it. So `None` means "not
    # mine to say" and defers to _busy(), and only the upload's own
    # lifecycle states the flag outright.

    def _status(self, text: str, kind: str = "FG", *, busy: bool | None = None) -> None:
        """Push one status-strip line. See the note above on `busy`."""
        self._push(
            "onStatus",
            {
                "text": text,
                "kind": kind,
                "busy": self._busy() if busy is None else busy,
            },
        )

    def _progress(
        self,
        pct: float,
        text: str = "",
        kind: str = "FG",
        *,
        mode: str = "determinate",
        busy: bool | None = None,
    ) -> None:
        """Push one progress-bar state. See the note above on `busy`."""
        self._push(
            "onProgress",
            {
                "mode": mode,
                "pct": pct,
                "text": text,
                "kind": kind,
                "busy": self._busy() if busy is None else busy,
            },
        )

    def _alert(self, kind: str, title: str, body: str) -> None:
        """Non-blocking message box: info, error, or warning."""
        self._push(
            "onDialog", {"kind": kind, "title": title, "body": body, "request_id": None}
        )

    def _confirm(
        self,
        title: str,
        body: str,
        *,
        destructive: bool = False,
        confirm_label: str | None = None,
    ) -> bool:
        """Ask the page a yes/no question and block until it answers.

        This blocks the CALLING thread, which must be a worker -- exactly as
        `messagebox.askyesno` blocked the Tk main thread it was called on.
        The difference is which thread pays: calling this from the thread
        that services `pywebview.api.*` would deadlock, because
        `dialog_response` could never be delivered.

        The Event is registered before the push, not after: `evaluate_js`
        can complete and the user can answer before this method resumes.

        `destructive` picks the affirming button's treatment on the page.
        `confirm_label` may make that answer name a specific action and cost;
        the page retains its generic label when it is omitted. See _ask.
        """
        return self._ask(
            title,
            body,
            timeout=None,
            destructive=destructive,
            confirm_label=confirm_label,
        )

    def _ask(
        self,
        title: str,
        body: str,
        *,
        timeout: float | None,
        destructive: bool = False,
        confirm_label: str | None = None,
    ) -> bool:
        """The body of _confirm, with the wait made optional.

        `timeout=None` is _confirm's own unbounded wait, unchanged. A
        deadline is only useful to a caller that holds something while it
        waits -- see _eve_confirm.

        `destructive=True` sends the page a dialog whose Confirm is
        .btn.danger rather than .btn.acc. It is a claim about the ACTION,
        not about the wording: pass it wherever the affirming answer
        destroys something clicking again will not bring back. The
        default is False because most confirms are not that, and a
        destructive treatment that appears everywhere says nothing.

        This exists because panel.js used to hard-code `btn acc` on every
        confirm under a comment reading "Upload is the app's only
        irreversible action". Delete and the EVE settings copy had both
        falsified that by the time it was read, so the one dialog in the
        app that overwrites 34 characters' settings was rendering its
        Confirm in the same encouraging purple as `Upload`.
        """
        request_id = self._id_factory()
        event = threading.Event()
        entry = [event, False]
        with self._dialog_lock:
            self._dialogs[request_id] = entry
        try:
            self._push(
                "onDialog",
                {
                    "kind": "confirm",
                    "title": title,
                    "body": body,
                    "request_id": request_id,
                    "destructive": destructive,
                    "confirm_label": confirm_label,
                },
            )
            if not event.wait(timeout):
                logger.warning(
                    "No answer to %r within %ss; treating it as a refusal",
                    title,
                    timeout,
                )
                return False
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

        Unless the user SKIPPED first run, in which case the empty push is
        the whole point. #list-empty starts hidden in markup and is only
        ever unhidden by list.js's render(), which runs on this push -- so
        without it a skipped install lands on a list with no rows, no empty
        state and no explanation, which is precisely the inert screen
        DESIGN.md warns reads as a broken one.
        """
        if self._state.recording_dir is None:
            if self._state.settings.get("first_run_skipped"):
                self._push("onRows", {"rows": []})
            return
        self._generation += 1
        generation = self._generation
        self._stop_drain()

        rebuilt = self._rows.rebuild(self._state.recording_dir, preselect=preselect)
        # rebuild() mints new ids, so every key already in _links is dead --
        # rows.py's whole contract is that a stale id resolves to nothing.
        # Cleared rather than left, because the restore loop below re-adds a
        # key per linked row on EVERY refresh (launch, tray open, settings
        # save, delete, watcher find) and this map would otherwise grow
        # without bound across a long session, holding ids nothing can reach.
        self._links.clear()
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

        # Links, from the same place and for the same reason: rebuild()
        # mints new ids and freezes each Row before anything is known about
        # it, so a link that is not re-applied here never reaches the page.
        # Before this loop existed the Link column was empty on every fresh
        # launch, including for recordings that were already on YouTube --
        # which is the question the column is there to answer.
        #
        # AUTHORITATIVE IN BOTH DIRECTIONS, which is not optional. The
        # snapshot's own link map is keyed by PATH and survives rebuild on
        # purpose, so a file re-recorded at a path uploaded earlier in this
        # session comes back out of rebuild() carrying the previous
        # recording's video. Only the persisted store can tell the two
        # apart, because only it is keyed on (size, mtime) -- so a miss has
        # to CLEAR rather than be skipped. Setting without clearing passed
        # every test that used a fresh Api and failed the moment one
        # session did both.
        #
        # BOTH maps are filled. self._links is keyed by row id and is what
        # copy_path and open_path read back; the snapshot's is keyed by path
        # and is what renders the cell. A restore that filled only the
        # snapshot would draw a link the context menu could not open.
        for row_id, info in zip(ids, infos):
            url = links.lookup(self._link_store, info.path, info.size, info.mtime)
            if url:
                self._links[row_id] = url
            self._rows.set_link(row_id, url)

        self._push("onRows", {"rows": self._rows.rows()})
        # Restated on every rebuild, and this is the ONLY thing that can
        # repair it. A disarming push lost into a hidden window (which
        # _push swallows, by design) leaves the page drawing the button as
        # disabled, and a disabled button takes neither a click nor a
        # keypress -- so it cannot ask for its own repair. A rebuild is
        # what a watcher announcement, a delete and a folder change all
        # produce, so the wrong state cannot outlive the next recording.
        self._push("onLogPostRunning", {"running": self._logs_busy()})
        work = [
            (row_id, info)
            for row_id, info in zip(ids, infos)
            if id(info) in outstanding
        ]
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
        pairs = [
            (rid, info) for rid in ids if (info := self._rows.resolve(rid)) is not None
        ]
        if not pairs:
            self._alert(
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
        if not self._confirm(
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
        self._status(message)

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
        self._status("Link copied to clipboard", "SUCCESS")
        return url

    def open_path(self, row_id: str) -> None:
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
            self._status("That list is out of date. Refresh and try again.", "WARNING")
            return
        self._play_thread = self._spawn(
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
            self._status(f"That recording is no longer there: {path.name}", "WARNING")
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
            self._status(f"That file could not be opened: {path.name}", "WARNING")

    def rename_recording(self, row_id: str, stem: str) -> dict:
        """Rename one recording on disk, keeping its extension.

        Returns `{ok, error}` for the page to render rather than pushing a
        status line: the page owns the dialog this answers (`WM.prompt` --
        `_confirm` would deadlock the bridge thread it is called on), and a
        refusal re-opens that dialog with the typed text still in it, so a
        typo does not cost the whole name.

        Runs on the BRIDGE THREAD deliberately, but not because that makes
        it exclusive: `poll_tick` runs on the Scheduler's thread, so a poll
        CAN land in the middle of this. The stores below tolerate that --
        each mutation is a single dict operation and `Watcher._save` copies
        before it walks -- and the alternative, a worker, would buy nothing:
        the work is milliseconds of metadata with no dialog to park on,
        because the page has already answered the prompt.

        The one visible consequence of that race is benign. A rebuild
        landing between `resolve` and `self._rows.rename` re-mints the ids,
        so the repaint below finds nothing -- but that rebuild has just
        re-scanned the folder and is already drawing the new name.
        """
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
        if self._busy():
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

        # ONLY after the rename succeeded. Four stores are keyed by path,
        # and moving keys first would leave every one of them describing a
        # file that does not exist. A rename changes neither size nor mtime,
        # so each is a key move with the entry intact.
        #
        # The watcher is the one that fails quietly: its seen-set is keyed
        # by path, so without this the next poll finds a settled, closed,
        # unknown file and announces it as a newly finished recording --
        # preselected, ready to upload, for the second time.
        if self._watcher is not None:
            self._watcher.rename(old_path, new_path)
        # links cannot be rebuilt by anything (links.py's docstring), so
        # losing this key loses the Link column's answer permanently.
        links.rename(self._link_store, old_path, new_path)
        links.save(self._links_file, self._link_store)
        # Cheap rather than critical: a lost duration costs one ffprobe.
        durations.rename(self._cache, old_path, new_path)
        durations.save(self._durations_file, self._cache)
        # The fourth store, and the one the CELL renders from.
        self._rows.rename(row_id, new_path)

        # A targeted repaint, not list_rows(). A rebuild re-mints every id
        # and the page's selection, focus ring and sort position go with
        # them -- and a rename is an incidental action on one row, unlike
        # the delete that is the only other refresh to clear a selection.
        self._push("onRowRenamed", {"id": row_id, "name": new_path.name})
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
            self._status(
                "No recording folder is set. Choose one in Settings.", "WARNING"
            )
            return False
        if not Path(folder).is_dir():
            # The same case __main__ treats as first run at launch: a
            # folder that was configured and has since gone. Naming it
            # beats "an error occurred", per PRODUCT.md's tone rule.
            self._status(f"That folder is gone: {folder}", "WARNING")
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
            self._status("That folder could not be opened.", "WARNING")
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

        def worker() -> None:
            try:
                for row_id, info in work:
                    if generation != self._generation:
                        break  # A newer list_rows owns the list now.
                    if info.probed:
                        continue  # Already resolved on demand.
                    duration, definitive = self._probe(
                        info.path, self._state.ffprobe_bin
                    )
                    self._probe_queue.put(
                        (generation, row_id, info, duration, definitive)
                    )
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
                durations.remember(
                    self._cache, info.path, info.size, info.mtime, duration
                )
            self._push_duration(row_id, duration, definitive)
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

    def _push_duration(self, row_id, duration, definitive: bool) -> None:
        """Record one probe result and tell the page what the cell says.

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
        """
        rendered = self._rows.set_duration(row_id, duration, definitive)
        if rendered is None:
            return
        self._push(
            "onDuration",
            {"id": row_id, "duration": rendered, "definitive": definitive},
        )

    # ----- upload -----------------------------------------------------------

    def _busy(self) -> bool:
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

    def _logs_busy(self) -> bool:
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

    def _update_installation_preparing(self, *, show_window: bool) -> None:
        if show_window and self._window is not None:
            self._window.show()
        self._alert("info", "Update", "Update installation is being prepared.")

    def _claim_quit(self) -> bool:
        """Answer "may the app exit now?" and atomically close the work gate.

        Quit destroys the window, which returns from the GUI loop and ends
        the process. The upload worker is a daemon, so an upload in flight
        dies mid-chunk: no message, no log line, and a multi-gigabyte
        transfer discarded by one menu click. This is the only thing
        standing between that click and the discard.

        Private, and called from `__main__.on_quit` -- the same reach
        `__main__` already makes for `_busy`, `_push` and `_alert`. It may
        NOT be public: pywebview builds its JS proxy from public attributes,
        so a public name here would hand the page a way to ask the user to
        quit.

        Three things this gets right that the obvious version does not.

        It raises the window BEFORE asking. This is a tray app whose window
        is usually hidden -- `--hidden` is how the login entry starts it --
        and `_push` into a hidden window is swallowed, so the dialog would
        never be seen and the wait would run to its timeout. Quit would
        look broken.

        It uses a BOUNDED wait. `_confirm` blocks forever by design, which
        is right for a worker and wrong here: this runs on the pystray
        thread, and parking it stops the whole tray menu.

        Silence means DO NOT QUIT. A page that crashed or is mid-reload
        never answers, and the two failures are not symmetric -- reading
        silence as "stay running" costs a second click, reading it as
        "quit" costs the upload.
        """
        claim = self._work_gate.claim_quit(force_upload=False)
        if claim:
            return True
        if claim.reason != "upload":
            self._update_installation_preparing(show_window=True)
            return False

        window = self._window
        if window is None:
            # No page to ask and no way to warn. Refusing here would make
            # Quit inert with nothing on screen explaining why, which is a
            # worse failure than the discard this guard exists to prevent.
            logger.warning("Quit requested with an upload running and no window.")
        else:
            window.show()
            if not self._ask(
                "Upload in progress",
                copy_mod.format_quit_confirm(self._last_pct),
                timeout=QUIT_CONFIRM_TIMEOUT_S,
            ):
                return False

        claim = self._work_gate.claim_quit(force_upload=True)
        if claim:
            return True

        # An updater can win after a confirmed upload ends but before Quit
        # takes its claim. Never destroy the window under that handoff.
        self._update_installation_preparing(show_window=True)
        return False

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
            self._alert(
                "warning", "No Selection", "Select at least one video to upload."
            )
            return
        if stitch and len(pairs) < 2:
            self._alert("warning", "Stitch", "Select at least two videos to stitch.")
            return
        if self._logs_busy():
            # Its own sentence. Reusing the line above would say an upload
            # is running when none is, on the one screen where the user can
            # see that nothing is uploading.
            self._alert(
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
                self._alert("warning", "Busy", "An upload is already in progress.")
            else:
                self._update_installation_preparing(show_window=False)
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
        body = copy_mod.format_upload_confirm(
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
        if not self._confirm("Confirm Upload", body):
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
        self._links[row_id] = url
        self._rows.set_link(row_id, url)
        links.remember(self._link_store, info.path, info.size, info.mtime, url)
        links.save(self._links_file, self._link_store)
        self._push("onLink", {"id": row_id, "url": url})

    def _upload_done(self, job: UploadJob) -> None:
        self._retry_state = None
        # Disarmed HERE and not left to _upload_worker's finally: the video
        # half is over, but the combat-log half below still runs on this
        # thread and can take seconds. The finally is several frames away,
        # so a Cancel left armed across the log post would be a live button
        # with nothing polling its flag -- a click that does nothing, which
        # is the state D5 exists to remove rather than relocate.
        self._push("onCancelAvailable", {"available": False})
        summary = _upload_summary(job)
        # Explicit False on both: this runs ON the upload thread, so
        # _busy() is still true here and the default would refuse to settle
        # the very line that says the job is over.
        self._status(f"{summary}.", "SUCCESS", busy=False)
        self._progress(100.0, kind="SUCCESS", busy=False)
        self._push("onRetryAvailable", {"available": False})
        # Round 3's finding 5, panel half. A SEMANTIC event -- the job
        # finished -- not an instruction: the page decides that this means
        # dropping the selection, because selection is client state and
        # never crosses this bridge. Pushed here rather than from the two
        # call sites so the resume tail reports completion the same way a
        # plain job does.
        self._push("onUploadDone", {})
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
                self._progress(
                    0.0, "Stitching with FFmpeg…", mode="indeterminate", busy=True
                )
                with stitch.stitched(
                    sources, self._state.ffmpeg_bin, paths.tmp_dir()
                ) as merged:
                    self._progress(0.0, busy=True)
                    # Armed HERE, inside the context manager and after the
                    # join, not at the top of the branch: D5 scopes cancel
                    # to the upload phase only. stitch.stitched() runs a
                    # bundled ffmpeg with no interruption seam, and a
                    # Cancel that did nothing for the minutes a join takes
                    # is worse than no Cancel at all.
                    self._push("onCancelAvailable", {"available": True})
                    vid = self._upload_one(
                        youtube, MediaFileUpload, merged, job, 0, 1, close_media=True
                    )
                # Every source recording gets the stitched video's URL,
                # each persisted against its own file identity.
                for row_id, item in zip(job.ids, job.items):
                    self._link(row_id, vid, item)
            else:
                total = len(job.items)
                self._push("onCancelAvailable", {"available": True})
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
            text = copy_mod.format_upload_cancelled(done, len(job.items))
            # No _retry_state and no onRetryAvailable, per D5: Retry exists
            # to recover from a failure, and a stop is not one. Offering it
            # here would also re-arm the slot the Cancel button was just
            # occupying.
            self._retry_state = None
            # Not ERROR: the user asked for this. The bar keeps the ground
            # the job actually covered rather than resetting to 0, which
            # would contradict a sentence saying two of four are up.
            self._status(text, "WARNING", busy=False)
            self._progress(self._last_pct, kind="WARNING", busy=False)
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
            self._alert("error", "Upload Failed", str(exc))
            self._status(str(exc), "ERROR", busy=False)
            if exc.outcome is uploader.Outcome.RETRY:
                self._push("onRetryAvailable", {"available": True})
        except Exception as exc:  # noqa: BLE001 - reported to the user, never raised
            self._retry_state = None
            # Covers a stitch failure too (StitchError isn't an
            # UploadFailed): if the bar was left indeterminate above, put it
            # back rather than leaving it animating behind the error.
            self._progress(0.0, busy=False)
            self._alert("error", "Upload Failed", str(exc))
            self._status(f"Error: {exc}", "ERROR", busy=False)
        finally:
            # Every exit, including the success one: the slot is shared with
            # Retry and the two are never live at once, so a Cancel left
            # armed would sit beside the Retry a failure just enabled.
            self._push("onCancelAvailable", {"available": False})

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
            self._progress(
                self._last_pct,
                copy_mod.format_progress(index, total, fraction),
                busy=True,
            )

        def on_retry(attempt: int, delay: float) -> None:
            # Carries the last percentage rather than zero: the upload has
            # not lost the ground it covered, and a bar snapping backwards
            # while the text says "retrying" reads as a restart.
            self._progress(
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
        self._push(
            "onChannel",
            {
                "channel_id": channel_id,
                "channel_title": channel_title,
                # Rendered here, not in the page: format_destination states the
                # "learned from the first upload" case in words, and that
                # explanation is copy with its own test, not a template.
                "destination": copy_mod.format_destination(
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
        self._push_auth("connected")

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
            self._push("onRetryAvailable", {"available": False})
            if claim.reason == "upload":
                self._alert("warning", "Busy", "An upload is already in progress.")
            else:
                self._update_installation_preparing(show_window=False)
            return
        try:
            # Disabled immediately, not by the worker: the click that got here
            # must not be repeatable while the resume is being set up.
            self._push("onRetryAvailable", {"available": False})
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
                self._progress(
                    self._last_pct,
                    copy_mod.format_progress(state.resume_index, total, fraction),
                    busy=True,
                )

            # Armed for the resumed file too, not just for the tail that
            # _upload_worker picks up below. Without it the button would be
            # absent for one file and then appear part-way through the same
            # job, which is a control blinking in and out under the pointer
            # -- the hazard index.html's stitch note already records for
            # this screen.
            self._push("onCancelAvailable", {"available": True})
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
            self._status(
                copy_mod.format_upload_cancelled(
                    state.resume_index, len(state.job.items)
                ),
                "WARNING",
                busy=False,
            )
            self._progress(self._last_pct, kind="WARNING", busy=False)
            self._push("onCancelAvailable", {"available": False})
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
            self._status(str(exc), "ERROR", busy=False)
            self._push("onCancelAvailable", {"available": False})
            if retryable:
                self._push("onRetryAvailable", {"available": True})
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            # _upload_worker arms and disarms the control itself, in its own
            # finally, so this hands the slot straight over rather than
            # disarming between the two halves of one job.
            self._upload_worker(replace(state.job, start_index=state.resume_index + 1))
        else:
            self._upload_done(state.job)
            self._push("onCancelAvailable", {"available": False})

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
        if self._logs_busy():
            self._push("onLogPostRunning", {"running": True})
            self._status("Combat logs are already being posted.", "WARNING")
            return
        if self._busy():
            self._push("onLogPostRunning", {"running": False})
            self._status(
                "An upload is running. Post the logs when it finishes.", "WARNING"
            )
            return

        target = self._log_target()
        if target.hook is None or target.gamelogs_dir is None:
            self._push("onLogPostRunning", {"running": False})
            # "not posted", never "skipped": nothing else ran, so there is no
            # successful half for this to be a footnote to.
            self._status(f"Combat logs not posted: {target.problem}", "WARNING")
            return

        self._push("onLogPostRunning", {"running": True})
        # Claimed under the lock, and the claim is what makes this safe:
        # pywebview serves each bridge call on its own thread, and a guard
        # written against thread.is_alive() would answer False for the
        # handle assigned a microsecond ago and let a second post through.
        with self._logs_lock:
            if self._logs_running:
                return
            self._logs_running = True
        try:
            self._logs_thread = self._spawn(
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
            self._push("onLogPostRunning", {"running": False})
            self._status("Combat logs not posted: it could not start.", "WARNING")

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
            self._push("onLogPostRunning", {"running": False})

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
        self._status(f"{summary}. Combat logs skipped: {reason}", "WARNING", busy=False)

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
            self._status(f"Reading recording lengths… ({index}/{total})", busy=True)
            duration, definitive = library.probe(info.path, self._state.ffprobe_bin)
            if definitive:
                durations.remember(
                    self._cache, info.path, info.size, info.mtime, duration
                )
                measured += 1
            self._push_duration(row_id, duration, definitive)
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
            self._status("Collecting combat logs…", busy=True)
            selection = combatlog.select_logs(gamelogs_dir, start_utc, end_utc)
            if not selection.logs:
                self._alert(
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
                self._status(terminal("No combat logs found."), "SUCCESS", busy=False)
                return

            stamp = start_utc.strftime("%Y-%m-%d_%H-%M")
            out = paths.tmp_dir() / f"combatlogs-{stamp}.zip"
            self._status("Building archive…", busy=True)
            archive = combatlog.build_archive(selection, out, start_utc, end_utc)

            content = combatlog.summarize_archive(archive, start_utc, end_utc)
            self._status("Posting to Discord…", busy=True)
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
                self._status(terminal(status_text), "SUCCESS", busy=False)
            else:
                # Keep the archive: the window is fixed by the recording and
                # there is no UI for selecting fewer logs, so a user told
                # "too large" has no move available unless the file survives.
                self._alert(
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
                self._status(terminal(result.message), "ERROR", busy=False)
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
            self._alert("error", "Combat log upload failed", detail)
            self._status(terminal(f"Error: {exc}"), "ERROR", busy=False)

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
                cfg.get("discord_webhook", "") or ""
            ),
            "detected": {
                "recording": str(detected_rec) if detected_rec else "",
                "gamelogs": str(detected_logs) if detected_logs else "",
            },
            # Depends only on values Python owns (channel title and
            # privacy), so it is rendered here rather than templated in the
            # page -- format_destination is tested copy.
            "destination": copy_mod.format_destination(
                cfg.get("channel_title", ""), cfg.get("privacy", "")
            ),
            # Pushed from __version__, never typed into the page. M2: the
            # value was already plumbed to the Discord user-agent, the ESI
            # user-agent and the backup names, and the UI was the only
            # consumer that never read it -- so a user reporting a bug had
            # no way to say which build they were on. A hand-typed copy in
            # the page is exactly the drift DESIGN.md's "State that must
            # not be retyped" exists to stop.
            #
            # It rides the settings payload rather than a bridge method of
            # its own because get_settings is already the one read the page
            # makes at load, and a new _push name would need a WM.HANDLERS
            # entry. Top level, beside the other derived values: it is not
            # a setting and must never be written back.
            "version": _version,
            # Settings 1's words half. Delivered rather than templated into
            # index.html, where the Previews one used to live: static markup
            # is unreachable from any test and unreusable by any other
            # screen, which is how one release ended up explaining the same
            # situation two different ways.
            #
            # The whole table, not the one entry that happens to apply right
            # now: which notes are showing is a render decision the page
            # makes from state it already has (previews on/off, webhook
            # configured or not), and re-deriving that here would put the
            # predicate in two places.
            "inert_notes": dict(copy_mod.INERT_NOTES),
            # M3. Read from the registry on every render, not stored: the
            # login entry IS the state, and a user can delete it from Task
            # Manager's Startup tab at any time. A settings.json copy would
            # be a second answer that goes stale the first time they do,
            # and the checkbox would then describe a world that no longer
            # exists. Derived, top level, never written back.
            "start_on_login": autostart.is_enabled(),
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

        Returns the same shape the per-field endpoints push after a
        successful write, so the page has one renderer for both.
        """
        return self._settings_payload()

    def update_status(self) -> dict:
        return self._update_snapshot()

    def check_for_updates(self) -> dict:
        return self._start_update_check(automatic=False)

    def _page_ready(self) -> None:
        """Start optional network work only after WebView2 owns the page."""
        self.refresh_auth()
        self._start_update_check(automatic=True)

    def download_update(self) -> dict:
        with self._update_lock:
            if (
                self._update.state
                not in {
                    "available",
                    "check_failed",
                    "download_failed",
                }
                or self._update.release is None
            ):
                return self._update_snapshot_locked()
            release = self._update.release
            self._update.state = "downloading"
            self._update.staged = None
            self._update.downloaded_bytes = 0
            self._update.total_bytes = release.size
            self._update.error = ""
            snapshot = self._update_snapshot_locked()
        try:
            worker = self._update_spawn(
                target=self._update_download_worker,
                args=(release,),
                daemon=True,
                name="wingman-update-download",
            )
        except Exception:  # noqa: BLE001 - construction failure becomes retryable status
            return self._rollback_update_start("download")
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
            self._update.worker = worker
        self._push_update_status()
        try:
            worker.start()
        except Exception:  # noqa: BLE001 - start failure becomes retryable status
            return self._rollback_update_start("download")
        return snapshot

    def _update_download_worker(self, release: updates_mod.ReleaseInfo) -> None:
        path = None

        def progress(done: int, total: int) -> None:
            with self._update_lock:
                if self._update.state != "downloading":
                    return
                self._update.downloaded_bytes = done
                self._update.total_bytes = total
            self._push_update_status()

        try:
            path = self._update_service.download_release(
                release,
                self._update_staging_root(),
                on_progress=progress,
            )
            with self._update_lock:
                closed = self._update.state == "closed"
            if closed:
                self._remove_unhanded_update(path)
                return
            self._update_service.verify_after_attachment(release, path)
        except Exception as exc:
            if path is not None:
                self._remove_unhanded_update(path)
            logger.debug("Wingman update download failed", exc_info=True)
            with self._update_lock:
                if self._update.state == "closed":
                    return
                self._update.worker = None
                self._update.state = "download_failed"
                self._update.staged = None
                self._update.error = self._update_download_error(exc)
            self._push_update_status()
            return

        with self._update_lock:
            if self._update.state == "closed":
                closed = True
            else:
                closed = False
                self._update.worker = None
                self._update.state = "ready"
                self._update.staged = Path(path)
                self._update.downloaded_bytes = release.size
                self._update.total_bytes = release.size
                self._update.error = ""
        if closed:
            self._remove_unhanded_update(path)
            return
        self._push_update_status()

    def install_update(self) -> dict:
        if not self._is_frozen():
            return self._update_snapshot()
        # Reserve the runtime phase before consulting the work gate. That
        # reservation is the owner token Task 4 deliberately did not add to
        # _WorkGate, and avoids nesting the two locks.
        with self._update_lock:
            if (
                self._update.state != "ready"
                or self._update.release is None
                or self._update.staged is None
            ):
                return self._update_snapshot_locked()
            release = self._update.release
            path = self._update.staged
            self._update.state = "handing_off"
            self._update.error = ""
            snapshot = self._update_snapshot_locked()

        claim = self._work_gate.claim_handoff("handing_off")
        if not claim:
            with self._update_lock:
                if self._update.state == "handing_off":
                    self._update.state = "ready"
                    if claim.reason == "upload":
                        self._update.error = (
                            "Finish the active upload before installing the update."
                        )
                    snapshot = self._update_snapshot_locked()
            self._push_update_status()
            return snapshot

        try:
            worker = self._update_spawn(
                target=self._update_install_worker,
                args=(release, path),
                daemon=True,
                name="wingman-update-install",
            )
        except Exception:  # noqa: BLE001 - construction failure rolls back handoff
            return self._rollback_update_start("install")
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
            self._update.worker = worker
        self._push_update_status()
        try:
            worker.start()
        except Exception:  # noqa: BLE001 - start failure rolls back handoff
            return self._rollback_update_start("install")
        return snapshot

    def _update_install_worker(
        self, release: updates_mod.ReleaseInfo, path: Path
    ) -> None:
        with self._update_lock:
            if self._update.state != "handing_off":
                return
            self._update.state = "revalidating"
        if not self._work_gate.claim_handoff("revalidating"):
            self._finish_install_failure(
                updates_mod.UpdateFailure(
                    "launch", "claim", "update handoff ownership was lost"
                ),
                path,
            )
            return
        self._push_update_status()

        marker = None

        def before_launch() -> None:
            nonlocal marker
            marker = self._update_service.write_handoff_marker(path, release)

        try:
            process = self._update_service.launch_verified(
                release,
                path,
                before_launch=before_launch,
            )
            if not process:
                raise updates_mod.UpdateFailure(
                    "launch", "shell", "installer launch returned no process"
                )
        except Exception as exc:  # noqa: BLE001 - handoff failure must recover the app
            marker_failure = (
                isinstance(exc, updates_mod.UpdateFailure) and exc.stage == "cleanup"
            )
            marker_to_remove = marker
            if marker_to_remove is None and marker_failure:
                marker_to_remove = path.with_name(path.name + ".handoff.json")
            if marker_to_remove is not None:
                try:
                    self._update_service.remove_handoff_marker(marker_to_remove)
                except Exception:
                    logger.warning(
                        "Could not remove failed updater handoff marker",
                        exc_info=True,
                    )
            self._finish_install_failure(exc, path)
            return

        with self._update_lock:
            if self._update.state == "closed":
                closed = True
            else:
                closed = False
                self._update.state = "launching"
                self._update.worker = None
        if closed:
            self._close_update_process(process)
            return
        if not self._work_gate.claim_handoff("launching"):
            # This cannot happen while this runtime owns `revalidating`, but
            # retain the launched process handle even if lifecycle state is
            # corrupted: Setup already exists and must not be leaked.
            logger.error("Update handoff ownership was lost after Setup launch")
        self._push_update_status()
        self._close_update_process(process)
        if not self._work_gate.begin_update_shutdown():
            logger.error("Update handoff could not begin orderly shutdown")
        request_shutdown = self._request_shutdown
        if request_shutdown is not None:
            try:
                request_shutdown()
            except Exception:
                # Setup is already launched and durably classified. The shared
                # teardown is one-way, so report the failure without rollback
                # or a second destruction attempt.
                logger.exception("Window shutdown failed after installer launch")

    def _close_update_process(self, process: int) -> None:
        try:
            self._update_service.close_process_handle(process)
        except Exception:
            logger.warning("Could not close installer process handle", exc_info=True)

    def _finish_install_failure(self, exc: Exception, path: Path) -> None:
        retry_ready = isinstance(exc, updates_mod.UpdateFailure) and exc.stage in {
            "cleanup",
            "launch",
        }
        requires_download = not retry_ready
        with self._update_lock:
            if self._update.state == "closed":
                return
        self._work_gate.release_handoff()
        with self._update_lock:
            if self._update.state == "closed":
                return
            self._update.worker = None
            self._update.state = "download_failed" if requires_download else "ready"
            if requires_download:
                self._update.staged = None
            self._update.error = self._update_install_error(exc)
        if requires_download:
            self._remove_unhanded_update(path)
        self._push_update_status()

    def _rollback_update_start(self, stage: str) -> dict:
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
        if stage == "install":
            self._work_gate.release_handoff()
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
            self._update.worker = None
            self._update.state = "ready" if stage == "install" else "download_failed"
            self._update.error = self._update_start_error(stage)
            snapshot = self._update_snapshot_locked()
        self._push_update_status()
        return snapshot

    def shutdown_updates(self) -> None:
        with self._update_lock:
            if self._update.state == "closed":
                return
            preserve = self._update.state == "launching"
            staged = self._update.staged
            self._update.state = "closed"
            self._update.staged = None
            self._update.worker = None
            self._update.error = ""
        if staged is not None and not preserve:
            self._remove_unhanded_update(staged)
        self._update_service.cleanup_staging(self._update_staging_root())

    @staticmethod
    def _update_staging_root() -> Path:
        return paths.tmp_dir() / "updates"

    @staticmethod
    def _remove_unhanded_update(path: Path) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            # A native scanner or Setup may still have the file. Stale cleanup
            # retries later; forcing deletion is never safe on this path.
            logger.warning("Could not remove updater staging file", exc_info=True)

    def _start_update_check(self, automatic: bool) -> dict:
        allowed = {
            "idle",
            "current",
            "available",
            "unavailable",
            "check_failed",
            "download_failed",
        }
        previous = None
        with self._update_lock:
            if self._update.state == "checking":
                if not automatic:
                    self._update.automatic_failure = False
                return self._update_snapshot_locked()
            if self._update.state not in allowed:
                return self._update_snapshot_locked()
            previous = replace(self._update)
            self._update.state = "checking"
            self._update.error = ""
            self._update.automatic_failure = automatic
            snapshot = self._update_snapshot_locked()
        try:
            worker = self._update_spawn(
                target=self._update_check_worker,
                args=(),
                daemon=True,
            )
        except Exception:  # noqa: BLE001 - construction failure becomes retryable update status
            return self._rollback_update_check(previous, automatic)
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
            self._update.worker = worker
        self._push_update_status()
        try:
            worker.start()
        except Exception:  # noqa: BLE001 - start failure becomes retryable update status
            return self._rollback_update_check(previous, automatic)
        return snapshot

    def _rollback_update_check(self, previous: _UpdateRuntime, automatic: bool) -> dict:
        with self._update_lock:
            if self._update.state == "closed":
                return self._update_snapshot_locked()
            self._update = replace(previous)
            if not automatic:
                self._update.error = self._update_start_error("check")
            snapshot = self._update_snapshot_locked()
        self._push_update_status()
        return snapshot

    def _update_check_worker(self) -> None:
        try:
            release = self._update_service.latest_release(_version)
        except Exception as exc:
            logger.debug("Wingman update check failed", exc_info=True)
            with self._update_lock:
                if self._update.state == "closed":
                    return
                automatic = self._update.automatic_failure
                self._update.worker = None
                self._update.automatic_failure = False
                if automatic:
                    self._update.state = (
                        "available"
                        if self._update.release is not None
                        else "unavailable"
                    )
                    self._update.error = ""
                else:
                    self._update.state = "check_failed"
                    self._update.error = self._update_check_error(exc)
        else:
            with self._update_lock:
                if self._update.state == "closed":
                    return
                self._update.worker = None
                self._update.automatic_failure = False
                self._update.error = ""
                self._update.staged = None
                self._update.downloaded_bytes = 0
                self._update.total_bytes = 0
                if release is None:
                    self._update.release = None
                    self._update.state = "current"
                else:
                    self._update.release = release
                    self._update.state = "available"
        self._push_update_status()

    @staticmethod
    def _update_check_error(exc: Exception) -> str:
        if isinstance(exc, updates_mod.UpdateFailure):
            if exc.stage == "check" and exc.code == "network":
                return (
                    "Could not check for updates. Check your internet connection "
                    "and try again."
                )
            if exc.stage == "check":
                return (
                    "Could not check for updates. The latest release could not "
                    "be verified."
                )
        return "Could not check for updates. Try again."

    @staticmethod
    def _update_download_error(exc: Exception) -> str:
        if isinstance(exc, updates_mod.UpdateFailure):
            if exc.stage == "download" and exc.code == "network":
                return (
                    "Could not download the update. Check your internet connection "
                    "and try again."
                )
            if exc.code == "checksum":
                return (
                    "The download did not match the release checksum. "
                    "It was not installed."
                )
            if exc.stage == "download" and exc.code == "filesystem":
                return (
                    "Could not save the update. Check available disk space "
                    "and try again."
                )
            if exc.stage == "verify" and exc.code == "attachment":
                return (
                    "Windows could not mark the installer as an internet download. "
                    "It was not installed."
                )
        return "Could not download the update. Try again."

    @staticmethod
    def _update_install_error(exc: Exception) -> str:
        if isinstance(exc, updates_mod.UpdateFailure):
            if exc.stage == "launch":
                return "Could not open the installer. Try again."
            if exc.stage == "cleanup":
                return "Could not prepare the installer. Try installing again."
            if exc.stage == "verify" and exc.code == "attachment":
                return (
                    "Windows could not mark the installer as an internet download. "
                    "Download it again."
                )
        return (
            "The downloaded installer changed or is no longer available. "
            "Download it again."
        )

    @staticmethod
    def _update_start_error(stage: str) -> str:
        if stage == "check":
            return "Could not start checking for updates. Try again."
        if stage == "download":
            return "Could not start downloading the update. Try again."
        return "Could not start installing the update. Try again."

    def _update_snapshot(self) -> dict:
        with self._update_lock:
            return self._update_snapshot_locked()

    def _update_snapshot_locked(self) -> dict:
        release = self._update.release
        state = self._update.state
        update_available = release is not None
        available_version = ""
        if release is not None:
            available_version = ".".join(str(part) for part in release.version)
        return {
            "state": state,
            "installed_version": _version,
            "available_version": available_version,
            "update_available": update_available,
            "downloaded_bytes": self._update.downloaded_bytes,
            "total_bytes": self._update.total_bytes,
            "can_check": state
            in {
                "idle",
                "current",
                "available",
                "unavailable",
                "check_failed",
                "download_failed",
            },
            "can_download": update_available
            and state in {"available", "check_failed", "download_failed"},
            "can_install": state == "ready" and self._is_frozen(),
            "error": self._update.error,
        }

    def _push_update_status(self) -> None:
        with self._update_lock:
            if self._update.state == "closed":
                return
            snapshot = self._update_snapshot_locked()
        self._push("onUpdateStatus", snapshot)

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
        chosen = self._window.create_file_dialog(_folder_dialog_kind(), directory=start)
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
                self._alert(
                    "info",
                    "Gamelogs not found",
                    "Could not find an EVE Gamelogs folder under "
                    "Documents or OneDrive\\Documents. Use Browse… "
                    "to point at it.",
                )
                return ""
            if str(found) == current:
                self._alert(
                    "info", "Gamelogs", f"Already set to the detected folder:\n{found}"
                )
                return ""
            return str(found)

        detected = obsconfig.find_recording_dir()
        if detected is None or not detected.is_dir():
            self._alert(
                "info",
                "Detect recording folder",
                "Could not read OBS's configuration to detect a "
                "recording folder. Make sure OBS is installed and has "
                "recorded at least once, then try again.",
            )
            return ""
        if str(detected) == current:
            self._alert(
                "info",
                "Detect recording folder",
                f"Already set to the detected folder:\n{detected}",
            )
            return ""
        return str(detected)

    # ---- FightRecorder (the OBS plugin) ---------------------------------

    def fightrecorder_status(self, check: bool = False) -> dict:
        """What the page's FightRecorder card shows.

        Purely local unless `check` is set: the network round trip to the
        releases API happens only when the user presses Check for
        updates, never as a side effect of opening Settings -- a card
        that phones GitHub on every render is a card nobody asked for.

        Returned, not pushed: the card is the only consumer and there is
        nothing to keep in sync.
        """
        installed = fightrecorder.dll_path()
        status = {
            "installed": installed is not None,
            "path": installed or "",
            "detected": fightrecorder.find_obs_plugin_dir() is not None,
            "up_to_date": None,
            "latest_tag": "",
            "error": "",
        }
        if not check:
            return status
        try:
            release = fightrecorder.latest_release()
        except Exception:
            logger.exception("FightRecorder update check failed")
            status["error"] = "Could not reach GitHub -- check your internet."
            return status
        status["latest_tag"] = release["tag"]
        if installed is None:
            return status
        if not release["digest"]:
            # No digest to compare against: report the release without a
            # verdict rather than claiming either side of up-to-date.
            return status
        status["up_to_date"] = fightrecorder.sha256_file(installed) == release["digest"]
        return status

    def update_fightrecorder(self) -> dict:
        """Download, verify and install the latest FightRecorder DLL.

        The stages are deliberately sequential and each reports its own
        failure, because the three ways this fails are different user
        problems: offline (check the internet), checksum mismatch (don't
        install it), and the write (a UAC prompt the user may decline, or
        OBS holding the old DLL open).
        """
        plugin_dir = fightrecorder.find_obs_plugin_dir()
        if plugin_dir is None:
            return {
                "ok": False,
                "error": "OBS Studio was not detected on this machine.",
            }
        try:
            release = fightrecorder.latest_release()
        except Exception:
            logger.exception("FightRecorder update check failed")
            return {
                "ok": False,
                "error": "Could not reach GitHub -- check your internet.",
            }
        staged = os.path.join(tempfile.gettempdir(), fightrecorder.DLL_NAME)
        error = fightrecorder.download_latest(release["url"], release["digest"], staged)
        if error:
            return {"ok": False, "error": error}
        error = fightrecorder.apply_update(plugin_dir, staged)
        if error and "admin" in error:
            # The plugin directory is not writable by this user (OBS's
            # default install is under Program Files): one UAC prompt
            # covers the copy. The elevated helper is verified by
            # checking the result on disk, not by trusting exit codes.
            error = fightrecorder.elevated_copy(plugin_dir, staged)
        with contextlib.suppress(OSError):
            os.unlink(staged)
        if error:
            return {"ok": False, "error": error}
        installed = fightrecorder.dll_path()
        if (
            installed
            and release["digest"]
            and (fightrecorder.sha256_file(installed) != release["digest"])
        ):
            return {
                "ok": False,
                "error": "The installed file does not match the release "
                "checksum -- it may not have been replaced.",
            }
        return {"ok": True, "error": "", "tag": release["tag"]}

    # ---- per-field settings writes -------------------------------------
    #
    # The immediate-save Settings screen commits ONE field at a time, which
    # save_settings structurally cannot do. It validates and rewrites the
    # WHOLE document and refuses all of it on the first bad field, so a
    # blur out of a valid webhook while Category is momentarily empty saves
    # nothing and warns about a field the user is not looking at. It routes
    # every failure through _alert, which QUEUES (web/panel.js), so a URL
    # typed a character at a time would stack a pile of modals. It re-pushes
    # the complete payload, rewriting every field including the one still
    # being edited. And it has no no-op guard, so each call re-runs OBS and
    # gamelogs detection plus a full list_rows() ffprobe sweep.
    #
    # Shape: {"applied": bool, "persisted": bool, "error": str | None}.
    # This extends set_restore_preview_positions' contract with the one
    # thing a bool cannot carry -- WHY a value was refused -- phrased for
    # the field's own inline message rather than a queued modal.
    #
    #   applied False + error         -> rejected; page reverts and explains
    #   applied True, persisted False -> in effect, but not written to disk
    #   applied True, persisted True  -> done
    #
    # A truthy dict is also what separates success from a bridge failure,
    # which resolves to null on the page (web/app.js).

    @staticmethod
    def _field_ok(persisted: bool = True) -> dict:
        return {"applied": True, "persisted": persisted, "error": None}

    @staticmethod
    def _field_refused(error: str) -> dict:
        return {"applied": False, "persisted": False, "error": error}

    def _write_setting(self, key: str, value) -> dict:
        """Persist one already-validated scalar, no-op guarded.

        Through settings.update, never save(): the mutation has to happen
        inside _SAVE_LOCK or a concurrent writer is reverted, and update()
        restores the live dict if the write raises, so a failed write
        leaves the stored value as it was.
        """
        if self._state.settings.get(key) == value:
            # Not merely an optimisation. settings.save projects the
            # COMPLETE document, so a no-op write is a full rewrite -- and
            # an immediate-save page re-emits on every render.
            return self._field_ok()
        try:
            with settings_mod.update(self._state.settings) as doc:
                doc[key] = value
        except OSError:
            # Reported, not raised: a settings file that cannot be written
            # must not stop the setting taking effect, but the page has to
            # be able to say the choice is not saved.
            logger.exception("Could not persist %s", key)
            return self._field_ok(persisted=False)
        return self._field_ok()

    def set_start_on_login(self, value) -> dict:
        """Add or remove Wingman's Windows login entry.

        Not a _write_setting: nothing about this touches settings.json.
        The registry entry is the whole state, so there is no in-memory
        "applied" half that could succeed while the write fails -- and
        that collapses the commit contract's three outcomes to two here,
        honestly rather than by pretending:

          refused + error -> the write was denied; nothing changed
          applied+persisted -> the entry is now what the user asked for

        `applied True, persisted False` is unreachable, and faking it
        would tell the page a setting is "in effect but not saved" about a
        setting whose only effect is the saving. Naming that here so the
        next reader does not add a third branch to match the neighbours.

        Refusals are real on Windows: a managed machine can deny writes to
        the Run key by policy, and a checkbox that assumed success would
        silently do nothing every boot. PRODUCT.md's opt-in default lives
        on the page -- an unticked box on an install that was never asked
        -- and this endpoint has no opinion about it.
        """
        if not isinstance(value, bool):
            # The page sends a checkbox state. Anything else is a caller
            # bug, and coercing it would let a stray string enable a
            # login entry the user never ticked.
            return self._field_refused("Start on login is on or off.")
        try:
            if value:
                autostart.enable()
            else:
                autostart.disable()
        except OSError as exc:
            logger.exception(
                "Could not %s the login entry", "add" if value else "remove"
            )
            action = "add" if value else "remove"
            return self._field_refused(
                f"Windows would not let Wingman {action} its login entry. {exc}"
            )
        return self._field_ok()

    def set_privacy(self, value) -> dict:
        """Default privacy for new uploads."""
        if value not in settings_mod.VALID_PRIVACY:
            # settings._normalize would silently coerce this to the default
            # instead. Silent coercion is wrong for a field the user just
            # set: they would watch it snap back with no explanation.
            return self._field_refused("Choose private, unlisted, or public.")
        return self._write_setting("privacy", value)

    def set_notify_mode(self, value) -> dict:
        """What happens when a recording finishes."""
        if value not in settings_mod.VALID_NOTIFY:
            return self._field_refused("Choose one of the two options.")
        return self._write_setting("notify_mode", value)

    def set_category(self, value) -> dict:
        """YouTube category id. Digits only; 20 is Gaming."""
        text = str(value or "").strip()
        if not text.isdigit():
            return self._field_refused("A category is a number, like 20 for Gaming.")
        return self._write_setting("category", text)

    def set_discord_webhook(self, value) -> dict:
        """The combat-log webhook.

        Empty is REFUSED here. The whole-document `save_settings` this
        replaced treated it as "clear the webhook" and wrote "". Under
        immediate-save that made
        select-all, Delete, then look away silently destroy a configured
        secret -- with no Cancel to take it back and no pre-edit copy
        anywhere on the page. Removing a webhook is now its own explicit
        action; this endpoint only ever sets one.
        """
        text = str(value or "").strip()
        if not text:
            return self._field_refused(
                "Paste a webhook URL, or use Remove to clear it."
            )
        # parse_webhook RETURNS (webhook, error); it does not raise. An
        # except-ValueError around it never fires, which would have let
        # every malformed URL through.
        webhook, error = discord.parse_webhook(text)
        if webhook is None:
            return self._field_refused(error)
        return self._with_webhook_status(self._write_setting("discord_webhook", text))

    def clear_discord_webhook(self) -> dict:
        """Remove the webhook: the explicit counterpart to the above."""
        return self._with_webhook_status(self._write_setting("discord_webhook", ""))

    def _with_webhook_status(self, result: dict) -> dict:
        """Carry the new summary line back on the commit's own return.

        The per-field endpoints deliberately do not push a settings
        payload -- a whole-document delivery rewrites the field the user
        is still typing in -- and `get_settings` is fetched exactly once,
        at page load (app.js). Between those two facts, setting a webhook
        persisted while the page went on saying `not configured` and kept
        `Show` and `Remove` DISABLED for the rest of the session, which is
        the state WM.setEnabled is supposed to describe rather than
        outlive. Found by opening the real window; nothing in the suite
        renders the page, so it could not have been caught here.

        Returned rather than pushed, and only this one derived value
        rather than the document, so the fix cannot reintroduce the
        rewrite-while-typing bug the no-push rule exists to prevent.

        Only on an applied commit: a refusal changed nothing, so the line
        already on screen is still correct, and overwriting it would
        replace a description of what IS stored with one of what the user
        typed.
        """
        if not result["applied"]:
            return result
        return dict(
            result,
            webhook_status=copy_mod.webhook_status(
                self._state.settings.get("discord_webhook", "") or ""
            ),
        )

    def set_show_eve_tools(self, enabled) -> dict:
        """Show or hide the EVE destinations and sections.

        VISIBILITY ONLY. It never starts or stops anything: eve_bookmarks
        .enabled and preview.enabled stay the sole runtime switches.

        The guard is the whole design. Hiding a feature that is RUNNING
        would conceal its off switch -- previews would keep painting and
        eighteen global keybinds would keep firing in EVE, with no
        reachable control to stop them. Making this a kill switch instead
        was rejected: it would silently stop those from what reads as a
        display preference, and re-enabling could not know which of the two
        to restore without a third persisted value.

        So it simply refuses while either is on, and says which. Turning
        them off first is one extra step, and it is the honest order --
        that friction is what stops this being a kill switch by accident.
        """
        enabled = bool(enabled)
        if not enabled:
            running = []
            if self._state.settings.get("eve_bookmarks", {}).get("enabled"):
                running.append("Bookmarks")
            if self._state.settings.get("preview", {}).get("enabled"):
                running.append("Previews")
            if running:
                return self._field_refused(
                    "Turn off " + " and ".join(running) + " first — hiding "
                    "them here would leave them running with no way to "
                    "switch them off."
                )
        return self._write_setting("show_eve_tools", enabled)

    # ----- floating sig bar ---------------------------------------------

    def sig_bar_settings(self) -> dict:
        """The sig_bar section, for the bar page's one startup read.

        A copy, not the live dict: this crosses to JS, where a concurrent
        update_section rebuilding the section must not be observed
        half-written.
        """
        return dict(self._state.settings.get("sig_bar") or {})

    def _push_sig_bar_state(self) -> None:
        """Publish the whole sig_bar section after any change to it.

        The section, not a delta: the bar page restyles from it and the
        main page lights its toggle from `enabled`, and both are cheap.
        Fan-out through _push means no page is named here.
        """
        self._push("onSigBarState", self.sig_bar_settings())

    def toggle_sig_bar(self, on) -> dict:
        """Show or hide the floating sig bar, persisting the choice.

        The window is created on first enable and kept hidden afterwards
        (ui/sigbar.py's docstring holds the cost argument), so this only
        ever shows or hides -- except the first time, which builds it.
        """
        from wingman.ui import sigbar

        on = bool(on)
        settings_mod.update_section(self._state.settings, "sig_bar", {"enabled": on})
        bar = self._sigbar_window
        logger.info(
            "Sig bar toggle: requested %s, window %s.",
            on,
            "exists" if bar is not None else "not built yet",
        )
        try:
            if on:
                if bar is None:
                    sigbar.create(self, hidden=False)
                else:
                    bar.show()
                # The poll can be up to 3s away; a bar that opens empty for
                # 3s reads as broken. The page pulls nothing at load, so
                # this push is its content.
                self._push_eve_status()
            elif bar is not None:
                bar.hide()
        except Exception:
            # A bar that cannot appear is degraded chrome, not a failed
            # setting: the persisted choice stands and the next toggle
            # retries the window.
            logger.exception("sig bar window toggle failed")
        logger.info(
            "Sig bar toggle done: enabled=%s, visible=%s.",
            self._state.settings["sig_bar"]["enabled"],
            self._sig_bar_visible(),
        )
        self._push_sig_bar_state()
        return self._field_ok()

    def _sig_bar_visible(self):
        """Best-effort visibility readback, for the toggle log line only."""
        try:
            return bool(self._sigbar_window.native.Visible)
        except Exception:  # noqa: BLE001 -- logging only; any failure renders the same "unknown".
            return "unknown"

    def save_sig_bar_pos(self, x, y) -> None:
        """Persist the bar's last drag position. Fire-and-forget from JS.

        Called from the debounced moved handler in ui/sigbar.py, so this
        runs at most twice a second even across a long drag. No push: the
        bar is where it is, and the main page does not care.
        """
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return
        settings_mod.update_section(self._state.settings, "sig_bar", {"x": x, "y": y})

    def fit_sig_bar(self, width, height) -> None:
        """Resize the bar window to its content, as measured by the page.

        The page measures in CSS pixels and pywebview resizes in logical
        units -- the same units (see ui/window.py's placement notes), so
        the values are handed through unscaled.

        Verify-and-retry, not fire-and-forget: pywebview's resize is
        intermittently lost while the window is still materialising --
        reproduced, three correct resizes inside the first half-second all
        no-oped while the identical call at five seconds stuck. The page
        sends one fit per poll tick, so an unverified call could leave the
        bar at its broken birth size for the session. The caller is a
        per-call bridge thread, so parking here costs nothing else.
        """
        bar = self._sigbar_window
        if bar is None:
            return
        try:
            width, height = int(width), int(height)
        except (TypeError, ValueError):
            return
        if width <= 0 or height <= 0:
            return
        for _ in range(12):
            try:
                bar.resize(width, height)
            except Exception:
                # Before `shown`, resize can raise; the retry below is the
                # whole reason this loop exists.
                logger.debug("sig bar resize failed", exc_info=True)
            try:
                # +-1: logical->physical->logical round-trips through two
                # integer truncations, which drifts a pixel at fractional
                # scalings.
                if abs(bar.width - width) <= 1 and abs(bar.height - height) <= 1:
                    return
            except Exception:  # noqa: BLE001 -- no readable size (test doubles, headless): nothing to verify against, and the first call is then the whole contract.
                return
            time.sleep(0.25)
        logger.debug("sig bar resize never stuck at %sx%s", width, height)

    def set_folder(self, which: str, path: str) -> dict:
        """Persist one folder, and make the watcher match it.

        `which` mirrors pick_folder and detect_folder rather than inventing
        a second spelling for the same discriminator.

        This is also the only folder endpoint, which closes a hole that
        predates it. There used to be two: `set_recording_dir` could only
        CREATE a watcher (__main__'s start_watching returns early when a
        scheduler already exists) and `save_settings` could only REPOINT
        one (its rebind was guarded on _watcher being set). With _watcher
        None the folder persisted and _state.recording_dir was set --
        which un-gates list_rows, so the window looked healthy -- while
        nothing ever started polling. Both are gone; this handles both
        cases, and first run calls it too.
        """
        if which == "gamelogs":
            text = str(path or "").strip()
            # Unlike the recording folder this drives no watcher, and an
            # empty value legitimately means "no gamelogs folder".
            if text and not Path(text).is_dir():
                return self._field_refused("That folder does not exist.")
            result = self._write_setting("gamelogs_dir", text or None)
            # This IS the watcher this branch's docstring says it drives
            # none of: AlertService reads gamelogs_dir through the same
            # `folder` callable reconcile() re-evaluates, so a repointed
            # or newly-set folder is exactly the case that used to persist
            # while nothing ever polled it.
            if self._alerts is not None:
                self._alerts.reconcile()
            return result

        text = str(path or "").strip()
        if not text:
            # save_settings mapped empty to Path("None") and told the user
            # that "None is not a folder".
            return self._field_refused("Choose a recording folder.")
        folder = Path(text)
        if not folder.is_dir():
            return self._field_refused("That folder does not exist.")

        # Whichever way the user got here -- the first-run screen or
        # Settings -- naming a real folder settles the question the skip
        # deferred, so the flag stops applying. Cleared before the two
        # success paths below diverge, because both of them are "this
        # folder is now the answer". Its own write, and deliberately not
        # guarded: _write_setting is already a no-op when the value has
        # not changed, which is the common case by far.
        self._write_setting("first_run_skipped", False)

        if self._state.recording_dir == folder:
            # Already watching it. Returning before the rebind below is
            # what stops a re-commit of the same path re-baselining the
            # folder and swallowing recordings that arrived this session.
            return self._write_setting("recording_dir", str(folder))

        result = self._write_setting("recording_dir", str(folder))
        if not result["applied"]:
            return result

        self._state.recording_dir = folder
        if self._watcher is not None:
            # rebind() marks every file already in the folder as seen, so
            # switching folders does not announce a backlog as though it
            # had just been recorded.
            #
            # Counted BEFORE the rebind and only on this branch. Round 3's
            # B11 asked for the commit cost to be stated, and PRODUCT.md
            # wants the real number in it -- which no hint written before
            # the click can have, because it depends on what is in the
            # folder the user is about to name. This is the first moment
            # the number exists, so the disclosure is a report rather than
            # a warning. The other branch below cannot say the same thing:
            # start_watching() calls Watcher.baseline(), which silently
            # baselines only on a first-ever run and otherwise announces
            # what it finds, so "were not announced" would be a guess.
            #
            # A second walk of the folder rather than a count out of
            # rebind(): watcher.py is not this lane's file, and discover()
            # over one directory is the same work list_rows() does a few
            # lines below.
            suppressed = len(library.discover(folder))
            self._watcher.rebind(folder)
            result = dict(result, note=_folder_note(folder, suppressed))
        elif self._on_recording_dir_ready is not None:
            self._on_recording_dir_ready(folder)
        self.list_rows()
        return result

    def auth_labels(self) -> dict:
        """The whole account-state table, for the page to render from.

        Returned rather than pushed because it never changes: the page asks
        once at load and then only needs the `state` each onAuthState
        carries. Keeping the strings here keeps them under test, and stops
        the page growing a second copy that drifts.
        """
        return {
            state: {"message": message, "label": label, "enabled": enabled}
            for state, (message, label, enabled) in copy_mod.AUTH_STATES.items()
        }

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
        self._push(
            "onEveStatus",
            {
                "state": status.state,
                "sig": status.sig,
                "root": status.root,
                "next_num": status.next_num,
                "next_alpha": status.next_alpha,
                "failed_binds": status.failed_binds,
                # A failed start is otherwise invisible: this is the one
                # actionable thing the user can be told ("the engine is
                # missing, reinstall").
                "last_error": status.last_error,
            },
        )

    # ---- EVE client previews ------------------------------------------

    def start_previews_if_enabled(self) -> None:
        """Start the preview thread only if the user asked for it.

        Called on launch. Lazy on purpose: enabling costs a thread, a
        700ms discovery sweep and a foreground hook, and a user who never
        previews EVE clients should pay none of it.
        """
        if self._preview_host is None:
            if self._alerts is not None:
                self._alerts.reconcile()
            return
        section = self._state.settings.get("preview", {})
        # Pushed before start(): the first registration pass runs inside
        # start(), and a table applied only after it would leave every
        # binding unregistered until the next explicit save.
        self._preview_host.set_hotkeys(section.get("hotkeys") or {})
        if section.get("enabled"):
            self._preview_host.start()
        if self._alerts is not None:
            # After start(), not before: the folder callable __main__ wires
            # up gates on the host's live is_running, and reconciling
            # before start() would evaluate it against the pre-launch
            # state.
            self._alerts.reconcile()

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
        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg.setdefault("preview", {})["enabled"] = enabled
        except OSError:
            # Same posture as the channel persist above: a settings file
            # that cannot be written must not block the feature itself.
            logger.exception("Could not persist the preview setting")
        if self._preview_host is not None:
            if enabled:
                self._preview_host.start()
            else:
                self._preview_host.stop()
        if self._alerts is not None:
            # Alerts gate on preview.enabled through the `folder` callable
            # (decision: no previews, no polling thread), so a toggle here
            # is one of the five places that answer can change.
            self._alerts.reconcile()
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
        if self._preview_host is not None:
            try:
                self._preview_host.stop()
            except Exception:
                logger.exception("Preview host did not stop cleanly")
        if self._alerts is not None:
            # reconcile(), not a direct stop(): the folder callable
            # __main__ wires up gates on the host's live is_running, which
            # preview_host.stop() above has already flipped false, so this
            # is the same "no previews, no polling thread" answer every
            # other call site relies on -- run after the host teardown,
            # not before, or it would see the pre-shutdown state.
            try:
                self._alerts.reconcile()
            except Exception:
                logger.exception("Alert service did not stop cleanly")

    def capture_preview_bind(self, parts) -> dict:
        return preview_gestures.from_capture(parts if isinstance(parts, dict) else {})

    def parse_preview_bind(self, text) -> dict:
        parsed = preview_gestures.parse(text if isinstance(text, str) else "")
        if parsed is None:
            return {"gesture": "", "error": "unparseable"}
        return {"gesture": preview_gestures.display(parsed), "error": None}

    # ---- Preview hotkey private helpers (must run under _preview_hotkey_lock)

    def _preview_hotkeys(self) -> dict:
        """Deep copy of the current preview hotkeys table from settings."""
        return copy.deepcopy(
            self._state.settings.get("preview", {}).get("hotkeys") or {}
        )

    @staticmethod
    def _preview_group_result(applied, error, hotkeys) -> dict:
        """Build the standard group-operation result dict.

        Invariant: group operations persist before live host delivery, so
        ``persisted == applied`` always holds for this helper -- there is no
        partial state where the host has a change that was not also written
        to disk.
        """
        return {
            "applied": bool(applied),
            "persisted": bool(applied),
            "error": error,
            "hotkeys": copy.deepcopy(hotkeys),
        }

    def set_preview_binds(self, section) -> bool:
        """Replace the character keybinds and All-cycle chords, persist them,
        and push the full table to the host.

        Groups and group membership are left unchanged.

        Returns False on a chord that will not parse rather than silently
        dropping it: the page needs to tell a rejected entry from a saved
        one, and WM.send resolves to null on a bridge failure, so a bare
        None would be indistinguishable from a broken call.
        """
        if not isinstance(section, dict):
            return False
        table = {"characters": {}, "cycle_next": "", "cycle_prev": ""}
        characters = section.get("characters")
        if isinstance(characters, dict):
            for name, text in characters.items():
                if not isinstance(name, str) or name.startswith("hwnd:"):
                    return False
                if not text:
                    continue  # cleared, not invalid
                parsed = preview_gestures.parse(text)
                if parsed is None:
                    return False
                table["characters"][name] = preview_gestures.display(parsed)
        for key in ("cycle_next", "cycle_prev"):
            text = section.get(key)
            if not text:
                continue
            parsed = preview_gestures.parse(text)
            if parsed is None:
                return False
            table[key] = preview_gestures.display(parsed)

        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    hotkeys["characters"] = table["characters"]
                    hotkeys["cycle_next"] = table["cycle_next"]
                    hotkeys["cycle_prev"] = table["cycle_prev"]
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                return False
            applied = self._preview_hotkeys()
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(applied)
        return True

    def create_preview_cycle_group(self, name) -> dict:
        """Create a new named cycle group.

        Returns {applied, persisted, error, hotkeys}. The hotkeys field is
        the authoritative normalized table after the mutation.
        """
        if not isinstance(name, str) or not name.strip():
            # Acquire the writer lock before reading so the refusal table
            # reflects the authoritative post-commit (or post-rollback) state
            # rather than a transient mutation from a concurrent writer.
            with self._preview_hotkey_lock:
                empty = self._preview_hotkeys()
            return self._preview_group_result(
                False, "Group name must be a non-empty string", empty
            )
        clean_name = name.strip()
        folded = clean_name.casefold()
        new_id = self._id_factory()
        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    # Enforce unique case-insensitive name and unique ID.
                    groups = hotkeys.setdefault("groups", [])
                    for g in groups:
                        if g.get("name", "").casefold() == folded:
                            raise ValueError(
                                f"A group named {clean_name!r} already exists"
                            )
                    if any(g.get("id") == new_id for g in groups):
                        raise ValueError(f"ID collision for {new_id!r}")
                    groups.append({"id": new_id, "name": clean_name, "cycle": ""})
            except ValueError as exc:
                current = self._preview_hotkeys()
                return self._preview_group_result(False, str(exc), current)
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                current = self._preview_hotkeys()
                return self._preview_group_result(False, "Persist error", current)
            result_table = self._preview_hotkeys()
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(result_table)
        return self._preview_group_result(True, None, result_table)

    def rename_preview_cycle_group(self, group_id, name) -> dict:
        """Rename an existing cycle group by its stable ID.

        Returns {applied, persisted, error, hotkeys}.
        """
        if not isinstance(group_id, str) or not group_id:
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(False, "Invalid group_id", current)
        if not isinstance(name, str) or not name.strip():
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(
                False, "Group name must be a non-empty string", current
            )
        clean_name = name.strip()
        folded = clean_name.casefold()
        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    groups = hotkeys.setdefault("groups", [])
                    target = next((g for g in groups if g.get("id") == group_id), None)
                    if target is None:
                        raise ValueError(f"No group with id {group_id!r}")
                    for g in groups:
                        if g is not target and g.get("name", "").casefold() == folded:
                            raise ValueError(
                                f"A group named {clean_name!r} already exists"
                            )
                    target["name"] = clean_name
            except ValueError as exc:
                current = self._preview_hotkeys()
                return self._preview_group_result(False, str(exc), current)
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                current = self._preview_hotkeys()
                return self._preview_group_result(False, "Persist error", current)
            result_table = self._preview_hotkeys()
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(result_table)
        return self._preview_group_result(True, None, result_table)

    def delete_preview_cycle_group(self, group_id) -> dict:
        """Delete a cycle group and remove all character memberships.

        Returns {applied, persisted, error, hotkeys}.
        """
        if not isinstance(group_id, str) or not group_id:
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(False, "Invalid group_id", current)
        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    groups = hotkeys.setdefault("groups", [])
                    orig_len = len(groups)
                    hotkeys["groups"] = [g for g in groups if g.get("id") != group_id]
                    if len(hotkeys["groups"]) == orig_len:
                        raise ValueError(f"No group with id {group_id!r}")
                    mapping = hotkeys.setdefault("group_by_character", {})
                    hotkeys["group_by_character"] = {
                        name: gid for name, gid in mapping.items() if gid != group_id
                    }
            except ValueError as exc:
                current = self._preview_hotkeys()
                return self._preview_group_result(False, str(exc), current)
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                current = self._preview_hotkeys()
                return self._preview_group_result(False, "Persist error", current)
            result_table = self._preview_hotkeys()
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(result_table)
        return self._preview_group_result(True, None, result_table)

    def set_preview_cycle_group_bind(self, group_id, gesture) -> dict:
        """Set the cycle keybind for a named group.

        Returns {applied, persisted, error, hotkeys}. Empty gesture clears
        the bind. A non-empty string that does not parse is refused.
        """
        if not isinstance(group_id, str) or not group_id:
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(False, "Invalid group_id", current)
        if not isinstance(gesture, str):
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(
                False, "gesture must be a string", current
            )
        canonical = ""
        if gesture.strip():
            parsed = preview_gestures.parse(gesture)
            if parsed is None:
                with self._preview_hotkey_lock:
                    current = self._preview_hotkeys()
                return self._preview_group_result(
                    False, f"Unparseable gesture: {gesture!r}", current
                )
            canonical = preview_gestures.display(parsed)
        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    groups = hotkeys.setdefault("groups", [])
                    target = next((g for g in groups if g.get("id") == group_id), None)
                    if target is None:
                        raise ValueError(f"No group with id {group_id!r}")
                    target["cycle"] = canonical
            except ValueError as exc:
                current = self._preview_hotkeys()
                return self._preview_group_result(False, str(exc), current)
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                current = self._preview_hotkeys()
                return self._preview_group_result(False, "Persist error", current)
            result_table = self._preview_hotkeys()
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(result_table)
        return self._preview_group_result(True, None, result_table)

    def set_preview_character_group(self, name, group_id) -> dict:
        """Assign a character to a cycle group, or remove the assignment.

        An empty group_id removes the character from its group (All-only).
        Returns {applied, persisted, error, hotkeys}.
        Uses the same stable-name boundary as other preview APIs.
        """
        if not self._usable_preview_character(name):
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(
                False, f"Invalid character name: {name!r}", current
            )
        if not isinstance(group_id, str):
            with self._preview_hotkey_lock:
                current = self._preview_hotkeys()
            return self._preview_group_result(
                False, "group_id must be a string", current
            )
        with self._preview_hotkey_lock:
            try:
                with settings_mod.update(self._state.settings) as cfg:
                    hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
                    mapping = hotkeys.setdefault("group_by_character", {})
                    if group_id == "":
                        mapping.pop(name, None)
                    else:
                        groups = hotkeys.setdefault("groups", [])
                        valid_ids = {g.get("id") for g in groups}
                        if group_id not in valid_ids:
                            raise ValueError(f"No group with id {group_id!r}")
                        mapping[name] = group_id
            except ValueError as exc:
                current = self._preview_hotkeys()
                return self._preview_group_result(False, str(exc), current)
            except OSError:
                logger.exception("Could not persist preview hotkeys")
                current = self._preview_hotkeys()
                return self._preview_group_result(False, "Persist error", current)
            result_table = self._preview_hotkeys()
            # Finding 2: the normalizer enforces a 64-entry roster cap on
            # group_by_character.  If the assignment was silently discarded,
            # the operation did not really apply; refuse it truthfully and do
            # not deliver a table that claims the dropped assignment to the host.
            if group_id and name not in result_table.get("group_by_character", {}):
                return self._preview_group_result(
                    False,
                    f"Roster cap reached; {name!r} was not assigned to {group_id!r}",
                    result_table,
                )
            if self._preview_host is not None:
                self._preview_host.set_hotkeys(result_table)
        return self._preview_group_result(True, None, result_table)

    def set_bind_capture(self, armed) -> bool:
        """Tell the preview host a bind row is waiting for a keystroke.

        Returns rather than pushes, and the page WAITS for it before it
        invites the key: a chord that is already registered is delivered
        to the preview window as WM_HOTKEY and never reaches this page at
        all, so a press landing before this call took effect would switch
        clients -- and take the foreground away from the window being
        typed into -- instead of being captured.

        True is "the host knows", not "the key will arrive here": an
        unregistered chord still comes through the page's own keydown
        listener, which is the path that always worked.
        """
        if self._preview_host is None:
            return False
        self._preview_host.set_capture(bool(armed))
        return True

    def push_bind_captured(self, gesture) -> None:
        """A registered chord, redirected to the armed bind row."""
        self._push("onPreviewBindCaptured", {"gesture": gesture})

    def _preview_layout_entries(self) -> dict:
        """Latest valid layouts, including the host's undebounced state."""
        host = self._preview_host
        if host is not None:
            return {
                name: entry
                for name, entry in host.layout_entries().items()
                if self._usable_preview_character(name)
            }
        section = self._state.settings.get("preview", {})
        return {
            name: entry
            for name, entry in preview_layout.deserialize(
                section.get("layouts")
            ).items()
            if self._usable_preview_character(name)
        }

    def get_preview_hotkey_state(self) -> dict:
        """Everything the bind list needs, in one read.

        A read, not a push, and that is the point: previews start before the
        webview exists (__main__.py:476-478), so a registration conflict
        found at launch is pushed into a window that is not there yet and
        _push swallows it. The page asks for this on load.
        """
        section = self._state.settings.get("preview", {})
        host = self._preview_host
        # is_running, not merely "host is not None": there is a window
        # between stop() clearing the thread handle and _teardown running
        # on the preview thread itself where the host object still exists
        # but owns no chords and no windows. Gating on is_running closes
        # it -- a stopped host reports the same empty state as no host at
        # all, rather than serving whatever characters()/hotkey_status()
        # last held.
        live = host is not None and host.is_running
        online = set(host.characters() if live else [])
        layout_sources = [
            {"name": name, "online": name in online if live else None}
            for name in sorted(
                self._preview_layout_entries(),
                key=lambda name: (name not in online, name.casefold(), name),
            )
        ]
        return {
            "enabled": bool(section.get("enabled")),
            "hotkeys": dict(section.get("hotkeys") or {}),
            "roster": list(section.get("seen") or []),
            "characters": host.characters() if live else [],
            "registration": host.hotkey_status() if live else {},
            "bookmark_chords": self._bookmark_chords(),
            # Character-name lists, not per-character booleans -- see
            # PreviewHost._is_locked/_is_never_minimize and
            # set_preview_locked/set_never_minimize below. The per-character
            # table needs these to paint its two new checkboxes; riding this
            # payload (rather than a second round trip) keeps row state in
            # the one place previews.js already reads it from.
            "locked": list(section.get("locked") or []),
            # What a character NOT in `locked` is. The page needs it to
            # paint the row's box, because with this on the list holds the
            # characters that are UNlocked -- reading membership alone
            # would show every box inverted. previews.js resolves the pair
            # the same way PreviewHost._is_locked does.
            "lock_default": bool(section.get("lock_default")),
            "never_minimize": list(section.get("never_minimize") or []),
            # The third of the same kind: characters opted out of previews
            # entirely. Rides this payload rather than a second round trip
            # for the same reason the other two do -- row state belongs in
            # the one place previews.js already reads it from.
            "excluded": list(section.get("excluded") or []),
            # Sizes for the Size... dialog: what the preview is now, and
            # what its client's shape is, so the page can name the size
            # that would not distort it. client_sizes is sampled on the
            # preview thread (host._record_client_sizes) precisely so the
            # bridge thread never touches an HWND.
            "sizes": self._preview_sizes(),
            "client_sizes": host.client_sizes() if live else {},
            # Saved geometry sources are separate from row targets: old
            # settings may retain a valid offline layout after its roster entry
            # aged out, and that geometry is still useful to copy.
            "layout_sources": layout_sources,
            # Which characters set_preview_size can actually succeed for.
            #
            # It refuses outright for a character that is neither running
            # nor already in `layouts` -- there is no x/y to write, and
            # layout.deserialize drops an entry without a full rect, so a
            # w/h saved alone would vanish at the next load after the page
            # had already reported it accepted. That refusal is correct and
            # stays; what was wrong was offering the control anyway.
            #
            # A layouts entry is written when a preview is DRAGGED or
            # RESIZED (window.py's WM_LBUTTONUP -> host._layout_changed),
            # not merely when a client runs. So on a fresh install every
            # offline character fails this, which on a typical roster is
            # most of the list -- eleven of thirteen in the report this
            # came from. previews.js renders Size... only for names in
            # here, which is D6's rule (do not draw a control in the state
            # where it can do nothing) applied to the column that needed
            # it most.
            "sizable": sorted(
                set(host.characters() if live else [])
                | set((section.get("layouts") or {}).keys())
            ),
        }

    def _bookmark_chords(self) -> dict:
        """Bookmark chords, split by whether they are registered right now.

        A preview chord is global; a bookmark chord is an AHK hotkey scoped
        with #HotIf WinActive. Where they collide the preview wins WHILE EVE
        IS FOCUSED, silently taking a key from the feature that bind was
        written for -- and Windows reports nothing, because AHK's scoped
        hotkey is not a RegisterHotKey registration to collide with. Only
        Wingman can catch this, by reading both of its own sections.

        Split rather than filtered, because the collision does not stop
        existing when bookmarks are off -- it goes latent, and enabling them
        later resurrects it with nothing on screen to explain why that bind
        stopped working. "active" warns; "latent" only marks.

        Compared in display form. The two features store different notation
        on purpose (see preview/gestures.py), but bookmarks.parse_ahk
        renders "^q" as "Ctrl+Q" using the same modifier order and key names
        gestures.display uses, so the display string is the common ground.
        """
        eve = self._state.settings.get("eve_bookmarks") or {}
        chords = set()
        for value in (eve.get("keybinds") or {}).values():
            if not value:
                continue
            rendered = bookmarks.parse_ahk(value).get("display")
            if rendered:
                chords.add(rendered)
        live = bool(eve.get("enabled")) and any(eve.get("windows", {}).values())
        return {
            "active": sorted(chords) if live else [],
            "latent": [] if live else sorted(chords),
        }

    def push_preview_hotkeys(self, status=None) -> None:
        """Announce a change to a page that is already up. Never the only
        path -- see get_preview_hotkey_state."""
        payload = self.get_preview_hotkey_state()
        if status is not None:
            payload["registration"] = status
        self._push("onPreviewHotkeys", payload)

    # ---- Preview settings, generic writer --------------------------------

    def _write_preview_setting(self, path: tuple, value) -> dict:
        """Persist one value under `preview`, no-op guarded.

        `_write_setting` (above) cannot reach here: it only ever does
        `doc[key] = value` against the top-level document, and this needs
        to land under `preview` (or, via `_write_alert_setting` below,
        `preview.alerts`) instead. This follows set_restore_preview_
        positions's shape for the write itself -- descend through `doc.
        setdefault(...)` inside `settings_mod.update`, so the mutation
        happens under `_SAVE_LOCK` -- generalised to an arbitrary path so
        one writer covers every preview field instead of being copied for
        each.

        A raise here is reported as refused (`applied: False`), not as
        `applied: True, persisted: False`: settings_mod.update restores
        the live dict on OSError, so the value genuinely did NOT take
        effect for this session either -- `applied: True` would tell the
        page a change is live that never happened, and a checkbox or
        select left showing it would be showing a state the app is not
        in.

        `path` is walked fresh against `self._state.settings` both for the
        no-op check and inside the `update()` block, never against a
        `preview` reference held across the call: `_normalize` reassigns
        `preview` wholesale on every write (settings.py:373-378), so a
        reference captured before `update()` is stale by the time it
        returns.
        """
        node = self._state.settings.get("preview", {})
        for key in path[:-1]:
            node = node.get(key, {})
        if node.get(path[-1]) == value:
            # Same rationale as _write_setting's no-op guard: a save
            # projects the complete document, so this would otherwise be a
            # full rewrite for a value that has not changed.
            return self._field_ok()
        try:
            with settings_mod.update(self._state.settings) as doc:
                node = doc.setdefault("preview", {})
                for key in path[:-1]:
                    node = node.setdefault(key, {})
                node[path[-1]] = value
        except OSError:
            logger.exception("Could not persist preview setting %s", ".".join(path))
            return self._field_refused("Could not save this to settings.")
        return self._field_ok()

    def set_preview_show_labels(self, enabled) -> dict:
        """Persist whether preview thumbnails show their character-name
        label, then push it live onto every open preview via
        PreviewHost.restyle() -- the page must not wait for the next
        placement or restart to see it."""
        result = self._write_preview_setting(("show_labels",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def parse_preview_size(self, text) -> dict:
        """Validate a typed "1280x720", mirroring parse_preview_bind.

        The page sends the raw string rather than parsing it, so the one
        definition of what a size looks like stays in a pure module CI can
        test -- web/*.js is never executed by anything in the suite.
        """
        parsed = preview_geometry.parse_size(text)
        if parsed is None:
            return {"w": 0, "h": 0, "error": "Sizes look like 1280x720."}
        return {"w": parsed[0], "h": parsed[1], "error": None}

    def set_preview_snap(self, enabled) -> dict:
        """Persist whether a dragged preview snaps to its neighbours and the
        screen edges, then push it live via PreviewHost.restyle() -- snap is
        read per mouse-move, so the live PreviewWindow.snap has to be
        refreshed or the checkbox would do nothing until restart."""
        result = self._write_preview_setting(("snap",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_lock_aspect(self, enabled) -> dict:
        """Persist whether the drag handle holds the client's shape, then
        push it live via PreviewHost.restyle().

        Live-pushed for the same reason as snap: PreviewWindow reads the
        flag when a drag begins, so a write that only touched settings
        would leave the checkbox inert until the next launch.

        Unchecked, the handle resizes freely and DWM stretches the picture
        to whatever rectangle it is given -- it does NOT letterbox, which
        is measured in docs/preview-sizing-design.md. That is the cost the
        hint names, and it is the same cost a mismatched typed size in
        Size... has always carried; this only makes that escape hatch
        reachable from the handle.
        """
        result = self._write_preview_setting(("lock_aspect",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_hide_on_lost_focus(self, enabled) -> dict:
        """Persist whether every preview leaves the screen while the
        foreground belongs to neither an EVE client nor Wingman, then push
        it live via PreviewHost.restyle().

        TriffView's HideOnLostFocus, which is EVE-O Preview's
        HideThumbnailsOnLostFocus. PreviewHost._apply_visibility applies it
        and preview/visibility.py owns the predicate; nothing about the
        decision lives here.

        Two consequences worth knowing before reading a bug report about
        this. Alerts are hidden along with everything else -- an alert
        raised while you are in a browser is not seen until you come back,
        and only survives that long because preview.alerts
        persist_until_selected defaults on. And Wingman's own window does
        NOT count as lost focus, deliberately: the previews would otherwise
        vanish the moment you opened the screen that arranges them.

        Restyle for the same reason as snap and lock_aspect, though by a
        different route -- restyle re-runs the visibility pass, so
        unticking puts the previews back immediately instead of up to one
        700ms sweep later.
        """
        result = self._write_preview_setting(("hide_on_lost_focus",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_lock_default(self, enabled) -> dict:
        """Persist whether a character not named in `preview.locked` is
        locked anyway, then push it live via PreviewHost.restyle().

        This makes `locked` a list of EXCEPTIONS rather than a list of
        locked characters; PreviewHost._is_locked resolves the pair, and
        that one line is the only place the two are combined.

        Restyle for the same reason as snap and lock_aspect: a live
        PreviewWindow holds a resolved `locked` flag, so a write that only
        touched settings would leave every open preview at its old lock
        until the next launch.

        Flipping this flips every character NOT in the list, which is what
        a default means and is what the field's hint says. It is not a
        migration and does not rewrite the roster: the list keeps meaning
        "these differ from the default".

        That is not the same as being reversible, and the difference is
        worth stating because the obvious reading is wrong. Untick-after-
        tick restores the previous arrangement ONLY if no per-character
        box was touched in between. Tick the default with an empty roster,
        unlock one character (so they become the exception), then untick:
        that character is now the only LOCKED one. The roster was never
        rewritten -- the user changed it, meaning the opposite thing each
        side of the flip.
        """
        result = self._write_preview_setting(("lock_default",), bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_default_size(self, w, h) -> dict:
        """Persist the size an unsaved preview opens at.

        `preview.width`/`height` are not new -- they have fed
        geometry.default_stack since previews shipped -- but they had no
        user interface, so the only way to change them was to edit
        settings.json by hand. This is that interface.

        Validated exactly like set_preview_size, against the same
        preview_window.MIN_SIZE floor, because they are the same kind of
        value and a default the per-character control would refuse is a
        default that cannot be honoured.

        No restyle: this does not change any window that is already open.
        It decides where the NEXT unsaved preview is placed, and
        build_preview_host now reads it live, so nothing has to be pushed.

        Both keys are written in ONE `settings_mod.update` block rather
        than through two `_write_preview_setting` calls. They are a pair
        everywhere they are read -- geometry.default_stack takes one tuple
        -- and two calls can half-succeed: `update` restores the live dict
        on OSError, so a failed second write leaves the first one applied
        and persisted while this method reports `applied: False` and the
        page reverts its field. The user would then see the old pair over
        a preview section holding a new width and an old height.
        """
        try:
            width, height = int(w), int(h)
        except (TypeError, ValueError):
            return self._field_refused("Sizes look like 1280x720.")
        floor_w, floor_h = preview_window.MIN_SIZE
        if width < floor_w or height < floor_h:
            return self._field_refused(f"The smallest preview is {floor_w}x{floor_h}.")
        section = self._state.settings.get("preview", {})
        if section.get("width") == width and section.get("height") == height:
            # Same no-op guard every other preview write carries: a save
            # projects the complete document, so an unchanged pair would
            # otherwise be a full rewrite.
            return self._field_ok()
        try:
            with settings_mod.update(self._state.settings) as doc:
                node = doc.setdefault("preview", {})
                node["width"] = width
                node["height"] = height
        except OSError:
            logger.exception("Could not persist the default preview size")
            return self._field_refused("Could not save this to settings.")
        return self._field_ok()

    def apply_preview_default_size(self) -> dict:
        """Resize every OPEN preview to the persisted default size.

        The companion to set_preview_default_size, which by design changes
        only where the NEXT unsaved preview opens. This closes that gap:
        the field sets the default, this button applies it to what is on
        screen now.

        No arguments, and no re-validation: the width/height pair is read
        from settings, which validated_preview has already floored at
        MIN_SIZE -- accepting a size here that set_preview_default_size
        would refuse would let the page and the windows disagree.
        """
        host = self._preview_host
        if host is None or not host.is_running:
            return self._field_refused("Start previews first.")
        section = self._state.settings.get("preview", {})
        host.resize_all((section.get("width"), section.get("height")))
        # The cards show each character's size; every one just changed.
        self.push_preview_hotkeys()
        return self._field_ok()

    def set_preview_size(self, name, w, h) -> dict:
        """Persist one preview's size, and apply it live if that client is running.

        Three cases, and the third is the awkward one:

          running        -> resized now; the host records the new rect
          saved, offline -> the stored entry's w/h are rewritten in place
          neither        -> refused, because there is no x/y to write

        The third cannot be repaired by inventing coordinates.
        layout.deserialize drops any entry missing a full rect
        (preview/layout.py), so a w/h written without an x/y is discarded at
        the next load -- silently, after the page has already reported the
        size as accepted.
        """
        try:
            width, height = int(w), int(h)
        except (TypeError, ValueError):
            return self._field_refused("Sizes look like 1280x720.")
        floor_w, floor_h = preview_window.MIN_SIZE
        if width < floor_w or height < floor_h:
            return self._field_refused(f"The smallest preview is {floor_w}x{floor_h}.")
        host = self._preview_host
        if host is not None and host.is_running and name in host.characters():
            host.resize_preview(name, (width, height))
            return self._field_ok()
        layouts = self._state.settings.get("preview", {}).get("layouts") or {}
        if name not in layouts:
            return self._field_refused(
                "Start this client once, or drag its preview, before setting a size."
            )
        entry = dict(layouts[name])
        entry["w"], entry["h"] = width, height
        result = self._write_preview_setting(("layouts", name), entry)
        if result["applied"] and host is not None:
            host.sync_layout(
                name,
                preview_layout.Entry(
                    preview_geometry.Rect(
                        int(entry["x"]), int(entry["y"]), width, height
                    ),
                    bool(entry.get("locked", False)),
                ),
            )
        return result

    @staticmethod
    def _usable_preview_character(name) -> bool:
        return isinstance(name, str) and bool(name) and not name.startswith("hwnd:")

    def _preview_known_characters(self) -> set:
        """Names that can produce a target row on the Previews page."""
        section = self._state.settings.get("preview", {})
        names = set(section.get("seen") or []) | set(
            (section.get("hotkeys") or {}).get("characters") or {}
        )
        host = self._preview_host
        if host is not None and host.is_running:
            names |= set(host.characters())
        return {name for name in names if self._usable_preview_character(name)}

    def copy_preview_layout(self, target, source) -> dict:
        """Copy only a saved preview rectangle from source to target."""
        if (
            target == source
            or not self._usable_preview_character(target)
            or not self._usable_preview_character(source)
        ):
            return self._field_refused("Choose two different characters.")
        if target not in self._preview_known_characters():
            return self._field_refused("That target character is no longer available.")

        host = self._preview_host
        if host is not None:
            outcome = host.copy_layout(target, source)
            if outcome == preview_host_mod.COPY_PERSIST_FAILED:
                return self._field_refused("Could not save this to settings.")
            if outcome != preview_host_mod.COPY_OK:
                return self._field_refused(
                    "That saved preview placement is no longer available."
                )
            return self._field_ok()

        section = self._state.settings.get("preview", {})
        entries = preview_layout.deserialize(section.get("layouts"))
        source_entry = entries.get(source)
        if source_entry is None:
            return self._field_refused(
                "That saved preview placement is no longer available."
            )
        target_entry = entries.get(target)
        copied = preview_layout.Entry(
            source_entry.rect,
            target_entry.locked if target_entry is not None else False,
        )
        raw = preview_layout.serialize({target: copied})[target]
        return self._write_preview_setting(("layouts", target), raw)

    def reset_preview_layouts(self) -> dict:
        """Forget every saved preview position and size.

        Goes through the host when one is running so the open windows move
        too; falls back to clearing settings directly so a reset with
        previews switched off still takes effect at the next launch.

        The two branches do NOT make equally strong promises, and the
        difference is structural rather than an oversight. The offline
        branch writes here, so it catches OSError and refuses. The running
        branch only POSTS: LayoutStore.clear() does the write later on the
        preview thread and swallows OSError with a log line, and
        settings.update() restores the live dict on any exception. So a
        settings file that cannot be written leaves the windows moved to
        their defaults on screen while the saved layouts survive in memory
        and on disk, after this has already reported persisted: True.

        Reported that way anyway, because the bridge has no round trip to
        learn the outcome and a drag makes no stronger claim -- the same
        optimism _apply_resizes documents for a resize whose window has
        gone. It fails in the safe direction: the positions are kept, not
        lost, and reappear at the next launch. Closing it properly means
        giving the host a way to answer, which is a larger change than the
        failure justifies.
        """
        if self._preview_host is not None and self._preview_host.is_running:
            self._preview_host.reset_layouts()
            return self._field_ok()
        try:
            with settings_mod.update(self._state.settings) as doc:
                doc.setdefault("preview", {})["layouts"] = {}
        except OSError:
            logger.exception("Could not clear preview layouts")
            return self._field_refused("Could not save this to settings.")
        if self._preview_host is not None:
            self._preview_host.clear_layout_entries()
        self.push_preview_hotkeys()
        return self._field_ok()

    def _preview_sizes(self) -> dict:
        """Saved window size per character, for the Size... dialog's default.

        Read from settings rather than from the host so an offline character
        still reports the size it will open at.

        A character only gets a layout entry once _layout_changed has fired
        -- on drag, or on a prior Size... commit -- so a preview that has
        never been moved has no entry at all, and Reset previews empties
        every entry at once. Such a character falls back to
        (preview.width, preview.height): the same pair __main__.py hands
        PreviewHost's size= and the one every unsaved preview is actually
        placed at. Without this the dialog opened on an empty field and the
        hint quoted a hardcoded 640 that matched nothing on screen.

        The fallback is offered for every name the row list can show --
        running (host.characters()) and known offline (section["seen"]) --
        not only names already in layouts, since those are exactly the rows
        with no entry to read from in the first place.
        """
        section = self._state.settings.get("preview", {})
        default = [section.get("width", 320), section.get("height", 210)]
        layouts = section.get("layouts") or {}
        out = {}
        for name, entry in layouts.items():
            try:
                out[name] = [int(entry["w"]), int(entry["h"])]
            except (KeyError, TypeError, ValueError):
                continue
        host = self._preview_host
        names = set(section.get("seen") or [])
        if host is not None and host.is_running:
            names |= set(host.characters())
        for name in names:
            out.setdefault(name, list(default))
        return out

    def set_preview_opacity(self, value) -> dict:
        """Persist the DWM thumbnail opacity, then push it live.

        Deliberately does NOT clamp here: settings.validated_preview
        already owns the 20-255 range (settings.py:235-239), and letting
        update()'s normalise pass apply it keeps that the one place the
        range is defined -- same reasoning as set_alert_event's docstring
        for cooldown_s/pulses. A value outside the range is
        silently coerced by normalise rather than refused here.
        """
        result = self._write_preview_setting(("opacity",), value)
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_selection_color(self, value) -> dict:
        """Persist the selection ring's colour, then push it live.

        The hex string is stored verbatim and validated by
        validated_preview's _HEX_RE screen -- same division of labour as
        set_preview_opacity: the setter does not re-own the format, and a
        value the screen rejects falls back to the default colour rather
        than being refused here.
        """
        result = self._write_preview_setting(("selection_color",), str(value))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_minimize_inactive_clients(self, enabled) -> dict:
        """Persist whether an inactive EVE client's preview minimizes
        itself, then push it live via restyle() -- read per switch, not
        per window (host.py's restyle() docstring), but the flag itself
        still has to reach the host before the next switch sees it."""
        result = self._write_preview_setting(
            ("minimize_inactive_clients",), bool(enabled)
        )
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def _toggle_preview_roster(self, key: str, name: str, member: bool) -> dict:
        """Add or remove *name* from the character-name list at
        preview.<key> (locked, never_minimize or excluded), then persist through
        _write_preview_setting.

        A list, not a per-character flag: Task 1 moved lock storage out of
        preview.layouts precisely because that entry is dropped whenever it
        is missing a full rect (preview/layout.py's deserialize), which is
        exactly what a character who has never dragged their preview looks
        like. never_minimize needs the same shape for the same reason --
        both are read by PreviewHost as membership tests
        (_is_locked/_is_never_minimize), never by key lookup.

        Shared by set_preview_locked, set_never_minimize and
        set_preview_excluded below rather than duplicated: the
        add/remove-by-name logic is identical, only the settings key
        differs -- and what each caller does AFTERWARDS does not, which is
        why the live-update call stays with the caller rather than moving
        in here (two restyle, one sweeps and rebinds).
        """
        current = list(self._state.settings.get("preview", {}).get(key) or [])
        if member:
            if name not in current:
                current.append(name)
        else:
            current = [n for n in current if n != name]
        return self._write_preview_setting((key,), current)

    def set_preview_locked(self, name, locked) -> dict:
        """Persist whether *name*'s preview is locked against drag, then
        push it live via PreviewHost.restyle() -- lock is read per drag
        (preview/window.py), so the live PreviewWindow.locked has to be
        refreshed or the checkbox would do nothing until restart.

        `locked` is the EFFECTIVE state the caller wants, not membership of
        the roster. Since `preview.lock_default` landed the list holds
        characters that DIFFER from the default, so membership is the
        exclusive-or -- and computing it here rather than on the page keeps
        the rule beside PreviewHost._is_locked, which has to agree with it.
        With lock_default off (the shipped default) the expression is
        `bool(locked)` and this method behaves exactly as it always has.
        """
        section = self._state.settings.get("preview", {})
        member = bool(locked) != bool(section.get("lock_default"))
        result = self._toggle_preview_roster("locked", name, member)
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_never_minimize(self, name, enabled) -> dict:
        """Persist whether *name* is exempt from minimize_inactive_clients,
        then push it live via restyle() -- same reasoning as
        set_preview_locked above."""
        result = self._toggle_preview_roster("never_minimize", name, bool(enabled))
        if self._preview_host is not None:
            self._preview_host.restyle()
        return result

    def set_preview_excluded(self, name, excluded) -> dict:
        """Persist whether *name* is opted out of previews entirely.

        Not restyle(), unlike the two above: restyle only re-reads style on
        windows that already exist, and this setting decides whether the
        window exists at all. request_sweep() is what creates or destroys
        it -- _sweep filters its desired set on the same list.

        set_hotkeys re-pushes the CURRENT table unchanged. That looks like
        a no-op and is not: the focus keybind is filtered out at
        registration time (PreviewHost._registerable), and ticking this box
        edits no chord, so without a rebind the opted-out character would
        keep its registration until the next unrelated bind edit.

        request_rebind() rather than set_hotkeys() for that, though, and
        the difference is not cosmetic: set_hotkeys would mean reading the
        table back out of settings here and pushing it, and pywebview
        serves each JS call on its own thread. A set_preview_binds landing
        between that read and that push would be silently reverted inside
        the host -- page and settings file holding the new table while the
        host stayed registered against the old one, with nothing logged.
        A payload-free rebind has nothing to revert.
        """
        result = self._toggle_preview_roster("excluded", name, bool(excluded))
        if self._preview_host is not None:
            self._preview_host.request_sweep()
            self._preview_host.request_rebind()
        return result

    # ---- Gamelog alerts --------------------------------------------------

    def _write_alert_setting(self, path: tuple, value) -> dict:
        """Persist one value under preview.alerts, no-op guarded.

        A thin wrapper over `_write_preview_setting`, prefixing the path
        with `alerts` so there is one writer for everything nested under
        `preview`, not two. See that docstring for the no-op guard, the
        `_SAVE_LOCK` mutation shape, the `applied: False` rationale on a
        raise, and why `path` must be walked fresh rather than against a
        `preview`/`alerts` reference held across the call.
        """
        return self._write_preview_setting(("alerts", *path), value)

    def set_alert_enabled(self, enabled) -> dict:
        """Turn the gamelog alert poller on or off."""
        result = self._write_alert_setting(("enabled",), bool(enabled))
        if self._alerts is not None:
            # One of the five places reconcile() must run from: alerts
            # gate on this flag (composed with the preview/folder state in
            # the `folder` callable __main__ wires up), so this toggle is
            # exactly the case that can change AlertService._wanted()'s
            # answer.
            self._alerts.reconcile()
        return result

    def set_alert_pve_filter(self, enabled) -> dict:
        """Suppress alerts that look like NPC fire rather than a player's.

        Read live by the poll thread through the same config callable on
        its next tick -- no reconcile() needed, this cannot change whether
        the thread itself should run.
        """
        return self._write_alert_setting(("pve_filter",), bool(enabled))

    def set_alert_persist(self, enabled) -> dict:
        """Keep an alert pulsing until its preview is selected, rather
        than only for its configured duration."""
        return self._write_alert_setting(("persist_until_selected",), bool(enabled))

    def set_alert_volume(self, value) -> dict:
        """Persist how loud every alert sound is, 0-100.

        Read live by the poll thread through the same config callable on
        its next alert -- no reconcile() and no push: nothing is playing
        between two alerts, so there is no live state to correct.

        Deliberately does NOT clamp here, matching set_preview_opacity and
        set_alert_event: settings.validated_alerts owns the 0-100 range,
        in one place.
        """
        return self._write_alert_setting(("volume",), value)

    def set_alert_event(self, event, field, value) -> dict:
        """Persist one field of one event's alert spec.

        Refuses an unknown event or field outright. settings.validated_
        alerts iterates alert_patterns.EVENTS on load, so an unknown event
        would be silently dropped on the next normalise anyway -- refusing
        here tells the page immediately instead of on the next restart.

        Deliberately does NOT clamp cooldown_s/pulses or validate
        color/sound/flash_rate itself: settings.validated_alerts already
        owns those ranges, and letting `update()`'s normalise pass apply
        them keeps that the one place they are defined. A rejected value
        is silently dropped by normalise rather than reported here, which
        matches how every other clamped field in this file already
        behaves (e.g. set_folder never separately re-validates what
        settings._normalize will coerce).
        """
        if event not in alert_patterns.EVENTS:
            return self._field_refused(f"Unknown alert event: {event}")
        if field not in _ALERT_EVENT_FIELDS:
            return self._field_refused(f"Unknown alert field: {field}")
        if field == "enabled":
            value = bool(value)
        return self._write_alert_setting(("events", event, field), value)

    def test_alert(self, event) -> dict:
        """Fire one alert manually on every currently previewed character,
        bypassing cooldowns entirely. Reaches the host directly rather
        than through AlertService: the service owns the poll path, and
        Test is not a poll.

        NEVER persistent, regardless of persist_until_selected -- always
        `persisted: False`, on every path including success, since
        nothing is ever saved here: the user is looking at Wingman, not
        at a preview, so nothing would ever select the client to
        acknowledge it, and a persistent test alert would pulse until
        they alt-tabbed to that client by hand.

        The sound plays exactly once regardless of how many previews are
        open, matching AlertService._handle's one-sound-per-dispatched-
        event behaviour -- N previews must not mean N overlapping sounds.

        With no live preview to ring -- previews off (no host at all) or
        a host present but no named EVE client -- the sound still plays
        and this still reports `applied: True`: the sound genuinely fired,
        so nothing was refused, and a silent no-op here would be
        indistinguishable from a broken feature. `error` carries the
        plain-language reason nothing visual happened, distinguishing the
        two cases -- "previews are off" and "no client is open" leave the
        user looking at a different fix -- and the page renders it inline.
        """
        if event not in alert_patterns.EVENTS:
            return self._field_refused(f"Unknown alert event: {event}")
        events = (
            self._state.settings.get("preview", {}).get("alerts", {}).get("events", {})
        )
        spec = dict(events.get(event, {}))
        spec["persist_until_selected"] = False
        sound = spec.get("sound") or "none"
        if sound != "none":
            # At the configured volume, like a real alert -- Test exists to
            # show what one is like, and a Test that ignored the slider
            # would be the one place in the card that lies about it.
            #
            # Never suppressed by focus, unlike the poll path: you are
            # looking at Wingman when you press this, so no EVE client
            # holds the foreground and there is nothing to suppress.
            alert_service.play_sound(
                sound,
                self._state.settings.get("preview", {})
                .get("alerts", {})
                .get("volume", 100),
            )
        if self._preview_host is None:
            return {
                "applied": True,
                "persisted": False,
                "error": "Previews are off, so only the sound played.",
            }
        characters = self._preview_host.characters()
        if not characters:
            return {
                "applied": True,
                "persisted": False,
                "error": "No EVE clients are open, so only the sound played.",
            }
        for character in characters:
            self._preview_host.raise_alert(event=event, character=character, spec=spec)
        return self._field_ok(persisted=False)

    def get_alert_state(self) -> dict:
        """Everything the Alerts card needs, in one read.

        A read, not a push, for the same reason get_preview_hotkey_state
        is one: previews (and therefore alerts) can start before the
        webview exists -- start_previews_if_enabled runs before
        window_mod.run() -- so a health change discovered at launch would
        be pushed into a window that is not there yet and _push swallows
        it. The page asks for this on load instead.
        """
        section = self._state.settings.get("preview", {})
        alerts = section.get("alerts", {})
        gamelogs = self._state.settings.get("gamelogs_dir")
        folder = Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()
        # Same test as AlertService._wanted(): a folder that was valid and
        # stopped being one (an unmounted drive, an unlinked OneDrive
        # folder, a settings.json carried from another machine) must show
        # the no-folder banner, not the healthy card, even though the
        # setting still holds a path.
        if folder is not None and not folder.is_dir():
            folder = None
        if self._alerts is not None:
            health = self._alerts.health()
            running = health.running
            last_error = health.last_error
            characters = list(health.characters)
        else:
            running, last_error, characters = False, None, []
        return {
            "previews_enabled": bool(section.get("enabled")),
            "alerts": dict(alerts),
            "running": running,
            "last_error": last_error,
            "characters": characters,
            "gamelogs_folder": str(folder) if folder is not None else None,
        }

    # ---- Where a preview opens ------------------------------------------

    def set_restore_preview_positions(self, enabled) -> dict:
        """Persist whether a preview opens at its saved position.

        Governs ALL preview placement, not only placement at launch: a
        preview is created whenever its client appears, which is usually
        mid-session. PreviewHost re-reads the stored value per placement,
        so nothing has to be pushed to it here -- and nothing should be.
        The setting says where a preview OPENS; previews already on
        screen stay where the user put them.

        Returns a dict rather than a bare bool so a write that did not
        land can be reported. Leaving the checkbox showing a choice the
        next restart will discard is the failure this shape exists to
        prevent.
        """
        enabled = bool(enabled)
        section = self._state.settings.setdefault("preview", {})
        persisted = True
        if section.get("restore_preview_positions") != enabled:
            try:
                # Through settings.update, not save(): the mutation must
                # happen inside _SAVE_LOCK or a concurrent writer is
                # reverted. update() also restores the live dict if the
                # block raises, so a failed write leaves the stored value
                # as it was and the next toggle retries on its own --
                # which is why this needs no dirty-flag of its own.
                with settings_mod.update(self._state.settings) as doc:
                    doc.setdefault("preview", {})["restore_preview_positions"] = enabled
            except OSError:
                # Logged and reported, not raised. A settings file that
                # cannot be written must not break the toggle -- but the
                # page has to be able to say the choice is not saved.
                persisted = False
                logger.exception("Could not persist restore_preview_positions")
        return {"applied": True, "persisted": persisted}

    def _push_first_run_when_ready(self) -> None:
        """Tell the page to show its first-run route, once it can hear it.

        Deferred onto a short timer rather than pushed immediately: this is
        called before webview.start(), so app.js has not registered its
        handlers and _push would log the message and drop it. The page asks
        for state on load, but there is no state to ask for here -- an
        unconfigured folder is exactly the case list_rows() returns silently
        on -- so this is the one thing Python must volunteer.
        """
        if self._state.settings.get("first_run_skipped"):
            # Asked once and declined. A recording folder configures the
            # UPLOADER half, and PRODUCT.md holds the two halves
            # independent -- so someone here for previews and bookmark
            # keybinds must not be re-gated on it every launch. The screen
            # returns the moment they clear the flag by choosing a folder
            # (set_folder), or if they never do, from Settings.
            return
        timer = self._timer(FIRST_RUN_PUSH_S, lambda: self._push("onFirstRun", {}))
        timer.daemon = True
        timer.start()

    def skip_first_run(self) -> dict:
        """Dismiss the first-run screen without choosing a folder.

        Persisted rather than held for the session: __main__ shows that
        screen whenever no folder RESOLVES, so a session-only skip would be
        re-asked on the next launch -- and it is the one screen in the app
        with no exit.

        It records the DISMISSAL, not the absence of a folder, which is why
        it is a key of its own rather than a sentinel recording_dir. The
        two states __main__ could not otherwise tell apart are "never
        configured, and said so" and "configured once, folder has since
        gone"; only the first is a skip, and the second still deserves the
        screen.

        Returns the same {applied, persisted, error} envelope every other
        commit does, so the page can say the choice will not survive a
        restart rather than silently pretending it will.
        """
        return self._write_setting("first_run_skipped", True)

    def _push_auth(self, state: str, message: str | None = None) -> None:
        # Read live from settings rather than snapshotted: the channel is
        # learned from the first upload response, so a title captured at
        # construction would be empty for the whole of the session that
        # actually learned it.
        if message is None:
            message = copy_mod.account_line(
                state, self._state.settings.get("channel_title", "") or ""
            )
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
        self._auth_thread = threading.Thread(
            target=self._auth_check_worker, daemon=True
        )
        self._auth_thread.start()

    def _auth_check_worker(self) -> None:
        try:
            creds = uploader.load_credentials(paths.token_file())
            connected = creds is not None and not uploader.needs_reauth(creds)
        except Exception:  # noqa: BLE001 - unreadable is indistinguishable from disconnected
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
        except Exception as exc:  # noqa: BLE001 - reported to the user, never raised
            self._alert("error", "Connection failed", str(exc))
            self._push_auth("disconnected")
            return
        self._push_auth("connected")

    # ---- EVE bookmarks ------------------------------------------------

    def get_bookmarks(self) -> dict:
        """Everything the Bookmarks route renders, in one call."""
        section = self._state.settings["eve_bookmarks"]
        engine = self._state.engine
        status = (
            engine.status(enabled=section["enabled"]) if engine is not None else None
        )
        return {
            "settings": section,
            "labels": bookmarks.BIND_LABELS,
            "order": list(bookmarks.BIND_IDS),
            # Round 5, C8. Derived in bookmarks.bind_groups() from
            # BIND_LABELS, never listed in the page: PRODUCT.md makes that
            # table the one place a fork rewrites, and a second copy in JS
            # is the copy a fork would not know to change. `order` above
            # stays the flat list -- it is still the identity of the route's
            # display order, and the page falls back to it if this is
            # missing (an older payload, a fork that stripped it).
            "groups": list(bookmarks.bind_groups()),
            "windows": evewindows.list_eve_windows(),
            "collisions": bookmarks.collisions(section["keybinds"]),
            # Round 5, C6: the mirror of _bookmark_chords. Previews warned
            # about this collision on the screen that WINS it; the screen
            # whose bind is the one silently overridden showed nothing.
            "preview_chords": self._preview_chords(),
            # Human labels for the bound keys. Computed here rather than in
            # the page, which is the entire reason to_ahk returns a display
            # string: the page holds no mapping table and cannot drift from
            # this one. Without this the UI would show raw "^+s".
            "displays": {
                bid: bookmarks.parse_ahk(value)["display"]
                for bid, value in section["keybinds"].items()
                if value
            },
            "engine": {
                "state": status.state if status else "off",
                # Surfaces a failed start straight away. Without this the
                # toggle reads "on" while nothing is running, and the reason
                # never reaches the user at all.
                "last_error": status.last_error if status else None,
                # Config states that produce a live engine registering
                # nothing. Empty while the feature is off: nothing is
                # running, so there is nothing to warn about, and a warning
                # on a deliberately-disabled route is just noise.
                "blockers": (
                    bookmarks.registration_blockers(section)
                    if section["enabled"]
                    else []
                ),
            },
        }

    def _preview_chords(self) -> dict:
        """Preview chords, split by whether they are registered right now.

        The counterpart of _bookmark_chords() -- read that docstring for why
        the collision exists at all and why the split is not a filter. This
        is the same fact told from the other end: there, a bookmark chord
        that a preview will take; here, the preview chords that take one.

        NOT a straight mirror, and the asymmetry is the point rather than an
        oversight. _bookmark_chords() has to infer from configuration --
        AHK's `#HotIf WinActive` hotkey is not a RegisterHotKey
        registration, so Windows can report nothing about it and "enabled,
        with a window ticked" is the closest it can get. A preview chord IS
        a RegisterHotKey, so the host can say whether Windows actually
        granted it, and inferring from `preview.enabled` here would claim a
        bookmark had lost its key to a chord Windows refused.

        Three outcomes, not two, which is the same three previews.js's
        clashes() already distinguishes and for the same reason:

        - registered right now -> "active". The bookmark cannot fire while
          EVE is focused.
        - the host is not holding chords at all (previews off, or stopped)
          -> "latent". Nothing is taken yet and turning previews on would
          take it, which is exactly what the page says.
        - the host IS running and this chord is refused, or has not been
          reported on yet -> NEITHER. We cannot say a preview takes the key,
          and we cannot say turning previews on would, because they are on.
          An unmarked bind is the honest answer; previews.js surfaces the
          refusal on its own screen, where the user can act on it.

        Compared in display form, the common ground the two notations meet
        on: preview gestures are STORED in display form -- settings.py runs
        every one through preview.gestures.display() on load -- which is why
        nothing is rendered here.
        """
        preview = self._state.settings.get("preview") or {}
        hotkeys = preview.get("hotkeys") or {}
        chords = {
            chord
            for chord in [
                *(hotkeys.get("characters") or {}).values(),
                hotkeys.get("cycle_next"),
                hotkeys.get("cycle_prev"),
            ]
            if chord
        }
        host = self._preview_host
        # is_running, not `host is not None` -- the same window between
        # stop() and _teardown that get_preview_hotkey_state() gates on.
        live = host is not None and host.is_running
        if not live:
            return {"active": [], "latent": sorted(chords)}
        status = host.hotkey_status()
        return {
            "active": sorted(c for c in chords if status.get(c) is True),
            "latent": [],
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

        try:
            with settings_mod.update(self._state.settings) as cfg:
                cfg["eve_bookmarks"] = settings_mod.validated_eve(section)
        except OSError as exc:
            # Same contract as save_settings: update() restored the live
            # dict before re-raising, so state and disk never diverge, and
            # say why rather than letting the exception escape.
            self._alert(
                "error",
                "Could not save settings",
                f"Bookmark settings were not saved: {exc}",
            )
            return {**self.get_bookmarks(), "saved": False}

        # update() normalises self._state.settings in place; no rebind
        # needed (see save_settings's comment above for why not).
        clean = self._state.settings["eve_bookmarks"]

        engine = self._state.engine
        if engine is not None:
            engine.apply(clean)
            if clean["enabled"] and not engine.is_running():
                engine.start()
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

    def import_bookmarks(self) -> dict:
        """Import a standalone helper INI chosen by the user.

        The standalone script wrote its INI relative to its working
        directory, so there is no path worth probing -- the user points at
        it.
        """
        chosen = self._window.create_file_dialog(_open_file_dialog_kind(), directory="")
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
            return {
                "ok": False,
                "discarded": [],
                "notes": [f"Could not read that file: {exc}"],
            }

        result = bookmarks.import_legacy_ini(bookmarks.decode_ini_bytes(raw))
        if not result["parsed"]:
            # No sections at all. Indistinguishable from an empty config by
            # content, so it is treated as the failure it almost certainly
            # is: saving here would wipe the settings the import exists to
            # preserve.
            return {
                "ok": False,
                "discarded": [],
                "notes": [
                    "That file does not look like a bookmark helper INI - no "
                    "settings were found in it, so nothing was changed."
                ],
            }
        # Import never enables the engine: reading someone's old settings is
        # not consent to start a keyboard hook.
        result["section"]["enabled"] = self._state.settings["eve_bookmarks"]["enabled"]
        if not self.save_bookmarks(result["section"])["saved"]:
            # Deliberately no note: save_bookmarks has already raised its own
            # "Could not save settings" dialog naming the reason, and the
            # page only alerts on a failure that carries one. Returning a
            # second message here would put two dialogs on screen for one
            # failure -- and returning ok=True would put a contradictory
            # "Import complete" beside the error, which is the bug this
            # flag exists to close.
            return {"ok": False, "discarded": [], "notes": []}
        return {"ok": True, "discarded": result["discarded"], "notes": result["notes"]}

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

    # ----- EVE Settings ---------------------------------------------------

    def _eve_section(self) -> dict:
        # validated_eve_settings, not the private _eve_settings_defaults:
        # it is the public surface for this section, and it already returns
        # a fresh dict per call rather than the module global. Reaching
        # across a module boundary for a private name is how a caller ends
        # up depending on something the owning module is free to rename.
        return self._state.settings.setdefault(
            "eve_settings", settings_mod.validated_eve_settings({})
        )

    def _eve_clear_identification(self) -> int:
        """Discard the observation and any pair it authorized.

        Claims a new generation as it goes, and returns it: everything
        computed under the old number -- an in-flight publication here, a
        rendered offer on the page -- is stale from this moment.
        """
        with self._eve_identification_lock:
            return self._eve_clear_identification_locked()

    def _eve_clear_identification_locked(self) -> int:
        """_eve_clear_identification for a caller that already holds the lock."""
        self._eve_identification_generation += 1
        self._eve_identification = None
        self._eve_identification_candidate = None
        return self._eve_identification_generation

    def _eve_generation(self) -> int:
        """The identification generation, read atomically."""
        with self._eve_identification_lock:
            return self._eve_identification_generation

    def _eve_identification_state(
        self,
    ) -> tuple[int, evesettings_identity.Snapshot | None, _EveCandidate | None]:
        """Generation, observation and offer, as one coherent reading."""
        with self._eve_identification_lock:
            return (
                self._eve_identification_generation,
                self._eve_identification,
                self._eve_identification_candidate,
            )

    def _eve_identification_cancelled_locked(self) -> dict:
        """The answer to a pass whose generation was claimed by someone else.

        No error text: nothing failed. The user (or a confirmed deletion)
        ended this pass while it was still working, and the number tells
        the page that this response is the older of the two it holds.
        """
        return {
            "status": "cancelled",
            "error": None,
            "identification_generation": self._eve_identification_generation,
        }

    def _eve_account_identity(self, account_id: str, names=None, links=None) -> dict:
        section = self._eve_section()
        return evesettings_identity.account_identity(
            account_id,
            section.get("account_names") or {} if names is None else names,
            section.get("account_characters") or {} if links is None else links,
            lambda character_id: self._eve_names.label(int(character_id)),
        )

    def _eve_identity(self, path, names=None, links=None) -> dict:
        """One display representation for every Profiles identity surface.

        `names`/`links` are the account metadata to apply. They are passed
        explicitly rather than read here so one state request decides ONCE
        whether Tranquility metadata may be applied at all -- the answer
        depends on the discovered server, and re-deriving it per row would
        cost a discovery pass per file.
        """
        kind = evesettings_tree.file_kind(path)
        ident = evesettings_tree.file_id(path)
        if kind == "character" and ident.isdigit():
            primary = self._eve_names.label(int(ident))
            return {
                "primary": primary,
                "secondary": f"Character {ident}",
                "option": primary,
            }
        if kind == "account" and ident:
            return self._eve_account_identity(ident, names, links)
        primary = Path(path).stem
        return {"primary": primary, "secondary": "", "option": primary}

    def _eve_label(self, path) -> str:
        """The compact label shared by pickers, confirmations and status."""
        return self._eve_identity(path)["option"]

    def _eve_backup_identity(self, item, names=None, links=None) -> tuple[str, str]:
        if item.kind in ("character", "account"):
            prefix = "core_char_" if item.kind == "character" else "core_user_"
            suffix = item.stem.removeprefix(prefix)
            if suffix != item.stem and suffix.isascii() and suffix.isdigit():
                identity = self._eve_identity(f"{item.stem}.dat", names, links)
                if item.kind == "account":
                    return identity["primary"], identity["secondary"]
                return identity["primary"], f"Character {suffix}"
            return item.stem, item.kind.title()
        if item.kind == "profile":
            return item.stem.removeprefix("settings_"), "Profile"
        return item.stem, item.kind.title()

    @staticmethod
    def _eve_canonical(path) -> str:
        """realpath plus platform case folding, or "" for nothing selected."""
        if not path:
            return ""
        return os.path.normcase(os.path.realpath(os.path.expandvars(str(path))))

    def _eve_context(self, found) -> _EveContext:
        """The context *found* speaks for, and whether it can be trusted.

        Trust needs BOTH halves. `_shard()` calls anything containing
        "tranquil" Tranquility, which is right for a label and far too
        permissive for a persisted deletion, so the strict predicate has to
        agree -- and the server must be one discovery actually offered under
        that key, not a stale stored string.
        """
        server = self._eve_canonical(found.server)
        known = next(
            (s for s in found.servers if self._eve_canonical(s.path) == server), None
        )
        trusted = bool(
            server
            and known is not None
            and known.key == "tranquility"
            and evesettings_tree.is_tranquility_server(found.server)
        )
        return _EveContext(
            root=self._eve_canonical(found.root),
            server=server,
            profile=self._eve_canonical(found.profile),
            datasource="tranquility" if trusted else "",
        )

    def _eve_account_identity_available(self, found) -> bool:
        """Whether saved account names and links apply to this selection."""
        return self._eve_context(found).trusted

    def _eve_deleted_ids(self, found) -> set[str]:
        """Ids confirmed deleted that this selection would otherwise show.

        Empty for an untrusted context, whatever the cache holds: a
        Tranquility verdict is not evidence about another shard.
        """
        context = self._eve_context(found)
        if not context.trusted:
            return set()
        candidates = {r.file_id for r in found.characters if r.file_id.isdigit()}
        candidates.update(
            character_id
            for values in (self._eve_section().get("account_characters") or {}).values()
            for character_id in values
            if character_id.isdigit()
        )
        return {
            character_id
            for character_id in candidates
            if (context.datasource, int(character_id)) in self._eve_deleted
        }

    def _eve_is_deleted(self, character_id) -> bool:
        """One confirmed-deleted id, without a discovery pass.

        Account metadata is Tranquility's by definition (there is no
        datasource in the schema), so a Tranquility verdict disqualifies an
        id from being linked regardless of what is selected right now.
        """
        return (
            isinstance(character_id, str)
            and character_id.isascii()
            and character_id.isdigit()
            and ("tranquility", int(character_id)) in self._eve_deleted
        )

    def _eve_prune_deleted_links_locked(self, deleted_ids: set) -> bool:
        """Drop *deleted_ids* from every saved account. Caller holds the lock.

        True when no saved link references a deleted id any more -- both
        "there was nothing to do" and "pruned and persisted". False means the
        write failed and the links are still saved, which is the pending
        state: the payload keeps hiding them, the next pass retries, and an
        account edit is refused until it succeeds.
        """
        if not deleted_ids:
            return True
        section = self._eve_section()
        saved = section.get("account_characters") or {}
        pruned = {
            account_id: [c for c in character_ids if c not in deleted_ids]
            for account_id, character_ids in saved.items()
        }
        pruned = {
            account_id: character_ids
            for account_id, character_ids in pruned.items()
            if character_ids
        }
        if pruned == saved:
            return True
        try:
            settings_mod.update_section(
                self._state.settings, "eve_settings", {"account_characters": pruned}
            )
        except OSError:
            # Ids only. Account names are private local metadata and never
            # belong in a log line.
            logger.exception(
                "Could not remove deleted EVE character links %s", sorted(deleted_ids)
            )
            return False
        return True

    def eve_settings_state(self) -> dict:
        """The whole visible tree. Cheap enough to answer on the bridge
        thread: scandir over a few dozen files, and listing backups is one
        listdir with no archive opened.

        The one thing here that is NOT that -- the running-client probe --
        runs on a background thread and is read from cache below."""
        self._eve_refresh_running()
        section = self._eve_section()
        root = section.get("root")
        found = evesettings_tree.discover(
            root, section.get("server"), section.get("profile")
        )
        store = paths.eve_settings_backup_dir()
        # Decided ONCE per request, from the discovered server: whether this
        # selection may wear Tranquility's account metadata, and which of
        # its characters ESI has confirmed deleted. Nothing below re-derives
        # either, and found.characters is never mutated -- only the payload
        # is filtered, so discovery stays a pure inventory of local files.
        identity_available = self._eve_account_identity_available(found)
        deleted_ids = self._eve_deleted_ids(found)
        identity_names = (
            (section.get("account_names") or {}) if identity_available else {}
        )
        identity_links = (
            {
                account_id: [c for c in character_ids if c not in deleted_ids]
                for account_id, character_ids in (
                    section.get("account_characters") or {}
                ).items()
            }
            if identity_available
            else {}
        )
        visible_characters = [
            record for record in found.characters if record.file_id not in deleted_ids
        ]

        def describe(record):
            identity = self._eve_identity(record.path, identity_names, identity_links)
            item = {
                "path": str(record.path),
                "id": record.file_id,
                "name": identity["option"],
                "display_name": identity["primary"],
                "display_meta": identity["secondary"],
            }
            if record.kind == "account":
                item["account_name"] = identity_names.get(record.file_id, "")
                item["character_ids"] = list(identity_links.get(record.file_id, []))
            return item

        def backup_payload(item):
            display_name, display_meta = self._eve_backup_identity(
                item, identity_names, identity_links
            )
            return {
                "path": str(item.path),
                "created": item.created,
                "origin": item.origin,
                "kind": item.kind,
                "stem": item.stem,
                "display_name": display_name,
                "display_meta": display_meta,
            }

        def roster(records):
            """The order the Profiles roster reads in: by name (R1/D4).

            Sorted HERE and not in evesettings.tree, which is where the
            file_id sort this one supersedes still lives (as its stable
            base -- see the note there): tree.py has no names. A name
            is ESI's answer to a character id, resolved through
            _eve_label, and it arrives after discover() has returned --
            so the tree can only order by the id in the filename, which
            is what put 32 characters on screen in an order with no human
            pattern and made the filter box the only route to one of
            them. `.es-roster` is `columns: 170px` and flows
            top-to-bottom, so alphabetical reads down each column.

            Case-folded, and the id is the tie-break: an unresolved name
            degrades to "Character 98123456" (unidentified accounts sort
            by their explicit ID metadata), and two of those must not be free
            to swap places between two renders of the same folder.

            This reorders on the name push as well as at first render --
            eve_settings_resolve_names makes the page refetch once the
            real names land, which is the moment the roster becomes
            sortable at all.
            """
            return sorted(
                (describe(r) for r in records),
                key=lambda row: (row["name"].casefold(), row["id"]),
            )

        listed, backups_unreadable = evesettings_backup.enumerate_backups(store)
        codec_available = evesettings_codec.codec_available()
        identity_character_ids: set = set()
        if identity_available:
            identity_character_ids = {record.file_id for record in visible_characters}
            identity_character_ids.update(
                character_id
                for values in identity_links.values()
                for character_id in values
            )
        return {
            "root": str(found.root) if found.root else "",
            "default_root": str(evesettings_tree.default_root()),
            "server": str(found.server) if found.server else "",
            "profile": str(found.profile) if found.profile else "",
            "unreadable": found.unreadable,
            # Refused for being too wide to be an EVE folder, rather than
            # probed slowly. Distinct from `unreadable` because the user
            # action differs: this one means "pick a narrower folder".
            "too_broad": found.too_broad,
            # The LAST KNOWN answer, never a fresh probe. See
            # _eve_refresh_running: this method is costed as scandir over
            # a few dozen files and must stay that.
            "eve_running": self._eve_running,
            "identification_active": self._eve_identification is not None,
            # Derived here, never in the page: account names and links are
            # this product's Tranquility metadata, and recognizing a shard
            # is a Python job with a strict predicate behind it.
            "account_identity_available": identity_available,
            "servers": [{"path": str(s.path), "name": s.name} for s in found.servers],
            "profiles": [
                {"path": str(p.path), "name": p.name, "file_count": p.file_count}
                for p in found.profiles
            ],
            "characters": roster(visible_characters),
            "identity_characters": sorted(
                (
                    {
                        "id": character_id,
                        "name": self._eve_names.label(int(character_id)),
                    }
                    for character_id in identity_character_ids
                ),
                key=lambda item: (item["name"].casefold(), item["id"]),
            ),
            "accounts": roster(found.accounts),
            # Reported separately from an empty list for the same reason
            # `unreadable` is: "we could not read your backups" and "you
            # have no backups yet" are different answers, and telling a
            # user the second when the first is true invites them to
            # overwrite settings they believe are unprotected.
            "backups_unreadable": backups_unreadable,
            # The prune depth, so the page can say how many backups are
            # kept without typing the number into itself. Four places once
            # carried the bookmark-keybind count and three of them drifted;
            # this is the same shape, and DESIGN.md's "state that must not
            # be retyped" is the rule it is avoiding.
            "auto_keep": int(section.get("auto_keep", 10)),
            # Whether the bundled codec sidecar is present, so the page can
            # hide the formations editor entirely rather than let a click
            # end in eve_settings_formations's "not available in this
            # install" error.
            "formations_available": codec_available,
            "selective_copy_available": codec_available,
            "copy_groups": {
                "characters": evesettings_selective.groups_payload("character"),
                "accounts": evesettings_selective.groups_payload("account"),
            },
            "backups": [backup_payload(item) for item in listed],
        }

    def _eve_client_running(self) -> bool:
        """Advisory only -- nothing is blocked. preview.discovery already
        matches CLIENT_IMAGE ("exefile.exe"), handles an unopenable process
        as "not a client", and caches per PID."""
        try:
            from ..preview import discovery

            return bool(discovery.list_clients())
        except Exception:
            logger.debug("Could not check for a running EVE client", exc_info=True)
            return False

    def _eve_client_running_strict(self) -> bool:
        """Fresh fail-closed probe for writes that require EVE to be closed."""
        from ..preview import discovery

        return bool(discovery.list_clients(strict=True))

    def _eve_refresh_running(self) -> None:
        """Re-probe for a running client, off the bridge thread.

        eve_settings_state() is costed in the design as "scandir over a
        few dozen files", and list_clients() is not that: it enumerates
        every top-level window and resolves PIDs to executables. It caches
        per PID, so it is cheap in steady state, but the first call after
        a client starts or stops is not -- and it was being paid inline on
        the thread the whole UI answers on.

        It only drives an advisory pill, so a slightly stale answer costs
        nothing: state returns the last known value immediately and this
        pushes when the value actually CHANGES, which is the only moment
        the page has anything to redraw. Same push channel the name
        resolver uses, and for the same reason -- request/response cannot
        express an answer that arrives after the response did.
        """

        def worker() -> None:
            try:
                value = self._eve_client_running()
                if value != self._eve_running:
                    self._eve_running = value
                    self._push("onEveSettingsRunning", {"running": value})
            except Exception:
                logger.debug("EVE client probe failed", exc_info=True)
            finally:
                self._eve_probe.release()

        # Single-flight. Skipping is safe because the caller re-reads the
        # cached value either way, and the probe already in flight will
        # publish a fresher answer than this one could.
        if not self._eve_probe.acquire(blocking=False):
            return
        try:
            self._spawn(target=worker, daemon=True).start()
        except Exception:
            # Only the worker releases, and a worker that never started
            # never will -- that would wedge the probe for the process's
            # lifetime and freeze the pill on whatever it last said.
            self._eve_probe.release()
            logger.debug("Could not start the EVE client probe", exc_info=True)
        except BaseException:
            self._eve_probe.release()
            raise

    @contextlib.contextmanager
    def _eve_hold(self):
        """The mutation lock, for work that runs ON the bridge thread.

        Yields True when the lock was taken and False when it was already
        held; the caller declines in that case, exactly as _eve_begin
        does. `root` is an input to every containment check, so changing
        it while a restore or a copy is in flight would have that
        operation validate against a different root than the one in effect
        when it was approved -- and _eve_begin's stated policy is that EVE
        Settings mutations are refused rather than interleaved.

        Non-blocking, and not merely to match that policy. A worker
        holding the lock is parked in _eve_confirm() waiting for an answer
        the page delivers over the bridge, so blocking here would stop the
        bridge from carrying that answer. It is not a true deadlock --
        _eve_confirm is bounded by EVE_CONFIRM_TIMEOUT_S and reads a
        missing answer as "no", so the worker unwinds and releases -- but
        the price of blocking is a UI frozen for up to five minutes, which
        is not meaningfully better than one.
        """
        if not self._eve_mutation.acquire(blocking=False):
            self._alert(
                "warning",
                "EVE Settings busy",
                "Another EVE Settings operation is still running. "
                "Wait for it to finish, then try again.",
            )
            yield False
            return
        try:
            yield True
        finally:
            self._eve_mutation.release()

    def eve_settings_pick_root(self) -> str:
        # The lock is held across the dialog too, so a mutation cannot
        # start while the user is choosing. The alternative -- lock only
        # the write -- lets the user pick a folder and then discards it,
        # which is a worse answer to the same race.
        with self._eve_hold() as held:
            if not held:
                return ""
            section = self._eve_section()
            start = str(section.get("root") or evesettings_tree.default_root())
            chosen = self._window.create_file_dialog(
                _folder_dialog_kind(), directory=start
            )
            if not chosen:
                return ""
            picked = str(chosen[0])
            # The old server and profile belong to a tree that is no
            # longer the one on screen -- but rather than merely clearing
            # them, discover the tree the picked folder actually names
            # and persist ITS complete triple. normalize_selection lifts a
            # folder pointed at a server or a profile back up to the real
            # root, and the freshly discovered server/profile are what the
            # page renders as selected on the very next state() call,
            # instead of showing "none chosen" for a folder that plainly
            # has one.
            self._eve_clear_identification()
            found = evesettings_tree.discover(picked)
            self._eve_persist_selection(found)
            return str(found.root) if found.root else ""

    def eve_settings_detect_root(self) -> str:
        """Detect the EVE settings root, the way Folders detects OBS's.

        Profiles 4: `Detect` exists in Settings > Folders AND on the
        first-run screen, for a folder that is shallower and better known
        than this one -- while the EVE settings root, the folder the
        product is named for, got `Choose folder...` alone. PRODUCT.md
        names the job directly: "assume fluency. Do not explain EVE. Do
        explain Wingman -- where a folder is."

        A sibling of eve_settings_pick_root rather than a branch of
        detect_folder, and the difference is deliberate. detect_folder
        RETURNS a suggestion and leaves Save to the user, because its
        fields sit in an immediate-save form where writing under the user
        would discard their other edits. This screen has no form: its
        neighbour `Choose folder...` commits the moment the dialog closes.
        A Detect that only suggested, beside a Choose that commits, would
        be two behaviours for one question on one screen -- which is the
        class of inconsistency this whole round is about.

        So: same lock, same selection reset, same return shape as the
        picker. The lock is held across the probe for the picker's reason
        -- a mutation must not start midway.
        """
        with self._eve_hold() as held:
            if not held:
                return ""
            default = evesettings_tree.default_root()
            if not default.is_dir():
                # Named, not just refused. The path is the useful half of
                # the answer: a user whose EVE lives somewhere else learns
                # where we looked, which is what tells them Choose folder...
                # is the way out.
                self._alert(
                    "info",
                    "EVE settings folder not found",
                    "Could not find an EVE settings folder at:\n"
                    f"{default}\n\n"
                    "Use Choose folder... to point at it.",
                )
                return ""
            found = evesettings_tree.discover(default)
            section = self._eve_section()
            if str(found.root) == str(section.get("root") or ""):
                # Agreement reported as agreement, not as a silent rewrite
                # -- detect_folder's rule, and the reason it compares the
                # live value rather than blindly rewriting. Returning ""
                # here also keeps the selection intact, which the write
                # path below would otherwise clear for no reason.
                self._alert(
                    "info",
                    "EVE settings folder",
                    f"Already set to the detected folder:\n{found.root}",
                )
                return ""
            self._eve_clear_identification()
            self._eve_persist_selection(found)
            return str(found.root)

    def eve_settings_select(self, server: str, profile: str) -> bool:
        with self._eve_hold() as held:
            if not held:
                return False
            # The EFFECTIVE root, not the raw stored value: normalize_selection
            # rewrites a root pointed at a profile or server directory, and
            # in doing so it also discards whatever server/profile the
            # caller asked for in favor of the ones implied by that deep
            # root (see tree.py's normalize_selection). Discovering directly
            # from a legacy deep `root` would therefore silently overrule a
            # real selection change -- e.g. picking a sibling profile from a
            # pre-canonicalization install that stored `root` as the
            # original profile itself. Resolving the canonical root FIRST,
            # then discovering from IT with the requested tokens, is what
            # lets normalize_selection's third branch (which passes both
            # tokens through untouched) actually see them.
            effective_root = self._eve_discover().root
            found = evesettings_tree.discover(
                effective_root, server or None, profile or None
            )
            if found.root is None:
                return False
            # discover() falls back to the first server/profile it finds
            # when the requested token matches nothing on disk -- a
            # fabricated server or profile must not silently persist as
            # "whatever discover() picked instead". An empty profile is
            # the one deliberate case that IS a fallback: it asks for the
            # requested server's first profile, which is exactly what
            # discover() returns for a None profile.
            if server and not _eve_same_path(found.server, server):
                return False
            if profile and not _eve_same_path(found.profile, profile):
                return False
            self._eve_clear_identification()
            self._eve_persist_selection(found)
            return True

    def _eve_persist_selection(self, found) -> None:
        """The one place that writes root/server/profile to settings.

        Every explicit selection -- picker, Detect, eve_settings_select, and
        the profile a copy creates -- discovers a Tree first and persists ITS
        complete triple here, rather than writing back whatever the caller
        was originally given. A picked or typed value can be a server or a
        profile directory, or a legacy root that pointed one or two levels
        too deep; discover() already normalizes all of those, and persisting
        anything other than its answer would let the stored root drift out of
        step with the server/profile that were actually chosen alongside it.
        That is also why there is no per-leg override argument: a caller that
        wants a particular profile remembered discovers it first (see
        _eve_select_created_profile) so the whole triple stays consistent,
        rather than pasting one leg over a Tree that disagrees with it.
        """
        settings_mod.update_section(
            self._state.settings,
            "eve_settings",
            {
                "root": str(found.root) if found.root else None,
                "server": str(found.server) if found.server else None,
                "profile": str(found.profile) if found.profile else None,
            },
        )

    def _eve_discover(self):
        section = self._eve_section()
        return evesettings_tree.discover(
            section.get("root"), section.get("server"), section.get("profile")
        )

    @staticmethod
    def _eve_decimal_id(value) -> bool:
        return isinstance(value, str) and value.isascii() and value.isdigit()

    @staticmethod
    def _eve_validate_account_name(
        account_id: str, name: str, names: dict
    ) -> tuple[str | None, str | None]:
        cleaned = name.strip()
        if not cleaned:
            return None, "Enter an EVE Online username."
        if len(cleaned) > 80:
            return None, "Account names can be up to 80 characters."
        folded = cleaned.casefold()
        if any(
            other_id != account_id and str(other_name).strip().casefold() == folded
            for other_id, other_name in names.items()
        ):
            return (
                None,
                "That EVE Online username is already assigned to another account.",
            )
        return cleaned, None

    @staticmethod
    def _eve_relink_account_characters(
        associations: dict,
        account_id: str,
        remove_character_ids: list[str],
        account_characters: list[str],
    ) -> tuple[dict | None, str | None]:
        if len(set(account_characters)) > 3:
            return None, "An EVE account can have up to three characters."
        updated = {
            saved_account: [
                saved_character
                for saved_character in saved_characters
                if saved_character not in remove_character_ids
            ]
            for saved_account, saved_characters in associations.items()
        }
        updated = {
            saved_account: saved_characters
            for saved_account, saved_characters in updated.items()
            if saved_characters
        }
        if account_characters:
            updated[account_id] = account_characters
        else:
            updated.pop(account_id, None)
        return updated, None

    @contextlib.contextmanager
    def _eve_identity_hold(self):
        """Serialize synchronous identity edits without blocking the bridge.

        A worker can hold this lock while awaiting a page confirmation. Manual
        account edits must refuse in that state rather than block the bridge
        that delivers the answer and leave the worker parked until its timeout.
        """
        if not self._eve_mutation.acquire(blocking=False):
            yield False
            return
        try:
            yield True
        finally:
            self._eve_mutation.release()

    def eve_settings_set_account_name(self, account_id: str, name: str) -> dict:
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            if not self._eve_decimal_id(account_id) or not isinstance(name, str):
                return self._field_refused("Choose a valid account.")
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                return self._field_refused(_EVE_IDENTITY_UNAVAILABLE)
            if account_id not in {item.file_id for item in found.accounts}:
                return self._field_refused("That account is not in this profile.")
            if not self._eve_prune_deleted_links_locked(self._eve_deleted_ids(found)):
                return self._field_refused(_EVE_CLEANUP_FAILED)
            names = dict(self._eve_section().get("account_names") or {})
            cleaned, error = self._eve_validate_account_name(account_id, name, names)
            if error:
                return self._field_refused(error)
            names[account_id] = cleaned
            try:
                settings_mod.update_section(
                    self._state.settings, "eve_settings", {"account_names": names}
                )
            except OSError:
                logger.exception("Could not persist EVE account name")
                return self._field_refused("Could not save this account name.")
            return self._field_ok()

    def eve_settings_set_account_characters(
        self, account_id: str, character_ids: list
    ) -> dict:
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            if not self._eve_decimal_id(account_id) or not isinstance(
                character_ids, list
            ):
                return self._field_refused("Choose a valid account and characters.")
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                return self._field_refused(_EVE_IDENTITY_UNAVAILABLE)
            if account_id not in {item.file_id for item in found.accounts}:
                return self._field_refused("That account is not in this profile.")
            section = self._eve_section()
            if account_id not in (section.get("account_names") or {}):
                return self._field_refused(
                    "Name this account before adding characters."
                )
            # Before reading the roster, not after: the page submits its
            # VISIBLE list as the complete set, so a link it cannot see must
            # be gone from the saved mapping first or this edit would decide
            # its fate silently.
            deleted_ids = self._eve_deleted_ids(found)
            if not self._eve_prune_deleted_links_locked(deleted_ids):
                return self._field_refused(_EVE_CLEANUP_FAILED)
            # Re-read live section: update_section replaces the nested dict
            # object, so the snapshot taken above is stale after the prune.
            # Reading associations from it would re-persist a deleted link
            # that the prune just removed from another account.
            section = self._eve_section()
            associations = {
                key: list(value)
                for key, value in (section.get("account_characters") or {}).items()
            }
            known = {
                item.file_id
                for item in found.characters
                if item.file_id not in deleted_ids
            }
            known.update(value for values in associations.values() for value in values)
            wanted = []
            for value in character_ids:
                if self._eve_is_deleted(value):
                    return self._field_refused(_EVE_CHARACTER_DELETED)
                if not self._eve_decimal_id(value) or value not in known:
                    return self._field_refused(
                        "That character is not known to Wingman."
                    )
                if value not in wanted:
                    wanted.append(value)
            associations, error = self._eve_relink_account_characters(
                associations, account_id, wanted, wanted
            )
            if error:
                return self._field_refused(error)
            try:
                settings_mod.update_section(
                    self._state.settings,
                    "eve_settings",
                    {"account_characters": associations},
                )
            except OSError:
                logger.exception("Could not persist EVE account characters")
                return self._field_refused("Could not save these character links.")
            return self._field_ok()

    def eve_settings_identification_start(self) -> dict:
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "status": "busy",
                "error": "Another Profiles operation is running.",
                "identification_generation": self._eve_generation(),
            }
        try:
            # The claim comes first: the previous observation dies here, so
            # anything still working under the old number is already stale.
            generation = self._eve_clear_identification()
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                raise ValueError(_EVE_IDENTITY_UNAVAILABLE)
            deleted_ids = self._eve_deleted_ids(found)
            snapshot = evesettings_identity.take_snapshot(found)
            if not found.accounts or not [
                record
                for record in found.characters
                if record.file_id not in deleted_ids
            ]:
                raise ValueError(
                    "This profile needs an account and a character to identify."
                )
            # Compare-and-publish. The discovery above is filesystem work
            # done off the state lock, and a cancellation that landed
            # during it must win: either it ran before this and the claim
            # no longer matches, or it runs after and clears what was
            # published. There is no window in which neither is true.
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification = snapshot
        except (OSError, ValueError) as error:
            return {
                "status": "error",
                "error": str(error),
                "identification_generation": self._eve_generation(),
            }
        finally:
            self._eve_mutation.release()
        return {
            "status": "watching",
            "error": None,
            "identification_generation": generation,
        }

    def eve_settings_identification_check(self) -> dict:
        # A worker can hold this lock while parked on a bridge confirmation.
        # Refusing preserves the bridge thread that must deliver that answer.
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "status": "busy",
                "error": "Another Profiles operation is running.",
                "identification_generation": self._eve_generation(),
            }
        try:
            # A check speaks for the observation it reads, so it publishes
            # under that observation's generation rather than claiming one
            # of its own. Every status below carries the number it was
            # computed under, and the page discards an answer older than
            # the highest it has already seen.
            generation, snapshot, _ = self._eve_identification_state()
            if snapshot is None:
                return {
                    "status": "error",
                    "error": "Start account identification first.",
                    "identification_generation": generation,
                }
            # A new check supersedes every former offer, including one that
            # cannot compare because EVE has not closed yet.
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification_candidate = None
            try:
                if self._eve_client_running_strict():
                    return {
                        "status": "watching",
                        "error": "EVE is still running. Close that client, then check again.",
                        "identification_generation": generation,
                    }
            except Exception:
                # Fail closed: an unverified running state must not be treated as
                # the clean shutdown whose file changes identify an account.
                logger.warning(
                    "Could not verify EVE state during identification", exc_info=True
                )
                return {
                    "status": "watching",
                    "error": "Could not confirm that EVE is closed. Close it and try again.",
                    "identification_generation": generation,
                }
            found = self._eve_discover()
            changed = evesettings_identity.changes_since(snapshot, found)
            if changed.invalidated:
                with self._eve_identification_lock:
                    if self._eve_identification_generation != generation:
                        return self._eve_identification_cancelled_locked()
                    invalidated = self._eve_clear_identification_locked()
                return {
                    "status": "invalidated",
                    "error": "The selected EVE profile changed. Start identification again.",
                    "identification_generation": invalidated,
                }
            if len(changed.accounts) > 1:
                return {
                    "status": "ambiguous",
                    "error": "More than one account changed. Close the other EVE clients and start again.",
                    "identification_generation": generation,
                }
            # A deleted character's file can still be written by the client
            # that owned it, so it can still LOOK like the change that
            # identifies an account. It can never be offered as one.
            deleted_ids = self._eve_deleted_ids(found)
            characters = tuple(
                character_id
                for character_id in changed.characters
                if character_id not in deleted_ids
            )
            if len(changed.accounts) != 1 or not characters:
                return {
                    "status": "none",
                    "error": "No account and character changes were found. Make a small settings change in the client, then close it completely and check again.",
                    "identification_generation": generation,
                }
            account_id = changed.accounts[0]
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification_candidate = _EveCandidate(
                    generation, account_id, characters
                )
            return {
                "status": "candidate",
                "error": None,
                "account": {"id": account_id, **self._eve_account_identity(account_id)},
                "characters": [
                    {
                        "id": character_id,
                        "name": self._eve_names.label(int(character_id)),
                    }
                    for character_id in characters
                ],
                "identification_generation": generation,
            }
        finally:
            self._eve_mutation.release()

    def eve_settings_identification_confirm(
        self, account_id: str, character_id: str, account_name: str
    ) -> dict:
        """Persist one offered account/character pair as one settings update."""
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            candidate = None
            generation, _, offered = self._eve_identification_state()
            # The generation is read WITH the offer, not beside it: an
            # offer whose authorizing observation has been replaced is
            # stale even if the object survived the swap.
            if offered is not None and offered.generation == generation:
                candidate = offered
            if candidate is None:
                return self._field_refused("Start account identification again.")
            if (
                account_id != candidate.account_id
                or character_id not in candidate.character_ids
            ):
                return self._field_refused("That account match is no longer available.")
            if not isinstance(account_name, str):
                return self._field_refused("Enter an EVE Online username.")
            # The offer may have been made before the resolver learned this
            # character was gone; authorization is revalidated at the write.
            if self._eve_is_deleted(character_id):
                return self._field_refused(_EVE_CHARACTER_DELETED)
            # Pending cleanup first, exactly as the manual account edits do
            # it: this write replaces the whole mapping, so a deleted link
            # still saved for ANOTHER account would be carried along by it.
            if not self._eve_prune_deleted_links_locked(
                self._eve_deleted_ids(self._eve_discover())
            ):
                return self._field_refused(_EVE_CLEANUP_FAILED)

            # Read the live section AFTER the prune: update_section replaces
            # the nested dict object rather than mutating it, so a snapshot
            # taken earlier would re-persist the links just removed.
            section = self._eve_section()
            names = dict(section.get("account_names") or {})
            cleaned_name, error = self._eve_validate_account_name(
                account_id, account_name, names
            )
            if error:
                return self._field_refused(error)
            associations = {
                saved_account: list(character_ids)
                for saved_account, character_ids in (
                    section.get("account_characters") or {}
                ).items()
            }
            destination = associations.get(account_id, [])

            final_names = {**names, account_id: cleaned_name}
            final_associations = associations
            if character_id not in destination:
                final_associations, error = self._eve_relink_account_characters(
                    associations,
                    account_id,
                    [character_id],
                    [*destination, character_id],
                )
                if error:
                    return self._field_refused(error)

            if final_names != names or final_associations != associations:
                try:
                    settings_mod.update_section(
                        self._state.settings,
                        "eve_settings",
                        {
                            "account_names": final_names,
                            "account_characters": final_associations,
                        },
                    )
                except OSError:
                    # Account names are private local metadata; never include the
                    # supplied username in diagnostics.
                    logger.exception("Could not persist identified EVE account")
                    return self._field_refused("Could not save this account identity.")
            self._eve_clear_identification()
            return self._field_ok()

    def eve_settings_identification_cancel(self) -> dict:
        """End the pass. Never refused, never blocked, always a new number.

        Takes only the identification-state lock. Route exit cancels, and
        cleanup can own _eve_mutation for a whole ESI pass -- a cancel that
        waited for it would freeze the page on the way out of Profiles.

        The generation is the answer's substance, not decoration: a check
        whose candidate is still in flight returns the OLD number, so the
        page can drop it instead of rendering an offer the user just
        cancelled.
        """
        return {
            "status": "idle",
            "error": None,
            "identification_generation": self._eve_clear_identification(),
        }

    def eve_settings_resolve_names(self) -> None:
        """Verify and name the selected profile's characters, off the bridge.

        The one thing a request/response bridge cannot express on its own:
        the state that triggered this was already returned, carrying
        fallback ids and possibly a row for a character that no longer
        exists. One push per pass, not per name.

        Single-flight with ONE trailing pass. The page asks on every route
        entry and every profile switch, so requests arrive in bursts; a
        worker per request would multiply ESI traffic and let a slow pass
        publish over a newer one. A request that arrives while a pass runs
        is remembered, not queued, so switching A -> B mid-pass always ends
        up resolving B without another user action.
        """
        with self._eve_resolve_lock:
            if self._eve_resolve_running:
                self._eve_resolve_pending = True
                return
            self._eve_resolve_running = True
        self._eve_spawn_resolver()

    def _eve_spawn_resolver(self) -> None:
        """Start the worker that owns the claim, or give the claim back.

        A claim held by a worker that never started would silence the
        resolver for the life of the process -- every later request would
        coalesce into a pass nobody is running.
        """
        try:
            self._spawn(target=self._eve_resolve_worker, daemon=True).start()
        except Exception:
            self._eve_release_resolver()
            logger.warning("Could not start the EVE character resolver", exc_info=True)
        except BaseException:
            self._eve_release_resolver()
            raise

    def _eve_release_resolver(self) -> None:
        with self._eve_resolve_lock:
            self._eve_resolve_running = False
            self._eve_resolve_pending = False

    def _eve_resolve_worker(self) -> None:
        try:
            self._eve_resolve_pass()
        except Exception:
            logger.warning("EVE character resolution failed", exc_info=True)
        finally:
            # Running stays claimed ACROSS the handoff when a pass is owed,
            # so a request arriving in this gap coalesces into that pass
            # instead of starting a second worker beside it. The spawn is
            # decided under the lock and performed outside it: spawning
            # while holding it would re-enter this method under an inline
            # thread seam and deadlock.
            with self._eve_resolve_lock:
                restart = self._eve_resolve_pending
                self._eve_resolve_pending = False
                self._eve_resolve_running = restart
            if restart:
                self._eve_spawn_resolver()

    def _eve_resolve_pass(self) -> None:
        found = self._eve_discover()
        context = self._eve_context(found)
        local_ids = {int(r.file_id) for r in found.characters if r.file_id.isdigit()}
        linked_ids = {
            int(character_id)
            for values in (self._eve_section().get("account_characters") or {}).values()
            for character_id in values
            if character_id.isdigit()
        }
        if context.trusted:
            # Deleted is monotonic, so a confirmed id is never asked about
            # again. Active is NOT cached: a character alive on this visit
            # can be deleted before the next one, and a session can outlive
            # both. /universe/names still answers for ids with no local file
            # here -- they are names to show, not deletion candidates.
            unchecked = sorted(
                ident
                for ident in local_ids
                if (context.datasource, ident) not in self._eve_deleted
            )
            names, deleted = evesettings_characters.resolve(unchecked)
            self._eve_names.names.update(names)
            for ident in deleted:
                self._eve_deleted.add((context.datasource, ident))
            self._eve_names.resolve_missing(sorted(linked_ids - local_ids))
        else:
            self._eve_names.resolve_missing(sorted(local_ids | linked_ids))
        self._eve_apply_facts(context, local_ids | linked_ids)

    def _eve_apply_facts(self, context: _EveContext, ids: set) -> None:
        """Publish what the caches now say about *context*, if it is current.

        Remote facts are global and were cached above regardless. Applying
        them is per selection: a superseded pass may not clean, clear an
        identification, or repaint the profile that replaced it, and the
        trailing pass that follows re-evaluates the same cache against the
        selection that IS current -- which is how a fact learned by a stale
        pass still reaches the page.
        """
        if self._eve_context(self._eve_discover()) != context:
            return
        changed = False
        invalidated: tuple[str, ...] = ()
        deleted_ids = {
            str(ident)
            for ident in ids
            if (context.datasource, ident) in self._eve_deleted
        }
        if context.trusted and deleted_ids:
            changed, invalidated = self._eve_clean_deleted(context, deleted_ids)
        facts = (
            frozenset(
                (ident, self._eve_names.names[ident])
                for ident in ids
                if ident in self._eve_names.names
            ),
            frozenset(deleted_ids),
        )
        if facts != self._eve_applied.get(context, _EVE_NO_FACTS):
            self._eve_applied[context] = facts
            changed = True
        if changed:
            # Both keys always, the list empty when this pass invalidated
            # nothing: the page decides from the values, never from whether
            # a key happens to be present.
            self._push(
                "onEveSettingsNames",
                {
                    "identification_generation": self._eve_generation(),
                    "deleted_candidate_ids": sorted(invalidated),
                },
            )

    def _eve_clean_deleted(
        self, context: _EveContext, deleted_ids: set
    ) -> tuple[bool, tuple[str, ...]]:
        """Remove confirmed deleted ids from saved metadata.

        Returns (changed, invalidated_candidate_ids): whether anything the
        page shows moved, and which offered character ids this pass
        disqualified -- the page needs the ids to reset the one focused
        step it may be sitting on.

        Waits for the mutation lock rather than declining like the bridge
        endpoints do: this is already a background thread, so waiting costs
        nothing a user sees, and no network call is held across it. The
        context is revalidated INSIDE the lock, and the mapping is read
        there too -- a prune computed before the wait would write back a
        roster the user edited during it.
        """
        with self._eve_mutation:
            if self._eve_context(self._eve_discover()) != context:
                return False, ()
            before = self._eve_section().get("account_characters") or {}
            saved = {key: list(value) for key, value in before.items()}
            persisted = self._eve_prune_deleted_links_locked(deleted_ids)
            changed = (
                persisted
                and (self._eve_section().get("account_characters") or {}) != saved
            )
            # The offer on screen may name a character ESI has just called
            # deleted. Confirming it would persist a link this pass exists
            # to remove, so the whole observation goes -- under the state
            # lock, which this thread takes while holding _eve_mutation and
            # never the other way round.
            with self._eve_identification_lock:
                candidate = self._eve_identification_candidate
                invalidated: tuple[str, ...] = ()
                if candidate is not None:
                    invalidated = tuple(
                        character_id
                        for character_id in candidate.character_ids
                        if character_id in deleted_ids
                    )
                if invalidated:
                    self._eve_clear_identification_locked()
            return changed or bool(invalidated), invalidated

    def _eve_begin(self, worker, args) -> bool:
        """Claim the mutation lock and hand the work to a thread.

        Refused rather than queued: a queued operation's own confirmation
        would describe state that has since changed.
        """
        if self._eve_identification is not None:
            self._alert(
                "warning",
                "Account identification active",
                "Finish or cancel account identification, then try again.",
            )
            return False
        if not self._eve_mutation.acquire(blocking=False):
            self._alert(
                "warning",
                "EVE Settings busy",
                "Another EVE Settings operation is still running.",
            )
            return False
        try:
            self._spawn(target=worker, args=args, daemon=True).start()
        except Exception:
            # Only the worker releases the lock, and a worker that never
            # started never will: without this the feature is dead until
            # the app restarts.
            self._eve_mutation.release()
            logger.exception("Could not start the EVE Settings worker")
            self._alert("error", "EVE Settings", "That operation could not be started.")
            return False
        except BaseException:
            self._eve_mutation.release()
            raise
        return True

    def _eve_confirm(self, title: str, body: str, *, destructive: bool = False) -> bool:
        """_confirm, bounded, for the workers that hold the mutation lock.

        _push swallows every evaluate_js failure, so a confirmation whose
        push never reached the page would park the worker forever holding
        the lock -- permanently refusing every later copy, backup, restore
        and delete. A missing answer is read as "no".
        """
        return self._ask(
            title, body, timeout=EVE_CONFIRM_TIMEOUT_S, destructive=destructive
        )

    def _eve_done(self, ok: bool, **details) -> None:
        """Tell the page the mutation finished, so it can re-enable its
        buttons and refresh. The bridge call returned as soon as the worker
        was spawned, so this push is the page's only completion signal.

        *details* is how whole-profile copy says more than "finished"
        without a second completion channel: two handlers for one operation
        would let the page close its disclosure on one event and refresh on
        the other, in whichever order they happened to arrive. Callers with
        nothing extra to say pass `ok` alone and the payload is unchanged.
        """
        self._push("onEveSettingsDone", {"ok": bool(ok), **details})

    def _eve_auto_backup(self, target):
        store = paths.eve_settings_backup_dir()
        evesettings_backup.create_file_backup(store, target, origin="auto")

    def _eve_prune(self, keep: int, *, candidates=None) -> None:
        store = paths.eve_settings_backup_dir()
        report = (
            evesettings_backup.prune(store, keep)
            if candidates is None
            else evesettings_backup.prune(store, keep, candidates=candidates)
        )
        if report.failed:
            count = len(report.failed)
            self._alert(
                "warning",
                "Some automatic backups were not removed",
                f"Could not delete {count} automatic backup"
                f"{'s' if count != 1 else ''}. Wingman will try again later.",
            )

    def eve_settings_set_auto_keep(self, value) -> dict:
        current = int(self._eve_section().get("auto_keep", 10))
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        text = str(value).strip()
        if not text.isascii() or not text.isdigit():
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        wanted = int(text)
        if wanted < 1 or wanted > 100:
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        if wanted == current:
            return {"accepted": False, "value": current, "error": None}
        accepted = self._eve_begin(self._eve_auto_keep_worker, (wanted, current))
        return {
            "accepted": accepted,
            "value": current,
            "error": None if accepted else "Another Profiles operation is running.",
        }

    def _eve_auto_keep_worker(self, wanted: int, previous: int) -> None:
        ok = False
        try:
            store = paths.eve_settings_backup_dir()
            candidates = evesettings_backup.prune_candidates(store, wanted)
            if wanted < previous and candidates:
                count = len(candidates)
                noun = "backup" if count == 1 else "backups"
                if not self._eve_confirm(
                    "Change automatic backup retention",
                    f"Keep {wanted} automatic backups per item?\n\n"
                    f"This will permanently delete {count} older automatic {noun}. "
                    "Manual backups will be kept.",
                    destructive=True,
                ):
                    return
            settings_mod.update_section(
                self._state.settings, "eve_settings", {"auto_keep": wanted}
            )
            self._eve_prune(wanted, candidates=candidates)
            self._status(f"Keeping {wanted} automatic backups per item.")
            ok = True
        except Exception as error:
            logger.exception("Could not change EVE backup retention")
            self._alert("error", "Retention not changed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def eve_settings_copy(
        self, source: str, targets: list, groups: list | None = None
    ) -> bool:
        return self._eve_begin(
            self._eve_copy_worker,
            (source, [str(t) for t in targets or []], groups),
        )

    def _eve_copy_worker(
        self, source: str, targets: list, groups: list | None = None
    ) -> None:
        ok = False
        try:
            # None alone means the legacy byte-copy path. An empty list is
            # still a deliberate structured copy that preserves every
            # offered group from each target.
            if groups is None:
                # Derived from the targets, not passed by the page: the
                # Characters / Accounts switch already decides which files are
                # offered, so a mode argument on the bridge would be the same
                # fact written twice and free to disagree. A mixed set (which
                # the page cannot produce, but the bridge does not forbid)
                # resolves to None and falls back to naming files.
                kinds = {evesettings_tree.file_kind(t) for t in targets}
                kind = next(iter(kinds)) if len(kinds) == 1 else None
                # Plain copy remains advisory and best-effort for backwards
                # compatibility: a positive result warns in the confirmation.
                running = self._eve_client_running()
                preserved_labels = None
            else:
                kind = evesettings_tree.file_kind(source)
                offered = evesettings_selective.groups_for_kind(kind)
                valid_ids = {group.id for group in offered}
                if (
                    not isinstance(groups, list)
                    or any(not isinstance(group_id, str) for group_id in groups)
                    or len(set(groups)) != len(groups)
                    or not set(groups) <= valid_ids
                ):
                    raise ValueError(
                        "Selected groups must be a unique list offered for this file kind."
                    )
                preserved_labels = [
                    group.label for group in offered if group.id not in set(groups)
                ]
                try:
                    running = self._eve_client_running_strict()
                except Exception:
                    logger.exception("Could not verify that EVE is closed")
                    self._alert(
                        "error",
                        "Copy not started",
                        "Wingman could not verify that EVE is closed. "
                        "Close EVE and retry.",
                    )
                    return
                if running:
                    self._alert(
                        "error",
                        "Copy not started",
                        "EVE is running. Close EVE and retry.",
                    )
                    return

            if not self._eve_confirm(
                "Confirm Copy",
                copy_mod.format_eve_copy_confirm(
                    [self._eve_label(t) for t in targets],
                    kind,
                    running,
                    source_name=self._eve_label(source),
                    preserved_groups=preserved_labels,
                ),
                destructive=True,
            ):
                return
            if groups is None:
                report = evesettings_ops.copy_to_targets(
                    source,
                    targets,
                    root=self._eve_section().get("root"),
                    backup=self._eve_auto_backup,
                )
            else:
                report = evesettings_ops.copy_selected_to_targets(
                    source,
                    targets,
                    selected_groups=groups,
                    root=self._eve_section().get("root"),
                    backup=self._eve_auto_backup,
                )
            keep = int(self._eve_section().get("auto_keep", 10))
            self._eve_prune(keep)
            if report.failed:
                names = "\n".join(
                    f"  • {Path(o.path).stem}: {o.reason}" for o in report.failed
                )
                self._alert(
                    "error",
                    "Some copies did not happen",
                    f"Copied to {len(report.succeeded)} of "
                    f"{len(report.outcomes)}.\n\n{names}",
                )
            else:
                self._status(copy_mod.format_eve_copy_done(len(report.succeeded), kind))
                ok = True
        except Exception as error:
            logger.exception("EVE settings copy failed")
            self._alert("error", "Copy failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    # ---- whole-profile copy ----------------------------------------------

    def eve_settings_copy_profile(
        self, expected_source: str, mode: str, destination: str
    ) -> dict:
        """Create a new profile from the selected one, or replace another.

        The lock is claimed here rather than through _eve_begin, because two
        things have to happen on the bridge thread before a worker can
        exist. The request is validated against a freshly discovered tree,
        so a token the page rendered before a selection change landed comes
        back as a refusal the user reads beside the button they pressed --
        not as an alert about work that appeared to start. And any legacy
        deep `root` is canonicalized and persisted before a single file is
        touched. A worker could do neither: its answer would arrive after
        this call had already returned "accepted".

        Returns immediately. The outcome arrives through _eve_done.
        """
        if self._eve_identification is not None:
            return {
                "accepted": False,
                "error": "Finish or cancel account identification first.",
            }
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "accepted": False,
                "error": "Another Profiles operation is running.",
            }
        try:
            found = self._eve_discover()
            plan = evesettings_profilecopy.prepare_copy(
                found, expected_source, mode, destination
            )
            try:
                self._eve_persist_selection(found)
            except OSError as error:
                # Aborts untouched. The tree this request was validated
                # against would not be the one on disk in settings, and the
                # design's rule is that a failed canonical write is a copy
                # that never started rather than one that half-happened.
                logger.exception("Could not persist the canonical EVE selection")
                raise ValueError(
                    "Wingman could not save the folder selection, so nothing was "
                    "copied. Check that the settings file is writable and retry."
                ) from error
            self._spawn(
                target=self._eve_copy_profile_worker, args=(plan,), daemon=True
            ).start()
        except (OSError, ValueError) as error:
            self._eve_mutation.release()
            return {"accepted": False, "error": str(error)}
        except Exception:
            # Only the worker releases the lock, and a worker that never
            # started never will -- _eve_begin's rule, and the same cost:
            # every later Profiles mutation refused until the app restarts.
            self._eve_mutation.release()
            logger.exception("Could not start EVE profile copy")
            return {"accepted": False, "error": "Profile copy could not be started."}
        except BaseException:
            self._eve_mutation.release()
            raise
        return {"accepted": True, "error": None}

    def _eve_profile_copy_refusal(self) -> str | None:
        """None when EVE is provably closed; the refusal to show otherwise.

        Deliberately not _eve_client_running_strict(): that predicate reads
        an EVE-titled window whose PID or executable image could not be
        resolved as "not a client", which for a write that rewrites a whole
        profile is a guess in the dangerous direction. UNKNOWN gets its own
        message rather than borrowing the running one, because "EVE is
        running" sends the user to close a client that may not be there.
        """
        from ..preview import discovery

        probe = discovery.probe_eve_client_state()
        if probe.state is discovery.EveClientState.CLOSED:
            return None
        if probe.state is discovery.EveClientState.RUNNING:
            return "EVE is running. Close EVE and retry."
        logger.warning("Could not verify that EVE is closed: %r", probe.errors)
        return "Wingman could not verify that EVE is closed. Close EVE and retry."

    def _eve_select_created_profile(self, plan, created) -> bool:
        """Persist the newly created profile as the selection.

        Returns False rather than raising: the profile exists on disk
        either way, and the design keeps publication and remembering the
        selection as separate outcomes so a retry never implies nothing was
        created. A discover() that fell back to some OTHER profile (the
        created one vanished under us) is that same failure, not a licence
        to persist a selection nobody asked for.
        """
        try:
            found = evesettings_tree.discover(plan.root, plan.server, created)
            if not _eve_same_path(found.profile, created):
                logger.warning("The created profile %s was not discoverable", created)
                return False
            self._eve_persist_selection(found)
        except (OSError, ValueError):
            logger.exception("Could not persist the new EVE profile selection")
            return False
        return True

    def _eve_copy_profile_worker(self, plan) -> None:
        ok = False
        published = False
        # Whether the selection the page will see is the one this operation
        # intends. Replacement does not move the selection, and the source
        # it retains was persisted with the whole canonical triple before
        # this worker was spawned -- so it is already true here, on every
        # exit including a declined confirmation or a failed rollback.
        # Creation is the only mode with a NEW selection to save, and only
        # its own save decides this.
        selection_persisted = plan.mode != "new"
        error_message = None
        # Retention runs only once the destination has settled -- after a
        # successful publication, or after a rollback that put the old one
        # back. Pruning while the destination holds a mix of both profiles
        # would consider deleting automatic backups during the one window
        # in which the newest of them is the only way back.
        prune_after = False
        try:
            error_message = self._eve_profile_copy_refusal()
            if error_message:
                self._alert("error", "Copy not started", error_message)
                return
            created = None
            with evesettings_profilecopy.stage_copy(plan) as staged:
                if plan.mode == "new":
                    # No confirmation: creating a profile overwrites
                    # nothing, so there is nothing to warn about.
                    created = evesettings_profilecopy.publish_new(staged)
                    published = True
                else:
                    if not self._eve_confirm(
                        "Confirm Replace",
                        f"Replace {plan.destination_name} with a copy of "
                        f"{plan.source_name}?\n\n{plan.destination_name} is backed "
                        "up first. Its EVE settings files are replaced with "
                        f"{plan.source_name}'s, and any settings file "
                        f"{plan.source_name} does not have is removed.",
                        destructive=True,
                    ):
                        return
                    # Staging happened before the question, so the answer is
                    # the last thing between here and the destination -- and
                    # EVE can start while a confirmation sits on screen.
                    error_message = self._eve_profile_copy_refusal()
                    if error_message:
                        self._alert("error", "Copy not started", error_message)
                        return
                    store = paths.eve_settings_backup_dir()
                    try:
                        archive = evesettings_backup.create_profile_backup(
                            store, plan.destination, origin="auto"
                        )
                    except Exception as failure:
                        logger.exception(
                            "Could not back up %s before replacing it", plan.destination
                        )
                        error_message = (
                            f"{plan.destination_name} was not changed: Wingman "
                            "could not back it up first. "
                            f"{evesettings_ops.describe(failure)}"
                        )
                        self._alert("error", "Destination unchanged", error_message)
                        return

                    def rollback() -> None:
                        # backup_current=False: the archive taken moments ago
                        # IS what rollback restores from. A fresh backup here
                        # would archive the half-published profile this call
                        # exists to erase, and would add a second chance to
                        # fail inside the recovery path itself.
                        evesettings_backup.restore(
                            store, archive, plan.root, backup_current=False
                        )

                    try:
                        evesettings_profilecopy.publish_replacement(
                            staged, rollback=rollback
                        )
                    except evesettings_profilecopy.ReplacementFailed as failure:
                        logger.exception("EVE profile replacement failed")
                        prune_after = failure.destination_restored
                        if failure.destination_restored:
                            error_message = (
                                f"{plan.destination_name} was restored from its "
                                "automatic backup and is unchanged. "
                                f"{evesettings_ops.describe(failure.publication_error)}"
                            )
                            self._alert("error", "Replacement failed", error_message)
                        else:
                            # The archive is named because it is now the only
                            # way back, and Backups is where it is restored
                            # from -- an instruction, not an error code.
                            error_message = (
                                f"{plan.destination_name} may now hold a mix of both "
                                "profiles and Wingman could not put it back. Restore "
                                f"{archive.name} from Backups. "
                                f"{evesettings_ops.describe(failure.publication_error)}"
                            )
                            self._alert(
                                "error",
                                "Replacement and rollback failed",
                                error_message,
                            )
                        return
                    published = True
                    prune_after = True
            # Staging is gone by here: the design removes it before
            # retention runs, and before anything reports success.
            if plan.mode == "new":
                selection_persisted = self._eve_select_created_profile(plan, created)
                if selection_persisted:
                    self._status(f"Created {plan.destination_name}.")
                else:
                    # Still ok: the profile is on disk and the refreshed
                    # dropdown offers it. Only the selection was lost, and
                    # saying "failed" would invite a retry that collides
                    # with the profile this call just created.
                    error_message = (
                        f"Created {plan.destination_name}, but Wingman could not "
                        "remember the selection. Select it from Profile."
                    )
                    self._alert("warning", "Profile created", error_message)
            else:
                # The source stays selected, and it already is -- see the
                # initialiser above: the canonical triple was persisted
                # when the request was accepted, and replacement never
                # moves the selection.
                self._status(
                    f"Replaced {plan.destination_name} with a copy of "
                    f"{plan.source_name}."
                )
            ok = True
        except Exception as failure:
            logger.exception("EVE profile copy failed")
            error_message = evesettings_ops.describe(failure)
            self._alert("error", "Copy failed", error_message)
        finally:
            if prune_after:
                try:
                    self._eve_prune(int(self._eve_section().get("auto_keep", 10)))
                except Exception:
                    # Retention is housekeeping. It must never be the reason
                    # the lock is not released or the page never hears that
                    # the copy it is waiting on has finished.
                    logger.exception("Could not prune automatic backups")
            self._eve_mutation.release()
            self._eve_done(
                ok,
                operation="profile_copy",
                mode=plan.mode,
                published=published,
                selection_persisted=selection_persisted,
                error=error_message,
            )

    def eve_settings_backup(self, path: str, kind: str) -> bool:
        return self._eve_begin(self._eve_backup_worker, (path, kind))

    def _eve_backup_worker(self, path: str, kind: str) -> None:
        ok = False
        try:
            # Decided here, not in the page: an empty path is what Path()
            # resolves to the app's own working directory, which
            # create_profile_backup would happily walk and report as a
            # successful backup of nothing.
            if not path:
                raise ValueError("Choose a settings set to back up first.")
            resolved = evesettings_tree.require_under(
                self._eve_section().get("root"), path
            )
            if not resolved.exists():
                raise ValueError("That no longer exists.")
            store = paths.eve_settings_backup_dir()
            if kind == "profile":
                evesettings_backup.create_profile_backup(store, path, origin="manual")
            else:
                evesettings_backup.create_file_backup(store, path, origin="manual")
            label = (
                f"{resolved.name.removeprefix('settings_')} profile"
                if kind == "profile"
                else self._eve_label(resolved)
            )
            self._status(f"Backed up {label}.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings backup failed")
            self._alert("error", "Backup failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def eve_settings_restore(self, archive: str) -> bool:
        return self._eve_begin(self._eve_restore_worker, (archive,))

    def _eve_restore_worker(self, archive: str) -> None:
        ok = False
        try:
            info = evesettings_backup.parse_name(Path(archive).name)
            target = "this backup"
            created = ""
            if info is not None:
                target = self._eve_backup_identity(info)[0]
                try:
                    match = datetime.datetime.strptime(
                        info.created, "%Y%m%d-%H%M%S"
                    ).replace(tzinfo=datetime.UTC)
                except ValueError:
                    created = f" from {info.created}"
                else:
                    created = f" from {match:%Y-%m-%d %H:%M UTC}"
            if not self._eve_confirm(
                "Confirm Restore",
                f"Restore {target}{created}?\n\nThe current settings are backed "
                "up first. For a whole settings set, any file not in the "
                "backup is removed.",
                destructive=True,
            ):
                return
            store = paths.eve_settings_backup_dir()
            found = self._eve_discover()
            if found.root is None:
                raise ValueError("Choose the EVE settings folder first.")
            written = evesettings_backup.restore(store, archive, found.root)
            keep = int(self._eve_section().get("auto_keep", 10))
            self._eve_prune(keep)
            self._status(f"Restored into {written.name}.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings restore failed")
            self._alert("error", "Restore failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def eve_settings_delete_backup(self, archive: str) -> bool:
        return self._eve_begin(self._eve_delete_backup_worker, (archive,))

    def _eve_delete_backup_worker(self, archive: str) -> None:
        ok = False
        try:
            if not self._eve_confirm(
                "Confirm Delete",
                f"Permanently delete {Path(archive).name}?\n\nThis cannot be undone.",
                destructive=True,
            ):
                return
            evesettings_backup.delete(paths.eve_settings_backup_dir(), archive)
            self._status("Backup deleted.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings backup delete failed")
            self._alert("error", "Delete failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    # -- probe formations ---------------------------------------------------

    def _eve_account_file(self, path: str) -> Path:
        """Containment + kind check shared by the two formation endpoints."""
        root = self._eve_section().get("root")
        if not root:
            raise ValueError("Choose the EVE settings folder first.")
        resolved = evesettings_tree.require_under(root, path, suffix=".dat")
        if evesettings_tree.file_kind(resolved) != "account":
            raise ValueError(
                "Formations live in an account file, not a character file."
            )
        return resolved

    def eve_settings_formations(self, path: str) -> dict:
        """Decode one account file and return its user formations, in meters.

        Synchronous on purpose: a decode is milliseconds, and the page needs
        the answer to draw the editor. _eve_hold keeps it from reading a
        file a copy worker is mid-way through replacing.
        """
        with self._eve_hold() as held:
            if not held:
                return {
                    "ok": False,
                    "error": "Another EVE Settings operation is still running.",
                }
            try:
                target = self._eve_account_file(path)
                document = evesettings_codec.read_document(target)
                found = evesettings_formations.read_formations(document.doc)
            except (ValueError, OSError, evesettings_codec.CodecError) as error:
                return {"ok": False, "error": str(error)}
            return {
                "ok": True,
                "path": str(target),
                "name": self._eve_label(str(target)),
                "formations": evesettings_formations.to_payload(found),
            }

    def eve_settings_save_formations(self, path: str, formations: list) -> bool:
        return self._eve_begin(
            self._eve_save_formations_worker, (path, list(formations or []))
        )

    def _eve_save_formations_worker(self, path: str, items: list) -> None:
        ok = False
        try:
            target = self._eve_account_file(path)
            wanted = evesettings_formations.from_payload(items)
            evesettings_formations.validate(wanted)
            # Fail closed while a client runs: EVE holds core_*.dat open for
            # the session and rewrites it on exit, so a write now is either
            # refused by the sharing violation or silently overwritten
            # later. Copy merely warns because its targets are usually not
            # the running character; this always is the running account.
            try:
                running = self._eve_client_running_strict()
            except Exception:
                logger.exception("Could not verify that EVE is closed")
                self._alert(
                    "error",
                    "Formations not saved",
                    "Wingman could not verify that EVE is closed. Close EVE and retry.",
                )
                return
            if running:
                self._alert(
                    "error",
                    "Formations not saved",
                    "The file is in use. Close EVE and retry.",
                )
                return
            document = evesettings_codec.read_document(target)
            updated = evesettings_formations.write_formations(
                document.doc, wanted, now=time.time()
            )
            evesettings_codec.write_document(
                target,
                evesettings_codec.Document(doc=updated, had_crc=document.had_crc),
                backup=self._eve_auto_backup,
            )
            keep = int(self._eve_section().get("auto_keep", 10))
            self._eve_prune(keep)
            self._status(
                f"Saved {len(wanted)} formation(s) to {self._eve_label(str(target))}."
            )
            ok = True
        except (ValueError, evesettings_codec.CodecError) as error:
            self._alert("error", "Formations not saved", str(error))
        except Exception as error:
            logger.exception("formation save failed")
            self._alert(
                "error", "Formations not saved", evesettings_ops.describe(error)
            )
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    # ---- EVE skills ---

    def skills_state(self) -> dict:
        """Everything the Skills route renders, in one call."""
        if self._skills is None:
            return _empty_skills_state()
        return _with_fetch_labels(self._skills.state_payload())

    def skills_character_detail(self, character_id, plan_name) -> dict:
        if self._skills is None:
            return {
                "ok": False,
                "message": "The EVE skills subsystem is unavailable.",
                "character_id": 0,
                "plan_name": "",
                "readiness": "Unknown",
                "estimated_finish_utc": "",
                "queue_timing_unknown": False,
                "requirements": [],
            }
        return self._skills.character_detail(character_id, plan_name)

    def skills_plan_text(self, plan_name) -> str:
        """The selected plan as text, for the page to put on the clipboard.

        S7. The write itself is the page's job for the same reason
        copy_path's is: with Tk gone there is no toolkit clipboard and
        navigator.clipboard is right there.

        "" means the plan could not be read -- the page holds a plan list
        that a reload may have invalidated, exactly as skills_select_plan
        documents. A listed plan always has at least one requirement
        (plans.parse rejects a file with none), so "" never means "an empty
        plan" and the page can treat it as the failure it is.
        """
        if self._skills is None:
            return ""
        text = self._skills.plan_text(plan_name)
        if not text:
            self._status("That plan is no longer available. Reload plans.", "WARNING")
            return ""
        # The browser performs navigator.clipboard.writeText after this returns.
        # Do not claim a copy succeeded before that operation has completed.
        return text

    def skills_add_character(self) -> bool:
        """Start an interactive EVE sign-in. Returns before it finishes.

        True even with no controller, and even though nothing happened.
        `WM.send` resolves to null on a bridge failure and the page cannot
        otherwise tell the two apart -- the comment on set_preview_enabled
        above records that returning None from a no-op WAS the bug, and that
        it cost a checkbox that reverted on every successful toggle.
        """
        if self._skills is not None:
            self._skills.authenticate()
        return True

    def skills_cancel_auth(self) -> bool:
        if self._skills is not None:
            self._skills.cancel_auth()
        return True

    def skills_forget_character(self, character_id) -> bool:
        """False is meaningful here: nothing was forgotten."""
        if self._skills is None:
            return False
        return self._skills.forget(character_id)

    def skills_refresh(self) -> bool:
        if self._skills is not None:
            self._skills.refresh_characters()
        return True

    def skills_reload_plans(self) -> bool:
        if self._skills is not None:
            self._skills.reload_plans()
        return True

    def skills_open_plans_folder(self) -> bool:
        if self._skills is not None:
            self._skills.open_plans_folder()
        return True

    def skills_select_plan(self, plan_name) -> bool:
        if self._skills is None:
            return True
        return self._skills.select_plan(plan_name)

    def skills_set_character_group(self, character_id, group_name) -> bool:
        if self._skills is None:
            return True
        return self._skills.set_character_group(character_id, group_name)

    def skills_select_group(self, group_name) -> bool:
        if self._skills is None:
            return True
        return self._skills.select_group(group_name)

    def skills_rename_group(self, old_name, new_name) -> bool:
        if self._skills is None:
            return True
        return self._skills.rename_group(old_name, new_name)

    def skills_delete_group(self, name) -> bool:
        if self._skills is None:
            return True
        return self._skills.delete_group(name)

    def shutdown_skills(self) -> None:
        """Tear the subsystem down on the way out. main() only.

        Not a façade -- the page never calls it, exactly as it never calls
        shutdown_previews(). Runs on every exit path, so like
        shutdown_engine() it must never be the thing that raises: a live
        loopback socket on the fixed redirect port would make the NEXT
        launch's sign-in fail to bind, and there is no fallback port.
        """
        if self._skills is None:
            return
        try:
            self._skills.shutdown()
        except Exception:
            logger.exception("EVE skills subsystem did not stop cleanly")
