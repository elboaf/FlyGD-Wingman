"""Legal upper-bound journals and the legacy indented encoder, test-only."""

import base64
import json
from dataclasses import replace
from uuid import UUID

from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, TOKEN
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


def legacy_bytes(state):
    return json.dumps(s._to_dict(state), indent=2, allow_nan=False).encode()


def compact_bytes(state):
    return json.dumps(
        s._to_dict(state), separators=(",", ":"), allow_nan=False
    ).encode()
