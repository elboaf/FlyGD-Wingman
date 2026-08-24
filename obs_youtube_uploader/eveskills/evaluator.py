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

# Requirement state -> the plan readiness it contributes. Locked ranks
# WORSE than Training on purpose: a character who has trained a skill but
# cannot use it (inactive clone, lapsed Omega) needs the user to go do
# something, while one actively training will arrive on its own.
_CONTRIBUTION = {
    ACTIVE: READY,
    QUEUED: TRAINING,
    TRAINED_INACTIVE: LOCKED,
    MISSING: READINESS_MISSING,
    UNKNOWN: READINESS_UNKNOWN,
}


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


@dataclass(frozen=True)
class RequirementAnalysis:
    skill_name: str
    required_level: int
    active_level: int | None
    trained_level: int | None
    state: str
    queued_finish_utc: datetime | None
    queue_timing_unknown: bool


@dataclass(frozen=True)
class PlanAnalysis:
    readiness: str
    estimated_finish_utc: datetime | None
    queue_timing_unknown: bool
    requirements: tuple

    def _count(self, state: str) -> int:
        return sum(1 for a in self.requirements if a.state == state)

    @property
    def active_count(self) -> int:
        return self._count(ACTIVE)

    @property
    def trained_inactive_count(self) -> int:
        return self._count(TRAINED_INACTIVE)

    @property
    def queued_count(self) -> int:
        return self._count(QUEUED)

    @property
    def missing_count(self) -> int:
        return self._count(MISSING)

    @property
    def unknown_count(self) -> int:
        return self._count(UNKNOWN)


def compact_status(analyses) -> str:
    """The worst readiness any requirement contributes.

    Unknown > Missing > Locked > Training > Ready. An empty sequence is
    Ready: a plan with nothing in it is trivially satisfied, and Unscored
    is reached by evaluate()'s has_snapshot gate rather than by counting.

    An unrecognised state contributes Unknown rather than being skipped,
    so a state added to this module without a _CONTRIBUTION entry cannot
    silently score a plan Ready.
    """
    worst = READY
    for analysis in analyses:
        contribution = _CONTRIBUTION.get(analysis.state, READINESS_UNKNOWN)
        if READINESS_ORDER.index(contribution) > READINESS_ORDER.index(worst):
            worst = contribution
    return worst


def evaluate(requirements, skill_ids, active_levels, trained_levels,
             queue, has_snapshot: bool) -> PlanAnalysis:
    """Score *requirements* for one character against one snapshot."""
    if not has_snapshot:
        # Unscored, with an EMPTY requirement list. Every newly
        # authorised character is here until its first refresh lands, so
        # this is the most common state a user sees -- and marking every
        # requirement Unknown instead would make an ordinary new
        # character look like a broken plan.
        return PlanAnalysis(UNSCORED, None, False, ())

    # Case-insensitive on the name, because the cache is keyed on the
    # spelling ESI returned and the plan file carries whatever the user
    # typed. Built once per plan rather than per requirement.
    lookup = {str(name).casefold(): int(type_id)
              for name, type_id in skill_ids.items()}

    analyses = []
    for req in requirements:
        skill_id = lookup.get(req.skill_name.casefold())
        if skill_id is None:
            # Unknown is about the plan, not the character. No levels are
            # reported because there is no id to have looked them up by.
            analyses.append(RequirementAnalysis(
                skill_name=req.skill_name, required_level=req.level,
                active_level=None, trained_level=None, state=UNKNOWN,
                queued_finish_utc=None, queue_timing_unknown=False))
            continue
        # Defaults to 0, not None, matching the source's TryGetValue: a
        # resolved skill the character has simply never trained is level
        # 0, which is a different fact from the name never resolving to
        # an id at all (that case reports None above, and only there).
        active = active_levels.get(skill_id, 0)
        trained = trained_levels.get(skill_id, 0)
        chosen = None
        # First match wins, in exactly this order. Active before trained
        # because a skill that is usable is usable; trained before queued
        # because owning it beats being on the way to owning it.
        if active >= req.level:
            state = ACTIVE
        elif trained >= req.level:
            state = TRAINED_INACTIVE
        else:
            chosen = lowest_sufficient_entry(queue, skill_id, req.level)
            state = QUEUED if chosen is not None else MISSING
        analyses.append(RequirementAnalysis(
            skill_name=req.skill_name,
            required_level=req.level,
            active_level=active,
            trained_level=trained,
            state=state,
            queued_finish_utc=chosen.finish_date if chosen else None,
            # A paused queue reports null dates. The requirement is still
            # queued; what is unknown is when it lands.
            queue_timing_unknown=bool(chosen is not None
                                      and chosen.finish_date is None),
        ))

    readiness = compact_status(analyses)
    timing_unknown = any(a.queue_timing_unknown for a in analyses)
    finishes = [a.queued_finish_utc for a in analyses
                if a.state == QUEUED and a.queued_finish_utc is not None]
    # The MAXIMUM, not the minimum: the plan completes when the last
    # queued requirement does. And only when readiness is exactly
    # Training -- a Locked plan has a dated queue entry too, and showing
    # it would promise a completion the inactive clone will not deliver.
    # One dateless entry suppresses it entirely, because the maximum of
    # the rest could be beaten by the one with no date.
    estimated = None
    if readiness == TRAINING and finishes and not timing_unknown:
        estimated = max(finishes)
    return PlanAnalysis(readiness, estimated, timing_unknown, tuple(analyses))
