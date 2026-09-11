"""Legal upper-bound journals and the legacy indented encoder, test-only."""

import base64
import json
from dataclasses import fields, replace
from uuid import UUID

from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, TOKEN
from tests.test_fleetsharing_worker import UUID as EPOCH
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def source_id(index):
    return str(UUID(int=index + 1, version=4))


def maximal_state(*, stops=False):
    # DNS: 253 chars, labels <=63, plus longest port; session's legacy bound is
    # 128, not the modern 43-character token. Astral letters cost 12 JSON bytes.
    origin = "https://" + ".".join(["a" * 63] * 3 + ["a" * 61]) + ":65535"
    url = origin + "/" + "\U00010000" * (2048 - len(origin) - 1)
    identity = replace(
        PAIRED_STATE.identity,
        protected_private_key_b64=base64.b64encode(bytes(6144)).decode(),
    )
    return replace(
        PAIRED_STATE,
        identity=identity,
        relay_origin=origin,
        session_id="s" * 128,
        last_revision=p.INT4_MAX,
        device_id=source_id(0),
        session_expires_at=DATE,
        feature_enabled=False,
        approved_capabilities=(p.SHARED_CAPABILITY,),
        session_approved_capabilities=(p.SHARED_CAPABILITY,),
        acknowledged_capabilities=(p.SHARED_CAPABILITY,),
        observed_participation=p.Participation(False, p.INT4_MAX),
        pending_recovery=s.PendingRecovery(
            TOKEN, DATE, p.RecoveryChallenge(source_id(0), TOKEN, TOKEN, DATE)
        ),
        pending_pairing=s.PendingPairing("initial", "p" * 128, url, DATE, False),
        pending_participation=s.PendingParticipation(
            source_id(0), False, p.INT4_MAX - 1, False
        ),
        auth_pause=s.AuthPause("account_ineligible", DATE),
        pending_source_commands=tuple(
            p.StopSource(source_id(i), p.INT4_MAX - 1)
            if stops
            else p.StartSource(source_id(i), p.JS_SAFE_MAX, source_id(0), DATE)
            for i in range(p.MAX_SOURCE_INTENTS)
        ),
    )


def fixture_bytes(state, *, indented=False):
    """Independent encoder for the ASCII Start journals used by preparation.

    Spell the persisted shapes here, not through the writer or capacity policy:
    a serializer regression must not move both the fixture and its byte oracle.
    Pairing, auth pauses, Stops and non-ASCII fixtures are intentionally outside
    this builder's scope; the existing maximum/UTF-8 tests cover those shapes.
    """
    assert type(state) is s.SharingState
    assert type(state.identity) is s.DeviceIdentity
    assert state.pending_pairing is None and state.auth_pause is None
    identity = {
        "protected_private_key_b64": state.identity.protected_private_key_b64,
        "public_key_spki_b64": state.identity.public_key_spki_b64,
    }
    observed = state.observed_participation
    assert observed is None or type(observed) is p.Participation
    observation = (
        None
        if observed is None
        else {"enabled": observed.enabled, "generation": observed.generation}
    )
    pending = state.pending_participation
    assert pending is None or type(pending) is s.PendingParticipation
    participation = (
        None
        if pending is None
        else {
            "intent_id": pending.intent_id,
            "enabled": pending.enabled,
            "expected_generation": pending.expected_generation,
            "attempted": pending.attempted,
        }
    )
    recovery = state.pending_recovery
    assert recovery is None or type(recovery) is s.PendingRecovery
    challenge = recovery.challenge if recovery else None
    assert challenge is None or type(challenge) is p.RecoveryChallenge
    challenge_document = (
        None
        if challenge is None
        else {
            "challenge_id": challenge.challenge_id,
            "request_id": challenge.request_id,
            "nonce": challenge.nonce,
            "expires_at": challenge.expires_at,
        }
    )
    recovery_document = (
        None
        if recovery is None
        else {
            "request_id": recovery.request_id,
            "issued_at": recovery.issued_at,
            "challenge": challenge_document,
        }
    )
    # Check the keys actually emitted, including nested non-default metadata.
    # New dataclass fields must prompt a fixture review, not silently disappear.
    for value, document in (
        (state.identity, identity),
        (observed, observation),
        (pending, participation),
        (recovery, recovery_document),
        (challenge, challenge_document),
    ):
        if value is not None:
            assert {f.name for f in fields(value)} == set(document)
    commands = []
    for command in state.pending_source_commands:
        assert type(command) is p.StartSource, "fixture supports only Start commands"
        document = {
            "operation": "start",
            "source_id": command.source_id,
            "character_id": command.character_id,
            "character_link_epoch": command.character_link_epoch,
            "intent_created_at": command.intent_created_at,
            "expected_generation": command.expected_generation,
        }
        assert {f.name for f in fields(command)} == set(document) - {"operation"}
        commands.append(document)
    raw = {
        "version": 3,
        "identity": identity,
        "relay_origin": state.relay_origin,
        "session_id": state.session_id,
        "last_revision": state.last_revision,
        "device_id": state.device_id,
        "session_expires_at": state.session_expires_at,
        "feature_enabled": state.feature_enabled,
        "approved_capabilities": state.approved_capabilities,
        "session_approved_capabilities": state.session_approved_capabilities,
        "acknowledged_capabilities": state.acknowledged_capabilities,
        "observed_participation": observation,
        "pending_recovery": recovery_document,
        "pending_source_commands": commands,
        "pending_pairing": None,
        "pending_participation": participation,
        "auth_pause": None,
    }
    assert set(raw) == {"version", *(f.name for f in fields(s.SharingState))}
    encoding = {"indent": 2} if indented else {"separators": (",", ":")}
    text = json.dumps(raw, ensure_ascii=False, allow_nan=False, **encoding)
    assert text.isascii(), "fixture supports only ASCII values"
    return text.encode("ascii")


def start_boundary(state, *, limit=s.MAX_STATE_FILE_BYTES, indented=False):
    """Return last-fitting and next-refused prefixes, without writing either.

    Start entries only add bytes, so a bounded binary search replaces hundreds
    of prefix writes. The consumers still prove both outcomes with real I/O.
    """
    assert not state.pending_source_commands
    commands = tuple(
        p.StartSource(source_id(i), 1, EPOCH, DATE) for i in range(p.MAX_SOURCE_INTENTS)
    )

    def prefix(count):
        return replace(state, pending_source_commands=commands[:count])

    def fits(candidate):
        return len(fixture_bytes(candidate, indented=indented)) <= limit

    low, high = 0, len(commands)
    assert fits(state), "fixture base must fit"
    assert not fits(prefix(high)), "fixture must reach the byte bound before count"
    while high - low > 1:
        middle = (low + high) // 2
        if fits(prefix(middle)):
            low = middle
        else:
            high = middle
    return prefix(low), prefix(high)


def legacy_bytes(state):
    return json.dumps(s._to_dict(state), indent=2, allow_nan=False).encode()


def compact_bytes(state):
    return json.dumps(
        s._to_dict(state), separators=(",", ":"), allow_nan=False
    ).encode()
