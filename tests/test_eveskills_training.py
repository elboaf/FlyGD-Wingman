from datetime import UTC, datetime

import pytest

from wingman.eveskills import evaluator, plans, training

NOW = datetime(2026, 9, 2, tzinfo=UTC)
ATTRS = {
    "charisma": 19,
    "intelligence": 20,
    "memory": 20,
    "perception": 27,
    "willpower": 21,
}
META = training.SkillTrainingMetadata(
    rank=1,
    primary_attribute="perception",
    secondary_attribute="willpower",
    fetched_utc=NOW,
)
META_RANK_3 = training.SkillTrainingMetadata(
    rank=3,
    primary_attribute="charisma",
    secondary_attribute="memory",
    fetched_utc=NOW,
)


def req(name="Gunnery", level=5):
    return plans.Requirement(skill_name=name, level=level)


def test_cumulative_sp_thresholds_match_eve_levels():
    assert [training.skill_point_threshold(1, level) for level in range(1, 6)] == [
        250,
        1415,
        8000,
        45255,
        256000,
    ]
    assert training.skill_point_threshold(3, 5) == 768000


def test_estimate_uses_partial_sp_and_current_attribute_pair():
    result = training.estimate(
        [req(level=4)],
        {"gunnery": 3300},
        {3300: 40_000},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    # 5,255 SP at 37.5 SP/minute, rounded up once at the final second.
    assert result == training.TrainingEstimate(seconds=8408, status=training.AVAILABLE)


def test_queued_position_does_not_remove_remaining_sp():
    # Queue state is intentionally not an estimator input.
    result = training.estimate(
        [req(level=5)],
        {"gunnery": 3300},
        {3300: 45_255},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert result.seconds > 0


def test_absent_skill_is_zero_only_in_a_complete_snapshot():
    complete = training.estimate(
        [req(level=1)],
        {"gunnery": 3300},
        {},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    incomplete = training.estimate(
        [req(level=1)],
        {"gunnery": 3300},
        {},
        skill_points_complete=False,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert complete.status == training.AVAILABLE
    assert incomplete == training.TrainingEstimate(None, training.REFRESH_REQUIRED)


def test_one_missing_metadata_record_suppresses_the_whole_sum():
    result = training.estimate(
        [req("Gunnery", 3), req("Navigation", 3)],
        {"gunnery": 3300, "navigation": 3449},
        {3300: 8000, 3449: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert result == training.TrainingEstimate(None, training.METADATA_UNAVAILABLE)


def test_malformed_rank_returns_metadata_unavailable():
    bad_meta = training.SkillTrainingMetadata(
        rank=-1,
        primary_attribute="perception",
        secondary_attribute="willpower",
        fetched_utc=NOW,
    )
    result = training.estimate(
        [req(level=3)],
        {"gunnery": 3300},
        {3300: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: bad_meta},
    )
    assert result == training.TrainingEstimate(None, training.METADATA_UNAVAILABLE)


def test_unknown_metadata_attribute_name_returns_metadata_unavailable():
    bad_meta = training.SkillTrainingMetadata(
        rank=1,
        primary_attribute="invalid_attr",
        secondary_attribute="willpower",
        fetched_utc=NOW,
    )
    result = training.estimate(
        [req(level=3)],
        {"gunnery": 3300},
        {3300: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: bad_meta},
    )
    assert result == training.TrainingEstimate(None, training.METADATA_UNAVAILABLE)


def test_missing_one_character_attribute_returns_attributes_unavailable():
    incomplete_attrs = {
        "charisma": 19,
        "intelligence": 20,
        "memory": 20,
        "perception": 27,
    }
    result = training.estimate(
        [req(level=3)],
        {"gunnery": 3300},
        {3300: 0},
        skill_points_complete=True,
        attributes=incomplete_attrs,
        metadata={3300: META},
    )
    assert result == training.TrainingEstimate(None, training.ATTRIBUTES_UNAVAILABLE)


def test_already_trained_skill_produces_zero_seconds():
    result = training.estimate(
        [req(level=1)],
        {"gunnery": 3300},
        {3300: 500},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert result == training.TrainingEstimate(0, training.AVAILABLE)


def test_multiple_skills_with_different_attribute_pairs_accumulate():
    result = training.estimate(
        [req("Gunnery", 2), req("Navigation", 2)],
        {"gunnery": 3300, "navigation": 3449},
        {3300: 0, 3449: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={
            3300: META,
            3449: META_RANK_3,
        },
    )
    # Exact, not merely positive: a lookup that resolved both
    # requirements to the SAME id would still sum to something positive.
    # Gunnery II is 1,415 SP over perception/willpower (2264s exactly);
    # Navigation II is rank 3, so 4,245 SP over charisma/memory
    # (254700/29 s); the single final ceiling lands on 11,047.
    assert result == training.TrainingEstimate(11047, training.AVAILABLE)
    assert isinstance(result.seconds, int)


def test_a_name_folds_here_exactly_as_it_folds_for_readiness():
    """The readiness and the estimate are two halves of one roster row,
    built from the identical id mapping, so they must agree about whether
    a name is known. lower() and casefold() disagree on the German
    eszett -- "STRASSE" lowers to "strasse" but "stra\u00dfe" lowers to
    itself -- which is enough for a scored requirement to sit beside a
    blank estimate that claims the metadata is missing."""
    skill_ids = {"Stra\u00dfe": 3300}
    requirements = [req("STRASSE", 1)]

    analysis = evaluator.evaluate(
        requirements, skill_ids, {3300: 0}, {3300: 0}, (), True
    )
    result = training.estimate(
        requirements,
        skill_ids,
        {3300: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )

    assert analysis.requirements[0].state != evaluator.UNKNOWN
    # 250 SP at 75 SP/2min: the estimate resolved the same id readiness did.
    assert result == training.TrainingEstimate(400, training.AVAILABLE)


def test_an_arbitrarily_cased_mapping_still_resolves():
    """skill_ids arrives folded from the cache today, but this module is
    pure and takes whatever it is handed -- a mapping keyed on the
    spelling ESI returned must keep resolving."""
    result = training.estimate(
        [req("gUnNeRy", 1)],
        {"GUNNERY": 3300},
        {3300: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )

    assert result == training.TrainingEstimate(400, training.AVAILABLE)


def test_arbitrary_extra_fields_in_attributes_do_not_affect_estimate():
    attrs_with_extras = {
        "charisma": 19,
        "intelligence": 20,
        "memory": 20,
        "perception": 27,
        "willpower": 21,
        "extra_string": "should be ignored",
        "extra_negative": -5,
    }
    result_with_extras = training.estimate(
        [req(level=4)],
        {"gunnery": 3300},
        {3300: 40_000},
        skill_points_complete=True,
        attributes=attrs_with_extras,
        metadata={3300: META},
    )
    result_without_extras = training.estimate(
        [req(level=4)],
        {"gunnery": 3300},
        {3300: 40_000},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert result_with_extras == result_without_extras


@pytest.mark.parametrize(
    ("seconds", "label"),
    [
        (None, ""),
        (0, "0m"),
        (1, "<1m"),
        (12 * 60, "12m"),
        (4 * 3600 + 20 * 60, "4h 20m"),
        (2 * 86400 + 4 * 3600 + 31 * 60, "2d 4h"),
        (2 * 86400 + 30 * 60, "2d 0h"),
        (3 * 3600 + 30 * 60, "3h 30m"),
    ],
)
def test_format_duration(seconds, label):
    assert training.format_duration(seconds) == label
