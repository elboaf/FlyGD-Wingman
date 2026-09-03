"""Per-character authority lifecycle, authorization, and participant contracts."""

import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from wingman.eveauth import application
from wingman.eveauth import jwt as jwt_mod
from wingman.eveauth import loopback as loopback_mod
from wingman.eveauth import sso as sso_mod
from wingman.eveauth import state as state_mod
from wingman.eveauth.controller import AuthorityController, MutationResult

T0 = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


class InlineSpawn:
    def __call__(self, *, target, daemon=False):
        del daemon
        return SimpleNamespace(start=target)


class DeferredSpawn:
    def __init__(self):
        self.targets = []

    def __call__(self, *, target, daemon=False):
        del daemon
        self.targets.append(target)
        return SimpleNamespace(start=lambda: None)

    def run_next(self):
        self.targets.pop(0)()


class FakeAuthSso:
    def __init__(self, token_set=None):
        self.token_set = token_set or sso_mod.TokenSet(
            access_token="access-auth", refresh_token="refresh-auth", expires_in=1200
        )
        self.authorized_scopes = []

    def generate_pkce(self):
        return sso_mod.Pkce("state", "v" * 43, "challenge")

    def authorize_url(self, pkce, scopes):
        assert pkce.state == "state"
        self.authorized_scopes.append(frozenset(scopes))
        return "https://login.eveonline.com/authorize"

    def exchange_code(self, code, verifier):
        assert (code, verifier) == ("code", "v" * 43)
        return self.token_set

    def refresh_token(self, token):
        return sso_mod.TokenSet("access-refresh", "", 1200)


class FakeListener:
    def __init__(self, on_wait=None):
        self.on_wait = on_wait
        self.cancelled = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def wait(self, expected_state):
        assert expected_state == "state"
        if self.on_wait is not None:
            self.on_wait()
        if self.cancelled:
            raise loopback_mod.CallbackCancelled()
        return loopback_mod.Callback(code="code", error="")

    def cancel(self):
        self.cancelled = True


class Participant:
    def __init__(self, *, prepare=None, order=None, authority=None):
        self.prepare = prepare or MutationResult(True, True, "")
        self.order = order
        self.authority = authority
        self.prepared = []
        self.removed = []
        self.invalidated = []
        self.reconciled = []
        self.feature_lock = threading.RLock()
        self.lock_observation = None

    def prepare_forget(self, character_id):
        self.prepared.append(character_id)
        if self.order is not None:
            self.order.append("prepare")
        if self.authority is not None:
            gate = self.authority._lifecycle_gate(character_id)
            self.lock_observation = (
                gate._is_owned(),
                self.authority._lock._is_owned(),
            )
        with self.feature_lock:
            return self.prepare

    def authority_removed(self, character_id):
        self.removed.append(character_id)
        if self.order is not None:
            self.order.append("cleanup")

    def grant_invalidated(self, character_id):
        self.invalidated.append(character_id)

    def reconcile_characters(self, characters):
        self.reconciled.append(
            tuple(character.character_id for character in characters)
        )


def stored_character(
    character_id=42,
    *,
    scopes=application.SKILLS_SCOPES,
    owner_hash="owner-42",
):
    return state_mod.AuthorityCharacter(
        character_id=character_id,
        character_name=f"Character {character_id}",
        owner_hash=owner_hash,
        scopes=tuple(sorted(scopes)),
        authenticated_utc=T0,
        refresh_token_blob=f"refresh-{character_id}",
    )


def build(
    tmp_path,
    *,
    characters=None,
    sso=None,
    returned_identity=None,
    listener=None,
    saver=state_mod.save_authority,
    spawn=None,
    alert=None,
    wrapper=lambda token: token,
):
    authority_state = state_mod.AuthorityState(
        list(characters if characters is not None else [stored_character()])
    )
    path = tmp_path / "eve_authority.json"
    state_mod.save_authority(path, authority_state)
    alerts = []
    launched = []
    listener = listener or FakeListener()
    controller = AuthorityController(
        state_path=path,
        authority=authority_state,
        alert=alert or (lambda kind, title, body: alerts.append((kind, title, body))),
        changed=lambda: None,
        now=lambda: T0,
        sso=sso or FakeAuthSso(),
        validate_token=lambda token, **kwargs: (
            returned_identity
            or jwt_mod.EveIdentity(
                character_id=42,
                name="Aiga Otsolen",
                owner_hash="owner-42",
                scopes=frozenset(
                    kwargs["required_scopes"] or application.SKILLS_SCOPES
                ),
            )
        ),
        listener_factory=lambda **kwargs: listener,
        launch_browser=launched.append,
        spawn=spawn or InlineSpawn(),
        wrap_token=wrapper,
        unwrap_token=lambda blob: blob or None,
        save_authority=saver,
    )
    return controller, alerts, launched, listener


def test_each_character_has_one_distinct_reentrant_lifecycle_gate(tmp_path):
    authority, _, _, _ = build(
        tmp_path, characters=[stored_character(42), stored_character(43)]
    )

    gate_42 = authority._lifecycle_gate(42)
    assert gate_42 is authority._lifecycle_gate(42)
    assert gate_42 is not authority._lifecycle_gate(43)
    with gate_42, gate_42:
        assert True


def test_access_token_can_reenter_an_active_lifecycle_lease(tmp_path):
    authority, _, _, _ = build(tmp_path)

    with authority.lifecycle(42, application.SKILLS) as lease:
        result = authority.access_token(42, application.SKILLS)

    assert lease.character.character_id == 42
    assert lease.generation == 0
    assert result.token == "access-refresh"


def test_lifecycle_refuses_a_capability_missing_from_the_grant(tmp_path):
    authority, _, _, _ = build(tmp_path)

    with (
        pytest.raises(PermissionError, match="not enabled"),
        authority.lifecycle(42, application.FITTINGS),
    ):
        pass


def test_forget_waits_for_an_active_lifecycle_lease(tmp_path):
    authority, _, _, _ = build(tmp_path)
    lease_entered = threading.Event()
    release_lease = threading.Event()
    forgotten = threading.Event()

    def hold_lease():
        with authority.lifecycle(42, application.SKILLS):
            lease_entered.set()
            assert release_lease.wait(timeout=2)

    def forget():
        authority.forget(42)
        forgotten.set()

    holder = threading.Thread(target=hold_lease)
    remover = threading.Thread(target=forget)
    holder.start()
    assert lease_entered.wait(timeout=2)
    remover.start()
    assert not forgotten.wait(timeout=0.1)
    release_lease.set()
    holder.join(timeout=2)
    remover.join(timeout=2)

    assert forgotten.is_set()
    assert authority.character(42) is None


def test_every_prepare_runs_and_a_refusal_prevents_authority_removal(tmp_path):
    authority, _, _, _ = build(tmp_path)
    refusing = Participant(
        prepare=MutationResult(False, True, "Reconcile unknown writes first.")
    )
    ready = Participant()
    authority.register_participant(refusing)
    authority.register_participant(ready)

    result = authority.forget(42)

    assert result == MutationResult(False, False, "Reconcile unknown writes first.")
    assert authority.character(42) is not None
    assert refusing.prepared == ready.prepared == [42]
    assert refusing.removed == ready.removed == []


def test_authority_save_failure_causes_no_participant_cleanup(tmp_path):
    def refuse_save(path, authority_state):
        raise OSError("disk full")

    authority, _, _, _ = build(tmp_path, saver=refuse_save)
    participant = Participant()
    authority.register_participant(participant)

    result = authority.forget(42)

    assert result.applied is False and result.persisted is False
    assert authority.character(42) is not None
    assert participant.prepared == [42]
    assert participant.removed == []


def test_participant_cleanup_follows_persisted_authority_removal(tmp_path):
    order = []

    def recording_save(path, authority_state):
        assert authority_state.characters == []
        order.append("persist")
        state_mod.save_authority(path, authority_state)

    authority, _, _, _ = build(tmp_path, saver=recording_save)
    participant = Participant(order=order)
    authority.register_participant(participant)

    result = authority.forget(42)

    assert result == MutationResult(True, True, "")
    assert order == ["prepare", "persist", "cleanup"]
    assert participant.removed == [42]


def test_forget_retries_cleanup_when_authority_was_already_removed(tmp_path):
    authority, _, _, _ = build(tmp_path)
    participant = Participant()
    authority.register_participant(participant)
    authority.forget(42)
    participant.removed.clear()

    result = authority.forget(42)

    assert result == MutationResult(True, True, "")
    assert participant.removed == [42]


def test_participant_hooks_run_lifecycle_then_feature_without_authority_lock(tmp_path):
    authority, _, _, _ = build(tmp_path)
    participant = Participant(authority=authority)
    authority.register_participant(participant)

    authority.forget(42)

    assert participant.lock_observation == (True, False)


def test_register_participant_reconciles_against_immutable_roster(tmp_path):
    authority, _, _, _ = build(
        tmp_path, characters=[stored_character(42), stored_character(43)]
    )
    participant = Participant()

    authority.register_participant(participant)

    assert participant.reconciled == [(42, 43)]


def test_definitive_grant_invalidation_notifies_every_participant(tmp_path):
    error = sso_mod.OAuthError(400, "invalid_grant", "revoked")

    class RefusingSso(FakeAuthSso):
        def refresh_token(self, token):
            raise error

    authority, _, _, _ = build(tmp_path, sso=RefusingSso())
    participant = Participant()
    authority.register_participant(participant)

    authority.access_token(42, application.SKILLS)

    assert participant.invalidated == [42]


def test_enable_fittings_requests_union_for_the_exact_character(tmp_path):
    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    fake_sso = FakeAuthSso()
    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=frozenset(requested),
    )
    authority, alerts, launched, _ = build(
        tmp_path, sso=fake_sso, returned_identity=returned
    )

    result = authority.enable_capability(42, application.FITTINGS)

    assert result.applied is True
    assert fake_sso.authorized_scopes == [frozenset(requested)]
    assert authority.capability_status(42, application.FITTINGS) == "enabled"
    assert launched == ["https://login.eveonline.com/authorize"]
    assert alerts == []


def test_enable_capability_rejects_a_different_returned_character(tmp_path):
    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    returned = jwt_mod.EveIdentity(
        character_id=99,
        name="Wrong Character",
        owner_hash="owner-99",
        scopes=frozenset(requested),
    )
    authority, alerts, _, _ = build(tmp_path, returned_identity=returned)

    authority.enable_capability(42, application.FITTINGS)

    assert authority.capability_status(42, application.FITTINGS) == "enable"
    assert any("different character" in body.lower() for _, _, body in alerts)


def test_late_capability_callback_cannot_resurrect_a_forgotten_character(tmp_path):
    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=frozenset(requested),
    )
    authority = None

    def forget_during_wait():
        result = authority.forget(42)
        assert result.applied is True

    wrapped = []
    listener = FakeListener(on_wait=forget_during_wait)
    authority, alerts, _, _ = build(
        tmp_path,
        returned_identity=returned,
        listener=listener,
        wrapper=lambda token: wrapped.append(token) or token,
    )

    authority.enable_capability(42, application.FITTINGS)

    assert authority.character(42) is None
    assert wrapped == [], "stale authorization must be rejected before token handling"
    assert any("no longer" in body.lower() for _, _, body in alerts)


def test_browser_and_loopback_wait_hold_neither_authority_nor_lifecycle_lock(tmp_path):
    authority = None
    observations = []

    def inspect_locks():
        acquired = threading.Event()

        def acquire_gate():
            with authority._lifecycle_gate(42):
                acquired.set()

        probe = threading.Thread(target=acquire_gate)
        probe.start()
        probe.join(timeout=1)
        observations.append((authority._lock._is_owned(), acquired.is_set()))

    listener = FakeListener(on_wait=inspect_locks)
    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=frozenset(requested),
    )
    authority, _, _, _ = build(tmp_path, returned_identity=returned, listener=listener)

    authority.enable_capability(42, application.FITTINGS)

    assert observations == [(False, True)]


def test_auth_failure_alerts_run_without_the_authority_document_lock(tmp_path):
    authority = None
    lock_observations = []

    def observe_alert(kind, title, body):
        del kind, title, body
        lock_observations.append(authority._lock._is_owned())

    def refuse_save(path, authority_state):
        raise OSError("disk full")

    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=frozenset(requested),
    )
    authority, _, _, _ = build(
        tmp_path,
        returned_identity=returned,
        saver=refuse_save,
        alert=observe_alert,
    )

    authority.enable_capability(42, application.FITTINGS)

    assert lock_observations == [False]


def test_upgrade_save_failure_keeps_previous_skills_authority(tmp_path):
    def refuse_save(path, authority_state):
        raise OSError("disk full")

    requested = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=frozenset(requested),
    )
    authority, alerts, _, _ = build(
        tmp_path, returned_identity=returned, saver=refuse_save
    )

    authority.enable_capability(42, application.FITTINGS)

    assert authority.capability_status(42, application.SKILLS) == "enabled"
    assert authority.capability_status(42, application.FITTINGS) == "enable"
    assert any("not saved" in body.lower() for _, _, body in alerts)


def test_authenticate_skills_requests_only_skills_and_adds_returned_character(tmp_path):
    fake_sso = FakeAuthSso()
    returned = jwt_mod.EveIdentity(
        character_id=77,
        name="New Character",
        owner_hash="owner-77",
        scopes=application.SKILLS_SCOPES,
    )
    authority, alerts, _, _ = build(
        tmp_path,
        characters=[],
        sso=fake_sso,
        returned_identity=returned,
    )

    result = authority.authenticate_skills()

    assert result.applied is True
    assert fake_sso.authorized_scopes == [application.SKILLS_SCOPES]
    assert authority.capability_status(77, application.SKILLS) == "enabled"
    assert authority.capability_status(77, application.FITTINGS) == "enable"
    assert alerts == []


def test_forget_generation_rejects_late_work_even_after_same_id_is_added(tmp_path):
    authority, _, _, _ = build(tmp_path)
    original_generation = authority.character(42).generation
    authority.forget(42)

    returned = jwt_mod.EveIdentity(
        character_id=42,
        name="Aiga Otsolen",
        owner_hash="owner-42",
        scopes=application.SKILLS_SCOPES,
    )
    authority._validate_token = lambda token, **kwargs: returned
    authority.authenticate_skills()

    assert authority.character(42).generation == original_generation + 1


def test_auth_is_globally_single_flight_and_cancel_reaches_listener(tmp_path):
    spawn = DeferredSpawn()
    authority, alerts, _, listener = build(tmp_path, spawn=spawn)

    first = authority.authenticate_skills()
    second = authority.authenticate_skills()
    authority.cancel_auth()

    assert first.applied is True
    assert second.applied is False
    assert "already" in second.error.lower()
    assert listener.cancelled is False, "listener is not bound until the worker starts"
    spawn.run_next()
    assert listener.cancelled is True, "an early cancellation must reach a later bind"
    assert any("already" in title.lower() for _, title, _ in alerts)


def test_shutdown_refuses_new_token_work(tmp_path):
    authority, _, _, _ = build(tmp_path)

    authority.shutdown()
    result = authority.access_token(42, application.SKILLS)

    assert result.token is None
    assert result.grant_invalidated is False
    assert "shutting down" in result.error.lower()


def test_shutdown_cancels_a_bound_listener_without_raising(tmp_path):
    authority = None

    def stop_during_wait():
        authority.shutdown()

    listener = FakeListener(on_wait=stop_during_wait)
    authority, alerts, _, _ = build(tmp_path, listener=listener)

    authority.authenticate_skills()

    assert listener.cancelled is True
    assert alerts == []
