"""Readiness scoring. Pure: mappings in, an analysis out.

Ported from TriffView's SkillPlanEvaluator.cs. Dates are timezone-aware
UTC datetimes throughout; conversion to ISO strings happens only at the
bridge boundary in controller.py, so nothing here formats anything.
"""
from dataclasses import dataclass
from datetime import datetime

# --- RequirementState ---------------------------------------------------
ACTIVE = "Active"
TRAINED_INACTIVE = "TrainedInactive"
QUEUED = "Queued"
MISSING = "Missing"
UNKNOWN = "Unknown"

# --- PlanReadiness ------------------------------------------------------
READY = "Ready"
TRAINING = "Training"
LOCKED = "Locked"
READINESS_MISSING = "Missing"
READINESS_UNKNOWN = "Unknown"
UNSCORED = "Unscored"

# Best first. compact_status() takes the worst present, so a plan is only
# Ready when every one of its requirements is.
READINESS_ORDER = (READY, TRAINING, LOCKED, READINESS_MISSING,
                   READINESS_UNKNOWN, UNSCORED)


@dataclass(frozen=True)
class QueueEntry:
    skill_id: int
    finished_level: int
    start_date: datetime | None
    finish_date: datetime | None
    queue_position: int


def lowest_sufficient_entry(queue, skill_id: int, required_level: int):
    """The queued entry that satisfies *required_level* at the lowest level.

    Sorts by lowest sufficient finished level, tie-broken by queue
    position, and NEVER by date. The C# original is called
    EarliestSufficientEntry (SkillPlanEvaluator.cs:121), which misleads:
    "earliest" reads as a date and no date is consulted. A plan asking
    for Navigation III takes the entry finishing at III even when a
    later-positioned entry finishing at V has an earlier finish date.

    The behaviour is kept because the row's ETA must describe the entry
    that actually satisfies the requirement, not the deepest one that
    happens to cover it.
    """
    candidates = [e for e in queue
                  if e.skill_id == skill_id
                  and e.finished_level >= required_level]
    if not candidates:
        return None
    return min(candidates, key=lambda e: (e.finished_level, e.queue_position))
