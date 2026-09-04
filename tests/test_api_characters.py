"""Shared EVE character authority bridge methods."""

from unittest.mock import Mock

import pytest

from tests.test_api import make_api
from wingman.eveauth.controller import AuthorizationCommandResult, MutationResult


def test_character_state_is_display_safe(tmp_path):
    authority = Mock()
    authority.management_state.return_value = {
        "authorization_activity": "idle",
        "authorization_notice": "",
        "characters": [
            {
                "character_id": 2,
                "character_name": "Aiga Otsolen",
                "authenticated_utc": "2026-09-04T12:00:00+00:00",
                "skills": "authorized",
                "fittings": "sign_in",
                "needs_reauth": False,
                "persistence_error": "",
            }
        ],
    }
    api = make_api(tmp_path, authority=authority)

    payload = api.eve_characters_state()

    assert payload["available"] is True
    assert payload["auth_configured"] is True
    encoded = repr(payload).lower()
    for forbidden in (
        "refresh_token",
        "access_token",
        "owner_hash",
        "scopes",
        "claims",
        "generation",
    ):
        assert forbidden not in encoded


def test_character_state_has_a_safe_unavailable_fallback(tmp_path):
    api = make_api(
        tmp_path,
        authority_warnings=["Restore eve_authority.json, then restart Wingman."],
    )

    assert api.eve_characters_state() == {
        "available": False,
        "auth_configured": True,
        "authorization_activity": "idle",
        "authorization_notice": "",
        "characters": [],
        "warnings": ["Restore eve_authority.json, then restart Wingman."],
    }


def test_character_state_bounds_warning_count_and_text(tmp_path):
    authority = Mock()
    authority.management_state.return_value = {
        "authorization_activity": "idle",
        "authorization_notice": "",
        "characters": [],
    }
    warnings = [f"{index:02d}-" + ("w" * 600) for index in range(25)]
    api = make_api(tmp_path, authority=authority, authority_warnings=warnings)

    payload = api.eve_characters_state()

    assert len(payload["warnings"]) == 20
    assert payload["warnings"][0] == warnings[0][:500]
    assert payload["warnings"][-1] == warnings[19][:500]
    assert all(len(warning) == 500 for warning in payload["warnings"])
    assert warnings[20][:500] not in payload["warnings"]


def test_authenticate_preserves_acceptance_without_claiming_completion(tmp_path):
    authority = Mock()
    authority.start_full_authorization.return_value = AuthorizationCommandResult(
        True, ""
    )
    api = make_api(tmp_path, authority=authority)

    assert api.eve_characters_authenticate() == {"accepted": True, "error": ""}


def test_cancel_auth_preserves_a_lost_race_result(tmp_path):
    authority = Mock()
    authority.cancel_authorization.return_value = AuthorizationCommandResult(
        False, "The EVE sign-in already finished."
    )
    api = make_api(tmp_path, authority=authority)

    assert api.eve_characters_cancel_auth() == {
        "accepted": False,
        "error": "The EVE sign-in already finished.",
    }


@pytest.mark.parametrize(
    ("method_name", "result"),
    [
        (
            "eve_characters_authenticate",
            AuthorizationCommandResult(True, "a" * 700),
        ),
        (
            "eve_characters_cancel_auth",
            AuthorizationCommandResult(False, "c" * 700),
        ),
        (
            "eve_characters_forget",
            MutationResult(True, False, "f" * 700),
        ),
    ],
)
def test_character_commands_bound_returned_errors(tmp_path, method_name, result):
    authority = Mock()
    if method_name == "eve_characters_authenticate":
        authority.start_full_authorization.return_value = result
        payload = make_api(tmp_path, authority=authority).eve_characters_authenticate()
    elif method_name == "eve_characters_cancel_auth":
        authority.cancel_authorization.return_value = result
        payload = make_api(tmp_path, authority=authority).eve_characters_cancel_auth()
    else:
        authority.forget.return_value = result
        payload = make_api(tmp_path, authority=authority).eve_characters_forget(42)

    assert payload["error"] == result.error[:500]
    assert len(payload["error"]) == 500


def test_forget_preserves_all_three_result_fields(tmp_path):
    authority = Mock()
    authority.forget.return_value = MutationResult(
        True, False, "Feature cleanup is incomplete."
    )
    api = make_api(tmp_path, authority=authority)

    assert api.eve_characters_forget(42) == {
        "applied": True,
        "persisted": False,
        "error": "Feature cleanup is incomplete.",
    }
