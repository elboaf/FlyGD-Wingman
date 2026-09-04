"""Pure arithmetic training time calculator.

Calculates exact remaining seconds to train skills using deterministic EVE
thresholds and Fraction arithmetic, with single final ceiling. All-or-nothing
validation: unresolved skill IDs or invalid metadata abort the entire sum.

Threshold table is canonical; formula accumulates seconds without per-skill
rounding. Character attributes must be exactly the five named fields; metadata
attribute names validate against those names before lookup. Deficit is clamped
to non-negative (already-trained skills produce zero contribution).
"""

import math
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

AVAILABLE = "available"
REFRESH_REQUIRED = "refresh_required"
ATTRIBUTES_UNAVAILABLE = "attributes_unavailable"
METADATA_UNAVAILABLE = "metadata_unavailable"
ATTRIBUTE_NAMES = frozenset(
    {"charisma", "intelligence", "memory", "perception", "willpower"}
)


@dataclass(frozen=True)
class SkillTrainingMetadata:
    rank: int
    primary_attribute: str
    secondary_attribute: str
    fetched_utc: datetime


@dataclass(frozen=True)
class TrainingEstimate:
    seconds: int | None
    status: str


_RANK_ONE_THRESHOLDS = (0, 250, 1415, 8000, 45255, 256000)
# Canonical threshold table: _RANK_ONE_THRESHOLDS[level] * rank = total SP.


def skill_point_threshold(rank: int, level: int) -> int:
    if rank <= 0 or not 1 <= level <= 5:
        raise ValueError("Skill rank and level must be positive EVE values.")
    return rank * _RANK_ONE_THRESHOLDS[level]


def estimate(
    requirements,
    skill_ids,
    skill_points,
    *,
    skill_points_complete,
    attributes,
    metadata,
) -> TrainingEstimate:
    if not skill_points_complete:
        return TrainingEstimate(None, REFRESH_REQUIRED)

    if not attributes or not all(attr in attributes for attr in ATTRIBUTE_NAMES):
        return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

    # Validate only the five named attributes: all present, all positive integers, none bool
    for attr_name in ATTRIBUTE_NAMES:
        val = attributes[attr_name]
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
            return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

    total_seconds = Fraction(0)

    # One casefolded index, built before the loop instead of a linear scan
    # per requirement -- and casefold(), not lower(), because
    # evaluator.evaluate() resolves the same name from the same mapping
    # with casefold(). The two answers are printed in one roster row, and
    # the two folds disagree on a handful of names (German eszett, Greek
    # final sigma), which is enough for a scored requirement to sit beside
    # an estimate claiming its metadata is missing.
    lookup = {str(name).casefold(): sid for name, sid in skill_ids.items()}

    for req in requirements:
        skill_id = lookup.get(req.skill_name.casefold())

        if skill_id is None:
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        if skill_id not in metadata:
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        meta = metadata[skill_id]

        try:
            target_sp = skill_point_threshold(meta.rank, req.level)
        except ValueError:
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        if not isinstance(meta.primary_attribute, str) or not isinstance(
            meta.secondary_attribute, str
        ):
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        if (
            meta.primary_attribute.lower() not in ATTRIBUTE_NAMES
            or meta.secondary_attribute.lower() not in ATTRIBUTE_NAMES
        ):
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        current_sp = skill_points.get(skill_id, 0)
        deficit = max(0, target_sp - current_sp)

        if deficit > 0:
            primary = attributes.get(meta.primary_attribute.lower(), None)
            secondary = attributes.get(meta.secondary_attribute.lower(), None)

            if primary is None or secondary is None:
                return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

            denominator = primary * 2 + secondary
            if denominator <= 0:
                return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

            seconds_fraction = Fraction(deficit * 120, denominator)
            total_seconds += seconds_fraction

    result_seconds = math.ceil(total_seconds)
    return TrainingEstimate(result_seconds, AVAILABLE)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""

    if seconds == 0:
        return "0m"

    minutes = (seconds + 30) // 60

    if minutes == 0:
        return "<1m"

    days = minutes // (24 * 60)
    remaining_minutes = minutes % (24 * 60)
    hours = remaining_minutes // 60
    mins = remaining_minutes % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
        parts.append(f"{hours}h")
    elif hours > 0:
        parts.append(f"{hours}h")
        parts.append(f"{mins}m")
    else:
        parts.append(f"{mins}m")

    return " ".join(parts[:2])
