"""The preview thread: its pump, its windows, and its lifecycle.

pywebview runs its GUI on a thread of its own and does NOT pump on the
thread that calls webview.start() -- measured, not assumed. A window
created on the main thread is therefore orphaned: nobody dispatches its
messages. So previews get their own thread with a real GetMessage loop,
which is also what RegisterHotKey and SetWinEventHook require.

Same shape as ui/scheduler.py, one level lower: that module's docstring
records the identical discovery about webview.start() carrying none of
the old event loop, and answers it with an owned loop.
"""

import contextlib
import ctypes
import logging
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

from . import (
    cycle,
    discovery,
    geometry,
    gestures,
    layout,
    switching,
    visibility,
    win32,
)
from . import window as window_mod
from .window import PreviewWindow

logger = logging.getLogger(__name__)

SWEEP_MS = 700  # TriffView uses the same interval
# Upper bound on the minimize send. With SMTO_ABORTIFHUNG this is what
# keeps a still-loading EVE client from stalling the preview thread --
# see the SendMessageTimeoutW bind comment in win32.py. The send now goes
# to a client that still holds the foreground (see _activate_client), the
# case measured at 6-9ms; the budget is a ceiling for a hung one, not the
# expected wait.
MINIMIZE_TIMEOUT_MS = 100
SWEEP_TIMER_ID = 1
ACTIVATE_RETRY_TIMER_ID = 3
ACTIVATE_RETRY_MS = 20
ACTIVATE_RETRY_MAX = 5
# How long an armed bind capture survives without being disarmed. Long
# enough that nobody meets it while deciding which key to press; short
# enough that a page which died mid-capture cannot leave the preview
# hotkeys inert for the rest of the session.
CAPTURE_TIMEOUT_S = 30.0
# Runs only while something is armed, and is killed the moment nothing is
# -- an 80ms timer left running is a wakeup 12 times a second for the life
# of the session, on the thread that also pumps the hotkey loop.
ALERT_TIMER_ID = 2
ALERT_MS = 80
JOIN_TIMEOUT_S = 5.0
DEFAULT_SIZE = (320, 210)
# Anything beyond a handful means the pump has stopped draining, not that
# a lot of characters are in a fight at once -- raise_alert's docstring
# has the reasoning.
PENDING_ALERTS_MAX = 10
COPY_OK = "ok"
COPY_MISSING = "missing"
COPY_PERSIST_FAILED = "persist_failed"


@dataclass(frozen=True)
class _PendingSwitch:
    """The one restore still awaiting Windows' foreground verdict."""

    stable_key: str
    hwnd: int
    previous_key: str | None
    previous_hwnd: int
    minimize: bool
    attempts: int = 0


@contextlib.contextmanager
def _animation_off(libs):
    """Suspend the minimize/restore window animation for the block.

    Ported from EVE-O Preview (WindowManager.TurnOffAnimation /
    RestoreAnimation), where it is the default. What it buys is the
    VISIBLE zoom, and only that -- measured 2026-08-30, cross-thread
    SendMessageTimeoutW(SC_MINIMIZE) against a synthetic top-level
    window, n=7 each: 12.6ms median with the animation ON, 14.2ms with
    it OFF. The animation is composited by DWM, not run inside the
    target's message handler, so it delays neither the send nor the
    switch. An earlier version of this comment claimed ~200-250ms and
    called it "the bulk of the visible lag"; the blocking half of that
    claim is measurably false, and the duration of the zoom itself has
    never been measured here. It is also a no-op for anyone whose
    animation is already off -- including this repo's maintainer, whose
    desktop reads iMinAnimate=0 -- so it explains no part of the field
    reports that motivated the switch reorder.

    Kept anyway: for the Windows default (animation ON) the zoom is real
    and on screen for every minimize and every restore of a minimized
    client, which is perceived latency even when nothing is blocked.

    Toggled for the switch only and put back in a finally, so a refused
    activation or an exception cannot leave the user's desktop without
    its animation. Left alone when it is already off: nothing to write,
    and nothing to "restore" to a value the user never had.

    fWinIni is 0 on both calls -- the live value changes, the user's
    registry preference does not.

    The restore of a target that was itself minimized is asynchronous
    (ShowWindowAsync in window.activate), so the animation can come back
    before the client processes it. EVE-O Preview carries the same race
    and it is not visible in practice; a synchronous ShowWindow would
    close it at the cost of blocking on a loading client, which is the
    stall SendMessageTimeoutW exists to avoid.
    """
    if libs is None:
        yield
        return
    info = win32.ANIMATIONINFO()
    size = info.cbSize = ctypes.sizeof(info)
    got = libs.user32.SystemParametersInfoW(
        win32.SPI_GETANIMATION, size, ctypes.pointer(info), 0
    )
    if not got or not info.iMinAnimate:
        yield
        return
    # Restored to what was read, not to a literal 1: the field is
    # documented as a flag but it is the user's value, and it goes back
    # exactly as it came.
    original = info.iMinAnimate
    info.iMinAnimate = 0
    if not libs.user32.SystemParametersInfoW(
        win32.SPI_SETANIMATION, size, ctypes.pointer(info), 0
    ):
        # Nothing changed, so nothing to put back -- and the zoom the
        # user came to lose is still there, which is worth one line.
        logger.info("Could not suspend the window animation for the switch")
        yield
        return
    try:
        yield
    finally:
        info.iMinAnimate = original
        if not libs.user32.SystemParametersInfoW(
            win32.SPI_SETANIMATION, size, ctypes.pointer(info), 0
        ):
            # The one outcome this block exists to prevent: the user's
            # desktop left without its animation for the session. It
            # cannot be retried usefully from here, but it must not be
            # silent.
            logger.warning(
                "Could not restore the window animation after the switch; "
                "it stays off until the next switch or logon"
            )


def coalesce_hotkey_ids(peek, hwnd, first_ident) -> list[int]:
    """Drain this host's queued hotkeys without disturbing other messages.

    There is deliberately no cap: every queued press contributes to the
    sequential target, while folding keeps the cost to one final activation.
    PeekMessageW stops as soon as this host's finite hotkey queue is caught up.
    """
    ids = [int(first_ident)]
    message = wintypes.MSG()
    while peek(
        ctypes.byref(message),
        hwnd,
        win32.WM_HOTKEY,
        win32.WM_HOTKEY,
        win32.PM_REMOVE,
    ):
        ids.append(int(message.wParam))
    return ids


def reconcile(current: set, desired: set):
    """(added, removed, kept) stable keys between two sweeps."""
    return (
        sorted(desired - current),
        sorted(current - desired),
        sorted(current & desired),
    )


HOTKEY_ID_BASE = 1
HOTKEY_ID_MAX = 0xBFFF  # Windows reserves 0xC000+ for DLLs


def plan_registrations(table) -> list:
    """(hotkey_id, gesture_text, action) for every registerable binding.

    Pure, and separated from the Win32 half for exactly that reason: id
    assignment, duplicate merging and gesture validation are where the
    bugs are, and none of them need a window.

    Order is deterministic so a rebind that changed nothing produces the
    same ids -- rebinding unregisters and re-registers wholesale, and an
    unstable assignment would churn registrations that did not change.

    A focus action carries a TUPLE of names, not one name. Several
    characters on one chord is a supported setup: a multiboxer runs a
    different subset each session and wants one key to mean "go to
    whichever of these is up". Windows has only one registration per
    chord to give, so the names ride together on it and _on_hotkeys
    resolves between them against who is actually running.
    """
    table = table if isinstance(table, dict) else {}
    characters = table.get("characters")

    # Characters first and merged, then the two cycle chords. A cycle
    # chord cannot join a focus registration -- it is a different action,
    # so one of the two genuinely loses, and it is the cycle chord, which
    # is what its missing hotkey_status entry tells the page.
    by_chord: dict = {}
    if isinstance(characters, dict):
        for name in sorted(characters):
            parsed = gestures.parse(characters[name])
            if parsed is None:
                continue
            # Insertion order is the plan's order, and sorted(characters)
            # above fixes it -- no second list is needed to remember it.
            by_chord.setdefault(gestures.display(parsed), []).append(name)

    entries = [(chord, ("focus", tuple(names))) for chord, names in by_chord.items()]
    entries.append((table.get("cycle_next"), ("cycle", 1)))
    entries.append((table.get("cycle_prev"), ("cycle", -1)))

    plan, claimed = [], set()
    for text, action in entries:
        parsed = gestures.parse(text)
        if parsed is None:
            continue
        canonical = gestures.display(parsed)
        if canonical in claimed:
            # Reached only by a cycle chord a character already holds --
            # the character entries were merged above and cannot collide
            # with each other any more. Windows would refuse the second
            # registration anyway; dropping it here keeps the reported
            # status honest about which binding actually lost.
            continue
        ident = HOTKEY_ID_BASE + len(plan)
        if ident > HOTKEY_ID_MAX:
            logger.warning("Too many preview hotkeys; dropping %s", canonical)
            break
        claimed.add(canonical)
        plan.append((ident, canonical, action))
    return plan


class PreviewHost:
    """Owns the preview thread. Public methods are callable from anywhere;
    anything touching an HWND is marshalled onto the thread."""

    def __init__(
        self,
        on_layout_changed,
        saved_layouts=None,
        size=DEFAULT_SIZE,
        flush_layouts=None,
        on_clients_changed=None,
        on_layouts_changed=None,
        on_hotkey_status=None,
        on_bind_captured=None,
        restore_positions=None,
        show_labels=None,
        opacity=None,
        minimize_inactive_clients=None,
        never_minimize=None,
        locked=None,
        lock_default=None,
        excluded=None,
        snap=None,
        lock_aspect=None,
        selection_color=None,
        clear_layouts=None,
        replace_layout=None,
        hide_on_lost_focus=None,
    ):
        self._on_layout_changed = on_layout_changed
        # Called during teardown, before any window is destroyed. Layout
        # writes are debounced, so without this a drag in the last second
        # before quitting is simply lost.
        self._flush_layouts = flush_layouts
        # Called by _reset_layouts to empty the on-disk table, same as
        # flush_layouts above being called by _teardown: the store owns
        # persistence, the host only tells it when to act.
        self._clear_layouts = clear_layouts
        # Synchronous per-key persistence for an explicit Copy operation.
        # LayoutStore owns pending-delta ordering; the host changes its cache
        # and windows only after this reports that the write landed.
        self._replace_layout = replace_layout
        # Reported outward when the discovered set changes, so the page can
        # order the bind list by who is actually online. Nothing else
        # carries that out of the subsystem: _settings_payload returns
        # persisted settings only.
        self._on_clients_changed = on_clients_changed
        # Announces only when source eligibility changes (a character gains
        # its first complete layout), not on every drag coordinate.
        self._on_layouts_changed = on_layouts_changed
        self._saved = dict(saved_layouts or {})
        # Read per placement, never captured: a preview is created whenever
        # its client appears, which is usually mid-session, so the value
        # the app started with is not the value that should apply. None
        # means "always restore" -- the behaviour that predates the toggle.
        self._restore_positions = restore_positions
        # Read live, same reasoning as _restore_positions above: each of
        # these can change mid-session (a Settings toggle, a lock or
        # never-minimize edit), and a preview is created -- or restyled --
        # long after the app started. None means "the caller has not
        # wired this yet", not "off"; _labels_shown/_current_opacity/etc.
        # below fall back to today's shipped behaviour in that case.
        self._show_labels = show_labels
        self._opacity = opacity
        self._minimize_inactive_clients = minimize_inactive_clients
        # preview.hide_on_lost_focus: whether every preview leaves the
        # screen while the foreground belongs to neither an EVE client nor
        # us. Read live like the rest, and read once per _apply_visibility
        # rather than per window -- it is a fact about the foreground, not
        # about any one character.
        self._hide_on_lost_focus = hide_on_lost_focus
        # What _apply_visibility last applied to every preview. Host level,
        # not per window, because the answer is the same for all of them --
        # and it is what lets the off path (the default) return without
        # reading the foreground's process. Touched only on the preview
        # thread.
        self._previews_hidden = False
        # All three of these are character-name LISTS (preview.never_minimize,
        # preview.locked, preview.excluded), not per-character booleans: a
        # per-character callable would need the character key at construction
        # time, and build_preview_host does not have it. _is_never_minimize/
        # _is_locked/_is_excluded below do the per-window membership test.
        self._never_minimize = never_minimize
        self._locked = locked
        # preview.lock_default: whether a character NOT in `locked` is
        # locked anyway, which makes `locked` a list of exceptions. Read
        # live like the roster it modifies, and resolved with it in one
        # place (_is_locked) so the two cannot be consulted separately and
        # disagree.
        self._lock_default = lock_default
        # preview.excluded: characters opted out of previews entirely. Read
        # live like the rest, and read in THREE places rather than one --
        # _sweep (no window), _registerable (no hotkey registration) and
        # _cycle_keys (not a stop on the walk) -- because the opt-out is a
        # statement about the character, not about one window.
        self._excluded = excluded
        # Same reasoning as _restore_positions/_show_labels/etc.: read
        # live so a Settings toggle mid-session reaches previews already
        # open. None means "the caller has not wired this yet" -- see
        # _snapping.
        self._snap = snap
        # Same live-read contract as _snap: PreviewWindow samples it when a
        # drag begins, so the Settings checkbox must reach an already-open
        # preview without a restart.
        self._lock_aspect = lock_aspect
        # Same live-read contract as _snap: the Settings colour picker must
        # recolour already-open previews through _restyle, not on a restart.
        self._selection_color = selection_color
        # A pair, or a callable returning one. Every other setting here is
        # live and this one was not: it was sampled once at construction,
        # so preview.width/height could only take effect on a restart --
        # tolerable while they had no user interface, and not once they
        # got a field. _default_size() resolves whichever was passed, so
        # the old positional pair still works and every existing caller
        # (and test) keeps its meaning.
        self._size = size
        self._thread = None
        self._hwnd = None  # message-only window, see _run
        self._windows = {}
        # Every DISCOVERED client, not just those with a window. _windows
        # drops any whose creation failed, and a chord aimed at a running
        # client must not depend on its preview having been created.
        self._clients = {}
        # Physical client -> last positively identified character, for the
        # consecutive sweeps where that HWND and PID remain present. This is
        # not character identity: it carries only placement continuity and
        # preview exclusion while the title is generic, and is never persisted.
        self._last_character_by_process = {}
        self._hook = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

        self._on_hotkey_status = on_hotkey_status
        # Where a chord goes while the bind screen is waiting for one.
        #
        # A registered chord is delivered to THIS window as WM_HOTKEY and
        # never reaches the focused WebView2 window, so the page's keydown
        # listener cannot see a key that is already bound -- rebinding one
        # was impossible without clearing it first, and the press focused
        # a client instead, taking the foreground away mid-capture. While
        # armed, the chord is reported up rather than acted on; chords
        # that are NOT registered still arrive at the page as an ordinary
        # keydown, and between them the two paths cover every key.
        self._on_bind_captured = on_bind_captured
        # A DEADLINE, not a flag. The page disarms on every exit path it
        # knows about, but a WebView2 crash or a reload with a capture
        # armed knows none of them, and a flag left set would turn every
        # preview hotkey into a silent no-op for the session.
        self._capture_until = 0.0
        # ident -> the canonical chord text registered for it. _registered
        # holds the ACTION, which is what dispatch needs; a capture needs
        # to answer with the chord, and re-deriving it from the desired
        # table would read a table that may have been replaced since.
        self._registered_text = {}
        # The desired table, written by any thread and read by the preview
        # thread when it processes WM_APP_REBIND. PostMessage cannot carry
        # a dict, so the value travels in a field and only the signal is
        # posted -- the same shape _saved already uses.
        self._desired_hotkeys = {}
        self._registered = {}  # hotkey_id -> action
        self._hotkey_status = {}  # gesture text -> registered?
        self._last_cycled = None
        # Same shape as _desired_hotkeys above, and for the same reason:
        # PostMessageW carries integers only, so the payload travels in a
        # field under the lock and only the signal is posted. A list, not
        # one slot, because two clients can be alerted between ticks.
        self._pending_alerts = []
        # Same shape as _desired_hotkeys/_pending_alerts: PostMessageW
        # carries integers only, so a typed size travels in a field under
        # the lock and only the signal is posted. A dict, keyed by stable
        # key, because more than one resize can be requested between ticks.
        self._pending_resize = {}
        # The "apply to open previews" size, or None. A scalar, not a dict:
        # the request is always "every window, one size", and unlike
        # _pending_resize there is no keying to do. Swapped to None under
        # the lock when drained, same as the dict above.
        self._pending_resize_all = None
        # Complete copied layouts waiting to be applied on the preview thread.
        # Persistence and the in-memory cache are updated before they enter
        # this queue; the message only performs monitor-safe live movement.
        self._pending_layouts = {}
        # Last sampled client-area size per character, refreshed every
        # sweep by _record_client_sizes. Read from the UI thread through
        # client_sizes(), like hotkey_status() below.
        self._client_sizes = {}
        # Whether the 80ms alert tick timer is currently running. Tracked
        # rather than derived so KillTimer is called exactly once when the
        # last alert clears, and only ever from the preview thread.
        self._alert_timer = False
        # A restored EVE client can briefly remain iconic after activation.
        # Retain the outgoing decision so a later observed success completes
        # the same switch, but never block this thread waiting for Windows.
        self._pending_switch = None
        # Like _alert_timer, track the OS timer rather than inferring it from
        # the request: a newer pending target replaces the request but shares
        # its periodic timer, which must be killed exactly once on any exit.
        self._pending_activation_timer = False
        # Recorded by the foreground hook (an arbitrary thread) and
        # resolved by _sweep, never the other way around -- see
        # _install_hook and _apply_selection.
        self._foreground = 0
        # Two keys, deliberately, because two different questions are
        # being asked and they used to share one answer:
        #
        # _focused_key -- the client that owns the foreground RIGHT NOW,
        #   None the instant you click a browser, Discord or Wingman
        #   itself. This is the one alerts hang off: PreviewWindow's
        #   set_focused acknowledges a persistent alert, and arm_alert
        #   reads `focused` to decide whether you are already looking at
        #   the client. Making this sticky would mean an alert on the
        #   client you last used counts as seen and expires unread.
        #
        # _selected_key -- the client the ring is drawn on: the last one
        #   that held the foreground, kept through any amount of time
        #   spent outside EVE and cleared only when another client takes
        #   over or that client exits. The ring answers "which client are
        #   you flying", and clearing it the moment you tabbed out was
        #   reported as unexpected. It was the same key as the focus one
        #   until then; the alert reasoning that justified that is now
        #   carried by _focused_key instead.
        self._focused_key = None
        self._selected_key = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return  # Idempotent: a second enable must not orphan a pump.
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="wingman-preview"
            )
            self._thread.start()

    def stop(self, timeout: float = JOIN_TIMEOUT_S) -> None:
        """Idempotent, and safe when never started."""
        with self._lock:
            thread, self._thread = self._thread, None
        if thread is None:
            return
        if self._hwnd:
            libs = win32.bind()
            libs.user32.PostMessageW(self._hwnd, win32.WM_APP_SHUTDOWN, 0, 0)
        thread.join(timeout)
        if thread.is_alive():
            # A stop() that returns while the thread still owns HWNDs
            # produces a Wingman that vanishes from the tray and lingers
            # in Task Manager.
            logger.warning("Preview thread did not exit within %.1fs", timeout)

    def _layout_changed(self, stable_key, rect, locked) -> None:
        """Record the new rect locally, then pass it outward.

        Keeping _saved current matters within a single session: a client
        that disappears and comes back -- an EVE client restart, or a
        transient discovery miss -- is a new entry to the next sweep. If
        _saved still held only what was loaded at startup, that preview
        would be placed by default_stack and the position the user dragged
        it to would not return until the whole app was restarted.
        """
        with self._lock:
            first_layout = (
                self._usable_character(stable_key) and stable_key not in self._saved
            )
            saved = dict(self._saved)
            saved[stable_key] = layout.Entry(rect, locked)
            self._saved = saved
        self._on_layout_changed(stable_key, rect, locked)
        if first_layout:
            self._announce_layouts_changed()

    def _announce_layouts_changed(self) -> None:
        if self._on_layouts_changed is None:
            return
        try:
            self._on_layouts_changed()
        except Exception:
            # A page refresh is secondary to keeping the preview pump alive.
            logger.exception("on_layouts_changed callback raised")

    def request_sweep(self) -> None:
        """Ask for an immediate sweep. Safe from any thread."""
        self._post(win32.WM_APP_SWEEP_NOW)

    def raise_alert(self, character: str, event: str, spec: dict) -> None:
        """Queue an alert and nudge the pump. Safe from any thread.

        The queue is filled whether or not a window exists to post to:
        start() returns before the preview thread has created _hwnd, and
        an alert raised in that gap would otherwise be dropped.

        Bounded to PENDING_ALERTS_MAX: _apply_alerts drains this every
        WM_APP_ALERT, and in normal operation that is within ~80ms. Only
        a pump that is not running at all -- previews disabled, the host
        window not yet created -- lets this grow, and there the right
        answer is dropping the oldest, not remembering an unbounded
        session's worth of fights for whenever the pump comes back.
        """
        with self._lock:
            self._pending_alerts.append((character, event, dict(spec)))
            if len(self._pending_alerts) > PENDING_ALERTS_MAX:
                del self._pending_alerts[:-PENDING_ALERTS_MAX]
        self._post(win32.WM_APP_ALERT)

    def _post(self, msg) -> None:
        if self._hwnd:
            win32.bind().user32.PostMessageW(self._hwnd, msg, 0, 0)

    def _drain_alerts(self) -> list:
        with self._lock:
            pending, self._pending_alerts = self._pending_alerts, []
        return pending

    def set_hotkeys(self, table) -> None:
        """Replace the whole binding table. Safe from any thread.

        Wholesale rather than diffed: the table is a dozen entries, and
        diffing registration state against Windows is a bug farm for no
        measurable gain.
        """
        with self._lock:
            self._desired_hotkeys = dict(table or {})
        if self._hwnd:
            win32.bind().user32.PostMessageW(self._hwnd, win32.WM_APP_REBIND, 0, 0)

    def request_rebind(self) -> None:
        """Re-apply the table already held, without supplying one.

        For a caller that changed something the REGISTRATION depends on
        rather than the table itself -- today only preview.excluded, which
        _registerable filters on. set_hotkeys would work, but only by
        having the caller read the table back out of settings and push it,
        which loses a race it has no need to enter: pywebview serves each
        call on its own thread, so a set_preview_binds landing between that
        read and that push would be silently reverted inside the host.
        WM_APP_REBIND re-reads _desired_hotkeys under this object's own
        lock, so a payload-free signal has nothing to revert.
        """
        self._post(win32.WM_APP_REBIND)

    def set_capture(self, armed: bool) -> None:
        """Arm or disarm bind capture. Safe from any thread.

        No PostMessageW: unlike set_hotkeys there is nothing for the
        preview thread to DO about this, only something for it to read the
        next time a chord fires. Posting would also lose the race this
        exists to close -- the page waits for this call to return before
        it invites the keystroke.
        """
        with self._lock:
            self._capture_until = time.monotonic() + CAPTURE_TIMEOUT_S if armed else 0.0

    def restyle(self) -> None:
        """Ask every open preview to re-read show_labels, opacity, locked
        and never_minimize. Safe from any thread, same shape as
        set_hotkeys() above -- except there is no payload to stash under
        the lock: the callables themselves are the live state, so this
        only has to post the signal.

        The single live-update entry point for these settings
        (minimize_inactive_clients included): there is no separate "minimize
        changed" message, because minimize is read per switch, not per window.
        """
        self._post(win32.WM_APP_RESTYLE)

    def hotkey_status(self) -> dict:
        """Outcome of the most recent registration pass.

        Readable, not only announced. Previews start before the webview
        exists (__main__.py:476-478), so a conflict found at launch has
        nowhere to be pushed and would otherwise be lost for the session.
        """
        return dict(self._hotkey_status)

    def resize_preview(self, stable_key: str, size) -> None:
        """Set one preview's size on demand. Safe from any thread.

        Same shape as set_hotkeys: PostMessageW carries integers only, so the
        payload travels in a field under the lock and only the signal is
        posted.
        """
        with self._lock:
            self._pending_resize[stable_key] = (int(size[0]), int(size[1]))
        self._post(win32.WM_APP_RESIZE_ONE)

    def resize_all(self, size) -> None:
        """Set EVERY open preview's size. Safe from any thread.

        Deliberately overrides custom sizes: this is the "make them all
        this size" action, and honouring per-window exceptions would make
        it silently skip windows the user sized once and forgot. A window
        sized individually afterwards simply overwrites its entry again.
        """
        with self._lock:
            self._pending_resize_all = (int(size[0]), int(size[1]))
        self._post(win32.WM_APP_RESIZE_ALL)

    def _mirror_resize(self, driver_key: str, rect) -> None:
        """Copy a resize-all chord's size onto every OTHER open preview.

        Runs on the preview thread -- called from a PreviewWindow wndproc
        (see the thread-affinity note on PreviewWindow) -- so it may touch
        the windows directly. Recorded on every coalesced move like the
        drags are: _layout_changed updates in-memory state cheaply and the
        store debounces the disk write, so per-move recording costs
        nothing and means the chord's result survives a quit mid-drag.

        Size only, never position: the chord says how big, and re-flowing
        where every preview sits would both overlap them all and fight the
        layout the user arranged.
        """
        for key, win in self._windows.items():
            if key == driver_key:
                continue
            win.move(win.rect._replace(w=rect.w, h=rect.h))
            self._layout_changed(key, win.rect, win.locked)

    def layout_entries(self) -> dict:
        """Latest complete layouts, including undebounced drags."""
        with self._lock:
            return dict(self._saved)

    def _layout_entry(self, stable_key: str):
        with self._lock:
            return self._saved.get(stable_key)

    def sync_layout(self, stable_key: str, entry) -> None:
        """Mirror a layout already persisted by an offline API path."""
        with self._lock:
            saved = dict(self._saved)
            saved[stable_key] = entry
            self._saved = saved

    def clear_layout_entries(self) -> None:
        """Mirror a layout clear already persisted by an offline API path."""
        with self._lock:
            self._saved = {}
            self._pending_layouts = {}

    @staticmethod
    def _usable_character(name) -> bool:
        return isinstance(name, str) and bool(name) and not name.startswith("hwnd:")

    def copy_layout(self, target: str, source: str) -> str:
        """Persist source geometry for target, then queue live movement."""
        if (
            target == source
            or not self._usable_character(target)
            or not self._usable_character(source)
            or self._replace_layout is None
        ):
            return COPY_MISSING
        with self._lock:
            source_entry = self._saved.get(source)
            target_entry = self._saved.get(target)
        if source_entry is None:
            return COPY_MISSING
        entry = layout.Entry(
            source_entry.rect,
            target_entry.locked if target_entry is not None else False,
        )
        if not self._replace_layout(target, entry):
            return COPY_PERSIST_FAILED
        with self._lock:
            # A drag that landed while the settings transaction was in
            # progress is the later user action. LayoutStore has its delta;
            # do not move the window/cache back to the copied rectangle.
            if self._saved.get(target) != target_entry:
                return COPY_OK
            saved = dict(self._saved)
            saved[target] = entry
            self._saved = saved
            should_post = bool(self._hwnd)
            if should_post:
                self._pending_layouts[target] = entry
        if should_post:
            self._post(win32.WM_APP_APPLY_LAYOUTS)
        return COPY_OK

    def reset_layouts(self) -> None:
        """Forget every saved position and re-place. Safe from any thread."""
        self._post(win32.WM_APP_RESET_LAYOUTS)

    def client_sizes(self) -> dict:
        """Last sampled client-area size per character. Safe from any thread."""
        with self._lock:
            return dict(self._client_sizes)

    def focused_character(self):
        """The character whose client owns the foreground, or None.

        Safe from any thread, and deliberately NOT lock-held: the value is
        a str or None written as a single attribute assignment on the
        preview thread (_apply_selection), so a reader sees one generation
        or the next and never a torn one. Taking _lock here would add no
        guarantee the write side does not already give, and this is called
        once a second from the alert poll thread.

        The value is a Client.stable_key, which is the character name for
        any client past character-select and a synthetic "hwnd:0x..." for
        one that is not (discovery.py). That is exactly right for the one
        caller: an alert names the character its gamelog belongs to, so a
        client with no character cannot match one, and a login screen is
        never treated as the client you are flying.

        _focused_key, not _selected_key: the question this answers is
        "are you looking at this client right now", which is what decides
        whether an alert on it needs to make a noise. The selection ring
        is sticky and survives a trip to a browser, so answering from it
        would silence alerts for the client you last used while you read
        Discord -- the exact case the two keys were split apart for.
        """
        return self._focused_key

    # ---- everything below runs ON the preview thread -------------------

    def _run(self) -> None:
        libs = win32.bind()

        # First, before any window exists. Thread-local, so the process
        # keeps the PROCESS_SYSTEM_DPI_AWARE contract __main__.py:99-114
        # deliberately chose and ui/chrome.py:177-186 depends on. Verified
        # to isolate correctly on a 192-DPI monitor.
        prev = libs.user32.SetThreadDpiAwarenessContext(
            ctypes.c_void_p(win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
        logger.debug("Preview thread DPI override accepted: %s", bool(prev))

        self._hwnd = self._create_host_window(libs)
        if not self._hwnd:
            logger.error(
                "Preview host window could not be created; "
                "previews are disabled for this session"
            )
            return

        self._sweep(libs)
        self._install_hook(libs)
        with self._lock:
            initial = dict(self._desired_hotkeys)
        self._apply_hotkeys(libs, initial)
        libs.user32.SetTimer(
            self._hwnd, ctypes.c_void_p(SWEEP_TIMER_ID), SWEEP_MS, None
        )
        self._ready.set()
        self._apply_alerts(libs, self._drain_alerts())

        msg = wintypes.MSG()
        while libs.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            libs.user32.TranslateMessage(ctypes.byref(msg))
            libs.user32.DispatchMessageW(ctypes.byref(msg))

    def _create_host_window(self, libs):
        """A message-only window that outlives every preview.

        Not optional: PostMessageW needs an HWND, and there is no preview
        to post to when zero clients are running -- which is the state at
        startup and after the last client quits. Without this, stop() has
        nothing to signal and blocks until its timeout on exactly the
        paths that matter most.
        """

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", win32.wndproc_type()),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        proc = win32.wndproc_type()(self._host_proc)
        win32._KEEPALIVE.append(proc)
        cls = WNDCLASSW()
        cls.lpfnWndProc = proc
        cls.hInstance = libs.kernel32.GetModuleHandleW(None)
        cls.lpszClassName = "WingmanPreviewHost"
        libs.user32.RegisterClassW(ctypes.byref(cls))
        return libs.user32.CreateWindowExW(
            0,
            "WingmanPreviewHost",
            "wingman-preview-host",
            0,
            0,
            0,
            0,
            0,
            wintypes.HWND(win32.HWND_MESSAGE),
            None,
            cls.hInstance,
            None,
        )

    def _host_proc(self, hwnd, msg, wparam, lparam):
        libs = win32.bind()
        if msg == win32.WM_TIMER and wparam == ACTIVATE_RETRY_TIMER_ID:
            self._retry_pending_activation(libs)
            return 0
        if msg == win32.WM_TIMER and wparam == SWEEP_TIMER_ID:
            self._sweep(libs)
            return 0
        if msg == win32.WM_TIMER and wparam == ALERT_TIMER_ID:
            self._tick_alerts(libs)
            return 0
        if msg == win32.WM_APP_SWEEP_NOW:
            self._sweep(libs)
            return 0
        if msg == win32.WM_APP_SHUTDOWN:
            self._teardown(libs)
            return 0
        if msg == win32.WM_APP_REBIND:
            with self._lock:
                table = dict(self._desired_hotkeys)
            self._apply_hotkeys(libs, table)
            return 0
        if msg == win32.WM_APP_ALERT:
            self._apply_alerts(libs, self._drain_alerts())
            return 0
        if msg == win32.WM_APP_RESTYLE:
            self._restyle(libs)
            return 0
        if msg == win32.WM_APP_RESIZE_ONE:
            self._apply_resizes()
            return 0
        if msg == win32.WM_APP_RESIZE_ALL:
            self._apply_resize_all()
            return 0
        if msg == win32.WM_APP_RESET_LAYOUTS:
            self._reset_layouts()
            return 0
        if msg == win32.WM_APP_APPLY_LAYOUTS:
            self._apply_layouts()
            return 0
        if msg == win32.WM_HOTKEY:
            idents = coalesce_hotkey_ids(libs.user32.PeekMessageW, hwnd, wparam)
            self._on_hotkeys(libs, idents)
            return 0
        return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _install_hook(self, libs):
        """Foreground changes trigger a sweep, but never inline: the hook
        callback arrives on an arbitrary thread, and touching HWNDs from
        there is the thread-affinity violation that hangs."""

        def on_event(hook, event, hwnd, obj, child, tid, ms):
            # Recorded, not resolved: this callback arrives on an arbitrary
            # thread and must not touch a preview. _sweep resolves it, which
            # is also the only place _clients is refreshed -- so a
            # just-launched client's first focus cannot resolve against a
            # stale registry.
            self._foreground = int(hwnd) if hwnd else 0
            self.request_sweep()

        cb = win32.winevent_proc_type()(on_event)
        win32._KEEPALIVE.append(cb)
        self._hook = libs.user32.SetWinEventHook(
            win32.EVENT_SYSTEM_FOREGROUND,
            win32.EVENT_SYSTEM_FOREGROUND,
            None,
            cb,
            0,
            0,
            win32.WINEVENT_OUTOFCONTEXT,
        )
        if not self._hook:
            logger.warning(
                "SetWinEventHook failed; previews will only refresh on the %dms sweep",
                SWEEP_MS,
            )

    def _sweep(self, libs) -> None:
        clients = {c.stable_key: c for c in discovery.list_clients()}
        # A title change from a named character to character selection changes
        # the stable key even though the physical client continues. Capture the
        # live rect before reconciliation closes the named window. This is
        # continuity, not restoration, so restore_preview_positions does not
        # decide whether the rect survives.
        previous_by_process = {
            (client.hwnd, client.pid): self._windows.get(key)
            for key, client in self._clients.items()
            if client.character
        }
        last_character = dict(self._last_character_by_process)
        for client in self._clients.values():
            if client.character:
                last_character[(client.hwnd, client.pid)] = client.character
        present_processes = {(client.hwnd, client.pid) for client in clients.values()}
        last_character = {
            process: character
            for process, character in last_character.items()
            if process in present_processes
        }
        for client in clients.values():
            if client.character:
                last_character[(client.hwnd, client.pid)] = client.character
        self._last_character_by_process = last_character

        continuity_rects = {}
        for key, client in clients.items():
            if client.character:
                continue
            previous = previous_by_process.get((client.hwnd, client.pid))
            if previous is not None:
                continuity_rects[key] = previous.rect
        # Guarded like _apply_selection's libs.user32 read below: several
        # tests drive _sweep with libs=None to exercise placement without
        # standing up the whole Win32 surface, and GetClientRect is not
        # needed for those -- only real callers, which always pass real
        # libs, get sampled sizes.
        if libs is not None:
            self._record_client_sizes(libs, clients)
        discovery.flush_image_cache_periodically()
        before = self.characters()
        # Wholesale, never merged. reconcile() compares stable keys only, so
        # a character that reappears on a new HWND between sweeps counts as
        # "kept" -- keeping the old record would leave it pointing at a dead
        # window. Keys survive; handles are re-read.
        self._clients = clients
        # The DESIRED window set, not the discovered one. A character opted
        # out of previews is still discovered, still reported to the page
        # and still in _clients -- they simply get no window, which is what
        # makes ticking the box mid-session close the one already open
        # (reconcile puts them in `removed`) and unticking it open a new one.
        #
        # Filtering `clients` itself instead would take the character off
        # the page's row list, leaving no row to untick.
        desired = {
            key
            for key, client in clients.items()
            if not self._is_excluded(
                client.character or last_character.get((client.hwnd, client.pid)) or key
            )
        }
        added, removed, _kept = reconcile(set(self._windows), desired)

        for key in removed:
            self._windows.pop(key).close()

        # Once per sweep, not once per added preview: the hardware does not
        # change between two keys of the same batch, and a failure here must
        # not log a line per client.
        monitors = self._monitors() if added else []

        for key in added:
            client = clients[key]
            entry = self._layout_entry(key)
            continuity = continuity_rects.get(key)
            rect = (
                geometry.clamp_to_monitors(continuity, monitors)
                if continuity is not None
                else self._resolve_rect(key, len(self._windows), monitors, entry)
            )
            win = PreviewWindow.create(
                libs,
                client,
                rect,
                on_activate=lambda c: self._activate_client(libs, c),
                on_rect_changed=self._layout_changed,
                neighbours=lambda k=key: [
                    w.rect for k2, w in self._windows.items() if k2 != k
                ],
                screen=self._screen,
                # Resolved from the `locked` character-name list, not from
                # entry.locked: Task 1 moved lock storage to
                # preview.locked, so the saved layout entry is no longer
                # the source of truth for what a NEW window opens locked
                # as. entry.locked is now written by _layout_changed and
                # deserialized by layout.py but read by nothing -- retained
                # rather than removed because it still round-trips through
                # the layouts section of every existing settings file, and
                # dropping the field would discard that data on the next
                # save for no gain.
                locked=self._is_locked(key),
                show_labels=self._labels_shown(),
                opacity=self._current_opacity(),
                snap=self._snapping(),
                lock_aspect=self._locking_aspect(),
                selection_color=self._selection_ring_color(),
                # Bound per window: the mirror must skip the very window
                # that is driving the drag, and the key is only known
                # here, at creation.
                on_resize_all=lambda rect, k=key: self._mirror_resize(k, rect),
            )
            if win is not None:
                self._windows[key] = win

        if added or removed:
            logger.info(
                "Preview sweep: +%s -%s (%d live)", added, removed, len(self._windows)
            )

        now = self.characters()
        if now != before and self._on_clients_changed is not None:
            # Guarded like _flush_layouts in _teardown: this runs inside
            # _run(), before SetTimer/_ready.set() on the very first sweep.
            # An exception here would unwind out of _run and kill the pump
            # while self._hwnd is still set -- previews dead for the
            # session, and stop() then blocks for JOIN_TIMEOUT_S posting to
            # a window nothing is pumping for.
            try:
                self._on_clients_changed(now)
            except Exception:
                logger.exception("on_clients_changed callback raised")

        self._apply_selection(libs)

    def _apply_selection(self, libs) -> None:
        """Push both flags -- which client has the foreground, and which
        one the ring is drawn on -- onto the previews.

        They part company whenever the foreground is not an EVE client.
        Focus goes to None there; the ring stays where it was, on the last
        client used, because that client is still the one on screen and
        losing the highlight for the duration of a glance at a browser
        reads as a bug.

        The ring was cleared here too, once, so that a sticky highlight
        could never be mistaken for an alert or quietly acknowledge one.
        That reasoning survives intact -- it just attaches to focus now,
        which is what PreviewWindow spends `selected`/`focused` on.
        """
        foreground = self._foreground or (
            libs.user32.GetForegroundWindow() if libs is not None else 0
        )
        focus = next(
            (k for k, c in self._clients.items() if c.hwnd == foreground), None
        )
        self._focused_key = focus
        if focus is not None:
            self._selected_key = focus
        elif self._selected_key not in self._clients:
            # Sticky outlives the foreground, never the client. _clients was
            # replaced wholesale in _sweep just above, so a character that
            # has logged out is already gone from it; without this the ring
            # would sit on a dead key for the session and then be handed
            # straight back to whatever reappeared under the same name.
            self._selected_key = None

        # Every window, every sweep, rather than a diff against the previous
        # keys. Both setters early-return on an unchanged flag (window.py's
        # set_selected/set_focused), so the cost is one attribute compare per
        # preview per 700ms -- and applying unconditionally is what puts the
        # ring on a preview whose creation failed on an earlier sweep and
        # succeeded on this one, while its client held the foreground
        # throughout. That case used to need a branch of its own.
        for key, win in self._windows.items():
            win.set_focused(key == focus)
            win.set_selected(key == self._selected_key)

        self._apply_visibility(libs, foreground)

    def _apply_visibility(self, libs, foreground) -> None:
        """Hide or show every preview according to hide-on-lost-focus.

        Runs off _apply_selection's already-resolved foreground rather than
        on a poll of its own: that call site is reached from both the 700ms
        sweep and the foreground hook, which is exactly the set of moments
        this can change. A timer here would be a third clock measuring the
        same thing.

        The decision itself is visibility.should_hide, kept pure so the
        truth table is testable on Linux -- the same split switching.py
        draws for minimize.

        Nothing here is per character: the flag is a fact about the
        foreground, so the settings read and the ownership probe happen
        once and every window gets the same answer. set_hidden early-returns
        on an unchanged flag, so the steady-state cost is one attribute
        compare per preview.

        `_previews_hidden` is what makes the off path free. It records what
        was last applied, so a host with the feature off -- the default,
        and so most installs -- returns before reading the foreground's
        process at all. It cannot be replaced by "skip when nothing
        changed": while previews ARE hidden, a client appearing mid-hide
        creates a window born visible, and only re-applying every sweep
        catches it.
        """
        enabled = self._hiding_on_lost_focus()
        if not enabled and not self._previews_hidden:
            return
        # The same fallback _apply_selection makes, and for the same
        # reason: `self._foreground` is 0 until the win-event hook first
        # fires, goes back to 0 whenever the hook reports no foreground,
        # and stays 0 all session if SetWinEventHook failed -- which is
        # logged and carried on from, not fatal.
        #
        # _apply_selection reaches here having already resolved it, so
        # this only bites on the _restyle path, which hands over the raw
        # value. Without it a 0 is simply "not one of the clients" and
        # every preview hides the moment any unrelated setting changes,
        # reappearing a sweep later with nothing to explain the flash.
        if not foreground and libs is not None:
            foreground = libs.user32.GetForegroundWindow()
        hide = visibility.should_hide(
            enabled=enabled,
            foreground=foreground,
            client_hwnds=[c.hwnd for c in self._clients.values()],
            foreground_is_ours=self._foreground_is_ours(libs, foreground),
        )
        for win in self._windows.values():
            win.set_hidden(hide)
        self._previews_hidden = hide

    def characters(self) -> list:
        """Named characters currently discovered, sorted. Safe from any
        thread: the registry is replaced wholesale, never mutated in place.

        Clients at character-select are excluded -- discovery falls their
        stable_key back to "hwnd:0x...", which names nothing a user could
        bind to.
        """
        return sorted(key for key in self._clients if not key.startswith("hwnd:"))

    def _registerable(self, table) -> dict:
        """*table* with opted-out characters dropped.

        Applied here rather than in plan_registrations, which is pure and
        stays that way -- and applied on every rebind rather than once,
        because the excluded list changes independently of the binding
        table: ticking the box does not edit a single chord, so api.py
        re-pushes the SAME table to force this filter to run again.

        The two cycle chords are untouched: they are app commands, not
        characters, and there is nothing to opt out of them.
        """
        table = dict(table or {})
        characters = table.get("characters")
        if not isinstance(characters, dict):
            return table
        table["characters"] = {
            name: chord
            for name, chord in characters.items()
            if not self._is_excluded(name)
        }
        return table

    def _apply_hotkeys(self, libs, table) -> None:
        """Unregister everything, then register the new table."""
        for ident in list(self._registered):
            libs.user32.UnregisterHotKey(self._hwnd, ident)
        self._registered.clear()
        self._registered_text.clear()

        status = {}
        for ident, text, action in plan_registrations(self._registerable(table)):
            parsed = gestures.parse(text)
            ok = bool(
                libs.user32.RegisterHotKey(self._hwnd, ident, parsed.mods, parsed.vk)
            )
            status[text] = ok
            if ok:
                self._registered[ident] = action
                self._registered_text[ident] = text
            else:
                # A chord another application already owns. User-actionable,
                # not a bug -- and the parent design requires it be visible
                # rather than logged only.
                logger.warning(
                    "Could not register preview hotkey %s; "
                    "another application may already own it",
                    text,
                )
        self._hotkey_status = status
        # One line per pass, not per chord: this is the only place that
        # would tell "nothing is bound" from "everything failed" from
        # "some chord lost the fight" if a field report ever needed it.
        logger.info(
            "Preview hotkeys: %d registered, %d refused",
            sum(1 for ok in status.values() if ok),
            sum(1 for ok in status.values() if not ok),
        )
        if self._on_hotkey_status is not None:
            # Guarded for the same reason as _on_clients_changed above: the
            # initial pass runs in _run() before SetTimer/_ready.set(), and
            # a raise here would otherwise kill the pump and strand
            # self._hwnd -- or, from WM_APP_REBIND, propagate into the
            # wndproc where sys.unraisablehook silently swallows it.
            try:
                self._on_hotkey_status(dict(status))
            except Exception:
                logger.exception("on_hotkey_status callback raised")

    def _on_hotkey(self, libs, ident) -> None:
        """Keep the one-message entry point for direct callers and tests."""
        self._on_hotkeys(libs, [ident])

    def _on_hotkeys(self, libs, idents: list[int]) -> None:
        registered = []
        for ident in idents:
            action = self._registered.get(ident)
            if action is None:
                # Not silent by accident: this is the one case Risk 4 (does
                # WM_HOTKEY even reach this window) would look like on a real
                # machine, and it must not read the same as "nothing happened
                # because nothing was pressed".
                logger.debug("WM_HOTKEY for unknown id %s ignored", ident)
                continue
            registered.append((ident, action))

        newest_text = next(
            (
                self._registered_text.get(ident)
                for ident, _action in reversed(registered)
                if self._registered_text.get(ident)
            ),
            None,
        )
        if self._take_capture(newest_text):
            if len(registered) > 1:
                logger.debug(
                    "Coalesced preview hotkeys: %d -> captured %s",
                    len(registered),
                    newest_text,
                )
            return
        if not registered:
            return

        foreground = libs.user32.GetForegroundWindow()
        foreground_key = next(
            (key for key, client in self._clients.items() if client.hwnd == foreground),
            None,
        )
        # This is a virtual cursor over the whole batch. Focus tie-breaking
        # starts from the actual foreground; only cycle actions may fall back
        # to the last cycle target when no action in this batch established one.
        target = foreground_key
        cycle_seen = False
        final_action = None
        for _ident, action in registered:
            final_action = action
            kind, value = action
            if kind == "focus":
                target = self._pick_focus_target(value, target)
                if target is None:
                    # An unavailable absolute request supersedes an earlier
                    # virtual target; a later action can establish a new one.
                    logger.debug("Preview hotkey targets %r are not running", value)
                continue

            cycle_seen = True
            keys = self._cycle_keys()
            if not keys:
                # Distinct from the "not running" no-op below, and it has
                # to be: every candidate here IS running, and was left out
                # on purpose. Borrowing that message would send a reader
                # looking for a client that is on screen in front of them.
                logger.debug(
                    "Cycle keybind had nothing to visit: every running "
                    "character is opted out of previews"
                )
                target = None
                continue
            target = cycle.step(keys, target or self._last_cycled, value)

        if cycle_seen and target is not None:
            self._last_cycled = target
        if len(registered) > 1:
            logger.debug(
                "Coalesced preview hotkeys: %d, final %s -> %s",
                len(registered),
                final_action,
                target,
            )
        else:
            logger.debug("Preview hotkey fired: %s -> %s", final_action, target)

        if target is None:
            # The action-specific branch already explained why resolution
            # failed; a second "target None is not running" line is noise.
            return
        if cycle_seen and target == foreground_key:
            # A folded cycle sequence can cancel back to its starting client,
            # so activating would add work without changing sequential state.
            # This intentionally also makes cycling a one-client roster a no-op.
            return
        client = self._clients.get(target)
        if client is None:
            # A concrete target can disappear between resolution and dispatch.
            logger.debug("Preview hotkey target %r is not running", target)
            return
        # Folding ends in one host-owned switch, including its pending-restore
        # and minimize decisions.
        self._activate_client(libs, client)

    def _take_capture(self, text) -> bool:
        """Hand *text* to an armed capture. Returns whether it was taken.

        Disarms on the way out: the page sends set_capture(False) too, but
        that round trip is not instant and a second press arriving inside
        it must not be eaten as well.
        """
        if not text:
            return False
        with self._lock:
            if time.monotonic() >= self._capture_until:
                return False
            self._capture_until = 0.0
        logger.debug("Preview hotkey %s taken by an armed bind capture", text)
        if self._on_bind_captured is not None:
            try:
                self._on_bind_captured(text)
            except Exception:
                # Same guard as _on_hotkey_status: this is outside code
                # called from the wndproc, where sys.unraisablehook would
                # swallow the traceback and leave the pump in doubt.
                logger.exception("on_bind_captured callback raised")
        return True

    def _pick_focus_target(self, names, current_target):
        """Which of the characters sharing this chord to switch to.

        Several names on one chord is the supported multibox setup (see
        plan_registrations): the same key every session, whoever of that
        group is up. So offline names are not an error here, they are the
        normal case -- they are simply skipped.

        Among the ones running, prefer any that is not the batch's virtual
        target, so queued presses behave like sequential activations even
        though only the final target is activated. It is a tie-break and not
        a filter: with a single running match that is already the target, that
        match is still the answer, or the key would go dead on that client.

        Sorted, so with several running and no current match the choice is
        stable rather than dependent on discovery order.
        """
        running = sorted(name for name in names if name in self._clients)
        if not running:
            return None
        for name in running:
            if name != current_target:
                return name
        return running[0]

    def _arm_pending_activation(self, libs, pending: _PendingSwitch) -> None:
        """Retain the newest restore request and arrange its next pump turn."""
        self._pending_switch = pending
        if self._hwnd and libs is not None and not self._pending_activation_timer:
            libs.user32.SetTimer(
                self._hwnd,
                ctypes.c_void_p(ACTIVATE_RETRY_TIMER_ID),
                ACTIVATE_RETRY_MS,
                None,
            )
            self._pending_activation_timer = True

    def _clear_pending_activation(self, libs) -> None:
        """Forget an outstanding restore and stop its timer exactly once."""
        self._pending_switch = None
        if self._pending_activation_timer:
            if self._hwnd and libs is not None:
                libs.user32.KillTimer(
                    self._hwnd, ctypes.c_void_p(ACTIVATE_RETRY_TIMER_ID)
                )
            self._pending_activation_timer = False

    def _complete_pending_minimize(self, libs, pending: _PendingSwitch) -> None:
        """Minimize the verified outgoing client after its iconic switch wins."""
        if not pending.minimize:
            return
        previous = self._clients.get(pending.previous_key)
        if previous is None or previous.hwnd != pending.previous_hwnd:
            logger.info(
                "Pending activation of %s: saved minimize skipped; previous %s "
                "exited or changed",
                pending.stable_key,
                pending.previous_key,
            )
            return
        with _animation_off(libs):
            self._minimize(libs, previous.hwnd)

    def _mark_client_activated(self, libs, client) -> None:
        """Commit foreground-derived host state after an observed success."""
        self._foreground = client.hwnd
        self._apply_selection(libs)

    def _retry_pending_activation(self, libs) -> None:
        """Retry one restored target without ever waiting inside the pump."""
        pending = self._pending_switch
        if pending is None:
            return
        client = self._clients.get(pending.stable_key)
        if client is None or client.hwnd != pending.hwnd:
            logger.info(
                "Pending activation of %s discarded; its window exited or changed",
                pending.stable_key,
            )
            self._clear_pending_activation(libs)
            return

        result = window_mod.activate(libs, client.hwnd)
        if result is window_mod.ActivationResult.ACTIVATED:
            self._clear_pending_activation(libs)
            self._complete_pending_minimize(libs, pending)
            self._mark_client_activated(libs, client)
            return
        if result is window_mod.ActivationResult.PENDING_RESTORE:
            attempts = pending.attempts + 1
            if attempts < ACTIVATE_RETRY_MAX:
                self._arm_pending_activation(
                    libs,
                    _PendingSwitch(
                        pending.stable_key,
                        pending.hwnd,
                        pending.previous_key,
                        pending.previous_hwnd,
                        pending.minimize,
                        attempts,
                    ),
                )
                return
            logger.info(
                "Activation of %s did not complete after %d restore retries",
                pending.stable_key,
                ACTIVATE_RETRY_MAX,
            )
        else:
            logger.info("Pending activation of %s was refused", pending.stable_key)
        self._clear_pending_activation(libs)

    def _activate_client(self, libs, client) -> window_mod.ActivationResult:
        """Switch the foreground to *client* and report the observed result.

        The single owner of the switch. Both entry points land here -- a
        hotkey, and a click on a preview (PreviewWindow classifies the
        gesture and calls this through its on_activate callback, rather
        than activating on its own as it used to). Keeping one sequence
        is what lets the host read the outgoing foreground before it
        moves; a later step in the switch added here applies to both.

        The ActivationResult is window_mod.activate's observed
        GetForegroundWindow verdict. It must be compared by identity: each
        enum value is truthy, including refused and pending restore.

        The order is EVE-O Preview's (ThumbnailManager.SwitchActiveClient:
        MinimizeWindow, then ActivateWindow), and it replaced TriffView's
        activate / settle 10ms / minimize / re-activate:

        - The minimize goes to a client that still HAS the foreground.
          It does NOT make the send reliably faster: measured on two
          live clients 2026-08-30, both orders are quick when the
          clients are quiet -- old order median 29.6ms, new order
          40.0ms, and with this thread owning a DWM thumbnail of the
          target (the app's real shape) the old order ran 9.1ms. None
          of 26 probe sends came near the budget.

          What it does buy is what happens when the send DOES exceed
          the budget: a timed-out send is still delivered later, and in
          the old order that late minimize landed on the window the
          switch had just left, which is where the compensating
          re-activation came from. Minimizing before the activation
          means a late minimize lands on a window that is no longer
          the foreground, so it cannot take focus off the client the
          user just asked for.

          An earlier version of this comment said the old send "timed
          out for its full budget on every switch (166 consecutive
          timeouts)". That is not supported: the code logs only the
          FAILURES, never the successes, so the field log's 223 lines
          have no denominator. The 44 of them that carry an elapsed
          time are real waits clipped at the budget (min 102ms, median
          114ms, max 231ms), spread across normal play, and no probe
          has reproduced one -- the remaining candidate is the client's
          own message-pump latency during a busy moment (grid load, a
          jump, a session change), which is EVE-side and not ordering.
        - No settle sleep remains. It used to stall this thread -- the pump
          that handles hotkeys, alerts, sweeps, and preview mouse messages --
          solely to separate a post-activation minimize and compensating
          re-activation that this ordering removed.
        - A pending restore does not minimize at all while Windows catches
          up. Its timer retries from the pump; only an observed success,
          including an iconic target that succeeds immediately, applies the
          already-recorded outgoing minimize decision. This is deliberately
          limited to the iconic/pending continuation: minimizing after an
          ordinary activation can steal foreground from the target. The
          external transition probe supplied no safe basis for changing that
          general order, so only the pending-restore case differs.
        - A refused non-iconic activation attempts to bring the outgoing
          client back (switching.should_restore); the restore can itself be
          refused, so the desktop-gap risk remains with minimize-first.

        Every decision about *whether* to minimize or restore lives in
        switching.py so it can be tested off Windows; this function owns
        only the Win32 calls and their order.
        """
        # Read BEFORE anything moves: once the foreground has changed
        # there is nothing left to identify the outgoing client by. This
        # ordering is the reason the switch has a single owner -- the
        # click path used to activate inside window.py and tell the host
        # afterwards, by which point this read was already too late.
        # A newer click or hotkey is user intent too. It must supersede a
        # restore still awaiting its first foreground verdict.
        self._clear_pending_activation(libs)
        previous_hwnd = libs.user32.GetForegroundWindow() if libs is not None else 0
        previous_key, previous = next(
            ((k, c) for k, c in self._clients.items() if c.hwnd == previous_hwnd),
            (None, None),
        )

        minimize = switching.should_minimize(
            enabled=self._minimizing_inactive(),
            previous_key=previous_key,
            next_key=client.stable_key,
            # should_minimize only asks whether previous_key is in the
            # roster, so the guarded per-key reader answers it exactly;
            # there is no guarded reader for the whole list.
            never=[previous_key] if self._is_never_minimize(previous_key) else [],
        )

        # PENDING_RESTORE is only possible for an iconic target. Preserve the
        # existing minimize-first behavior for all other switches, but leave
        # the outgoing client alone while this target's restoration races.
        # window_mod.activate probes IsIconic again because it owns restoration
        # and its verdict; this probe has to precede that external call so the
        # host can choose its ordering. Sharing it would couple those layers
        # and still race a window changing state between the two operations.
        target_was_iconic = (
            bool(libs.user32.IsIconic(client.hwnd)) if libs is not None else False
        )
        pending = _PendingSwitch(
            client.stable_key,
            client.hwnd,
            previous_key,
            previous_hwnd,
            minimize,
        )
        with _animation_off(libs):
            if minimize and not target_was_iconic:
                self._minimize(libs, previous.hwnd)
            try:
                result = window_mod.activate(libs, client.hwnd)
            except Exception:
                # The outgoing client is already down and the verdict was
                # never reached. On the click path the caller is the
                # ctypes WndProc, which prints an uncaught exception to
                # stderr and swallows it -- so without this the user gets
                # the empty desktop with no line in the log. Roll back,
                # say so, and let the exception carry on to whoever logs
                # it; the switch itself is still a failure.
                if switching.should_restore(
                    activated=False, attempted=minimize and not target_was_iconic
                ):
                    logger.exception(
                        "Switch to 0x%x raised; restoring 0x%x",
                        client.hwnd,
                        previous.hwnd,
                    )
                    window_mod.activate(libs, previous.hwnd)
                raise
            if result is window_mod.ActivationResult.PENDING_RESTORE:
                self._arm_pending_activation(libs, pending)
                return result
            if result is window_mod.ActivationResult.ACTIVATED:
                if target_was_iconic:
                    self._complete_pending_minimize(libs, pending)
                # The ring moves HERE, inline, the instant the switch is
                # known to have taken -- not on the sweep the foreground
                # hook asks for. The hook and the sweep stay exactly as
                # they were: they are still the only thing that catches
                # alt-tab, and the only thing that moves the ring off a
                # client the user left by any route other than a switch
                # Wingman performed itself. TriffView marks its highlight
                # in the same place (TriffViewSubsystem.cs,
                # TryActivateClient).
                #
                # Assigned rather than left for the hook to report:
                # activate() read GetForegroundWindow to reach `ok`, so
                # this IS the live foreground, and _apply_selection
                # prefers _foreground over a syscall of its own. Leaving
                # it stale would make the line below re-apply the
                # OUTGOING client's ring.
                self._mark_client_activated(libs, client)
            elif switching.should_restore(
                activated=False, attempted=minimize and not target_was_iconic
            ):
                # activate() restores an iconic window before raising it,
                # so this one call undoes the minimize AND hands the
                # foreground back. Its verdict does not reach the caller
                # -- their bool is about the client they asked for -- but
                # it is logged: the refusal that stopped the switch (no
                # recent input in this process) applies to the rollback
                # too, and without this line the user's log shows two
                # "did not take" lines for two hwnds with nothing saying
                # the second was a rollback. A refused rollback IS the
                # empty-desktop case the smoke checklist says to watch.
                restored = window_mod.activate(libs, previous.hwnd)
                logger.info(
                    "Switch to 0x%x refused; %s 0x%x",
                    client.hwnd,
                    (
                        "restored"
                        if restored is window_mod.ActivationResult.ACTIVATED
                        else "could not restore"
                    ),
                    previous.hwnd,
                )
        return result

    def _minimize(self, libs, hwnd) -> None:
        """Send SC_MINIMIZE to *hwnd*, logging a send that did not complete.

        No verdict is returned on purpose: a timed-out send is still
        delivered later, so the caller could not act on "it did not
        minimize" even if told -- see switching.should_restore.
        """
        started = time.perf_counter()
        sent = libs.user32.SendMessageTimeoutW(
            hwnd,
            win32.WM_SYSCOMMAND,
            win32.SC_MINIMIZE,
            0,
            win32.SMTO_ABORTIFHUNG,
            MINIMIZE_TIMEOUT_MS,
            None,
        )
        if sent:
            return
        # Zero covers three cases the API does not separate: the send
        # timed out, it was abandoned because the client was hung
        # (ABORTIFHUNG), or it simply failed -- an invalid hwnd, or a
        # client that exited between the foreground read and here. A timed-out
        # send may still be delivered later, so the switch cannot infer the
        # client's final show state from this return. INFO for
        # the same reason window.py logs a refused activation at INFO:
        # the root logger runs at INFO, and this is what "minimize
        # sometimes does nothing" looks like in a user's log.
        #
        # The elapsed time is what separates those three, and it is the
        # only one of them a user's log can ever tell us: a send that
        # spent the whole budget waiting really did time out, while one
        # that came back in under a millisecond was refused outright and
        # never waited for anything. Without it the line reads
        # identically either way -- which is how a live install could
        # log 166 of these in a session and still leave the cause open.
        logger.info(
            "Minimize of 0x%x did not complete (timeout or abandoned) "
            "after %.0fms of a %dms budget; leaving it as it is",
            hwnd,
            (time.perf_counter() - started) * 1000,
            MINIMIZE_TIMEOUT_MS,
        )

    def _apply_alerts(self, libs, pending) -> None:
        """Arm the preview each event names, then make sure the tick timer
        matches reality.

        The lookup is direct: `_windows` is keyed by `Client.stable_key`,
        which discovery sets to the character name for any client past
        character-select (`discovery.py:71`), and the character an alert
        names comes from that client's own gamelog. An alert for a
        character with no preview -- previews off for that client, or it
        quit between the log line and this drain -- is a no-op, and is
        logged rather than dropped silently, because "the sound played and
        nothing flashed" is otherwise indistinguishable from a broken
        render path.

        preview.excluded made that state reachable ON PURPOSE rather than
        only transiently, so the choice is now worth stating: an excluded
        character still PLAYS its alert sound, with nothing on screen to
        flash. That is deliberate. The alert is what tells a multiboxer
        something is happening to a character they are not watching, and
        the character they have chosen not to mirror is exactly the one
        they are not watching -- silencing it would remove the last signal
        rather than an unwanted one. Alerts have their own per-event
        enable in Settings for anyone who wants the opposite.
        """
        now = time.monotonic()
        for character, event, spec in pending:
            win = self._windows.get(character)
            if win is None:
                logger.debug(
                    "Alert for %s (%s): no preview open, so only the sound played",
                    character,
                    event,
                )
                continue
            win.arm_alert(event, spec, now)
        self._update_alert_timer(libs)

    def _update_alert_timer(self, libs) -> None:
        """Start the tick timer when anything is armed, kill it when
        nothing is. Idempotent: SetTimer on a live id just resets it."""
        if self._hwnd is None:
            return
        armed = any(w.alert_is_armed() for w in self._windows.values())
        if armed and not self._alert_timer:
            libs.user32.SetTimer(
                self._hwnd, ctypes.c_void_p(ALERT_TIMER_ID), ALERT_MS, None
            )
            self._alert_timer = True
        elif not armed and self._alert_timer:
            libs.user32.KillTimer(self._hwnd, ctypes.c_void_p(ALERT_TIMER_ID))
            self._alert_timer = False

    def _tick_alerts(self, libs) -> None:
        """One pulse frame for every armed preview."""
        now = time.monotonic()
        for win in list(self._windows.values()):
            if not win.alert_is_armed():
                continue
            try:
                win.tick_alert(now)
            except Exception:
                # Guarded per window, like every other callback on this
                # thread: an exception here unwinds into the WndProc where
                # sys.unraisablehook swallows it, so one bad preview would
                # silently stop every OTHER preview's pulse and keep doing
                # so 12 times a second.
                logger.exception("Alert tick failed for %s", win.client.stable_key)
                win.clear_alert()
        self._update_alert_timer(libs)

    def _screen(self):
        """Virtual-desktop bounds, re-read each sweep.

        Not cached for the process: monitors get plugged in, unplugged,
        and rearranged while Wingman runs, and a stale origin puts new
        previews off-screen where they cannot be dragged back.
        """
        libs = win32.bind()
        return geometry.virtual_desktop(libs.user32.GetSystemMetrics)

    def _monitors(self):
        """Every attached display, as absolute rects.

        Re-read per sweep for the same reason as `_screen`, and separate
        from it because they are genuinely different shapes: `_screen` is
        the bounding rectangle of all monitors, this is the monitors
        themselves. Where the arrangement is not flush-aligned the two
        differ, and the difference is space no display covers.

        Any failure yields an empty list, which `clamp_to_monitors` treats
        as "do not move anything". That includes a PARTIAL failure, where
        the enumeration succeeds but one monitor does not report: a short
        list is worse than no list, because `clamp_to_monitors` cannot
        tell a missing display from dead space and would haul every
        preview off the unreported monitor onto a reported one, silently
        collapsing the user's layout onto one screen.

        Declining to clamp is the safe direction either way -- the worst
        case is the placement we had before this existed.
        """
        libs = win32.bind()
        found = []
        failed = []

        def callback(hmonitor, hdc, lprect, lparam):
            # Body wrapped for the same reason evewindows.py wraps its
            # EnumWindows callback: an exception here cannot propagate out
            # of a ctypes callback, so it would otherwise reach
            # sys.unraisablehook -- which is stderr, and stderr is nowhere
            # at all in a console=False frozen build.
            try:
                info = win32.MONITORINFO()
                info.cbSize = ctypes.sizeof(win32.MONITORINFO)
                if libs.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                    r = info.rcMonitor
                    found.append(
                        geometry.Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)
                    )
                else:
                    failed.append(hmonitor)
            except Exception:
                logger.exception("Skipped a monitor during enumeration.")
                failed.append(hmonitor)
            return True

        proc = win32.monitor_enum_proc_type()(callback)
        # Held only for the duration of the call: EnumDisplayMonitors is
        # synchronous and Windows does not retain the pointer afterwards,
        # unlike the WndProc and WinEvent callbacks that _KEEPALIVE exists
        # for. A local reference is enough to keep it alive across the call.
        if not libs.user32.EnumDisplayMonitors(None, None, proc, 0):
            logger.warning(
                "EnumDisplayMonitors failed; preview placement "
                "will not be clamped to a display this sweep"
            )
            return []
        if failed:
            logger.warning(
                "GetMonitorInfoW failed for %d of %d monitors; "
                "preview placement will not be clamped to a "
                "display this sweep",
                len(failed),
                len(failed) + len(found),
            )
            return []
        if not found:
            # A TRUE return with no callbacks at all: an RDP session or
            # every display asleep. Distinguishable from "clamping ran and
            # nothing needed moving" only if it is said out loud.
            logger.warning(
                "EnumDisplayMonitors reported no displays; "
                "preview placement will not be clamped"
            )
        return found

    def _resolve_rect(self, key, index, monitors, entry=None):
        """Where preview *key* should sit: its saved rect, or a default.

        Clamped either way. The default can land in a dead zone of the
        virtual desktop's bounding box, and a saved rect can name a
        monitor that has since been unplugged; both put the preview
        somewhere it cannot be seen or grabbed, and a preview that cannot
        be grabbed can never be dragged back to somewhere it can.

        The `restore_preview_positions` setting chooses between the two
        paths; it does not choose whether to clamp. Returning the raw
        default on the off path would reintroduce exactly the off-screen
        placement this method exists to prevent.

        *monitors* is passed in rather than read here so one sweep costs
        one enumeration rather than one per added preview -- and, when
        enumeration fails, one log line rather than one per preview.
        """
        if entry is None:
            entry = self._layout_entry(key)
        if entry and self._restoring():
            # A saved rect is the user's own choice. Only rescued when it
            # is on no display at all -- pulling a preview they deliberately
            # parked half off-screen back on would be the wrong kind of help.
            return geometry.clamp_to_monitors(entry.rect, monitors)
        # A default is ours, so it is placed properly rather than merely
        # rescued: down the rightmost display, anchored to that display's
        # top edge instead of the bounding box's.
        target = geometry.stack_monitor(monitors, self._screen())
        return geometry.clamp_to_monitors(
            geometry.default_stack(index, target, self._default_size()), monitors
        )

    def _default_size(self) -> tuple:
        """The size an unsaved preview opens at, read live.

        Accepts either a plain pair or a callable returning one, so the
        positional `size=(w, h)` every existing caller passes keeps working
        while build_preview_host hands over a live read instead.

        Same posture as _snapping and the rest: this runs on the preview
        thread inside the pump, so a callable that raises must not kill it.
        The fallback is DEFAULT_SIZE, the constant this argument defaults
        to, rather than a remembered last-good value -- a preview placed at
        a stale size is harder to explain than one placed at the shipped
        one.
        """
        if self._size is None:
            return DEFAULT_SIZE
        if not callable(self._size):
            return self._size
        try:
            width, height = self._size()
            return (int(width), int(height))
        except Exception:
            logger.exception(
                "Could not read preview.width/height; using the default size"
            )
            return DEFAULT_SIZE

    def _restoring(self) -> bool:
        """Whether a saved rect should be honoured, read live.

        Runs on the preview thread inside the sweep, so it must not be
        the thing that kills the pump. A callable that raises falls back
        to restoring -- the behaviour that predates the toggle, and the
        one that loses none of the user's positioning.
        """
        if self._restore_positions is None:
            return True
        try:
            return bool(self._restore_positions())
        except Exception:
            logger.exception(
                "Could not read restore_preview_positions; restoring the saved position"
            )
            return True

    def _snapping(self) -> bool:
        """Whether a dragged preview snaps, read live.

        Same posture as _restoring(): this runs on the preview thread
        inside the pump, so a callable that raises must not be the thing
        that kills it. Falls back to snapping -- the behaviour that
        predates the toggle.
        """
        if self._snap is None:
            return True
        try:
            return bool(self._snap())
        except Exception:
            logger.exception("Could not read preview.snap; leaving snapping on")
            return True

    def _locking_aspect(self) -> bool:
        """Whether the resize handle holds the client's shape, read live.

        Same posture as _snapping(): runs on the preview thread inside the
        pump, so a callable that raises must not kill it. Falls back to
        locking -- the behaviour that predates the toggle.
        """
        if self._lock_aspect is None:
            return True
        try:
            return bool(self._lock_aspect())
        except Exception:
            logger.exception(
                "Could not read preview.lock_aspect; leaving the aspect locked"
            )
            return True

    def _selection_ring_color(self) -> str:
        """The selection ring's #rrggbb, read live.

        Same posture as _snapping(): runs on the preview thread inside the
        pump, so a callable that raises must not kill it. Falls back to the
        cyan PreviewWindow hardcoded until the setting existed, so a
        failing read changes nothing the user can see.
        """
        if self._selection_color is None:
            return "#00c8dc"
        try:
            return str(self._selection_color())
        except Exception:
            logger.exception(
                "Could not read preview.selection_color; using the default ring colour"
            )
            return "#00c8dc"

    def _labels_shown(self) -> bool:
        """Whether preview chrome draws a label band, read live.

        Runs on the preview thread -- in _sweep for a newly created
        window, and in the WM_APP_RESTYLE handler for every open one --
        so it must not be the thing that kills the pump. A callable that
        raises falls back to labels-on, the behaviour that shipped before
        this toggle existed.
        """
        if self._show_labels is None:
            return True
        try:
            return bool(self._show_labels())
        except Exception:
            logger.exception("Could not read show_labels; defaulting to labels on")
            return True

    def _current_opacity(self) -> int:
        """DWM thumbnail opacity, read live. Same guard as _labels_shown."""
        if self._opacity is None:
            return 255
        try:
            return int(self._opacity())
        except Exception:
            logger.exception("Could not read preview opacity; defaulting to opaque")
            return 255

    def _minimizing_inactive(self) -> bool:
        """Whether an unfocused client's real window should be minimized,
        read live. Same guard as _labels_shown.

        Consulted for each switch rather than cached on a preview, so a
        settings change applies immediately without rebuilding windows.
        """
        if self._minimize_inactive_clients is None:
            return False
        try:
            return bool(self._minimize_inactive_clients())
        except Exception:
            logger.exception(
                "Could not read minimize_inactive_clients; defaulting to no minimize"
            )
            return False

    def _hiding_on_lost_focus(self) -> bool:
        """Whether previews leave the screen while the foreground belongs
        to neither an EVE client nor us, read live. Same guard as
        _labels_shown; see _minimizing_inactive.

        The fallback matters more here than for the other seams: guessing
        wrong in the "on" direction leaves a user with an empty screen and
        nothing on it to explain why, so a raise means previews stay.
        """
        if self._hide_on_lost_focus is None:
            return False
        try:
            return bool(self._hide_on_lost_focus())
        except Exception:
            logger.exception(
                "Could not read hide_on_lost_focus; leaving previews visible"
            )
            return False

    def _foreground_is_ours(self, libs, foreground) -> bool:
        """Whether *foreground* is a window of this process.

        By PROCESS rather than by handle on purpose: PreviewHost is built
        in __main__.py before webview.start(), so the main window's HWND
        does not exist yet and could never be passed in. One pid compare
        covers the main window, a WM.confirm dialog, the tray menu and the
        previews themselves, and it cannot go stale when any of those are
        recreated.

        False when there are no libs -- several tests drive _sweep with
        libs=None -- and false for a foreground of 0, which is what
        GetForegroundWindow returns on a secure desktop.
        """
        if libs is None or not foreground:
            return False
        from ctypes import byref

        try:
            pid = wintypes.DWORD()
            libs.user32.GetWindowThreadProcessId(foreground, byref(pid))
            return bool(pid.value) and pid.value == libs.kernel32.GetCurrentProcessId()
        except Exception:
            logger.exception("Could not resolve the foreground window's process")
            return False

    def _is_never_minimize(self, stable_key) -> bool:
        """Whether *stable_key* is exempt from minimize_inactive_clients,
        read live. Same guard as _labels_shown; see _minimizing_inactive.
        """
        if self._never_minimize is None:
            return False
        try:
            return stable_key in (self._never_minimize() or [])
        except Exception:
            logger.exception("Could not read never_minimize; defaulting to not exempt")
            return False

    def _is_locked(self, stable_key) -> bool:
        """Whether *stable_key* is locked against drag, read live.

        The source of truth moved here from the saved layout entry's
        `locked` flag when Task 1 introduced the `preview.locked`
        character-name list -- see the comment on the _sweep call site.
        Same guard as _labels_shown.

        Two inputs, resolved together and only here. `preview.lock_default`
        says what a character NOT in the list is, so the list holds
        EXCEPTIONS to it and the answer is the exclusive-or of the two.
        With lock_default absent or False the expression collapses to
        `stable_key in locked`, which is exactly the behaviour that
        predates the setting -- which is why it needs no migration.

        Both reads are inside the one try: a failure in either leaves the
        preview unlocked, the same posture the other rosters take. Locking
        a window because a settings read failed would take away the drag
        with nothing on screen to explain it.
        """
        if self._locked is None:
            return False
        try:
            default = False
            if self._lock_default is not None:
                default = bool(self._lock_default())
            return default != (stable_key in (self._locked() or []))
        except Exception:
            logger.exception("Could not read locked; defaulting to unlocked")
            return False

    def _is_excluded(self, stable_key) -> bool:
        """Whether *stable_key* is opted out of previews entirely, read
        live. Same guard as _labels_shown.

        Defaults to NOT excluded on a read failure, which is the same
        posture the other two rosters take: a settings file that cannot be
        read must leave previews working, not silently blank the screen
        with nothing on the page to explain it.
        """
        if self._excluded is None:
            return False
        try:
            return stable_key in (self._excluded() or [])
        except Exception:
            logger.exception("Could not read excluded; defaulting to included")
            return False

    def _cycle_keys(self) -> list:
        """The characters the cycle keybinds walk.

        characters() minus the opted-out, and deliberately NOT a change to
        characters() itself: that one feeds the page's row list, which has
        to keep showing an excluded character or there would be no row left
        to re-enable them from.

        Note what this does NOT filter: the ANCHOR in _on_hotkeys is still
        resolved against _clients, so cycling while an excluded character's
        own client holds the foreground finds an anchor that is not in this
        list. cycle.step then takes its documented "anchor has gone"
        branch and restarts at the first name rather than continuing from
        the neighbour. Left as it is: it is the same fallback as cycling
        from a browser, it self-corrects on the next press, and filtering
        the anchor too would mean inventing a position in a walk this
        character is deliberately not part of.
        """
        return [key for key in self.characters() if not self._is_excluded(key)]

    def _restyle(self, libs=None) -> None:
        """Push live show_labels/opacity/locked onto every open preview,
        and re-run the visibility pass.

        minimize_inactive_clients and never_minimize are read per switch,
        not walked here -- there is no per-window state for them to update.

        hide_on_lost_focus IS walked here, unlike those two, because there
        is per-window state: unticking the box has to put the previews back
        immediately. Waiting for the next sweep would be worse than a
        700ms delay -- the user who unticks it is by definition looking at
        Wingman rather than at EVE, so on the parity reading the sweep
        would go on hiding them and the box would look inert.

        `libs` defaults to None for the TESTS, which drive this directly
        and mostly do not care about visibility. The one production caller
        -- the WM_APP_RESTYLE handler -- was changed by this branch to pass
        them, and must keep doing so: without libs `_foreground_is_ours`
        cannot claim ownership, so a restyle while Wingman itself holds the
        foreground would hide every preview.
        """
        show_labels = self._labels_shown()
        opacity = self._current_opacity()
        for key, win in self._windows.items():
            # set_labels, not an attribute write: the label is a window
            # now (see PreviewWindow._ensure_label_overlay), so showing
            # or hiding it is the method's whole job.
            win.set_labels(show_labels)
            win.opacity = opacity
            win.locked = self._is_locked(key)
            win.snap = self._snapping()
            win.lock_aspect = self._locking_aspect()
            win.selection_color = self._selection_ring_color()
            win.redraw()
            # Mirrors PreviewWindow.create/.move: opacity is a DWM
            # thumbnail property, not a chrome pixel, so it needs its own
            # push whether or not redraw() decided the bitmap changed.
            if win._thumb is not None:
                win._thumb.update(
                    # The window's CURRENT inset, not the BORDER constant.
                    # An armed alert has widened it to ALERT_BORDER so the
                    # 6px ring is not overpainted, and re-pushing BORDER
                    # here would snap the video back over the ring the
                    # moment any live setting changed under fire -- the
                    # ring left showing as corner brackets until the alert
                    # cleared, with nothing to explain it.
                    geometry.thumbnail_rect(win.rect, win._inset),
                    win.opacity,
                )

        # Last, after every window has been restyled: hiding one that is
        # about to be repainted anyway would push a bitmap nobody can see.
        self._apply_visibility(libs, self._foreground)

    def _apply_layouts(self) -> None:
        """Apply copied layouts to targets that are open on this thread.

        The saved coordinates stay byte-for-byte copied. Clamping is a display
        rescue, as it is in _resolve_rect, so reconnecting a monitor can restore
        the arrangement the user chose rather than a rewritten rescue point.
        """
        with self._lock:
            pending, self._pending_layouts = dict(self._pending_layouts), {}
        if not pending:
            return
        monitors = self._monitors()
        for key, entry in pending.items():
            win = self._windows.get(key)
            if win is not None:
                win.move(geometry.clamp_to_monitors(entry.rect, monitors))

    def _apply_resizes(self) -> None:
        """Apply every pending typed size to its still-open window.

        A stable_key with no current window is dropped rather than
        retried: set_preview_size already reported applied=True to the
        bridge before this posted message is even read, so if the client
        quit in the gap between that reply and this running, nothing here
        can un-report it -- unlike raise_alert, which documents its own
        pre-window-creation gap because that queue is drained once the
        window exists. Closing this one properly needs a round trip the
        bridge does not have.
        """
        with self._lock:
            pending, self._pending_resize = dict(self._pending_resize), {}
        for key, (w, h) in pending.items():
            win = self._windows.get(key)
            if win is None:
                continue
            win.move(win.rect._replace(w=w, h=h))
            # Recorded like a drag: a typed size is the user's choice and
            # must survive a restart exactly as a dragged position does.
            self._layout_changed(key, win.rect, win.locked)

    def _apply_resize_all(self) -> None:
        """Apply the pending bulk size to every open window.

        Recorded, unlike _reset_layouts: these sizes ARE the user's
        choice, and leaving them unrecorded would make the next launch
        re-place every window at the old default -- an apply that visibly
        undid itself on restart. Position (x, y) is kept per window; only
        w and h change.
        """
        with self._lock:
            size, self._pending_resize_all = self._pending_resize_all, None
        if size is None:
            return
        w, h = size
        for key, win in self._windows.items():
            win.move(win.rect._replace(w=w, h=h))
            self._layout_changed(key, win.rect, win.locked)

    def _reset_layouts(self) -> None:
        """Clear saved layouts and re-place every open preview.

        Deliberately does NOT record the new rects. They are defaults, and
        writing them back would repopulate the very table this just cleared --
        a reset that leaves the file exactly as full as it found it.
        """
        had_layouts = bool(self.layout_entries())
        if self._clear_layouts is not None:
            self._clear_layouts()
        self.clear_layout_entries()
        if had_layouts:
            self._announce_layouts_changed()
        monitors = self._monitors()
        for index, (key, win) in enumerate(self._windows.items()):
            win.move(self._resolve_rect(key, index, monitors, None))

    def _record_client_sizes(self, libs, clients) -> None:
        """Sample each client's client-area size, on the preview thread.

        Readable from the UI thread afterwards, like hotkey_status(): the
        page needs a client's shape to tell the user which size would not
        distort it, and calling GetClientRect from the bridge thread is the
        thread-affinity violation this module is organised to avoid.
        """
        sizes = {}
        rect = win32.RECT()
        for key, client in clients.items():
            if libs.user32.GetClientRect(client.hwnd, ctypes.byref(rect)):
                w, h = rect.right - rect.left, rect.bottom - rect.top
                if w > 0 and h > 0:
                    sizes[key] = (w, h)
        with self._lock:
            self._client_sizes = sizes

    def _teardown(self, libs) -> None:
        """Ordered, and all of it on this thread."""
        # First, while the windows still exist and their rects are still
        # readable. Layout writes are debounced by a second, so quitting
        # right after a drag would otherwise discard it. settings.save()
        # is lock-serialised, so writing from this thread is safe.
        if self._flush_layouts is not None:
            try:
                self._flush_layouts()
            except Exception:
                # Teardown must complete. A settings file that cannot be
                # written is not a reason to leak HWNDs and a live pump.
                logger.exception("Could not flush preview layouts on shutdown")
        # Step 1, before the window they are registered against dies. The
        # parent design's Lifecycle section lists this first and noted its
        # absence; it stops being harmless the moment anything registers.
        for ident in list(self._registered):
            libs.user32.UnregisterHotKey(self._hwnd, ident)
        self._registered.clear()
        # And the reports about them: characters()/hotkey_status() are read
        # from any thread with no liveness check of their own (get_preview_
        # hotkey_state gates on is_running instead, see ui/api.py). Leaving
        # these populated after teardown would have the bind list claim
        # every character is online and every chord registered while the
        # thread that owned them is gone and Windows holds none of them.
        # Replaced wholesale, not .clear()'d in place, for the same reason
        # _sweep() and _apply_hotkeys() never mutate them in place either:
        # a reader on another thread must never observe a half-cleared dict.
        self._clients = {}
        self._hotkey_status = {}
        self._clear_pending_activation(libs)
        # Same reasoning, for the state the render path reads: an hour-old
        # batch queued between stop() and the next enable would arm every
        # preview at once with a stale fight (raise_alert is safe from any
        # thread and keeps filling this while the pump is torn down).
        # And the two selection keys would otherwise survive a stop/start:
        # _selected_key is sticky by design now, so without this the ring
        # would come back on a character from the previous session before
        # the first sweep has confirmed it is even running.
        with self._lock:
            self._pending_alerts = []
        self._focused_key = None
        self._selected_key = None
        self._foreground = 0
        self._last_character_by_process = {}
        if self._hook:
            libs.user32.UnhookWinEvent(self._hook)  # 1. hook
            self._hook = None
        for win in list(self._windows.values()):
            win.close()  # 2. thumbnails + windows
        self._windows.clear()
        if self._hwnd:
            libs.user32.KillTimer(self._hwnd, ctypes.c_void_p(SWEEP_TIMER_ID))
            if self._alert_timer:
                libs.user32.KillTimer(self._hwnd, ctypes.c_void_p(ALERT_TIMER_ID))
                self._alert_timer = False
            libs.user32.DestroyWindow(self._hwnd)  # 3. host window
            self._hwnd = None
        libs.user32.PostQuitMessage(0)  # 4. end the pump
