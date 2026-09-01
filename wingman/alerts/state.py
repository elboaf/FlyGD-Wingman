"""What an alert does over time.

Pure: `now` is always passed in, never read. That is what lets the whole
state machine be covered on ubuntu-latest, and it is the same trade
preview/geometry.py makes for placement.

One predicate -- is_active -- backs the query, the expiry sweep and the
severity guard. Three call sites disagreeing about whether an alert is
still live is exactly how a persistent alert gets silently downgraded by
a lower-severity event.
"""

import math
from typing import NamedTuple

from .patterns import SEVERITY

# Six steps is past what the eye resolves in a 1200ms pulse, and each one
# costs a DIB while an alert is armed.
FRAME_ALPHAS = (110, 139, 168, 197, 226, 255)

# How long ONE flash lasts, per speed preset. The keys are the values
# settings stores and the Alerts card offers, so a preset added here is
# added everywhere -- test_page_conventions.py checks the dropdown against
# this table rather than against a hand-kept copy of it.
#
# Normal is 400ms because 400 x 3 is 1200ms, the duration every install
# has had since alerts shipped: the default arrangement has to reproduce
# exactly what it replaced, or this becomes a silent retiming of a signal
# people already read at a glance.
FLASH_MS = {"slow": 600, "normal": 400, "fast": 250}
DEFAULT_FLASH_RATE = "normal"


def duration_for(rate, pulses) -> int:
    """How long an alert of *pulses* flashes at *rate* runs, in ms.

    The one place the two stored knobs become a duration. An unknown rate
    falls back rather than raising: this is reached from arm_alert on the
    preview thread, where an exception takes down the pump that also
    serves previews and hotkeys, and a hand-edited settings.json is a
    legitimate way to get here.
    """
    per_flash = FLASH_MS.get(rate, FLASH_MS[DEFAULT_FLASH_RATE])
    try:
        count = int(pulses)
    except (TypeError, ValueError):
        count = 1
    # Never zero: progress() divides by the duration, so a zero-length
    # alert would arm, never draw, and leave nothing to explain why.
    return per_flash * max(1, count)


class Alert(NamedTuple):
    event: str
    color: str
    started: float
    # None means persistent: it clears on acknowledgement, never on time.
    expires: float | None
    duration_ms: int
    pulses: int


def is_active(alert, now: float) -> bool:
    return alert is not None and (alert.expires is None or alert.expires > now)


def arm(
    current,
    event: str,
    color: str,
    now: float,
    *,
    duration_ms: int,
    pulses: int,
    persist: bool,
    target_is_selected: bool,
) -> Alert:
    """Fold an incoming event into whatever is already showing."""
    expires = None if (persist and not target_is_selected) else now + duration_ms / 1000
    incoming = Alert(event, color, now, expires, duration_ms, pulses)
    if not is_active(current, now):
        return incoming

    rank, current_rank = SEVERITY[event], SEVERITY[current.event]
    if rank > current_rank:
        return incoming
    if rank == current_rank:
        # Restart the pulse and re-stamp the expiry. Colour comes from the
        # incoming event so a live colour change in settings takes effect.
        return current._replace(started=now, expires=expires, color=color)

    # Lower severity: extend only, never repaint.
    if current.expires is None or expires is None:
        # Mixed persistent/timed cannot arise for one preview in one tick --
        # persist and target_is_selected are the same for both -- so the
        # safe reading is "leave the higher-severity alert exactly as is".
        return current
    return current._replace(expires=max(current.expires, expires))


def clear_expired(alert, now: float):
    return alert if is_active(alert, now) else None


def acknowledge(alert):
    """Clear a persistent alert. A timed one is left to expire.

    Acknowledging a timed alert would make selecting a client cut short a
    ring that had only just appeared.
    """
    if alert is not None and alert.expires is None:
        return None
    return alert


def progress(alert, now: float) -> float:
    if alert.duration_ms <= 0:
        return 1.0
    p = (now - alert.started) * 1000.0 / alert.duration_ms
    if alert.expires is None:
        # Free-running, so a persistent alert keeps pulsing at the same
        # cadence instead of finishing and holding.
        return p % 1.0
    return min(1.0, max(0.0, p))


def alpha_for(progress: float, pulses: int) -> int:
    wave = (math.sin(progress * pulses * 2 * math.pi) + 1) / 2
    # 110, not 0: a pulse that dims to fully transparent mid-cycle reads
    # as the alert having ended, so the floor is baked into the constant
    # term rather than clamped after the fact -- 110 + wave * 145 already
    # ranges over [110, 255] for wave in [0, 1], so a max(90, ...) here
    # could never bind and would only mislead about which term is the
    # floor.
    return min(255, int(110 + wave * 145))


def frame_index(alert, now: float) -> int:
    alpha = alpha_for(progress(alert, now), alert.pulses)
    return min(range(len(FRAME_ALPHAS)), key=lambda i: abs(FRAME_ALPHAS[i] - alpha))
