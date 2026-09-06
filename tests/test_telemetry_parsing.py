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


def _fixture_line(name: str, phrase: str) -> tuple[str, str]:
    body = (FIXTURES / name).read_text(encoding="utf-8-sig").splitlines()
    who = next(
        line.split(":", 1)[1].strip()
        for line in body
        if line.strip().startswith("Listener:")
    )
    return who, next(line for line in body if phrase in line)


def test_tackle_fixtures_preserve_scram_and_point():
    scram_who, scram_line = _fixture_line(
        "player_scramble.txt", "Warp scramble attempt"
    )
    point_who, point_line = _fixture_line(
        "player_unresolved.txt", "Warp disruption attempt"
    )

    assert [fact.kind for fact in parsing.parse_line(scram_line, scram_who).facts] == [
        "incoming_scram"
    ]
    assert [fact.kind for fact in parsing.parse_line(point_line, point_who).facts] == [
        "incoming_point"
    ]


def test_incoming_neut_fixture_parses_amount_and_source():
    who, line = _fixture_line("incoming_neut.txt", "237 GJ")

    parsed = parsing.parse_line(line, who)

    assert len(parsed.facts) == 1
    assert parsed.facts[0].kind == "incoming_neut"
    assert parsed.facts[0].amount == 237
    assert parsed.facts[0].source == "Doran Velk [BURN] Curse"


def test_zero_gj_incoming_neut_still_reports_neut_activity():
    who, line = _fixture_line("incoming_neut.txt", "0xffe57f7f><b>0 GJ")

    parsed = parsing.parse_line(line, who)

    assert len(parsed.facts) == 1
    assert parsed.facts[0].kind == "incoming_neut"
    assert parsed.facts[0].amount == 0


def test_outgoing_neut_is_not_incoming_ewar_even_when_amount_is_zero():
    who, line = _fixture_line("incoming_neut.txt", "0xff7fffff><b>0 GJ")

    assert parsing.parse_line(line, who).facts == ()


def test_outgoing_plain_amount_falls_back_to_stripped_text_capture():
    line = (
        "[ 2025.11.14 01:15:33 ] (combat) <color=0xff00ffff>1,299 "
        "<color=0x77ffffff><font size=10>to</font> "
        "<b>Target Ship</b><font size=10> - Missile - Hits</font>"
    )

    parsed = parsing.parse_line(line, "Alice")

    assert len(parsed.facts) == 1
    assert parsed.facts[0].kind == "outgoing_damage"
    assert parsed.facts[0].amount == 1299


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
