"""The combat trigger (#320): one chord per fight, fired on the gated
combat alert.

The spec's most important behavioral sentence lives here: **one stream
per fight, Wingman presses once.** A second chord while the fleet is
live is the toggle that kills their feed, so the guards make a second
press unreachable from Wingman:

- **Episode latch, per character.** Every gated combat alert refreshes
  its character's latch. The chord fires only when NO character holds
  an active latch -- the first alert after a quiet period (``quiet_s``,
  60-900, default 300, read live). Ongoing combat keeps refreshing the
  latches, which is the asymmetry argument from the spec: too short a
  window risks the mid-fight toggle-off, so a fight's own alerts hold
  the process disarmed until it has truly gone quiet.
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
waits on a spell, a focus read or a SendInput.

Pure pieces (``spell_chord``, ``ChordPlan``) and the controller are
Linux-unit-testable with injected ports, like every other subsystem;
the real Win32 seams are lazy-ctypes functions touched only in
production. Imports nothing from ``ui`` and never holds the window.
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


def send_keystrokes(plan: ChordPlan) -> None:
    """The real seam: one SendInput of the chord. Pure ctypes, house
    Win32 style, no new dependency. Modifiers down, base down, base up,
    modifiers up -- the same shape a real keystroke makes, so Discord's
    global keybind sees an ordinary press. Returns silently off-Windows
    and on any Win32 failure: the worker must survive the seam, and the
    armed row's honesty comes from the fire decision, not from here.
    """
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError, ImportError):
        return

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def key_event(vk: int, up: bool) -> _INPUT:
        flags = 0
        if up:
            flags |= KEYEVENTF_KEYUP
        if plan.extended:
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

    sequence = [key_event(vk, False) for vk in plan.mods]
    sequence.append(key_event(plan.vk, False))
    sequence.append(key_event(plan.vk, True))
    sequence.extend(key_event(vk, True) for vk in reversed(plan.mods))
    array = (_INPUT * len(sequence))(*sequence)
    # Pin signatures so the count pointer marshals correctly on x64.
    user32.SendInput.argtypes = (
        ctypes.c_uint,
        ctypes.POINTER(_INPUT),
        ctypes.c_int,
    )
    user32.SendInput.restype = ctypes.c_uint
    sent = user32.SendInput(len(array), array, ctypes.sizeof(_INPUT))
    if sent != len(array):
        # WARNING, not debug: a rejected batch is the exact failure that
        # made the controller log "fired" above this line while nothing
        # was pressed (the wrong-size INPUT incident, 2026-10-06).
        logger.warning(
            "SendInput delivered %d of %d events for the stream chord",
            sent,
            len(array),
        )


@dataclass(frozen=True)
class StreamCouplingPorts:
    """Injected seams. ``coupling`` re-reads the live committed settings
    on every decision -- the quiet period changes without a restart --
    and every other callable is a platform seam the tests replace."""

    coupling: Callable[[], dict]
    mirror_running: Callable[[], bool]
    char_vk: Callable[[str], tuple[int, int] | None] | None
    send: Callable[[ChordPlan], None]
    publish_state: Callable[[dict], None]
    publish_fired: Callable[[dict], None]


class StreamCouplingController:
    """Owns the latches and the send; one worker thread owns the decisions.

    Construction starts the worker; ``close`` stops it exactly once (a
    timed-out thread stays tracked -- never joined twice, never
    replaced). The lock guards only latch/last-fired state; joins and
    publishes happen outside it.
    """

    _QUIET_DEFAULT = 300
    _QUIET_MIN = 60
    _QUIET_MAX = 900

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
        # (character, wall time) of the last fired chord, for the row.
        self._last_fired: tuple[str, float] | None = None
        # (chord, sendable) cache: spellability consults the layout and
        # must not become a per-tick syscall.
        self._spellable: tuple[str, bool] | None = None
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
        }

    def _run(self) -> None:
        while True:
            item = self._queue.get()
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
            # arrived; the refresh below then starts this fight's episode.
            armed = all(now - stamped >= quiet for stamped in self._latches.values())
            for character in characters:
                self._latches[character] = now
        fired = None
        if chord and armed:
            fired = self._try_fire(chord, characters)
        self._ports.publish_state(self.state_payload())
        if fired is not None:
            character, wall_time = fired
            self._ports.publish_fired(
                {
                    "character": character,
                    "display": self._format_wall(wall_time),
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
            self._last_fired = (character, wall_time)
        logger.info("Stream chord fired for %s", character)
        return character, wall_time

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
