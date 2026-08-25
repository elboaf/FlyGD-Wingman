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

import ctypes
import logging
import threading

from . import cycle, discovery, geometry, gestures, layout, win32
from . import window as window_mod
from .window import PreviewWindow

logger = logging.getLogger(__name__)

SWEEP_MS = 700  # TriffView uses the same interval
SWEEP_TIMER_ID = 1
JOIN_TIMEOUT_S = 5.0
DEFAULT_SIZE = (320, 210)
# Anything beyond a handful means the pump has stopped draining, not that
# a lot of characters are in a fight at once -- raise_alert's docstring
# has the reasoning.
PENDING_ALERTS_MAX = 10


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
    assignment, duplicate rejection and gesture validation are where the
    bugs are, and none of them need a window.

    Order is deterministic so a rebind that changed nothing produces the
    same ids -- rebinding unregisters and re-registers wholesale, and an
    unstable assignment would churn registrations that did not change.
    """
    table = table if isinstance(table, dict) else {}
    characters = table.get("characters")
    entries = []
    if isinstance(characters, dict):
        for name in sorted(characters):
            entries.append((characters[name], ("focus", name)))
    entries.append((table.get("cycle_next"), ("cycle", 1)))
    entries.append((table.get("cycle_prev"), ("cycle", -1)))

    plan, claimed = [], set()
    for text, action in entries:
        parsed = gestures.parse(text)
        if parsed is None:
            continue
        canonical = gestures.display(parsed)
        if canonical in claimed:
            # Windows would refuse the second registration anyway. Dropping
            # it here keeps the reported status honest about which binding
            # actually lost.
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
        on_hotkey_status=None,
        restore_positions=None,
        show_labels=None,
        opacity=None,
        minimize_inactive_clients=None,
        never_minimize=None,
        locked=None,
    ):
        self._on_layout_changed = on_layout_changed
        # Called during teardown, before any window is destroyed. Layout
        # writes are debounced, so without this a drag in the last second
        # before quitting is simply lost.
        self._flush_layouts = flush_layouts
        # Reported outward when the discovered set changes, so the page can
        # order the bind list by who is actually online. Nothing else
        # carries that out of the subsystem: _settings_payload returns
        # persisted settings only.
        self._on_clients_changed = on_clients_changed
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
        # Both of these are character-name LISTS (preview.never_minimize,
        # preview.locked), not per-character booleans: a per-character
        # callable would need the character key at construction time, and
        # build_preview_host does not have it. _is_never_minimize/
        # _is_locked below do the per-window membership test.
        self._never_minimize = never_minimize
        self._locked = locked
        self._size = size
        self._thread = None
        self._hwnd = None  # message-only window, see _run
        self._windows = {}
        # Every DISCOVERED client, not just those with a window. _windows
        # drops any whose creation failed, and a chord aimed at a running
        # client must not depend on its preview having been created.
        self._clients = {}
        self._hook = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

        self._on_hotkey_status = on_hotkey_status
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
        # Recorded by the foreground hook (an arbitrary thread) and
        # resolved by _sweep, never the other way around -- see
        # _install_hook and _apply_selection.
        self._foreground = 0
        # The stable_key whose client currently owns the foreground
        # window, or None when it is not a client at all (a browser,
        # Discord, or Wingman itself). Read by PreviewWindow.set_selected
        # callers in _apply_selection.
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
        self._saved[stable_key] = layout.Entry(rect, locked)
        self._on_layout_changed(stable_key, rect, locked)

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

    def restyle(self) -> None:
        """Ask every open preview to re-read show_labels, opacity, locked
        and never_minimize. Safe from any thread, same shape as
        set_hotkeys() above -- except there is no payload to stash under
        the lock: the callables themselves are the live state, so this
        only has to post the signal.

        The single live-update entry point for all five settings this
        task wires (minimize_inactive_clients included): there is no
        separate "minimize changed" message, because minimize is read per
        switch (Task 7), not per window.
        """
        self._post(win32.WM_APP_RESTYLE)

    def hotkey_status(self) -> dict:
        """Outcome of the most recent registration pass.

        Readable, not only announced. Previews start before the webview
        exists (__main__.py:476-478), so a conflict found at launch has
        nowhere to be pushed and would otherwise be lost for the session.
        """
        return dict(self._hotkey_status)

    # ---- everything below runs ON the preview thread -------------------

    def _run(self) -> None:
        from ctypes import wintypes

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
        from ctypes import wintypes

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
        if msg == win32.WM_TIMER and wparam == SWEEP_TIMER_ID:
            self._sweep(libs)
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
            self._restyle()
            return 0
        if msg == win32.WM_HOTKEY:
            self._on_hotkey(libs, wparam)
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
        discovery.flush_image_cache_periodically()
        before = self.characters()
        # Wholesale, never merged. reconcile() compares stable keys only, so
        # a character that reappears on a new HWND between sweeps counts as
        # "kept" -- keeping the old record would leave it pointing at a dead
        # window. Keys survive; handles are re-read.
        self._clients = clients
        added, removed, _kept = reconcile(set(self._windows), set(clients))

        for key in removed:
            self._windows.pop(key).close()

        # Once per sweep, not once per added preview: the hardware does not
        # change between two keys of the same batch, and a failure here must
        # not log a line per client.
        monitors = self._monitors() if added else []

        for key in added:
            client = clients[key]
            entry = self._saved.get(key)
            rect = self._resolve_rect(key, len(self._windows), monitors, entry)
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
                # as. entry.locked itself is still written by
                # _layout_changed (layout.py's own callers still read it),
                # just no longer consulted here.
                locked=self._is_locked(key),
                show_labels=self._labels_shown(),
                opacity=self._current_opacity(),
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
        """Mark the preview whose client owns the foreground window.

        Nothing is selected when the foreground is not an EVE client --
        a browser, Discord, or Wingman itself. That is deliberate: a
        sticky "last client used" highlight could not be distinguished
        from an alert on that same client, and acknowledging the alert
        would then clear one the user never saw.
        """
        foreground = self._foreground or (
            libs.user32.GetForegroundWindow() if libs is not None else 0
        )
        key = next((k for k, c in self._clients.items() if c.hwnd == foreground), None)
        if key == self._selected_key:
            # Usually a genuine no-op: the common case is a foreground
            # that has not changed and a window that is already selected,
            # and PreviewWindow.set_selected is itself idempotent
            # (window.py:356), so calling it costs a dict lookup and one
            # no-op call, not a repaint. It is NOT always a no-op though:
            # a preview whose creation failed on an earlier sweep and
            # succeeded on this one, while its client stayed foreground
            # the whole time, reaches this branch with a brand-new window
            # that has never been told it is selected. Applying it here
            # is what puts the ring on it without waiting for the user to
            # tab away and back. The early return itself stays -- that is
            # the hot path this whole branch exists to keep cheap.
            win = self._windows.get(key) if key else None
            if win is not None:
                win.set_selected(True)
            return
        previous, self._selected_key = self._selected_key, key
        for candidate in (previous, key):
            win = self._windows.get(candidate) if candidate else None
            if win is not None:
                win.set_selected(candidate == key)

    def characters(self) -> list:
        """Named characters currently discovered, sorted. Safe from any
        thread: the registry is replaced wholesale, never mutated in place.

        Clients at character-select are excluded -- discovery falls their
        stable_key back to "hwnd:0x...", which names nothing a user could
        bind to.
        """
        return sorted(key for key in self._clients if not key.startswith("hwnd:"))

    def _apply_hotkeys(self, libs, table) -> None:
        """Unregister everything, then register the new table."""
        for ident in list(self._registered):
            libs.user32.UnregisterHotKey(self._hwnd, ident)
        self._registered.clear()

        status = {}
        for ident, text, action in plan_registrations(table):
            parsed = gestures.parse(text)
            ok = bool(
                libs.user32.RegisterHotKey(self._hwnd, ident, parsed.mods, parsed.vk)
            )
            status[text] = ok
            if ok:
                self._registered[ident] = action
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
        action = self._registered.get(ident)
        if action is None:
            # Not silent by accident: this is the one case Risk 4 (does
            # WM_HOTKEY even reach this window) would look like on a real
            # machine, and it must not read the same as "nothing happened
            # because nothing was pressed".
            logger.debug("WM_HOTKEY for unknown id %s ignored", ident)
            return
        kind, value = action
        if kind == "focus":
            target = value
        else:
            foreground = libs.user32.GetForegroundWindow()
            anchor = next(
                (
                    key
                    for key, client in self._clients.items()
                    if client.hwnd == foreground
                ),
                None,
            )
            # Fall back to the last chord's target when focus is not on a
            # client at all -- a browser, or Wingman itself.
            target = cycle.step(self.characters(), anchor or self._last_cycled, value)
            self._last_cycled = target
        logger.debug("Preview hotkey fired: %s -> %s", action, target)
        client = self._clients.get(target)
        if client is None:
            # bound to a character that is not running: correct no-op, but
            # logged -- otherwise this is indistinguishable from the chord
            # never reaching the process at all.
            logger.debug("Preview hotkey target %r is not running", target)
            return
        self._activate_client(libs, client)

    def _activate_client(self, libs, client) -> bool:
        """Switch the foreground to *client*. Returns whether it took.

        The single owner of the switch. Both entry points land here -- a
        hotkey, and a click on a preview (PreviewWindow classifies the
        gesture and calls this through its on_activate callback, rather
        than activating on its own as it used to). Keeping one sequence
        is what lets the host read the outgoing foreground before it
        moves; a later step in the switch added here applies to both.

        The bool is window_mod.activate's verdict, read from
        GetForegroundWindow -- callers that do more work after the switch
        need to know it actually happened.
        """
        return window_mod.activate(libs, client.hwnd)

    def _apply_alerts(self, libs, pending) -> None:
        """No-op for now -- rendering the alert on its preview window is
        wired up by a later task. Just keep the mailbox draining so
        raise_alert() never backs up unbounded.
        """
        for character, event, spec in pending:
            logger.debug(
                "Alert for %s (%s, %s) received; renderer not wired yet",
                character,
                event,
                spec,
            )

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
            entry = self._saved.get(key)
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
            geometry.default_stack(index, target, self._size), monitors
        )

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

        Not consulted anywhere in this task -- Task 7's switching logic
        is the first caller -- but stored and guarded now so
        build_preview_host wires all five settings in one pass.
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
        """
        if self._locked is None:
            return False
        try:
            return stable_key in (self._locked() or [])
        except Exception:
            logger.exception("Could not read locked; defaulting to unlocked")
            return False

    def _restyle(self) -> None:
        """Push live show_labels/opacity/locked onto every open preview.

        minimize_inactive_clients and never_minimize are read per switch
        (Task 7), not walked here -- there is no per-window state for
        them to update.
        """
        show_labels = self._labels_shown()
        opacity = self._current_opacity()
        label_h = window_mod.LABEL_H if show_labels else 0
        for key, win in self._windows.items():
            win.show_labels = show_labels
            win.opacity = opacity
            win.locked = self._is_locked(key)
            win.redraw()
            # Mirrors PreviewWindow.create/.move: opacity is a DWM
            # thumbnail property, not a chrome pixel, so it needs its own
            # push whether or not redraw() decided the bitmap changed.
            if win._thumb is not None:
                win._thumb.update(
                    geometry.thumbnail_rect(win.rect, window_mod.BORDER, label_h),
                    win.opacity,
                )

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
        # Same reasoning, for state the held render path will start
        # reading: _apply_alerts is a no-op today, but once it renders,
        # an hour-old batch queued between stop() and the next enable
        # would arm every preview at once with a stale fight (raise_alert
        # is safe from any thread and keeps filling this while the pump
        # is torn down). And _apply_selection's `if key == self.
        # _selected_key: return` would otherwise leave a freshly-created
        # window unselected forever across a stop/start, since nothing
        # else resets it.
        with self._lock:
            self._pending_alerts = []
        self._selected_key = None
        self._foreground = 0
        if self._hook:
            libs.user32.UnhookWinEvent(self._hook)  # 1. hook
            self._hook = None
        for win in list(self._windows.values()):
            win.close()  # 2. thumbnails + windows
        self._windows.clear()
        if self._hwnd:
            libs.user32.KillTimer(self._hwnd, ctypes.c_void_p(SWEEP_TIMER_ID))
            libs.user32.DestroyWindow(self._hwnd)  # 3. host window
            self._hwnd = None
        libs.user32.PostQuitMessage(0)  # 4. end the pump
