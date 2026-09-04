"""Prototype crop harness: the checkout-only host that puts the crop
window and the crop picker on the real preview pump.

This is a Phase 0 engineering probe (see
docs/preview-evolution-crops-design.md), not production code: it is not
imported by wingman/__main__.py, ui/api.py, or any shipped module, it is
excluded from the frozen build, and it persists NOTHING -- no settings
write, no layout write, no restart restoration. Every crop it opens dies
with the process.

It is a subclass rather than a rewrite on purpose. Discovery, the message
pump, the DPI scope, the activation coordinator, hide-on-lost-focus, the
lock roster and teardown ordering are the parts of the real host a crop
has to live inside, and a probe that reimplemented any of them would
prove nothing about how crops behave in the shipped one. What the
subclass adds is exactly the crop-specific reconciliation:

    _sweep(libs) -> super()._sweep(libs) -> _reconcile_probe(libs)

_reconcile_probe is a method of its own, not inline in _sweep, so the
Linux tests can drive reconciliation against a fake client registry
without standing up discovery, a desktop, or EVE.

No new WM_APP message is introduced. Public intent (`set_probe_count`)
is stored under the inherited lock and the real pump is woken with
`request_sweep()`, which is the base host's own "there is nothing for you
to carry, only something to re-read" signal (see PreviewHost.request_rebind
for the same reasoning applied to hotkeys).

Same Linux-import constraint as wingman/preview/win32.py and the two
controllers this drives: no native call happens at module scope. The only
one this module makes at all is GetClientRect, through injected libs.
Importing this file parses no arguments, starts no thread, binds no native
library and does not even import wingman/__main__.py -- everything the CLI
at the bottom needs from the application entry point is imported inside the
function that uses it.
"""

import argparse
import contextlib
import ctypes
import importlib.util
import logging
import sys
import time
from pathlib import Path

from wingman.preview import geometry, win32
from wingman.preview.host import PreviewHost

# tests/manual/preview_crop_windows.py and tests/manual/preview_crop_model.py
# are sibling harness modules, not package members -- the same reason the
# window module loads the model this way and the tests load both. Importing
# them normally would require tests/manual on sys.path, which is exactly the
# packaging exposure this probe is supposed to avoid.
_HERE = Path(__file__).parent


def _load_sibling(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_crop_model = _load_sibling("preview_crop_model")
_crop_windows = _load_sibling("preview_crop_windows")

central_source = _crop_model.central_source
fit_within = _crop_model.fit_within
stack_from_bottom_right = _crop_model.stack_from_bottom_right
validated_stage = _crop_model.validated_stage
PrototypeCropWindow = _crop_windows.PrototypeCropWindow
PrototypeCropPicker = _crop_windows.PrototypeCropPicker

logger = logging.getLogger(__name__)

# The probe guard from the design doc's prototype scope, NOT a production
# cap: eight is the largest staged count the load path measures, and the
# measurement is what decides the real cap later.
PROBE_MAX = 8
# The staged simultaneous counts the design doc's performance gates name,
# in the order the load path walks them. Not a second copy of the
# validation rule: `validated_stage` in the pure model owns which counts
# exist, and the tests assert these are exactly the ones it accepts.
PROBE_STAGES = (1, 2, 4, 8)
# How large a load-staged crop opens. The staged crops exist to be counted
# and measured, not arranged, so they take the aspect of their own source
# (via fit_within) and stack up the bottom-right corner out of the way.
PROBE_SIZE_MAX = (480, 320)


def _discard_layout(stable_key, rect, locked) -> None:
    """The probe's on_layout_changed. PreviewHost requires the callback;
    the prototype must never reach a settings file, so dragged geometry
    dies with the process exactly like the crops themselves."""


class PrototypePreviewHost(PreviewHost):
    """PreviewHost plus one picker and up to PROBE_MAX ephemeral crops.

    Identity is `(stable_key, HWND, PID)`, not the stable key alone. A
    character who logs out and back in is the same NAME on a different
    process, and a crop is a DWM relationship with a specific window --
    keeping the old one would mirror a dead HWND under a live name, which
    is the failure the primary registry's wholesale replacement avoids by
    rebuilding rather than merging.

    Everything below `_sweep` runs on the inherited pump thread: the sweep
    itself, both picker callbacks (they arrive through the picker's own
    WndProc, which this thread dispatches), and teardown.
    """

    def __init__(
        self,
        *,
        character=None,
        crop_factory=PrototypeCropWindow.create,
        picker_factory=PrototypeCropPicker.create,
        **host_kwargs,
    ):
        # Before super().__init__, deliberately: _apply_visibility,
        # _restyle and _teardown are overridden here and are reachable
        # from base-class paths, so their registries must exist before any
        # base method can possibly run.
        self._crop_factory = crop_factory
        self._picker_factory = picker_factory
        # The character the interactive path is waiting for, or None for
        # the load path. Matched case-insensitively: the operator types
        # this on a command line.
        self._probe_character = character
        # One picker per host, ever. Not "one at a time": a cancelled
        # picker that reopened on the next sweep would be unclosable, and
        # the user cancelling it is a decision, not a transient failure.
        self._probe_attempted = False
        self._probe_picker = None
        # Bumped for every picker opened, and captured by that picker's
        # callbacks. The callbacks are built before the picker object
        # exists (they are arguments to its create), so a token is what
        # lets a late confirm/cancel from a superseded picker identify
        # itself as stale.
        self._probe_picker_token = 0
        self._probe_crops = {}  # stable_key -> (hwnd, pid, crop)
        self._probe_count = 0
        self._probe_failures = []
        # The confirmed interactive selection: stable_key -> (source_rect,
        # destination_rect). Retained beyond the crop itself because there
        # is nothing to recompute it from -- unlike a load crop, whose
        # central half is re-derived from the current client every time.
        # In memory only, and never written anywhere.
        self._probe_sources = {}
        # Which key (if any) came from the picker rather than the stage,
        # so a load stage of 1 does not evict the crop the user chose.
        self._probe_interactive_key = None
        host_kwargs.setdefault("on_layout_changed", _discard_layout)
        super().__init__(**host_kwargs)

    # ---- public, callable from the CLI thread --------------------------

    def set_probe_count(self, count) -> int:
        """Ask for *count* simultaneous load crops. Safe from any thread.

        Stored first and woken second, and in that order because the CLI
        calls this before the pump has created its message-only window:
        request_sweep is a no-op until then, so the stored intent is the
        only thing that carries the request into the first sweep.

        Raises ValueError for anything but 1, 2, 4 or 8 -- the staged
        counts the design doc names, validated by the pure model rather
        than by a second copy of the rule here.

        Clearing the failure record is deliberate: reconciliation must not
        retry a failed crop every 700ms, and an explicit stage request is
        the "meaningful lifecycle event or explicit user action" the
        design requires before it tries again.
        """
        stage = validated_stage(count)
        with self._lock:
            self._probe_count = stage
            self._probe_failures = []
        self.request_sweep()
        return stage

    def wait_ready(self, timeout: float = 5.0) -> bool:
        """Whether the inherited pump finished its first sweep in time."""
        return self._ready.wait(timeout)

    def probe_status(self) -> dict:
        """A snapshot for the operator. Safe from any thread: every
        registry it reads is REPLACED wholesale on the pump thread rather
        than mutated in place, the same discipline PreviewHost applies to
        _clients and _hotkey_status, so a reader never sees a half-built
        one."""
        with self._lock:
            crops = self._probe_crops
            failures = list(self._probe_failures)
            requested = self._probe_count
        return {
            "character": self._probe_character,
            "requested": requested,
            "live": len(crops),
            "crops": sorted(crops),
            "picker_open": self._probe_picker is not None,
            "failures": failures,
            "clients": self.characters(),
        }

    # ---- everything below runs ON the preview thread -------------------

    def _sweep(self, libs) -> None:
        # Base first, always: it refreshes _clients, which is the registry
        # every decision below is made against, and applies selection and
        # visibility to the primary previews.
        super()._sweep(libs)
        self._reconcile_probe(libs)

    def _reconcile_probe(self, libs) -> None:
        """Bring the crop registry back in line with the client registry.

        Driven directly by the Linux tests, which is why it takes libs
        rather than reading them: real discovery needs a desktop with EVE
        on it and belongs to the smoke checklist.
        """
        named = self._named_clients()
        by_key = {client.stable_key: client for client in named}
        crops = dict(self._probe_crops)

        # 1. Bindings that no longer hold. A missing key is a logout or an
        #    exit; a changed (hwnd, pid) under the SAME key is a relog,
        #    which is a different window wearing a name the old crop still
        #    matches. Both close here and, if still desired, are recreated
        #    against the current client below.
        for key in sorted(crops):
            hwnd, pid, crop = crops[key]
            client = by_key.get(key)
            if client is None or (client.hwnd, client.pid) != (hwnd, pid):
                crop.close()
                del crops[key]

        # 2. The picker DECISION, taken before the display is read so a
        #    pass that opens a picker and stages crops shares one
        #    enumeration. An already-open picker whose client is gone is
        #    ended here; opening happens below.
        picker_client = self._picker_candidate(by_key)

        with self._lock:
            count = self._probe_count
        desired = self._desired_keys(named, count)

        # 3. Crops the current stage no longer wants (a decrease), which
        #    is a different reason from the closures above: the client is
        #    still there and the crop is still live.
        for key in sorted(set(crops) - set(desired)):
            crops.pop(key)[2].close()

        # 4. Creations. The display is enumerated at most ONCE per
        #    reconcile and shared by the picker and every crop: the
        #    hardware does not change between two keys of the same batch,
        #    _monitors() logs a line per failed enumeration, and a pass
        #    that opened the picker AND staged crops used to enumerate
        #    twice for one answer.
        pending = [key for key in desired if key not in crops]
        monitor = (
            self._probe_monitor() if pending or picker_client is not None else None
        )
        if picker_client is not None:
            self._open_picker(libs, picker_client, monitor)
        for index, key in enumerate(desired):
            if key not in pending:
                continue
            client = by_key[key]
            if self._has_failed(client):
                continue
            self._create_probe_crop(libs, crops, client, index, monitor)

        self._publish_probe_crops(crops)

    def _named_clients(self) -> list:
        """Discovered clients with a real character, case-insensitively
        ordered.

        Case-insensitive because a plain sort puts every capitalised name
        ahead of every lowercase one, which would stage the same
        characters last on every run regardless of how many clients are
        up. The raw key breaks ties so the order is still deterministic
        for two names differing only in case.

        Anonymous clients are excluded here, once, which is what makes
        both the picker and the load stages reject them: a client at
        character select has no character to own a crop, and the design
        forbids it borrowing the previous one's.
        """
        named = [
            client
            for client in self._clients.values()
            if self._usable_character(client.character)
        ]
        return sorted(named, key=lambda c: (c.stable_key.lower(), c.stable_key))

    def _desired_keys(self, named, count) -> list:
        """Which characters should have a crop right now, in stack order.

        The interactive crop comes first and is not counted against the
        stage: the user chose it, and a load stage of 1 evicting it would
        be the probe undoing its own picker.
        """
        desired = []
        if self._probe_interactive_key is not None and any(
            client.stable_key == self._probe_interactive_key for client in named
        ):
            desired.append(self._probe_interactive_key)
        for client in named[:count]:
            if client.stable_key not in desired:
                desired.append(client.stable_key)
        return desired[:PROBE_MAX]

    def _probe_monitor(self):
        """The display crops stack up, chosen exactly as the primary
        previews' default stack chooses one."""
        return geometry.stack_monitor(self._monitors(), self._screen())

    def _create_probe_crop(self, libs, crops, client, index, monitor) -> None:
        plan = self._crop_geometry(libs, client, index, monitor)
        if plan is None:
            return
        source_rect, rect = plan
        key = client.stable_key
        crop = self._crop_factory(
            libs,
            client,
            source_rect,
            rect,
            # The ONLY activation route. Foreground policy, the pending
            # switch and the minimize decision belong to the base host,
            # and a probe calling SetForegroundWindow itself would measure
            # its own shortcut rather than Wingman's behaviour.
            on_activate=lambda current: self._activate_client(libs, current),
            locked=self._is_locked(key),
        )
        if crop is None:
            # The factory already logged the native failure; this records
            # it where probe_status can report it, and _has_failed keeps
            # it from being retried on every 700ms sweep.
            self._record_probe_failure(client, "crop-failed")
            return
        # The base host applied visibility during super()._sweep(), before
        # this crop existed -- so a crop born while previews are hidden
        # has to be told, exactly like PreviewWindow's own born-visible
        # case that _apply_visibility re-applies for every sweep.
        crop.set_hidden(self._previews_hidden)
        crops[key] = (client.hwnd, client.pid, crop)

    def _crop_geometry(self, libs, client, index, monitor):
        """(source_rect, destination_rect) for a crop about to be created,
        or None when the client's size could not be read.

        A retained interactive selection wins outright, including its
        destination: it is the user's own choice of both, and recomputing
        either on a relog would move the window they placed. A load crop
        is re-derived from the CURRENT client instead -- the client may
        have come back at a different resolution, and the central half of
        the old one would be off-centre or out of bounds.
        """
        retained = self._probe_sources.get(client.stable_key)
        if retained is not None:
            return retained
        size = self._client_size(libs, client)
        if size is None:
            self._record_probe_failure(client, "client-size")
            return None
        source_rect = central_source(size)
        rect = stack_from_bottom_right(
            index, monitor, fit_within((source_rect.w, source_rect.h), PROBE_SIZE_MAX)
        )
        return source_rect, rect

    def _client_size(self, libs, client):
        """The client's current client-area size, or None.

        Read here rather than taken from the inherited _client_sizes cache
        because this is a creation-time fact: the cache is sampled at the
        top of the sweep, and a crop is created after the picker and the
        reconciliation have both had a chance to act on it.
        """
        rect = win32.RECT()
        if not libs.user32.GetClientRect(client.hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return (w, h)

    # -- picker ----------------------------------------------------------

    def _picker_candidate(self, by_key):
        """The client an interactive picker should open for, or None.

        Decision only -- opening is `_open_picker`, and the two are split
        so the caller can resolve the display once for the picker and the
        staged crops together instead of enumerating it twice in one
        reconcile. Ending an already-open picker whose client is gone DOES
        happen here: it needs no display and must not wait on one.
        """
        picker = self._probe_picker
        if picker is not None:
            current = by_key.get(picker.client.stable_key)
            if current is None or (current.hwnd, current.pid) != (
                picker.client.hwnd,
                picker.client.pid,
            ):
                # Through the PUBLIC seam, never _finish_cancel: the
                # picker owns its own teardown order and its callback-once
                # latch, and reaching past them from here would be a
                # second copy of both.
                picker.cancel("client-lost")
            return None
        if self._probe_character is None or self._probe_attempted:
            return None
        # None here is not an attempt: the character is not up YET. The
        # client at character select a moment ago is usually the one that
        # logs in next, and consuming the attempt would mean the picker
        # never opened at all.
        return self._match_character(by_key)

    def _open_picker(self, libs, client, monitor) -> None:
        """Open the one interactive picker on the already-resolved
        display."""
        # Consumed before the factory runs, so a creation failure is not
        # retried on every sweep either.
        self._probe_attempted = True
        token = self._probe_picker_token = self._probe_picker_token + 1
        created = self._picker_factory(
            libs,
            client,
            monitor,
            lambda confirmed, source_rect: self._on_picker_confirm(
                libs, token, confirmed, source_rect
            ),
            lambda reason: self._on_picker_cancel(token, reason),
        )
        if created is None:
            self._record_probe_failure(client, "picker-failed")
            return
        self._probe_picker = created

    def _match_character(self, by_key):
        """The running client for the requested character, or None.

        Case-insensitive because the name comes from a command line, and
        deterministic in the (impossible today, cheap to guarantee) case
        of two keys matching.
        """
        wanted = self._probe_character.strip().casefold()
        for key in sorted(by_key):
            if key.casefold() == wanted:
                return by_key[key]
        return None

    def _on_picker_confirm(self, libs, token, client, source_rect) -> None:
        """A selection the user confirmed, delivered on the pump thread."""
        if token != self._probe_picker_token:
            return  # a superseded picker's late callback
        self._probe_picker = None
        current = self._clients.get(client.stable_key)
        if current is None or (current.hwnd, current.pid) != (client.hwnd, client.pid):
            # Re-resolved, not trusted: the picker's client record is as
            # old as the picker, and a crop created against a stale HWND
            # would mirror whatever now owns that handle.
            logger.warning(
                "Crop selection for %s discarded: the client changed while "
                "the picker was open",
                client.stable_key,
            )
            return
        crops = dict(self._probe_crops)
        monitor = self._probe_monitor()
        rect = stack_from_bottom_right(
            len(crops),
            monitor,
            fit_within((source_rect.w, source_rect.h), PROBE_SIZE_MAX),
        )
        # Retained BEFORE creation so a crop that fails to open still has
        # the user's selection to retry from on the next lifecycle event.
        self._probe_sources[current.stable_key] = (source_rect, rect)
        self._probe_interactive_key = current.stable_key
        self._create_probe_crop(libs, crops, current, len(crops), monitor)
        self._publish_probe_crops(crops)

    def _on_picker_cancel(self, token, reason) -> None:
        if token != self._probe_picker_token:
            return
        self._probe_picker = None
        logger.info("Crop picker closed: %s", reason)

    # -- failure record --------------------------------------------------

    def _record_probe_failure(self, client, reason) -> None:
        """Remember a failure against the exact client instance it
        happened on.

        Keyed by (stable_key, hwnd, pid) like everything else here, which
        is what lets the same character retry after a relog -- a new
        process is a real lifecycle event -- while a failure on the client
        that is still running is not retried 85 times a minute.
        """
        with self._lock:
            entry = {
                "stable_key": client.stable_key,
                "hwnd": client.hwnd,
                "pid": client.pid,
                "stage": self._probe_count,
                "reason": reason,
            }
            self._probe_failures = [*self._probe_failures, entry]
        logger.warning(
            "Crop probe failure for %s (hwnd=0x%x pid=%d): %s",
            client.stable_key,
            client.hwnd,
            client.pid,
            reason,
        )

    def _has_failed(self, client) -> bool:
        with self._lock:
            failures = self._probe_failures
        return any(
            entry["reason"] in ("crop-failed", "client-size")
            and (entry["stable_key"], entry["hwnd"], entry["pid"])
            == (client.stable_key, client.hwnd, client.pid)
            for entry in failures
        )

    def _publish_probe_crops(self, crops) -> None:
        """Replace the registry wholesale -- see probe_status."""
        with self._lock:
            self._probe_crops = dict(crops)

    def _live_crops(self) -> dict:
        with self._lock:
            return self._probe_crops

    # -- inherited passes ------------------------------------------------

    def _apply_visibility(self, libs, foreground) -> None:
        """Crops follow the primary previews' hide decision exactly.

        The decision itself is not re-derived: `_previews_hidden` is what
        the base pass just applied, and a second visibility.should_hide
        call here could disagree with it on the same sweep.
        """
        super()._apply_visibility(libs, foreground)
        for _hwnd, _pid, crop in self._live_crops().values():
            crop.set_hidden(self._previews_hidden)

    def _restyle(self, libs=None) -> None:
        """The lock roster is per character, so a crop takes the same lock
        its character's primary preview does -- version 1 of the design
        deliberately has no crop-specific lock."""
        super()._restyle(libs)
        for key, (_hwnd, _pid, crop) in self._live_crops().items():
            crop.set_locked(self._is_locked(key))

    def _teardown(self, libs) -> None:
        """Picker, then crops, then the base teardown -- in that order.

        The base pass destroys the host window and posts WM_QUIT, so
        anything closed after it unwinds a DWM relationship on a thread
        that has stopped pumping. `_probe_attempted` is deliberately NOT
        reset: the probe offers one picker per process, and a stop/start
        must not put the picker back on screen.
        """
        picker, self._probe_picker = self._probe_picker, None
        if picker is not None:
            picker.cancel("host-teardown")  # public seam, see _reconcile_picker
        with self._lock:
            crops, self._probe_crops = self._probe_crops, {}
            self._probe_sources = {}
            self._probe_failures = []
            self._probe_count = 0
        for _hwnd, _pid, crop in crops.values():
            crop.close()
        self._probe_interactive_key = None
        super()._teardown(libs)


# ---- the checkout-only CLI ---------------------------------------------
#
# Everything below runs on the CLI thread and only after a subcommand has
# been parsed. Nothing here is reachable from the application: no module
# in wingman/ imports this file, packaging/uploader.spec excludes
# tests/manual, and the harness writes no settings and no layout.

# Deliberately long, and every parser sets allow_abbrev=False so no prefix
# of it works either. This probe opens always-on-top layered windows
# against live EVE clients and holds Wingman's own single-instance mutex
# while it runs; starting it must be an explicit sentence, not a flag that
# can be tab-completed or half-typed.
_OPT_IN = "--i-understand-this-is-an-ephemeral-windows-probe"

# How long the CLI waits for the inherited pump's first sweep. The base
# host sets _ready at the end of that sweep, so this covers window class
# registration, the message-only window and one discovery pass.
READY_TIMEOUT_S = 5.0
# How long a staged count is given to appear. set_probe_count only stores
# the intent and wakes the pump, so the crops arrive on a later sweep --
# printing the status immediately would report every stage as empty.
STAGE_TIMEOUT_S = 5.0
_STAGE_POLL_S = 0.1

_PICK_CONTROLS = (
    "  picker: left drag selects, Enter confirms, Escape cancels\n"
    "  crop:   left click activates, left drag moves, right drag resizes"
)


def _acquire_single_instance():
    """Wingman's own single-instance guard, imported here and not above.

    A module-scope import would pull the whole application entry point --
    and with it pywebview, pystray and the tray icon's dependencies -- into
    every pytest run that merely loads this file, and would break the
    import inertness the probe shares with the two controllers it drives.
    """
    from wingman.__main__ import acquire_single_instance

    return acquire_single_instance()


def _set_dpi_awareness() -> None:
    """PROCESS_SYSTEM_DPI_AWARE, through the application's own helper.

    Imported lazily for the same reason as above. Calling Wingman's helper
    rather than SetProcessDpiAwareness directly is the point: the probe has
    to measure crops in the DPI mode the shipped app actually runs in.
    """
    from wingman.__main__ import set_dpi_awareness

    set_dpi_awareness()


def _require_probe_environment() -> None:
    """Refuse to start anywhere the probe would be unsafe or meaningless.

    The single-instance check is not politeness. An installed Wingman on
    the same desktop would discover the same clients, hold its own DWM
    relationships against them and apply its own visibility and activation
    decisions -- so every number this probe records would be measured
    against two preview subsystems, and the app's settings file would be
    live under a process that is supposed to persist nothing.

    Acquiring the mutex (rather than only testing it) is deliberate too:
    for as long as the probe runs, Wingman refuses to start beside it.
    """
    if sys.platform != "win32":
        raise RuntimeError("the crop probe requires Windows")
    if _acquire_single_instance() is None:
        raise RuntimeError(
            "FlyGD Wingman (or its 3.x predecessor) is already running; "
            "close it before running the crop probe"
        )


def _wait_for_enter(prompt) -> None:
    """Hold the probe open until the operator presses Enter.

    EOFError becomes a RuntimeError so a run with no console -- redirected
    stdin, a scheduled task -- ends as this harness's own one-line failure
    rather than a traceback. Silently continuing would be worse: every
    pause here exists so a human can look at, or measure, what is on
    screen.
    """
    print(prompt, flush=True)
    try:
        input()
    except EOFError:
        raise RuntimeError(
            "the crop probe needs an interactive console to wait for Enter"
        ) from None


def _format_status(status) -> str:
    return "\n".join(
        (
            f"  requested: {status['requested']}",
            f"  live crops: {status['live']} {status['crops']}",
            f"  picker open: {status['picker_open']}",
            f"  named clients: {status['clients']}",
            f"  failures: {status['failures']}",
        )
    )


@contextlib.contextmanager
def _probe_host(character=None):
    """The one host lifecycle a probe run gets.

    Constructed with no settings persistence callbacks at all -- the
    subclass supplies its own discarding on_layout_changed -- and stopped
    in `finally` whatever happens, because a pump left running owns HWNDs
    and DWM relationships with nothing left to close them.
    """
    _require_probe_environment()
    # Before the host, never after: its windows are placed in physical
    # pixels the moment the pump starts, and a process that became
    # DPI-aware afterwards would be measuring a desktop it no longer has.
    _set_dpi_awareness()
    host = PrototypePreviewHost(character=character)
    try:
        host.start()
        if not host.wait_ready(READY_TIMEOUT_S):
            raise RuntimeError(
                f"the preview host was not ready within {READY_TIMEOUT_S:.1f}s"
            )
        yield host
    finally:
        host.stop()


def _await_stage(host, stage, timeout=STAGE_TIMEOUT_S):
    """The status once *stage* crops are live, a failure is recorded, or
    the wait runs out. The timed-out status is RETURNED rather than raised
    on: a stage that could not be filled is a result the operator has to
    record, not an error that should discard the run so far."""
    deadline = time.monotonic() + timeout
    while True:
        status = host.probe_status()
        if status["live"] >= stage or status["failures"]:
            return status
        if time.monotonic() >= deadline:
            return status
        time.sleep(_STAGE_POLL_S)


def _run_pick(args) -> None:
    """Interactive path: one picker for one named character."""
    with _probe_host(character=args.character) as host:
        print(f"waiting for {args.character}; the picker opens once that client is up")
        print(_PICK_CONTROLS, flush=True)
        _wait_for_enter("press Enter to close the probe and every crop it opened")
        print(_format_status(host.probe_status()))


def _run_load(args) -> None:
    """Load path: the staged simultaneous counts, one stage at a time.

    Each stage pauses for Enter so the operator can record the metrics the
    design doc's performance gates ask for before the next one opens. A
    stage the machine cannot fill is not run at all -- fewer clients than
    crops measures something other than the gate it is named after.
    """
    with _probe_host() as host:
        clients = host.probe_status()["clients"]
        if not clients:
            raise RuntimeError(
                "no named EVE client is running; log at least one character in first"
            )
        print(f"named clients: {clients}", flush=True)
        for stage in PROBE_STAGES:
            if len(clients) < stage:
                print(
                    f"stopping before stage {stage}: "
                    f"only {len(clients)} named client(s) are running"
                )
                return
            host.set_probe_count(stage)
            status = _await_stage(host, stage)
            print(f"stage {stage}:")
            print(_format_status(status), flush=True)
            if status["failures"]:
                print(f"stopping at stage {stage}: a crop did not open")
                return
            clients = status["clients"]
            _wait_for_enter(f"stage {stage} is up; press Enter to continue")


def _add_opt_in(parser) -> None:
    parser.add_argument(
        _OPT_IN,
        action="store_true",
        required=True,
        help="required acknowledgement that this opens ephemeral probe windows",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Windows-only engineering probe for cropped preview regions. "
            "Persists nothing; every window it opens dies with the process."
        ),
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    pick = commands.add_parser(
        "pick",
        help="open one interactive crop picker for a named character",
        allow_abbrev=False,
    )
    pick.add_argument("--character", required=True)
    _add_opt_in(pick)
    pick.set_defaults(handler=_run_pick)

    load = commands.add_parser(
        "load",
        help="stage 1, 2, 4 and 8 simultaneous crops for measurement",
        allow_abbrev=False,
    )
    _add_opt_in(load)
    load.set_defaults(handler=_run_load)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except (OSError, RuntimeError) as exc:
        # Every refusal in this file is one of these two, and the probe is
        # run from a console: one line is the whole report. Native detail
        # that matters is already in the log the controllers write to.
        print(f"crop probe failure: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
