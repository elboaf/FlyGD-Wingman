"""Preflight tickets and durable, one-attempt fitting copy operations."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from wingman.eveesi import EsiResponse, MutationResponse
from wingman.evefittings import contracts
from wingman.evefittings.controller import FittingsController
from wingman.evefittings.model import (
    CharacterSnapshot,
    FittingsState,
    Presence,
    WriteIntent,
    new_library_entry,
    validate_remote_snapshot,
)
from wingman.evefittings.store import load_fittings, save_fittings

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def remote(
    fitting_id: int,
    name: str,
    *,
    ship_type_id: int = 100,
    type_id: int = 200,
    flag: str = "HiSlot0",
):
    return validate_remote_snapshot(
        [
            {
                "fitting_id": fitting_id,
                "ship_type_id": ship_type_id,
                "name": name,
                "description": f"Description for {name}",
                "items": [{"flag": flag, "quantity": 1, "type_id": type_id}],
            }
        ]
    )[0]


def entry(entry_id: str, fitting_id: int, name: str, **kwargs):
    return new_library_entry(
        remote(fitting_id, name, **kwargs), entry_id=entry_id, now=NOW
    )


def presence(character_id: int, remote_id: int, fit, *, source_name=None):
    return Presence(
        character_id=character_id,
        remote_fitting_id=remote_id,
        library_entry_id=fit.id,
        source_name=source_name or fit.preferred_name,
        source_description=fit.preferred_description,
        source_template=fit.source_template,
        first_seen_utc=NOW - timedelta(days=1),
        discovered_batch_id="batch-before-copy",
        last_confirmed_utc=NOW,
    )


def snapshot(character_id: int, *, age=0, error=""):
    return CharacterSnapshot(
        character_id=character_id,
        fetched_utc=NOW - timedelta(seconds=age),
        etag=f'"etag-{character_id}"',
        error=error,
    )


def intent(
    operation_id: str,
    character_id: int,
    fit,
    *,
    status="unknown",
    error="",
):
    return WriteIntent(
        operation_id=operation_id,
        character_id=character_id,
        library_entry_id=fit.id,
        content=fit.content,
        status=status,
        created_utc=NOW - timedelta(minutes=1),
        sent_utc=NOW - timedelta(minutes=1),
        completed_utc=NOW - timedelta(minutes=1)
        if status in {"success", "failed"}
        else None,
        error=error,
    )


class FakeAuthority:
    def __init__(self, character_ids=(42, 43), *, enabled=None):
        self.character_ids = list(character_ids)
        self.enabled = set(character_ids if enabled is None else enabled)
        self.events = []
        self.active_character = None
        self.feature_lock = None

    @property
    def characters(self):
        return tuple(
            SimpleNamespace(character_id=value, character_name=f"Pilot {value}")
            for value in self.character_ids
        )

    @property
    def auth_in_progress(self):
        return False

    def capability_status(self, character_id, capability):
        assert capability == "fittings"
        if character_id not in self.character_ids:
            return "missing"
        return "enabled" if character_id in self.enabled else "enable"

    @contextmanager
    def lifecycle(self, character_id, capability):
        assert capability == "fittings"
        assert not self.feature_lock._is_owned()
        if character_id not in self.character_ids:
            raise KeyError(character_id)
        if character_id not in self.enabled:
            raise PermissionError(character_id)
        assert self.active_character is None
        self.active_character = character_id
        self.events.append(("enter", character_id))
        try:
            yield SimpleNamespace(
                character=SimpleNamespace(
                    character_id=character_id,
                    character_name=f"Pilot {character_id}",
                )
            )
        finally:
            self.events.append(("exit", character_id))
            self.active_character = None

    def access_token(self, character_id, capability, *, rejected_token=None):
        assert capability == "fittings"
        assert rejected_token is None
        assert self.active_character == character_id
        return SimpleNamespace(token=f"token-{character_id}", error="")


class FakeClient:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.post_calls = []
        self.authority = None
        self.on_post = None
        self.get_calls = []
        self.get_reply = EsiResponse(
            200, [], "", '"snapshot"', "GET", "/characters/42/fittings"
        )
        self.on_get = None

    def get(self, path, *, token, etag=None):
        assert self.authority.active_character == int(path.split("/")[2])
        self.get_calls.append((path, etag))
        if self.on_get is not None:
            self.on_get()
        return self.get_reply

    def post_once(self, path, body, *, token):
        assert self.authority.active_character == int(path.split("/")[2])
        assert not self.authority.feature_lock._is_owned()
        self.post_calls.append((path, body, token))
        if self.on_post is not None:
            self.on_post(len(self.post_calls))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def mutation(status=201, data=None, *, response_received=True, error=""):
    return MutationResponse(
        response_received=response_received,
        status=status if response_received else None,
        data={"fitting_id": 9001} if data is None and status == 201 else data,
        error=error
        or (
            f"ESI rejected create ({status})."
            if isinstance(status, int) and status >= 400
            else ""
        ),
        headers={},
    )


def make_controller(
    tmp_path,
    state,
    *,
    authority=None,
    replies=(),
    save_state=save_fittings,
    progress=None,
    now=lambda: NOW,
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, state)
    authority = authority or FakeAuthority()
    client = FakeClient(replies)
    client.authority = authority
    controller = FittingsController(
        state_path=path,
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=client,
        now=now,
        save_state=save_state,
        progress=progress or (lambda payload: None),
    )
    authority.feature_lock = controller._lock
    ticket_ids = iter(f"ticket-{index}" for index in range(100))
    operation_ids = iter(f"operation-{index}" for index in range(100))
    controller._ticket_id_factory = lambda: next(ticket_ids)
    controller._operation_id_factory = lambda: next(operation_ids)
    return controller, authority, client, path


def ready_state(*, count=1, character_ids=(42,)):
    entries = tuple(
        entry(f"fit-{index}", index + 1, f"Fit {index}", type_id=200 + index)
        for index in range(count)
    )
    return FittingsState(
        entries=entries,
        snapshots=tuple(snapshot(character_id) for character_id in character_ids),
    )


def ready_ticket(controller, *, fit_ids=None, character_ids=(42,)):
    fit_ids = fit_ids or [controller.state.entries[0].id]
    result = controller.preflight_copy(fit_ids, list(character_ids))
    assert result["accepted"] is True
    assert result["write_count"] == len(fit_ids) * len(character_ids)
    return result["ticket_id"]


def test_preflight_classifies_present_conflict_ready_and_unavailable(tmp_path):
    fit_a = entry("fit-a", 1, "Fit A", type_id=201)
    fit_b = entry("fit-b", 2, "Fit B", type_id=202)
    other = entry("other", 3, "Other", type_id=203)
    state = FittingsState(
        entries=(fit_a, fit_b, other),
        presences=(
            presence(42, 1001, fit_a),
            presence(42, 1002, other, source_name="Fit B"),
        ),
        snapshots=(snapshot(42), snapshot(43)),
        intents=(intent("old-unknown", 43, fit_a),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy(["fit-a", "fit-b"], [42, 43])

    assert result["accepted"] is True
    assert result["counts"] == {
        "ready": 1,
        "present": 1,
        "conflict": 1,
        "unavailable": 1,
    }
    statuses = {
        (row["entry_id"], row["character_id"]): row["status"] for row in result["pairs"]
    }
    assert statuses == {
        ("fit-a", 42): "present",
        ("fit-a", 43): "unavailable",
        ("fit-b", 42): "conflict",
        ("fit-b", 43): "ready",
    }


def test_name_conflict_uses_nfc_casefold_and_accepts_valid_alternate(tmp_path):
    wanted = entry("wanted", 1, "Caf\u00e9", type_id=201)
    existing = entry("existing", 2, "Other", type_id=202)
    state = FittingsState(
        entries=(wanted, existing),
        presences=(presence(42, 10, existing, source_name="CAFE\u0301"),),
        snapshots=(snapshot(42),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    conflicted = controller.preflight_copy(["wanted"], [42])
    resolved = controller.preflight_copy(
        ["wanted"], [42], {"wanted:42": "Caf\u00e9 doctrine"}
    )

    assert conflicted["pairs"][0]["status"] == "conflict"
    assert conflicted["requires_resolution"] is True
    assert resolved["pairs"][0]["status"] == "ready"
    assert resolved["pairs"][0]["chosen_name"] == "Caf\u00e9 doctrine"
    assert resolved["write_count"] == 1


@pytest.mark.parametrize("alternate", ["", "x" * 51, "CAFE\u0301"])
def test_conflict_alternate_name_must_be_valid_and_available(tmp_path, alternate):
    wanted = entry("wanted", 1, "Caf\u00e9", type_id=201)
    existing = entry("existing", 2, "Other", type_id=202)
    state = FittingsState(
        entries=(wanted, existing),
        presences=(presence(42, 10, existing, source_name="Caf\u00e9"),),
        snapshots=(snapshot(42),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy(["wanted"], [42], {"wanted:42": alternate})

    assert result["accepted"] is False
    assert result["ticket_id"] == ""
    assert result["error"]


def test_conflict_can_be_explicitly_skipped(tmp_path):
    wanted = entry("wanted", 1, "Same", type_id=201)
    existing = entry("existing", 2, "Other", type_id=202)
    state = FittingsState(
        entries=(wanted, existing),
        presences=(presence(42, 10, existing, source_name="same"),),
        snapshots=(snapshot(42),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy(["wanted"], [42], {"wanted:42": None})

    assert result["accepted"] is True
    assert result["requires_resolution"] is False
    assert result["write_count"] == 0
    assert result["pairs"][0]["status"] == "conflict"
    assert result["pairs"][0]["skipped"] is True


@pytest.mark.parametrize(
    ("state", "authority"),
    [
        (
            FittingsState(
                entries=(
                    replace(
                        entry("fit", 1, "Fit", type_id=201),
                        deployment_template=None,
                    ),
                ),
                snapshots=(snapshot(42),),
            ),
            FakeAuthority((42,)),
        ),
        (ready_state(), FakeAuthority((42,), enabled=())),
        (
            FittingsState(
                entries=ready_state().entries,
                snapshots=(snapshot(42, age=contracts.READ_CACHE_SECONDS + 1),),
            ),
            FakeAuthority((42,)),
        ),
    ],
    ids=["non-deployable", "missing-scope", "stale-snapshot"],
)
def test_preflight_marks_ineligible_pairs_unavailable(tmp_path, state, authority):
    controller, _, _, _ = make_controller(tmp_path, state, authority=authority)

    result = controller.preflight_copy([state.entries[0].id], [42])

    assert result["pairs"][0]["status"] == "unavailable"
    assert result["write_count"] == 0


def test_known_capacity_failure_blocks_that_character(tmp_path):
    fit = ready_state().entries[0]
    state = FittingsState(
        entries=(fit,),
        snapshots=(snapshot(42, age=120),),
        intents=(
            intent(
                "capacity-failure",
                42,
                fit,
                status="failed",
                error="Character has reached the maximum number of fittings.",
            ),
        ),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy([fit.id], [42])

    assert result["pairs"][0]["status"] == "unavailable"
    assert "capacity" in result["pairs"][0]["error"].lower()


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        ("success", "", "present"),
        (
            "failed",
            "Character has reached the maximum number of fittings.",
            "unavailable",
        ),
    ],
)
def test_local_terminal_evidence_newer_than_snapshot_still_blocks(
    tmp_path, status, error, expected
):
    fit = ready_state().entries[0]
    state = FittingsState(
        entries=(fit,),
        snapshots=(snapshot(42, age=120),),
        intents=(intent("newer-evidence", 42, fit, status=status, error=error),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy([fit.id], [42])

    assert result["pairs"][0]["status"] == expected
    assert result["write_count"] == 0


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        ("success", "", "present"),
        (
            "failed",
            "Character has reached the maximum number of fittings.",
            "unavailable",
        ),
    ],
)
def test_local_terminal_evidence_tied_with_content_snapshot_still_blocks(
    tmp_path, status, error, expected
):
    fit = ready_state().entries[0]
    evidence_utc = NOW - timedelta(minutes=1)
    state = FittingsState(
        entries=(fit,),
        snapshots=(
            CharacterSnapshot(
                character_id=42,
                fetched_utc=NOW,
                content_utc=evidence_utc,
                etag='"etag-42"',
            ),
        ),
        intents=(intent("tied-evidence", 42, fit, status=status, error=error),),
    )
    controller, _, _, _ = make_controller(tmp_path, state)

    result = controller.preflight_copy([fit.id], [42])

    assert result["pairs"][0]["status"] == expected
    assert result["write_count"] == 0


def test_preflight_refuses_more_than_twenty_actual_creates(tmp_path):
    character_ids = tuple(range(100, 121))
    state = ready_state(character_ids=character_ids)
    authority = FakeAuthority(character_ids)
    controller, _, _, _ = make_controller(tmp_path, state, authority=authority)

    result = controller.preflight_copy(["fit-0"], list(character_ids))

    assert result["accepted"] is False
    assert result["error"] == "Split this copy into batches of 20 fittings or fewer."
    assert result["ticket_id"] == ""


def test_tickets_expire_after_fifteen_minutes_and_are_bounded_to_twenty(tmp_path):
    clock = [NOW]
    state = ready_state()
    controller, _, _, _ = make_controller(tmp_path, state)
    controller._now = lambda: clock[0]

    oldest = ready_ticket(controller)
    for _ in range(20):
        ready_ticket(controller)
    assert controller.start_copy(oldest)["status"] == "invalid_ticket"

    newest = ready_ticket(controller)
    clock[0] += timedelta(minutes=15, microseconds=1)
    assert controller.start_copy(newest)["status"] == "invalid_ticket"


def test_copy_progress_and_completion_carry_the_consumed_ticket_id(tmp_path):
    progress = []
    controller, _, _, _ = make_controller(
        tmp_path,
        ready_state(),
        replies=[mutation()],
        progress=progress.append,
    )
    ticket_id = ready_ticket(controller)

    controller.start_copy(ticket_id)

    copy_progress = [payload for payload in progress if payload.get("kind") == "copy"]
    assert [payload["phase"] for payload in copy_progress] == [
        "progress",
        "complete",
    ]
    assert {payload["ticket_id"] for payload in copy_progress} == {ticket_id}


def test_execution_saves_in_flight_before_the_single_post(tmp_path):
    events = []

    def recording_save(path, state):
        events.append(f"save:{state.intents[-1].status}")
        save_fittings(path, state)

    state = ready_state()
    controller, _, client, _ = make_controller(
        tmp_path, state, replies=[mutation()], save_state=recording_save
    )
    client.on_post = lambda count: events.append("post_once")
    ticket_id = ready_ticket(controller)

    result = controller.start_copy(ticket_id)

    assert events == ["save:in_flight", "post_once", "save:success"]
    assert len(client.post_calls) == 1
    assert result["operation_id"] == "operation-0"
    assert result["status"] == "complete"
    assert result["results"][0]["status"] == "success"
    assert result["results"][0]["remote_fitting_id"] == 9001


def test_outcome_replaces_a_rebuilt_intent_by_durable_key(tmp_path):
    controller, _, client, _ = make_controller(
        tmp_path, ready_state(), replies=[mutation(201, {"fitting_id": 88})]
    )

    def rebuild_immutable_state(_count):
        with controller._lock:
            controller._state = replace(
                controller._state,
                intents=tuple(replace(item) for item in controller._state.intents),
            )

    client.on_post = rebuild_immutable_state
    ticket_id = ready_ticket(controller)

    result = controller.start_copy(ticket_id)

    assert result["results"][0]["status"] == "success"
    assert controller.state.intents[-1].status == "success"
    assert controller.state.intents[-1].remote_fitting_id == 88


def test_missing_durable_intent_fails_safe_after_the_post(tmp_path):
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(201, {"fitting_id": 88})]
    )

    def drop_live_intent(_count):
        with controller._lock:
            controller._state = replace(controller._state, intents=())

    client.on_post = drop_live_intent
    ticket_id = ready_ticket(controller)

    result = controller.start_copy(ticket_id)

    assert result["status"] == "persistence_failed"
    assert result["results"][0]["status"] == "unknown"
    assert result["results"][0]["attempted"] is True
    persisted, _warnings = load_fittings(path)
    assert persisted.intents[-1].status == "unknown"
    assert persisted.intents[-1].unresolved is True


def test_failed_intent_save_sends_nothing(tmp_path):
    def refuse_save(path, state):
        raise OSError("disk full")

    controller, _, client, _ = make_controller(
        tmp_path, ready_state(), replies=[mutation()], save_state=refuse_save
    )
    ticket_id = ready_ticket(controller)

    result = controller.start_copy(ticket_id)

    assert client.post_calls == []
    assert result["status"] == "persistence_failed"
    assert result["write_count"] == 0
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["attempted"] is False


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (mutation(201, {"fitting_id": 88}), "success"),
        (mutation(201, {}), "unknown"),
        (mutation(201, {"fitting_id": True}), "unknown"),
        (mutation(408, {}), "unknown"),
        (mutation(500, {}), "unknown"),
        (mutation(None, {}, response_received=False, error="timeout"), "unknown"),
        (TimeoutError("no response"), "unknown"),
        (mutation(400, {}), "failed"),
        (mutation(403, {}), "failed"),
    ],
)
def test_outcomes_are_classified_without_retry(tmp_path, reply, expected):
    controller, _, client, _ = make_controller(tmp_path, ready_state(), replies=[reply])
    ticket_id = ready_ticket(controller)

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 1
    assert result["results"][0]["status"] == expected
    stored = controller.state.intents[-1]
    assert stored.status == expected


def test_ordinary_four_hundred_persists_outcome_before_the_next_pair(tmp_path):
    events = []

    def recording_save(path, state):
        events.append(f"save:{state.intents[-1].status}")
        save_fittings(path, state)

    controller, _, client, _ = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(400, {}), mutation(201, {"fitting_id": 2})],
        save_state=recording_save,
    )
    client.on_post = lambda count: events.append(f"post:{count}")
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 2
    assert [row["status"] for row in result["results"]] == ["failed", "success"]
    assert events == [
        "save:in_flight",
        "post:1",
        "save:failed",
        "save:in_flight",
        "post:2",
        "save:success",
    ]


@pytest.mark.parametrize("etag", ['"cached-before-post"', ""])
def test_cached_empty_200_cannot_reopen_copy_after_success_even_after_restart(
    tmp_path, etag
):
    clock = [NOW]
    controller, authority, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(), mutation()], now=lambda: clock[0]
    )
    first = controller.start_copy(ready_ticket(controller))
    assert first["results"][0]["status"] == "success"
    assert controller.preflight_copy(["fit-0"], [42])["pairs"][0]["status"] == "present"
    saved_success = load_fittings(path)[0].intents
    client.get_reply = replace(client.get_reply, etag=etag)
    clock[0] += timedelta(seconds=2)
    assert controller.refresh([42])["ok"] is True
    second = controller.preflight_copy(["fit-0"], [42])
    controller.start_copy(second["ticket_id"])
    assert len(client.post_calls) == 1
    assert second["pairs"][0]["status"] == "present"
    assert load_fittings(path)[0].intents == saved_success

    restarted = FittingsController(
        state_path=path,
        names_path=tmp_path / "names.json",
        authority=authority,
        client=client,
        now=lambda: clock[0],
    )
    authority.feature_lock = restarted._lock
    ticket = restarted.preflight_copy(["fit-0"], [42])
    restarted.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert ticket["pairs"][0]["status"] == "present"
    assert restarted.state.intents == saved_success


@pytest.mark.parametrize("status", [200, 304])
@pytest.mark.parametrize("etag", ['"before-post"', ""])
def test_only_post_horizon_full_content_releases_success_for_explicit_copy(
    tmp_path, status, etag
):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(), mutation()], now=lambda: clock[0]
    )
    controller.start_copy(ready_ticket(controller))
    clock[0] += timedelta(seconds=contracts.READ_CACHE_SECONDS)
    client.get_reply = replace(client.get_reply, status=status, etag=etag)
    assert controller.refresh([42])["ok"] is True
    assert client.get_calls[-1][1] is None
    ticket = controller.preflight_copy(["fit-0"], [42])
    assert ticket["pairs"][0]["status"] == ("ready" if status == 200 else "present")
    assert len(load_fittings(path)[0].intents) == (0 if status == 200 else 1)
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == (2 if status == 200 else 1)
    assert all(item.status == "success" for item in load_fittings(path)[0].intents)


@pytest.mark.parametrize(
    ("start_seconds", "finish_seconds"),
    [(299, 310), (-1, 310), (301, 299)],
)
def test_unsafe_get_timing_does_not_release_success(
    tmp_path, start_seconds, finish_seconds
):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(), mutation()], now=lambda: clock[0]
    )
    controller.start_copy(ready_ticket(controller))
    clock[0] = NOW + timedelta(seconds=start_seconds)
    client.on_get = lambda: clock.__setitem__(
        0, NOW + timedelta(seconds=finish_seconds)
    )
    assert controller.refresh([42])["ok"] is True
    ticket = controller.preflight_copy(["fit-0"], [42])
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert ticket["pairs"][0]["status"] == "present"
    assert load_fittings(path)[0].intents[0].status == "success"


def test_success_horizon_starts_at_completion_not_send(tmp_path):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(), mutation()], now=lambda: clock[0]
    )
    client.on_post = lambda _: clock.__setitem__(0, NOW + timedelta(seconds=60))
    controller.start_copy(ready_ticket(controller))
    clock[0] = NOW + timedelta(seconds=contracts.READ_CACHE_SECONDS)
    assert controller.refresh([42])["ok"] is True
    ticket = controller.preflight_copy(["fit-0"], [42])
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert load_fittings(path)[0].intents[0].completed_utc == NOW + timedelta(
        seconds=60
    )


def test_positive_content_immediately_establishes_presence_without_losing_protection(
    tmp_path,
):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation(), mutation()], now=lambda: clock[0]
    )
    controller.start_copy(ready_ticket(controller))
    clock[0] += timedelta(seconds=1)
    fit = controller.state.entries[0]
    body = {"fitting_id": 9001, **client.post_calls[0][1]}
    client.get_reply = replace(client.get_reply, data=[body])
    assert controller.refresh([42])["ok"] is True
    assert load_fittings(path)[0].presences[0].library_entry_id == fit.id
    # An early positive followed by another cache's older empty body is still unsafe.
    clock[0] += timedelta(seconds=1)
    client.get_reply = replace(client.get_reply, data=[])
    assert controller.refresh([42])["ok"] is True
    ticket = controller.preflight_copy([fit.id], [42])
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert load_fittings(path)[0].intents[0].status == "success"


def state_with_history(*, successes=0, failures=0, unknowns=0):
    state = ready_state(count=2, character_ids=(42, 43))
    history = tuple(
        intent(f"{status}-{index}", 43, state.entries[0], status=status)
        for status, count in (
            ("success", successes),
            ("failed", failures),
            ("unknown", unknowns),
        )
        for index in range(count)
    )
    return replace(state, intents=history)


@pytest.mark.parametrize(
    "success_count",
    [contracts.MAX_OPERATION_RECORDS, contracts.MAX_OPERATION_RECORDS + 1],
)
def test_full_or_overfull_success_evidence_refuses_before_intent_save_and_post(
    tmp_path, success_count
):
    saved = []

    def record_save(path, state):
        saved.append(state)
        save_fittings(path, state)

    state = state_with_history(successes=success_count)
    controller, _, client, path = make_controller(
        tmp_path,
        state,
        replies=[mutation()],
        save_state=record_save,
    )
    assert len(controller.state.intents) == success_count
    ticket = controller.preflight_copy(["fit-0"], [42])
    result = controller.start_copy(ticket["ticket_id"])
    assert client.post_calls == []
    assert saved == []
    assert result["results"][0]["attempted"] is False
    assert "refresh" in result["results"][0]["error"].lower()
    assert load_fittings(path)[0].intents == state.intents
    # Success is still success, not an unresolved-intent veto on Forget.
    assert controller.prepare_forget(43).applied is True


def test_each_pair_reserves_success_capacity_and_evicts_diagnostics_first(tmp_path):
    state = state_with_history(
        successes=contracts.MAX_OPERATION_RECORDS - 1,
        failures=3,
        unknowns=contracts.MAX_OPERATION_RECORDS + 1,
    )
    candidates = []

    def record_save(path, candidate):
        candidates.append(candidate)
        save_fittings(path, candidate)

    controller, _, client, path = make_controller(
        tmp_path,
        state,
        replies=[mutation(), mutation()],
        save_state=record_save,
    )
    # Both pairs were preflighted together, before the first consumed the last slot.
    ticket = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])
    result = controller.start_copy(ticket)
    assert len(client.post_calls) == 1
    assert [row["attempted"] for row in result["results"]] == [True, False]
    assert result["results"][0]["status"] == "success"
    assert "refresh" in result["results"][1]["error"].lower()
    assert len(candidates) == 2  # durable in_flight, then its success; no second intent
    loaded, _ = load_fittings(path)
    assert loaded == controller.state
    assert (
        sum(item.status == "success" for item in loaded.intents)
        == contracts.MAX_OPERATION_RECORDS
    )
    assert (
        sum(item.unresolved for item in loaded.intents)
        == contracts.MAX_OPERATION_RECORDS + 1
    )
    assert not any(item.status == "failed" for item in loaded.intents)


def test_diagnostic_and_unresolved_history_do_not_consume_success_capacity(tmp_path):
    state = state_with_history(
        failures=contracts.MAX_OPERATION_RECORDS,
        unknowns=contracts.MAX_OPERATION_RECORDS + 1,
    )
    controller, _, client, path = make_controller(tmp_path, state, replies=[mutation()])
    result = controller.start_copy(ready_ticket(controller))
    assert result["results"][0]["status"] == "success"
    assert len(client.post_calls) == 1
    loaded, _ = load_fittings(path)
    assert loaded == controller.state
    assert (
        sum(item.unresolved for item in loaded.intents)
        == contracts.MAX_OPERATION_RECORDS + 1
    )
    assert (
        sum(not item.unresolved for item in loaded.intents)
        == contracts.MAX_OPERATION_RECORDS
    )
    assert loaded.intents[-1].status == "success"


@pytest.mark.parametrize("positive", [False, True])
def test_qualifying_refresh_releases_evidence_capacity_and_keeps_safe_operations_available(
    tmp_path, positive
):
    clock = [NOW]
    state = state_with_history(successes=contracts.MAX_OPERATION_RECORDS)
    controller, _, client, path = make_controller(
        tmp_path, state, replies=[mutation()], now=lambda: clock[0]
    )
    blocked = controller.preflight_copy(["fit-0"], [42])
    result = controller.start_copy(blocked["ticket_id"])
    assert result["results"][0]["attempted"] is False
    assert len(client.post_calls) == 0
    # The refusals do not prevent refresh, including refresh of another character.
    clock[0] += timedelta(seconds=contracts.READ_CACHE_SECONDS)
    if positive:
        fit = state.entries[0]
        client.get_reply = replace(
            client.get_reply,
            data=[
                {
                    "fitting_id": 9001,
                    "name": fit.preferred_name,
                    "description": fit.preferred_description,
                    "ship_type_id": fit.content.ship_type_id,
                    "items": [{"flag": "HiSlot0", "quantity": 1, "type_id": 200}],
                }
            ],
        )
    assert controller.refresh([43])["ok"] is True
    assert load_fittings(path)[0].intents == ()
    assert bool(load_fittings(path)[0].presences) is positive
    client.get_reply = replace(client.get_reply, data=[])
    assert controller.refresh([42])["ok"] is True
    result = controller.start_copy(ready_ticket(controller))
    assert result["results"][0]["status"] == "success"
    assert len(client.post_calls) == 1
    assert len(load_fittings(path)[0].intents) == 1


def test_failed_reconciliation_save_retains_success_and_blocks_duplicate(tmp_path):
    clock = [NOW]
    candidates = []

    def save_until_refresh(path, state):
        candidates.append(state)
        if clock[0] > NOW:
            raise OSError("disk full")
        save_fittings(path, state)

    controller, _, client, path = make_controller(
        tmp_path,
        ready_state(),
        replies=[mutation(), mutation()],
        now=lambda: clock[0],
        save_state=save_until_refresh,
    )
    controller.start_copy(ready_ticket(controller))
    before = load_fittings(path)[0]
    clock[0] += timedelta(seconds=contracts.READ_CACHE_SECONDS)
    assert controller.refresh([42])["ok"] is False
    assert candidates[-1].intents == ()  # attempted retirement did not commit
    assert controller.state == load_fittings(path)[0] == before
    ticket = controller.preflight_copy(["fit-0"], [42])
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert ticket["pairs"][0]["status"] == "present"


@pytest.mark.parametrize(
    "first_response", [mutation(400), mutation(response_received=False)]
)
def test_non_success_does_not_consume_the_last_success_slot(tmp_path, first_response):
    state = state_with_history(successes=contracts.MAX_OPERATION_RECORDS - 1)
    controller, _, client, path = make_controller(
        tmp_path,
        state,
        replies=[first_response, mutation()],
    )
    result = controller.start_copy(ready_ticket(controller, fit_ids=["fit-0", "fit-1"]))
    assert result["results"][1]["status"] == "success"
    assert len(client.post_calls) == 2
    loaded, _ = load_fittings(path)
    assert loaded == controller.state
    assert (
        sum(item.status == "success" for item in loaded.intents)
        == contracts.MAX_OPERATION_RECORDS
    )
    assert sum(item.unresolved for item in loaded.intents) == (
        0 if first_response.response_received else 1
    )


def test_rolled_back_post_completion_cannot_shorten_success_horizon(tmp_path):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path,
        ready_state(),
        replies=[mutation(), mutation()],
        now=lambda: clock[0],
    )
    client.on_post = lambda _: clock.__setitem__(0, NOW - timedelta(seconds=60))
    controller.start_copy(ready_ticket(controller))
    clock[0] = NOW + timedelta(seconds=contracts.READ_CACHE_SECONDS - 1)
    assert controller.refresh([42])["ok"] is True
    ticket = controller.preflight_copy(["fit-0"], [42])
    controller.start_copy(ticket["ticket_id"])
    assert len(client.post_calls) == 1
    assert len(load_fittings(path)[0].intents) == 1


def test_library_deletion_cannot_discard_protective_success(tmp_path):
    clock = [NOW]
    controller, _, client, path = make_controller(
        tmp_path, ready_state(), replies=[mutation()], now=lambda: clock[0]
    )
    controller.start_copy(ready_ticket(controller))
    before = load_fittings(path)[0]
    assert controller.delete_entry("fit-0") is False
    assert load_fittings(path)[0] == before
    clock[0] += timedelta(seconds=contracts.READ_CACHE_SECONDS)
    assert controller.refresh([42])["ok"] is True
    assert controller.delete_entry("fit-0") is True
    assert not any(item.id == "fit-0" for item in load_fittings(path)[0].entries)
    assert len(client.post_calls) == 1


def test_durable_success_blocks_an_immediate_duplicate_copy(tmp_path):
    state = replace(ready_state(), snapshots=(snapshot(42, age=1),))
    controller, _, client, _ = make_controller(
        tmp_path, state, replies=[mutation(201, {"fitting_id": 88})]
    )
    first_ticket = ready_ticket(controller)
    first = controller.start_copy(first_ticket)

    second = controller.preflight_copy(["fit-0"], [42])

    assert first["results"][0]["status"] == "success"
    assert len(client.post_calls) == 1
    assert second["write_count"] == 0
    assert second["pairs"][0]["status"] == "present"


@pytest.mark.parametrize("status", [420, 429])
def test_throttle_stops_the_remainder(tmp_path, status):
    controller, _, client, _ = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(status, {})],
    )
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 1
    assert result["status"] == "throttled"
    assert [row["status"] for row in result["results"]] == [
        "failed",
        "unattempted_throttle",
    ]


def test_cancellation_takes_effect_before_the_next_request(tmp_path):
    controller, _, client, _ = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(201, {"fitting_id": 1})],
    )
    client.on_post = lambda count: controller.cancel_copy()
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 1
    assert result["status"] == "cancelled"
    assert [row["status"] for row in result["results"]] == [
        "success",
        "cancelled",
    ]


@pytest.mark.parametrize("keyed", [False, True])
def test_a_cancel_that_beats_the_worker_to_its_ticket_still_stands(tmp_path, keyed):
    """The page sends cancel from route-leave right after confirm, so it
    can reach the bridge before the worker thread has consumed the ticket.
    The Event-based cancel was cleared by start_copy at that point, and
    the copy ran to completion under a "Cancelling" overlay. Un-keyed is
    the pre-ticket bridge shape and must behave the same."""
    controller, _, client, _ = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(201, {"fitting_id": 1}), mutation(201, {"fitting_id": 2})],
    )
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])

    assert controller.cancel_copy(ticket_id if keyed else None) is True
    result = controller.start_copy(ticket_id)

    assert client.post_calls == []
    assert result["status"] == "cancelled"
    assert [row["status"] for row in result["results"]] == ["cancelled", "cancelled"]


def test_a_keyed_cancel_stops_only_its_own_ticket(tmp_path):
    controller, _, client, _ = make_controller(
        tmp_path, ready_state(), replies=[mutation(201, {"fitting_id": 1})]
    )
    doomed = ready_ticket(controller)
    wanted = ready_ticket(controller)

    controller.cancel_copy(doomed)
    result = controller.start_copy(wanted)

    assert result["status"] == "complete"
    assert len(client.post_calls) == 1


def test_a_cancel_does_not_linger_into_the_next_copy(tmp_path):
    """An un-keyed cancel resolves to the tickets that exist when it
    arrives. A flag that stayed set until the next start would cancel a
    copy the user starts an hour later."""
    controller, _, client, _ = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(201, {"fitting_id": 1}), mutation(201, {"fitting_id": 2})],
    )
    first = controller.start_copy(ready_ticket(controller, fit_ids=["fit-0"]))
    assert first["status"] == "complete"

    controller.cancel_copy()  # Route-leave after a copy already finished.
    second = controller.start_copy(ready_ticket(controller, fit_ids=["fit-1"]))

    assert second["status"] == "complete"
    assert len(client.post_calls) == 2


def test_a_cancel_for_a_finished_ticket_is_forgotten(tmp_path):
    controller, _, _client, _ = make_controller(
        tmp_path, ready_state(), replies=[mutation(201, {"fitting_id": 1})]
    )
    ticket_id = ready_ticket(controller)
    controller.cancel_copy(ticket_id)
    controller.start_copy(ticket_id)

    assert controller._cancelled_tickets == set()
    assert controller._active_copy_ticket is None


def test_outcome_save_failure_stops_and_retains_in_flight_safety_key(tmp_path):
    saves = 0

    def fail_second_save(path, state):
        nonlocal saves
        saves += 1
        if saves == 2:
            raise OSError("disk full after response")
        save_fittings(path, state)

    controller, _, client, path = make_controller(
        tmp_path,
        ready_state(count=2),
        replies=[mutation(201, {"fitting_id": 1})],
        save_state=fail_second_save,
    )
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 1
    assert result["status"] == "persistence_failed"
    assert result["write_count"] == 1
    assert [row["status"] for row in result["results"]] == ["unknown", "failed"]
    assert result["results"][0]["attempted"] is True
    assert result["results"][1]["attempted"] is False
    assert "not attempted" in result["results"][1]["error"].lower()
    loaded, _ = load_fittings(path)
    assert loaded.intents[-1].status == "unknown"
    assert loaded.intents[-1].content == controller.state.entries[0].content


def test_execution_revalidation_only_reduces_ticket_writes(tmp_path):
    state = ready_state(count=2)
    controller, _, client, _ = make_controller(
        tmp_path, state, replies=[mutation(201, {"fitting_id": 2})]
    )
    ticket_id = ready_ticket(controller, fit_ids=["fit-0", "fit-1"])
    first, _second = controller.state.entries
    controller._state = replace(
        controller.state,
        presences=(presence(42, 501, first),),
    )

    result = controller.start_copy(ticket_id)

    assert len(client.post_calls) == 1
    assert result["write_count"] <= 2
    assert [row["entry_id"] for row in result["results"]] == ["fit-0", "fit-1"]
    assert [row["status"] for row in result["results"]] == ["present", "success"]
    assert all(row["entry_id"] in {"fit-0", "fit-1"} for row in result["results"])


def test_completed_history_has_an_age_cap_but_unresolved_intents_survive(tmp_path):
    fit = ready_state().entries[0]
    old = NOW - contracts.COMPLETED_OPERATION_MAX_AGE - timedelta(seconds=1)
    state = FittingsState(
        entries=(fit,),
        intents=(
            replace(
                intent("old-failed", 42, fit, status="failed"),
                created_utc=old,
                sent_utc=old,
                completed_utc=old,
            ),
            replace(
                intent("old-unknown", 42, fit),
                created_utc=old,
                sent_utc=old,
            ),
        ),
    )
    path = tmp_path / "eve_fittings.json"

    save_fittings(path, state, now=lambda: NOW)
    loaded, _ = load_fittings(path)

    assert [row.operation_id for row in loaded.intents] == ["old-unknown"]
