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

**Workers use semantic push chokepoints.** Most call `_push`; the independent
Fleet page uses `_push_fleet_snapshot`. Both serialize a complete semantic
payload and call `evaluate_js`, which is safe from any thread; there is no UI
thread to marshal onto.

`_window` is assigned by ui.window.create() after construction rather than
passed in: create_window() needs js_api before a window object exists.
"""

import contextlib
import copy
import json
import logging
import math
import os
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from .. import __version__ as _version
from .. import (
    autostart,
    bookmarks,
    combatlog,
    discord,
    evewindows,
    fightrecorder,
    library,
    obsconfig,
    paths,
    uploader,
)
from .. import settings as settings_mod
from .. import updates as updates_mod
from ..alerts import patterns as alert_patterns
from ..alerts import service as alert_service
from ..eveauth import application as eveauth_application
from ..evesettings.controller import ProfilesController, ProfilesPorts
from ..preview import crops as preview_crops
from ..preview import geometry as preview_geometry
from ..preview import gestures as preview_gestures
from ..preview import host as preview_host_mod
from ..preview import layout as preview_layout
from ..preview import window as preview_window
from ..upload.controller import (
    PROBE_DRAIN_S,
    UploaderController,
    UploaderPorts,
    folder_note,
)
from ..upload.gate import WorkGate
from . import copy as copy_mod
from .fleetpresentation import (
    FleetDelivery,
    FleetPresentationWorker,
    RosterMemory,
    RosterWrite,
)
from .rows import RowSnapshot
from .scheduler import Scheduler

logger = logging.getLogger(__name__)


def _page_payload(payload):
    """JSON data, not an object literal (whose __proto__ changes prototypes)."""
    try:
        encoded = json.dumps(payload, allow_nan=False)
    except ValueError:
        # The previous literal transport accepted non-finite numbers. Preserve
        # those values without teaching JSON.parse a nonstandard JSON dialect.
        # Round-trip first for json.dumps' existing tuple/key/type semantics.
        value = json.loads(json.dumps(payload))
        assignments = []

        def finite(item, path):
            if isinstance(item, float) and not math.isfinite(item):
                assignments.append(f"{path}={json.dumps(item)};")
                return None
            if isinstance(item, dict):
                return {
                    key: finite(child, f"{path}[{json.dumps(key)}]")
                    for key, child in item.items()
                }
            if isinstance(item, list):
                return [finite(child, f"{path}[{i}]") for i, child in enumerate(item)]
            return item

        encoded = json.dumps(finite(value, "value"), allow_nan=False)
        return (
            "(function(value){" + "".join(assignments) + "return value;})("
            f"JSON.parse({json.dumps(encoded)}))"
        )
    return f"JSON.parse({json.dumps(encoded)})"


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

# The sig bar's focus-gate cadence. Sub-second like the preview sweep, so
# alt-tabbing between clients flips the bar about as fast as the previews
# flip their focus rings. Each tick is one GetForegroundWindow read plus a
# settings lookup; a native ShowWindow only happens on a real transition.
SIG_BAR_FOCUS_POLL_S = 0.7

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


class _FleetVisibilityNoChange(Exception):
    """End a settings transaction without turning an idempotent request into a save."""


class _FleetVisibilityRefused(Exception):
    """Reject a visibility mutation from inside its serialized settings transaction."""


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


# Shared authority warnings come from startup migration/load paths and are
# replayed on demand through a state read, not a one-shot dialog. Keep them
# bounded per entry and in count, matching the Skills route's payload-sized
# posture and the authority controller's 500-character notice cap.
EVE_CHARACTERS_MAX_WARNINGS = 20
EVE_CHARACTERS_MAX_TEXT_CHARS = 500


def _bound_eve_characters_text(text: str) -> str:
    return text[:EVE_CHARACTERS_MAX_TEXT_CHARS]


def _bound_eve_characters_warnings(warnings=None) -> list[str]:
    if warnings is None:
        return []
    return [
        _bound_eve_characters_text(warning)
        for warning in warnings[:EVE_CHARACTERS_MAX_WARNINGS]
    ]


def _empty_eve_characters_state(warnings=None) -> dict:
    """The shared character-management answer when no authority exists."""
    raw_warnings = list(
        warnings or ["The shared EVE character authority is unavailable."]
    )
    return {
        "available": False,
        "auth_configured": eveauth_application.is_configured(),
        "authorization_activity": "idle",
        "authorization_notice": "",
        "characters": [],
        "warnings": _bound_eve_characters_warnings(raw_warnings),
    }


def _empty_skills_state(warnings=None) -> dict:
    """The state payload when there is no controller at all.

    Same keys as the real one so skills.js has exactly one renderer. A
    payload that drops fields when the subsystem is absent means every
    access in the page needs a guard, and the one that gets forgotten
    throws inside a click handler with no console attached.
    """
    return {
        "refresh_in_flight": False,
        "selected_plan_name": "",
        "selected_group": "",
        "groups": [],
        "plans": [],
        "characters": [],
        "plan_issues": [],
        "warnings": list(warnings or ["The EVE skills subsystem is unavailable."]),
        "plans_updated_utc": "",
    }


def _empty_fittings_state(warnings=None) -> dict:
    """The Fittings route's answer when no controller is wired.

    Task 9 replaces the Task 6 stub with real `self._fittings.workspace(...)`
    delegation; this remains only the safe fallback for a build where the
    Fittings subsystem failed to construct (see `build_fittings_controller`).
    Same `warnings`-list convention as `_empty_skills_state`, so the one
    real payload shape (task 9's `workspace()`) can carry the same key
    without the page needing a second renderer.
    """
    return {
        "available": False,
        "warnings": list(warnings or ["The EVE fitting library is not available yet."]),
    }


class _SettingUnchanged(Exception):
    """Exit a serialized no-op without rewriting the complete settings file."""


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
        telemetry=None,
        authority=None,
        fittings=None,
        authority_warnings=(),
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
        # Independent display-only Fleet window. Like the sig bar this must
        # stay private or pywebview recursively walks its WinForms native.
        self._fleetbar_window = None
        self._fleetbar_ready = False
        # LOCK ORDER: shutdown_lock -> _fleetbar_lifecycle_lock ->
        # _fleet_presentation_lock. The settings save lock and this lock are
        # never nested, and evaluate_js is never called while this lock is
        # held. A dispatcher callback may otherwise race a mode transition
        # and restore rows from the retired telemetry activation.
        self._fleet_presentation_lock = threading.Lock()
        self._fleet_expected_generation = None  # rejecting sentinel
        self._fleet_presentation_revision = 0
        self._fleet_roster_signature = None
        self._fleet_roster = RosterMemory()
        self._fleet_snapshot = None
        self._fleet_unsubscribe = None
        self._fleet_activation = 0
        self._fleet_settings_dirty = False
        # Construction is inert. Main starts the owner before subscribing;
        # the dispatcher only folds state and sets its wakeup bit.
        self._fleet_worker = FleetPresentationWorker(self._present_fleet_snapshot)
        # pywebview serves bridge calls concurrently. Window construction,
        # show/hide, page-ready reveal, and shutdown must have one lifecycle
        # owner or a late enable can orphan an untracked topmost WebView.
        self._fleetbar_lifecycle_lock = threading.RLock()
        self._fleetbar_quitting = False
        # Creation, assignment, showing, delayed reveal, and shutdown's
        # destroy/clear are one lifecycle transaction at a time. RLock lets
        # toggle_sig_bar hold the boundary while sigbar.create enforces it
        # independently for startup restore.
        #
        # LOCK ORDER: main's shutdown_lock, then this lock. Sig-bar code never
        # takes shutdown_lock, and neither lock is held while claiming the work
        # gate; updater handoff marks quitting before it requests teardown.
        self._sigbar_lifecycle_lock = threading.RLock()
        self._sigbar_quitting = False
        # The focus-gate timer (see _schedule_sig_bar_focus_poll): one
        # chained threading.Timer while the bar is enabled, None while not.
        # Guarded by _sigbar_lifecycle_lock so arm/disarm never interleaves
        # with a toggle or shutdown mid-decision.
        self._sigbar_focus_timer = None
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

        # None off the happy path -- when the subsystem failed to build, and
        # in most tests. Every call site below tolerates its absence and
        # returns a safe value, which is what lets the page render the route
        # without probing for a capability first.
        self._skills = skills
        self._authority = authority
        # Wired after shared authority composition in production. Task 9 turns
        # the existing safe route stub into thin delegation; until then merely
        # retaining this private dependency must not change public bridge APIs.
        self._fittings = fittings
        # Migration/load failures must survive until the route asks for state;
        # pushing a dialog during construction happens before WebView handlers
        # exist and silently drops the only actionable recovery message.
        self._authority_warnings = list(authority_warnings)

        # Shared client/log infrastructure. None off Windows, in most tests,
        # or when optional construction failed; every call site degrades to
        # an inert preview/alert/fleet state.
        self._telemetry = telemetry

        self._spawn = spawn
        self._timer = timer
        self._update_service = update_service
        self._update_spawn = update_spawn
        self._is_frozen = is_frozen
        # Assigned by main() once its idempotent window teardown exists.
        # Tests and partial construction leave it unset; a successful native
        # launch still closes its process handle and owns the work gate.
        self._request_shutdown = None

        # The claim exists before a worker handle and survives through its
        # target's finally. Thread liveness has a pre-start gap and therefore
        # cannot arbitrate concurrent pywebview bridge calls.
        #
        # Constructed HERE, once, and handed to the uploader controller
        # below: the upload claim is taken there, while the updater's
        # handoff claim and Quit's claim are taken in this module. One
        # object is what makes those three exclude each other; see
        # WorkGate's docstring for why it was not moved with the uploader.
        self._work_gate = WorkGate()
        self._update_lock = threading.Lock()
        self._update = _UpdateRuntime()
        self._update_staging_cleaned = False
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
        self._preview_mode_lock = threading.Lock()
        self._preview_mode_changing = False
        # The uploader owns the rows, the durations cache, the link store
        # and every upload/log worker handle; the bridge keeps facades. Built
        # after the work gate, the dialog registry and the effect
        # collaborators it adapts, and before Profiles for no reason other
        # than that the Profiles guard checks it is the last thing bound.
        self._uploader = self._build_uploader_controller(
            rows=rows,
            durations_file=durations_file,
            links_file=links_file,
            drain_interval_s=drain_interval_s,
            probe=probe,
        )
        # Bind only after the worker and runtime collaborators exist. The
        # adapters resolve the window and replaceable effects when invoked;
        # construction itself must not touch the page or start Profiles work.
        self._profiles = self._build_profiles_controller()

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
        script = f"window.{handler} && window.{handler}({_page_payload(payload)})"
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

    def _push_fittings_changed(self, payload) -> None:
        """Literal adapter for FittingsController's `changed` callback.

        No presentation labels to add (unlike `_push_skills`): the payload
        is a small semantic reason/id, never a rendered fitting list --
        "no whole-library pushes" is the binding rule this method exists to
        keep. The page re-queries `fittings_state` for whatever it is
        currently viewing; this only tells it something changed.
        """
        self._push("onFittingsChanged", payload)

    def _push_fittings_progress(self, payload) -> None:
        """Literal adapter for FittingsController's `progress` callback."""
        self._push("onFittingsProgress", payload)

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

    # ----- Uploader ---------------------------------------------------------

    def _build_uploader_controller(
        self, *, rows, durations_file, links_file, drain_interval_s, probe
    ) -> UploaderController:
        return UploaderController(
            self._state,
            gate=self._work_gate,
            ports=UploaderPorts(
                publish_rows=self._publish_rows,
                publish_log_post_running=self._publish_log_post_running,
                publish_row_renamed=self._publish_row_renamed,
                publish_duration=self._publish_duration,
                publish_link=self._publish_link,
                publish_cancel_available=self._publish_cancel_available,
                publish_retry_available=self._publish_retry_available,
                publish_upload_done=self._publish_upload_done,
                publish_channel=self._publish_channel,
                publish_auth=self._uploader_publish_auth,
                status=self._uploader_status,
                progress=self._uploader_progress,
                alert=self._uploader_alert,
                confirm=self._uploader_confirm,
                spawn=self._spawn_uploader_worker,
                watcher=self._uploader_watcher,
                update_preparing=self._uploader_update_preparing,
                format_selection_summary=copy_mod.format_selection_summary,
                format_title_hint=copy_mod.format_title_hint,
                format_upload_confirm=copy_mod.format_upload_confirm,
                format_progress=copy_mod.format_progress,
                format_upload_cancelled=copy_mod.format_upload_cancelled,
                format_destination=copy_mod.format_destination,
            ),
            rows=rows if rows is not None else RowSnapshot(),
            scheduler=Scheduler,
            durations_file=durations_file,
            links_file=links_file,
            drain_interval_s=drain_interval_s,
            probe=probe,
            timer=self._timer,
        )

    def _publish_rows(self, payload: dict) -> None:
        self._push("onRows", payload)

    def _publish_log_post_running(self, payload: dict) -> None:
        self._push("onLogPostRunning", payload)

    def _publish_row_renamed(self, payload: dict) -> None:
        self._push("onRowRenamed", payload)

    def _publish_duration(self, payload: dict) -> None:
        self._push("onDuration", payload)

    def _publish_link(self, payload: dict) -> None:
        self._push("onLink", payload)

    def _publish_cancel_available(self, payload: dict) -> None:
        self._push("onCancelAvailable", payload)

    def _publish_retry_available(self, payload: dict) -> None:
        self._push("onRetryAvailable", payload)

    def _publish_upload_done(self, payload: dict) -> None:
        self._push("onUploadDone", payload)

    def _publish_channel(self, payload: dict) -> None:
        self._push("onChannel", payload)

    def _uploader_publish_auth(self, state: str) -> None:
        self._push_auth(state)

    def _uploader_status(self, text: str, kind: str = "FG", *, busy=None) -> None:
        self._status(text, kind, busy=busy)

    def _uploader_progress(
        self,
        pct: float,
        text: str = "",
        kind: str = "FG",
        *,
        mode="determinate",
        busy=None,
    ) -> None:
        self._progress(pct, text, kind, mode=mode, busy=busy)

    def _uploader_alert(self, kind: str, title: str, body: str) -> None:
        self._alert(kind, title, body)

    def _uploader_confirm(
        self, title: str, body: str, *, destructive: bool = False, confirm_label=None
    ) -> bool:
        return self._confirm(
            title, body, destructive=destructive, confirm_label=confirm_label
        )

    def _spawn_uploader_worker(self, **kwargs):
        # Forwarded verbatim rather than normalised to (target, args,
        # daemon): the probe worker spawns with no `args`, and the inline
        # thread double test_api.py injects takes none either.
        return self._spawn(**kwargs)

    def _uploader_watcher(self):
        # Resolved per call: __main__ assigns _watcher after construction.
        return self._watcher

    def _uploader_update_preparing(self, *, show_window: bool) -> None:
        self._update_installation_preparing(show_window=show_window)

    def list_rows(self, preselect: set | None = None) -> None:
        return self._uploader.list_rows(preselect)

    def panel_text(self, ids: list[str], stitch: bool) -> dict:
        return self._uploader.panel_text(ids, stitch)

    def delete_selected(self, ids) -> None:
        return self._uploader.delete_selected(ids)

    def copy_path(self, row_id: str) -> str:
        return self._uploader.copy_path(row_id)

    def open_path(self, row_id: str) -> None:
        return self._uploader.open_path(row_id)

    def play_recording(self, row_id: str) -> None:
        return self._uploader.play_recording(row_id)

    def rename_recording(self, row_id: str, stem: str) -> dict:
        return self._uploader.rename_recording(row_id, stem)

    def open_recording_dir(self) -> bool:
        return self._uploader.open_recording_dir()

    def start_upload(self, title, description, stitch, ids) -> None:
        return self._uploader.start_upload(title, description, stitch, ids)

    def cancel_upload(self) -> None:
        return self._uploader.cancel_upload()

    def retry(self) -> None:
        return self._uploader.retry()

    def post_recent_logs(self) -> None:
        return self._uploader.post_recent_logs()

    # ----- upload, quit and the shared gate ----------------------------------

    def _busy(self) -> bool:
        """Is a VIDEO UPLOAD running?

        UploaderController.busy owns the answer and the reasoning for why
        it is deliberately not widened to the combat-log post. It stays
        reachable here as a private method because `__main__.poll_tick`
        reads it to defer a list rebuild, and `_status`/`_progress` above
        read it to default the strip's `busy` flag.
        """
        return self._uploader.busy()

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
                copy_mod.format_quit_confirm(self._uploader.last_pct()),
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
        self._cleanup_update_staging_once()
        self._start_update_check(automatic=True)

    def _cleanup_update_staging_once(self) -> None:
        with self._update_lock:
            if self._update_staging_cleaned:
                return
            # Claim the attempt before I/O. A locked staging directory is retried
            # on the next launch, not repeatedly during this one.
            self._update_staging_cleaned = True
        try:
            self._update_service.cleanup_staging(self._update_staging_root())
        except Exception:
            logger.warning("Could not clean updater staging at startup", exc_info=True)

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
        # WorkGate, and avoids nesting the two locks.
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
                # Setup is already launched and classified by its on-disk
                # handoff marker. Per-window teardown failures are handled
                # inside the retryable callback;
                # an unexpected boundary failure still cannot roll back Setup.
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
        try:
            with settings_mod.update(self._state.settings) as doc:
                # Decide under serialization: an unlocked comparison can
                # acknowledge another writer's value before it rolls back.
                if doc.get(key) == value:
                    raise _SettingUnchanged
                doc[key] = value
        except _SettingUnchanged:
            return self._field_ok()
        except OSError:
            # update() rolled back; reporting session-only success would
            # leave the control showing a value the runtime does not use.
            logger.exception("Could not persist %s", key)
            return self._field_refused("Could not save this to settings.")
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
        .enabled, preview.enabled, and fleet_bar.enabled stay the sole
        runtime switches.

        The guard is the whole design. Hiding a feature that is RUNNING
        would conceal its off switch -- previews would keep painting,
        eighteen global keybinds would keep firing in EVE, or the fleet
        bar would keep running, with no reachable control to stop them.
        Making this a kill switch instead was rejected: it would silently
        stop those from what reads as a display preference, and re-enabling
        could not know which of the three to restore without additional
        persisted values.

        So it simply refuses while any of the three is on, and says which.
        Turning them off first is one extra step, and it is the honest
        order -- that friction is what stops this being a kill switch by
        accident.
        """
        enabled = bool(enabled)
        if not enabled:
            running = []
            if self._state.settings.get("eve_bookmarks", {}).get("enabled"):
                running.append("Bookmarks")
            if self._state.settings.get("preview", {}).get("enabled"):
                running.append("Previews")
            if self._state.settings.get("fleet_bar", {}).get("enabled"):
                running.append("Fleet Bar")
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
        ever shows or hides -- except the first time, and except after
        the window was destroyed out from under us (see _sig_bar_alive).
        """
        from wingman.ui import sigbar

        on = bool(on)
        settings_mod.update_section(self._state.settings, "sig_bar", {"enabled": on})
        shown = False
        try:
            with self._sigbar_lifecycle_lock:
                bar = self._sigbar_window
                logger.info(
                    "Sig bar toggle: requested %s, window %s.",
                    on,
                    "exists" if bar is not None else "not built yet",
                )
                if not self._sigbar_quitting:
                    if on:
                        # is_alive, not `is None`: a destroyed window
                        # leaves the Python object behind, and a toggle
                        # at the corpse must rebuild rather than report
                        # success at nothing. create() builds the bar
                        # hidden and styled; reveal_bar shows it without
                        # activating (pywebview's show() would steal the
                        # foreground from the client being flown).
                        if not sigbar.is_alive(bar):
                            bar = sigbar.create(self)
                        if bar is not None:
                            sigbar.reveal_bar(bar)
                            shown = True
                    elif sigbar.is_alive(bar):
                        sigbar.hide_bar(bar)
        except Exception:
            # A bar that cannot appear is degraded chrome, not a failed
            # setting: the persisted choice stands and the next toggle
            # retries the window.
            logger.exception("sig bar window toggle failed")
        if shown:
            # The poll can be up to 3s away; a bar that opens empty for 3s
            # reads as broken. The page pulls nothing at load, so this push
            # is its content.
            self._push_eve_status()
            # Arm the focus gate ONLY on a successful reveal, then apply it
            # once so an enable while a non-allowed client holds the
            # foreground hides the freshly revealed bar immediately
            # instead of one tick later. A toggle that was refused
            # (shutdown won the lifecycle) must not arm: the chain
            # outlives the call and would tick at a quitting process.
            self._schedule_sig_bar_focus_poll()
            self._apply_sig_bar_focus_gate()
        elif not on:
            # Disarm on a clean toggle-off. A refused toggle-on leaves any
            # existing chain alone -- if the bar never showed there is
            # nothing to disarm, and shutdown disarms its own way.
            self._schedule_sig_bar_focus_poll()
        logger.info(
            "Sig bar toggle done: enabled=%s, visible=%s.",
            self._state.settings["sig_bar"]["enabled"],
            self._sig_bar_visible(),
        )
        self._push_sig_bar_state()
        return self._field_ok()

    def _sig_bar_focus_allows(self) -> bool:
        """Whether the foreground may currently show the sig bar.

        The rule the feature ships with: `sig_bar.enabled` is the master
        toggle, and the eve_bookmarks window checkboxes are the per-client
        allowlist -- the bar shows only while an EVE client whose checkbox
        is checked holds the foreground.

        The inert case is "no box CHECKED", not "map empty": the bookmarks
        tab persists every live window as an entry, unchecked boxes stored
        as False, so a user who has merely OPENED that tab with EVE
        running has an all-False map. Reading that as "scoped" hid the
        bar from a user who never opted in -- shipped as "the bar does
        not show at all" in the first test build. The gate engages only
        when at least one client is actually checked.

        Identity is the full `EVE - <name>` title, exactly the key the
        bookmarks tab persists -- no name stripping here, or a client at
        character-select (whose title is not yet an engine title) would
        drift from the checkbox that names it.
        """
        windows = (self._state.settings.get("eve_bookmarks") or {}).get("windows")
        if not windows or not any(windows.values()):
            return True
        title = evewindows.focused_eve_title()
        return bool(title and windows.get(title))

    def _apply_sig_bar_focus_gate(self) -> None:
        """Show/hide the live bar to match the focus rule, if it differs.

        Runs on the focus timer's thread and after every toggle; both are
        off the UI thread, and reveal_bar/hide_bar are plain ShowWindow
        calls that pump nothing (ui/sigbar.py's native-show note). The
        lifecycle lock keeps a toggle or a shutdown from interleaving with
        the decision -- a gate that re-shows a bar the user just toggled
        off, or reveals one quitting is destroying.
        """
        from wingman.ui import sigbar

        if not (self._state.settings.get("sig_bar") or {}).get("enabled"):
            return
        with self._sigbar_lifecycle_lock:
            if self._sigbar_quitting:
                return
            bar = self._sigbar_window
            if not sigbar.is_alive(bar):
                return
            allowed = self._sig_bar_focus_allows()
            if allowed and not sigbar.is_visible(bar):
                sigbar.reveal_bar(bar)
            elif not allowed and sigbar.is_visible(bar):
                sigbar.hide_bar(bar)

    def _schedule_sig_bar_focus_poll(self) -> None:
        """(Re)arm the chained focus-gate timer, or disarm it.

        Called after every toggle, at launch restore, and at shutdown: the
        timer exists exactly while the bar is enabled and the process is
        not quitting. Chained threading.Timers rather than one loop
        thread, matching sigbar.restore's timer idiom: each tick is
        self-scheduling, so disarm is always just `cancel()`.

        RLock note: the tick re-enters this method, and the lock is an
        RLock by design (toggle_sig_bar holds the boundary while
        sigbar.create enforces it independently), so the re-entry is safe.
        """
        with self._sigbar_lifecycle_lock:
            if self._sigbar_focus_timer is not None:
                self._sigbar_focus_timer.cancel()
                self._sigbar_focus_timer = None
            enabled = bool((self._state.settings.get("sig_bar") or {}).get("enabled"))
            if self._sigbar_quitting or not enabled:
                return
            timer = threading.Timer(SIG_BAR_FOCUS_POLL_S, self._sig_bar_focus_tick)
            # Daemon, unlike sigbar.restore's one-shot: this chain lives
            # for the session and re-arms itself, and a test (or a
            # shutdown path that somehow skips the disarm) must never park
            # interpreter exit on the next tick.
            timer.daemon = True
            self._sigbar_focus_timer = timer
        timer.start()

    def _sig_bar_focus_tick(self) -> None:
        """One focus-gate cadence: re-arm first, then decide.

        Re-arming before the gate runs keeps one exception in the gate
        from killing the chain for the rest of the session -- the next
        tick still fires, and the log carries the failure.
        """
        self._schedule_sig_bar_focus_poll()
        try:
            self._apply_sig_bar_focus_gate()
        except Exception:
            logger.exception("sig bar focus gate failed")

    @staticmethod
    def _sig_bar_alive(bar) -> bool:
        """Whether the bar window can still be shown or hidden.

        Retired in favour of sigbar.is_alive (IsWindow on the HWND): the
        closed-event walk this replaced needed attribute-shape guesses
        over test fakes, while a handle check is one syscall and covers
        every teardown route. Kept as a thin delegate so the existing
        log-line helper and any page-side callers keep their name.
        """
        from wingman.ui import sigbar

        return sigbar.is_alive(bar)

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
        from wingman.ui import sigbar

        bar = self._sigbar_window
        if bar is None:
            return
        # NEVER resize a hidden bar: pywebview's resize is a raw
        # SetWindowPos carrying SWP_SHOWWINDOW, so a fit against a hidden
        # window SHOWS it. The page renders on every push -- including the
        # 3s poll aimed at a bar the user toggled off -- and each render
        # re-fits, which is how a toggled-off bar kept reappearing on the
        # next poll with the GUI still reporting it off. The reveal path
        # pushes status the moment it shows the bar, so the first fit a
        # visible bar receives is only ever one tick away.
        if not sigbar.is_visible(bar):
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

    # ----- floating Fleet DPS/EWAR bar ---------------------------------

    def _next_fleet_revision_locked(self) -> int:
        self._fleet_presentation_revision += 1
        return self._fleet_presentation_revision

    @staticmethod
    def _fleet_unique_names(names) -> list[str]:
        """Keep the first spelling and order from one persisted roster tier."""
        return list(dict.fromkeys(name for name in names if isinstance(name, str)))

    def _fleet_characters_locked(self, section: dict) -> list[dict]:
        snapshot = self._fleet_snapshot
        running = None if snapshot is None else {row.character for row in snapshot.rows}
        names = set(section.get("seen") or ())
        names.update(section.get("hidden") or ())
        names.update(self._fleet_roster.pending)
        if running is not None:
            names.update(running)
        hidden = set(section.get("hidden") or ())
        key = (
            (lambda name: (name.casefold(), name))
            if running is None
            else (lambda name: (name not in running, name.casefold(), name))
        )
        return [
            {
                "name": name,
                "running": None if running is None else name in running,
                "visible": name not in hidden,
            }
            for name in sorted(names, key=key)
            if isinstance(name, str)
        ]

    def _fleet_settings_payload_locked(self, section: dict, revision: int) -> dict:
        payload = {
            "enabled": bool(section.get("enabled")),
            "x": section.get("x"),
            "y": section.get("y"),
            "seen": list(section.get("seen") or ()),
            "hidden": list(section.get("hidden") or ()),
            "revision": revision,
        }
        payload["characters"] = self._fleet_characters_locked(section)
        return payload

    def _fleet_display_payload_locked(
        self, snapshot, section: dict, revision: int
    ) -> dict:
        if snapshot is None:
            return {
                "rows": [],
                "running_count": 0,
                "revision": revision,
                "stream_health": {"state": "stopped", "detail": None},
                "metric_error": None,
            }
        hidden = set(section.get("hidden") or ())
        return {
            "rows": [
                {
                    "character": row.character,
                    "dps": row.dps,
                    "ewar": list(row.ewar),
                    "log_status": row.log_status,
                }
                for row in snapshot.rows
                if row.character not in hidden
            ],
            "running_count": len(snapshot.rows),
            "revision": revision,
            "stream_health": {
                "state": snapshot.stream_health.state,
                "detail": snapshot.stream_health.detail,
            },
            "metric_error": snapshot.metric_error,
        }

    def _fleet_payloads_locked(self) -> tuple[dict, dict]:
        section = dict(self._state.settings.get("fleet_bar") or {})
        revision = self._fleet_presentation_revision
        return (
            self._fleet_settings_payload_locked(section, revision),
            self._fleet_display_payload_locked(self._fleet_snapshot, section, revision),
        )

    def fleet_bar_settings(self) -> dict:
        """Immutable Fleet settings and roster state for the main-page controls."""
        with self._fleet_presentation_lock:
            settings_payload, _ = self._fleet_payloads_locked()
        return settings_payload

    def _push_fleet_bar_state(self) -> None:
        # Always read the latest state on the presentation owner. A bridge
        # caller may still hold the native lifecycle lock here.
        self._queue_fleet_presentation(settings_changed=True)

    def fleet_bar_snapshot(self) -> dict:
        """Current complete display payload, also used by the bar at boot."""
        with self._fleet_presentation_lock:
            _, display_payload = self._fleet_payloads_locked()
        return display_payload

    def _push_fleet_snapshot(self, payload: dict, delivery: FleetDelivery) -> None:
        # Never look up a new bar after an earlier stage waited in WebView.
        bar = delivery.fleetbar
        if bar is None or not self._fleet_delivery_current(delivery):
            return
        script = (
            f"window.onFleetSnapshot && window.onFleetSnapshot({json.dumps(payload)})"
        )
        try:
            bar.evaluate_js(script)
        except Exception:
            logger.debug("Fleet Bar snapshot push failed", exc_info=True)

    def _fleet_state_push(
        self, handler: str, payload: dict, delivery: FleetDelivery
    ) -> None:
        script = f"window.{handler} && window.{handler}({_page_payload(payload)})"
        for target in (delivery.main, delivery.sigbar):
            if not self._fleet_delivery_current(delivery):
                return
            if target is not None:
                try:
                    target.evaluate_js(script)
                except Exception:
                    logger.debug("Fleet state push failed", exc_info=True)

    def _fleet_delivery_current(self, delivery: FleetDelivery) -> bool:
        with self._fleet_presentation_lock:
            return self._fleet_delivery_current_locked(delivery)

    def _fleet_delivery_current_locked(self, delivery: FleetDelivery) -> bool:
        return (
            not self._fleetbar_quitting
            and delivery.activation == self._fleet_activation
            and delivery.revision == self._fleet_presentation_revision
            and delivery.main is self._window
            and delivery.sigbar is self._sigbar_window
            and delivery.fleetbar is self._fleetbar_window
        )

    def _queue_fleet_presentation(self, *, settings_changed=False) -> None:
        with self._fleet_presentation_lock:
            if self._fleetbar_quitting:
                return
            if settings_changed:
                self._fleet_settings_dirty = True
                self._next_fleet_revision_locked()
            self._fleet_worker.notify()

    def _present_fleet_snapshot(self) -> None:
        """The worker alone performs persistence and all Fleet presentation I/O."""
        with self._fleet_presentation_lock:
            if self._fleetbar_quitting:
                return
            delivery = FleetDelivery(
                self._fleet_activation,
                self._fleet_presentation_revision,
                self._window,
                self._sigbar_window,
                self._fleetbar_window,
            )
            write = self._fleet_roster.take()
        if write is not None:
            self._remember_fleet_roster(write)
        if not self._fleet_delivery_current(delivery):
            # Target changes (notably sig-bar creation) need not publish any
            # telemetry. Preserve a wakeup even when this was the only job.
            self._queue_fleet_presentation()
            return
        with self._fleet_presentation_lock:
            settings_payload, display_payload = self._fleet_payloads_locked()
            settings_changed = self._fleet_settings_dirty
        if settings_changed:
            self._fleet_state_push("onFleetBarState", settings_payload, delivery)
        self._push_fleet_snapshot(display_payload, delivery)
        with self._fleet_presentation_lock:
            if self._fleet_delivery_current_locked(delivery):
                self._fleet_settings_dirty = False
            elif not self._fleetbar_quitting:
                self._fleet_worker.notify()

    def _remember_fleet_roster(self, write: RosterWrite) -> None:
        """Persist a folded batch; acknowledge only its captured admissions."""
        candidate = None
        try:
            with settings_mod.update(self._state.settings) as doc:
                section = dict(doc.get("fleet_bar") or {})
                persisted = list(section.get("seen") or ())
                normalized = settings_mod.validated_fleet_bar(
                    {
                        **section,
                        "seen": self._fleet_unique_names(
                            [*write.priority, *write.pending, *persisted]
                        ),
                    }
                )["seen"]
                if normalized == persisted:
                    candidate = normalized
                    raise _FleetVisibilityNoChange()
                section["seen"] = normalized
                doc["fleet_bar"] = section
            candidate = normalized
        except _FleetVisibilityNoChange:
            pass
        except OSError:
            logger.exception("Could not persist the Fleet character roster")
        finally:
            # No settings lock is held here. Later admissions (including a
            # repeat of a saved name) must survive this older acknowledgement.
            with self._fleet_presentation_lock:
                self._fleet_roster.acknowledge(write, candidate)

    def _receive_fleet_snapshot(self, snapshot) -> None:
        """Dispatcher handoff: state only, never I/O, joins or thread startup."""
        with self._fleet_presentation_lock:
            if (
                self._fleetbar_quitting
                or snapshot.activation_generation == 0
                or snapshot.activation_generation != self._fleet_expected_generation
            ):
                return
            signature = tuple(row.character for row in snapshot.rows)
            roster_changed = signature != self._fleet_roster_signature
            self._fleet_snapshot = snapshot
            self._next_fleet_revision_locked()
            self._fleet_roster_signature = signature
            if roster_changed:
                self._fleet_roster.admit(signature)
                self._fleet_settings_dirty = True
            self._fleet_worker.notify()

    def _start_fleet_presentation(self) -> bool:
        """Start before subscribing; retries never allocate a second owner."""
        with self._fleetbar_lifecycle_lock:
            if self._fleetbar_quitting or not self._fleet_worker.start():
                return False
            if self._telemetry is not None and self._fleet_unsubscribe is None:
                self._fleet_unsubscribe = self._telemetry.subscribe_fleet(
                    self._receive_fleet_snapshot
                )
            return True

    def _stop_fleet_presentation(self, timeout: float = 1.0) -> bool:
        """Close, detach, then join without holding native/presentation locks."""
        with self._fleetbar_lifecycle_lock:
            self._fleetbar_quitting = True
            self._close_fleet_presentation()
            unsubscribe = self._fleet_unsubscribe
            self._fleet_unsubscribe = None
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                logger.exception("Fleet snapshot subscriber did not detach cleanly")
        stopped = self._fleet_worker.stop(timeout)
        if not stopped:
            logger.warning("Fleet presentation worker is still stopping")
        return stopped

    def set_fleet_bar_character_visible(self, name, visible) -> dict:
        """Persist one exact character visibility choice without touching Preview."""
        if not isinstance(name, str) or not isinstance(visible, bool):
            return self._fleet_visibility_result(
                False, "Choose a character from the Fleet list."
            )
        with self._fleet_presentation_lock:
            section = dict(self._state.settings.get("fleet_bar") or {})
            known = {
                character["name"]
                for character in self._fleet_characters_locked(section)
            }
        if name not in known:
            return self._fleet_visibility_result(
                False, "Choose a character from the Fleet list."
            )
        changed = False
        try:
            with settings_mod.update(self._state.settings) as doc:
                section = dict(doc.get("fleet_bar") or {})
                hidden = list(section.get("hidden") or ())
                if visible:
                    updated = [item for item in hidden if item != name]
                    if updated == hidden:
                        raise _FleetVisibilityNoChange()
                else:
                    if name in hidden:
                        raise _FleetVisibilityNoChange()
                    if len(hidden) >= 64:
                        raise _FleetVisibilityRefused(
                            "Show a hidden character before hiding another."
                        )
                    updated = [*hidden, name]
                section["hidden"] = updated
                doc["fleet_bar"] = section
                changed = True
        except _FleetVisibilityNoChange:
            return self._fleet_visibility_result(True, None)
        except _FleetVisibilityRefused as exc:
            return self._fleet_visibility_result(False, str(exc))
        except OSError:
            logger.exception("Could not persist Fleet character visibility")
            return self._fleet_visibility_result(
                False, "Could not save Fleet character visibility."
            )
        if changed:
            with self._fleet_presentation_lock:
                self._next_fleet_revision_locked()
                settings_payload, _ = self._fleet_payloads_locked()
            self._push_fleet_bar_state()
            return {
                "applied": True,
                "persisted": True,
                "error": None,
                "state": settings_payload,
            }
        raise AssertionError("Fleet visibility transaction finished without a result")

    def _fleet_visibility_result(self, applied: bool, error: str | None) -> dict:
        return {
            "applied": applied,
            "persisted": applied,
            "error": error,
            "state": self.fleet_bar_settings(),
        }

    def _close_fleet_presentation(self):
        """Reject callbacks and retain enough state to undo an unsaved toggle."""
        with self._fleet_presentation_lock:
            accepted = (
                self._fleet_expected_generation,
                self._fleet_snapshot,
                self._fleet_roster_signature,
                self._fleet_presentation_revision,
            )
            self._fleet_activation += 1
            self._fleet_expected_generation = None
            self._fleet_snapshot = None
            self._fleet_roster_signature = None
            # Pending names survive activation boundaries until their roster
            # write succeeds; only the accepted snapshot/signature is stale.
            self._next_fleet_revision_locked()
        return accepted

    def _restore_fleet_presentation(self, accepted) -> None:
        """Restore a closed acceptance after its settings write was refused."""
        with self._fleet_presentation_lock:
            (
                self._fleet_expected_generation,
                self._fleet_snapshot,
                self._fleet_roster_signature,
                _revision,
            ) = accepted
            # Closing may already have been observed by a page. Restoring a
            # failed lifecycle transition is a new semantic presentation, not
            # permission to reuse an older revision.
            self._next_fleet_revision_locked()

    def _install_fleet_generation(self, generation: int | None) -> None:
        """Open acceptance for one coordinator reservation, still on WAITING."""
        with self._fleet_presentation_lock:
            self._fleet_activation += 1
            self._fleet_expected_generation = generation
            self._fleet_snapshot = None
            self._fleet_roster_signature = None
            self._next_fleet_revision_locked()

    def _requested_fleet_generation(self) -> int | None:
        """Read the coordinator reservation without letting recovery re-close Fleet."""
        if self._telemetry is None:
            return None
        try:
            return self._telemetry.requested_fleet_generation()
        except Exception:
            logger.exception("Could not read requested Fleet telemetry generation")
            return None

    def _reconcile_fleet_generation(self, *, transition: bool) -> int | None:
        """Reconcile Fleet without allowing a retired callback through the handoff."""
        if transition:
            # Startup enters through here too. A caller that must persist a
            # transition closes first so it can restore this acceptance on a
            # write failure; this second close keeps direct callers safe.
            self._close_fleet_presentation()
        failed = False
        generation = None
        try:
            generation = self._reconcile_eve_runtime()
        except Exception:
            # The setting is already durable. Preserve that choice, reserve
            # the coordinator's requested generation, and leave the bar in
            # WAITING instead of reviving an older accepted snapshot.
            failed = True
            logger.exception("Fleet telemetry reconciliation failed")
        finally:
            if generation is None:
                generation = self._requested_fleet_generation()
            # No failure path may leave the rejecting sentinel installed.
            self._install_fleet_generation(generation)
        if (
            not failed
            and self._telemetry is not None
            and self.fleet_bar_settings().get("enabled")
        ):
            self._receive_fleet_snapshot(self._telemetry.snapshot())
        return generation

    def toggle_fleet_bar(self, on) -> dict:
        """Serialize the persisted/runtime/window transition."""
        with self._fleetbar_lifecycle_lock:
            if self._fleetbar_quitting:
                return self._field_refused("Wingman is shutting down.")
            if on and not self._start_fleet_presentation():
                return self._field_refused("The Fleet Bar could not be opened.")
            return self._toggle_fleet_bar(bool(on))

    def _toggle_fleet_bar(self, on: bool) -> dict:
        from wingman.ui import fleetbar

        previous = bool(self._state.settings.get("fleet_bar", {}).get("enabled"))
        accepted = None
        if on != previous:
            # Close before persistence. The dispatcher can call back while
            # settings saves, but it sees the rejecting sentinel rather than
            # the prior activation. This never nests save and presentation
            # locks: _close_fleet_presentation() returns before update_section.
            accepted = self._close_fleet_presentation()
        try:
            settings_mod.update_section(
                self._state.settings, "fleet_bar", {"enabled": on}
            )
        except OSError:
            logger.exception("Could not persist the Fleet Bar setting")
            if accepted is not None:
                self._restore_fleet_presentation(accepted)
            return self._field_refused("Could not save the Fleet Bar setting.")
        if on != previous:
            self._reconcile_fleet_generation(transition=True)
        else:
            self._reconcile_eve_runtime()
        bar = self._fleetbar_window
        try:
            if on:
                if not fleetbar.is_alive(bar):
                    # The page reveals itself through fleet_bar_ready only
                    # after its first snapshot has rendered and fitted.
                    self._fleetbar_ready = False
                    bar = fleetbar.create(self, hidden=True)
                elif self._fleetbar_ready:
                    fleetbar.reveal_bar(bar)
                    self._queue_fleet_presentation()
            elif fleetbar.is_alive(bar):
                fleetbar.hide_bar(bar)
        except Exception:
            logger.exception("Fleet Bar window toggle failed")
            if on:
                failed = self._fleetbar_window
                self._fleetbar_window = None
                self._fleetbar_ready = False
                if failed is not None:
                    try:
                        failed.destroy()
                    except Exception:
                        logger.debug("Failed Fleet Bar did not destroy", exc_info=True)
                # A display feature that did not display is not enabled.
                # Close before the rollback write for the same reason as an
                # ordinary toggle: callbacks during persistence must not
                # repaint this just-failed activation with old rows.
                self._close_fleet_presentation()
                try:
                    settings_mod.update_section(
                        self._state.settings, "fleet_bar", {"enabled": False}
                    )
                except OSError:
                    # update() restores the live section to enabled=True, so
                    # below must reopen the existing requested generation.
                    logger.exception(
                        "Could not roll back the Fleet Bar setting after window creation failed"
                    )
                finally:
                    # Reconcile whichever setting is now authoritative. This
                    # is deliberately in finally: a second save failure used
                    # to strand callbacks behind _close_fleet_presentation().
                    self._reconcile_fleet_generation(transition=False)
                    self._push_fleet_bar_state()
                return self._field_refused("The Fleet Bar could not be opened.")
        self._push_fleet_bar_state()
        return self._field_ok()

    def fleet_bar_ready(self) -> None:
        """Reveal the current enabled page after its first successful fit."""
        from wingman.ui import fleetbar

        with self._fleetbar_lifecycle_lock:
            bar = self._fleetbar_window
            if self._fleetbar_quitting or not fleetbar.is_alive(bar):
                return
            # Readiness belongs to this page instance, not to today's toggle
            # state. If the user disabled it during boot, a later re-enable
            # can show the already-fitted page without waiting for an event
            # the page emits only once.
            self._fleetbar_ready = True
            if not self.fleet_bar_settings().get("enabled"):
                return
            try:
                fleetbar.reveal_bar(bar)
                self._queue_fleet_presentation()
            except Exception:
                logger.exception("Fleet Bar window could not be revealed")
                self._toggle_fleet_bar(False)

    def save_fleet_bar_pos(self, x, y) -> None:
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return
        settings_mod.update_section(self._state.settings, "fleet_bar", {"x": x, "y": y})

    def move_fleet_bar(self, x, y) -> None:
        """Keep dynamic growth inside the current browser-reported work area."""
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return
        with self._fleetbar_lifecycle_lock:
            bar = self._fleetbar_window
            if (
                bar is None
                or self._fleetbar_quitting
                or not self.fleet_bar_settings().get("enabled")
            ):
                return
            try:
                bar.move(x, y)
            except Exception:
                logger.debug("Fleet Bar visibility move failed", exc_info=True)
                return
            settings_mod.update_section(
                self._state.settings, "fleet_bar", {"x": x, "y": y}
            )

    def fit_fleet_bar(self, width, height) -> None:
        """Resize to measured content without resurrecting a disabled bar."""
        try:
            width, height = int(width), int(height)
        except (TypeError, ValueError):
            return
        if width <= 0 or height <= 0:
            return
        for _ in range(12):
            with self._fleetbar_lifecycle_lock:
                bar = self._fleetbar_window
                if (
                    bar is None
                    or self._fleetbar_quitting
                    or not self.fleet_bar_settings().get("enabled")
                ):
                    return
                try:
                    bar.resize(width, height)
                except Exception:
                    logger.debug("Fleet Bar resize failed", exc_info=True)
                try:
                    if abs(bar.width - width) <= 1 and abs(bar.height - height) <= 1:
                        return
                except Exception:  # noqa: BLE001 -- headless/test windows may expose no readable native size; the resize call remains the contract.
                    return
            time.sleep(0.25)
        logger.debug("Fleet Bar resize never stuck at %sx%s", width, height)

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
            # none of: shared telemetry reads gamelogs_dir through the same
            # folder callable reconcile() re-evaluates, so a repointed
            # or newly-set folder is exactly the case that used to persist
            # while nothing ever polled it.
            self._reconcile_eve_runtime()
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
            result = dict(result, note=folder_note(folder, suppressed))
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

    def _reconcile_eve_runtime(self) -> int | None:
        """Bring the sole shared EVE telemetry runtime in line with settings."""
        if self._telemetry is not None:
            return self._telemetry.reconcile()
        return None

    def start_previews_if_enabled(self) -> None:
        """Start Preview if enabled, then reconcile all shared EVE telemetry.

        Fleet can independently start discovery and gamelog workers while
        Preview stays off. The preview pump and foreground hook remain lazy.
        """
        if self._preview_host is None:
            self._start_fleet_telemetry_if_enabled()
            return
        section = self._state.settings.get("preview", {})
        # Pushed before start(): the first registration pass runs inside
        # start(), and a table applied only after it would leave every
        # binding unregistered until the next explicit save.
        self._preview_host.set_hotkeys(section.get("hotkeys") or {})
        if section.get("enabled"):
            self._preview_host.start()
        # After host start(), so Preview roster delivery has a live pump.
        # Telemetry follows this committed runtime, not tentative settings I/O.
        self._start_fleet_telemetry_if_enabled()

    def _start_fleet_telemetry_if_enabled(self) -> None:
        """Reserve and sample Fleet only when its persisted mode is enabled."""
        if self.fleet_bar_settings().get("enabled"):
            self._reconcile_fleet_generation(transition=True)
        else:
            self._reconcile_eve_runtime()

    def set_preview_enabled(self, enabled: bool) -> bool:
        # A reservation, not a lock held across settings I/O, stop.join or page
        # callbacks. Concurrent bridge calls must not read a tentative master
        # setting or reorder runtime delivery after their transactions.
        with self._preview_mode_lock:
            if self._preview_mode_changing:
                return False
            self._preview_mode_changing = True
        try:
            return self._set_preview_enabled(bool(enabled))
        finally:
            with self._preview_mode_lock:
                self._preview_mode_changing = False

    def _set_preview_enabled(self, enabled: bool) -> bool:
        """Toggle previews and persist the choice.

        start() and stop() are both idempotent, so a double-click on the
        checkbox cannot orphan a second pump owning HWNDs that nothing
        will tear down.
        """
        enabled = bool(enabled)
        if (
            enabled
            and self._preview_host is not None
            and self._preview_host.is_stopping
        ):
            return False
        try:
            with settings_mod.update(self._state.settings) as cfg:
                section = cfg.setdefault("preview", {})
                if section.get("enabled") == enabled:
                    raise _SettingUnchanged
                section["enabled"] = enabled
        except _SettingUnchanged:
            # True, not None: a serialized no-op is success, but must not
            # rewrite the document or restart an already-running host.
            return True
        except OSError:
            # Only a committed master setting authorizes runtime changes.
            logger.exception("Could not persist the preview setting")
            return False
        if self._preview_host is not None:
            if enabled:
                self._preview_host.start()
            else:
                self._preview_host.stop()
        self._reconcile_eve_runtime()
        # Truthy on success: WM.send resolves to null on a bridge failure
        # and cannot otherwise distinguish that from a method that simply
        # returned None (settings.js:181 documents the same trap).
        return True

    def push_preview_crops(self, state: dict) -> None:
        """Semantic committed state; safe before a crop page handler is registered."""
        self._push("onPreviewCrops", state)

    def shutdown_previews(self) -> None:
        """Tear the preview thread down on the way out.

        Runs on every exit path, so like shutdown_engine() it must never
        be the thing that raises. A stop() that does not happen leaves a
        thread owning HWNDs and Wingman lingering in Task Manager after
        it has left the tray.
        """
        if self._preview_host is not None:
            try:
                self._preview_host.stop(final=True)
            except Exception:
                logger.exception("Preview host did not stop cleanly")
        # Also called by main before native destruction. Idempotence covers
        # headless shutdown and retries after a blocked presentation owner.
        self._stop_fleet_presentation()
        if self._telemetry is not None:
            try:
                self._telemetry.stop()
            except Exception:
                logger.exception("EVE telemetry runtime did not stop cleanly")

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

    def get_preview_crop_state(self) -> dict:
        """Committed crop truth and retained outcomes, including missed pushes.

        The root revision orders HOST delivery, not persistence. Never rebuild
        it from settings: settings.update can expose a tentative crop dictionary.
        """
        if self._preview_host is not None:
            return self._preview_host.crop_state()
        return dict(
            revision=0,
            definitions={},
            operations={},
            statuses={},
            live_count=0,
            cap=preview_host_mod.MAX_LIVE_CROPS,
            runtime_enabled=False,
            busy=False,
        )

    def select_preview_crop(self, name) -> dict:
        """Select/reselect using the host's current named session, never an HWND."""
        return self._request_preview_crop("select", name)

    def set_preview_crop_enabled(self, name, enabled) -> dict:
        return self._request_preview_crop("enabled", name, enabled)

    def remove_preview_crop(self, name) -> dict:
        return self._request_preview_crop("remove", name)

    def _request_preview_crop(self, action, name, value=None) -> dict:
        def refused(error):
            return dict(self._field_refused(error), pending=False, operation_id=None)

        if not preview_crops.valid_owner(name):
            return refused("Choose a named character for the crop.")
        if action == "enabled" and type(value) is not bool:
            return refused("Crop enabled must be a boolean.")
        host = self._preview_host
        if host is None:
            return refused("Crops are unavailable.")
        if host.is_stopping:
            return refused("Previews are stopping.")
        state = host.crop_state()
        definition = state["definitions"].get(name)
        if action != "select" and definition is None:
            return refused("No saved crop for this character.")
        pending = any(
            op["name"] == name and op["pending"] for op in state["operations"].values()
        )
        if action == "select" and not state["runtime_enabled"]:
            return refused("Enable previews before selecting a crop.")
        if (
            (action == "select" or (action == "enabled" and value))
            and state["live_count"] >= state["cap"]
            and state["statuses"].get(name) not in ("live", "selecting", "saving")
        ):
            return refused("Crop limit reached; disable another crop first.")
        if (
            action == "enabled"
            and definition["enabled"] == value
            and not pending
            and (
                not value
                or not state["runtime_enabled"]
                or state["statuses"].get(name) == "live"
            )
        ):
            # Earlier same-owner commands have tokens even before the pump sees
            # them. A matching committed value alone is NOT a last-intent no-op.
            # Non-live runtime enables also need the pump's reservation check.
            return dict(self._field_ok(), pending=False, operation_id=None)
        # This cached precheck is only a fast refusal. The pump rechecks native
        # capacity/reservations, and the store owns admission and final outcomes.
        return host.request_crop(action, name, value)

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
            # One section hydration, with the same revised recovery snapshot as
            # the dedicated getter and onPreviewCrops. No second page round trip.
            "crops": self.get_preview_crop_state(),
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

        The no-op check shares the mutation's serialization. An unlocked
        comparison could acknowledge another writer's tentative value just
        before it rolls back. Walk `path` inside the transaction as well:
        normalization replaces nested sections on every settings write.
        """
        try:
            with settings_mod.update(self._state.settings) as doc:
                node = doc.setdefault("preview", {})
                for key in path[:-1]:
                    node = node.setdefault(key, {})
                if node.get(path[-1]) == value:
                    raise _SettingUnchanged
                node[path[-1]] = value
        except _SettingUnchanged:
            return self._field_ok()
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
        try:
            with settings_mod.update(self._state.settings) as doc:
                node = doc.setdefault("preview", {})
                if node.get("width") == width and node.get("height") == height:
                    raise _SettingUnchanged
                node["width"] = width
                node["height"] = height
        except _SettingUnchanged:
            return self._field_ok()
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
        if host.resize_all((section.get("width"), section.get("height"))) is False:
            return self._field_refused("Previews are stopping.")
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
            if host.resize_preview(name, (width, height)) is False:
                return self._field_refused("Previews are stopping.")
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
            if self._preview_host.reset_layouts() is False:
                return self._field_refused("Previews are stopping.")
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
        preview.<key> (locked, never_minimize or excluded).

        For `locked`, *member* is the desired effective lock; its difference
        from the default is resolved inside the same transaction as the
        roster read. Neither a concurrent default change nor another
        character's edit may be lost behind an accepted response.

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
        try:
            with settings_mod.update(self._state.settings) as doc:
                section = doc.setdefault("preview", {})
                if key == "locked":
                    member = member != bool(section.get("lock_default"))
                current = list(section.get(key) or [])
                if (name in current) == member:
                    raise _SettingUnchanged
                if member:
                    current.append(name)
                else:
                    current = [n for n in current if n != name]
                section[key] = current
        except _SettingUnchanged:
            return self._field_ok()
        except OSError:
            logger.exception("Could not persist preview roster %s", key)
            return self._field_refused("Could not save this to settings.")
        return self._field_ok()

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
        result = self._toggle_preview_roster("locked", name, bool(locked))
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
        self._reconcile_eve_runtime()
        return result

    def set_alert_pve_filter(self, enabled) -> dict:
        """Suppress alerts that look like NPC fire rather than a player's.

        Read live by AlertPolicy on its next telemetry batch -- no
        reconcile() needed, this cannot change whether
        the thread itself should run.
        """
        return self._write_alert_setting(("pve_filter",), bool(enabled))

    def set_alert_persist(self, enabled) -> dict:
        """Keep an alert pulsing until its preview is selected, rather
        than only for its configured duration."""
        return self._write_alert_setting(("persist_until_selected",), bool(enabled))

    def set_alert_volume(self, value) -> dict:
        """Persist how loud every alert sound is, 0-100.

        Read live by AlertPolicy on its next telemetry batch -- no
        reconcile() and no push: nothing is playing
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
        than through AlertPolicy: Test is not a gamelog event.

        NEVER persistent, regardless of persist_until_selected -- always
        `persisted: False`, on every path including success, since
        nothing is ever saved here: the user is looking at Wingman, not
        at a preview, so nothing would ever select the client to
        acknowledge it, and a persistent test alert would pulse until
        they alt-tabbed to that client by hand.

        The sound plays exactly once regardless of how many previews are
        open, matching AlertPolicy's one-sound-per-dispatched-event
        behaviour -- N previews must not mean N overlapping sounds.

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
        # Same test as the coordinator's resolver: a folder that was valid
        # and stopped being one (an unmounted drive, an unlinked OneDrive
        # folder, a settings.json carried from another machine) must show
        # the no-folder banner, not the healthy card, even though the
        # setting still holds a path.
        if folder is not None and not folder.is_dir():
            folder = None
        alerts_wanted = bool(
            self._preview_host is not None
            and section.get("enabled")
            and alerts.get("enabled")
        )
        if self._telemetry is not None and alerts_wanted:
            health = self._telemetry.stream_health()
            running = health.state in {"running", "active"}
            last_error = health.detail if health.state in {"stale", "error"} else None
            characters = list(self._telemetry.stream_characters())
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
        result = self._write_preview_setting(
            ("restore_preview_positions",), bool(enabled)
        )
        # Preserve this older endpoint's two-key result shape while sharing
        # the serialized no-op and truthful rollback handling above.
        return {"applied": result["applied"], "persisted": result["persisted"]}

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

    def _build_profiles_controller(self) -> ProfilesController:
        return ProfilesController(
            self._state.settings,
            ports=ProfilesPorts(
                publish_running=self._publish_eve_settings_running,
                publish_names=self._publish_eve_settings_names,
                publish_done=self._publish_eve_settings_done,
                alert=self._profiles_alert,
                status=self._profiles_status,
                confirm=self._profiles_confirm,
                choose_root=self._choose_eve_settings_root,
                spawn=self._spawn_profiles_worker,
                advisory_client_running=self._profiles_advisory_client_running,
                strict_client_running=self._profiles_strict_client_running,
                profile_copy_refusal=self._profiles_copy_refusal,
                backup_root=paths.eve_settings_backup_dir,
                update_settings=self._update_profiles_settings,
                format_copy_confirm=copy_mod.format_eve_copy_confirm,
                format_copy_done=copy_mod.format_eve_copy_done,
            ),
        )

    def _publish_eve_settings_running(self, payload: dict) -> None:
        self._push("onEveSettingsRunning", payload)

    def _publish_eve_settings_names(self, payload: dict) -> None:
        self._push("onEveSettingsNames", payload)

    def _publish_eve_settings_done(self, payload: dict) -> None:
        self._push("onEveSettingsDone", payload)

    def _profiles_alert(self, kind: str, title: str, body: str) -> None:
        self._alert(kind, title, body)

    def _profiles_status(self, text: str) -> None:
        self._status(text)

    def _profiles_confirm(
        self, title: str, body: str, *, destructive: bool = False
    ) -> bool:
        return self._eve_confirm(title, body, destructive=destructive)

    def _choose_eve_settings_root(self, initial: str) -> str:
        chosen = self._window.create_file_dialog(
            _folder_dialog_kind(), directory=initial
        )
        return str(chosen[0]) if chosen else ""

    def _spawn_profiles_worker(self, *, target, args=(), daemon=True):
        return self._spawn(target=target, args=args, daemon=daemon)

    def _profiles_advisory_client_running(self) -> bool:
        return self._eve_client_running()

    def _profiles_strict_client_running(self) -> bool:
        return self._eve_client_running_strict()

    def _profiles_copy_refusal(self) -> str | None:
        return self._eve_profile_copy_refusal()

    def _update_profiles_settings(self, values: dict) -> None:
        settings_mod.update_section(self._state.settings, "eve_settings", values)

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

    def eve_settings_state(self) -> dict:
        return self._profiles.state()

    def eve_settings_pick_root(self) -> str:
        return self._profiles.pick_root()

    def eve_settings_detect_root(self) -> str:
        return self._profiles.detect_root()

    def eve_settings_select(self, server: str, profile: str) -> bool:
        return self._profiles.select(server, profile)

    def eve_settings_set_account_name(self, account_id: str, name: str) -> dict:
        return self._profiles.set_account_name(account_id, name)

    def eve_settings_set_account_characters(
        self, account_id: str, character_ids: list
    ) -> dict:
        return self._profiles.set_account_characters(account_id, character_ids)

    def eve_settings_identification_start(self) -> dict:
        return self._profiles.identification_start()

    def eve_settings_identification_check(self) -> dict:
        # A worker can hold this lock while parked on a bridge confirmation.
        # Refusing preserves the bridge thread that must deliver that answer.
        return self._profiles.identification_check()

    def eve_settings_identification_confirm(
        self, account_id: str, character_id: str, account_name: str
    ) -> dict:
        return self._profiles.identification_confirm(
            account_id, character_id, account_name
        )

    def eve_settings_identification_cancel(self) -> dict:
        return self._profiles.identification_cancel()

    def eve_settings_resolve_names(self) -> None:
        return self._profiles.resolve_names()

    def eve_settings_set_auto_keep(self, value) -> dict:
        return self._profiles.set_auto_keep(value)

    def eve_settings_copy(
        self, source: str, targets: list, groups: list | None = None
    ) -> bool:
        return self._profiles.copy(source, targets, groups)

    def eve_settings_copy_profile(
        self, expected_source: str, mode: str, destination: str
    ) -> dict:
        return self._profiles.copy_profile(expected_source, mode, destination)

    def eve_settings_backup(self, path: str, kind: str) -> bool:
        return self._profiles.backup(path, kind)

    def eve_settings_restore(self, archive: str) -> bool:
        return self._profiles.restore(archive)

    def eve_settings_delete_backup(self, archive: str) -> bool:
        return self._profiles.delete_backup(archive)

    def eve_settings_formations(self, path: str) -> dict:
        return self._profiles.formations(path)

    def eve_settings_export_formations(self, items: list) -> dict:
        return self._profiles.export_formations(items)

    def eve_settings_parse_formations(self, text: str, existing_names: list) -> dict:
        return self._profiles.parse_formations(text, existing_names)

    def eve_settings_validate_formation_import(
        self, items: list, existing_names: list
    ) -> dict:
        return self._profiles.validate_formation_import(items, existing_names)

    def eve_settings_save_formations(
        self,
        path: str,
        formations: list,
        expected_content_revision: str = "",
        request_id: str = "",
    ) -> bool:
        return self._profiles.save_formations(
            path, formations, expected_content_revision, request_id
        )

    # ---- Shared EVE characters ---

    def eve_characters_state(self) -> dict:
        """The display-safe shared authority snapshot for management UI."""
        if self._authority is None:
            return _empty_eve_characters_state(self._authority_warnings)
        payload = dict(self._authority.management_state())
        payload["available"] = True
        payload["auth_configured"] = eveauth_application.is_configured()
        payload["warnings"] = _bound_eve_characters_warnings(self._authority_warnings)
        return payload

    def eve_characters_authenticate(self) -> dict:
        if self._authority is None:
            return {
                "accepted": False,
                "error": _bound_eve_characters_text(
                    "The shared EVE character authority is unavailable."
                ),
            }
        result = self._authority.start_full_authorization()
        return {
            "accepted": result.accepted,
            "error": _bound_eve_characters_text(result.error),
        }

    def eve_characters_cancel_auth(self) -> dict:
        if self._authority is None:
            return {
                "accepted": False,
                "error": _bound_eve_characters_text(
                    "The shared EVE character authority is unavailable."
                ),
            }
        result = self._authority.cancel_authorization()
        return {
            "accepted": result.accepted,
            "error": _bound_eve_characters_text(result.error),
        }

    def eve_characters_forget(self, character_id) -> dict:
        if self._authority is None:
            return {
                "applied": False,
                "persisted": False,
                "error": _bound_eve_characters_text(
                    "The shared EVE character authority is unavailable."
                ),
            }
        result = self._authority.forget(character_id)
        return {
            "applied": result.applied,
            "persisted": result.persisted,
            "error": _bound_eve_characters_text(result.error),
        }

    # ---- EVE skills ---

    def skills_state(self) -> dict:
        """Everything the Skills route renders, in one call."""
        if self._skills is None:
            return _empty_skills_state(self._authority_warnings)
        return _with_fetch_labels(self._skills.state_payload())

    # ---- EVE fittings ---

    def fittings_state(self, filters=None) -> dict:
        """The Fittings route's paged workspace: rail, roster, one page.

        A thin delegate to `FittingsController.workspace`, which owns every
        query decision (search, collection scope, sort, page bounds) --
        see the design doc's "backend owns search/collection/sort/page".
        `filters` is passed through unchanged; the controller is what
        coerces and bounds it, so a caller that hands over the wrong shape
        gets the controller's forgiving defaults rather than a second,
        divergent validation here.
        """
        if self._fittings is None:
            return _empty_fittings_state(self._authority_warnings)
        return self._fittings.workspace(filters)

    def fittings_detail(self, entry_id) -> dict | None:
        """One expanded fitting for the route's detail pane.

        None means "no such entry" (already gone, or a stale page) --
        distinct from `fittings_state`'s dict-shaped unavailable answer,
        because the detail pane has nothing to render either way and the
        page does not need to tell the two apart.
        """
        if self._fittings is None:
            return None
        return self._fittings.detail(entry_id)

    def fittings_refresh(self, character_ids=None) -> bool:
        """Start a refresh on a worker; returns before it finishes.

        Unlike Skills' `refresh_characters`, `FittingsController.refresh` is
        itself a blocking, sequential pass over every target character --
        it has no internal spawn of its own (task 8's design). Spawning
        here is what keeps this bridge call from blocking the caller for
        the length of a multi-character ESI pass; the controller's own
        `_refresh_gate` still makes concurrent refreshes single-flight, so
        a second click here just asks a controller that is already busy
        and gets its `busy` answer back on that worker instead of queuing
        a second ESI pass.
        """
        if self._fittings is None:
            return False
        ids = list(character_ids) if isinstance(character_ids, list) else None
        try:
            worker = self._spawn(
                target=self._fittings_refresh_worker, args=(ids,), daemon=True
            )
            worker.start()
        except RuntimeError:
            logger.exception("Could not start fitting refresh worker")
            self._push_fittings_changed({"reason": "refresh"})
            return False
        return True

    def _fittings_refresh_worker(self, character_ids) -> None:
        try:
            result = self._fittings.refresh(character_ids)
            if isinstance(result, dict) and result.get("error"):
                characters = result.get("characters")
                completed = len(characters) if isinstance(characters, list) else 0
                self._push_fittings_progress(
                    {
                        "kind": "refresh",
                        "phase": "complete",
                        "completed": completed,
                        "total": completed,
                        "busy": bool(result.get("busy")),
                        "error": str(result["error"]),
                    }
                )
        except Exception:
            logger.exception("Fitting refresh failed")
        finally:
            # The controller's own `changed` callback already covers a
            # resolved type-name batch; this is the one push guaranteed to
            # fire when a refresh ends, successfully or not, so the page's
            # "Refreshing..." state is never left stranded on a worker
            # that raised before reaching that callback.
            self._push_fittings_changed({"reason": "refresh"})

    # ---- EVE fittings: additive copy ---

    def fittings_preflight_copy(
        self, entry_ids, character_ids, alternate_names=None
    ) -> dict:
        if self._fittings is None:
            return {
                "accepted": False,
                "ticket_id": "",
                "created_utc": "",
                "write_count": 0,
                "counts": {
                    "ready": 0,
                    "present": 0,
                    "conflict": 0,
                    "unavailable": 0,
                },
                "requires_resolution": False,
                "pairs": [],
                "error": "The EVE fitting library is not available.",
            }
        names = alternate_names if isinstance(alternate_names, dict) else {}
        return self._fittings.preflight_copy(entry_ids, character_ids, names)

    def fittings_start_copy(self, ticket_id) -> bool:
        if self._fittings is None or not isinstance(ticket_id, str) or not ticket_id:
            return False
        try:
            worker = self._spawn(
                target=self._fittings_copy_worker, args=(ticket_id,), daemon=True
            )
            worker.start()
        except RuntimeError:
            logger.exception("Could not start fitting copy worker")
            self._push_fittings_progress(
                {
                    "kind": "copy",
                    "phase": "complete",
                    "ticket_id": ticket_id,
                    "operation_id": "",
                    "completed": 0,
                    "total": 0,
                    "result": {
                        "status": "failed",
                        "operation_id": "",
                        "results": [],
                        "write_count": 0,
                    },
                }
            )
            return False
        return True

    def _fittings_copy_worker(self, ticket_id) -> None:
        try:
            result = self._fittings.start_copy(ticket_id)
            # Normal operations publish their own progress and completion
            # through the injected callback. A refusal before an operation ID
            # exists has no callback path, so deliver it here rather than leave
            # the overlay parked in its optimistic progress state.
            if isinstance(result, dict) and not result.get("operation_id"):
                self._push_fittings_progress(
                    {
                        "kind": "copy",
                        "phase": "complete",
                        "ticket_id": ticket_id,
                        "operation_id": "",
                        "completed": 0,
                        "total": 0,
                        "result": result,
                    }
                )
        except Exception:
            logger.exception("Fitting copy failed")
            self._push_fittings_progress(
                {
                    "kind": "copy",
                    "phase": "complete",
                    "ticket_id": ticket_id,
                    "operation_id": "",
                    "completed": 0,
                    "total": 0,
                    "result": {
                        "status": "failed",
                        "operation_id": "",
                        "results": [],
                        "write_count": 0,
                    },
                }
            )

    def fittings_cancel_copy(self, ticket_id=None) -> bool:
        # Optional so the pre-ticket call shape still works: the page passes
        # the ticket it is cancelling, and the controller treats a missing
        # one as "everything pending or in flight".
        if self._fittings is not None:
            self._fittings.cancel_copy(ticket_id)
        return True

    # ---- EVE fittings: local curation ---
    #
    # Every method below is a thin delegate to FittingsController, which
    # owns validation, persistence, and the `onFittingsChanged` notify.
    # `self._fittings is None` answers the same safe no-op every other
    # bridge method in this app answers when its subsystem is absent.

    def fittings_create_collection(self, name) -> str:
        if self._fittings is None:
            return ""
        return self._fittings.create_collection(name)

    def fittings_rename_collection(self, collection_id, name) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.rename_collection(collection_id, name)

    def fittings_delete_collection(self, collection_id) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.delete_collection(collection_id)

    def fittings_update_metadata(self, entry_id, name, description) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.update_metadata(entry_id, name, description)

    def fittings_set_membership(self, entry_id, collection_id, member) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.set_membership(entry_id, collection_id, member)

    def fittings_set_supersession(self, entry_id, superseded_by) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.set_supersession(entry_id, superseded_by)

    def fittings_delete_entry(self, entry_id) -> bool:
        if self._fittings is None:
            return False
        return self._fittings.delete_entry(entry_id)

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

    def _eve_authority_changed(self) -> None:
        """Publish the shared authority event for Settings and EVE routes."""
        self._push("onEveAuthorityChanged", {})

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
        """Stop Skills workers before shared authority. main() only."""
        if self._skills is None:
            return
        try:
            self._skills.shutdown()
        except Exception:
            logger.exception("EVE skills subsystem did not stop cleanly")

    def shutdown_authority(self) -> None:
        """Stop shared EVE authorization after every feature consumer."""
        if self._authority is None:
            return
        try:
            self._authority.shutdown()
        except Exception:
            logger.exception("EVE authority did not stop cleanly")
