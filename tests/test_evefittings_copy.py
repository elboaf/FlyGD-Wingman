"""Preflight tickets and durable, one-attempt fitting copy operations."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from wingman.eveesi import MutationResponse
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
        now=lambda: NOW,
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
        snapshots=(snapshot(42),),
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


def test_durable_success_blocks_an_immediate_duplicate_copy(tmp_path):
    controller, _, client, _ = make_controller(
        tmp_path, ready_state(), replies=[mutation(201, {"fitting_id": 88})]
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
