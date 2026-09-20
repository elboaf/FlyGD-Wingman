"""Codec origin algebra, independent of clocks and runtime projection owners."""

import copy

import pytest

from wingman.fleetsharing import protocol as p


def put_row(activity=10, observation=10):
    return {
        "character_id": 1,
        "outgoing_dps": None,
        "incoming_dps": 0,
        "activity_age_ms": activity,
        "effects": [
            {"kind": "NEUT", "observations": [{"name": None, "age_ms": observation}]}
        ],
    }


def get_row(transport=10, activity=10, observation=10):
    return {
        **put_row(activity, observation),
        "character_name": "Alice",
        "state": "live",
        "age_ms": transport,
        "publication_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    }


@pytest.mark.parametrize(
    "sample,activity,observation,accept",
    [
        (0, 0, 0, True),
        (10, 10, 10, True),
        (11, 10, 11, True),
        (9, 10, 10, False),
        (10, 10, 11, False),
        (11, 11, 10, False),
        (29999, 29999, 29999, True),
    ],
)
def test_put_nonnegative_origins_and_activity_order(
    sample, activity, observation, accept
):
    value = {
        "protocol": 2,
        "sampled_at_ms": sample,
        "rows": [put_row(activity, observation)],
    }
    if accept:
        result = p.parse_combat_put(value)
        assert result.sampled_at_ms == sample
        assert result.rows[0].activity_age_ms == activity
        assert result.rows[0].effects[0].observations[0].age_ms == observation
    else:
        with pytest.raises(ValueError):
            p.parse_combat_put(value)


@pytest.mark.parametrize(
    "time,transport,activity,observation,accept",
    [
        (0, 0, 0, 0, True),
        (10, 10, 10, 10, True),
        (11, 9, 10, 11, True),
        (9, 10, 10, 10, False),
        (10, 9, 11, 11, False),
        (10, 9, 10, 11, False),
        (11, 11, 10, 11, False),
        (11, 9, 11, 10, False),
    ],
)
def test_get_nonnegative_origins_and_measurement_activity_order(
    time, transport, activity, observation, accept
):
    value = {
        "protocol": 2,
        "server_time_ms": time,
        "rows": [get_row(transport, activity, observation)],
    }
    if accept:
        result = p.parse_snapshot(value)
        assert result.server_time_ms == time
        assert result.rows[0].age_ms == transport
        assert result.rows[0].activity_age_ms == activity
        assert result.rows[0].effects[0].observations[0].age_ms == observation
    else:
        with pytest.raises(ValueError):
            p.parse_snapshot(value)


@pytest.mark.parametrize("read", [False, True])
def test_activity_origin_is_checked_even_without_effects(read):
    row = get_row(0) if read else put_row()
    row["effects"] = []
    key, parser = (
        ("server_time_ms", p.parse_snapshot)
        if read
        else ("sampled_at_ms", p.parse_combat_put)
    )
    value = {"protocol": 2, key: 10, "rows": [row]}
    assert parser(value).rows[0].activity_age_ms == 10
    value[key] = 9
    with pytest.raises(ValueError):
        parser(value)


@pytest.mark.parametrize("read", [False, True])
@pytest.mark.parametrize("bad_kind", ["SCRAM", "POINT", "NEUT"])
def test_one_bad_observation_in_later_row_rejects_whole_payload(read, bad_kind):
    row = get_row() if read else put_row()
    row["effects"] = [
        {"kind": kind, "observations": [{"name": None, "age_ms": 10}]}
        for kind in ("SCRAM", "POINT", "NEUT")
    ]
    second = copy.deepcopy(row)
    second["character_id"] = 2
    if read:
        second["publication_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    key, parser = (
        ("server_time_ms", p.parse_snapshot)
        if read
        else ("sampled_at_ms", p.parse_combat_put)
    )
    value = {"protocol": 2, key: 10, "rows": [row, second]}
    assert len(parser(value).rows) == 2
    next(effect for effect in second["effects"] if effect["kind"] == bad_kind)[
        "observations"
    ][0]["age_ms"] = 11
    with pytest.raises(ValueError):
        parser(value)
