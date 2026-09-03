import datetime
from pathlib import Path

import pytest

from wingman.telemetry import parsing

UTC = datetime.UTC
FIXTURES = Path(__file__).parent / "fixtures" / "gamelogs"


def _fixture(name: str) -> tuple[str, str]:
    body = (FIXTURES / name).read_text(encoding="utf-8-sig").splitlines()
    who = next(
        line.split(":", 1)[1].strip()
        for line in body
        if line.strip().startswith("Listener:")
    )
    combat = next(line for line in body if "(combat)" in line)
    return who, combat


def test_eve_timestamp_is_aware_utc():
    line = "[ 2026.09.03 12:34:56 ] (combat) body"
    assert parsing.parse_timestamp(line) == datetime.datetime(
        2026, 9, 3, 12, 34, 56, tzinfo=UTC
    )


def test_timestamp_requires_fixed_numeric_fields():
    assert parsing.parse_timestamp("[ 2026.9.03 12:34:56 ] (combat) body") is None


def test_invalid_timestamp_does_not_discard_alert_body_fact():
    parsed = parsing.parse_line(
        "[ 2026.02.30 12:34:56 ] (combat) Sleepless Patroller misses you",
        "Aiga Otsolen",
    )
    assert parsed.occurred_at is None
    assert parsed.timestamp_error
    assert [fact.kind for fact in parsed.facts] == ["incoming_miss"]


@pytest.mark.parametrize(
    ("name", "expected_at", "amount", "target", "source"),
    [
        (
            "outgoing_direct.txt",
            datetime.datetime(2025, 11, 14, 1, 15, 33, tzinfo=UTC),
            299,
            "Mara Veld[OXWLD](Sleepless Patroller)",
            "Caldari Navy Scourge Heavy Missile",
        ),
        (
            "outgoing_drone.txt",
            datetime.datetime(2025, 11, 16, 0, 2, 16, tzinfo=UTC),
            22,
            "Mara Veld[OXWLD](Sleepless Patroller)",
            "Acolyte II",
        ),
    ],
)
def test_outgoing_damage_fixtures_parse_amount_target_and_source(
    name, expected_at, amount, target, source
):
    who, line = _fixture(name)
    parsed = parsing.parse_line(line, who)

    assert parsed.occurred_at == expected_at
    assert parsed.timestamp_error is None
    assert len(parsed.facts) == 1

    fact = parsed.facts[0]
    assert fact.kind == "outgoing_damage"
    assert fact.amount == amount
    assert fact.target == target
    assert fact.source == source
