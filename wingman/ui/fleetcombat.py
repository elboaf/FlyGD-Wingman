"""Combat presentation only; these readers never alter collection or evidence."""

from ..telemetry.combat import combat_row_visible, read_combat


def labels(effects):
    effects = tuple(effects)
    kinds = list(
        dict.fromkeys(
            "SCRAM/POINT" if kind in ("SCRAM", "POINT") else kind for kind, _ in effects
        )
    )
    names = list(
        dict.fromkeys(f"{kind}: {name}" for kind, name in effects if name is not None)
    )
    return kinds, {"ewar_sources": names} if names else {}


def local_effects(row, now):
    activity = read_combat(row, now_mono=now)
    if activity is None:
        return list(row.ewar), {}
    return labels((effect.kind, effect.name) for effect in activity.observations)


def signature(rows, now, hide_inactive):
    return tuple(
        (
            row.character,
            combat_row_visible(row, now_mono=now) if hide_inactive else None,
            tuple(
                (effect.kind, effect.name)
                for effect in read_combat(row, now_mono=now).observations
            ),
        )
        for row in rows
        if row.combat is not None
    )
