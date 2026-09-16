import datetime
import json
import re
from pathlib import Path

import pytest

from wingman.alerts import patterns
from wingman.telemetry import parsing

UTC = datetime.UTC
FIXTURES = Path(__file__).parent / "fixtures" / "gamelogs"
NAME_VECTORS = json.loads(
    (FIXTURES.parent / "fleet-combat-v2.json").read_text(encoding="utf-8")
)["names"]


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


def _incoming_with_amount(token: str) -> tuple[str, str]:
    """Derive an incoming damage line with a custom amount token."""
    who, line = _fixture_line("player_damage_and_miss.txt", "from</font>")
    line = re.sub(r"(<b>)[\d,]+(</b>)", rf"\g<1>{token}\g<2>", line, count=1)
    return who, line


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


@pytest.mark.parametrize(
    ("token", "expected"), [("1234", 1234), ("1,234", 1234), ("12,345", 12345)]
)
def test_incoming_damage_accepts_metric_grade_amounts(token, expected):
    who, line = _incoming_with_amount(token)
    fact = parsing.parse_line(line, who).facts[0]
    assert fact.kind == "incoming_damage"
    assert fact.amount == expected
    assert fact.source


@pytest.mark.parametrize("token", ["1,,299", "12,34", ",,,"])
def test_incoming_damage_keeps_alert_fact_but_rejects_malformed_amount(token):
    who, line = _incoming_with_amount(token)
    fact = parsing.parse_line(line, who).facts[0]
    assert fact.kind == "incoming_damage"
    assert fact.amount is None
    assert fact.source


def test_incoming_damage_missing_amount_still_reports_attack_activity():
    who, line = _incoming_with_amount("")
    fact = parsing.parse_line(line, who).facts[0]
    assert fact.kind == "incoming_damage"
    assert fact.amount is None
    assert fact.source


@pytest.mark.parametrize(
    "fixture, phrase, kind, source, name, npc",
    [
        (
            "player_scramble.txt",
            "Warp scramble attempt",
            "incoming_scram",
            "Talia Renn [KVOS] Taranis",
            "Talia Renn",
            False,
        ),
        (
            "player_unresolved.txt",
            "Warp disruption attempt",
            "incoming_point",
            "Doran Velk Proteus",
            None,
            False,
        ),
        (
            "npc_scramble.txt",
            "Warp scramble attempt",
            "incoming_scram",
            "Emergent Preserver",
            None,
            True,
        ),
    ],
)
def test_tackle_name_is_additive_to_existing_fixture_source(
    fixture, phrase, kind, source, name, npc
):
    who, line = _fixture_line(fixture, phrase)
    parsed = parsing.parse_line(line, who)
    assert len(parsed.facts) == 1
    fact = parsed.facts[0]
    assert fact.kind == kind
    assert fact.amount is None
    assert fact.source.encode("utf-8") == source.encode("utf-8")
    assert patterns.match_line(line, who) == patterns.Match("warp_scramble", source)
    assert patterns.is_likely_npc(fact.source) is npc
    assert fact.observed_name == name


def _tackle_with_name(raw_name: str) -> tuple[str, str]:
    who, line = _fixture_line("player_scramble.txt", "Warp scramble attempt")
    return who, line.replace("Talia Renn", raw_name)


def test_malformed_outer_source_cannot_harvest_clean_nested_name():
    who, line = _tackle_with_name(
        "Bad<font size=10>from</font> "
        "<color=0xffffffff><b><color=0xffffffff><fontsize=12>Suffix"
    )
    line = line.replace("from</font>", "from</font", 1)

    parsed = parsing.parse_line(line, who)
    (fact,) = parsed.facts
    assert fact.kind == "incoming_scram"
    assert fact.amount is None
    assert fact.target == "you!"
    assert parsed.occurred_at == datetime.datetime(2025, 11, 14, 6, 41, 8, tzinfo=UTC)
    assert parsed.timestamp_error is None
    # Legacy source recovery stays permissive for Alerts; it is not proof that
    # a clean suffix is the complete raw candidate for additive attribution.
    assert fact.source.encode("utf-8") == b"Suffix [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Suffix [KVOS] Taranis"
    )
    assert patterns.is_likely_npc(fact.source) is False
    assert fact.observed_name is None


@pytest.mark.parametrize(
    "target_form, expected_target",
    [
        ("preposition_only", "you!"),
        (
            "plain_named",
            "Torvin Wexley [OXWLD] Drekavac [KVOS] Taranis to you!",
        ),
        (
            "decorated_named",
            "Torvin Wexley [OXWLD] Drekavac [KVOS] Taranis to you!",
        ),
    ],
)
def test_source_cannot_harvest_clean_prefix_before_fake_target(
    target_form, expected_target
):
    fake_target = ""
    if target_form == "plain_named":
        _, target_line = _fixture("player_scramble.txt")
        fake_target = target_line.split("<font size=10>to", 1)[1].replace(
            "you!", "Torvin Wexley [OXWLD] Drekavac"
        )
    elif target_form == "decorated_named":
        _, target_line = _fixture("npc_scramble.txt")
        fake_target = target_line.split("<font size=10>to", 1)[1]
    who, line = _tackle_with_name(
        "Prefix [FAKE]</color><color=0xfff0f000> Hull</color>"
        "<color=0xffffffff></b> <color=0x77ffffff><font size=10>to" + fake_target
    )

    parsed = parsing.parse_line(line, who)
    (fact,) = parsed.facts
    assert fact.kind == "incoming_scram"
    assert fact.amount is None
    assert fact.target == expected_target
    assert parsed.occurred_at == datetime.datetime(2025, 11, 14, 6, 41, 8, tzinfo=UTC)
    assert parsed.timestamp_error is None
    # The complete fake named targets still pass legacy victim admission at
    # their first ticker. Neither that nor a lone "to" proves a whole source.
    assert fact.source.encode("utf-8") == b"Prefix [FAKE] Hull"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Prefix [FAKE] Hull"
    )
    assert patterns.is_likely_npc(fact.source) is False
    assert fact.observed_name is None


@pytest.mark.parametrize("target_form", ["you", "plain_named", "decorated_named"])
@pytest.mark.parametrize("ending", ["", "\n", "\r\n", "\r"])
def test_complete_supported_target_preserves_name(target_form, ending):
    who, line = _tackle_with_name("Talia Renn")
    target = expected_target = "you!"
    if target_form != "you":
        target = expected_target = "Torvin Wexley [OXWLD] Drekavac"
    if target_form == "decorated_named":
        _, target_line = _fixture("npc_scramble.txt")
        target = target_line.split("</font>")[-1]
    line = line.removesuffix("you!") + target + ending
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == "incoming_scram"
    assert fact.target == expected_target
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Talia Renn [KVOS] Taranis"
    )
    assert fact.observed_name == "Talia Renn"


@pytest.mark.parametrize(
    "old, replacement",
    [
        ("to <b>", "to <b><i></i>"),
        ("<color=0xffffffff></font>you!", "<color=0xffffffff>you!"),
        ("to <b><color=0xffffffff></font>you!", "to <b>you!"),
        ("you!", "<i>you!</i>"),
        ("you!", "you!</b>"),
        ("you!", "you!<font size=10>"),
    ],
)
def test_malformed_target_framing_keeps_legacy_tackle_unnamed(old, replacement):
    who, line = _tackle_with_name("Talia Renn")
    line = line.replace(old, replacement)
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == "incoming_scram"
    assert fact.target == "you!"
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Talia Renn [KVOS] Taranis"
    )
    assert fact.observed_name is None


@pytest.mark.parametrize("decorated", [False, True])
@pytest.mark.parametrize(
    "remainder, expected_suffix",
    [
        (" [EXTRA] Hull", " [EXTRA] Hull"),
        ("</b>", ""),
        ("<font size=10>", ""),
        ("\nextra", " extra"),
    ],
)
def test_named_target_remainder_cannot_leave_clean_source_accepted(
    decorated, remainder, expected_suffix
):
    who, line = _tackle_with_name("Talia Renn")
    target = "Torvin Wexley [OXWLD] Drekavac"
    if decorated:
        _, target_line = _fixture("npc_scramble.txt")
        target = target_line.split("</font>")[-1]
    line = line.removesuffix("you!") + target + remainder
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == "incoming_scram"
    assert fact.target == "Torvin Wexley [OXWLD] Drekavac" + expected_suffix
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Talia Renn [KVOS] Taranis"
    )
    assert fact.observed_name is None


@pytest.mark.parametrize("prefix", ["broken ", "<font size=10>from</font "])
def test_observed_name_does_not_skip_unverified_leading_frame(prefix):
    who, line = _tackle_with_name("Talia Renn")
    line = prefix + line
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == "incoming_scram"
    assert fact.target == "you!"
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Talia Renn [KVOS] Taranis"
    )
    assert fact.observed_name is None


def test_verified_tackle_action_frame_without_timestamp_retains_name():
    who, line = _tackle_with_name("Talia Renn")
    line = line.removeprefix("[ 2025.11.14 06:41:08 ] ")
    parsed = parsing.parse_line(line, who)
    (fact,) = parsed.facts
    assert parsed.occurred_at is None
    assert parsed.timestamp_error is None
    assert fact.kind == "incoming_scram"
    assert fact.target == "you!"
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert fact.observed_name == "Talia Renn"


@pytest.mark.parametrize(
    "vector",
    [vector for vector in NAME_VECTORS if isinstance(vector["input"], str)],
    ids=lambda vector: vector["id"],
)
def test_tackle_raw_name_uses_shared_vectors_without_losing_the_effect(vector):
    who, line = _tackle_with_name(vector["input"])
    parsed = parsing.parse_line(line, who)
    assert len(parsed.facts) == 1
    assert parsed.facts[0].kind == "incoming_scram"
    assert parsed.facts[0].target == "you!"
    assert parsed.occurred_at == datetime.datetime(2025, 11, 14, 6, 41, 8, tzinfo=UTC)
    assert parsed.timestamp_error is None
    assert parsed.facts[0].observed_name == vector["normalized"]


@pytest.mark.parametrize(
    "raw_name, name, source",
    [
        ("Yoshi To", "Yoshi To", "Yoshi To [KVOS] Taranis"),
        ("Talia-Renn", "Talia-Renn", "Talia"),
        ("Talia - Renn", "Talia - Renn", "Talia"),
        ("Talia's Clone", "Talia's Clone", "Talia's Clone [KVOS] Taranis"),
        ("A  B", "A  B", "A B [KVOS] Taranis"),
        (" e\u0301 ", "é", "e\u0301 [KVOS] Taranis"),
        ("Talia [Other]", None, "Talia [Other] [KVOS] Taranis"),
        ("Talia] Renn", None, "Talia] Renn [KVOS] Taranis"),
        ("Talia [Renn", None, "Talia [Renn [KVOS] Taranis"),
        ("<b>Talia</b> Renn", None, "Talia Renn [KVOS] Taranis"),
        ("Talia</color><color=0xffffffff> Renn", None, "Talia Renn [KVOS] Taranis"),
    ],
)
def test_name_delimiters_never_rewrite_alert_sources(raw_name, name, source):
    who, line = _tackle_with_name(raw_name)
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == "incoming_scram"
    assert fact.source.encode("utf-8") == source.encode("utf-8")
    assert patterns.match_line(line, who) == patterns.Match("warp_scramble", source)
    assert patterns.is_likely_npc(fact.source) is False
    assert fact.observed_name == name


@pytest.mark.parametrize(
    "old, replacement",
    [
        ("Talia Renn [KVOS]", "Talia Renn"),
        ("[KVOS]", "[]"),
        ("[KVOS]", "[ ]"),
        ("[KVOS]", "[KVOS"),
        ("[KVOS]", "KVOS]"),
        ("[KVOS]", "[KV[OS]]"),
        (" [KVOS]", "[KVOS]"),
        ("<fontsize=12>", ""),
        ("[KVOS]</color>", "[KVOS]"),
        ("<color=0xfff0f000> Taranis</color>", " Taranis"),
        ("<color=0xfff0f000> Taranis</color>", "<color=0xfff0f000> </color>"),
        ("Taranis</color><color=0xffffffff></b>", "Taranis</b>"),
        ("Talia Renn [KVOS]", "Talia Renn [KVOS] Taranis"),
    ],
)
def test_malformed_separation_keeps_tackle_unnamed(old, replacement):
    who, line = _tackle_with_name("Talia Renn")
    (fact,) = parsing.parse_line(line.replace(old, replacement), who).facts
    assert fact.kind == "incoming_scram"
    assert fact.observed_name is None


def test_ambiguous_source_does_not_borrow_a_named_targets_markup():
    who, line = _fixture("npc_scramble.txt")
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.target == "Torvin Wexley [OXWLD] Drekavac"
    assert fact.source.encode("utf-8") == b"Emergent Preserver"
    assert fact.observed_name is None


@pytest.mark.parametrize(
    "source",
    [
        "Talia Renn [KVOS] Taranis",
        "<b>Talia Renn [KVOS] Taranis</b>",
        "<b>Talia Renn</b>",
    ],
)
def test_plain_or_bare_bold_source_is_not_enough_to_name_tackle(source):
    line = f"(combat) Warp scramble attempt from {source} to you!"
    (fact,) = parsing.parse_line(line, "Victim").facts
    assert fact.kind == "incoming_scram"
    assert fact.observed_name is None


@pytest.mark.parametrize("phrase", ["Warp disruption attempt", "Warp disruption zone"])
def test_separated_incoming_point_is_named(phrase):
    who, line = _tackle_with_name("Talia Renn")
    (fact,) = parsing.parse_line(
        line.replace("Warp scramble attempt", phrase), who
    ).facts
    assert fact.kind == "incoming_point"
    assert fact.observed_name == "Talia Renn"
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"


@pytest.mark.parametrize(
    "reader", ["Nobody Atall", "Talia Renn", "Torvin Wexley Jones"]
)
def test_named_tackle_does_not_emit_for_bystander_outgoing_or_wrong_victim(reader):
    _, source_line = _tackle_with_name("Talia Renn")
    victim, target_line = _fixture("npc_scramble.txt")
    line = source_line.removesuffix("you!") + target_line.split("</font>")[-1]
    (admitted,) = parsing.parse_line(line, victim).facts
    assert admitted.kind == "incoming_scram"
    assert admitted.observed_name == "Talia Renn"
    assert parsing.parse_line(line, reader).facts == ()
    assert patterns.match_line(line, reader) is None


@pytest.mark.parametrize(
    "stamp, error",
    [
        ("2026.02.30 12:34:56", "day is out of range for month"),
        ("2026.9.03 12:34:56", "malformed timestamp: 2026.9.03 12:34:56"),
    ],
)
def test_invalid_tackle_timestamp_preserves_named_fact_and_alert(stamp, error):
    who, line = _tackle_with_name("Talia Renn")
    line = line.replace("2025.11.14 06:41:08", stamp)
    parsed = parsing.parse_line(line, who)
    assert parsed.occurred_at is None
    assert parsed.timestamp_error == error
    (fact,) = parsed.facts
    assert fact.kind == "incoming_scram"
    assert fact.source.encode("utf-8") == b"Talia Renn [KVOS] Taranis"
    assert patterns.match_line(line, who) == patterns.Match(
        "warp_scramble", "Talia Renn [KVOS] Taranis"
    )
    assert patterns.is_likely_npc(fact.source) is False
    assert fact.observed_name == "Talia Renn"


@pytest.mark.parametrize(
    "fixture, phrase, kind, amount, source, event, npc",
    [
        (
            "player_damage_and_miss.txt",
            "><b>65</b>",
            "incoming_damage",
            65,
            "Bellrik Sanmar[VYKO](Vexor)",
            "combat",
            False,
        ),
        (
            "player_damage_and_miss.txt",
            "><b>83</b>",
            "incoming_damage",
            83,
            "Renar Duthie[VYKO](Vexor)",
            "combat",
            False,
        ),
        (
            "player_unresolved.txt",
            "><b>1230</b>",
            "incoming_damage",
            1230,
            "Doran Velk",
            "combat",
            False,
        ),
        (
            "npc_sleeper.txt",
            "><b>149</b>",
            "incoming_damage",
            149,
            "Sleepless Patroller",
            "combat",
            True,
        ),
        (
            "player_damage_and_miss.txt",
            "Hammerhead II belonging",
            "incoming_miss",
            None,
            "Hammerhead II belonging to Bellrik Sanmar",
            "combat",
            False,
        ),
        (
            "player_damage_and_miss.txt",
            "Hobgoblin II belonging",
            "incoming_miss",
            None,
            "Hobgoblin II belonging to Renar Duthie",
            "combat",
            False,
        ),
        (
            "npc_sleeper.txt",
            "misses you",
            "incoming_miss",
            None,
            "Sleepless Patroller",
            "combat",
            True,
        ),
        (
            "incoming_neut.txt",
            "237 GJ",
            "incoming_neut",
            237,
            "Doran Velk [BURN] Curse",
            None,
            False,
        ),
        (
            "incoming_neut.txt",
            "0xffe57f7f><b>0 GJ",
            "incoming_neut",
            0,
            "Doran Velk [BURN] Curse",
            None,
            False,
        ),
        (
            "outgoing_direct.txt",
            "(combat)",
            "outgoing_damage",
            299,
            "Caldari Navy Scourge Heavy Missile",
            None,
            False,
        ),
        (
            "outgoing_drone.txt",
            "(combat)",
            "outgoing_damage",
            22,
            "Acolyte II",
            None,
            False,
        ),
    ],
)
def test_non_tackle_fixture_sources_and_alert_decisions_remain_unchanged(
    fixture, phrase, kind, amount, source, event, npc
):
    who, line = _fixture_line(fixture, phrase)
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == kind
    assert fact.amount == amount
    assert fact.source.encode("utf-8") == source.encode("utf-8")
    expected_alert = patterns.Match(event, source) if event else None
    assert patterns.match_line(line, who) == expected_alert
    assert patterns.is_likely_npc(fact.source) is npc
    assert fact.observed_name is None


@pytest.mark.parametrize(
    "source, npc",
    [
        ("Farrowmark", False),
        ("Sleepless Patroller", True),
        ("Sleepless Patroller[BURN](Rifter)", False),
        ("Sleepless Patroller's Hobgoblin II", False),
        ("Élodie's Hobgoblin II", False),
    ],
)
@pytest.mark.parametrize("kind", ["incoming_damage", "incoming_miss"])
def test_drone_possessives_and_decorated_sources_preserve_alert_filtering(
    source, npc, kind
):
    if kind == "incoming_damage":
        who, line = _fixture_line("npc_sleeper.txt", "><b>149</b>")
        line = line.replace("Sleepless Patroller", source)
    else:
        who = "Torvin Wexley"
        line = f"[ 2025.11.14 01:15:37 ] (combat) {source} misses you completely"
    (fact,) = parsing.parse_line(line, who).facts
    assert fact.kind == kind
    assert fact.source.encode("utf-8") == source.encode("utf-8")
    assert patterns.match_line(line, who) == patterns.Match("combat", source)
    assert patterns.is_likely_npc(fact.source) is npc
    assert fact.observed_name is None


@pytest.mark.parametrize("amount", ["1,,299", "12,34", ",,,", ""])
def test_bad_amount_preserves_exact_damage_source_and_alert(amount):
    who, line = _incoming_with_amount(amount)
    parsed = parsing.parse_line(line, who)
    (fact,) = parsed.facts
    assert fact.kind == "incoming_damage"
    assert fact.amount is None
    assert fact.source.encode("utf-8") == b"Bellrik Sanmar[VYKO](Vexor)"
    assert patterns.match_line(line, who) == patterns.Match(
        "combat", "Bellrik Sanmar[VYKO](Vexor)"
    )
    assert patterns.is_likely_npc(fact.source) is False
    assert fact.observed_name is None
