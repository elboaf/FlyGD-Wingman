"""Per-character authority lifecycle, authorization, and participant contracts."""

import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from wingman.eveauth import CleanupVerification, application
from wingman.eveauth import jwt as jwt_mod
from wingman.eveauth import loopback as loopback_mod
from wingman.eveauth import sso as sso_mod
from wingman.eveauth import state as state_mod
from wingman.eveauth.controller import (
    AuthorityController,
    AuthorizationCommandResult,
    MutationResult,
)

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


class Gate:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def wait(self):
        self.entered.set()
        assert self.release.wait(timeout=2)

    def open(self):
        self.release.set()


class ProbeGate:
    def __init__(self):
        self._lock = threading.RLock()
        self.entered = threading.Event()
        self.release = threading.Event()

    def __enter__(self):
        if not self._lock._is_owned():
            self.entered.set()
            assert self.release.wait(timeout=2)
        self._lock.acquire()
        return self

    def __exit__(self, *exc):
        self._lock.release()
        return

    def open(self):
        self.release.set()

    def _is_owned(self):
        return self._lock._is_owned()


class FakeAuthSso:
    def __init__(self, token_set=None, *, exchange_gate=None, exchange_error=None):
        self.token_set = token_set or sso_mod.TokenSet(
            access_token="access-auth", refresh_token="refresh-auth", expires_in=1200
        )
        self.exchange_gate = exchange_gate
        self.exchange_error = exchange_error
        self.authorized_scopes = []

    def generate_pkce(self):
        return sso_mod.Pkce("state", "v" * 43, "challenge")

    def authorize_url(self, pkce, scopes):
        assert pkce.state == "state"
        self.authorized_scopes.append(frozenset(scopes))
        return "https://login.eveonline.com/authorize"

    def exchange_code(self, code, verifier):
        assert (code, verifier) == ("code", "v" * 43)
        if self.exchange_gate is not None:
            self.exchange_gate.wait()
        if self.exchange_error is not None:
            raise self.exchange_error
        return self.token_set

    def refresh_token(self, token):
        return sso_mod.TokenSet("access-refresh", "", 1200)

    def finish(self):
        if self.exchange_gate is not None:
            self.exchange_gate.open()


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
    def __init__(
        self,
        *,
        prepare=None,
        cleanup=None,
        verification=None,
        reconcile_error=None,
        order=None,
        authority=None,
    ):
        self.prepare = (
            prepare if prepare is not None else MutationResult(True, True, "")
        )
        self.cleanup = (
            cleanup if cleanup is not None else MutationResult(True, True, "")
        )
        self.verification = (
            verification
            if verification is not None
            else CleanupVerification(True, frozenset())
        )
        self.reconcile_error = reconcile_error
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
        with self.feature_lock:
            if isinstance(self.cleanup, Exception):
                raise self.cleanup
            return self.cleanup

    def grant_invalidated(self, character_id):
        self.invalidated.append(character_id)

    def reconcile_characters(self, characters):
        self.reconciled.append(
            tuple(character.character_id for character in characters)
        )
        if self.reconcile_error is not None:
            raise self.reconcile_error
        return self.verification


def full_identity(
    character_id=42,
    *,
    name="Aiga Otsolen",
    owner_hash="owner-42",
    scopes=application.FULL_AUTH_SCOPES,
):
    return jwt_mod.EveIdentity(
        character_id=character_id,
        name=name,
        owner_hash=owner_hash,
        scopes=frozenset(scopes),
    )


def stored_character(
    character_id=42,
    *,
    scopes=application.SKILLS_SCOPES,
    owner_hash="owner-42",
    needs_reauth=False,
):
    return state_mod.AuthorityCharacter(
        character_id=character_id,
        character_name=f"Character {character_id}",
        owner_hash=owner_hash,
        scopes=tuple(sorted(scopes)),
        authenticated_utc=T0,
        needs_reauth=needs_reauth,
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
    changed=None,
    validator=None,
    wrapper=lambda token: token,
    unwrapper=lambda blob: blob or None,
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
        changed=changed or (lambda: None),
        now=lambda: T0,
        sso=sso or FakeAuthSso(),
        validate_token=validator
        or (
            lambda token, **kwargs: (
                returned_identity
                or jwt_mod.EveIdentity(
                    character_id=42,
                    name="Aiga Otsolen",
                    owner_hash="owner-42",
                    scopes=frozenset(
                        kwargs["required_scopes"] or application.SKILLS_SCOPES
                    ),
                )
            )
        ),
        listener_factory=lambda **kwargs: listener,
        launch_browser=launched.append,
        spawn=spawn or InlineSpawn(),
        wrap_token=wrapper,
        unwrap_token=unwrapper,
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
    refusing = Participant(prepare=MutationResult(False, True, "Reconcile first."))
    ready = Participant()
    authority.register_participant(application.SKILLS, refusing)
    authority.register_participant(application.FITTINGS, ready)

    result = authority.forget(42)

    assert result == MutationResult(False, False, "Reconcile first.")
    assert authority.character(42) is not None
    assert refusing.prepared == ready.prepared == [42]
    assert refusing.removed == ready.removed == []


def test_authority_save_failure_causes_no_participant_cleanup(tmp_path):
    def refuse_save(path, authority_state):
        raise OSError("disk full")

    authority, _, _, _ = build(tmp_path, saver=refuse_save)
    participant = Participant()
    authority.register_participant(application.SKILLS, participant)

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
    authority.register_participant(application.SKILLS, participant)
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.forget(42)

    assert result == MutationResult(True, True, "")
    assert order == ["prepare", "persist", "cleanup"]
    assert participant.removed == [42]


def test_forget_reports_partial_cleanup_when_a_participant_cannot_save(tmp_path):
    authority, _, _, _ = build(tmp_path)
    partial = Participant(
        cleanup=MutationResult(True, False, "Could not save Skills cleanup.")
    )
    complete = Participant()
    authority.register_participant(application.SKILLS, partial)
    authority.register_participant(application.FITTINGS, complete)

    result = authority.forget(42)

    assert result.applied is True
    assert result.persisted is False
    assert "cleanup" in result.error.lower()
    assert authority.character(42) is None
    assert partial.removed == complete.removed == [42]


def test_forget_reports_partial_cleanup_when_a_required_slot_is_absent(tmp_path):
    authority, _, _, _ = build(tmp_path)
    authority.register_participant(application.SKILLS, Participant())

    result = authority.forget(42)

    assert result == MutationResult(True, False, "Fittings cleanup is unavailable.")
    assert authority.character(42) is None
    assert authority._cleanup_verification[application.FITTINGS] == CleanupVerification(
        False,
        frozenset({42}),
        "Fittings cleanup is unavailable.",
    )


def test_forget_retries_cleanup_when_authority_was_already_removed(tmp_path):
    authority, _, _, _ = build(tmp_path)
    participant = Participant()
    other = Participant()
    authority.register_participant(application.SKILLS, participant)
    authority.register_participant(application.FITTINGS, other)
    authority.forget(42)
    participant.removed.clear()
    other.removed.clear()

    result = authority.forget(42)

    assert result == MutationResult(True, True, "")
    assert participant.removed == [42]
    assert other.removed == [42]


def test_participant_hooks_run_lifecycle_then_feature_without_authority_lock(tmp_path):
    authority, _, _, _ = build(tmp_path)
    participant = Participant(authority=authority)
    authority.register_participant(application.SKILLS, participant)

    authority.forget(42)

    assert participant.lock_observation == (True, False)


def test_register_participant_reconciles_against_immutable_roster(tmp_path):
    authority, _, _, _ = build(
        tmp_path, characters=[stored_character(42), stored_character(43)]
    )
    participant = Participant()

    authority.register_participant(application.SKILLS, participant)

    assert participant.reconciled == [(42, 43)]


def test_register_participant_refuses_an_unknown_slot(tmp_path):
    authority, _, _, _ = build(tmp_path)

    with pytest.raises(ValueError, match="Unknown EVE capability"):
        authority.register_participant("bookmarks", Participant())


def test_register_participant_refuses_a_duplicate_slot(tmp_path):
    authority, _, _, _ = build(tmp_path)
    authority.register_participant(application.SKILLS, Participant())

    with pytest.raises(ValueError, match="already registered"):
        authority.register_participant(application.SKILLS, Participant())


def test_register_participant_turns_reconcile_exceptions_into_unverified_cleanup(
    tmp_path,
):
    authority, _, _, _ = build(tmp_path)
    authority.register_participant(application.FITTINGS, Participant())

    verification = authority.register_participant(
        application.SKILLS,
        Participant(reconcile_error=OSError("disk")),
    )

    assert verification == CleanupVerification(
        False,
        frozenset(),
        "Skills cleanup is unavailable.",
    )
    assert authority._verify_unknown_character(77) == MutationResult(
        False,
        False,
        "Skills cleanup is unavailable.",
    )


def test_cleanup_exception_preserves_prior_blocked_ids(tmp_path):
    authority, _, _, _ = build(tmp_path)
    authority.register_participant(
        application.SKILLS,
        Participant(
            verification=CleanupVerification(True, frozenset({7})),
            cleanup=OSError("disk"),
        ),
    )
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.forget(42)

    assert result == MutationResult(True, False, "Skills cleanup is unavailable.")
    assert authority._cleanup_verification[application.SKILLS] == CleanupVerification(
        False,
        frozenset({7, 42}),
        "Skills cleanup is unavailable.",
    )


def test_register_participant_verifies_only_after_both_named_slots_are_clean(tmp_path):
    authority, _, _, _ = build(tmp_path)

    first = authority.register_participant(application.SKILLS, Participant())
    second = authority.register_participant(application.FITTINGS, Participant())

    assert first == CleanupVerification(
        False,
        frozenset(),
        "Fittings cleanup is unavailable.",
    )
    assert second == CleanupVerification(True, frozenset(), "")


def test_unknown_id_is_blocked_while_a_required_slot_is_unverified(tmp_path):
    authority, _alerts, _launched, _listener = build(tmp_path)
    clean_skills = Participant(verification=CleanupVerification(True, frozenset()))
    authority.register_participant(application.SKILLS, clean_skills)

    assert authority._verify_unknown_character(77) == MutationResult(
        False,
        False,
        "Fittings cleanup is unavailable.",
    )


def test_an_exact_cleanup_block_does_not_block_an_unrelated_id(tmp_path):
    authority, _alerts, _launched, _listener = build(tmp_path)
    authority.register_participant(
        application.SKILLS,
        Participant(verification=CleanupVerification(True, frozenset({42}))),
    )
    authority.register_participant(
        application.FITTINGS,
        Participant(verification=CleanupVerification(True, frozenset())),
    )

    assert authority._verify_unknown_character(42).applied is False
    assert authority._verify_unknown_character(77).applied is True


def test_definitive_grant_invalidation_notifies_every_participant(tmp_path):
    error = sso_mod.OAuthError(400, "invalid_grant", "revoked")

    class RefusingSso(FakeAuthSso):
        def refresh_token(self, token):
            raise error

    authority, _, _, _ = build(tmp_path, sso=RefusingSso())
    participant = Participant()
    authority.register_participant(application.SKILLS, participant)

    authority.access_token(42, application.SKILLS)

    assert participant.invalidated == [42]


def persisted_authority(tmp_path):
    authority, warnings = state_mod.load_authority(tmp_path / "eve_authority.json")
    assert warnings == ()
    return authority


def test_start_reports_acceptance_not_completion(tmp_path):
    spawn = DeferredSpawn()
    authority, _, _, _ = build(tmp_path, spawn=spawn)

    result = authority.start_full_authorization()

    assert result == AuthorizationCommandResult(True, "")
    assert authority.authorization_activity == "waiting"


def test_terminal_failure_is_bounded_runtime_state(tmp_path):
    gate = Gate()
    spawn = DeferredSpawn()
    failing_sso = FakeAuthSso(
        exchange_gate=gate,
        exchange_error=sso_mod.OAuthError(400, "access_denied", "refused"),
    )
    authority, _alerts, _launched, _listener = build(
        tmp_path,
        sso=failing_sso,
        spawn=spawn,
    )

    authority.start_full_authorization()
    worker = threading.Thread(target=spawn.targets.pop(0))
    worker.start()
    assert gate.entered.wait(timeout=2)
    failing_sso.finish()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice
    assert len(authority.authorization_notice) <= 500


def test_start_full_authorization_refuses_an_unconfigured_build(tmp_path, monkeypatch):
    authority, alerts, _, _ = build(tmp_path, spawn=DeferredSpawn())
    with authority._lock:
        authority._authorization_notice = "Earlier failure."
    monkeypatch.setattr(application, "is_configured", lambda: False)

    result = authority.start_full_authorization()

    assert result.accepted is False
    assert "configured" in result.error.lower()
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == "Earlier failure."
    assert alerts == [
        (
            "warning",
            "EVE sign-in is not configured",
            "This build has no configured EVE application client id.",
        )
    ]


def test_single_flight_refusal_leaves_waiting_state_until_cancelled(tmp_path):
    spawn = DeferredSpawn()
    authority, alerts, _, listener = build(tmp_path, spawn=spawn)

    first = authority.start_full_authorization()
    second = authority.start_full_authorization()

    assert first == AuthorizationCommandResult(True, "")
    assert second.accepted is False
    assert "already" in second.error.lower()
    assert authority.authorization_activity == "waiting"
    assert authority.authorization_notice == ""
    assert listener.cancelled is False
    assert any("already" in title.lower() for _, title, _ in alerts)


def test_new_start_clears_the_previous_notice(tmp_path):
    authority, _alerts, _launched, _listener = build(tmp_path, spawn=DeferredSpawn())
    with authority._lock:
        authority._authorization_notice = "Earlier failure."

    authority.start_full_authorization()

    assert authority.authorization_notice == ""


def test_success_clears_the_previous_notice(tmp_path):
    authority, alerts, _launched, _listener = build(
        tmp_path,
        characters=[],
        returned_identity=full_identity(
            77, name="New Character", owner_hash="owner-77"
        ),
    )
    authority.register_participant(application.SKILLS, Participant())
    authority.register_participant(application.FITTINGS, Participant())
    with authority._lock:
        authority._authorization_notice = "Earlier failure."

    result = authority.start_full_authorization()

    assert result == AuthorizationCommandResult(True, "")
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == ""
    assert alerts == []


def test_cancel_authorization_returns_idle_without_an_error_notice(tmp_path):
    spawn = DeferredSpawn()
    authority, _alerts, _launched, _listener = build(tmp_path, spawn=spawn)
    authority.start_full_authorization()

    result = authority.cancel_authorization()

    assert result == AuthorizationCommandResult(True, "")
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == ""


def test_an_old_worker_cannot_clear_a_newer_attempt(tmp_path):
    spawn = DeferredSpawn()
    authority, _alerts, _launched, _listener = build(tmp_path, spawn=spawn)

    first = authority.start_full_authorization()
    cancelled = authority.cancel_authorization()
    second = authority.start_full_authorization()
    stale_worker = threading.Thread(target=spawn.targets.pop(0))
    stale_worker.start()
    stale_worker.join(timeout=2)

    assert first.accepted is True
    assert cancelled.accepted is True
    assert second.accepted is True
    assert not stale_worker.is_alive()
    assert authority.authorization_activity == "waiting"
    assert authority.authorization_notice == ""


def test_start_full_authorization_requests_full_scopes_and_adds_returned_character(
    tmp_path,
):
    fake_sso = FakeAuthSso()
    authority, alerts, launched, _ = build(
        tmp_path,
        characters=[],
        sso=fake_sso,
        returned_identity=full_identity(
            77, name="New Character", owner_hash="owner-77"
        ),
    )
    authority.register_participant(application.SKILLS, Participant())
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.start_full_authorization()

    assert result == AuthorizationCommandResult(True, "")
    assert fake_sso.authorized_scopes == [application.FULL_AUTH_SCOPES]
    assert authority.capability_status(77, application.SKILLS) == "enabled"
    assert authority.capability_status(77, application.FITTINGS) == "enabled"
    assert launched == ["https://login.eveonline.com/authorize"]
    assert alerts == []


def test_existing_same_owner_full_authorization_replaces_the_grant_and_clears_reauth(
    tmp_path,
):
    authority, _alerts, _launched, _listener = build(
        tmp_path,
        characters=[stored_character(needs_reauth=True)],
        returned_identity=full_identity(42),
    )

    authority.start_full_authorization()

    character = authority.character(42)
    assert character.needs_reauth is False
    assert character.scopes == tuple(sorted(application.FULL_AUTH_SCOPES))


def test_existing_character_with_a_different_owner_is_refused_unchanged(tmp_path):
    authority, alerts, _launched, _listener = build(
        tmp_path,
        returned_identity=full_identity(42, owner_hash="new-owner"),
    )

    result = authority.start_full_authorization()

    assert result.accepted is True
    assert authority.character(42).owner_hash == "owner-42"
    assert authority.character(42).scopes == tuple(sorted(application.SKILLS_SCOPES))
    assert "forget" in authority.authorization_notice.lower()
    assert any("forget" in body.lower() for _, _, body in alerts)


@pytest.mark.parametrize(
    ("stored_owner", "returned_owner", "expected_owner"),
    [("", "new-owner", "new-owner"), ("owner-42", "", "owner-42"), ("", "", "")],
)
def test_blank_owner_hashes_merge_compatibly(
    tmp_path, stored_owner, returned_owner, expected_owner
):
    authority, _alerts, _launched, _listener = build(
        tmp_path,
        characters=[stored_character(owner_hash=stored_owner)],
        returned_identity=full_identity(42, owner_hash=returned_owner),
    )

    authority.start_full_authorization()

    assert authority.character(42).owner_hash == expected_owner
    assert authority.capability_status(42, application.FITTINGS) == "enabled"


def test_unknown_id_verification_blocks_full_authorization_commit(tmp_path):
    authority, alerts, _launched, _listener = build(
        tmp_path,
        characters=[],
        returned_identity=full_identity(
            77, name="New Character", owner_hash="owner-77"
        ),
    )
    authority.register_participant(
        application.SKILLS,
        Participant(verification=CleanupVerification(True, frozenset({77}))),
    )
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.start_full_authorization()

    assert result.accepted is True
    assert authority.character(77) is None
    assert "reconcile" in authority.authorization_notice.lower()
    assert any("reconcile" in body.lower() for _, _, body in alerts)


def test_late_full_authorization_callback_cannot_resurrect_a_forgotten_character(
    tmp_path,
):
    authority = None

    def forget_during_wait():
        result = authority.forget(42)
        assert result.applied is True

    wrapped = []
    listener = FakeListener(on_wait=forget_during_wait)
    authority, alerts, _, _ = build(
        tmp_path,
        returned_identity=full_identity(42),
        listener=listener,
        wrapper=lambda token: wrapped.append(token) or token,
    )

    authority.start_full_authorization()

    assert authority.character(42) is None
    assert wrapped == ["refresh-auth"], (
        "Task 5's commit boundary prepares wrapping before the final generation "
        "recheck, so stale work may wrap but must not persist or resurrect the row"
    )
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
    authority, _, _, _ = build(
        tmp_path, returned_identity=full_identity(42), listener=listener
    )

    authority.start_full_authorization()

    assert observations == [(False, True)]


def test_auth_failure_alerts_run_without_the_authority_document_lock(tmp_path):
    authority = None
    lock_observations = []

    def observe_alert(kind, title, body):
        del kind, title, body
        lock_observations.append(authority._lock._is_owned())

    def refuse_save(path, authority_state):
        raise OSError("disk full")

    authority, _, _, _ = build(
        tmp_path,
        returned_identity=full_identity(42),
        saver=refuse_save,
        alert=observe_alert,
    )

    authority.start_full_authorization()

    assert lock_observations == [False]


def test_full_authorization_save_failure_keeps_the_previous_skills_grant(tmp_path):
    def refuse_save(path, authority_state):
        raise OSError("disk full")

    authority, alerts, _, _ = build(
        tmp_path,
        returned_identity=full_identity(42),
        saver=refuse_save,
    )

    authority.start_full_authorization()

    assert authority.capability_status(42, application.SKILLS) == "enabled"
    assert authority.capability_status(42, application.FITTINGS) == "enable"
    assert "not saved" in authority.authorization_notice.lower()
    assert any("not saved" in body.lower() for _, _, body in alerts)


def test_authenticate_skills_is_a_full_authorization_adapter(tmp_path):
    fake_sso = FakeAuthSso()
    authority, _alerts, _launched, _listener = build(
        tmp_path,
        characters=[],
        sso=fake_sso,
        returned_identity=full_identity(
            77, name="New Character", owner_hash="owner-77"
        ),
    )
    authority.register_participant(application.SKILLS, Participant())
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.authenticate_skills()

    assert result == MutationResult(True, True, "")
    assert fake_sso.authorized_scopes == [application.FULL_AUTH_SCOPES]
    assert authority.capability_status(77, application.FITTINGS) == "enabled"


def test_enable_capability_is_a_full_authorization_adapter(tmp_path):
    fake_sso = FakeAuthSso()
    authority, _alerts, _launched, _listener = build(
        tmp_path,
        sso=fake_sso,
        returned_identity=full_identity(
            77, name="New Character", owner_hash="owner-77"
        ),
    )
    authority.register_participant(application.SKILLS, Participant())
    authority.register_participant(application.FITTINGS, Participant())

    result = authority.enable_capability(42, application.FITTINGS)

    assert result == MutationResult(True, True, "")
    assert fake_sso.authorized_scopes == [application.FULL_AUTH_SCOPES]
    assert authority.capability_status(77, application.FITTINGS) == "enabled"


def test_forget_generation_rejects_late_work_even_after_same_id_is_added(tmp_path):
    authority, _, _, _ = build(tmp_path)
    authority.register_participant(application.SKILLS, Participant())
    authority.register_participant(application.FITTINGS, Participant())
    original_generation = authority.character(42).generation
    authority.forget(42)

    authority._validate_token = lambda token, **kwargs: full_identity(42)
    authority.start_full_authorization()

    assert authority.character(42).generation == original_generation + 1


def test_cancel_authorization_reaches_a_listener_bound_later(tmp_path):
    spawn = DeferredSpawn()
    authority, alerts, _, listener = build(tmp_path, spawn=spawn)

    first = authority.start_full_authorization()
    second = authority.start_full_authorization()
    cancelled = authority.cancel_authorization()

    assert first.accepted is True
    assert second.accepted is False
    assert cancelled.accepted is True
    assert "already" in second.error.lower()
    assert listener.cancelled is False, "listener is not bound until the worker starts"
    spawn.run_next()
    assert listener.cancelled is True, "an early cancellation must reach a later bind"
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == ""
    assert any("already" in title.lower() for _, title, _ in alerts)


@pytest.mark.parametrize(
    "phase",
    ("exchange", "validation", "lifecycle_gate", "pre_save"),
)
def test_cancel_authorization_wins_before_the_commit_linearization_point(
    tmp_path, phase
):
    gate = Gate()
    spawn = DeferredSpawn()
    build_kwargs = {"spawn": spawn}

    if phase == "exchange":
        build_kwargs["sso"] = FakeAuthSso(exchange_gate=gate)
    elif phase == "validation":

        def validator(token, **kwargs):
            del token, kwargs
            gate.wait()
            return full_identity(42)

        build_kwargs["validator"] = validator
    elif phase == "pre_save":

        def wrapper(token):
            gate.wait()
            return token

        build_kwargs["wrapper"] = wrapper

    authority, _alerts, _launched, _listener = build(tmp_path, **build_kwargs)
    if phase == "lifecycle_gate":
        gate = ProbeGate()
        authority._lifecycle_gates[42] = gate
    original = persisted_authority(tmp_path)

    authority.start_full_authorization()
    worker = threading.Thread(target=spawn.targets.pop(0))
    worker.start()
    assert gate.entered.wait(timeout=2)

    cancelled = authority.cancel_authorization()

    assert cancelled == AuthorizationCommandResult(True, "")
    assert persisted_authority(tmp_path) == original

    gate.open()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == ""


def test_cancel_authorization_reports_commit_won_after_the_linearization_point(
    tmp_path,
):
    spawn = DeferredSpawn()
    save_entered = threading.Event()
    release_save = threading.Event()
    cancel_called = threading.Event()
    cancel_finished = threading.Event()
    cancel_result = {}

    def block_inside_save(path, authority_state):
        save_entered.set()
        assert release_save.wait(timeout=2)
        state_mod.save_authority(path, authority_state)

    authority, _alerts, _launched, _listener = build(
        tmp_path,
        spawn=spawn,
        saver=block_inside_save,
    )

    authority.start_full_authorization()
    worker = threading.Thread(target=spawn.targets.pop(0))
    worker.start()
    assert save_entered.wait(timeout=2)

    def cancel():
        cancel_called.set()
        cancel_result["result"] = authority.cancel_authorization()
        cancel_finished.set()

    canceller = threading.Thread(target=cancel)
    canceller.start()
    assert cancel_called.wait(timeout=2)
    assert cancel_finished.is_set() is False

    release_save.set()
    worker.join(timeout=2)
    canceller.join(timeout=2)

    assert not worker.is_alive()
    assert not canceller.is_alive()
    assert cancel_result["result"].accepted is False
    assert authority.authorization_activity == "idle"
    assert authority.authorization_notice == ""
    assert authority.capability_status(42, application.FITTINGS) == "enabled"


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
