"""Pure readers for local combat evidence, using only the caller's clock."""

from dataclasses import replace

from wingman.telemetry.model import CombatActivity, FleetRow

# Keep the established EWAR presentation order without depending on its producer.
# The reader tests pin this to the current metrics order during the transition.
_EFFECT_ORDER = ("SCRAM", "POINT", "NEUT")


def read_combat(row: FleetRow, *, now_mono: float) -> CombatActivity | None:
    """Filter effects independently; retain row deadlines and IDs even after expiry."""
    activity = row.combat
    if activity is None:
        return None
    observations = tuple(
        sorted(
            (
                effect
                for effect in activity.observations
                if effect.expires_at_mono > now_mono
            ),
            key=lambda effect: _EFFECT_ORDER.index(effect.kind),
        )
    )
    return replace(activity, observations=observations)


def combat_row_visible(row: FleetRow, *, now_mono: float) -> bool:
    """Local visibility needs unexpired activity and at least one metric direction."""
    activity = row.combat
    return (
        activity is not None
        and activity.expires_at_mono is not None
        and activity.expires_at_mono > now_mono
        and (row.dps is not None or row.incoming_dps is not None)
    )


def next_combat_transition(
    rows: tuple[FleetRow, ...], *, now_mono: float
) -> float | None:
    """Find the next evidence expiry, independently of local metric availability."""
    deadlines = []
    for row in rows:
        activity = row.combat
        if activity is None:
            continue
        if activity.expires_at_mono is not None and activity.expires_at_mono > now_mono:
            deadlines.append(activity.expires_at_mono)
        deadlines.extend(
            effect.expires_at_mono
            for effect in activity.observations
            if effect.expires_at_mono > now_mono
        )
    return min(deadlines, default=None)
