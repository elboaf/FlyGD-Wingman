"""Readiness scoring. Ported from TriffView's SkillPlanEvaluator.cs.

This is the semantic core of the feature: every UI decision downstream
reads one of these strings, and TriffView has no automated coverage of
it at all. That is the one posture this port deliberately does not
inherit.
"""
from datetime import datetime, timedelta, timezone

import pytest

from obs_youtube_uploader.eveskills import evaluator as ev
from obs_youtube_uploader.eveskills.plans import Requirement

T0 = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def entry(skill_id, finished_level, position, finish=None):
    return ev.QueueEntry(skill_id=skill_id, finished_level=finished_level,
                         start_date=T0, finish_date=finish,
                         queue_position=position)


def test_no_sufficient_entry_returns_none():
    queue = [entry(100, 2, 0)]
    assert ev.lowest_sufficient_entry(queue, 100, 4) is None


def test_entries_for_other_skills_are_ignored():
    queue = [entry(999, 5, 0)]
    assert ev.lowest_sufficient_entry(queue, 100, 1) is None


def test_the_lowest_sufficient_level_wins():
    """A plan asking for III is satisfied by the entry that finishes at
    III, not by the one that eventually reaches V."""
    queue = [entry(100, 5, 0), entry(100, 3, 1), entry(100, 4, 2)]
    assert ev.lowest_sufficient_entry(queue, 100, 3).finished_level == 3


def test_queue_position_breaks_a_level_tie():
    queue = [entry(100, 4, 7), entry(100, 4, 2)]
    assert ev.lowest_sufficient_entry(queue, 100, 4).queue_position == 2


def test_the_finish_date_never_decides_which_entry_is_chosen():
    """The C# original is named EarliestSufficientEntry
    (SkillPlanEvaluator.cs:121) and the name misleads: it never looks at
    a date. Here the V entry finishes days BEFORE the III entry, and the
    III entry still wins because it is the lowest sufficient level. The
    port keeps that behaviour and renames the function to say so."""
    queue = [entry(100, 5, 0, finish=T0 + timedelta(days=1)),
             entry(100, 3, 1, finish=T0 + timedelta(days=9))]
    chosen = ev.lowest_sufficient_entry(queue, 100, 3)
    assert chosen.finished_level == 3
    assert chosen.finish_date == T0 + timedelta(days=9)


def test_an_entry_with_no_finish_date_is_still_selectable():
    """A paused queue reports entries with null dates. They still say
    "this skill is queued to a sufficient level", which is the whole
    question this function answers."""
    queue = [entry(100, 4, 0, finish=None)]
    assert ev.lowest_sufficient_entry(queue, 100, 4) is not None


def evaluate(reqs, *, ids=None, active=None, trained=None, queue=(),
             snapshot=True):
    """Call evaluate() with the four mappings defaulted to empty."""
    return ev.evaluate(reqs,
                       skill_ids={"Navigation": 100} if ids is None else ids,
                       active_levels=active or {},
                       trained_levels=trained or {},
                       queue=queue,
                       has_snapshot=snapshot)


NAV3 = (Requirement("Navigation", 3),)


def test_active_at_or_above_the_required_level_is_active():
    got = evaluate(NAV3, active={100: 3})
    assert got.requirements[0].state == ev.ACTIVE


def test_active_below_the_required_level_is_not_active():
    got = evaluate(NAV3, active={100: 2})
    assert got.requirements[0].state == ev.MISSING


def test_active_outranks_trained():
    """First match wins, in the order Unknown, Active, TrainedInactive,
    Queued, Missing. A skill that is both usable and trained is usable."""
    got = evaluate(NAV3, active={100: 5}, trained={100: 5})
    assert got.requirements[0].state == ev.ACTIVE


def test_trained_but_inactive_is_trained_inactive():
    """This is the inactive-clone / lapsed-Omega case: the level is
    trained, the active level is lower, so the character owns the skill
    and cannot currently use it."""
    got = evaluate(NAV3, active={100: 1}, trained={100: 4})
    assert got.requirements[0].state == ev.TRAINED_INACTIVE


def test_trained_outranks_queued():
    got = evaluate(NAV3, trained={100: 3}, queue=[entry(100, 5, 0)])
    assert got.requirements[0].state == ev.TRAINED_INACTIVE


def test_a_sufficient_queue_entry_is_queued():
    got = evaluate(NAV3, queue=[entry(100, 3, 0, finish=T0)])
    analysis = got.requirements[0]
    assert analysis.state == ev.QUEUED
    assert analysis.queued_finish_utc == T0


def test_an_insufficient_queue_entry_leaves_it_missing():
    got = evaluate(NAV3, queue=[entry(100, 2, 0, finish=T0)])
    assert got.requirements[0].state == ev.MISSING


def test_a_queued_entry_with_no_finish_date_flags_timing_unknown():
    """A paused queue reports null dates. The requirement is genuinely
    queued -- the row must say Training, and must not invent an ETA."""
    got = evaluate(NAV3, queue=[entry(100, 3, 0, finish=None)])
    analysis = got.requirements[0]
    assert analysis.state == ev.QUEUED
    assert analysis.queued_finish_utc is None
    assert analysis.queue_timing_unknown is True


def test_nothing_at_all_is_missing():
    assert evaluate(NAV3).requirements[0].state == ev.MISSING


def test_an_unresolved_skill_name_is_unknown():
    """Unknown is about the PLAN, not the character: the name never
    resolved to a validated category-16 type id, so no character can be
    scored against it."""
    got = evaluate((Requirement("Nvigation", 3),), ids={})
    assert got.requirements[0].state == ev.UNKNOWN


def test_the_skill_id_lookup_is_case_insensitive():
    """Every name comparison in this subsystem is case-insensitive, and
    the cache is keyed on whatever spelling ESI returned, which is not
    necessarily the spelling in the plan file."""
    got = evaluate((Requirement("navigation", 3),),
                   ids={"NAVIGATION": 100}, active={100: 5})
    assert got.requirements[0].state == ev.ACTIVE


def test_the_analysis_reports_the_levels_it_scored_against():
    """The expanded row renders these next to the requirement, so a user
    can see "you have III, this needs IV" without a second request."""
    got = evaluate(NAV3, active={100: 1}, trained={100: 2})
    analysis = got.requirements[0]
    assert (analysis.active_level, analysis.trained_level) == (1, 2)
    assert (analysis.skill_name, analysis.required_level) == ("Navigation", 3)


def test_an_unresolved_name_reports_no_levels():
    got = evaluate((Requirement("Nvigation", 3),), ids={}, active={100: 5})
    analysis = got.requirements[0]
    assert analysis.active_level is None and analysis.trained_level is None


def test_all_active_is_ready():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 5, 200: 5})
    assert got.readiness == ev.READY


def test_one_queued_requirement_makes_the_plan_training():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 5}, queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.TRAINING


def test_locked_outranks_training():
    """Stated as its own test because it is the counter-intuitive half of
    the table. A character who has TRAINED the skill but cannot use it --
    an inactive clone, a lapsed Omega -- is further from flying the plan
    than one actively training toward it: the second will get there on
    its own, the first needs the user to go do something. So Locked
    ranks WORSE than Training and the plan reads Locked."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5},
                   queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.LOCKED


def test_missing_outranks_locked():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5})
    assert got.readiness == ev.READINESS_MISSING


def test_one_unknown_name_poisons_the_whole_plan():
    """Unknown outranks everything. One unresolved skill name makes the
    plan Unknown for EVERY character, because the plan cannot be scored
    -- not because any character is deficient."""
    reqs = (Requirement("Navigation", 3), Requirement("Nvigation", 1))
    got = evaluate(reqs, ids={"Navigation": 100}, active={100: 5})
    assert got.readiness == ev.READINESS_UNKNOWN


def test_no_snapshot_is_unscored_with_an_empty_requirement_list():
    """Unscored is the most common state a user sees: every newly
    authorised character is Unscored until its first refresh lands. The
    requirement list is EMPTY rather than every-requirement-Unknown,
    because there is no data to score against and the roster must not
    read as "this plan is broken"."""
    got = evaluate(NAV3, active={100: 5}, snapshot=False)
    assert got.readiness == ev.UNSCORED
    assert got.requirements == ()
    assert got.estimated_finish_utc is None


def test_an_empty_plan_is_ready():
    """A plan with no requirements is trivially satisfied. Unscored is
    reached by the snapshot gate, never by counting requirements."""
    assert evaluate(()).readiness == ev.READY


def test_the_eta_is_the_latest_finish_not_the_earliest():
    """The plan completes when the LAST queued requirement does. Taking
    the minimum would promise a date by which the character still cannot
    fly the ship."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    late = T0 + timedelta(days=9)
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   queue=[entry(100, 3, 0, finish=T0),
                          entry(200, 2, 1, finish=late)])
    assert got.readiness == ev.TRAINING
    assert got.estimated_finish_utc == late


def test_one_dateless_queue_entry_suppresses_the_eta_entirely():
    """The other half. With a null date in the set, the maximum of the
    rest is a lie -- the missing one could land later. The row reads
    "Training - timing unknown" instead of showing a date it cannot
    stand behind."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   queue=[entry(100, 3, 0, finish=T0),
                          entry(200, 2, 1, finish=None)])
    assert got.readiness == ev.TRAINING
    assert got.estimated_finish_utc is None
    assert got.queue_timing_unknown is True


def test_a_ready_plan_has_no_eta():
    """The ETA is populated only when readiness is exactly Training.
    Nothing is being waited for otherwise."""
    got = evaluate(NAV3, active={100: 5})
    assert got.readiness == ev.READY and got.estimated_finish_utc is None


def test_a_locked_plan_has_no_eta_even_with_a_dated_queue_entry():
    """Exactly Training, not "Training is present". A Locked plan has a
    queued requirement with a real date, and showing it would promise a
    completion the inactive clone will not deliver."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5},
                   queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.LOCKED
    assert got.estimated_finish_utc is None


def test_the_counts_partition_the_requirements():
    reqs = (Requirement("A", 1), Requirement("B", 1), Requirement("C", 1),
            Requirement("D", 1), Requirement("E", 1))
    got = evaluate(reqs, ids={"A": 1, "B": 2, "C": 3, "D": 4},
                   active={1: 5}, trained={2: 5},
                   queue=[entry(3, 1, 0, finish=T0)])
    assert (got.active_count, got.trained_inactive_count, got.queued_count,
            got.missing_count, got.unknown_count) == (1, 1, 1, 1, 1)
    assert sum([got.active_count, got.trained_inactive_count,
                got.queued_count, got.missing_count,
                got.unknown_count]) == len(got.requirements)


def test_compact_status_of_nothing_is_ready():
    assert ev.compact_status(()) == ev.READY


def test_compact_status_maps_an_unrecognised_state_to_unknown():
    """Defensive, and cheap: a state string added to this module without
    a contribution entry must not silently score as Ready. The roster's
    catch-all bucket is the same instinct on the page side."""
    rogue = ev.RequirementAnalysis("X", 1, None, None, "Sideways", None, False)
    assert ev.compact_status([rogue]) == ev.READINESS_UNKNOWN
