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
    # Step 1: Validate skill_points_complete
    if not skill_points_complete:
        return TrainingEstimate(None, REFRESH_REQUIRED)

    # Step 2: Validate attributes
    if not attributes or not all(attr in attributes for attr in ATTRIBUTE_NAMES):
        return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

    # All attributes must be positive
    if not all(v > 0 for v in attributes.values()):
        return TrainingEstimate(None, ATTRIBUTES_UNAVAILABLE)

    # Step 3: Calculate total seconds using Fraction arithmetic
    total_seconds = Fraction(0)

    for req in requirements:
        # Get skill ID (case-insensitive lookup)
        # skill_ids maps skill_name -> skill_id
        skill_id = None
        for sname, sid in skill_ids.items():
            if sname.lower() == req.skill_name.lower():
                skill_id = sid
                break

        if skill_id is None:
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        # Check if metadata exists
        if skill_id not in metadata:
            return TrainingEstimate(None, METADATA_UNAVAILABLE)

        meta = metadata[skill_id]

        # Get current SP (0 if absent)
        current_sp = skill_points.get(skill_id, 0)

        # Calculate target SP
        target_sp = skill_point_threshold(meta.rank, req.level)

        # Calculate deficit (clamped to non-negative)
        deficit = max(0, target_sp - current_sp)

        if deficit > 0:
            # Get attributes (case-insensitive)
            attrs = {k.lower(): v for k, v in attributes.items()}
            primary = attrs.get(meta.primary_attribute.lower(), 0)
            secondary = attrs.get(meta.secondary_attribute.lower(), 0)

            # Calculate seconds using the formula
            seconds_fraction = Fraction(deficit * 120, primary * 2 + secondary)
            total_seconds += seconds_fraction

    # Round up once at the end
    result_seconds = math.ceil(total_seconds)

    return TrainingEstimate(result_seconds, AVAILABLE)


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""

    if seconds == 0:
        return "0m"

    # Round to nearest minute: (seconds + 30) // 60
    minutes = (seconds + 30) // 60

    # Positive seconds that round to 0 minutes get special treatment
    if minutes == 0:
        return "<1m"

    # Convert to days, hours, minutes
    days = minutes // (24 * 60)
    remaining_minutes = minutes % (24 * 60)
    hours = remaining_minutes // 60
    mins = remaining_minutes % 60

    # Build result with at most two units
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")

    # Return only the first two parts
    return " ".join(parts[:2])
