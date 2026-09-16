"""Single-attempt fleet-v2 HTTP boundary, using the unchanged fleet-v1 signatures.

Every signed method uses the SAME caller-owned session revision sequence/lane.
Scheduling, clocks, consent, attempted revisions and journals belong to the caller.
A response is usable only after framing, request binding and the whole DTO pass;
this alone does not establish runtime authority or a five-second clock anchor.
"""

from __future__ import annotations

import http.client
import json
import re
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256

from . import crypto, protocol
from .config import canonical_origin
from .model import FleetCatalogue

TIMEOUT_S = 5.0
MAX_RESPONSE_BYTES = 65536  # All errors and pre-session successes only.
MAX_SIGNED_RESPONSE_BYTES = 1048576
MAX_SNAPSHOT_RESPONSE_BYTES = 67108864
MAX_AUTOMATIC_RESPONSE_BYTES = 16384
CATALOGUE_PATH = "/api/fleet/v2/catalogue"
SNAPSHOT_PATH = "/api/fleet/v2/snapshot"
PAIRING_REQUESTS_PATH = "/api/fleet/v2/pairing-requests"
SESSION_PATH = "/api/fleet/v2/session"
DEVICE_PATH = "/api/fleet/v2/device"
PARTICIPATION_PATH = "/api/fleet/v2/participation"
ELIGIBILITY_PATH = "/api/fleet/v2/eligibility"
SOURCES_PATH = "/api/fleet/v2/sources"
RECOVERY_PATH = "/api/fleet/v2/recovery-challenges"
AUTOMATIC_PATH = "/api/fleet/v2/automatic-verification"
RECEIPTS_PATH = AUTOMATIC_PATH + "/receipts/"

# Only literal route shapes enter HTTP. Selector validation is repeated here so
# even the raw-byte signing seam cannot admit query/encoded/trailing segments.
_METHODS = {
    CATALOGUE_PATH: "GET",
    SNAPSHOT_PATH: "GET, PUT",
    SESSION_PATH: "PUT",
    DEVICE_PATH: "GET, PUT",
    PARTICIPATION_PATH: "PUT",
    ELIGIBILITY_PATH: "GET",
    SOURCES_PATH: "GET, PUT",
    AUTOMATIC_PATH: "GET, PUT",
    RECEIPTS_PATH: "GET",
    PAIRING_REQUESTS_PATH: "POST",
    PAIRING_REQUESTS_PATH + "/complete": "POST",
    RECOVERY_PATH: "POST",
    RECOVERY_PATH + "/complete": "POST",
}


class FleetRelayError(Exception):
    """Closed codes/fixed text only; malformed errors carry no actionable status.

    A generic 401/409 is not a proven recovery outcome. In particular, preserving
    such a status on malformed JSON would trigger old workers' coarse branches.
    """

    def __init__(self, status: int | None, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _malformed() -> FleetRelayError:
    return FleetRelayError(
        None, "malformed_response", "Fleet relay response had an unexpected shape."
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    # Redirects could forward proofs or signed headers to another origin/path.
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def _issued_at(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return protocol.utc_date(
        now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _route(path: str) -> str:
    protocol.literal_v2_path(path)
    if path.startswith(RECEIPTS_PATH):
        protocol.uuid4_lower(path[len(RECEIPTS_PATH) :])
        return RECEIPTS_PATH
    for base in (PAIRING_REQUESTS_PATH, RECOVERY_PATH):
        if path.startswith(base + "/") and path.endswith("/complete"):
            protocol.uuid(path[len(base) + 1 : -len("/complete")])
            return base + "/complete"
    if path not in _METHODS or path.endswith("/complete"):
        raise ValueError("Fleet request path has an unexpected shape.")
    return path


def _request_limits(path: str, method: str, body: bytes) -> tuple[str, int]:
    route = _route(path)
    if method not in _METHODS[route].split(", ") or not isinstance(body, bytes):
        raise ValueError("Fleet request has an unexpected shape.")
    request_bound = 0
    response_bound = MAX_SIGNED_RESPONSE_BYTES
    if method == "POST":
        request_bound, response_bound = 2048, MAX_RESPONSE_BYTES
    elif route in (AUTOMATIC_PATH, RECEIPTS_PATH):
        request_bound = 2048 if method == "PUT" else 0
        response_bound = MAX_AUTOMATIC_RESPONSE_BYTES
    elif route == SNAPSHOT_PATH:
        request_bound = 524288 if method == "PUT" else 0
        if method == "GET":
            response_bound = MAX_SNAPSHOT_RESPONSE_BYTES
    elif method == "PUT" and route != SESSION_PATH:
        request_bound = 2048 if route == SOURCES_PATH else 1024
    if len(body) > request_bound:
        raise ValueError("Fleet request body was too large.")
    return route, response_bound


_SIGNED_ERRORS = {
    400: ("bad_headers", "bad_request", "update_required", "invalid_intent"),
    401: ("unauthorized",),
    403: ("forbidden",),
    405: ("method_not_allowed",),
    409: ("revision_replayed",),
    429: ("rate_limited",),
    503: ("service_unavailable",),
}
_PRE_SESSION_ERRORS = {
    400: ("bad_request", "update_required"),
    405: ("method_not_allowed",),
    503: ("feature_disabled", "service_unavailable"),
}


def _known_errors(
    route: str,
    method: str,
    status: int,
    command: protocol.SourceCommand | protocol.AutomaticCommand | None,
) -> tuple[str, ...]:
    if method == "POST":
        codes = _PRE_SESSION_ERRORS.get(status, ())
        if route == PAIRING_REQUESTS_PATH and status == 400:
            codes += ("invalid_key",)
        if route == PAIRING_REQUESTS_PATH + "/complete" and status == 409:
            codes += ("not_completable",)
        if route.endswith("/complete") and status == 404:
            codes += ("not_found",)
        if route in (RECOVERY_PATH, RECOVERY_PATH + "/complete"):
            if status == 401:
                codes += ("unauthorized",)
            if status == 429:
                codes += ("rate_limited",)
        return codes
    codes = _SIGNED_ERRORS.get(status, ())
    if route != DEVICE_PATH or method == "PUT":
        if status == 503:
            codes += ("feature_disabled",)
        if status == 403 and route not in (CATALOGUE_PATH, SESSION_PATH):
            codes += ("capability_required",)
    if status == 409 and method == "PUT":
        if route in (PARTICIPATION_PATH, SOURCES_PATH, AUTOMATIC_PATH):
            codes += ("conflict",)
        if route in (SOURCES_PATH, AUTOMATIC_PATH):
            codes += ("request_id_conflict",)
    if (
        status == 403
        and route == SOURCES_PATH
        and isinstance(command, protocol.SourceStart)
    ):
        codes += ("fleet_read_required",)
    if status == 403 and route == SNAPSHOT_PATH:
        codes += ("not_verified",)
    if status == 404 and route == RECEIPTS_PATH:
        codes += ("receipt_not_found",)
    if (
        status == 429
        and route == AUTOMATIC_PATH
        and isinstance(command, protocol.AutomaticCommand)
        and command.enabled
    ):
        codes += ("receipt_capacity",)
    return codes


def _validate_entity_headers(headers) -> None:
    # get_all, not get: repeated/mixed-case lines must not silently select one.
    content_types = headers.get_all("Content-Type", [])
    if len(content_types) != 1 or not re.fullmatch(
        r'application/json(?:\s*;\s*charset=(?:utf-8|"utf-8"))?',
        content_types[0],
        re.IGNORECASE,
    ):
        raise _malformed()
    cache = headers.get_all("Cache-Control", [])
    if (
        len(cache) != 1
        or [part.strip().lower() for part in cache[0].split(",")].count("no-store") != 1
    ):
        raise _malformed()
    encoding = headers.get_all("Content-Encoding", [])
    if encoding and (len(encoding) != 1 or encoding[0].lower() != "identity"):
        raise _malformed()


def _validate_success_headers(headers, expected_binding: str) -> None:
    _validate_entity_headers(headers)
    bindings = headers.get_all("X-Fleet-Request-Binding", [])
    if (
        len(bindings) != 1
        or not re.fullmatch(r"[0-9a-f]{64}", bindings[0])
        or bindings[0] != expected_binding
    ):
        raise _malformed()


def _parse(parser, data):
    try:
        return parser(data)
    except ValueError:
        raise _malformed() from None


def _decode_response(raw: bytes) -> dict:
    parsed = _parse(protocol.decode_wire_json, raw)
    if not isinstance(parsed, dict):
        raise _malformed()
    if (
        type(parsed.get("protocol")) is not int
        or parsed["protocol"] != protocol.API_VERSION
    ):
        raise FleetRelayError(
            None,
            "protocol_mismatch",
            "Fleet relay response used an unsupported protocol.",
        )
    return parsed


def _status_error(route, method, status, raw, headers, command) -> FleetRelayError:
    try:
        if len(raw) > MAX_RESPONSE_BYTES:
            raise _malformed()
        _validate_entity_headers(headers)
        data = _decode_response(raw)
        code = _parse(protocol.parse_error, data)
        if code not in _known_errors(route, method, status, command):
            raise _malformed()
        if code == "method_not_allowed" and headers.get_all("Allow", []) != [
            _METHODS[route]
        ]:
            raise _malformed()
    except FleetRelayError as exc:
        return exc
    return FleetRelayError(
        status, code, f"Fleet relay returned status {status} ({code})."
    )


@dataclass(frozen=True)
class PairingBegin:
    pairing_id: str
    approval_url: str
    expires_at: str


@dataclass(frozen=True)
class PairingComplete:
    session_id: str
    catalogue: FleetCatalogue


class FleetRelayClient:
    """One origin; credentials and immutable commands supplied by the caller.

    Every public operation accepts optional before_send(). It runs once, after
    validation/serialization/signing/Request construction, immediately before HTTP.
    Admission exceptions propagate unchanged; no HTTP attempt or revision undo is
    performed. The caller owns final lifetime checks and actual GET-start capture.
    """

    def __init__(self, origin: str, *, transport=_default_transport):
        self._origin = canonical_origin(origin)
        self._transport = transport

    def begin_pairing(
        self,
        public_key_spki: bytes,
        *,
        requested_capabilities: tuple[str, ...] = (),
        before_send: Callable[[], None] | None = None,
    ) -> PairingBegin:
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "public_key_spki_b64url": protocol.public_key_spki_b64url(
                    crypto.public_key_spki_b64url(public_key_spki)
                ),
                "requested_capabilities": list(
                    protocol.capabilities(list(requested_capabilities))
                ),
            }
        )
        result = _parse(
            lambda d: protocol.parse_pairing_begun(d, origin=self._origin),
            self._send_pre_session(PAIRING_REQUESTS_PATH, body, before_send),
        )
        return PairingBegin(result.pairing_id, result.approval_url, result.expires_at)

    def complete_pairing(
        self,
        pairing_id: str,
        challenge: bytes,
        private_key: bytes,
        *,
        before_send: Callable[[], None] | None = None,
    ) -> PairingComplete:
        pairing_id = protocol.uuid(pairing_id)
        if not isinstance(
            challenge, bytes
        ) or challenge != crypto.pairing_challenge_preimage(pairing_id):
            raise ValueError("Fleet pairing challenge has an unexpected shape.")
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "completion_signature": crypto.sign_request(private_key, challenge),
            }
        )
        result = _parse(
            protocol.parse_pairing_completed,
            self._send_pre_session(
                f"{PAIRING_REQUESTS_PATH}/{pairing_id}/complete",
                body,
                before_send,
            ),
        )
        return PairingComplete(result.session_id, result.catalogue)

    def fetch_catalogue(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> FleetCatalogue:
        return _parse(
            protocol.parse_catalogue,
            self._send_signed(
                CATALOGUE_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def publish_snapshot(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        sampled_at_ms: int,
        rows: tuple[protocol.CombatRow, ...],
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> None:
        """Send original sample/aggregates; withdrawal is exactly sample0/rows[]."""
        body = _json(_combat_body(sampled_at_ms, rows))
        data = self._send_signed(
            SNAPSHOT_PATH,
            "PUT",
            body,
            session_id,
            private_key,
            revision,
            now,
            before_send=before_send,
        )
        _parse(lambda d: protocol.envelope(d, ""), data)

    def renew_session(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> str:
        """Empty-body renewal; expiry scheduling belongs to the caller."""
        return _parse(
            protocol.parse_session,
            self._send_signed(
                SESSION_PATH,
                "PUT",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        ).expires_at

    def fetch_device(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.DeviceState:
        return _parse(
            protocol.parse_device,
            self._send_signed(
                DEVICE_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def acknowledge_capabilities(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        capabilities: tuple[str, ...],
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.DeviceState:
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "capabilities": list(protocol.capabilities(list(capabilities))),
            }
        )
        return _parse(
            protocol.parse_device,
            self._send_signed(
                DEVICE_PATH,
                "PUT",
                body,
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def set_participation(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        enabled: bool,
        expected_generation: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.Participation:
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "enabled": protocol.boolean(enabled),
                "expected_generation": protocol.integer(
                    expected_generation, 0, protocol.INT4_MAX - 1
                ),
            }
        )
        return _parse(
            protocol.parse_participation_response,
            self._send_signed(
                PARTICIPATION_PATH,
                "PUT",
                body,
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def fetch_eligibility(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.Eligibility:
        return _parse(
            protocol.parse_eligibility,
            self._send_signed(
                ELIGIBILITY_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def fetch_sources(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.Sources:
        return _parse(
            protocol.parse_sources,
            self._send_signed(
                SOURCES_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def control_source(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        command: protocol.SourceCommand,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.SourceStartResult | protocol.SourceStopResult:
        body = _json(protocol.source_command_body(command))
        return _parse(
            lambda d: protocol.parse_source_result(d, command),
            self._send_signed(
                SOURCES_PATH,
                "PUT",
                body,
                session_id,
                private_key,
                revision,
                now,
                command=command,
                before_send=before_send,
            ),
        )

    def fetch_automatic(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.AutomaticGet:
        return _parse(
            protocol.parse_automatic_get,
            self._send_signed(
                AUTOMATIC_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def control_automatic(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        command: protocol.AutomaticCommand,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.AutomaticResult:
        body = _json(protocol.automatic_command_body(command))
        return _parse(
            lambda d: protocol.parse_automatic_result(d, command),
            self._send_signed(
                AUTOMATIC_PATH,
                "PUT",
                body,
                session_id,
                private_key,
                revision,
                now,
                command=command,
                before_send=before_send,
            ),
        )

    def fetch_receipt(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        request_id: str,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.ReceiptGet:
        request_id = protocol.uuid4_lower(request_id)
        return _parse(
            lambda d: protocol.parse_receipt_get(d, expected_request_id=request_id),
            self._send_signed(
                RECEIPTS_PATH + request_id,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def read_snapshot(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.CombatSnapshot:
        return _parse(
            protocol.parse_snapshot,
            self._send_signed(
                SNAPSHOT_PATH,
                "GET",
                b"",
                session_id,
                private_key,
                revision,
                now,
                before_send=before_send,
            ),
        )

    def begin_recovery(
        self,
        *,
        private_key: bytes,
        request_id: str,
        issued_at: str,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.RecoveryChallenge:
        """Caller persists request_id/issued_at; retries preserve both and the proof."""
        spki = crypto.public_key_spki(private_key)
        preimage = crypto.recovery_initiation_preimage(
            self._origin, request_id, issued_at, spki
        )
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "public_key_spki_b64url": crypto.public_key_spki_b64url(spki),
                "request_id": request_id,
                "issued_at": issued_at,
                "initiation_signature": crypto.sign_request(private_key, preimage),
            }
        )
        return _parse(
            lambda d: protocol.parse_recovery_challenge(
                d, expected_request_id=request_id
            ),
            self._send_pre_session(
                RECOVERY_PATH,
                body,
                before_send,
            ),
        )

    def complete_recovery(
        self,
        *,
        private_key: bytes,
        challenge: protocol.RecoveryChallenge,
        before_send: Callable[[], None] | None = None,
    ) -> protocol.RecoveryResult:
        """Caller persists the challenge BEFORE this one-use completion.

        Loss stays unknown; never retry or infer revocation from an HTTP error.
        """
        protocol.parse_recovery_challenge(
            {"protocol": protocol.API_VERSION, **asdict(challenge)}
        )
        preimage = crypto.recovery_challenge_preimage(
            self._origin,
            challenge.challenge_id,
            challenge.nonce,
            crypto.public_key_spki(private_key),
        )
        body = _json(
            {
                "protocol": protocol.API_VERSION,
                "nonce": challenge.nonce,
                "recovery_signature": crypto.sign_request(private_key, preimage),
            }
        )
        return _parse(
            protocol.parse_recovery_result,
            self._send_pre_session(
                f"{RECOVERY_PATH}/{challenge.challenge_id}/complete",
                body,
                before_send,
            ),
        )

    def _send_pre_session(self, path, body, before_send=None) -> dict:
        _request_limits(path, "POST", body)
        attempt = secrets.token_urlsafe(32)
        return self._send(
            path,
            "POST",
            body,
            headers={"X-Fleet-Attempt": attempt},
            expected_binding=protocol.pre_session_request_binding(
                self._origin, path, attempt, body
            ),
            before_send=before_send,
        )

    def _send_signed(
        self,
        path: str,
        method: str,
        body: bytes,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None,
        *,
        command: protocol.SourceCommand | protocol.AutomaticCommand | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> dict:
        _request_limits(path, method, body)
        if method == "POST":
            raise ValueError("Fleet signed request has an unexpected method.")
        protocol.token(session_id)
        protocol.integer(revision)
        issued_at = _issued_at(now if now is not None else datetime.now(UTC))
        body_sha256 = sha256(body).hexdigest()
        canonical = crypto.canonical_fleet_request(
            protocol=protocol.SIGNING_SCHEME_VERSION,
            method=method,
            path=path,
            session_id=session_id,
            issued_at=issued_at,
            revision=revision,
            body_sha256=body_sha256,
        )
        headers = {
            "X-Fleet-Session": session_id,
            "X-Fleet-Issued-At": issued_at,
            "X-Fleet-Revision": str(revision),
            "X-Fleet-Body-SHA256": body_sha256,
            "X-Fleet-Signature": crypto.sign_request(private_key, canonical),
        }
        return self._send(
            path,
            method,
            body,
            headers=headers,
            expected_binding=protocol.signed_request_binding(canonical),
            command=command,
            before_send=before_send,
        )

    def _send(
        self,
        path: str,
        method: str,
        body: bytes,
        *,
        headers: dict,
        expected_binding: str,
        command: protocol.SourceCommand | protocol.AutomaticCommand | None = None,
        before_send: Callable[[], None] | None = None,
    ) -> dict:
        route, bound = _request_limits(path, method, body)
        request = urllib.request.Request(
            self._origin + path,
            data=(body or None),
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
                **headers,
            },
            method=method,
        )
        # This is outside the HTTP exception boundary: admission refusal is the
        # caller's control flow, including OSError/HTTPError, not transport loss.
        if before_send is not None:
            before_send()
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                status = response.status
                response_headers = response.headers
                if status == 200:
                    _validate_success_headers(response_headers, expected_binding)
                raw = response.read(
                    (bound if status == 200 else MAX_RESPONSE_BYTES) + 1
                )
        except urllib.error.HTTPError as exc:
            # HTTPError owns a stream too. Read only the error ceiling even for
            # snapshot GET, and suppress provider URL/key context on read/close.
            try:
                raw = exc.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, urllib.error.URLError, http.client.HTTPException):
                raise FleetRelayError(
                    None, "transport_error", "Fleet relay could not be reached."
                ) from None
            finally:
                # Sibling except clauses cannot catch this handler's cleanup.
                # A close failure must not expose raw context or replace a fully
                # read, validated closed error with an untrusted traceback.
                with suppress(
                    OSError, urllib.error.URLError, http.client.HTTPException
                ):
                    exc.close()
            raise _status_error(
                route, method, exc.code, raw, exc.headers, command
            ) from None
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            raise FleetRelayError(
                None, "transport_error", "Fleet relay could not be reached."
            ) from None
        if status != 200:
            raise _status_error(
                route, method, status, raw, response_headers, command
            ) from None
        if len(raw) > bound:
            raise _malformed()
        return _decode_response(raw)


def _combat_body(sampled_at_ms: int, rows: tuple[protocol.CombatRow, ...]) -> dict:
    # Validate internal values BEFORE JSON: 2.0 and an already-rounded fraction
    # are not made trustworthy by decoding their serialized numeric lexemes.
    if not isinstance(rows, tuple) or any(
        type(row) is not protocol.CombatRow for row in rows
    ):
        raise ValueError("Fleet combat rows have an unexpected shape.")
    body = {
        "protocol": protocol.API_VERSION,
        "sampled_at_ms": sampled_at_ms,
        "rows": [
            {
                "character_id": row.character_id,
                "outgoing_dps": row.outgoing_dps,
                "incoming_dps": row.incoming_dps,
                "activity_age_ms": row.activity_age_ms,
                "effects": [
                    {
                        "kind": effect.kind,
                        "observations": [
                            asdict(observation) for observation in effect.observations
                        ],
                    }
                    for effect in row.effects
                ],
            }
            for row in rows
        ],
    }
    protocol.parse_combat_put(body)
    return body


def _json(value: dict) -> bytes:
    return json.dumps(value).encode("utf-8")
