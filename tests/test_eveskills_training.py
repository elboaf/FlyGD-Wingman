from datetime import UTC, datetime

import pytest

from wingman.eveskills import plans, training

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


@pytest.mark.parametrize(
    ("seconds", "label"),
    [
        (None, ""),
        (0, "0m"),
        (1, "<1m"),
        (12 * 60, "12m"),
        (4 * 3600 + 20 * 60, "4h 20m"),
        (2 * 86400 + 4 * 3600 + 31 * 60, "2d 4h"),
    ],
)
def test_format_duration(seconds, label):
    assert training.format_duration(seconds) == label
