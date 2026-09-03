import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from wingman.eveesi import EsiResponse
from wingman.evefittings import contracts
from wingman.evefittings.model import (
    FittingsState,
    Presence,
    WriteIntent,
    canonicalize,
    new_library_entry,
    validate_remote_snapshot,
)
from wingman.evefittings.store import load_fittings, save_fittings

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def fitting(
    *,
    fitting_id=10,
    ship_type_id=100,
    name="Imported",
    flag="HiSlot0",
    type_id=200,
):
    return {
        "fitting_id": fitting_id,
        "ship_type_id": ship_type_id,
        "name": name,
        "description": f"Description for {name}",
        "items": [{"flag": flag, "quantity": 1, "type_id": type_id}],
    }


def response(status=200, data=None, *, etag=""):
    return EsiResponse(
        status=status,
        data=data,
        error="ESI unavailable" if status >= 400 else "",
        etag=etag,
        method="GET",
        path="/characters/42/fittings",
    )


class FakeAuthority:
    def __init__(self, character_ids=(42, 43)):
        self._ids = tuple(character_ids)
        self.active_character = None
        self.events = []
        self.feature_lock = None

    @property
    def characters(self):
        return tuple(
            SimpleNamespace(character_id=value, character_name=f"Pilot {value}")
            for value in self._ids
        )

    def capability_status(self, character_id, capability):
        assert capability == "fittings"
        return "enabled" if character_id in self._ids else "missing"

    @contextmanager
    def lifecycle(self, character_id, capability):
        assert capability == "fittings"
        if self.feature_lock is not None:
            assert not self.feature_lock._is_owned()
        if character_id not in self._ids:
            raise KeyError(character_id)
        assert self.active_character is None
        self.active_character = character_id
        self.events.append(("enter", character_id))
        try:
            yield SimpleNamespace(character=SimpleNamespace(character_id=character_id))
        finally:
            self.events.append(("exit", character_id))
            self.active_character = None

    def access_token(self, character_id, capability, *, rejected_token=None):
        assert self.active_character == character_id
        assert capability == "fittings"
        return SimpleNamespace(
            token=f"token-{character_id}",
            error="",
            grant_invalidated=False,
            reason="",
        )

    def character(self, character_id):
        if character_id not in self._ids:
            return None
        return SimpleNamespace(character_id=character_id, owner_hash="owner")


class FakeEsi:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.get_calls = []
        self.post_calls = []
        self.post_reply = response(200, [])
        self.authority = None
        self.started = None
        self.release = None
        self.active = 0
        self.max_active = 0

    def get(self, path, *, token=None, etag=None):
        character_id = int(path.split("/")[2])
        assert self.authority.active_character == character_id
        self.get_calls.append((character_id, token, etag))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.started is not None:
                self.started.set()
            if self.release is not None:
                assert self.release.wait(2)
            reply = self.replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return reply
        finally:
            self.active -= 1

    def post(self, path, body, *, token=None):
        assert self.authority.active_character is None
        self.post_calls.append((path, list(body), token))
        return self.post_reply


def make_controller(tmp_path, replies=(), *, now=lambda: NOW, initial=None, save=None):
    from wingman.evefittings.controller import FittingsController

    state_path = tmp_path / "eve_fittings.json"
    if initial is not None:
        save_fittings(state_path, initial)
    authority = FakeAuthority()
    esi = FakeEsi(replies)
    esi.authority = authority
    entry_ids = iter(f"new-entry-{index}" for index in range(1000))
    controller = FittingsController(
        state_path=state_path,
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=esi,
        now=now,
        save_state=save or save_fittings,
        id_factory=lambda: next(entry_ids),
        batch_id_factory=lambda: "batch-1",
    )
    authority.feature_lock = controller._lock
    return controller, authority, esi, state_path


def seeded_state(*, intent=None):
    remote = validate_remote_snapshot([fitting(name="Seeded")])[0]
    entry = new_library_entry(remote, entry_id="existing-entry", now=NOW)
    presence = Presence(
        character_id=42,
        remote_fitting_id=10,
        library_entry_id=entry.id,
        source_name=remote.name,
        source_description=remote.description,
        source_template=remote.items,
        first_seen_utc=NOW - timedelta(days=1),
        discovered_batch_id="old-batch",
        last_confirmed_utc=NOW - timedelta(hours=1),
    )
    intents = () if intent is None else (intent(entry),)
    return FittingsState(entries=(entry,), presences=(presence,), intents=intents)


def unknown_intent(entry):
    return WriteIntent(
        operation_id="operation-1",
        character_id=42,
        library_entry_id=entry.id,
        content=entry.content,
        status="unknown",
        created_utc=NOW,
        sent_utc=NOW,
    )


def test_valid_refresh_imports_and_records_discovery(tmp_path):
    controller, authority, _esi, state_path = make_controller(
        tmp_path, [response(200, [fitting()], etag='"one"')]
    )

    result = controller.refresh([42])

    assert result["ok"] is True
    assert result["batch_id"] == "batch-1"
    assert len(controller.state.entries) == 1
    entry = controller.state.entries[0]
    presence = controller.state.presences[0]
    assert entry.content == canonicalize(validate_remote_snapshot([fitting()])[0])
    assert presence.library_entry_id == entry.id
    assert presence.first_seen_utc == NOW
    assert presence.discovered_batch_id == result["batch_id"]
    assert load_fittings(state_path)[0] == controller.state
    assert authority.events == [("enter", 42), ("exit", 42)]


def test_valid_empty_refresh_replaces_authoritative_presence(tmp_path):
    controller, _authority, _esi, _path = make_controller(
        tmp_path, [response(200, [])], initial=seeded_state()
    )

    result = controller.refresh([42])

    assert result["ok"] is True
    assert controller.state.presences == ()
    assert controller.state.entries[0].id == "existing-entry"


def test_malformed_or_unknown_flag_refresh_retains_prior_presence_stale(tmp_path):
    malformed = fitting()
    malformed["items"][0]["flag"] = "FutureSlot0"
    controller, _authority, _esi, _path = make_controller(
        tmp_path, [response(200, [malformed])], initial=seeded_state()
    )

    result = controller.refresh([42])

    assert result["ok"] is False
    assert controller.state.presences == seeded_state().presences
    snapshot = controller.character_status(42)
    assert snapshot.stale is True
    assert "unknown fitting flag" in snapshot.error


def test_oversized_transport_failure_retains_prior_presence_stale(tmp_path):
    controller, _authority, _esi, _path = make_controller(
        tmp_path,
        [ValueError("ESI response exceeded the bounded body limit")],
        initial=seeded_state(),
    )

    result = controller.refresh([42])

    assert result["ok"] is False
    assert controller.state.presences == seeded_state().presences
    assert controller.character_status(42).stale is True
    assert "bounded body limit" in controller.character_status(42).error


def test_304_confirms_retained_data_without_replacing_it(tmp_path):
    clock = [NOW]
    initial = replace(
        seeded_state(),
        snapshots=(),
    )
    controller, _authority, esi, _path = make_controller(
        tmp_path,
        [response(200, [fitting(name="Seeded")], etag='"one"'), response(304)],
        initial=initial,
        now=lambda: clock[0],
    )
    controller.refresh([42])
    first = controller.state.presences[0]
    clock[0] += timedelta(minutes=1)

    result = controller.refresh([42])

    retained = controller.state.presences[0]
    assert result["ok"] is True
    assert result["characters"][0]["not_modified"] is True
    assert retained.first_seen_utc == first.first_seen_utc
    assert retained.discovered_batch_id == first.discovered_batch_id
    assert retained.last_confirmed_utc == clock[0]
    assert controller.character_status(42).fetched_utc == clock[0]
    assert esi.get_calls[-1][2] == '"one"'


def test_invalid_flag_import_is_retained_but_not_deployable(tmp_path):
    controller, _authority, _esi, _path = make_controller(
        tmp_path, [response(200, [fitting(flag="Invalid")])]
    )

    assert controller.refresh([42])["ok"] is True

    entry = controller.state.entries[0]
    assert entry.content.items[0].location == "Invalid"
    assert entry.deployment_template is None


def test_equivalent_content_uses_digest_hint_and_full_canonical_equality(tmp_path):
    old_remote = validate_remote_snapshot([fitting(name="Old", flag="HiSlot0")])[0]
    old_entry = new_library_entry(old_remote, entry_id="older-entry", now=NOW)
    controller, _authority, _esi, _path = make_controller(
        tmp_path,
        [response(200, [fitting(name="New", flag="HiSlot7")])],
        initial=FittingsState(entries=(old_entry,)),
    )

    result = controller.refresh([43])

    assert result["ok"] is True
    assert len(controller.state.entries) == 1
    assert controller.state.entries[0].id == "older-entry"
    assert {alias.name for alias in controller.state.entries[0].aliases} == {
        "Old",
        "New",
    }
    discovered = controller.state.presences[0]
    assert discovered.character_id == 43
    assert discovered.first_seen_utc == NOW
    assert discovered.discovered_batch_id == "batch-1"


def test_refresh_preserves_unknown_intent_overlay(tmp_path):
    initial = seeded_state(intent=unknown_intent)
    controller, _authority, _esi, _path = make_controller(
        tmp_path,
        [response(200, [fitting(name="Seeded")])],
        initial=initial,
    )

    controller.refresh([42])

    assert controller.state.intents == initial.intents


def test_failed_snapshot_save_preserves_prior_durable_and_live_state(tmp_path):
    initial = seeded_state()
    state_path = tmp_path / "eve_fittings.json"
    save_fittings(state_path, initial)
    before = state_path.read_bytes()

    def failing_save(_path, _state):
        raise OSError("disk full")

    controller, _authority, _esi, _path = make_controller(
        tmp_path,
        [response(200, [fitting(fitting_id=99, type_id=999)])],
        initial=None,
        save=failing_save,
    )

    result = controller.refresh([42])

    assert result["ok"] is False
    assert controller.state == initial
    assert state_path.read_bytes() == before


def test_all_character_refresh_is_sequential_and_globally_single_flight(tmp_path):
    controller, authority, esi, _path = make_controller(
        tmp_path,
        [
            response(200, [fitting()]),
            response(200, [fitting(fitting_id=20, type_id=201)]),
        ],
    )
    esi.started = threading.Event()
    esi.release = threading.Event()
    first_result = []
    worker = threading.Thread(target=lambda: first_result.append(controller.refresh()))
    worker.start()
    assert esi.started.wait(1)

    overlapping = controller.refresh([42])
    esi.release.set()
    worker.join(2)

    assert overlapping["ok"] is False
    assert overlapping["busy"] is True
    assert first_result[0]["ok"] is True
    assert [call[0] for call in esi.get_calls] == [42, 43]
    assert esi.max_active == 1
    assert authority.events == [
        ("enter", 42),
        ("exit", 42),
        ("enter", 43),
        ("exit", 43),
    ]


def test_lifecycle_lease_remains_held_through_atomic_snapshot_save(tmp_path):
    from wingman.evefittings.controller import FittingsController

    authority = FakeAuthority((42,))
    esi = FakeEsi([response(200, [fitting()])])
    esi.authority = authority
    save_observations = []

    def leased_save(path, state):
        save_observations.append(authority.active_character)
        save_fittings(path, state)

    controller = FittingsController(
        state_path=tmp_path / "eve_fittings.json",
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=esi,
        save_state=leased_save,
    )
    authority.feature_lock = controller._lock

    assert controller.refresh([42])["ok"] is True
    assert save_observations == [42]


def test_grant_invalidation_clears_snapshot_but_preserves_unknown_intent(tmp_path):
    initial = seeded_state(intent=unknown_intent)
    controller, _authority, _esi, _path = make_controller(tmp_path, initial=initial)

    controller.grant_invalidated(42)

    assert controller.state.entries == initial.entries
    assert controller.state.presences == ()
    assert controller.state.snapshots == ()
    assert controller.state.intents == initial.intents
    assert controller.prepare_forget(42).applied is False


def test_authority_removal_prunes_character_state_but_keeps_library(tmp_path):
    initial = seeded_state()
    controller, _authority, _esi, state_path = make_controller(
        tmp_path, initial=initial
    )

    controller.authority_removed(42)

    assert controller.state.entries == initial.entries
    assert controller.state.presences == ()
    assert controller.state.snapshots == ()
    assert load_fittings(state_path)[0] == controller.state


def test_remote_snapshot_count_limit_is_not_silently_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "MAX_REMOTE_FITTINGS", 1)
    controller, _authority, _esi, _path = make_controller(
        tmp_path,
        [response(200, [fitting(), fitting(fitting_id=11)])],
        initial=seeded_state(),
    )

    result = controller.refresh([42])

    assert result["ok"] is False
    assert controller.state.presences == seeded_state().presences
    assert "exceeds 1 fittings" in controller.character_status(42).error
