"""Cross-feature lifecycle races for fitting writes and shared authority."""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from wingman.eveauth import CleanupVerification, application
from wingman.eveauth import state as authority_state_mod
from wingman.eveauth.controller import AuthorityController, MutationResult
from wingman.eveesi import EsiResponse, MutationResponse
from wingman.evefittings.controller import FittingsController
from wingman.evefittings.model import (
    CharacterSnapshot,
    Collection,
    FittingsState,
    Presence,
    WriteIntent,
    new_library_entry,
    validate_remote_snapshot,
)
from wingman.evefittings.store import save_fittings

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
CHARACTER_ID = 42


def _entry(entry_id="fit-1", fitting_id=1, type_id=200):
    remote = validate_remote_snapshot(
        [
            {
                "fitting_id": fitting_id,
                "ship_type_id": 100,
                "name": f"Fit {fitting_id}",
                "description": "",
                "items": [{"flag": "HiSlot0", "quantity": 1, "type_id": type_id}],
            }
        ]
    )[0]
    return new_library_entry(remote, entry_id=entry_id, now=NOW)


def _presence(entry, *, character_id=CHARACTER_ID, remote_fitting_id=1):
    return Presence(
        character_id=character_id,
        remote_fitting_id=remote_fitting_id,
        library_entry_id=entry.id,
        source_name=entry.preferred_name,
        source_description=entry.preferred_description,
        source_template=entry.source_template,
        first_seen_utc=NOW,
        discovered_batch_id="batch-1",
        last_confirmed_utc=NOW,
    )


def _snapshot(*, character_id=CHARACTER_ID, etag='"before-copy"'):
    return CharacterSnapshot(
        character_id=character_id,
        fetched_utc=NOW,
        content_utc=NOW,
        etag=etag,
    )


def _intent(
    entry,
    *,
    character_id=CHARACTER_ID,
    operation_id="copy-1",
    status="unknown",
):
    return WriteIntent(
        operation_id=operation_id,
        character_id=character_id,
        library_entry_id=entry.id,
        content=entry.content,
        status=status,
        created_utc=NOW,
        sent_utc=NOW,
        completed_utc=NOW if status == "success" else None,
    )


def _authority(tmp_path):
    persistent = authority_state_mod.AuthorityState(
        [
            authority_state_mod.AuthorityCharacter(
                character_id=CHARACTER_ID,
                character_name="Pilot 42",
                owner_hash="owner-42",
                scopes=tuple(
                    sorted(application.SKILLS_SCOPES | application.FITTINGS_SCOPES)
                ),
                authenticated_utc=NOW,
                refresh_token_blob="refresh-42",
            )
        ]
    )
    path = tmp_path / "eve_authority.json"
    authority_state_mod.save_authority(path, persistent)
    controller = AuthorityController(
        state_path=path,
        authority=persistent,
        now=lambda: NOW,
        unwrap_token=lambda blob: blob or None,
    )
    controller._access_tokens[CHARACTER_ID] = (
        "access-42",
        NOW + timedelta(hours=1),
    )
    return controller


def _fittings(
    tmp_path,
    authority,
    client,
    *,
    entries=None,
    progress=None,
    state=None,
    save_state=save_fittings,
):
    entries = tuple(entries or (_entry(),))
    if state is None:
        state = FittingsState(entries=entries, snapshots=(_snapshot(),))
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, state)
    controller = FittingsController(
        state_path=path,
        names_path=tmp_path / "eve_fittings_names.json",
        authority=authority,
        client=client,
        now=lambda: NOW,
        progress=progress or (lambda _payload: None),
        save_state=save_state,
    )
    authority.register_participant(application.FITTINGS, controller)
    return controller


class BlockingUnknownClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def post_once(self, path, body, *, token):
        del path, body, token
        self.calls += 1
        self.started.set()
        assert self.release.wait(timeout=2)
        return MutationResponse(False, None, None, "timeout", {})


class BlockingRefreshClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def get(self, path, *, token, etag=None):
        del path, token, etag
        self.started.set()
        assert self.release.wait(timeout=2)
        return EsiResponse(200, [], "", "", "GET", "/characters/42/fittings")


class BlockingSuccessClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def post_once(self, path, body, *, token):
        del path, body, token
        self.calls += 1
        self.started.set()
        assert self.release.wait(timeout=2)
        return MutationResponse(True, 201, {"fitting_id": 9001}, "", {})


class SuccessClient:
    def __init__(self):
        self.calls = 0

    def post_once(self, path, body, *, token):
        del path, body, token
        self.calls += 1
        return MutationResponse(True, 201, {"fitting_id": 9000 + self.calls}, "", {})


@pytest.mark.parametrize(
    ("state", "label"),
    [
        pytest.param(
            lambda entry: FittingsState(
                entries=(entry,),
                presences=(_presence(entry),),
            ),
            "presence",
            id="presence",
        ),
        pytest.param(
            lambda entry: FittingsState(
                entries=(entry,),
                snapshots=(_snapshot(),),
            ),
            "snapshot",
            id="snapshot",
        ),
        pytest.param(
            lambda entry: FittingsState(
                entries=(entry,),
                intents=(_intent(entry),),
            ),
            "intent",
            id="intent",
        ),
    ],
)
def test_failed_reconciliation_reports_blocked_character_from_each_source(
    tmp_path, state, label
):
    authority = _authority(tmp_path)
    entry = _entry()

    def fail_save(*_args, **_kwargs):
        raise OSError("disk")

    fittings = _fittings(
        tmp_path,
        authority,
        SuccessClient(),
        state=state(entry),
        save_state=fail_save,
    )

    verification = fittings.reconcile_characters(())

    assert verification.verified is True
    assert verification.blocked_character_ids == frozenset({CHARACTER_ID})
    assert label in {"presence", "snapshot", "intent"}


def test_unresolved_intent_still_refuses_prepare_forget_after_reconciliation(tmp_path):
    authority = _authority(tmp_path)
    entry = _entry()
    fittings = _fittings(
        tmp_path,
        authority,
        SuccessClient(),
        state=FittingsState(entries=(entry,), intents=(_intent(entry),)),
    )

    verification = fittings.reconcile_characters(())

    assert verification.blocked_character_ids == frozenset({CHARACTER_ID})
    assert fittings.prepare_forget(CHARACTER_ID) == MutationResult(
        False,
        True,
        "Refresh this character to reconcile an unresolved fitting copy first.",
    )


def test_successful_cleanup_retains_fitting_library_entries_and_collections(tmp_path):
    authority = _authority(tmp_path)
    entry = _entry()
    state = FittingsState(
        entries=(entry,),
        collections=(Collection(id="doctrine", name="Doctrine"),),
        presences=(_presence(entry),),
        snapshots=(_snapshot(),),
        intents=(_intent(entry, status="success"),),
    )
    fittings = _fittings(tmp_path, authority, SuccessClient(), state=state)

    verification = fittings.reconcile_characters(())

    assert verification.blocked_character_ids == frozenset()
    assert fittings.state.entries == state.entries
    assert fittings.state.collections == state.collections
    assert fittings.state.presences == ()
    assert fittings.state.snapshots == ()
    assert fittings.state.intents == ()


def test_failed_authority_removal_save_is_retryable_for_fittings(tmp_path):
    authority = _authority(tmp_path)
    entry = _entry()
    state = FittingsState(
        entries=(entry,),
        collections=(Collection(id="doctrine", name="Doctrine"),),
        presences=(_presence(entry),),
        snapshots=(_snapshot(),),
        intents=(_intent(entry, status="success"),),
    )
    calls = 0

    def fail_once(path, candidate):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk")
        save_fittings(path, candidate)

    fittings = _fittings(
        tmp_path,
        authority,
        SuccessClient(),
        state=state,
        save_state=fail_once,
    )

    result = fittings.authority_removed(CHARACTER_ID)

    assert result == MutationResult(True, False, "Could not save Fittings cleanup.")
    assert fittings.state.presences == state.presences
    assert fittings.state.snapshots == state.snapshots
    assert fittings.state.intents == state.intents

    verification = fittings.reconcile_characters(())

    assert verification.blocked_character_ids == frozenset()
    assert fittings.state.entries == state.entries
    assert fittings.state.collections == state.collections
    assert fittings.state.presences == ()
    assert fittings.state.snapshots == ()
    assert fittings.state.intents == ()


def test_forget_during_in_flight_post_waits_then_refuses_unknown(tmp_path):
    authority = _authority(tmp_path)
    client = BlockingUnknownClient()
    fittings = _fittings(tmp_path, authority, client)
    ticket = fittings.preflight_copy(["fit-1"], [CHARACTER_ID])["ticket_id"]
    copy_result = []
    forget_result = []
    forget_started = threading.Event()
    forget_finished = threading.Event()

    copy_worker = threading.Thread(
        target=lambda: copy_result.append(fittings.start_copy(ticket))
    )

    def forget():
        forget_started.set()
        forget_result.append(authority.forget(CHARACTER_ID))
        forget_finished.set()

    forget_worker = threading.Thread(target=forget)
    copy_worker.start()
    assert client.started.wait(timeout=2)
    forget_worker.start()
    assert forget_started.wait(timeout=2)
    assert not forget_finished.wait(timeout=0.1)

    client.release.set()
    copy_worker.join(timeout=2)
    forget_worker.join(timeout=2)

    assert copy_result[0]["write_count"] == 1
    assert copy_result[0]["results"][0]["status"] == "unknown"
    assert forget_result[0].applied is False
    assert "reconcile" in forget_result[0].error.lower()
    assert authority.character(CHARACTER_ID) is not None
    assert fittings.state.intents[0].status == "unknown"


def test_shutdown_waits_for_in_flight_refresh(tmp_path):
    authority = _authority(tmp_path)
    client = BlockingRefreshClient()
    fittings = _fittings(tmp_path, authority, client)
    refresh_result = []
    shutdown_finished = threading.Event()
    refresh_worker = threading.Thread(
        target=lambda: refresh_result.append(fittings.refresh([CHARACTER_ID]))
    )

    def shutdown():
        fittings.shutdown()
        shutdown_finished.set()

    shutdown_worker = threading.Thread(target=shutdown)
    refresh_worker.start()
    assert client.started.wait(timeout=2)
    shutdown_worker.start()
    assert not shutdown_finished.wait(timeout=0.1)

    client.release.set()
    refresh_worker.join(timeout=2)
    shutdown_worker.join(timeout=2)

    assert shutdown_finished.is_set()
    assert refresh_result[0]["characters"][0]["ok"] is True


def test_shutdown_waits_for_in_flight_copy_and_reports_honest_counts(tmp_path):
    authority = _authority(tmp_path)
    client = BlockingSuccessClient()
    fittings = _fittings(
        tmp_path,
        authority,
        client,
        entries=(_entry("fit-1", 1, 200), _entry("fit-2", 2, 201)),
    )
    ticket = fittings.preflight_copy(["fit-1", "fit-2"], [CHARACTER_ID])["ticket_id"]
    copy_result = []
    shutdown_finished = threading.Event()
    copy_worker = threading.Thread(
        target=lambda: copy_result.append(fittings.start_copy(ticket))
    )

    def shutdown():
        fittings.shutdown()
        shutdown_finished.set()

    shutdown_worker = threading.Thread(target=shutdown)
    copy_worker.start()
    assert client.started.wait(timeout=2)
    shutdown_worker.start()
    assert not shutdown_finished.wait(timeout=0.1)

    client.release.set()
    copy_worker.join(timeout=2)
    shutdown_worker.join(timeout=2)

    assert shutdown_finished.is_set()
    assert client.calls == 1
    assert copy_result[0]["status"] == "cancelled"
    assert copy_result[0]["write_count"] == 1
    assert [row["status"] for row in copy_result[0]["results"]] == [
        "success",
        "cancelled",
    ]


def test_shutdown_refuses_new_copy_and_refresh_work(tmp_path):
    authority = _authority(tmp_path)
    client = SuccessClient()
    fittings = _fittings(tmp_path, authority, client)
    ticket = fittings.preflight_copy(["fit-1"], [CHARACTER_ID])["ticket_id"]

    fittings.shutdown()
    copy_result = fittings.start_copy(ticket)
    refresh_result = fittings.refresh([CHARACTER_ID])

    assert copy_result["status"] == "shutting_down"
    assert copy_result["write_count"] == 0
    assert refresh_result["ok"] is False
    assert "shutting down" in refresh_result["error"].lower()
    assert client.calls == 0


def test_startup_converts_in_flight_to_unknown_before_forget_preflight(tmp_path):
    authority = _authority(tmp_path)
    fit = _entry()
    state = FittingsState(
        entries=(fit,),
        snapshots=(
            CharacterSnapshot(
                character_id=CHARACTER_ID,
                fetched_utc=NOW,
                content_utc=NOW,
            ),
        ),
        intents=(
            WriteIntent(
                operation_id="crashed-copy",
                character_id=CHARACTER_ID,
                library_entry_id=fit.id,
                content=fit.content,
                status="in_flight",
                created_utc=NOW,
                sent_utc=NOW,
            ),
        ),
    )
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, state)
    fittings = FittingsController(
        state_path=path,
        names_path=tmp_path / "eve_fittings_names.json",
        authority=authority,
        client=SuccessClient(),
        now=lambda: NOW,
    )
    authority.register_participant(application.FITTINGS, fittings)

    assert fittings.state.intents[0].status == "unknown"
    assert fittings.prepare_forget(CHARACTER_ID).applied is False
    preflight = fittings.preflight_copy([fit.id], [CHARACTER_ID])
    assert preflight["pairs"][0]["status"] == "unavailable"
    assert "unknown" in preflight["pairs"][0]["error"].lower()


def test_startup_reconciliation_prunes_orphans_but_keeps_unknown_evidence(
    tmp_path,
):
    authority = _authority(tmp_path)
    fit = _entry()
    state = FittingsState(
        entries=(fit,),
        presences=(
            Presence(
                character_id=CHARACTER_ID,
                remote_fitting_id=1,
                library_entry_id=fit.id,
                source_name=fit.preferred_name,
                source_description=fit.preferred_description,
                source_template=fit.source_template,
                first_seen_utc=NOW,
                discovered_batch_id="batch-1",
                last_confirmed_utc=NOW,
            ),
        ),
        snapshots=(
            CharacterSnapshot(
                character_id=CHARACTER_ID,
                fetched_utc=NOW,
                content_utc=NOW,
            ),
        ),
        intents=(
            WriteIntent(
                operation_id="unknown-copy",
                character_id=CHARACTER_ID,
                library_entry_id=fit.id,
                content=fit.content,
                status="unknown",
                created_utc=NOW,
                sent_utc=NOW,
            ),
        ),
    )
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, state)
    fittings = FittingsController(
        state_path=path,
        names_path=tmp_path / "eve_fittings_names.json",
        authority=authority,
        client=SuccessClient(),
        now=lambda: NOW,
    )

    fittings.reconcile_characters(())

    assert fittings.state.presences == ()
    assert fittings.state.snapshots == ()
    assert fittings.state.intents == state.intents


def test_forget_between_copy_pairs_prevents_the_later_send(tmp_path):
    authority = _authority(tmp_path)
    client = SuccessClient()
    first_finished = threading.Event()
    continue_copy = threading.Event()

    def progress(payload):
        if payload.get("phase") == "progress" and payload.get("completed") == 1:
            first_finished.set()
            assert continue_copy.wait(timeout=2)

    fittings = _fittings(
        tmp_path,
        authority,
        client,
        entries=(_entry("fit-1", 1, 200), _entry("fit-2", 2, 201)),
        progress=progress,
    )

    class CleanSkillsParticipant:
        def prepare_forget(self, character_id):
            del character_id
            return MutationResult(True, True, "")

        def authority_removed(self, character_id):
            del character_id
            return MutationResult(True, True, "")

        def grant_invalidated(self, character_id):
            del character_id

        def reconcile_characters(self, characters):
            del characters
            return CleanupVerification(True, frozenset())

    authority.register_participant(application.SKILLS, CleanSkillsParticipant())
    ticket = fittings.preflight_copy(["fit-1", "fit-2"], [CHARACTER_ID])["ticket_id"]
    copy_result = []
    worker = threading.Thread(
        target=lambda: copy_result.append(fittings.start_copy(ticket))
    )
    worker.start()
    assert first_finished.wait(timeout=2)

    forgotten = authority.forget(CHARACTER_ID)
    continue_copy.set()
    worker.join(timeout=2)

    assert forgotten.applied is True and forgotten.persisted is True
    assert authority.character(CHARACTER_ID) is None
    assert client.calls == 1
    assert copy_result[0]["write_count"] == 1
    assert [row["status"] for row in copy_result[0]["results"]] == [
        "success",
        "unavailable",
    ]
