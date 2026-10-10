"""The combat trigger (#320): one chord per fight, fired on the gated
combat alert.

The spec's most important behavioral sentence lives here: **one stream
per fight.** The chord is a TOGGLE, so the presses must strictly
alternate -- the first gated alert after a quiet period presses the
stream live, and when the fight has been quiet for the whole quiet
period the worker presses the same chord once more to end it (field
finding 2026-10-06: without the stop press the stream runs forever,
and the NEXT fight's start press toggles it off mid-fight). While an
episode is open, no start can fire -- the guards below make a second
press mid-fight unreachable from Wingman by construction; a hand press
mid-episode can still desync the alternation, which is the card
collision warning's territory:

- **Episode latch, per character.** Every gated combat alert refreshes
  its character's latch. The chord fires only when NO character holds
  an active latch AND no episode is open -- the first alert after a
  quiet period (fixed 600 s, rev 4 -- see the stop gate below). Ongoing
  combat keeps refreshing the latches, which is the asymmetry argument
  from the spec: too short a window risks the mid-fight toggle-off, so
  a fight's own alerts hold the process disarmed until it has truly
  gone quiet.
- **Process-wide disarm.** Any active latch blocks every character --
  the chord is one machine-wide keypress, not a per-pilot one. When A
  fires, B and C's alerts seconds later find A's latch active and stay
  pressed. Latches are maintained even while inert (no chord yet), so
  recording a keybind mid-fight does not fire into the fight already
  running; the next quiet period arms it.
- **Consent is structural.** The first gate on every decision is the
  recorded chord itself -- an empty string returns before anything can
  be spelled or sent. There is no other switch, by design (#319).
- **Mirror gate.** The chord fires only while the stream mirror is
  actually running: without the registered game window there is nothing
  for Discord to pin, and a chord pressed anyway would toggle off a
  stream the user started by hand. The spec's failure-modes table calls
  the feature inert without a mirror window; this is that line.
- **No foreground gate (decided, 2026-10-06).** The original
  confirmation gate -- no chord while Discord is foreground, failing
  closed on an unprovable read -- is gone at the user's call: the
  chord IS their Discord bind, so pressing it with Discord focused is
  the user pressing their own keybind. The gate never fired a refusal
  that helped, either: its read was doubly broken (it looked
  QueryFullProcessImageNameW up on user32 when it lives in kernel32 --
  the AttributeError was swallowed into None -- and it called
  GetForegroundWindow unpinned, truncating the 64-bit HWND to a
  32-bit int, the mangling evewindows._enumerate documents), so live
  proof 2026-10-06 was 30/30 reads None and every fire refused as "an
  unprovable window". Any future foreground read re-pins every
  signature and imports from the right DLL.

The send is an injected seam executed on this controller's own worker
thread -- never the telemetry dispatcher's, never the policy's. The
policy funnel (``AlertPolicy.handle``) hands over only the characters
whose combat alert actually dispatched (enabled, PvE-filtered,
cooldown-elapsed); handover is a queue put, so the dispatcher never
waits on a spell, a focus read or a SendInput. The same worker owns
the stop: with an episode open it idles on a timed wake (the queue
get's timeout) until every latch has expired, then gates the stop
press on a gateway probe (#335, rev 4) before pressing.

Pure pieces (``spell_chord``, ``ChordPlan``, ``chord_choreography``) and
the controller are Linux-unit-testable with injected ports, like every
other subsystem; the real Win32 seams are lazy-ctypes functions touched
only in production. Imports nothing from ``ui`` and never holds the
window.
"""

import ctypes
import logging
import queue
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from typing import NamedTuple

from .. import bookmarks
from ..preview import gestures

logger = logging.getLogger(__name__)

# Press order for synthesized modifiers -- the house display order
# (bookmarks._MODIFIERS), so a spelled chord reads the same everywhere.
_MODIFIER_VKS = (
    ("ctrl", 0x11),  # VK_CONTROL
    ("alt", 0x12),  # VK_MENU
    ("shift", 0x10),  # VK_SHIFT
    ("meta", 0x5B),  # VK_LWIN
)

_VK_NUMPAD_ENTER = 0x0D

# The seam presses the LEFT variant of every modifier. A keyboard never
# produces the generic VK_CONTROL -- it produces VK_LCONTROL, and the
# system derives the generic state from it -- so the generic VK is an
# observable difference between Wingman's press and the user's hand, and
# the 2026-10-07 field report is apps acting on the bare base key
# (ctrl+alt+f9 opened a focused EVE client's map). VK_LWIN is already the
# left key.
_LEFT_MOD_VKS = {
    0x11: 0xA2,  # VK_CONTROL -> VK_LCONTROL
    0x12: 0xA4,  # VK_MENU -> VK_LMENU
    0x10: 0xA0,  # VK_SHIFT -> VK_LSHIFT
    0x5B: 0x5B,  # VK_LWIN
}

# The press is paced like a hand, not one SendInput batch: a batch lands
# every event inside one scheduler tick, so the modifiers are down and up
# before a poller's next frame or a dispatch-time async key state read --
# the other half of the same field report. These gaps hold the chord for
# ~100ms around the tap, which is what every observer sees a real press
# do; ~150ms on the daemon worker thread is nothing.
_STEP_GAP_S = 0.02  # between modifier downs (and before the first)
_CHORD_GAP_S = 0.04  # last modifier down -> base key down
_TAP_HOLD_S = 0.03  # base key down -> base key up
_RELEASE_GAP_S = 0.01  # base up -> first modifier up, and between ups


# The Win32 INPUT family at its true shape. The union's largest member is
# MOUSEINPUT, and SendInput validates cbSize against the REAL INPUT: a
# keyboard-only union computes 32 bytes on x64, and SendInput rejects every
# batch with a silent 0 -- which is how every stream chord through
# #320's field tests logged "fired" while pressing nothing (2026-10-06).
# Module scope so the size pin can be asserted on Linux CI.
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class ChordPlan(NamedTuple):
    """A chord spelled into concrete keys: modifier VKs in press order,
    then the one base key. ``extended`` marks the numpad's Enter, whose
    synthetic event must carry KEYEVENTF_EXTENDEDKEY to be the key the
    user bound."""

    mods: tuple[int, ...]
    vk: int
    extended: bool


def spell_chord(text, *, char_vk=None):
    """Spell a stored AHK-style chord into a ChordPlan, or None.

    None means "unspellable": nothing anywhere may fire on a chord the
    send cannot reproduce, and the armed row says so (chord_sendable).
    The stored notation is the single source of truth (#319 wrote it,
    this reads it back) -- the modifier symbols parse via the same table
    parse_ahk wrote them from.

    A one-character base is a PRODUCED character (ADR 0002 -- capture
    stores what the layout typed): a stored "d" on a Dvorak box means the
    physical key this layout types "d" with, not the key a static US
    table would guess. It resolves through the injected ``char_vk``
    first -- production passes keylayout.char_vk, which asks the
    foreground thread's own layout. Named position tokens ("Numpad3",
    "F5", "PgUp") have one meaning everywhere and resolve through
    gestures' VK table -- the one table the house keeps, not a second
    copy that can drift. A produced character the resolver cannot place
    falls back to the table too: for ASCII that is the same key, and
    refusing a chord a US-layout box bound would disarm a working setup
    for no field-visible reason.
    """
    parsed = bookmarks.parse_ahk(text if isinstance(text, str) else "")
    if parsed["error"] or not parsed["ahk"]:
        return None
    ahk = parsed["ahk"]
    parts = dict.fromkeys(("ctrl", "alt", "shift", "meta"), False)
    index = 0
    while index < len(ahk) and ahk[index] in bookmarks._SYMBOL_TO_KEY:
        parts[bookmarks._SYMBOL_TO_KEY[ahk[index]]] = True
        index += 1
    base = ahk[index:]
    if not base:  # parse_ahk already refuses modifier-only input; be total.
        return None
    if base == "NumpadEnter":
        # gestures' table cannot carry it: RegisterHotKey has no extended
        # distinction, so the previews never needed one. SendInput does.
        return ChordPlan(_mods(parts, False), _VK_NUMPAD_ENTER, True)
    vk = None
    needs_shift = False
    if len(base) == 1 and char_vk is not None:
        resolved = char_vk(base)
        if resolved is not None:
            vk, needs_shift = resolved
    if vk is None:
        vk = gestures.vk_for(base)
    if vk is None:
        return None
    return ChordPlan(_mods(parts, needs_shift), vk, False)


def _mods(parts: dict, needs_shift: bool) -> tuple[int, ...]:
    """Modifier VKs in press order; a produced character that implies
    Shift (an "@" the layout types with Shift+2) unions it in -- pressing
    it unshifted would type the wrong key."""
    return tuple(
        vk
        for key, vk in _MODIFIER_VKS
        if parts[key] or (key == "shift" and needs_shift)
    )


def chord_choreography(plan: ChordPlan) -> tuple[tuple[int, bool, bool, float], ...]:
    """The press a hand makes, as ``(vk, up, extended, sleep_before_s)``
    in send order -- pure, so the shape is pinned on Linux and the seam
    only flushes it. Modifiers down as left keys, base down, base up,
    modifiers up in reverse, each step separated by the pacing gaps; the
    extended flag rides the base key alone (an extended ctrl-down is
    right ctrl -- on a NumpadEnter chord it would press modifiers
    Discord never bound).
    """
    mods = tuple(_LEFT_MOD_VKS.get(vk, vk) for vk in plan.mods)
    steps = [(vk, False, False, _STEP_GAP_S) for vk in mods]
    steps.append((plan.vk, False, plan.extended, _CHORD_GAP_S))
    steps.append((plan.vk, True, plan.extended, _TAP_HOLD_S))
    steps.extend((vk, True, False, _RELEASE_GAP_S) for vk in reversed(mods))
    return tuple(steps)


def send_keystrokes(plan: ChordPlan) -> None:
    """The real seam: flush ``chord_choreography`` one SendInput per
    event, so the press reads as an ordinary keystroke at every point a
    listener can read -- Discord's global keybind included. Returns
    silently off-Windows and on any Win32 failure: the worker must
    survive the seam, and the armed row's honesty comes from the fire
    decision, not from here. A failure mid-press first releases whatever
    is still held -- a chord that dies between ctrl-down and ctrl-up
    must not leave a modifier latched on the user's keyboard long after
    the stream it started is over.
    """
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError, ImportError):
        return

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def key_event(vk: int, up: bool, extended: bool) -> _INPUT:
        flags = KEYEVENTF_KEYUP if up else 0
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        event = _INPUT()
        event.type = INPUT_KEYBOARD
        event.ki = _KEYBDINPUT(
            vk,
            user32.MapVirtualKeyW(vk, 0),  # MAPVK_VK_TO_VSC
            flags,
            0,
            None,
        )
        return event

    # Pin signatures so the count pointer marshals correctly on x64.
    user32.SendInput.argtypes = (
        ctypes.c_uint,
        ctypes.POINTER(_INPUT),
        ctypes.c_int,
    )
    user32.SendInput.restype = ctypes.c_uint

    steps = chord_choreography(plan)
    # Held so far, press order: the choreography releases in exact
    # reverse, so a pop per keyup tracks it, and the failure path unwinds
    # whatever a broken press left down.
    held: list[tuple[int, bool]] = []
    delivered = 0
    for vk, up, extended, delay in steps:
        if delay:
            time.sleep(delay)
        one = (_INPUT * 1)(key_event(vk, up, extended))
        if user32.SendInput(1, one, ctypes.sizeof(_INPUT)) != 1:
            for held_vk, held_extended in reversed(held):
                release = (_INPUT * 1)(key_event(held_vk, True, held_extended))
                user32.SendInput(1, release, ctypes.sizeof(_INPUT))
            break
        delivered += 1
        if up:
            held.pop()
        else:
            held.append((vk, extended))
    if delivered != len(steps):
        # WARNING, not debug: a rejected event is the exact failure that
        # made the controller log "fired" above this line while nothing
        # was pressed (the wrong-size INPUT incident, 2026-10-06).
        logger.warning(
            "SendInput delivered %d of %d events for the stream chord",
            delivered,
            len(steps),
        )


@dataclass(frozen=True)
class StreamCouplingPorts:
    """Injected seams. ``coupling`` re-reads the live committed settings
    on every decision, every other callable is a platform seam the tests
    replace. ``probe_live`` is the gateway probe seam (#335): a sync
    call returning True (live) / False (clean not-live snapshot), raised
    ProbeError on no answer -- it runs on this controller's worker only.
    ``budget_spend`` reserves one probe from the daily allowance and
    returns False when the day is dry (degrade to open-loop).
    ``budget_status`` reports the day's standing for the card
    (``{"budget_used": int, "budget_limit": int}``).
    ``publish_probe_status`` pushes the last probe's answer for the card
    (#337): ``{"live": bool|None, "display": "HH:MM"|None, "degraded":
    str|None, "budget_used": int, "budget_limit": int}``.
    """

    coupling: Callable[[], dict]
    mirror_running: Callable[[], bool]
    char_vk: Callable[[str], tuple[int, int] | None] | None
    send: Callable[[ChordPlan], None]
    publish_state: Callable[[dict], None]
    publish_fired: Callable[[dict], None]
    probe_live: Callable[[], bool] | None = None
    budget_spend: Callable[[], bool] | None = None
    budget_status: Callable[[], dict] | None = None
    publish_probe_status: Callable[[dict], None] | None = None


class StreamCouplingController:
    """Owns the latches and the send; one worker thread owns the decisions.

    Construction starts the worker; ``close`` stops it exactly once (a
    timed-out thread stays tracked -- never joined twice, never
    replaced). The lock guards only latch/last-fired state; joins and
    publishes happen outside it.
    """

    # Rev 4 (#335): fixed 600. The range 60-900 and the 300 default are
    # retired -- the stop is snapshot-gated, so running long is a
    # one-sided error (the probe ends a stream later, never earlier).
    _QUIET_DEFAULT = 600
    _QUIET_MIN = 600
    _QUIET_MAX = 600

    def __init__(
        self,
        ports: StreamCouplingPorts,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        spawn=threading.Thread,
    ):
        self._ports = ports
        self._clock = clock
        self._wall = wall
        self._lock = threading.Lock()
        # character -> monotonic time of its last gated combat alert.
        self._latches: dict[str, float] = {}
        # The character whose fight Wingman pressed live, or None. The
        # toggle's other half: while an episode is open no start may
        # fire, and the worker's timed wake stops the stream once every
        # latch has expired.
        self._episode = None
        # (character or None, wall time, action) of the last press, for
        # the row -- action is "start" or "stop".
        self._last_fired: tuple[str | None, float, str] | None = None
        # (chord, sendable) cache: spellability consults the layout and
        # must not become a per-tick syscall.
        self._spellable: tuple[str, bool] | None = None
        # The one flag that makes stops safe (#335): set ONLY when a
        # fresh snapshot confirms the stream live while a Wingman-
        # originated episode is open. A manually started stream never
        # sets it; a manual stop clears it at the next probe.
        self._wingman_live = False
        # The last probe's answer for the card (#337): (live, wall time,
        # degraded-code-or-None). None live = no answer yet.
        self._probe_record: tuple[bool | None, float, str | None] = (None, 0.0, None)
        self._closed = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._thread = spawn(target=self._run, name="stream-coupling", daemon=True)
        self._thread.start()

    def observe_combat(self, characters) -> None:
        """Hand over the characters whose gated combat alert dispatched.

        Total and cheap: it runs on the telemetry dispatcher thread,
        which may never wait on a spell, a focus read or a send.
        """
        if self._closed.is_set():
            return
        names = tuple(dict.fromkeys(c for c in characters if isinstance(c, str) and c))
        if names:
            self._queue.put(names)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._queue.put(None)
        self._thread.join(timeout=2.0)

    def state_payload(self) -> dict:
        """The armed row: state, chord, latched characters, last fire.

        States, in the order the decision gates bind: ``inert`` (no
        consent chord), ``standby`` (consent present but the mirror is
        not running -- nothing to pin, and saying held would imply the
        chord fires once the hold ends), ``held`` (an episode latch is
        active), ``armed`` (the next gated combat alert fires). The row
        says armed, never live: nothing here knows whether Discord is
        actually streaming, and it must never claim to.
        """
        coupling = self._read_coupling()
        chord = coupling["chord"]
        quiet = coupling["quiet_s"]
        now = self._clock()
        with self._lock:
            active = {
                character: stamped
                for character, stamped in self._latches.items()
                if now - stamped < quiet
            }
            last = self._last_fired
        remaining = max(
            (quiet - (now - stamped) for stamped in active.values()),
            default=0.0,
        )
        if not chord:
            state = "inert"
        elif not self._ports.mirror_running():
            state = "standby"
        elif active:
            state = "held"
        else:
            state = "armed"
        display = ""
        if chord:
            parsed = bookmarks.parse_ahk(chord)
            if not parsed["error"]:
                display = parsed["display"]
        return {
            "state": state,
            "chord_display": display,
            "chord_sendable": self._chord_sendable(chord),
            "quiet_s": quiet,
            "latched": sorted(active),
            "latched_remaining_s": round(remaining),
            "last_fired_character": last[0] if last else None,
            "last_fired_display": self._format_wall(last[1]) if last else None,
            "last_fired_action": last[2] if last else None,
            **self.probe_status_payload(),
        }

    def probe_status_payload(self) -> dict:
        """The card's probe fields (#337, carried by the state row): the
        last probe's answer and when, the degrade notice when open-loop,
        and the day's budget standing. ``live`` None = no answer yet."""
        with self._lock:
            live, wall_time, degraded = self._probe_record
            wingman_live = self._wingman_live
        payload = {
            "live": live,
            "live_display": self._format_wall(wall_time) if live is not None else None,
            "degraded": degraded,
            "wingman_live": wingman_live,
        }
        budget = self._ports.budget_status
        if budget is not None:
            payload.update(budget())
        return payload

    def _run(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=self._wake_delay())
            except queue.Empty:
                try:
                    self._maybe_stop()
                except Exception:
                    # One bad stop check must not kill the worker.
                    logger.exception("Stream coupling stop check failed")
                continue
            if item is None:
                return
            try:
                self._process(item)
            except Exception:
                # One bad decision must not kill the worker.
                logger.exception("Stream coupling worker failed")

    def _process(self, characters: tuple[str, ...]) -> None:
        coupling = self._read_coupling()
        chord = coupling["chord"]
        quiet = coupling["quiet_s"]
        now = self._clock()
        with self._lock:
            # Armed means every latch was ALREADY expired when this alert
            # arrived AND Wingman holds no open episode: a late-arriving
            # alert inside the window before the stop press must refresh
            # the running fight, never toggle the live stream off. The
            # refresh below then starts (or extends) this fight's episode.
            armed = self._episode is None and all(
                now - stamped >= quiet for stamped in self._latches.values()
            )
            for character in characters:
                self._latches[character] = now
        fired = None
        if chord and armed:
            fired = self._try_fire(chord, characters)
        if fired is not None:
            with self._lock:
                # The toggle just OPENED the stream; the stop press at
                # quiet expiry is what closes it. That is the whole
                # alternation: open here, closed in _maybe_stop. The
                # confirmation flag starts false every episode and is
                # consumed by whichever probe confirms or stop press
                # ends it (#335 pins the lifecycle).
                self._wingman_live = False
                self._episode = fired[0]
        self._ports.publish_state(self.state_payload())
        if fired is not None:
            character, wall_time = fired
            self._ports.publish_fired(
                {
                    "character": character,
                    "display": self._format_wall(wall_time),
                    "action": "start",
                }
            )

    def _try_fire(self, chord: str, characters: tuple[str, ...]):
        """Every gate passed the consent check; run the mirror and
        spelling gates. Returns (character, wall time) when the chord
        went out, None when a gate refused."""
        if not self._ports.mirror_running():
            # The spec's failure-modes line: the feature stays inert
            # without a mirror window to pin -- and a chord pressed with
            # the mirror down could toggle off a stream the user started
            # by hand. Standing by is the safe posture.
            logger.info("Combat auto-start standing by: the mirror is not running")
            return None
        plan = spell_chord(chord, char_vk=self._ports.char_vk)
        if plan is None:
            logger.info("The recorded stream chord cannot be spelled for SendInput")
            return None
        try:
            self._ports.send(plan)
        except Exception:
            # A failed seam must not kill the worker.
            logger.exception("Could not send the stream chord")
            return None
        character = characters[0]
        wall_time = self._wall()
        with self._lock:
            self._last_fired = (character, wall_time, "start")
        logger.info("Stream chord fired for %s", character)
        return character, wall_time

    def _wake_delay(self):
        """How long the worker may idle before re-checking an open
        episode's stop deadline, or None to block until the next
        combat alert. Recomputed after every wake, so a fight that
        resumes pushes the stop out without anyone re-programming it."""
        quiet = self._read_coupling()["quiet_s"]
        now = self._clock()
        with self._lock:
            if self._episode is None or not self._latches:
                return None
            deadline = max(self._latches.values()) + quiet
        # The 1s floor: an expired deadline is due NOW, but a stop that
        # keeps failing must retry on a cadence, not hot-spin the worker.
        return max(1.0, deadline - now)

    def _maybe_stop(self) -> None:
        """The toggle's other half, rev 4 (#335): the stop decision is
        PROBE-GATED whenever the probe can answer. At quiet expiry with
        the episode open, spend one budgeted probe:

        - still live -> send the stop chord. The episode is
          Wingman-originated by construction (the alternation guard:
          only Wingman's start press opens one), and the fresh snapshot
          says the stream it opened is still up; this is the
          ``wingman_live``-confirmed press the invariant asks for.
        - already off (the user stopped by hand) -> clear the latch,
          send NOTHING, re-arm. No confirm probe: a lost chord
          self-corrects here -- one dead episode max, never a zombie.
        - probe unavailable (no token/ids, gateway down) or the budget
          is dry -> degrade to OPEN-LOOP: fire today's chord
          unconditionally, exactly the shipped rev-3 behaviour. The
          degraded loop must never become a missed stop -- a zombie
          stream is the one outcome the ticket forbids -- and a manual
          toggle mid-episode is the card collision warning's territory,
          unchanged from rev 3. The card says why (#337).
        """
        with self._lock:
            episode = self._episode
        if episode is None:
            return
        coupling = self._read_coupling()
        chord = coupling["chord"]
        quiet = coupling["quiet_s"]
        now = self._clock()
        with self._lock:
            if not all(now - stamped >= quiet for stamped in self._latches.values()):
                # The fight resumed between the wake and this check; the
                # latches are refreshed and the next wake re-arms itself.
                return

        # The gate: one budgeted probe before anything else.
        verdict = self._run_probe()
        if verdict is True:
            with self._lock:
                # Confirmed Wingman-originated and still live: this is
                # the one state in which the stop chord may fire.
                self._wingman_live = True
        elif verdict is False:
            with self._lock:
                # Already off -- the user stopped it by hand, or the
                # start chord never landed. Clear the latch, send
                # nothing, re-arm. A lost chord self-corrects here.
                self._wingman_live = False
                self._episode = None
            logger.info(
                "Combat auto-stream episode closed by the probe: the stream is already off"
            )
            self._ports.publish_state(self.state_payload())
            return
        # verdict None: degraded -- open-loop below. The episode is
        # Wingman-originated by construction (the alternation guard:
        # only Wingman's start press opens one), so today's chord fires
        # unconditionally -- "degrade to open-loop", never a zombie
        # stream. A manual stream the user toggled mid-episode is the
        # card collision warning's territory, not a new gate here.

        with self._lock:
            self._episode = None

        def abandon(reason: str) -> None:
            logger.info(
                "Combat auto-stream episode closed without a stop press: %s", reason
            )
            self._ports.publish_state(self.state_payload())

        if not chord:
            # Consent was withdrawn mid-episode: the empty field is the
            # off switch, and it switches off PRESSES -- including this
            # one. Whatever the stream is doing now is the user's to end.
            abandon("the chord was cleared")
            return
        if not self._ports.mirror_running():
            # Discord pins the mirror window; a dead window has already
            # ended the share on its own, and a press now could only
            # toggle off a stream the user started by hand afterwards.
            abandon("the mirror is not running")
            return
        plan = spell_chord(chord, char_vk=self._ports.char_vk)
        if plan is None:
            abandon("the chord cannot be spelled any more")
            return
        try:
            self._ports.send(plan)
        except Exception:
            # A failed seam must not kill the worker; the episode is
            # already closed, so a real fight's next press starts fresh.
            logger.exception("Could not send the stream stop chord")
            abandon("the stop press failed")
            return
        wall_time = self._wall()
        with self._lock:
            self._wingman_live = False
            self._last_fired = (None, wall_time, "stop")
        logger.info("Stream chord fired to end the stream (fight quiet for %ss)", quiet)
        self._ports.publish_state(self.state_payload())
        self._ports.publish_fired(
            {
                "character": None,
                "display": self._format_wall(wall_time),
                "action": "stop",
            }
        )

    def _run_probe(self) -> bool | None:
        """One budgeted gateway probe at a decision gate. True/False is
        the snapshot's answer; None is no answer -- token missing, the
        day's budget dry, or the gateway refused. The budget counter and
        the degrade notice ride to the card through probe_status (#337).
        """
        probe = self._ports.probe_live
        spend = self._ports.budget_spend
        if probe is None or spend is None:
            self._record_probe(None, "not configured")
            return None
        if not spend():
            self._record_probe(None, "budget dry -- open-loop")
            return None
        try:
            answer = probe()
        except Exception:
            # A failed probe must not kill the worker; degrade.
            logger.exception("The stream state probe failed")
            self._record_probe(None, "probe failed -- open-loop")
            return None
        self._record_probe(answer, None)
        return answer

    def _record_probe(self, live: bool | None, degraded: str | None) -> None:
        with self._lock:
            self._probe_record = (live, self._wall(), degraded)
        self._publish_probe_status()

    def _publish_probe_status(self) -> None:
        if self._ports.publish_probe_status is None:
            return
        # A dedicated push, not piggybacked on the state row: the card's
        # live badge updates the moment a probe answers, even mid-episode
        # when the state row would dedup to nothing new.
        self._ports.publish_probe_status(self.probe_status_payload())

    def _read_coupling(self) -> dict:
        """The live committed coupling, defended to exactly two keys."""
        try:
            raw = self._ports.coupling() or {}
        except Exception:
            # A failed read stalls the trigger, never the worker.
            logger.exception("Could not read the stream coupling settings")
            return {"chord": "", "quiet_s": self._QUIET_DEFAULT}
        chord = raw.get("chord")
        quiet = raw.get("quiet_s")
        if not isinstance(quiet, int) or isinstance(quiet, bool):
            quiet = self._QUIET_DEFAULT
        return {
            "chord": chord if isinstance(chord, str) else "",
            "quiet_s": max(self._QUIET_MIN, min(self._QUIET_MAX, quiet)),
        }

    def _chord_sendable(self, chord: str) -> bool:
        if not chord:
            return False
        with self._lock:
            if self._spellable is not None and self._spellable[0] == chord:
                return self._spellable[1]
        sendable = spell_chord(chord, char_vk=self._ports.char_vk) is not None
        with self._lock:
            self._spellable = (chord, sendable)
        return sendable

    def _format_wall(self, wall_time: float) -> str:
        return time.strftime("%H:%M", time.localtime(wall_time))
