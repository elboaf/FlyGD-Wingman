"""Single-owner controls with a time-enforcing, CAS-aware relay, no network/DPAPI.

The prior one-pass catalogue+renew+publish expectations are deliberately replaced:
legacy unknown grants bootstrap, and Settings True is not an explicit On action.
"""

from __future__ import annotations

import http.client
import threading
import time
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from uuid import uuid4

import pytest

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayError, PairingBegin, PairingComplete
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow
from wingman.fleetsharing.worker import (
    FleetSharingWorker,
    _noop_thread_factory,
)
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
DATE = "2026-09-07T12:00:00.000Z"
EXPIRY = "2026-09-07T12:30:00.000Z"
UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TOKEN = "A" * 43
CAPS = (p.SHARED_CAPABILITY,)
KEY = bytes(32)
DEVICE = p.DeviceState(UUID, EXPIRY, True, CAPS, CAPS, CAPS, p.Participation(True, 1))
PAIRED_STATE = s.SharingState(
    identity=s.DeviceIdentity(
        "cHJvdGVjdGVk",
        crypto.canonical_device_public_key_b64(crypto.public_key_spki(KEY)),
    ),
    relay_origin="https://relay.test",
    session_id="session-1",
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
        self.valid_sessions = {"session-1": KEY} if registered else {}
        self.active_session = "session-1" if registered else None
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
        self.remote = (p.ObservedRemoteRow(2, "Bob", 20, (), "live", 400, UUID),)
        self.withdrawal_completed = False
        self.challenge = None
        self.recovery_result = "reconnected"
        self.recoveries = 0
        self.pair_keys = []
        self.hold = None
        self.entered = threading.Event()
        self.release = threading.Event()

    def _call(self, operation, args, apply):
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
        return self._call("fetch_device", args, lambda: self._session_device(args))

    def acknowledge_capabilities(self, **args):
        def apply():
            assert args["capabilities"] == CAPS
            return self._update_session(args, acknowledged_capabilities=CAPS)

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
        self.fetch_calls.append(args["revision"])
        return self._call("fetch_catalogue", args, lambda: self.catalogue)

    def renew_session(self, **args):
        self.renew_calls.append(args["revision"])

        def apply():
            expiry = _date(self.utc() + timedelta(minutes=30))
            self._update_session(args, session_expires_at=expiry)
            return expiry

        return self._call("renew_session", args, apply)

    def publish_snapshot(self, **args):
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
        return self._call("read_snapshot", args, lambda: self.remote)

    def fetch_sources(self, **args):
        return self._call(
            "fetch_sources",
            args,
            lambda: p.Sources(
                tuple(self.source_views.values()),
                (p.SourceCharacter(1, "Alice", UUID, True, True),),
            ),
        )

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
                    return current
                self.source_intents[command.source_id] = command
                # Provider activation is an explicit fixture simplification;
                # production initially returns pending, with the same CAS identity.
                current = p.SourceView(
                    command.source_id, 1, command.character_id, "active", None, None
                )
            else:
                if (
                    current.generation if current else 0
                ) != command.expected_generation:
                    raise FleetRelayError(409, "conflict", "stop")
                if current and current.state == "ended":
                    return current
                current = p.SourceView(
                    command.source_id,
                    (current.generation if current else 0) + 1,
                    current.character_id if current else None,
                    "ended",
                    "stopped",
                    None,
                )
            self.source_views[command.source_id] = current
            return current

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
                UUID,
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
            pairing_id = (
                "pair-id"
                if len(self.pair_keys) == 1
                else "pair-id-" + str(len(self.pair_keys))
            )
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

    def complete_pairing(self, pairing_id, challenge, private_key):
        def apply():
            binding = self.pairings.get(pairing_id)
            if (
                binding is None
                or binding[2]
                or self.utc() >= datetime.fromisoformat(binding[1])
            ):
                raise FleetRelayError(409, "conflict", "pairing consumed/expired")
            key = crypto.public_key_spki(private_key)
            if key != binding[0] or challenge != crypto.pairing_challenge_preimage(
                pairing_id
            ):
                raise FleetRelayError(401, "unauthorized", "pairing proof")
            if binding[3] and not self.device.feature_enabled:
                raise FleetRelayError(503, "feature_disabled", "pairing")
            grants = tuple(
                sorted(
                    set(binding[3])
                    | (
                        set(self.device.approved_capabilities)
                        if key in self.registered_keys
                        else set()
                    )
                )
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
            self._install_session("paired-session", private_key, device)
            return PairingComplete("paired-session", self.catalogue)

        return self._call("complete_pairing", {}, apply)


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
):
    mono = clock or (lambda: 1000.0)
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
        _clock=mono,
        _utc_clock=client.utc,
        _jitter=lambda: 0,
    )


def drive(worker, mono, turns=20, snapshot=None):
    for _ in range(turns):
        if snapshot:
            worker.submit(snapshot)
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


def test_simultaneous_periodic_controls_completion_cadence_and_withdrawal():
    from wingman.fleetsharing.scheduling import OPERATIONS

    assert dict(OPERATIONS) == OPERATION_BUCKETS
    worker, client, store, mono = rig()
    client.latency = lambda: mono.__setitem__(0, mono[0] + 0.2)
    drive(worker, mono, snapshot=_snapshot(42))
    assert client.publish_calls[-1][1] == (PublishRow(1, 42, ()),)
    mono[0] += 1800 - 65
    for _ in range(10):
        worker.request_source_start(1, UUID)
        drive(worker, mono, 1, _snapshot(43))
    worker.request_participation(False)
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


def test_injected_read_429_does_not_stall_publication_or_rejuvenate_remote():
    worker, client, _, mono = rig()
    events = []
    worker.subscribe_remote(events.append)
    drive(worker, mono, snapshot=_snapshot(42))
    replacements = [e for e in events if e.kind == "replace"]
    assert replacements
    old = replacements[-1]
    client.errors["read_snapshot"] = FleetRelayError(429, "rate_limited", "injected")
    before = len(client.publish_calls)
    drive(worker, mono, 10, _snapshot(43))
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
    worker.request_participation(True)
    drive(worker, mono, 10)
    assert client.participation_calls == [(True, 6)]


def test_participation_response_loss_reconciles_without_duplicate_cas():
    worker, client, store, mono = rig()
    worker.request_participation(False)
    client.loss.add("set_participation")
    drive(worker, mono, 20)
    assert client.participation_calls == [(False, 1)]
    assert store.load().pending_participation is None
    assert worker.status().participation == "acknowledged"


def test_start_then_stop_before_ack_fences_same_uuid_generation_zero():
    worker, client, store, mono = rig(enabled=False)
    source_id = worker.request_source_start(1, UUID)
    assert source_id and not store.saves and not client.calls
    assert worker.request_source_stop(source_id)
    drive(worker, mono, 15)
    assert client.controls == [p.StopSource(source_id, 0)]
    assert store.load().pending_source_commands == ()
    assert not client.publish_calls


def test_lost_start_stop_cas_reread_and_start_aba():
    worker, client, store, mono = rig(enabled=False)
    source_id = worker.request_source_start(1, UUID)
    client.loss.add("control_source")
    drive(worker, mono, 8)
    start = client.controls[0]
    assert start.source_id == source_id and start.intent_created_at == DATE
    assert len(client.controls) == 1
    assert worker.request_source_stop(source_id, expected_generation=0)
    new_id = worker.request_source_start(1, UUID)
    client.loss.add("control_source")
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
    assert "fetch_sources" in [k for k, _, _ in client.calls]
    assert store.load().pending_source_commands == ()


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
    assert not client.pair_keys and client.publish_calls
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
        client, state=s.load(path), clock=lambda: mono[0], utc_clock=client.utc
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
            pending_source_commands=(p.StopSource(UUID, 0),),
            pending_participation=s.PendingParticipation(UUID, False),
        )
    )
    assert worker.request_pairing(mode="upgrade")
    assert not store.saves and not client.calls
    client.loss.add("complete_pairing")
    drive(worker, mono, 35)
    assert client.pair_keys == [crypto.public_key_spki(KEY)]
    assert store.load().pending_source_commands == ()
    assert client.source_views[UUID].state == "ended"
    assert client.device.participation.enabled is False
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
    assert store.load().session_id == "paired-session"
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
    if boundary.startswith("participation") or boundary == "intent":
        worker.request_participation(False)
    if boundary == "source_ack":
        worker.request_source_stop(UUID)

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
    worker, client, _, mono = rig()
    events, statuses = [], []
    unsubscribe = worker.subscribe_remote(events.append)
    unstatus = worker.subscribe_status(statuses.append)
    drive(worker, mono, 10)
    assert events[-1].rows == client.remote
    assert events[-1].request_elapsed >= 0 and events[-1].receipt_monotonic <= mono[0]
    worker.request_participation(False)
    assert events[-1].kind == "clear" and events[-1].rows == ()
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
        "server_error" if read_fails else "service_unavailable"
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


def test_source_429_is_bounded_while_other_controls_and_periodic_work_continue():
    worker, client, _, mono = rig()
    client.errors["control_source"] = FleetRelayError(429, "rate_limited", "capacity")
    worker.request_source_start(1, UUID)
    drive(worker, mono, 40, _snapshot(42))
    attempts = [t for k, t, _ in client.calls if k == "control_source"]
    assert len(attempts) <= 6
    assert all(b - a >= 1 for a, b in pairwise(attempts))
    assert client.publish_calls and any(
        k == "read_snapshot" for k, _, _ in client.calls
    )
    worker.request_participation(False)
    drive(worker, mono, 10)
    assert client.device.participation.enabled is False


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
    client.remote = ()
    drive(worker, mono, 6)
    assert events[-1].kind == "replace" and events[-1].rows == ()
    before = len(events)
    client.errors["read_snapshot"] = FleetRelayError(None, "transport_error", "lost")
    drive(worker, mono, 6)
    assert len(events) == before


def test_projection_coalesces_heartbeats_omission_and_stale_drop():
    worker, client, _, mono = rig()
    drive(worker, mono, 8, _snapshot(42))
    before = len(client.publish_calls)
    worker.submit(_snapshot(20))
    worker.submit(_snapshot(30))
    drive(worker, mono, 2)
    assert client.publish_calls[-1][1] == (PublishRow(1, 30, ()),)
    assert len(client.publish_calls) == before + 1
    drive(worker, mono, 5, _snapshot(30))
    assert len(client.publish_calls) > before + 1
    worker.submit(_snapshot(30, character="Nobody"))
    drive(worker, mono, 2)
    assert client.publish_calls[-1][1] == ()
    before = len(client.publish_calls)
    drive(worker, mono, 12, _snapshot(30, character="Nobody"))
    assert len(client.publish_calls) == before
    worker.submit(_snapshot(99))
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


def test_fresh_setup_is_explicit_and_discards_old_identity_commands():
    pending = s.PendingParticipation(UUID, True, 1)
    original = replace(
        PAIRED_STATE,
        pending_source_commands=(p.StopSource(UUID, 0),),
        pending_participation=pending,
        auth_pause=s.AuthPause("device_revoked"),
    )
    worker, client, store, mono = rig(state=original, enabled=False)
    worker.resume_pending()
    drive(worker, mono, 4)
    assert not client.calls
    worker.request_pairing(mode="fresh", configured_origin="https://relay.test")
    drive(worker, mono, 10)
    assert client.pair_keys and not client.controls and not client.participation_calls
    assert (
        not store.load().pending_source_commands
        and store.load().pending_participation is None
    )


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
        worker.request_participation(False)
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
    replacement = _worker(client, clock=lambda: mono[0], utc_clock=client.utc)
    replacement._load_state = lambda: s.load(path)
    replacement._save_state = lambda state: s.save(path, state)
    replacement.resume_pending()
    drive(replacement, mono, 30)
    if operation == "set_participation":
        assert client.participation_calls == [(False, 1)]
        assert s.load(path).pending_participation is None
    elif operation == "control_source":
        assert client.controls == [p.StartSource(source_id, 1, UUID, DATE)]
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
        pending_participation=s.PendingParticipation(UUID, False),
        pending_source_commands=(p.StopSource(UUID, 0),),
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


def test_preserved_real_thread_mailbox_publishes_latest_after_held_publication():
    client = FakeRelayClient(device=DEVICE)
    client.hold = "publish_snapshot"
    worker = _worker(client, clock=time.monotonic, thread_factory=threading.Thread)
    worker.submit(_snapshot(10))
    assert worker.start()
    try:
        assert client.entered.wait(5)
        started = time.monotonic()
        worker.submit(_snapshot(20))
        worker.submit(_snapshot(30))
        assert time.monotonic() - started < 0.2
        client.release.set()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and len(client.publish_calls) < 2:
            time.sleep(0.01)
        assert [rows[0].dps for _, rows in client.publish_calls[:2]] == [10, 30]
    finally:
        client.release.set()
        assert worker.stop(timeout=5)


def test_preserved_real_thread_submit_flood_cannot_shorten_publish_retry():
    client = FakeRelayClient(device=DEVICE)
    client.errors["publish_snapshot"] = FleetRelayError(500, "server_error", "down")
    worker = _worker(client, clock=time.monotonic, thread_factory=threading.Thread)
    worker.submit(_snapshot(10))
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
            worker.submit(_snapshot(11))
            time.sleep(0.01)
        assert len([t for k, t, _ in client.calls if k == "publish_snapshot"]) == 1
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and not client.publish_calls:
            worker.submit(_snapshot(11))
            time.sleep(0.01)
        attempts = [t for k, t, _ in client.calls if k == "publish_snapshot"]
        assert len(attempts) == 2 and attempts[1] - attempts[0] >= 1
        assert client.publish_calls[-1][1] == (PublishRow(1, 11, ()),)
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


def test_preserved_stale_mailbox_does_not_withdraw_a_previous_nonempty_publish():
    worker, client, _, mono = rig()
    drive(worker, mono, 10, _snapshot(42))
    assert client.publish_calls[-1][1] == (PublishRow(1, 42, ()),)
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
        worker.request_source_stop(source_id)
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
        assert client.controls[-1] == p.StopSource(source_id, 1)
    finally:
        client.release.set()
        assert worker.stop(timeout=5)


def test_coordinator_cadence_and_local_metrics_continue_while_publish_is_held(tmp_path):
    from wingman.telemetry.coordinator import TelemetryCoordinator
    from wingman.telemetry.model import RosterSnapshot

    class Discovery:
        def subscribe(self, callback):
            return lambda: None

        def start(self):
            return True

        def stop(self, timeout=5):
            return True

        def request_scan(self):
            pass

        def snapshot(self):
            return RosterSnapshot(generation=1, clients=())

    class Stream:
        def subscribe_batches(self, callback):
            return lambda: None

        def start(self, folder):
            return True

        def stop(self, timeout=3):
            return True

        def health(self):
            return STREAM_HEALTH

    class Metrics:
        def reset(self):
            pass

        def consume(self, envelope):
            pass

        def snapshot(self, sequence, health):
            return _snapshot(24)

    client = FakeRelayClient(device=DEVICE)
    client.hold = "publish_snapshot"
    worker = _worker(client, clock=time.monotonic, thread_factory=threading.Thread)
    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: False,
        fleet_enabled=lambda: False,
        alerts_enabled=lambda: False,
        sharing_enabled=lambda: True,
        gamelogs_folder=lambda: tmp_path,
        discovery=Discovery(),
        stream=Stream(),
        metrics=Metrics(),
    )
    snapshots = []
    coordinator.subscribe_fleet(snapshots.append)
    coordinator.subscribe_fleet(worker.submit)
    worker.start()
    try:
        coordinator.reconcile()
        assert client.entered.wait(5)
        before = len(snapshots)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(snapshots) <= before:
            time.sleep(0.02)
        assert len(snapshots) > before
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
        worker.request_participation(False)
        store.fail = lambda state: (
            bool(client.participation_calls) and state.pending_participation is None
        )
    elif boundary == "pair_session":
        worker.request_pairing(mode="upgrade")
        store.fail = lambda state: state.session_id == "paired-session"
    else:
        store._state = replace(PAIRED_STATE, session_id=None)
        client.recovery_result = "device_revoked"
        store.fail = lambda state: state.auth_pause is not None
    drive(worker, mono, 10)
    assert worker._state == store.load()
    if boundary == "pair_session":
        assert all(session != "paired-session" for session in client.sessions)
    elif boundary == "auth_pause":
        assert store.load().auth_pause is None
    elif boundary == "source_journal":
        assert not client.controls
    else:
        assert worker.status().state == "error"


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
    client.errors["complete_pairing"] = FleetRelayError(409, "conflict", "not approved")
    worker.request_pairing(configured_origin="https://relay.test")
    drive(worker, mono, 20)
    calls = [t for k, t, _ in client.calls if k == "complete_pairing"]
    assert 1 < len(calls) <= 5
    assert store.load().auth_pause is None
    assert worker.status().approval_url == "https://relay.test/approve"
    client.errors.clear()
    drive(worker, mono, 40)
    assert store.load().session_id == "paired-session"


def test_expired_unadmitted_start_does_not_claim_server_acknowledgement():
    start = p.StartSource(UUID, 1, UUID, "2026-09-07T11:58:00.000Z")
    worker, client, _, mono = rig(
        state=replace(PAIRED_STATE, pending_source_commands=(start,)), enabled=False
    )
    worker.resume_pending()
    drive(worker, mono, 10)
    assert not client.controls and not client.source_views
    assert worker.status().source_control == "expired"


@pytest.mark.parametrize("kind", ["participation", "source"])
def test_control_superseded_after_selection_is_fenced_before_dispatch(kind):
    worker, client, _, mono = rig(
        device=replace(DEVICE, participation=p.Participation(False, 2))
    )
    if kind == "participation":
        worker.request_participation(True)
    else:
        source_id = worker.request_source_start(1, UUID)
    worker.iterate_once()  # bootstrap and bind the explicit intent
    mono[0] += 0.5
    choose = worker._scheduler.choose

    def supersede(work, now):
        chosen = choose(work, now)
        if kind == "participation":
            assert chosen.operation == "set_participation"
            worker.request_participation(False)
        else:
            assert chosen.operation == "control_source"
            worker.request_source_stop(source_id)
        return chosen

    worker._scheduler.choose = supersede
    worker.iterate_once()
    assert client.participation_calls == [] and client.controls == []
    worker._scheduler.choose = choose
    drive(worker, mono, 10)
    if kind == "source":
        assert client.controls == [p.StopSource(source_id, 0)]
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
    worker.request_participation(True)
    submitted = []

    def callback(status):
        if status.participation == "acknowledged" and not submitted:
            submitted.append(True)
            worker.request_participation(False)

    worker.subscribe_status(callback)
    drive(worker, mono, 2)
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
