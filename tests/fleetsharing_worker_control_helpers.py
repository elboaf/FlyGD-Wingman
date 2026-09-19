"""Bounded real-client B transport fixture, not publication/receiver authority."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from tests.test_fleetsharing_client import Response, framing_headers, request_binding
from tests.test_fleetsharing_worker import DEVICE, EXPIRY, TOKEN, UUID
from tests.test_fleetsharing_worker_automatic import OFF, receipt_body, status
from tests.test_fleetsharing_worker_controls import wire
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient


class ControlRelay:
    """Complete control DTOs through FleetRelayClient, with exact source receipts."""

    def __init__(self, worker, store):
        self.worker, self.store = worker, store
        self.calls, self.sources, self.starts, self.receipts = [], {}, {}, {}
        self.device, self.consent = DEVICE, OFF
        self.before = self.after = None
        self.approval_url = "https://relay.test/approve"
        self.approved = False
        worker._client_factory = lambda origin: FleetRelayClient(
            origin, transport=self.transport
        )

    def transport(self, request, timeout):
        saved = s.load(self.store.path)
        revision = request.get_header("X-fleet-revision")
        if revision is not None:
            assert saved.last_revision == int(revision)
        self.calls.append((request, saved))
        if self.before:
            self.before(request, saved)
        body, code = self.reply(request, saved)
        if self.after:
            self.after(request, saved)
        return Response(
            json.dumps(body).encode(), framing_headers(request_binding(request)), code
        )

    def reply(self, request, saved):
        path = urlsplit(request.full_url).path
        body = json.loads(request.data) if request.data else None
        if path.endswith("/recovery-challenges"):
            assert saved.pending_recovery.request_id == body["request_id"]
            assert saved.pending_recovery.issued_at == body["issued_at"]
            return {
                "protocol": 2,
                "challenge_id": UUID,
                "request_id": body["request_id"],
                "nonce": TOKEN,
                "expires_at": EXPIRY,
            }, 200
        if "/recovery-challenges/" in path:
            assert saved.pending_recovery.completion_attempted
            return {
                "protocol": 2,
                "result": "reconnected",
                "device_id": UUID,
                "session_id": "B" * 42 + "A",
                "session_expires_at": self.device.session_expires_at,
                "approved_capabilities": list(self.device.approved_capabilities),
                "participation": wire(self.device.participation),
            }, 200
        if path.endswith("/pairing-requests"):
            assert saved.pending_pairing is not None
            return {
                "protocol": 2,
                "pairing_id": UUID,
                "approval_url": self.approval_url,
                "expires_at": EXPIRY,
            }, 200
        if "/pairing-requests/" in path:
            assert saved.pending_pairing.completion_attempted
            if self.approved:
                return {
                    "protocol": 2,
                    "session_id": "C" * 42 + "A",
                    "catalogue": {"revision": 1, "characters": []},
                }, 200
            return {"protocol": 2, "error": "not_completable"}, 409
        if path.endswith("/device"):
            return {"protocol": 2, **wire(self.device)}, 200
        if path.endswith("/participation"):
            pending = saved.pending_participation
            assert (
                pending.attempted
                and pending.enabled == body["enabled"]
                and pending.expected_generation == body["expected_generation"]
            )
            if body["expected_generation"] != self.device.participation.generation:
                return {"protocol": 2, "error": "conflict"}, 409
            self.device = replace(
                self.device,
                participation=p.Participation(
                    body["enabled"], body["expected_generation"] + 1
                ),
            )
            return {
                "protocol": 2,
                "participation": wire(self.device.participation),
            }, 200
        if "/receipts/" in path:
            receipt = self.receipts.get(path.rsplit("/", 1)[1])
            if receipt is None:
                return {"protocol": 2, "error": "receipt_not_found"}, 404
            return {
                "protocol": 2,
                "receipt": receipt,
                "status": wire(status(self.consent)),
            }, 200
        if path.endswith("/automatic-verification"):
            if request.method == "GET":
                return {"protocol": 2, "status": wire(status(self.consent))}, 200
            command = p.parse_automatic_command(body)
            assert (
                saved.automatic.pending.command == command
                and saved.automatic.pending.attempted
            )
            if (command.expected_generation, command.expected_revision) != (
                self.consent.generation,
                self.consent.revision,
            ):
                return {"protocol": 2, "error": "conflict"}, 409
            if not self.consent.enabled and not command.enabled:
                return {
                    "protocol": 2,
                    "request_id": command.request_id,
                    "result": "already_off",
                    "receipt": None,
                    "status": wire(status(self.consent)),
                }, 200
            self.consent = (
                p.Consent(
                    command.expected_generation + 1,
                    command.expected_revision + 1,
                    True,
                    UUID,
                    command.intent_created_at,
                    None,
                    None,
                )
                if command.enabled
                else replace(
                    self.consent,
                    enabled=False,
                    revision=self.consent.revision + 1,
                    disabled_at=command.intent_created_at,
                    closed_reason="explicit_off",
                )
            )
            receipt = receipt_body(command, self.consent)
            self.receipts[command.request_id] = receipt
            return {
                "protocol": 2,
                "request_id": command.request_id,
                "result": "applied",
                "receipt": receipt,
                "status": wire(status(self.consent)),
            }, 200
        if path.endswith("/sources"):
            if request.method == "GET":
                return {
                    "protocol": 2,
                    "sources": [wire(self.sources[k]) for k in sorted(self.sources)],
                    "characters": [
                        wire(p.SourceCharacter(1, "Alice", UUID, True, True))
                    ],
                }, 200
            command = p.parse_source_command(body)
            assert command in saved.pending_source_commands
            key = command.source_id.lower()
            source = self.sources.get(key)
            if (
                isinstance(command, p.SourceStop)
                and command.request_id in self.receipts
            ):
                receipt = self.receipts[command.request_id]
                if receipt["command"] != body:
                    return {"protocol": 2, "error": "request_id_conflict"}, 409
                return {
                    "protocol": 2,
                    "request_id": command.request_id,
                    "result": "replayed",
                    "receipt": receipt,
                    "source": receipt["source"],
                    "automatic_effect": receipt["automatic_effect"],
                    "status": wire(status(self.consent)),
                }, 200
            if isinstance(command, p.SourceStart) and self.starts.get(key) == command:
                return {"protocol": 2, "source": wire(source)}, 200
            age = (
                self.worker._utc_clock()
                - datetime.fromisoformat(command.intent_created_at)
            ).total_seconds()
            if not 0 <= age < 60:
                return {"protocol": 2, "error": "invalid_intent"}, 400
            if isinstance(command, p.SourceStart):
                if source is not None:
                    return {"protocol": 2, "error": "conflict"}, 409
                self.starts[key] = command
                source = p.SourceView(
                    command.source_id,
                    1,
                    command.character_id,
                    "active",
                    None,
                    None,
                    None,
                )
                self.sources[key] = source
                return {"protocol": 2, "source": wire(source)}, 200
            if command.expected_generation != (
                source.generation if source else 0
            ) or command.expected_automatic != (source.automatic if source else None):
                return {"protocol": 2, "error": "conflict"}, 409
            # This fixture offers manual sources only; no automatic provenance is guessed.
            assert command.expected_automatic is None
            ended = p.SourceView(
                command.source_id,
                (source.generation + 1) if source else 1,
                source.character_id if source else None,
                "ended",
                "stopped",
                None,
                None,
            )
            effect = "manual_only" if source else "unknown_cancelled"
            accepted = self.worker._utc_text()
            expires = (
                (datetime.fromisoformat(accepted) + timedelta(hours=24))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            receipt = {
                "kind": "source_stop",
                "command": body,
                "accepted_at": accepted,
                "expires_at": expires,
                "source": wire(ended),
                "automatic_effect": effect,
                "consent": wire(self.consent),
            }
            self.sources[key], self.receipts[command.request_id] = ended, receipt
            result = {
                "protocol": 2,
                "request_id": command.request_id,
                "result": "applied",
                "receipt": receipt,
                "source": wire(ended),
                "automatic_effect": effect,
                "status": wire(status(self.consent)),
            }
            p.parse_source_result(result, command)
            return result, 200
        if path.endswith("/catalogue"):
            return {"protocol": 2, "revision": 1, "characters": []}, 200
        return {"protocol": 2, "error": "service_unavailable"}, 503
