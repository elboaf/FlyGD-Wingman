"""Gamelog alert policy and sound dispatch.

File discovery and cursor ownership live exclusively in ``telemetry.gamelogs``.
This module is intentionally thread-free: the shared coordinator hands an
ordered event batch to ``AlertPolicy.handle`` and the policy decides whether
to filter, suppress, sound, and flash it.
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import paths
from ..telemetry.model import CustomMatch
from . import patterns, sound
from .custom import AlertRuntimeSnapshot, presentation_spec, rule_is_current

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PlannedAlert:
    character: str
    event: str
    spec: dict
    priority: tuple[int, int, str]
    match: CustomMatch | None = None


class AlertPolicy:
    """Cooldowns, NPC filtering, focus suppression, sound, and dispatch.

    Inputs are callables because settings normalization replaces nested
    dictionaries and foreground ownership changes continuously. Caching either
    would make policy decisions against stale state.
    """

    def __init__(
        self,
        config,
        sound,
        focused,
        on_alert,
        *,
        runtime_snapshot: Callable[[], AlertRuntimeSnapshot] | None = None,
        custom_current: Callable[[str, int, int], bool] | None = None,
    ):
        self._config = config
        self._sound = sound
        self._focused = focused
        self._on_alert = on_alert
        self._runtime_snapshot = runtime_snapshot
        self._custom_current = custom_current
        # (character, event) -> monotonic time it last dispatched.
        self._cooldowns = {}
        self._custom_cooldowns: dict[tuple[str, str, int], float] = {}

    def reset(self) -> None:
        """Start a fresh lifecycle generation with no inherited cooldowns."""
        self._cooldowns.clear()
        self._custom_cooldowns.clear()

    def forget_custom_character(self, character: str) -> None:
        """Retiring a log source must not reset another pilot or built-in state."""
        self._custom_cooldowns = {
            key: last
            for key, last in self._custom_cooldowns.items()
            if key[0] != character
        }

    def _prune_custom_cooldowns(self, snapshot: AlertRuntimeSnapshot) -> None:
        current = {(row.rule.id, row.generation) for row in snapshot.custom_rules}
        self._custom_cooldowns = {
            key: last
            for key, last in self._custom_cooldowns.items()
            if key[1:] in current
        }

    def _custom_is_current(self, match: CustomMatch) -> bool:
        if self._runtime_snapshot is None or self._custom_current is None:
            return False
        return rule_is_current(
            self._runtime_snapshot(),
            match.rule_id,
            match.generation,
            match.activation_epoch,
        ) and self._custom_current(
            match.rule_id, match.generation, match.activation_epoch
        )

    def _focused_character(self):
        """Read focus without allowing a secondary suppression to lose a poll."""
        try:
            return self._focused()
        except Exception:
            # Losing sound suppression is recoverable; losing every alert in
            # the coordinator's batch is not.
            logger.debug("Could not read the focused client", exc_info=True)
            return None

    def handle(
        self, events, now: float, *, custom_matches: tuple[CustomMatch, ...] = ()
    ) -> list[tuple[str, str, str]]:
        """Plan every eligible visual, then sound one winner across all pilots."""
        snapshot = self._runtime_snapshot() if self._runtime_snapshot else None
        if snapshot is None:
            cfg = self._config() or {}
            table = cfg.get("events") or {}
            pve = bool(cfg.get("pve_filter"))
            persist = bool(cfg.get("persist_until_selected"))
            # Absent means full volume for settings documents predating the key.
            volume = cfg.get("volume", 100)
        else:
            # One committed projection supplies both families, never a second
            # config read that could observe a different settings transaction.
            table = {}
            for builtin in snapshot.builtins:
                spec = asdict(builtin)
                table[spec.pop("event")] = spec
            pve = snapshot.pve_filter
            persist = snapshot.persist_until_selected
            volume = snapshot.volume
            self._prune_custom_cooldowns(snapshot)
        focused = self._focused_character()
        planned = []
        for order, event in enumerate(events):
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
            payload = dict(spec)
            # Sound and persistence share one focus observation. Reading focus
            # on the pump again could yield silence plus a persistent ring.
            payload["persist_until_selected"] = persist and event.character != focused
            planned.append(
                _PlannedAlert(
                    event.character,
                    event.event,
                    payload,
                    (-patterns.SEVERITY[event.event], order, ""),
                )
            )
        if snapshot is not None and self._custom_current is not None:
            planned.extend(self._plan_custom(custom_matches, snapshot, focused, now))

        dispatched = []
        audible = []
        for alert in planned:
            if alert.match is not None:
                # No effect callbacks between this admission check, cooldown
                # consumption and host delivery. The host checks again at arm.
                if not self._custom_is_current(alert.match):
                    continue
                match = alert.match
                self._custom_cooldowns[
                    (match.character, match.rule_id, match.generation)
                ] = now
            self._on_alert(alert.character, alert.event, alert.spec)
            dispatched.append((alert.character, alert.event, alert.spec.get("color")))
            if (
                volume > 0
                and alert.character != focused
                and (alert.spec.get("sound") or "none") != "none"
            ):
                audible.append(alert)
        for alert in sorted(audible, key=lambda item: item.priority):
            # An edit/close during visual delivery may retire the first winner.
            # Try the next candidate; never play a stale cue or queue losers.
            if alert.match is not None and not self._custom_is_current(alert.match):
                continue
            self._sound(alert.spec["sound"], volume)
            break
        return dispatched

    def _plan_custom(
        self,
        matches: tuple[CustomMatch, ...],
        snapshot: AlertRuntimeSnapshot,
        focused: str | None,
        now: float,
    ) -> Iterator[_PlannedAlert]:
        rows = {row.rule.id: row for row in snapshot.executable}
        for match in matches:
            row = rows.get(match.rule_id)
            if (
                row is None
                or row.generation != match.generation
                or snapshot.activation_epoch != match.activation_epoch
            ):
                continue
            last = self._custom_cooldowns.get(
                (match.character, match.rule_id, match.generation)
            )
            if last is not None and now - last < row.rule.cooldown_s:
                continue
            spec = presentation_spec(
                row.rule,
                persist=snapshot.persist_until_selected and match.character != focused,
            )
            spec.update(
                custom_rule_id=match.rule_id,
                custom_generation=match.generation,
                custom_activation_epoch=match.activation_epoch,
            )
            yield _PlannedAlert(
                match.character,
                "custom",
                spec,
                (-patterns.SEVERITY["custom"], row.position, row.rule.id),
                match,
            )


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
