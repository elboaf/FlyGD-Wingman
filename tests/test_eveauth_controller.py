"""Shared EVE authority capability and token-refresh contracts."""

import inspect
import threading
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from wingman import eveauth
from wingman.eveauth import application
from wingman.eveauth import jwt as jwt_mod
from wingman.eveauth import sso as sso_mod
from wingman.eveauth import state as state_mod
from wingman.eveauth.controller import (
    AccessTokenResult,
    AuthorityController,
    LifecycleLease,
    MutationResult,
)

T0 = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


class FakeSso:
    def __init__(self, *, token_set=None, error=None, wait=None):
        self.token_set = token_set or sso_mod.TokenSet(
            access_token="access-new", refresh_token="refresh-new", expires_in=1200
        )
        self.error = error
        self.wait = wait
        self.refreshes = []

    def refresh_token(self, token):
        self.refreshes.append(token)
        if self.wait is not None:
            self.wait()
        if self.error is not None:
            raise self.error
        return self.token_set


class Validator:
    def __init__(self, identity):
        self.identity = identity
        self.calls = []

    def __call__(self, token, **kwargs):
        self.calls.append((token, kwargs))
        return self.identity


def identity(
    character_id=42,
    *,
    owner_hash="owner-42",
    scopes=application.SKILLS_SCOPES,
):
    return jwt_mod.EveIdentity(
        character_id=character_id,
        name="Aiga Otsolen",
        owner_hash=owner_hash,
        scopes=frozenset(scopes),
    )


def persistent_character(
    character_id=42,
    *,
    owner_hash="owner-42",
    scopes=application.SKILLS_SCOPES,
    needs_reauth=False,
    token="refresh-old",
):
    return state_mod.AuthorityCharacter(
        character_id=character_id,
        character_name="Aiga Otsolen",
        owner_hash=owner_hash,
        scopes=tuple(sorted(scopes)),
        authenticated_utc=T0,
        needs_reauth=needs_reauth,
        refresh_token_blob=token,
    )


def build_authority(
    tmp_path,
    *,
    characters=None,
    fake_sso=None,
    validator=None,
    saver=state_mod.save_authority,
    wrapper=lambda token: token,
):
    authority_state = state_mod.AuthorityState(
        list(characters if characters is not None else [persistent_character()])
    )
    path = tmp_path / "eve_authority.json"
    state_mod.save_authority(path, authority_state)
    alerts = []
    changed = []
    controller = AuthorityController(
        state_path=path,
        authority=authority_state,
        alert=lambda kind, title, body: alerts.append((kind, title, body)),
        changed=lambda: changed.append(True),
        now=lambda: T0,
        sso=fake_sso or FakeSso(),
        validate_token=validator or Validator(identity()),
        wrap_token=wrapper,
        unwrap_token=lambda blob: blob or None,
        save_authority=saver,
    )
    return controller, alerts, changed


def test_skills_capability_accepts_a_skills_only_grant(tmp_path):
    authority, _, _ = build_authority(tmp_path)

    assert authority.capability_status(42, application.SKILLS) == "enabled"
    assert authority.capability_status(42, application.FITTINGS) == "enable"


def test_capability_is_derived_from_validated_claims_not_requested_scopes(tmp_path):
    granted = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    validator = Validator(identity(scopes=granted))
    authority, _, _ = build_authority(
        tmp_path,
        characters=[persistent_character(scopes=granted)],
        validator=validator,
    )

    result = authority.access_token(42, application.FITTINGS)

    assert result.token == "access-new"
    assert authority.capability_status(42, application.FITTINGS) == "enabled"
    assert validator.calls[0][1]["required_scopes"] == frozenset()
    assert authority.character(42).scopes == tuple(sorted(granted))


def test_refresh_claim_subset_disables_only_the_missing_capability(tmp_path):
    granted = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    authority, _, _ = build_authority(
        tmp_path,
        characters=[persistent_character(scopes=granted)],
        validator=Validator(identity(scopes=application.SKILLS_SCOPES)),
    )

    result = authority.access_token(42, application.FITTINGS)

    assert result.token is None
    assert result.grant_invalidated is False
    assert authority.capability_status(42, application.SKILLS) == "enabled"
    assert authority.capability_status(42, application.FITTINGS) == "enable"
    assert authority.character(42).needs_reauth is False


def test_missing_fittings_claim_does_not_invalidate_skills_grant(tmp_path):
    authority, _, _ = build_authority(tmp_path)

    result = authority.access_token(42, application.FITTINGS)

    assert result.token is None
    assert result.grant_invalidated is False
    assert authority.capability_status(42, application.SKILLS) == "enabled"
    assert authority.capability_status(42, application.FITTINGS) == "enable"
    assert authority.character(42).needs_reauth is False


def test_invalid_grant_globally_invalidates_the_grant(tmp_path):
    error = sso_mod.OAuthError(400, "invalid_grant", "revoked")
    authority, _, _ = build_authority(tmp_path, fake_sso=FakeSso(error=error))

    result = authority.access_token(42, application.SKILLS)

    assert result.grant_invalidated is True
    assert result.reason == "invalid_grant"
    assert authority.character(42).needs_reauth is True
    assert authority.capability_status(42, application.SKILLS) == "reauthenticate"


def test_untrusted_identity_mismatch_error_code_is_not_global_invalidation(tmp_path):
    error = sso_mod.OAuthError(400, "identity_mismatch", "untrusted response body")
    authority, _, _ = build_authority(tmp_path, fake_sso=FakeSso(error=error))

    result = authority.access_token(42, application.SKILLS)

    assert result.grant_invalidated is False
    assert authority.character(42).needs_reauth is False


def test_validated_character_mismatch_globally_invalidates_the_grant(tmp_path):
    authority, _, _ = build_authority(
        tmp_path, validator=Validator(identity(character_id=99))
    )

    result = authority.access_token(42, application.SKILLS)

    assert result.grant_invalidated is True
    assert result.reason == "identity_mismatch"
    assert authority.character(42).needs_reauth is True


def test_validated_owner_mismatch_globally_invalidates_the_grant(tmp_path):
    authority, _, _ = build_authority(
        tmp_path, validator=Validator(identity(owner_hash="new-owner"))
    )

    result = authority.access_token(42, application.SKILLS)

    assert result.grant_invalidated is True
    assert result.reason == "owner_changed"
    assert authority.character(42).needs_reauth is True


@pytest.mark.parametrize(
    ("stored_owner", "claim_owner"),
    [("", "new-owner"), ("owner-42", "")],
)
def test_blank_owner_claim_on_either_side_is_not_a_mismatch(
    tmp_path, stored_owner, claim_owner
):
    authority, _, _ = build_authority(
        tmp_path,
        characters=[persistent_character(owner_hash=stored_owner)],
        validator=Validator(identity(owner_hash=claim_owner)),
    )

    result = authority.access_token(42, application.SKILLS)

    assert result.token == "access-new"
    assert result.grant_invalidated is False


def test_token_rotation_is_saved_and_reused(tmp_path):
    sso = FakeSso()
    authority, _, _ = build_authority(tmp_path, fake_sso=sso)

    first = authority.access_token(42, application.SKILLS)
    second = authority.access_token(42, application.SKILLS)

    persisted, warnings = state_mod.load_authority(tmp_path / "eve_authority.json")
    assert warnings == ()
    assert first.token == second.token == "access-new"
    assert sso.refreshes == ["refresh-old"]
    persisted_character = next(
        character for character in persisted.characters if character.character_id == 42
    )
    assert persisted_character.refresh_token_blob == "refresh-new"


def test_omitted_rotated_token_keeps_the_previous_refresh_token(tmp_path):
    sso = FakeSso(
        token_set=sso_mod.TokenSet(
            access_token="access-new", refresh_token="", expires_in=1200
        )
    )
    authority, _, _ = build_authority(tmp_path, fake_sso=sso)

    result = authority.access_token(42, application.SKILLS)

    assert result.token == "access-new"
    stored = next(
        character
        for character in authority._state.characters
        if character.character_id == 42
    )
    assert stored.refresh_token_blob == "refresh-old"


def test_rotation_save_failure_keeps_new_token_in_memory_and_reports_risk(tmp_path):
    save_calls = []

    def refuse_save(path, authority_state):
        save_calls.append((path, authority_state))
        raise OSError("disk full")

    sso = FakeSso()
    authority, _, _ = build_authority(tmp_path, fake_sso=sso, saver=refuse_save)

    first = authority.access_token(42, application.SKILLS)
    second = authority.access_token(42, application.SKILLS, rejected_token="access-new")

    assert first.token == "access-new"
    assert first.error == "The rotated EVE token is live but could not be saved."
    assert second.token == "access-new"
    assert sso.refreshes == ["refresh-old", "refresh-new"]
    stored = next(
        character
        for character in authority._state.characters
        if character.character_id == 42
    )
    assert stored.refresh_token_blob == "refresh-new"
    assert len(save_calls) == 2


def test_rotation_wrap_failure_keeps_new_raw_token_in_memory(tmp_path):
    def refuse_wrap(token):
        raise OSError(f"cannot protect {len(token)} characters")

    sso = FakeSso()
    authority, _, _ = build_authority(tmp_path, fake_sso=sso, wrapper=refuse_wrap)

    first = authority.access_token(42, application.SKILLS)
    second = authority.access_token(42, application.SKILLS, rejected_token="access-new")

    assert first.token == second.token == "access-new"
    assert first.error == "The rotated EVE token is live but could not be saved."
    assert sso.refreshes == ["refresh-old", "refresh-new"]


def test_omitted_rotation_after_wrap_failure_keeps_live_raw_token(tmp_path):
    wrap_attempts = []

    def fail_first_wrap(token):
        wrap_attempts.append(token)
        if len(wrap_attempts) == 1:
            raise OSError("DPAPI unavailable")
        return token

    sso = FakeSso()
    authority, _, _ = build_authority(tmp_path, fake_sso=sso, wrapper=fail_first_wrap)
    first = authority.access_token(42, application.SKILLS)
    sso.token_set = sso_mod.TokenSet("access-next", "", 1200)

    second = authority.access_token(42, application.SKILLS, rejected_token=first.token)
    third = authority.access_token(42, application.SKILLS, rejected_token=second.token)

    assert first.error == "The rotated EVE token is live but could not be saved."
    assert second.token == third.token == "access-next"
    assert sso.refreshes == ["refresh-old", "refresh-new", "refresh-new"]
    assert authority.capability_status(42, application.SKILLS) == "enabled"


def test_concurrent_consumers_share_one_token_refresh(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def pause_refresh():
        entered.set()
        assert release.wait(timeout=2)

    sso = FakeSso(wait=pause_refresh)
    authority, _, _ = build_authority(tmp_path, fake_sso=sso)
    results = []

    first = threading.Thread(
        target=lambda: results.append(authority.access_token(42, application.SKILLS))
    )
    second = threading.Thread(
        target=lambda: results.append(authority.access_token(42, application.SKILLS))
    )
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert [result.token for result in results] == ["access-new", "access-new"]
    assert sso.refreshes == ["refresh-old"]


def test_endpoint_status_has_no_authority_mutation_contract(tmp_path):
    authority, _, _ = build_authority(tmp_path)

    public_methods = {
        name
        for name, value in inspect.getmembers(type(authority), inspect.isfunction)
        if not name.startswith("_")
    }

    assert "record_operation_error" not in public_methods
    assert authority.character(42).needs_reauth is False


def test_eveauth_package_exports_the_shared_authority_contract():
    assert eveauth.AuthorityController is AuthorityController
    assert eveauth.AccessTokenResult is AccessTokenResult
    assert eveauth.MutationResult is MutationResult
    assert eveauth.LifecycleLease is LifecycleLease
    assert eveauth.SKILLS == application.SKILLS
    assert eveauth.FITTINGS == application.FITTINGS


def test_controller_results_and_leases_are_immutable():
    legacy_result = AccessTokenResult("token", "", False)
    assert legacy_result.reason == ""
    values = [
        legacy_result,
        MutationResult(True, True, ""),
        LifecycleLease(None, application.SKILLS, 0),
    ]

    for value in values:
        with pytest.raises(FrozenInstanceError):
            value.error = "changed"
