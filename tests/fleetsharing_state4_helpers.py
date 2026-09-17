"""Independent disk fixtures: never import worker fixtures or derive legacy via save."""

import json
from copy import deepcopy

DATE = "2026-09-07T12:00:00.000Z"
EXPIRY = "2026-09-08T12:00:00.000Z"
TOKEN = "A" * 43
UUID = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
REQUEST = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CANCEL = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ORIGIN = "https://relay.example.test"
# RFC 8032 test-vector public key, not a generated key or runtime serializer.
IDENTITY = {
    "protected_private_key_b64": "cHJvdGVjdGVk",
    "public_key_spki_b64": "MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
}
LEGACY_V1 = {
    "version": 1,
    "identity": IDENTITY,
    "relay_origin": "HTTPS://Relay.Example.test:443/",
    "session_id": "old-opaque-session",
    "last_revision": 7,
}
LEGACY_V2 = {
    "version": 2,
    "identity": IDENTITY,
    "relay_origin": "HTTPS://Relay.Example.test:443/",
    "session_id": "old-opaque-session",
    "last_revision": 7,
    "device_id": UUID,
    "session_expires_at": DATE,
    "feature_enabled": False,
    "approved_capabilities": ["shared-source-v1"],
    "session_approved_capabilities": ["shared-source-v1"],
    "acknowledged_capabilities": [],
    "observed_participation": {"enabled": True, "generation": 3},
    "pending_recovery": {
        "request_id": TOKEN,
        "issued_at": DATE,
        "challenge": {
            "challenge_id": UUID,
            "request_id": TOKEN,
            "nonce": TOKEN,
            "expires_at": DATE,
        },
    },
    "pending_source_commands": [
        {
            "operation": "start",
            "source_id": UUID,
            "expected_generation": 0,
            "character_id": 42,
            "character_link_epoch": UUID,
            "intent_created_at": DATE,
        },
        {"operation": "stop", "source_id": REQUEST, "expected_generation": 6},
    ],
}
LEGACY_V3 = {
    **LEGACY_V2,
    "version": 3,
    "pending_pairing": {
        "mode": "upgrade",
        "pairing_id": "old.opaque-pair-id",
        "approval_url": ORIGIN + "/approve",
        "expires_at": DATE,
        "completion_attempted": True,
    },
    "pending_participation": {
        "intent_id": UUID,
        "enabled": False,
        "expected_generation": None,
        "attempted": True,
    },
    "auth_pause": {"result": "account_ineligible", "retry_not_before": DATE},
}
ACTIVE_V4 = {
    "version": 4,
    "identity": IDENTITY,
    "relay_origin": ORIGIN,
    "session_id": TOKEN,
    "last_revision": 7,
    "device_id": UUID,
    "session_expires_at": DATE,
    "feature_enabled": False,
    "approved_capabilities": ["shared-source-v1", "combat-v2"],
    "session_approved_capabilities": ["shared-source-v1", "combat-v2"],
    "acknowledged_capabilities": [],
    "observed_participation": {"enabled": False, "generation": 3},
    "pending_recovery": {
        "request_id": TOKEN,
        "issued_at": DATE,
        "challenge": LEGACY_V2["pending_recovery"]["challenge"],
        "completion_attempted": True,
    },
    "pending_source_commands": [
        {"protocol": 2, **LEGACY_V2["pending_source_commands"][0]},
        {
            "protocol": 2,
            "operation": "stop",
            "source_id": REQUEST,
            "request_id": CANCEL,
            "intent_created_at": DATE,
            "expected_generation": 6,
            "expected_automatic": {"consent_generation": 5},
        },
    ],
    "pending_pairing": {
        "mode": "upgrade",
        "pairing_id": UUID,
        "approval_url": ORIGIN + "/approve",
        "expires_at": DATE,
        "completion_attempted": True,
        "requested_capabilities": ["shared-source-v1", "combat-v2"],
    },
    "pending_participation": {
        "intent_id": UUID,
        "enabled": False,
        "expected_generation": 3,
        "attempted": True,
    },
    "auth_pause": {"result": "account_ineligible", "retry_not_before": DATE},
    "cutover": None,
    "automatic": {"observed_consent": None, "pending": None, "last_result": None},
}
COMMAND = {
    "protocol": 2,
    "request_id": REQUEST,
    "intent_created_at": DATE,
    "enabled": True,
    "expected_generation": 4,
    "expected_revision": 7,
}
CONSENT = {
    "generation": 5,
    "revision": 8,
    "enabled": True,
    "approving_device_id": UUID,
    "approved_at": DATE,
    "disabled_at": None,
    "closed_reason": None,
}
RECEIPT = {
    "kind": "automatic",
    "command": COMMAND,
    "accepted_at": DATE,
    "expires_at": EXPIRY,
    "result": CONSENT,
}
PENDING = {
    "command": COMMAND,
    "attempted": True,
    "cancel_after_on": {"request_id": CANCEL, "intent_created_at": DATE},
}


def legacy(version=3):
    return deepcopy({1: LEGACY_V1, 2: LEGACY_V2, 3: LEGACY_V3}[version])


def active():
    return deepcopy(ACTIVE_V4)


def compact(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8", "backslashreplace")


def put(path, value):
    path.write_bytes(compact(value))
    return path.read_bytes()
