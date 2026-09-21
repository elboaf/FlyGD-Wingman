"""Single-owner controls with a time-enforcing, CAS-aware relay, no network/DPAPI.

The prior one-pass catalogue+renew+publish expectations are deliberately replaced:
legacy unknown grants bootstrap, and Settings True is not an explicit On action.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import threading
import time
import urllib.error
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from itertools import count, pairwise
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.serialization import load_der_public_key

from tests.fleetsharing_timing_helpers import FakePublicationSource
from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import (
    FleetRelayClient,
    FleetRelayError,
    PairingBegin,
    PairingComplete,
)
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
from wingman.fleetsharing.timing import TimingContext
from wingman.fleetsharing.worker import (
    FleetSharingWorker,
    _noop_thread_factory,
)
from wingman.telemetry.model import (
    CombatActivity,
    FleetRow,
    FleetSnapshot,
    StreamHealth,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
DATE = "2026-09-07T12:00:00.000Z"
EXPIRY = "2026-09-07T12:30:00.000Z"
UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TOKEN = "A" * 43
CAPS = (p.SHARED_CAPABILITY,)
KEY = bytes(32)
SESSION = TOKEN
PAIRED_SESSION = "B" * 42 + "A"
DEVICE = p.parse_device(
    {
        "protocol": 2,
        "device_id": UUID,
        "session_expires_at": EXPIRY,
        "feature_enabled": True,
        "approved_capabilities": list(CAPS),
        "session_approved_capabilities": list(CAPS),
        "acknowledged_capabilities": list(CAPS),
        "participation": {"enabled": True, "generation": 1},
        "server_time_ms": 1788782400000,
    }
)
COMBAT_DEVICE = replace(
    DEVICE,
    approved_capabilities=(*CAPS, p.COMBAT_CAPABILITY),
    session_approved_capabilities=(*CAPS, p.COMBAT_CAPABILITY),
    acknowledged_capabilities=(*CAPS, p.COMBAT_CAPABILITY),
)
_SOURCE_IDS = count(1)
_SOURCE_LIFETIME = uuid4()


def _source(dps, now, *, character="Alice", inactive=False):
    activity = (
        CombatActivity()
        if inactive
        else CombatActivity(now + 30, (_SOURCE_LIFETIME, next(_SOURCE_IDS)))
    )
    return FakePublicationSource(
        FleetSnapshot(
            (FleetRow(character, dps, incoming_dps=0, combat=activity),),
            StreamHealth("active"),
            sampled_at_mono=now,
        )
    )


PAIRED_STATE = s.SharingState(
    identity=s.DeviceIdentity(
        "cHJvdGVjdGVk",
        crypto.canonical_device_public_key_b64(crypto.public_key_spki(KEY)),
    ),
    relay_origin="https://relay.test",
    session_id=SESSION,
)
CATALOGUE = FleetCatalogue(1, (CatalogueCharacter(1, "Alice"),))
STREAM_HEALTH = StreamHealth(state="active")
# Independently transcribed contract, later checked against production table.
OPERATION_BUCKETS = {
    "publish_snapshot": "publication",
    "fetch_device": "read",
    "acknowledge_capabilities": "read",
    "set_participation": "read",
    "fetch_sources": "read",
    "control_source": "read",
    "fetch_automatic": "read",
    "control_automatic": "read",
    "fetch_receipt": "read",
    "fetch_catalogue": "read",
    "fetch_eligibility": "read",
    "read_snapshot": "read",
    "renew_session": "read",
    "begin_pairing": "bootstrap",
    "complete_pairing": "bootstrap",
    "begin_recovery": "bootstrap",
    "complete_recovery": "bootstrap",
}
READ_OPERATIONS = {k for k, v in OPERATION_BUCKETS.items() if v == "read"}


def _snapshot(dps, *, character="Alice", ewar=()):
    return FleetSnapshot(
        rows=(FleetRow(character=character, dps=dps, ewar=ewar, log_status=None),),
        stream_health=STREAM_HEALTH,
    )


def _unwrap(_blob):
    return KEY


def _date(now):
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FakeRelayClient:
    """Enforces completion-based cadence and session revisions, and real CAS."""

    def __init__(self, *, device, catalogue=CATALOGUE, registered=True):
        # An explicit DeviceState describes the registered KEY/session fixture,
        # not permissions invented for an unregistered initial-pairing candidate.
        self.device = device
        self.catalogue = catalogue
        self.registered_keys = {crypto.public_key_spki(KEY)} if registered else set()
        self.valid_sessions = {SESSION: KEY} if registered else {}
        self.active_session = SESSION if registered else None
        self.session_views = {}
        self.precommit_loss = set()
        self.admissions = {}
        self.consumed_challenges = set()
        self.pairings = {}
        self.source_intents = {}
        self.clock = lambda: 1000.0
        self.utc = lambda: NOW
        self.latency = lambda: None
        self.calls = []
        self.sessions = []
        self.completed = []
        self.deadlines = {}
        self.revisions = {}
        self.errors = {}
        self.loss = set()
        self.cadence_refusals = 0
        self.publish_calls = []
        self.fetch_calls = []
        self.renew_calls = []
        self.controls = []
        self.participation_calls = []
        self.source_views = {}
        self.receipts = {}
        self.automatic_consent = p.Consent(0, 0, False, None, None, None, None)
        self.remote = p.parse_snapshot(
            {
                "protocol": 2,
                "server_time_ms": DEVICE.server_time_ms,
                "rows": [
                    {
                        "character_id": 2,
                        "character_name": "Bob",
                        "outgoing_dps": 20,
                        "incoming_dps": None,
                        "activity_age_ms": 400,
                        "effects": [],
                        "state": "live",
                        "age_ms": 400,
                        "publication_id": UUID,
                    }
                ],
            }
        )
        self.withdrawal_completed = False
        self.challenge = None
        self.recovery_result = "reconnected"
        self.recoveries = 0
        self.pair_keys = []
        self.hold = None
        self.entered = threading.Event()
        self.release = threading.Event()

    def _call(self, operation, args, apply):
        hook = args.get("before_send")
        if hook is not None:
            hook()
        bucket = OPERATION_BUCKETS[operation]
        now = self.clock()
        revision = args.get("revision")
        self.calls.append((operation, now, revision))
        self.sessions.append(args.get("session_id"))
        if now < self.deadlines.get(bucket, 0):
            self.cadence_refusals += 1
            raise FleetRelayError(429, "rate_limited", "cadence")
        if revision is not None:
            session = args["session_id"]
            assert revision > self.revisions.get(session, 0)
            self.revisions[session] = revision
        try:
            if operation == self.hold:
                self.entered.set()
                assert self.release.wait(5), "held fixture timed out"
            if operation in self.errors:
                raise self.errors[operation]
            if operation in self.precommit_loss:
                self.precommit_loss.remove(operation)
                raise FleetRelayError(None, "transport_error", "before commit")
            self._authorize(operation, args)
            result = apply()
            if operation in self.loss:
                self.loss.remove(operation)
                raise FleetRelayError(None, "transport_error", "lost response")
            return result
        finally:
            self.latency()
            end = self.clock()
            self.deadlines[bucket] = end + (1 if bucket == "bootstrap" else 0.5)
            self.completed.append((operation, end))

    def _session_device(self, args):
        session_id = args["session_id"]
        view = (
            self.device
            if session_id == self.active_session
            else self.session_views[session_id]
        )
        return replace(
            self.device,
            session_expires_at=view.session_expires_at,
            session_approved_capabilities=view.session_approved_capabilities,
            acknowledged_capabilities=view.acknowledged_capabilities,
            server_time_ms=int(self.utc().timestamp() * 1000),
        )

    def _install_session(self, session_id, private_key, device, *, retire=False):
        if self.active_session is not None:
            self.session_views[self.active_session] = self.device
        if retire:
            self.valid_sessions.clear()
            self.session_views.clear()
        self.valid_sessions[session_id] = private_key
        self.active_session = session_id
        self.device = device

    def _update_session(self, args, **changes):
        device = replace(self._session_device(args), **changes)
        if args["session_id"] == self.active_session:
            self.device = device
        else:
            self.session_views[args["session_id"]] = device
        return device

    def _authorize(self, operation, args):
        if OPERATION_BUCKETS[operation] == "bootstrap":
            return
        if self.valid_sessions.get(args["session_id"]) != args[
            "private_key"
        ] or self.utc() >= datetime.fromisoformat(
            self._session_device(args).session_expires_at
        ):
            raise FleetRelayError(401, "unauthorized", "session")
        if operation in ("fetch_device", "fetch_catalogue", "renew_session"):
            return
        terminal = (
            operation in ("fetch_automatic", "fetch_receipt")
            or (operation == "control_automatic" and not args["command"].enabled)
            or (
                operation == "control_source"
                and isinstance(args["command"], p.StopSource)
            )
        )
        if terminal:
            if p.SHARED_CAPABILITY not in self.device.approved_capabilities:
                raise FleetRelayError(403, "capability_required", "durable approval")
            return
        shared = operation in ("publish_snapshot", "read_snapshot", "fetch_eligibility")
        if not self.device.feature_enabled:
            # A retains legacy snapshot endpoints while disabled. This fixture
            # has no legacy own-fleet evidence; only empty withdrawal can succeed.
            if operation == "publish_snapshot" and not args["rows"]:
                return
            legacy = operation == "publish_snapshot"
            raise FleetRelayError(
                403 if legacy else 503,
                "forbidden" if legacy else "feature_disabled",
                "mode",
            )
        device = self._session_device(args)
        capabilities = [
            device.approved_capabilities,
            device.session_approved_capabilities,
        ]
        if operation != "acknowledge_capabilities":
            capabilities.append(device.acknowledged_capabilities)
        if not all(p.SHARED_CAPABILITY in caps for caps in capabilities):
            raise FleetRelayError(
                403, "forbidden" if shared else "capability_required", "authority"
            )
        if not self.device.participation.enabled and (
            operation == "read_snapshot"
            or (operation == "publish_snapshot" and args["rows"])
        ):
            raise FleetRelayError(403, "forbidden", "participation")

    def fetch_device(self, **args):
        return self._call(
            "fetch_device",
            args,
            lambda: p.parse_device(
                {
                    "protocol": 2,
                    **asdict(self._session_device(args)),
                    "approved_capabilities": list(self.device.approved_capabilities),
                    "session_approved_capabilities": list(
                        self._session_device(args).session_approved_capabilities
                    ),
                    "acknowledged_capabilities": list(
                        self._session_device(args).acknowledged_capabilities
                    ),
                    "server_time_ms": int(self.utc().timestamp() * 1000),
                }
            ),
        )

    def acknowledge_capabilities(self, **args):
        def apply():
            device = self._session_device(args)
            approved = tuple(
                cap
                for cap in (*CAPS, p.COMBAT_CAPABILITY)
                if cap in device.approved_capabilities
                and cap in device.session_approved_capabilities
            )
            assert args["capabilities"] == approved
            return self._update_session(args, acknowledged_capabilities=approved)

        return self._call("acknowledge_capabilities", args, apply)

    def set_participation(self, **args):
        def apply():
            self.participation_calls.append(
                (args["enabled"], args["expected_generation"])
            )
            current = self.device.participation
            if args["expected_generation"] != current.generation:
                raise FleetRelayError(409, "conflict", "CAS")
            current = p.Participation(args["enabled"], current.generation + 1)
            self.device = replace(self.device, participation=current)
            return current

        return self._call("set_participation", args, apply)

    def fetch_catalogue(self, **args):
        def apply():
            self.fetch_calls.append(args["revision"])
            return self.catalogue

        return self._call("fetch_catalogue", args, apply)

    def renew_session(self, **args):
        def apply():
            self.renew_calls.append(args["revision"])
            expiry = _date(self.utc() + timedelta(minutes=30))
            self._update_session(args, session_expires_at=expiry)
            return expiry

        return self._call("renew_session", args, apply)

    def publish_snapshot(self, *, sampled_at_ms, **args):
        # No protocol-1 success shim: the worker must supply real API2 payloads.
        p.parse_combat_put(
            json.loads(
                json.dumps(
                    {
                        "protocol": 2,
                        "sampled_at_ms": sampled_at_ms,
                        "rows": [asdict(row) for row in args["rows"]],
                    }
                )
            )
        )

        def apply():
            self.publish_calls.append((args["revision"], args["rows"]))
            if not args["rows"]:
                self.withdrawal_completed = True

        return self._call("publish_snapshot", args, apply)

    def fetch_eligibility(self, **args):
        def apply():
            part = self.device.participation
            return p.Eligibility(
                part.generation,
                "ready" if part.enabled else "participation_off",
                (
                    p.EligibilityEntry(
                        1, UUID, 1, 1, _date(self.utc() + timedelta(seconds=10))
                    ),
                )
                if part.enabled
                else (),
            )

        return self._call("fetch_eligibility", args, apply)

    def read_snapshot(self, **args):
        def apply():
            # One fixed publication's origins age at the current DB sample; never
            # restamp old rows as new evidence just to satisfy runtime timing.
            wire = json.loads(json.dumps({"protocol": 2, **asdict(self.remote)}))
            now = int(self.utc().timestamp() * 1000)
            elapsed = now - wire["server_time_ms"]
            wire["server_time_ms"] = now
            rows = []
            for row in wire["rows"]:
                row["age_ms"] += elapsed
                row["activity_age_ms"] += elapsed
                if row["age_ms"] >= 10000 or row["activity_age_ms"] >= 30000:
                    continue
                row["state"] = "live" if row["age_ms"] < 3000 else "stale"
                for effect in row["effects"]:
                    for observation in effect["observations"]:
                        observation["age_ms"] += elapsed
                    effect["observations"] = [
                        o for o in effect["observations"] if o["age_ms"] < 30000
                    ]
                row["effects"] = [e for e in row["effects"] if e["observations"]]
                rows.append(row)
            wire["rows"] = rows
            return p.parse_snapshot(wire)

        return self._call("read_snapshot", args, apply)

    def fetch_sources(self, **args):
        return self._call(
            "fetch_sources",
            args,
            lambda: p.Sources(
                tuple(self.source_views.values()),
                (p.SourceCharacter(1, "Alice", UUID, True, True),),
            ),
        )

    def _automatic_status(self):
        consent = self.automatic_consent
        return p.AutomaticStatus(
            consent,
            "none" if consent.generation == 0 else "this_device",
            "waiting_for_grant" if consent.enabled else "off",
            "none",
            None,
            (),
        )

    def fetch_automatic(self, **args):
        return self._call(
            "fetch_automatic", args, lambda: p.AutomaticGet(self._automatic_status())
        )

    def fetch_receipt(self, **args):
        def apply():
            receipt = self.receipts.get(args["request_id"])
            if receipt is None or self.utc() >= datetime.fromisoformat(
                receipt.expires_at
            ):
                raise FleetRelayError(404, "receipt_not_found", "not retained")
            return p.ReceiptGet(receipt, self._automatic_status())

        return self._call("fetch_receipt", args, apply)

    def control_automatic(self, **args):
        command = args["command"]
        p.automatic_command_body(command)

        def apply():
            receipt = self.receipts.get(command.request_id)
            if receipt is not None:
                if receipt.command != command:
                    raise FleetRelayError(409, "request_id_conflict", "binding")
                return p.AutomaticResult(
                    command.request_id, "replayed", receipt, self._automatic_status()
                )
            current = self.automatic_consent
            if (command.expected_generation, command.expected_revision) != (
                current.generation,
                current.revision,
            ):
                raise FleetRelayError(409, "conflict", "CAS")
            age = (
                self.utc() - datetime.fromisoformat(command.intent_created_at)
            ).total_seconds()
            if age < 0 or (command.enabled and age >= 60):
                raise FleetRelayError(400, "invalid_intent", "freshness")
            if not command.enabled and not current.enabled:
                return p.AutomaticResult(
                    command.request_id, "already_off", None, self._automatic_status()
                )
            if command.enabled:
                current = p.Consent(
                    current.generation + 1,
                    current.revision + 1,
                    True,
                    self.device.device_id,
                    _date(self.utc()),
                    None,
                    None,
                )
            else:
                current = replace(
                    current,
                    revision=current.revision + 1,
                    enabled=False,
                    disabled_at=_date(self.utc()),
                    closed_reason="explicit_off",
                )
            self.automatic_consent = current
            receipt = p.AutomaticReceipt(
                command,
                _date(self.utc()),
                _date(self.utc() + timedelta(hours=24)),
                current,
            )
            self.receipts[command.request_id] = receipt
            return p.AutomaticResult(
                command.request_id, "applied", receipt, self._automatic_status()
            )

        return self._call("control_automatic", args, apply)

    def control_source(self, **args):
        command = args["command"]

        def apply():
            self.controls.append(command)
            current = self.source_views.get(command.source_id)
            if isinstance(command, p.StartSource):
                age = (
                    self.utc() - datetime.fromisoformat(command.intent_created_at)
                ).total_seconds()
                if not 0 <= age < 60:
                    raise FleetRelayError(400, "invalid_intent", "start freshness")
                if command.character_id != 1 or command.character_link_epoch != UUID:
                    raise FleetRelayError(403, "forbidden", "character binding")
                if current is not None:
                    if (
                        current.state == "ended"
                        or self.source_intents.get(command.source_id) != command
                    ):
                        raise FleetRelayError(409, "conflict", "start")
                    return p.SourceStartResult(current)
                self.source_intents[command.source_id] = command
                # Provider activation is an explicit fixture simplification;
                # production initially returns pending, with the same CAS identity.
                current = p.SourceView(
                    command.source_id,
                    1,
                    command.character_id,
                    "active",
                    None,
                    None,
                    None,
                )
            else:
                if (
                    current.generation if current else 0
                ) != command.expected_generation:
                    raise FleetRelayError(409, "conflict", "stop")
                if current and current.state == "ended":
                    consent = p.Consent(0, 0, False, None, None, None, None)
                    status = p.AutomaticStatus(consent, "none", "off", "none", None, ())
                    return p.SourceStopResult(
                        command.request_id,
                        "already_stopped",
                        None,
                        current,
                        "manual_only",
                        status,
                    )
                current = p.SourceView(
                    command.source_id,
                    (current.generation if current else 0) + 1,
                    current.character_id if current else None,
                    "ended",
                    "stopped",
                    None,
                    None,
                )
            self.source_views[command.source_id] = current
            if isinstance(command, p.StartSource):
                return p.SourceStartResult(current)
            consent = p.Consent(0, 0, False, None, None, None, None)
            status = p.AutomaticStatus(consent, "none", "off", "none", None, ())
            effect = (
                "manual_only" if command.expected_generation else "unknown_cancelled"
            )
            receipt = p.SourceStopReceipt(
                command,
                _date(self.utc()),
                _date(self.utc() + timedelta(hours=24)),
                current,
                effect,
                consent,
            )
            self.receipts[command.request_id] = receipt
            return p.SourceStopResult(
                command.request_id, "applied", receipt, current, effect, status
            )

        return self._call("control_source", args, apply)

    def begin_recovery(self, **args):
        def apply():
            key = crypto.public_key_spki(args["private_key"])
            if not self.device.feature_enabled:
                raise FleetRelayError(503, "feature_disabled", "recovery")
            if (
                key not in self.registered_keys
                or abs(
                    (
                        self.utc() - datetime.fromisoformat(args["issued_at"])
                    ).total_seconds()
                )
                >= 60
            ):
                raise FleetRelayError(401, "unauthorized", "admission")
            binding = (key, args["request_id"])
            if binding in self.admissions:
                issued_at, challenge = self.admissions[binding]
                if (
                    issued_at != args["issued_at"]
                    or challenge.challenge_id in self.consumed_challenges
                    or self.utc() >= datetime.fromisoformat(challenge.expires_at)
                ):
                    raise FleetRelayError(401, "unauthorized", "admission binding")
                self.challenge = challenge
                return challenge
            self.challenge = p.RecoveryChallenge(
                str(uuid4()),
                args["request_id"],
                TOKEN,
                _date(self.utc() + timedelta(seconds=120)),
            )
            self.admissions[binding] = (args["issued_at"], self.challenge)
            return self.challenge

        return self._call("begin_recovery", args, apply)

    def complete_recovery(self, **args):
        def apply():
            challenge = args["challenge"]
            binding = (
                crypto.public_key_spki(args["private_key"]),
                challenge.request_id,
            )
            admitted = self.admissions.get(binding)
            if (
                admitted is None
                or admitted[1] != challenge
                or challenge.challenge_id in self.consumed_challenges
                or self.utc() >= datetime.fromisoformat(challenge.expires_at)
            ):
                raise FleetRelayError(401, "unauthorized", "consumed")
            if not self.device.feature_enabled:
                raise FleetRelayError(503, "feature_disabled", "recovery")
            self.consumed_challenges.add(challenge.challenge_id)
            self.challenge = None
            if self.recovery_result != "reconnected":
                delay = {"account_ineligible": 60000, "retry_later": 1000}.get(
                    self.recovery_result
                )
                return p.RecoveryResult(self.recovery_result, retry_after_ms=delay)
            self.recoveries += 1
            device = replace(
                self.device,
                session_approved_capabilities=self.device.approved_capabilities,
                acknowledged_capabilities=(),
                session_expires_at=_date(self.utc() + timedelta(minutes=30)),
            )
            session_id = "A" * 42 + "AEIM"[self.recoveries % 4]
            self._install_session(session_id, args["private_key"], device, retire=True)
            return p.RecoveryResult(
                "reconnected",
                self.device.device_id,
                session_id,
                self.device.session_expires_at,
                self.device.approved_capabilities,
                self.device.participation,
            )

        return self._call("complete_recovery", args, apply)

    def begin_pairing(self, public_key_spki, **args):
        def apply():
            if args.get("requested_capabilities") and not self.device.feature_enabled:
                raise FleetRelayError(503, "feature_disabled", "pairing")
            self.pair_keys.append(public_key_spki)
            pairing_id = str(uuid4())
            admission = PairingBegin(
                pairing_id,
                "https://relay.test/approve",
                _date(self.utc() + timedelta(minutes=10)),
            )
            self.pairings[pairing_id] = (
                public_key_spki,
                admission.expires_at,
                False,
                args.get("requested_capabilities", ()),
            )
            return admission

        return self._call("begin_pairing", args, apply)

    def complete_pairing(self, pairing_id, challenge, private_key, *, before_send=None):
        def apply():
            binding = self.pairings.get(pairing_id)
            if (
                binding is None
                or binding[2]
                or self.utc() >= datetime.fromisoformat(binding[1])
            ):
                raise FleetRelayError(
                    409, "not_completable", "pairing consumed/expired"
                )
            key = crypto.public_key_spki(private_key)
            if key != binding[0] or challenge != crypto.pairing_challenge_preimage(
                pairing_id
            ):
                raise FleetRelayError(401, "unauthorized", "pairing proof")
            if binding[3] and not self.device.feature_enabled:
                raise FleetRelayError(503, "feature_disabled", "pairing")
            granted = set(binding[3])
            if key in self.registered_keys:
                granted.update(self.device.approved_capabilities)
            # API2 capability order is shared then combat, not lexical sorting.
            grants = tuple(
                cap
                for cap in (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)
                if cap in granted
            )
            device = replace(
                self.device,
                approved_capabilities=grants,
                session_approved_capabilities=binding[3],
                acknowledged_capabilities=(),
                participation=self.device.participation
                if key in self.registered_keys
                else p.Participation(False, 0),
                session_expires_at=_date(self.utc() + timedelta(minutes=30)),
            )
            self.registered_keys.add(key)
            self.pairings[pairing_id] = (key, binding[1], True, binding[3])
            self._install_session(PAIRED_SESSION, private_key, device)
            return PairingComplete(PAIRED_SESSION, self.catalogue)

        return self._call("complete_pairing", {"before_send": before_send}, apply)


class SignedPublicationRelay(FakeRelayClient):
    """Real publication client; server holds/errors/cadence begin at HTTP only.

    Metadata/CAS doubles remain useful, but no PUB argument reconstruction is a
    publication witness. Every PUB here verifies actual immutable Request bytes,
    Ed25519 signature and freshly loaded validated state before server work.
    """

    def __init__(self, *, store, **kwargs):
        super().__init__(**kwargs)
        self.store = store
        self.signed_publications = []
        self.published = []
        self.relay = FleetRelayClient(
            "https://relay.test", transport=self._publication_transport
        )

    def publish_snapshot(self, **args):
        return self.relay.publish_snapshot(**args)

    def _publication_transport(self, request, timeout=None):
        from tests.test_fleetsharing_client import FakeTransport, _headers_of

        assert request.method == "PUT"
        assert request.full_url == "https://relay.test/api/fleet/v2/snapshot"
        headers = _headers_of(request)
        raw = request.data
        assert isinstance(raw, bytes)
        digest = hashlib.sha256(raw).hexdigest()
        assert headers["x-fleet-body-sha256"] == digest
        session = headers["x-fleet-session"]
        revision = int(headers["x-fleet-revision"])
        saved = self.store.load()
        assert (saved.last_revision, saved.session_id) == (revision, session)
        canonical = "\n".join(
            (
                "fleet-v1",
                "PUT",
                "/api/fleet/v2/snapshot",
                session,
                headers["x-fleet-issued-at"],
                str(revision),
                digest,
            )
        ).encode()
        signature = headers["x-fleet-signature"]
        load_der_public_key(crypto.public_key_spki(KEY)).verify(
            base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)), canonical
        )
        body = p.parse_combat_put(json.loads(raw))
        record = {
            "request": request,
            "revision": saved.last_revision,
            "started": self.clock(),
        }
        self.signed_publications.append(record)
        args = {
            "session_id": session,
            "private_key": KEY,
            "revision": revision,
            "rows": body.rows,
        }

        def apply():
            self.publish_calls.append((revision, body.rows))
            self.published.append((record["started"], body))
            if not body.rows:
                self.withdrawal_completed = True

        try:
            self._call("publish_snapshot", args, apply)
        except FleetRelayError as exc:
            if exc.status is None:
                raise urllib.error.URLError("test transport lost response") from exc
            return FakeTransport({"protocol": 2, "error": exc.code}, exc.status)(
                request, timeout
            )
        finally:
            record["completed"] = self.clock()
            assert request.data is raw, "signed request bytes changed at HTTP"
        return FakeTransport({"protocol": 2})(request, timeout)


class _InMemoryStateStore:
    def __init__(self, state):
        self._state = state
        self.saves = []
        self.loads = 0
        self.fail = lambda state: False

    def load(self):
        self.loads += 1
        return self._state

    def save(self, state):
        if self.fail(state):
            raise OSError("disk full")
        s.check_control_capacity(state)
        self.saves.append(state)
        self._state = state


def _worker(
    client,
    *,
    state=PAIRED_STATE,
    store=None,
    clock=None,
    utc_clock=None,
    thread_factory=_noop_thread_factory,
    sharing_enabled=lambda: True,
    save_state=None,
    timing_context=None,
):
    timing_context = timing_context or TimingContext(
        clock=clock or (lambda: 1000.0),
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )
    mono = timing_context._clock
    client.clock = mono
    client.utc = utc_clock or (lambda: NOW)
    store = store or _InMemoryStateStore(state)
    return FleetSharingWorker(
        load_state=store.load,
        save_state=save_state or store.save,
        client_factory=lambda origin: client,
        unwrap_private_key=_unwrap,
        wrap_private_key=lambda raw: "cHJvdGVjdGVk",
        _generate_private_key=lambda: KEY,
        sharing_enabled=sharing_enabled,
        _thread_factory=thread_factory,
        timing_context=timing_context,
        _utc_clock=client.utc,
        _jitter=lambda: 0,
    )


def drive(worker, mono, turns=20, snapshot=None):
    for _ in range(turns):
        if snapshot:
            worker.submit(snapshot(mono[0]) if callable(snapshot) else snapshot)
        worker.iterate_once()
        mono[0] += 0.5


def rig(*, state=PAIRED_STATE, enabled=True, device=DEVICE):
    mono = [1000.0]
    store = _InMemoryStateStore(state)
    client = FakeRelayClient(device=device, registered=state.identity is not None)
    worker = _worker(
        client,
        store=store,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
        sharing_enabled=lambda: enabled,
    )
    return worker, client, store, mono


def signed_rig(tmp_path):
    from tests.test_fleetsharing_worker_state4 import FileStore

    mono = [1000.0]
    store = FileStore(tmp_path / "signed-publication.json")
    store.save(PAIRED_STATE)
    client = SignedPublicationRelay(store=store, device=COMBAT_DEVICE)
    worker = _worker(
        client,
        store=store,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
    )
    return worker, client, store, mono


def test_simultaneous_periodic_controls_completion_cadence_and_withdrawal(tmp_path):
    from wingman.fleetsharing.scheduling import OPERATIONS

    assert dict(OPERATIONS) == OPERATION_BUCKETS
    worker, client, store, mono = signed_rig(tmp_path)
    client.latency = lambda: mono.__setitem__(0, mono[0] + 0.2)
    drive(worker, mono, snapshot=lambda now: _source(42, now))
    assert client.publish_calls[-1][1] == (p.CombatRow(1, 42, 0, 0, ()),)
    mono[0] += 1800 - 65
    for _ in range(10):
        worker.request_source_start(1, UUID)
        drive(worker, mono, 1, lambda now: _source(43, now))
    worker.request_participation(
        False,
        expected_generation=client.device.participation.generation,
        binding=worker.status().metadata.binding,
    )
    drive(worker, mono, 20)
    read_times = [t for kind, t, _rev in client.calls if kind in READ_OPERATIONS]
    assert all(b - a >= 0.5 for a, b in pairwise(read_times))
    signed = [rev for _, _, rev in client.calls if rev is not None]
    assert len(set(signed)) == len(signed)
    assert client.withdrawal_completed and client.device.participation.enabled is False
    assert client.cadence_refusals == 0 and client.renew_calls
    assert store.load().last_revision == max(signed)
    assert all(
        len([c for c in client.calls if c[1] == t]) <= 1 for _, t, _ in client.calls
    )


def test_iterate_seam_enforces_completion_deadlines_without_thread_sleep():
    worker, client, _, mono = rig()
    client.latency = lambda: mono.__setitem__(0, mono[0] + 0.2)
    worker.iterate_once()
    first = len(client.calls)
    worker.iterate_once()
    assert len(client.calls) == first
    mono[0] += 0.49
    worker.iterate_once()
    assert len(client.calls) == first
    mono[0] += 0.02
    worker.iterate_once()
    assert len(client.calls) == first + 1
    assert client.cadence_refusals == 0


def test_injected_read_429_does_not_stall_publication_or_rejuvenate_remote(tmp_path):
    worker, client, _, mono = signed_rig(tmp_path)
    events = []
    worker.subscribe_remote(events.append)
    drive(worker, mono, snapshot=lambda now: _source(42, now))
    replacements = [e for e in events if e.kind == "replace"]
    assert replacements
    old = replacements[-1]
    client.errors["read_snapshot"] = FleetRelayError(429, "rate_limited", "injected")
    before = len(client.publish_calls)
    drive(worker, mono, 10, lambda now: _source(43, now))
    assert len(client.publish_calls) > before
    assert [e for e in events if e.kind == "replace"][-1] is old
    assert client.cadence_refusals == 0


@pytest.mark.parametrize(
    "missing,want",
    [
        ("approved_capabilities", "needs_upgrade"),
        ("session_approved_capabilities", "begin_recovery"),
        ("acknowledged_capabilities", "acknowledge_capabilities"),
    ],
)
def test_grant_ceiling_and_ack_are_distinct(missing, want):
    worker, client, _, mono = rig(device=replace(DEVICE, **{missing: ()}))
    drive(worker, mono, 12, _snapshot(42))
    if want == "needs_upgrade":
        assert worker.status().detail == want
        assert client.publish_calls == [] and not client.pair_keys
    else:
        assert want in [k for k, _, _ in client.calls]
    assert not client.pair_keys


def test_settings_true_never_manufactures_on_and_new_on_reads_then_binds():
    worker, client, store, mono = rig(
        device=replace(DEVICE, participation=p.Participation(False, 8))
    )
    drive(worker, mono, 5, _snapshot(42))
    assert client.participation_calls == [] and client.publish_calls == []
    intent = worker.request_participation(True)
    before = len(client.calls)
    drive(worker, mono, 10, _snapshot(42))
    assert store.load().pending_participation == s.PendingParticipation(intent, True)
    assert not client.participation_calls
    intent = worker.confirm_participation(
        intent, expected_generation=8, binding=worker.status().metadata.binding
    )
    drive(worker, mono, 6)
    calls = [k for k, _, _ in client.calls[before:]]
    assert calls.index("fetch_device") < calls.index("set_participation")
    assert client.participation_calls == [(True, 8)]
    assert any(
        v.pending_participation
        and v.pending_participation.intent_id == intent
        and v.pending_participation.expected_generation == 8
        for v in store.saves
    )
    assert store.load().pending_participation is None


def test_old_bound_on_cannot_rebase_over_new_server_off():
    pending = s.PendingParticipation(UUID, True, 4, True)
    worker, client, store, mono = rig(
        state=replace(PAIRED_STATE, pending_participation=pending),
        device=replace(DEVICE, participation=p.Participation(False, 6)),
    )
    drive(worker, mono, 10)
    assert client.participation_calls == []
    assert worker.status().detail == "needs_fresh_intent"
    assert store.load().pending_participation == pending


def test_unbound_on_json_restart_requires_confirmation(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        PAIRED_STATE, pending_participation=s.PendingParticipation(UUID, True)
    )
    s.save(path, original)
    worker, client, _, mono = rig(
        state=s.load(path),
        device=replace(DEVICE, participation=p.Participation(False, 6)),
    )
    drive(worker, mono, 10)
    assert not client.participation_calls
    assert worker.status().detail == "needs_fresh_intent"
    worker.confirm_participation(
        UUID, expected_generation=6, binding=worker.status().metadata.binding
    )
    drive(worker, mono, 10)
    assert client.participation_calls == [(True, 6)]


def test_participation_response_loss_reconciles_without_duplicate_cas():
    worker, client, store, mono = rig()
    drive(worker, mono, 1)
    worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    client.loss.add("set_participation")
    drive(worker, mono, 20)
    assert client.participation_calls == [(False, 1)]
    assert store.load().pending_participation is None
    assert worker.status().participation == "observed_choice"


def test_start_then_stop_before_ack_fences_same_uuid_generation_zero():
    worker, client, store, mono = rig(enabled=False)
    source_id = worker.request_source_start(1, UUID)
    assert source_id and not store.saves and not client.calls
    assert worker.request_source_stop(
        source_id, expected_generation=0, expected_automatic=None
    )
    stop = worker._commands["source:" + source_id].payload
    drive(worker, mono, 15)
    assert client.controls == [stop]
    assert store.load().pending_source_commands == ()
    assert not client.publish_calls


def test_lost_start_stop_cas_reread_and_start_aba():
    worker, client, store, mono = rig(enabled=False)
    source_id = worker.request_source_start(1, UUID)
    client.loss.add("control_source")
    drive(worker, mono, 8)
    start = client.controls[0]
    assert start.source_id == source_id and start.intent_created_at == DATE
    assert len(client.controls) == 2 and client.controls == [start, start]
    assert worker.request_source_stop(
        source_id, expected_generation=0, expected_automatic=None
    )
    old_stop = worker._commands["source:" + source_id].payload
    new_id = worker.request_source_start(1, UUID)
    drive(worker, mono, 12)
    assert old_stop in store.load().pending_source_commands
    assert old_stop.expected_generation == 0
    assert worker.request_source_stop(
        source_id, expected_generation=1, expected_automatic=None, supersedes=old_stop
    )
    drive(worker, mono, 30)
    assert new_id != source_id
    assert client.source_views[source_id].state == "ended"
    assert client.source_views[new_id].state == "active"
    assert store.load().pending_source_commands == ()
    assert not client.publish_calls


def test_expired_start_is_observed_not_retimestamped_or_replaced():
    start = p.StartSource(UUID, 1, UUID, "2026-09-07T11:58:00.000Z")
    worker, client, store, mono = rig(
        state=replace(PAIRED_STATE, pending_source_commands=(start,)), enabled=False
    )
    worker.resume_pending()
    drive(worker, mono, 15)
    assert not client.controls
    assert store.load().pending_source_commands == (start,)


def test_source_watch_and_one_startup_probe_do_not_require_telemetry():
    worker, client, store, mono = rig(enabled=False)
    drive(worker, mono)
    assert store.loads == 0 and not client.calls
    assert worker.resume_pending() and not worker.resume_pending()
    drive(worker, mono)
    assert store.loads == 1 and not client.calls
    worker.set_source_watch(True)
    drive(worker, mono)
    assert worker.status().sources is not None and not client.publish_calls
    worker.set_source_watch(False)
    before = len(client.calls)
    drive(worker, mono, 100)
    assert len(client.calls) == before and store.loads == 1


@pytest.mark.parametrize("lost", ["begin_recovery", "complete_recovery"])
def test_generic401_and_one_use_response_loss_recover_same_key_without_browser(lost):
    worker, client, store, mono = rig()
    client.errors["fetch_device"] = FleetRelayError(401, "unauthorized", "expired")
    drive(worker, mono, 1)
    client.errors.clear()
    client.loss.add(lost)
    drive(worker, mono, 35, _snapshot(42))
    assert client.recoveries >= 1 and store.load().pending_recovery is None
    assert store.load().identity == PAIRED_STATE.identity
    assert not client.pair_keys
    assert worker.status().metadata.has_session
    assert worker.status().metadata.device_id == UUID
    # Publication is the separate D checkpoint, not authentication evidence.
    if lost == "complete_recovery":
        assert client.recoveries == 2
    assert client.cadence_refusals == 0


@pytest.mark.parametrize(
    "result,floor",
    [
        ("device_revoked", None),
        ("device_key_conflict", None),
        ("account_ineligible", 60),
        ("retry_later", 1),
    ],
)
def test_proven_auth_pause_survives_json_restart(tmp_path, result, floor):
    worker, client, store, mono = rig(state=replace(PAIRED_STATE, session_id=None))
    client.recovery_result = result
    drive(worker, mono, 6)  # startup bucket floor, admission, then one-use proof
    state = store.load()
    assert state.auth_pause.result == result
    path = tmp_path / "state.json"
    s.save(path, state)
    other = _worker(
        client,
        state=s.load(path),
        timing_context=worker._timing_context,
        utc_clock=client.utc,
    )
    before = len(client.calls)
    if floor is None:
        drive(other, mono, 200)
        assert len(client.calls) == before
        assert other.status().detail == "needs_fresh_key"
    else:
        # Restart at the original wall timestamp is conservatively early.
        other._utc_clock = lambda: NOW
        other.iterate_once()
        assert len(client.calls) == before


def test_remaining_expiry_is_used_not_new_ten_minute_grace():
    device = replace(DEVICE, session_expires_at="2026-09-07T12:00:03.000Z")
    worker, client, store, mono = rig(device=device)
    drive(worker, mono, 5)
    assert client.renew_calls
    assert store.load().session_expires_at != device.session_expires_at


def test_pairing_upgrade_same_key_keeps_stop_and_participation_journals():
    worker, client, store, mono = rig(
        state=replace(
            PAIRED_STATE,
            pending_source_commands=(p.StopSource(UUID, 0, UUID, DATE, None),),
            pending_participation=s.PendingParticipation(UUID, False),
        )
    )
    assert worker.request_pairing(mode="upgrade")
    assert not store.saves and not client.calls
    # B permits terminal work before browser completion. Keep this Stop genuinely
    # unresolved so this A regression still proves authentication cannot erase it.
    client.errors["fetch_receipt"] = FleetRelayError(503, "service_unavailable", "held")
    client.loss.add("complete_pairing")
    for _ in range(35):
        drive(worker, mono, 1)
        if client.recoveries:
            break
    assert client.pair_keys == [crypto.public_key_spki(KEY)]
    assert store.load().pending_source_commands == (
        p.StopSource(UUID, 0, UUID, DATE, None),
    )
    assert store.load().pending_participation == s.PendingParticipation(UUID, False)
    # Terminal/source settlement belongs to B; authentication never erases them.
    assert client.recoveries and store.load().identity == PAIRED_STATE.identity
    assert any(
        v.pending_pairing and v.pending_pairing.approval_url for v in store.saves
    )


def test_initial_pairing_saves_candidate_and_admission_before_exposure():
    worker, client, store, mono = rig(state=s.EMPTY, enabled=False)
    worker.request_pairing(configured_origin="https://relay.test")
    assert not store.saves and not client.calls
    drive(worker, mono, 12)
    assert store.saves[0].identity and store.saves[0].pending_pairing
    assert store.load().session_id == PAIRED_SESSION
    assert store.load().device_id == UUID


@pytest.mark.parametrize(
    "boundary",
    [
        "intent",
        "revision",
        "device",
        "recovery_begin",
        "challenge",
        "session",
        "pair_candidate",
        "pair_admission",
        "pair_attempt",
        "participation_binding",
        "participation_attempt",
        "source_ack",
    ],
)
def test_persistence_failure_never_installs_unsaved_state_or_sends_past_boundary(
    boundary,
):
    worker, client, store, mono = rig()
    if boundary.startswith("recovery") or boundary in ("challenge", "session"):
        store._state = replace(PAIRED_STATE, session_id=None)
    if boundary.startswith("pair"):
        worker.request_pairing(mode="upgrade")
    if boundary.startswith("participation"):
        drive(worker, mono, 1)
        worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
    elif boundary == "intent":
        worker.request_participation(False)
    if boundary == "source_ack":
        worker.request_source_stop(UUID, expected_generation=0, expected_automatic=None)

    def fail(v):
        return {
            "intent": v.pending_participation is not None,
            "revision": v.last_revision > 0,
            "device": v.device_id is not None,
            "recovery_begin": v.pending_recovery is not None,
            "challenge": v.pending_recovery is not None
            and v.pending_recovery.challenge is not None,
            "session": v.session_id is not None,
            "pair_candidate": v.pending_pairing is not None,
            "pair_admission": v.pending_pairing is not None
            and v.pending_pairing.pairing_id is not None,
            "pair_attempt": v.pending_pairing is not None
            and v.pending_pairing.completion_attempted,
            "participation_binding": v.pending_participation is not None
            and v.pending_participation.expected_generation is not None,
            "participation_attempt": v.pending_participation is not None
            and v.pending_participation.attempted,
            "source_ack": bool(client.controls) and not v.pending_source_commands,
        }[boundary]

    store.fail = fail
    drive(worker, mono, 12)
    if boundary == "session":
        # One-use retirement may be followed by a new initiation. That progress
        # is not an unsaved session, regardless of the final turn's status.
        assert store.load().session_id is None
        assert any(
            v.pending_recovery and v.pending_recovery.completion_attempted
            for v in store.saves
        )
    else:
        assert worker.status().state == "error"
    assert worker._state == store._state
    kinds = [k for k, _, _ in client.calls]
    forbidden = {
        "intent": "set_participation",
        "revision": "fetch_device",
        "device": "fetch_catalogue",
        "recovery_begin": "begin_recovery",
        "challenge": "complete_recovery",
        "session": "fetch_device",
        "pair_candidate": "begin_pairing",
        "pair_admission": "complete_pairing",
        "pair_attempt": "complete_pairing",
        "participation_binding": "set_participation",
        "participation_attempt": "set_participation",
    }
    if boundary in forbidden:
        assert forbidden[boundary] not in kinds
    else:
        assert store.load().pending_source_commands


def test_status_exposes_observed_participation_and_off_clears_eligibility_immediately():
    worker, client, _, mono = rig()
    drive(worker, mono, 10)
    assert worker.status().observed_participation == client.device.participation
    assert worker.status().eligibility is not None
    worker.request_participation(False)
    assert worker.status().eligibility is None
    assert worker.status().observed_participation.enabled is True


def test_remote_replacement_clear_and_unsubscribe_are_immutable():
    worker, _client, _, mono = rig()
    events, statuses = [], []
    unsubscribe = worker.subscribe_remote(events.append)
    unstatus = worker.subscribe_status(statuses.append)
    drive(worker, mono, 10)
    from fractions import Fraction

    payload = events[-1].payload
    assert payload is worker._timing_context._state.receiver.payload
    assert payload.rows[0].character_name == "Bob"
    assert (payload.rows[0].outgoing_dps, payload.rows[0].incoming_dps) == (20, None)
    assert payload.rows[0].sampled_at_mono == Fraction(4997, 5)
    protected = worker._timing_context._state.receiver.records
    worker.request_participation(False)
    assert events[-1].kind == "clear" and events[-1].payload is None
    assert worker._timing_context._state.receiver.records is protected
    assert worker.status().participation == "queued"
    unsubscribe()
    unstatus()
    sizes = len(events), len(statuses)
    drive(worker, mono)
    assert (len(events), len(statuses)) == sizes


def test_real_thread_held_read_off_stop_restart_and_no_obsolete_completion():
    client = FakeRelayClient(device=DEVICE)
    client.hold = "read_snapshot"
    store = _InMemoryStateStore(PAIRED_STATE)
    worker = _worker(
        client, store=store, clock=time.monotonic, thread_factory=threading.Thread
    )
    events = []
    worker.subscribe_remote(events.append)
    assert worker.start()
    try:
        assert client.entered.wait(5)
        before = len(store.saves)
        started = time.monotonic()
        worker.submit(_snapshot(20))
        worker.submit(_snapshot(30))
        worker.request_participation(False)
        assert time.monotonic() - started < 0.2
        assert events[-1].kind == "clear"
        assert worker.stop(timeout=0.05) is False
        assert worker.start() is False
        with pytest.raises(RuntimeError):
            worker.iterate_once()
        assert len(store.saves) == before
        client.release.set()
        assert worker.stop(timeout=5)
        assert len(store.saves) == before
        assert not [e for e in events if e.kind == "replace"]
        assert worker.start()
    finally:
        client.release.set()
        assert worker.stop(timeout=5)


@pytest.mark.parametrize(
    "close_type", [OSError, http.client.HTTPException, urllib.error.URLError]
)
@pytest.mark.parametrize("read_fails", [False, True])
def test_http_error_cleanup_cannot_reach_worker_unexpected_traceback(
    caplog, close_type, read_fails
):
    from test_fleetsharing_controls import ClosingErrorStream, closing_error_transport

    from wingman.fleetsharing.client import FleetRelayClient

    stream = ClosingErrorStream(close_type, OSError if read_fails else None)
    relay = FleetRelayClient(
        PAIRED_STATE.relay_origin, transport=closing_error_transport(stream)
    )
    worker = _worker(relay)
    worker.iterate_once()
    # Device bootstrap admits endpoint-local service_unavailable; catalogue's
    # older coarse status fallback was server_error. Cleanup must preserve both.
    assert worker.status().detail == (
        "transport_error" if read_fails else "service_unavailable"
    )
    assert stream.close_attempts == 1 and stream.read_amounts == [65537]
    assert stream.private_context not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_fairness_control_burst_serves_each_overdue_periodic_class_within_slots():
    worker, client, _, mono = rig()
    drive(worker, mono, 12, _snapshot(42))
    mono[0] += 61
    before = len(client.calls)
    for _ in range(24):
        worker.request_source_start(1, UUID)
        drive(worker, mono, 1, _snapshot(43))
    calls = [k for k, _, _ in client.calls[before:] if k in READ_OPERATIONS]
    for operation in (
        "fetch_device",
        "fetch_catalogue",
        "fetch_eligibility",
        "read_snapshot",
    ):
        assert operation in calls[:12], (operation, calls)
    assert client.cadence_refusals == 0


def test_source_429_is_bounded_while_other_controls_and_periodic_work_continue(
    tmp_path,
):
    worker, client, _, mono = signed_rig(tmp_path)
    client.errors["control_source"] = FleetRelayError(429, "rate_limited", "capacity")
    worker.request_source_start(1, UUID)
    drive(worker, mono, 40, lambda now: _source(42, now))
    attempts = [t for k, t, _ in client.calls if k == "control_source"]
    assert len(attempts) <= 6
    assert all(b - a >= 1 for a, b in pairwise(attempts))
    assert client.publish_calls and any(
        k == "read_snapshot" for k, _, _ in client.calls
    )
    worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    drive(worker, mono, 10)
    assert client.device.participation.enabled is False


def test_source_backoff_and_confirmed_off_progress_without_publication_claim():
    # B portion of the mixed source-429/PUB test: D still owes timed publication.
    worker, client, _, mono = rig()
    client.errors["control_source"] = FleetRelayError(429, "rate_limited", "capacity")
    worker.request_source_start(1, UUID)
    drive(worker, mono, 40)
    attempts = [t for k, t, _ in client.calls if k == "control_source"]
    assert 1 <= len(attempts) <= 6
    assert all(b - a >= 1 for a, b in pairwise(attempts))
    assert any(k == "fetch_device" for k, _, _ in client.calls)
    assert worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    drive(worker, mono, 10)
    assert client.participation_calls == [(False, 1)]
    assert not client.device.participation.enabled
    assert client.cadence_refusals == 0


@pytest.mark.parametrize("value", [None, "bad", NOW.replace(tzinfo=None)])
def test_utc_failure_cannot_send_or_extend_expiry(value):
    worker, client, _, mono = rig()
    worker._utc_clock = lambda: value
    drive(worker, mono, 4)
    assert not client.calls
    assert worker.status().state == "error"
    assert worker.request_source_start(1, UUID) is None


def test_expiry_conversion_is_not_restamped_by_wall_clock_changes():
    device = replace(DEVICE, session_expires_at="2026-09-07T12:01:30.000Z")
    worker, client, _, mono = rig(device=device)
    drive(worker, mono, 2)
    worker._utc_clock = lambda: NOW - timedelta(hours=1)
    mono[0] += 31
    drive(worker, mono, 2)
    assert client.renew_calls


def test_off_during_remote_delivery_fences_remaining_subscribers():
    worker, _, _, mono = rig()
    received = []

    def inhibit(event):
        if event.kind == "replace":
            worker.request_participation(False)

    worker.subscribe_remote(inhibit)
    worker.subscribe_remote(received.append)
    drive(worker, mono, 10)
    assert received and all(event.kind == "clear" for event in received)


def test_successful_empty_remote_replaces_and_failed_read_does_not_emit():
    worker, client, _, mono = rig()
    events = []
    worker.subscribe_remote(events.append)
    drive(worker, mono, 10)
    client.remote = replace(client.remote, rows=())
    drive(worker, mono, 6)
    assert events[-1].kind == "replace" and events[-1].payload.rows == ()
    before = len(events)
    client.errors["read_snapshot"] = FleetRelayError(None, "transport_error", "lost")
    drive(worker, mono, 6)
    assert len(events) == before


def test_projection_coalesces_heartbeats_omission_and_stale_drop(tmp_path):
    worker, client, _, mono = signed_rig(tmp_path)
    drive(worker, mono, 8, lambda now: _source(42, now))
    before = len(client.publish_calls)
    worker.submit(_source(20, mono[0]))
    latest = _source(30, mono[0])
    worker.submit(latest)
    drive(worker, mono, 2)
    assert client.publish_calls[-1][1] == (p.CombatRow(1, 30, 0, 0, ()),)
    assert len(client.publish_calls) == before + 1
    drive(
        worker,
        mono,
        5,
        lambda now: FakePublicationSource(
            replace(latest.snapshot, sampled_at_mono=now)
        ),
    )
    assert len(client.publish_calls) > before + 1
    before = len(client.publish_calls)
    worker.submit(_source(30, mono[0], character="Nobody"))
    drive(worker, mono, 2)
    assert len(client.publish_calls) == before  # Uncertain ownership is not empty.
    worker.submit(_source(0, mono[0], inactive=True))
    drive(worker, mono, 2)
    assert client.publish_calls[-1][1] == ()
    before = len(client.publish_calls)
    drive(worker, mono, 12, lambda now: _source(0, now, inactive=True))
    assert len(client.publish_calls) == before
    worker.submit(_source(99, mono[0]))
    mono[0] += 6
    drive(worker, mono, 4)
    assert len(client.publish_calls) == before


def test_no_key_load_or_periodic_io_when_dormant_even_after_startup_probe():
    worker, client, store, mono = rig(enabled=False)

    def bad_unwrap(blob):
        pytest.fail("dormant key access")

    worker._unwrap_private_key = bad_unwrap
    worker.resume_pending()
    drive(worker, mono, 50, _snapshot(42))
    assert store.loads == 1 and not store.saves and not client.calls


def test_fresh_setup_refuses_to_discard_old_identity_commands():
    pending = s.PendingParticipation(UUID, True, 1)
    original = replace(
        PAIRED_STATE,
        pending_source_commands=(p.StopSource(UUID, 0, UUID, DATE, None),),
        pending_participation=pending,
        auth_pause=s.AuthPause("device_revoked"),
    )
    worker, client, store, mono = rig(state=original, enabled=False)
    worker.resume_pending()
    drive(worker, mono, 4)
    assert not client.calls
    worker.request_pairing(mode="fresh", configured_origin="https://relay.test")
    drive(worker, mono, 10)
    assert (
        not client.pair_keys and not client.controls and not client.participation_calls
    )
    assert store.load() == original
    assert worker.status().detail == "unresolved_history"


def test_unpaired_control_rejection_remains_visible_without_network_or_key():
    worker, client, _, mono = rig(state=s.EMPTY, enabled=False)
    worker.request_source_start(1, UUID)
    drive(worker, mono, 3)
    assert worker.status().state == "refused"
    assert worker.status().detail == "needs_pairing"
    assert not client.calls


def test_unproved_fresh_and_ordinary_pairing_do_not_rotate_registered_key():
    worker, client, store, mono = rig(enabled=False)
    worker.request_pairing(mode="fresh")
    drive(worker, mono, 3)
    assert worker.status().detail == "fresh_key_not_authorized"
    assert not client.calls and not store.saves
    worker.request_pairing()
    drive(worker, mono, 3)
    assert worker.status().detail == "use_key_recovery"
    assert store.load().identity == PAIRED_STATE.identity


def test_explicit_origin_change_never_sends_old_identity_to_new_origin():
    worker, client, store, mono = rig(enabled=False)
    origins = []
    worker._client_factory = lambda origin: origins.append(origin) or client
    worker.request_pairing(mode="upgrade", configured_origin="https://other.test")
    drive(worker, mono, 2)
    assert not origins and not client.calls and not store.saves
    assert store.load().relay_origin == PAIRED_STATE.relay_origin


def test_start_retries_keep_original_timestamp_and_uuid_before_sixty_seconds():
    worker, client, _, mono = rig(enabled=False)
    client.errors["control_source"] = FleetRelayError(
        503, "service_unavailable", "down"
    )
    source_id = worker.request_source_start(1, UUID)
    drive(worker, mono, 12)
    client.errors.clear()
    drive(worker, mono, 12)
    assert client.controls == [p.StartSource(source_id, 1, UUID, DATE)]


@pytest.mark.parametrize(
    "operation",
    ["set_participation", "control_source", "complete_recovery", "complete_pairing"],
)
def test_control_response_loss_reconciles_across_actual_json_restart(
    tmp_path, operation
):
    path = tmp_path / "state.json"
    original = (
        replace(PAIRED_STATE, session_id=None)
        if operation == "complete_recovery"
        else PAIRED_STATE
    )
    s.save(path, original)
    worker, client, _, mono = rig()
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    if operation == "set_participation":
        drive(worker, mono, 2)
        assert worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
    elif operation == "control_source":
        source_id = worker.request_source_start(1, UUID)
    elif operation == "complete_pairing":
        worker.request_pairing(mode="upgrade")
    client.loss.add(operation)
    for _ in range(15):
        drive(worker, mono, 1)
        if operation not in client.loss:
            break
    assert operation not in client.loss
    assert worker.stop()
    replacement = _worker(
        client, timing_context=worker._timing_context, utc_clock=client.utc
    )
    replacement._load_state = lambda: s.load(path)
    replacement._save_state = lambda state: s.save(path, state)
    replacement.resume_pending()
    drive(replacement, mono, 30)
    if operation == "set_participation":
        assert client.participation_calls == [(False, 1)]
        assert s.load(path).pending_participation is None
    elif operation == "control_source":
        assert client.controls == [p.StartSource(source_id, 1, UUID, DATE)] * 2
        assert not s.load(path).pending_source_commands
    else:
        assert s.load(path).pending_recovery is None and s.load(path).session_id
        assert client.recoveries == (2 if operation == "complete_recovery" else 1)
        assert len(client.pair_keys) == (1 if operation == "complete_pairing" else 0)
    assert client.cadence_refusals == 0


def test_json_pending_off_stop_resume_after_restart_without_settings_on(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        PAIRED_STATE,
        last_revision=13,
        pending_participation=s.PendingParticipation(UUID, False, 1),
        pending_source_commands=(p.StopSource(UUID, 0, UUID, DATE, None),),
    )
    s.save(path, original)
    worker, client, _, mono = rig(enabled=False)
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    worker.resume_pending()
    drive(worker, mono, 15)
    assert client.calls[0][2] == 14
    assert (
        not s.load(path).pending_source_commands
        and s.load(path).pending_participation is None
    )
    assert (
        client.source_views[UUID].state == "ended"
        and not client.device.participation.enabled
    )
    before = len(client.calls)
    drive(worker, mono, 30)
    assert len(client.calls) == before


def test_preserved_lifecycle_is_idempotent_non_daemon_named_and_bounded():
    worker, _, _, _ = rig(enabled=False)
    made = []

    def factory(**kwargs):
        made.append(kwargs)
        return _noop_thread_factory(**kwargs)

    worker._thread_factory = factory
    assert worker.stop()
    assert worker.start() and worker.start()
    assert len(made) == 1
    assert made[0]["name"] == "fleet-sharing-worker"
    assert made[0]["daemon"] is False
    assert worker.stop() and worker.stop()


def test_preserved_real_thread_mailbox_publishes_latest_after_held_publication(
    tmp_path,
):
    _, client, store, _ = signed_rig(tmp_path)
    client.hold = "publish_snapshot"
    start = time.monotonic()
    worker = _worker(
        client,
        store=store,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        utc_clock=lambda: NOW + timedelta(seconds=time.monotonic() - start),
    )
    worker.submit(_source(10, time.monotonic()))
    assert worker.start()
    try:
        assert client.entered.wait(5)
        started = time.monotonic()
        worker.submit(_source(20, time.monotonic()))
        worker.submit(_source(30, time.monotonic()))
        assert time.monotonic() - started < 0.2
        assert len(client.signed_publications) == 1
        assert (
            json.loads(client.signed_publications[0]["request"].data)["rows"][0][
                "outgoing_dps"
            ]
            == 10
        )
        assert (
            s.load(store.path).last_revision
            == client.signed_publications[0]["revision"]
        )
        client.release.set()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and len(client.publish_calls) < 2:
            time.sleep(0.01)
        assert [rows[0].outgoing_dps for _, rows in client.publish_calls[:2]] == [
            10,
            30,
        ]
    finally:
        client.release.set()
        assert worker.stop(timeout=5)


def test_preserved_real_thread_submit_flood_cannot_shorten_publish_retry(tmp_path):
    _, client, store, _ = signed_rig(tmp_path)
    client.errors["publish_snapshot"] = FleetRelayError(500, "server_error", "down")
    start = time.monotonic()
    worker = _worker(
        client,
        store=store,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        utc_clock=lambda: NOW + timedelta(seconds=time.monotonic() - start),
    )
    worker.submit(_source(10, time.monotonic()))
    assert worker.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(
            k == "publish_snapshot" for k, _, _ in client.calls
        ):
            time.sleep(0.01)
        attempts = [t for k, t, _ in client.calls if k == "publish_snapshot"]
        assert len(attempts) == 1
        client.errors.clear()
        until = time.monotonic() + 0.4
        while time.monotonic() < until:
            worker.submit(_source(11, time.monotonic()))
            time.sleep(0.01)
        assert len([t for k, t, _ in client.calls if k == "publish_snapshot"]) == 1
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and not client.publish_calls:
            worker.submit(_source(11, time.monotonic()))
            time.sleep(0.01)
        attempts = [t for k, t, _ in client.calls if k == "publish_snapshot"]
        assert len(attempts) == 2 and attempts[1] - attempts[0] >= 1
        assert len(client.signed_publications) == 2
        assert (
            client.signed_publications[1]["started"]
            >= client.signed_publications[0]["completed"] + 1
        )
        assert client.publish_calls[-1][1] == (p.CombatRow(1, 11, 0, 0, ()),)
    finally:
        assert worker.stop(timeout=5)


def test_preserved_client_construction_failure_is_bounded_and_recoverable():
    worker, client, _, mono = rig()
    calls = []

    def factory(origin):
        calls.append(origin)
        if len(calls) == 1:
            raise ValueError("private construction detail")
        return client

    worker._client_factory = factory
    worker.iterate_once()
    assert (
        worker.status().state == "error" and worker.status().detail == "local_failure"
    )
    worker.iterate_once()
    assert len(calls) == 1 and not client.calls
    mono[0] += 1
    worker.iterate_once()
    assert worker.status().state == "active" and len(calls) == 2


@pytest.mark.parametrize("unwrap", [lambda blob: None, lambda blob: b"short"])
def test_preserved_unusable_key_never_reaches_network(unwrap):
    worker, client, store, mono = rig()
    worker._unwrap_private_key = unwrap
    drive(worker, mono, 5)
    assert worker.status().state == "error"
    assert not client.calls and not store.saves


def test_preserved_settings_predicate_exception_fails_closed_without_loading():
    worker, client, store, mono = rig()

    def unavailable():
        raise RuntimeError("settings unavailable")

    worker._sharing_enabled = unavailable
    drive(worker, mono, 5, _snapshot(42))
    assert worker.status().state == "stopped"
    assert not client.calls and not store.loads


def test_preserved_stale_mailbox_does_not_withdraw_a_previous_nonempty_publish(
    tmp_path,
):
    worker, client, _, mono = signed_rig(tmp_path)
    drive(worker, mono, 10, lambda now: _source(42, now))
    assert client.publish_calls[-1][1] == (p.CombatRow(1, 42, 0, 0, ()),)
    before = len(client.publish_calls)
    mono[0] += 6
    drive(worker, mono, 6)
    assert len(client.publish_calls) == before


def test_preserved_idle_turn_does_not_emit_a_new_contact_status():
    worker, client, _, _ = rig()
    statuses = []
    worker.subscribe_status(statuses.append)
    worker.iterate_once()
    before = len(statuses), len(client.calls)
    worker.iterate_once()
    assert (len(statuses), len(client.calls)) == before


def test_real_thread_start_response_cannot_erase_new_stop():
    client = FakeRelayClient(device=DEVICE)
    client.hold = "control_source"
    store = _InMemoryStateStore(PAIRED_STATE)
    worker = _worker(
        client,
        store=store,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        sharing_enabled=lambda: False,
    )
    source_id = worker.request_source_start(1, UUID)
    assert worker.start()
    try:
        assert client.entered.wait(5)
        before = len(store.saves)
        started = time.monotonic()
        original = store.load().pending_source_commands[0]
        assert worker.request_source_stop(
            source_id,
            expected_generation=1,
            expected_automatic=None,
            supersedes=original,
        )
        assert time.monotonic() - started < 0.2
        client.release.set()
        deadline = time.monotonic() + 4
        while (
            time.monotonic() < deadline
            and client.source_views.get(source_id, None) is None
        ):
            time.sleep(0.01)
        # The first completion's attempt was fenced; any later writes retain
        # the pending Start until the queued same-ID Stop is persisted.
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            view = client.source_views.get(source_id)
            if view and view.state == "ended":
                break
            time.sleep(0.01)
        assert client.source_views[source_id].state == "ended"
        assert all(value.pending_source_commands for value in store.saves[before:-1])
        assert isinstance(client.controls[-1], p.StopSource)
        assert client.controls[-1].source_id == source_id
        assert client.controls[-1].expected_generation == 1
        assert client.controls[-1].expected_automatic is None
    finally:
        client.release.set()
        assert worker.stop(timeout=5)


def test_coordinator_cadence_and_local_metrics_continue_while_publish_is_held(tmp_path):
    from tests.test_fleetsharing_worker_state4 import FileStore
    from tests.test_telemetry_gamelogs import NOW as LOG_NOW
    from tests.test_telemetry_gamelogs import OUTGOING_DAMAGE_LINE, _log
    from tests.test_telemetry_source_admission import _threaded_runtime

    # Keep the real autonomous dispatcher/publisher cadence witness, but replace
    # uncertified producer doubles with C23's actual reset-cut/producer startup.
    runtime = _threaded_runtime(tmp_path)
    coordinator = runtime.coordinator
    store = FileStore(tmp_path / "cadence-sharing.json")
    store.save(PAIRED_STATE)
    client = SignedPublicationRelay(store=store, device=COMBAT_DEVICE)
    client.hold = "publish_snapshot"
    start = time.monotonic()
    worker = _worker(
        client,
        store=store,
        clock=time.monotonic,
        utc_clock=lambda: NOW + timedelta(seconds=time.monotonic() - start),
        thread_factory=threading.Thread,
    )
    snapshots = []
    progressed = threading.Event()

    def receive(snapshot):
        snapshots.append(snapshot)
        if client.entered.is_set():
            progressed.set()

    coordinator.subscribe_fleet(receive)
    coordinator.subscribe_admitted_fleet(worker.submit)
    worker.start()
    try:
        coordinator.reconcile()
        assert runtime.admitted.wait(5)
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE.replace("11:30:00", "12:00:00"))
        runtime.stream.scan_once(LOG_NOW)
        assert client.entered.wait(5)
        before = len(snapshots)
        progressed.clear()
        assert progressed.wait(3), "autonomous dispatcher stalled behind HTTP"
        assert len(snapshots) > before
        assert snapshots[-1].rows[0].dps == 30
        assert client.signed_publications
    finally:
        client.release.set()
        assert worker.stop(timeout=5)
        assert coordinator.stop(timeout=5)


@pytest.mark.parametrize(
    "boundary",
    [
        "source_journal",
        "renew_expiry",
        "participation_ack",
        "pair_session",
        "auth_pause",
    ],
)
def test_additional_persistence_boundaries_cannot_advance_unsaved_state(boundary):
    worker, client, store, mono = rig()
    if boundary == "source_journal":
        worker.request_source_start(1, UUID)
        store.fail = lambda state: bool(state.pending_source_commands)
    elif boundary == "renew_expiry":
        client.device = replace(DEVICE, session_expires_at="2026-09-07T12:00:20.000Z")
        # Fail the returned renewal expiry, not the bootstrap expiry.
        store.fail = lambda state: (
            bool(client.renew_calls)
            and state.session_expires_at == client.device.session_expires_at
        )
    elif boundary == "participation_ack":
        drive(worker, mono, 2)
        assert worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
        store.fail = lambda state: (
            bool(client.participation_calls) and state.pending_participation is None
        )
    elif boundary == "pair_session":
        worker.request_pairing(mode="upgrade")
        store.fail = lambda state: state.session_id == PAIRED_SESSION
    else:
        store._state = replace(PAIRED_STATE, session_id=None)
        client.recovery_result = "device_revoked"
        store.fail = lambda state: state.auth_pause is not None
    drive(worker, mono, 10)
    assert worker._state == store.load()
    if boundary == "pair_session":
        assert all(session != PAIRED_SESSION for session in client.sessions)
    elif boundary == "auth_pause":
        assert store.load().auth_pause is None
    elif boundary == "source_journal":
        assert not client.controls
    else:
        assert worker.status().state == "error"
        if boundary == "participation_ack":
            assert client.participation_calls == [(False, 1)]
            assert store.load().pending_participation.attempted
            assert worker.status().detail == "persistence_failed"


def test_off_save_failure_inhibits_immediately_and_never_claims_ack():
    worker, client, store, mono = rig()
    events = []
    worker.subscribe_remote(events.append)
    drive(worker, mono, 10, _snapshot(42))
    store.fail = lambda state: state.pending_participation is not None
    worker.request_participation(False)
    before = len(client.calls)
    assert events[-1].kind == "clear"
    drive(worker, mono, 10, _snapshot(100))
    assert len(client.calls) == before
    assert worker.status().participation == "queued"
    assert worker.status().detail == "persistence_failed"
    assert client.device.participation.enabled


def test_pairing_completion_conflict_polls_bounded_and_never_marks_revoked():
    worker, client, store, mono = rig(state=s.EMPTY, enabled=False)
    client.errors["complete_pairing"] = FleetRelayError(
        409, "not_completable", "not approved"
    )
    worker.request_pairing(configured_origin="https://relay.test")
    drive(worker, mono, 20)
    calls = [t for k, t, _ in client.calls if k == "complete_pairing"]
    assert 1 < len(calls) <= 5
    assert store.load().auth_pause is None
    assert worker.status().approval_url == "https://relay.test/approve"
    client.errors.clear()
    drive(worker, mono, 40)
    assert store.load().session_id == PAIRED_SESSION


def test_expired_unadmitted_start_does_not_claim_server_acknowledgement():
    start = p.StartSource(UUID, 1, UUID, "2026-09-07T11:58:00.000Z")
    worker, client, _, mono = rig(
        state=replace(PAIRED_STATE, pending_source_commands=(start,)), enabled=False
    )
    worker.resume_pending()
    drive(worker, mono, 10)
    assert not client.controls and not client.source_views
    assert worker._state.pending_source_commands == (start,)
    assert worker.status().source_control != "acknowledged"
    assert worker.request_dismiss_source(
        start, binding=worker.status().metadata.binding
    )
    worker.iterate_once()
    assert worker._state.pending_source_commands == ()
    assert not client.controls


@pytest.mark.parametrize("kind", ["participation", "source"])
def test_control_superseded_after_selection_is_fenced_before_dispatch(kind):
    worker, client, _, mono = rig(
        device=replace(DEVICE, participation=p.Participation(False, 2))
    )
    drive(worker, mono, 4)
    if kind == "participation":
        assert worker.request_participation(
            True, expected_generation=2, binding=worker.status().metadata.binding
        )
    else:
        source_id = worker.request_source_start(1, UUID)
    choose = worker._scheduler.choose
    reached = []

    def supersede(work, now):
        chosen = choose(work, now)
        expected = "set_participation" if kind == "participation" else "control_source"
        if chosen and chosen.operation == expected and not reached:
            reached.append(chosen)
            if kind == "participation":
                worker.request_participation(
                    False,
                    expected_generation=2,
                    binding=worker.status().metadata.binding,
                    supersedes=worker._state.pending_participation,
                )
            else:
                worker.request_source_stop(
                    source_id,
                    expected_generation=0,
                    expected_automatic=None,
                    supersedes=chosen.payload,
                )
        return chosen

    worker._scheduler.choose = supersede
    for _ in range(6):
        drive(worker, mono, 1)
        if reached:
            break
    assert len(reached) == 1, "intended selection barrier never reached"
    assert client.participation_calls == [] and client.controls == []
    worker._scheduler.choose = choose
    drive(worker, mono, 10)
    if kind == "source":
        assert len(client.controls) == 1
        assert isinstance(client.controls[0], p.StopSource)
        assert client.controls[0].source_id == source_id
        assert client.controls[0].expected_generation == 0
    else:
        assert not client.device.participation.enabled


def test_same_instance_restart_reobserves_before_any_publication():
    worker, client, _, mono = rig()
    drive(worker, mono, 10, _snapshot(42))
    worker.stop()
    client.device = replace(DEVICE, participation=p.Participation(False, 9))
    before = len(client.publish_calls)
    worker.start()
    worker.submit(_snapshot(999))
    drive(worker, mono, 4)
    assert len(client.publish_calls) == before
    worker.stop()


def test_control_queued_from_status_callback_cannot_be_overwritten_by_old_active():
    worker, client, _, mono = rig(
        device=replace(DEVICE, participation=p.Participation(False, 2))
    )
    drive(worker, mono, 4)
    assert worker.request_participation(
        True, expected_generation=2, binding=worker.status().metadata.binding
    )
    submitted = []

    def callback(status):
        if status.participation == "acknowledged" and not submitted:
            submitted.append(True)
            worker.request_participation(
                False, expected_generation=3, binding=status.metadata.binding
            )

    worker.subscribe_status(callback)
    for _ in range(6):
        drive(worker, mono, 1)
        if submitted:
            break
    assert submitted
    assert worker.status().participation == "queued"
    assert worker.status().local_inhibited
    assert not client.publish_calls


def test_postproof_refusal_status_is_not_overwritten_by_active_completion():
    worker, client, _, mono = rig(state=replace(PAIRED_STATE, session_id=None))
    client.recovery_result = "device_revoked"
    statuses = []
    worker.subscribe_status(statuses.append)
    drive(worker, mono, 5)
    last_refused = max(
        i for i, status in enumerate(statuses) if status.detail == "needs_fresh_key"
    )
    assert not any(status.state == "active" for status in statuses[last_refused:])


def test_source_watch_close_stops_periodic_session_renewal_as_well():
    worker, client, _, mono = rig(enabled=False)
    worker.set_source_watch(True)
    drive(worker, mono, 8)
    worker.set_source_watch(False)
    before = len(client.calls)
    mono[0] += 700
    drive(worker, mono, 8)
    assert len(client.calls) == before
