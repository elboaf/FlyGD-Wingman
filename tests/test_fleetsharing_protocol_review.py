"""Regressions for the adjudicated v2 codec review — real closed payloads."""

import copy
from dataclasses import replace

import pytest
from test_fleetsharing_protocol import FIXTURE, SOURCE, STOP

from wingman.fleetsharing import protocol as p

ORIGIN = "https://relay.example.test"
OTHER_UUID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def automatic_noop():
    payload = copy.deepcopy(FIXTURE["valid"]["automatic_result"])
    command = p.parse_automatic_command(payload["receipt"]["command"])
    payload.update(result="already_off", receipt=None)
    return payload, replace(command, expected_revision=9)


def stop_noop():
    payload = copy.deepcopy(FIXTURE["valid"]["source_stop_result"])
    payload.update(
        result="already_stopped", receipt=None, automatic_effect="current_already_off"
    )
    return payload, p.parse_source_command(STOP)


def newer_on():
    status = copy.deepcopy(FIXTURE["valid"]["automatic_get"]["status"])
    status["consent"].update(generation=8, revision=10)
    status["sources"] = []
    status["readiness"] = "waiting_for_fleet"
    return status


def paired_source_result():
    payload = copy.deepcopy(FIXTURE["valid"]["source_stop_result"])
    source_id = "abcdefab-abcd-4abc-8abc-abcdefabcdef"
    payload["source"]["source_id"] = source_id
    payload["receipt"]["source"]["source_id"] = source_id
    payload["receipt"]["command"]["source_id"] = source_id
    return payload, p.parse_source_command(payload["receipt"]["command"])


def paired_consent_reply(kind):
    base = "source_stop_result" if kind.startswith("source") else "automatic_result"
    payload = copy.deepcopy(FIXTURE["valid"][base])
    parser = (
        p.parse_source_result if kind.startswith("source") else p.parse_automatic_result
    )
    if kind.endswith("receipt_get"):
        payload = {key: payload[key] for key in ("protocol", "receipt", "status")}
        parser = p.parse_receipt_get
    return payload, parser


@pytest.mark.parametrize("location", ["command", "returned_source"])
def test_paired_source_uuid_case_is_identity_only_and_preserves_spelling(location):
    payload, command = paired_source_result()
    original_id = command.source_id
    if location == "command":
        command = replace(command, source_id=original_id.upper())
    else:
        payload["source"]["source_id"] = original_id.upper()
    result = p.parse_source_result(payload, command)
    assert result.source.source_id == payload["source"]["source_id"]
    assert result.receipt.source.source_id == original_id
    assert result.receipt.command.source_id == original_id
    assert p.source_command_body(command)["source_id"] == command.source_id
    assert p.uuid(original_id.upper()) == original_id.upper()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", OTHER_UUID),
        ("expected_generation", 2),
        ("intent_created_at", "2026-09-07T11:59:59.999Z"),
        ("request_id", OTHER_UUID),
    ],
)
def test_paired_stop_command_nonidentity_fields_still_match_exactly(field, value):
    payload, command = paired_source_result()
    with pytest.raises(ValueError):
        p.parse_source_result(payload, replace(command, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", OTHER_UUID),
        ("generation", 2),
        ("character_id", 43),
        ("reason", "expired"),
    ],
)
def test_paired_returned_source_nonidentity_fields_still_match_exactly(field, value):
    payload, command = paired_source_result()
    payload["source"][field] = value
    with pytest.raises(ValueError):
        p.parse_source_result(payload, command)


@pytest.mark.parametrize(
    "kind",
    [
        "automatic_result",
        "source_result",
        "automatic_receipt_get",
        "source_receipt_get",
    ],
)
def test_paired_consent_uuid_case_preserves_both_historical_and_live_spelling(kind):
    payload, parser = paired_consent_reply(kind)
    original_id = payload["status"]["consent"]["approving_device_id"]
    payload["status"]["consent"]["approving_device_id"] = original_id.upper()
    result = parser(payload)
    assert result.status.consent.approving_device_id == original_id.upper()
    historical = (
        result.receipt.consent if kind.startswith("source") else result.receipt.result
    )
    assert historical.approving_device_id == original_id


@pytest.mark.parametrize(
    "kind",
    [
        "automatic_result",
        "source_result",
        "automatic_receipt_get",
        "source_receipt_get",
    ],
)
@pytest.mark.parametrize(
    "field,value",
    [
        ("approving_device_id", OTHER_UUID),
        ("generation", 8),
        ("approved_at", "2026-09-07T10:59:59.999Z"),
        ("closed_reason", "approver_revoked"),
    ],
)
def test_paired_consent_different_identity_cas_date_or_reason_still_rejects(
    kind, field, value
):
    payload, parser = paired_consent_reply(kind)
    payload["status"]["consent"][field] = value
    with pytest.raises(ValueError):
        parser(payload)


@pytest.mark.parametrize(
    "effect", ["manual_only", "current_already_off", "older_generation_only"]
)
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_stop_noop_exact_source_cas(effect, offset):
    payload, command = stop_noop()
    payload["source"]["generation"] = 2
    payload["automatic_effect"] = effect
    command = replace(command, expected_generation=2 + offset)
    if effect == "manual_only":
        payload["source"]["automatic"] = None
        command = replace(command, expected_automatic=None)
    elif effect == "older_generation_only":
        payload["status"] = newer_on()
    if offset:
        with pytest.raises(ValueError):
            p.parse_source_result(payload, command)
    else:
        assert p.parse_source_result(payload, command).source.generation == 2


@pytest.mark.parametrize("outcome", ["applied", "replayed"])
def test_receipt_terminal_generation_may_increment_but_noop_cannot(outcome):
    payload, command = paired_source_result()
    payload["result"] = outcome
    payload["source"]["generation"] = 2
    payload["receipt"]["source"]["generation"] = 2
    assert p.parse_source_result(payload, command).source.generation == 2
    payload.update(
        result="already_stopped", receipt=None, automatic_effect="current_already_off"
    )
    with pytest.raises(ValueError):
        p.parse_source_result(payload, command)


@pytest.mark.parametrize("outcome", ["applied", "replayed"])
def test_unknown_cancelled_requires_receipt_not_noop_cas_exception(outcome):
    payload, command = paired_source_result()
    command = replace(command, expected_generation=0, expected_automatic=None)
    payload.update(result=outcome, automatic_effect="unknown_cancelled")
    payload["source"]["automatic"] = None
    payload["receipt"]["source"]["automatic"] = None
    payload["receipt"]["automatic_effect"] = "unknown_cancelled"
    payload["receipt"]["command"] = p.source_command_body(command)
    result = p.parse_source_result(payload, command)
    assert result.source.generation == 1
    assert result.receipt.command.expected_generation == 0
    payload.update(result="already_stopped", receipt=None)
    with pytest.raises(ValueError):
        p.parse_source_result(payload, command)


def test_wire_names_are_exact_nfc_not_casefold_identity():
    value = {
        "kind": "POINT",
        "observations": [
            {"name": "Pilot", "age_ms": 0},
            {"name": "PILOT", "age_ms": 1},
        ],
    }
    assert p.parse_effect(value).observations == (
        p.Observation("Pilot", 0),
        p.Observation("PILOT", 1),
    )
    value["observations"][1]["name"] = "Pilot"
    with pytest.raises(ValueError):
        p.parse_effect(value)


def test_full_tackle_capacity_remains_parseable_and_independent_by_kind():
    observations = [{"name": str(index), "age_ms": 29999} for index in range(8)] + [
        {"name": None, "age_ms": 29999}
    ]
    row = {
        "character_id": 1,
        "outgoing_dps": None,
        "incoming_dps": 0,
        "activity_age_ms": 29999,
        "effects": [
            {"kind": "SCRAM", "observations": observations},
            {"kind": "POINT", "observations": observations},
            {"kind": "NEUT", "observations": [{"name": None, "age_ms": 29999}]},
        ],
    }
    parsed = p.parse_combat_put({"protocol": 2, "sampled_at_ms": 29999, "rows": [row]})
    assert sum(len(effect.observations) for effect in parsed.rows[0].effects) == 19


@pytest.mark.parametrize("field", ["sources", "characters"])
def test_sources_retained_and_character_catalogue_bound_is_256(field):
    payload = {"protocol": 2, "sources": [], "characters": []}
    if field == "sources":
        entries = [
            {**SOURCE, "source_id": f"{index:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}
            for index in range(257)
        ]
    else:
        row = FIXTURE["valid"]["sources"]["characters"][0]
        entries = [{**row, "character_id": index + 1} for index in range(257)]
    payload[field] = entries[:256]
    assert len(getattr(p.parse_sources(payload), field)) == 256
    for bad in (entries, list(reversed(entries[:2])), [entries[0], entries[0]]):
        payload[field] = bad
        with pytest.raises(ValueError):
            p.parse_sources(payload)


def test_status_current_sources_sorted_unique_and_bounded():
    status = newer_on()
    sources = [
        {
            "source_id": f"{index:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "source_generation": 1,
            "consent_generation": 8,
        }
        for index in range(17)
    ]
    status["sources"] = sources[:16]
    assert len(p.parse_automatic_status(status).sources) == 16
    for bad in (sources, list(reversed(sources[:2])), [sources[0], sources[0]]):
        status["sources"] = bad
        with pytest.raises(ValueError):
            p.parse_automatic_status(status)


def test_on_receipt_checked_increment_and_terminal_counter_boundaries():
    receipt = copy.deepcopy(FIXTURE["valid"]["automatic_result"]["receipt"])
    receipt["command"]["enabled"] = True
    receipt["result"].update(
        generation=8, enabled=True, disabled_at=None, closed_reason=None
    )
    assert p.parse_automatic_receipt(receipt).result.generation == 8
    for key, value in (("generation", 7), ("revision", 10), ("enabled", False)):
        bad = copy.deepcopy(receipt)
        bad["result"][key] = value
        with pytest.raises(ValueError):
            p.parse_automatic_receipt(bad)
    # Scalar command parsing does not perform runtime terminal-reservation admission.
    receipt["command"].update(
        expected_generation=9007199254740991, expected_revision=9007199254740991
    )
    assert (
        p.parse_automatic_command(receipt["command"]).expected_revision
        == 9007199254740991
    )
    receipt["result"].update(generation=9007199254740992, revision=9007199254740992)
    with pytest.raises(ValueError):
        p.parse_automatic_receipt(receipt)


@pytest.mark.parametrize(
    "effect",
    [
        "manual_only",
        "unknown_cancelled",
        "disabled_current",
        "current_already_off",
        "older_generation_only",
    ],
)
def test_stop_receipt_effect_binding_and_command_context(effect):
    receipt = copy.deepcopy(FIXTURE["valid"]["source_stop_result"]["receipt"])
    receipt["automatic_effect"] = effect
    if effect in ("manual_only", "unknown_cancelled"):
        receipt["source"]["automatic"] = None
        receipt["command"]["expected_automatic"] = None
    if effect == "unknown_cancelled":
        receipt["command"]["expected_generation"] = 0
    elif effect == "older_generation_only":
        receipt["consent"].update(generation=8, revision=10)
    assert p.parse_source_stop_receipt(receipt).automatic_effect == effect
    for key, value in (
        ("source_id", OTHER_UUID),
        ("expected_automatic", {"consent_generation": 9}),
        ("intent_created_at", "tomorrow"),
    ):
        bad = copy.deepcopy(receipt)
        bad["command"][key] = value
        with pytest.raises(ValueError):
            p.parse_source_stop_receipt(bad)


@pytest.mark.parametrize("kind", ["on", "off", "source_stop"])
def test_receipt_acceptance_never_precedes_immutable_intent(kind):
    base = "source_stop_result" if kind == "source_stop" else "automatic_result"
    receipt = copy.deepcopy(FIXTURE["valid"][base]["receipt"])
    if kind == "on":
        receipt["command"]["enabled"] = True
        receipt["result"].update(
            generation=8, enabled=True, disabled_at=None, closed_reason=None
        )
    receipt["command"]["intent_created_at"] = "2026-09-07T12:00:00.001Z"
    parser = (
        p.parse_source_stop_receipt
        if kind == "source_stop"
        else p.parse_automatic_receipt
    )
    with pytest.raises(ValueError):
        parser(receipt)


@pytest.mark.parametrize("kind", ["on", "source_stop"])
def test_short_lived_receipt_acceptance_is_strictly_before_sixty_seconds(kind):
    base = "source_stop_result" if kind == "source_stop" else "automatic_result"
    receipt = copy.deepcopy(FIXTURE["valid"][base]["receipt"])
    if kind == "on":
        receipt["command"]["enabled"] = True
        receipt["result"].update(
            generation=8, enabled=True, disabled_at=None, closed_reason=None
        )
    parser = (
        p.parse_source_stop_receipt
        if kind == "source_stop"
        else p.parse_automatic_receipt
    )
    receipt["command"]["intent_created_at"] = "2026-09-07T11:59:00.001Z"
    assert parser(receipt).accepted_at == "2026-09-07T12:00:00.000Z"
    receipt["command"]["intent_created_at"] = "2026-09-07T11:59:00.000Z"
    with pytest.raises(ValueError):
        parser(receipt)


def test_days_old_off_receipt_uses_historical_acceptance_not_live_status_time():
    payload = copy.deepcopy(FIXTURE["valid"]["automatic_result"])
    payload["receipt"]["command"]["intent_created_at"] = "2026-09-01T12:00:00.000Z"
    payload.update(result="replayed", status=newer_on())
    command = p.parse_automatic_command(payload["receipt"]["command"])
    result = p.parse_automatic_result(payload, command)
    assert result.receipt.accepted_at == "2026-09-07T12:00:00.000Z"
    assert result.receipt.result.enabled is False
    assert result.status.consent.enabled is True


def test_paused_source_reason_and_expiry_are_independent():
    for expiry in (None, "2026-09-07T12:01:00.000Z"):
        source = {
            **SOURCE,
            "state": "paused",
            "reason": "token_invalid",
            "pending_expires_at": expiry,
        }
        assert p.parse_source(source).reason == "token_invalid"
    with pytest.raises(ValueError):
        p.parse_source({**SOURCE, "reason": None})


@pytest.mark.parametrize("enabled", [False, True])
def test_old_stop_receipt_can_observe_newer_on_or_off(enabled):
    receipt = copy.deepcopy(FIXTURE["valid"]["source_stop_result"]["receipt"])
    receipt["automatic_effect"] = "older_generation_only"
    receipt["consent"].update(generation=8, revision=10)
    if enabled:
        receipt["consent"].update(enabled=True, disabled_at=None, closed_reason=None)
    # Terminal transitions may increment the source counter; it is not the request CAS.
    receipt["source"]["generation"] = 2
    result = p.parse_source_stop_receipt(receipt)
    assert result.consent.enabled is enabled
    assert result.source.generation == 2
    receipt["consent"]["generation"] = 7
    with pytest.raises(ValueError):
        p.parse_source_stop_receipt(receipt)


@pytest.mark.parametrize("with_command", [False, True])
@pytest.mark.parametrize(
    "bad",
    [
        "active",
        "current_on",
        "disabled_current",
        "manual_only",
        "older_generation_only",
    ],
)
def test_stopped_noop_rejects_inconsistent_closed_result(bad, with_command):
    payload, command = stop_noop()
    if bad == "active":
        payload["source"].update(state="active", reason=None)
    elif bad == "current_on":
        payload["status"] = copy.deepcopy(FIXTURE["valid"]["automatic_get"]["status"])
    else:
        payload["automatic_effect"] = bad
    with pytest.raises(ValueError):
        p.parse_source_result(payload, command if with_command else None)


@pytest.mark.parametrize("bad", ["source", "binding", "request", "unknown_generation"])
def test_stopped_noop_requires_request_context(bad):
    payload, command = stop_noop()
    if bad == "source":
        command = replace(command, source_id=OTHER_UUID)
    elif bad == "binding":
        command = replace(command, expected_automatic=None)
    elif bad == "request":
        command = replace(command, request_id=OTHER_UUID)
    else:
        payload["source"]["automatic"] = None
        payload["automatic_effect"] = "unknown_cancelled"
        command = replace(command, expected_automatic=None)
    with pytest.raises(ValueError):
        p.parse_source_result(payload, command)


@pytest.mark.parametrize("mode", ["current_off", "older_on", "manual"])
def test_stopped_noop_accepts_exact_binding_and_preserves_current_status(mode):
    payload, command = stop_noop()
    if mode == "older_on":
        payload["automatic_effect"] = "older_generation_only"
        payload["status"] = newer_on()
    elif mode == "manual":
        payload["automatic_effect"] = "manual_only"
        payload["source"]["automatic"] = None
        command = replace(command, expected_automatic=None)
    result = p.parse_source_result(payload, command)
    assert result.receipt is None and result.source.state == "ended"
    assert result.status.consent.enabled is (mode == "older_on")


@pytest.mark.parametrize("with_command", [False, True])
def test_automatic_already_off_rejects_current_enabled(with_command):
    payload, command = automatic_noop()
    payload["status"] = newer_on()
    with pytest.raises(ValueError):
        p.parse_automatic_result(payload, command if with_command else None)


@pytest.mark.parametrize(
    "mutation",
    [{"enabled": True}, {"expected_generation": 6}, {"expected_revision": 8}],
)
def test_automatic_already_off_requires_off_and_same_cas(mutation):
    payload, command = automatic_noop()
    with pytest.raises(ValueError):
        p.parse_automatic_result(payload, replace(command, **mutation))


def test_automatic_noop_and_historical_receipt_are_not_interchangeable():
    payload, command = automatic_noop()
    result = p.parse_automatic_result(payload, command)
    assert result.receipt is None and result.status.consent.revision == 9
    historical = copy.deepcopy(FIXTURE["valid"]["automatic_result"])
    historical.update(result="replayed", status=newer_on())
    result = p.parse_automatic_result(historical, replace(command, expected_revision=8))
    assert result.receipt.result.enabled is False
    assert result.status.consent.enabled is True
    assert result.status.consent.revision == 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("readiness", "ready"),
        ("recovery_action", "wait"),
        ("retry_at", "2026-09-07T12:01:00.000Z"),
        ("approver", "none"),
    ],
)
def test_positive_disabled_status_requires_off_observation(field, value):
    status = copy.deepcopy(FIXTURE["valid"]["automatic_result"]["status"])
    status[field] = value
    with pytest.raises(ValueError):
        p.parse_automatic_status(status)


@pytest.mark.parametrize("field,value", [("readiness", "off"), ("approver", "none")])
def test_enabled_status_cannot_claim_absent_or_off(field, value):
    status = newer_on()
    status[field] = value
    with pytest.raises(ValueError):
        p.parse_automatic_status(status)


@pytest.mark.parametrize(
    "readiness,approver,action",
    [
        ("ready", "this_device", "none"),
        ("verifying", "this_device", "none"),
        ("waiting_for_fleet", "this_device", "none"),
        ("global_disabled", "this_device", "wait"),
        ("capacity_limited", "this_device", "wait"),
        ("reconnecting", "this_device", "wait"),
        ("member_required", "this_device", "restore_membership"),
        ("authorization_required", "this_device", "authorize_fleet_read"),
        ("authorization_required", "revoked", "reauthorize_automatic"),
    ],
)
def test_status_enforces_only_documented_action_mapping(readiness, approver, action):
    status = newer_on()
    status.update(readiness=readiness, approver=approver, recovery_action=action)
    assert p.parse_automatic_status(status).recovery_action == action
    status["recovery_action"] = "wait" if action == "none" else "none"
    with pytest.raises(ValueError):
        p.parse_automatic_status(status)


def test_waiting_for_grant_has_no_invented_action_mapping():
    for action in ("none", "wait", "authorize_fleet_read"):
        status = newer_on()
        status.update(readiness="waiting_for_grant", recovery_action=action)
        assert p.parse_automatic_status(status).recovery_action == action


def test_snapshot_import_alias_retains_server_time_authority():
    result = p.parse_observed_snapshot(FIXTURE["valid"]["combat_get"])
    assert isinstance(result, p.CombatSnapshot)
    assert result.server_time_ms == 12500


def test_identity_approval_and_observed_name_policies_stay_separate():
    from wingman import combatprofile

    assert p.text("\U0001fae9" * 200) == "\U0001fae9" * 200
    assert p.text(" <Identity> e\u0301 ") == " <Identity> e\u0301 "
    with pytest.raises(ValueError):
        p.text("A" * 201)
    assert combatprofile.validate_observed_name("A" * 64)
    assert not combatprofile.validate_observed_name("A" * 65)
    assert not combatprofile.validate_observed_name("<Identity>")
    assert not combatprofile.validate_observed_name("e\u0301")
    for length in (200, 201, 2048):
        url = "/" + "a" * (length - 1)
        value = {**FIXTURE["valid"]["pairing_begun"], "approval_url": url}
        assert p.parse_pairing_begun(value, origin=ORIGIN).approval_url == ORIGIN + url
    with pytest.raises(ValueError):
        p.parse_pairing_begun(
            {**FIXTURE["valid"]["pairing_begun"], "approval_url": "/" + "a" * 2048},
            origin=ORIGIN,
        )


def test_identity_codec_uses_public_frozen_category_seam(monkeypatch):
    from wingman import combatprofile

    original = combatprofile.is_forbidden_scalar
    # A caller regression: bypassing this shared seam would accept the sentinel.
    monkeypatch.setattr(
        combatprofile, "is_forbidden_scalar", lambda cp: cp == 65 or original(cp)
    )
    assert p.text("Bob") == "Bob"
    with pytest.raises(ValueError):
        p.text("Alice")


def test_pairing_relative_url_is_stored_as_same_origin_absolute():
    value = FIXTURE["valid"]["pairing_begun"]
    result = p.parse_pairing_begun(value, origin="https://RELAY.example.test:443/")
    assert result.approval_url == ORIGIN + value["approval_url"]


@pytest.mark.parametrize(
    "url",
    [
        "https://other.test/pair",
        "http://relay.example.test/pair",
        "https://user@relay.example.test/pair",
        "//other.test/pair",
        "///other.test/pair",
        "javascript:alert(1)",
        "/pair\\evil",
        "/pair\tevil",
    ],
)
def test_pairing_untrusted_url_never_accepted_even_without_origin(url):
    value = {**FIXTURE["valid"]["pairing_begun"], "approval_url": url}
    with pytest.raises(ValueError):
        p.parse_pairing_begun(value, origin=ORIGIN)
    with pytest.raises((ValueError, TypeError)):
        p.parse_pairing_begun(value)
