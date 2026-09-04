"""Gamelog alert policy and sound dispatch.

File discovery and cursor ownership live exclusively in ``telemetry.gamelogs``.
This module is intentionally thread-free: the shared coordinator hands an
ordered event batch to ``AlertPolicy.handle`` and the policy decides whether
to filter, suppress, sound, and flash it.
"""

import logging
from pathlib import Path

from .. import paths
from . import patterns, sound

logger = logging.getLogger(__name__)


class AlertPolicy:
    """Cooldowns, NPC filtering, focus suppression, sound, and dispatch.

    Inputs are callables because settings normalization replaces nested
    dictionaries and foreground ownership changes continuously. Caching either
    would make policy decisions against stale state.
    """

    def __init__(self, config, sound, focused, on_alert):
        self._config = config
        self._sound = sound
        self._focused = focused
        self._on_alert = on_alert
        # (character, event) -> monotonic time it last dispatched.
        self._cooldowns = {}

    def _focused_character(self):
        """Read focus without allowing a secondary suppression to lose a poll."""
        try:
            return self._focused()
        except Exception:
            # Losing sound suppression is recoverable; losing every alert in
            # the coordinator's batch is not.
            logger.debug("Could not read the focused client", exc_info=True)
            return None

    def handle(self, events, now: float) -> list[tuple[str, str, str]]:
        """Filter and dispatch one ordered coordinator batch."""
        cfg = self._config() or {}
        table = cfg.get("events") or {}
        pve = bool(cfg.get("pve_filter"))
        # Absent means full volume for settings documents predating the key.
        volume = cfg.get("volume", 100)
        focused = self._focused_character()
        dispatched = []
        for event in events:
            spec = table.get(event.event)
            if not spec or not spec.get("enabled"):
                continue
            if (
                pve
                and event.event in patterns.FILTERED_EVENTS
                and patterns.is_likely_npc(event.source)
            ):
                continue
            key = (event.character, event.event)
            last = self._cooldowns.get(key)
            if last is not None and now - last < spec.get("cooldown_s", 0):
                continue
            self._cooldowns[key] = now
            sound_id = spec.get("sound") or "none"
            silent = event.character == focused
            if sound_id != "none" and not silent:
                self._sound(sound_id, volume)

            payload = dict(spec)
            persist = bool(cfg.get("persist_until_selected"))
            if silent:
                # Sound and persistence share one focus observation. Reading
                # focus again on Preview's pump could produce no sound plus a
                # persistent ring if the client changed in between.
                persist = False
            payload["persist_until_selected"] = persist
            self._on_alert(event.character, event.event, payload)
            dispatched.append((event.character, event.event, spec.get("color")))
        return dispatched


def sound_path(sound_id: str) -> Path | None:
    """Resolve a sound id in a frozen bundle or source checkout."""
    if sound_id in (None, "", "none"):
        return None
    frozen_candidate = paths.bundle_dir() / "assets" / "sounds" / f"{sound_id}.wav"
    if frozen_candidate.is_file():
        return frozen_candidate
    source_candidate = (
        Path(__file__).resolve().parent.parent / "assets" / "sounds" / f"{sound_id}.wav"
    )
    if source_candidate.is_file():
        return source_candidate
    return None


def _play_file(path) -> None:
    """Hand a WAV file to the Windows audio device asynchronously."""
    try:
        import winsound  # Deferred: CI is ubuntu-latest.
    except ImportError:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError:
        logger.exception("Could not play alert sound %s", path)


def play_sound(sound_id: str, volume: int = 100) -> None:
    """Play *sound_id* at *volume* (0-100)."""
    if volume <= 0:
        return
    path = sound_path(sound_id)
    if path is None:
        logger.warning("No sound file for id %r; alert will be silent", sound_id)
        return
    _play_file(sound.playable_path(sound_id, path, volume))
