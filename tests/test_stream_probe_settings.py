"""The probe identity settings (#335): ``preview.alerts.stream_probe``
-- guild_id and user_id, the non-secret half of the probe's
configuration. The bot token is a DPAPI credential, never settings
(the house rule: credentials never belong in settings)."""

from wingman import settings


def sp(raw):
    return settings.validated_preview(
        {"enabled": True, "alerts": {"stream_probe": raw}}
    )["alerts"]["stream_probe"]


def test_defaults_are_empty():
    fresh = settings.validated_preview({"enabled": True})
    assert fresh["alerts"]["stream_probe"] == {"guild_id": "", "user_id": ""}


def test_ids_persist_as_stripped_strings():
    assert sp({"guild_id": " 111 ", "user_id": " 222 "}) == {
        "guild_id": "111",
        "user_id": "222",
    }


def test_non_strings_fall_back_to_empty():
    assert sp({"guild_id": 111, "user_id": None}) == {"guild_id": "", "user_id": ""}


def test_a_malformed_section_falls_back_whole():
    assert sp("junk") == {"guild_id": "", "user_id": ""}


def test_the_section_survives_a_round_trip():
    once = sp({"guild_id": "111", "user_id": "222"})
    assert sp(once) == {"guild_id": "111", "user_id": "222"}
