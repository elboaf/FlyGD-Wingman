"""Single-attempt fleet-v1 HTTP boundary; no queue, revision allocation or retries.

Every signed method uses the SAME caller-owned session revision sequence. The
server has separate 500ms publish and control/read cadence buckets; the worker
must still serialize all signed calls. Scheduling, consent and persistence are
not transport responsibilities. Recovery admission is retryable only with the
original journaled request binding; completion is one-use even on response loss.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import quote, urlsplit

from . import crypto, projection, protocol
from .config import canonical_origin
from .model import FleetCatalogue, PublishRow

TIMEOUT_S = 5.0
MAX_RESPONSE_BYTES = 64 * 1024
MAX_SNAPSHOT_RESPONSE_BYTES = 1024 * 1024
CATALOGUE_PATH = "/api/fleet/v1/catalogue"
SNAPSHOT_PATH = "/api/fleet/v1/snapshot"
PAIRING_REQUESTS_PATH = "/api/fleet/v1/pairing-requests"
SESSION_PATH = "/api/fleet/v1/session"
DEVICE_PATH = "/api/fleet/v1/device"
PARTICIPATION_PATH = "/api/fleet/v1/participation"
ELIGIBILITY_PATH = "/api/fleet/v1/eligibility"
SOURCES_PATH = "/api/fleet/v1/sources"
RECOVERY_PATH = "/api/fleet/v1/recovery-challenges"


class FleetRelayError(Exception):
    """Only closed codes and fixed text, never raw bodies or exception context.

    A 401/replay/timeout is not a proven device revocation. Only a successfully
    parsed recovery completion result can require explicit fresh-key setup.
    """

    def __init__(self, status: int | None, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


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
    return now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


_PAIRING_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _validate_pairing_id(pairing_id: str) -> str:
    # Preserve the existing opaque V1 caller contract; URL quoting is additional
    # defence, not permission to put slashes or control characters in the path.
    if not isinstance(pairing_id, str) or not _PAIRING_ID_RE.fullmatch(pairing_id):
        raise ValueError("Fleet relay pairing id has an unexpected shape.")
    return pairing_id


def _classify_status(status: int) -> str:
    return {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        429: "rate_limited",
    }.get(status, "server_error" if 500 <= status < 600 else "bad_request")


# Only codes emitted by the particular route/method at this status are admitted.
# Everything else (including postproof result names in an error body) falls back
# to the old safe status classification. Recovery variants never enter this map.
_CONTROL_ERRORS = {
    400: ("bad_headers", "bad_request", "invalid_intent"),
    401: ("unauthorized",),
    403: ("forbidden",),
    409: ("revision_replayed",),
    429: ("rate_limited",),
    503: ("service_unavailable",),
}
_RECOVERY_ERRORS = {
    400: ("bad_request", "update_required"),
    401: ("unauthorized",),
    429: ("rate_limited",),
    503: ("feature_disabled", "service_unavailable"),
}


def _known_errors(path: str, method: str, status: int) -> tuple[str, ...]:
    if path == RECOVERY_PATH or (
        path.startswith(RECOVERY_PATH + "/") and path.endswith("/complete")
    ):
        return _RECOVERY_ERRORS.get(status, ())
    if path in (DEVICE_PATH, PARTICIPATION_PATH, ELIGIBILITY_PATH, SOURCES_PATH):
        codes = _CONTROL_ERRORS.get(status, ())
        if method == "PUT" and status == 400:
            codes += ("update_required",)
        if path != DEVICE_PATH or method == "PUT":
            if status == 403:
                codes += ("capability_required",)
            if status == 503:
                codes += ("feature_disabled",)
        if (
            method == "PUT"
            and path in (PARTICIPATION_PATH, SOURCES_PATH)
            and status == 409
        ):
            codes += ("conflict",)
        if method == "PUT" and path == SOURCES_PATH and status == 403:
            codes += ("fleet_read_required",)
        return codes
    # Existing publication/catalogue callers keep their coarse classifications.
    # Only explicit update guidance is new on the legacy request-body endpoints.
    if (
        status == 400
        and method in ("PUT", "POST")
        and (
            path in (SNAPSHOT_PATH, PAIRING_REQUESTS_PATH)
            or path.startswith(PAIRING_REQUESTS_PATH + "/")
        )
    ):
        return ("update_required",)
    return ()


def _status_error(path: str, method: str, status: int, raw: bytes) -> FleetRelayError:
    code = _classify_status(status)
    if len(raw) <= MAX_RESPONSE_BYTES:
        try:
            data = protocol.envelope(protocol.decode_json(raw), "error")
            known = _known_errors(path, method, status)
            code = protocol.enum(data["error"], known)
        except ValueError:
            pass  # Untrusted/unknown details are intentionally not surfaced.
    return FleetRelayError(
        status, code, f"Fleet relay returned status {status} ({code})."
    )


def _parse(parser, data):
    try:
        return parser(data)
    except ValueError:
        raise FleetRelayError(
            None, "malformed_response", "Fleet relay response had an unexpected shape."
        ) from None


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
    """One origin; credentials and durable bindings always supplied by the caller."""

    def __init__(self, origin: str, *, transport=_default_transport):
        self._origin = canonical_origin(origin)
        self._transport = transport

    def _validate_approval_url(self, raw_url: str) -> str:
        try:
            protocol.text(raw_url, 2048)
            if any(c.isspace() for c in raw_url) or "\\" in raw_url:
                raise ValueError
            parsed = urlsplit(raw_url)
            if (
                not parsed.scheme
                and not parsed.netloc
                and raw_url.startswith("/")
                and not raw_url.startswith("//")
            ):
                return self._origin + raw_url
            if canonical_origin(f"{parsed.scheme}://{parsed.netloc}") != self._origin:
                raise ValueError
            return raw_url
        except ValueError:
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay approval URL was not same-origin HTTPS.",
            ) from None

    def begin_pairing(
        self,
        public_key_spki: bytes,
        *,
        requested_capabilities: tuple[str, ...] | None = None,
    ) -> PairingBegin:
        body = {
            "protocol": 1,
            "public_key_spki_b64url": crypto.public_key_spki_b64url(public_key_spki),
        }
        if requested_capabilities is not None:
            body["requested_capabilities"] = list(
                protocol.capabilities(list(requested_capabilities))
            )
        data = self._send(PAIRING_REQUESTS_PATH, "POST", _json(body), headers=None)
        _parse(
            lambda d: protocol.envelope(d, "pairing_id approval_url expires_at"), data
        )
        return PairingBegin(
            _parse(_validate_pairing_id, data["pairing_id"]),
            self._validate_approval_url(data["approval_url"]),
            _parse(protocol.utc_date, data["expires_at"]),
        )

    def complete_pairing(
        self, pairing_id: str, challenge: bytes, private_key: bytes
    ) -> PairingComplete:
        pairing_id = _validate_pairing_id(pairing_id)
        body = _json(
            {
                "protocol": 1,
                "completion_signature": crypto.sign_request(private_key, challenge),
            }
        )
        path = f"{PAIRING_REQUESTS_PATH}/{quote(pairing_id, safe='')}/complete"
        data = self._send(path, "POST", body, headers=None)
        _parse(lambda d: protocol.envelope(d, "session_id catalogue"), data)
        return PairingComplete(
            _parse(_opaque_session, data["session_id"]),
            _parse(
                lambda d: protocol.parse_catalogue(d, nested=True), data["catalogue"]
            ),
        )

    def fetch_catalogue(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> FleetCatalogue:
        return _parse(
            protocol.parse_catalogue,
            self._send_signed(
                CATALOGUE_PATH, "GET", b"", session_id, private_key, revision, now
            ),
        )

    def publish_snapshot(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        rows: tuple[PublishRow, ...],
        now: datetime | None = None,
    ) -> None:
        # Keep the existing sparse V1 publication bytes/schema, including withdrawal.
        projection.validate_publish_batch(rows)
        body = _json(
            {
                "protocol": 1,
                "rows": [
                    {
                        "character_id": row.character_id,
                        "dps": row.dps,
                        "ewar": list(row.ewar),
                    }
                    for row in rows
                ],
            }
        )
        data = self._send_signed(
            SNAPSHOT_PATH, "PUT", body, session_id, private_key, revision, now
        )
        _parse(lambda d: protocol.envelope(d, ""), data)

    def renew_session(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> str:
        """Empty-body renewal in place; expiry scheduling still belongs to the worker."""
        data = self._send_signed(
            SESSION_PATH, "PUT", b"", session_id, private_key, revision, now
        )
        _parse(lambda d: protocol.envelope(d, "expires_at"), data)
        return _parse(protocol.utc_date, data["expires_at"])

    def fetch_device(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> protocol.DeviceState:
        return _parse(
            protocol.parse_device,
            self._send_signed(
                DEVICE_PATH, "GET", b"", session_id, private_key, revision, now
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
    ) -> protocol.DeviceState:
        body = _json(
            {
                "protocol": 1,
                "capabilities": list(protocol.capabilities(list(capabilities))),
            }
        )
        return _parse(
            protocol.parse_device,
            self._send_signed(
                DEVICE_PATH, "PUT", body, session_id, private_key, revision, now
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
    ) -> protocol.Participation:
        body = _json(
            {
                "protocol": 1,
                "enabled": protocol.boolean(enabled),
                "expected_generation": protocol.integer(
                    expected_generation, 0, protocol.INT4_MAX - 1
                ),
            }
        )
        return _parse(
            protocol.parse_participation_response,
            self._send_signed(
                PARTICIPATION_PATH, "PUT", body, session_id, private_key, revision, now
            ),
        )

    def fetch_eligibility(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> protocol.Eligibility:
        return _parse(
            protocol.parse_eligibility,
            self._send_signed(
                ELIGIBILITY_PATH, "GET", b"", session_id, private_key, revision, now
            ),
        )

    def fetch_sources(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> protocol.Sources:
        return _parse(
            protocol.parse_sources,
            self._send_signed(
                SOURCES_PATH, "GET", b"", session_id, private_key, revision, now
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
    ) -> protocol.SourceView:
        body = _json(protocol.source_command_body(command))
        source = _parse(
            protocol.parse_source_control,
            self._send_signed(
                SOURCES_PATH, "PUT", body, session_id, private_key, revision, now
            ),
        )
        if source.source_id.lower() != command.source_id.lower():
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay response had an unexpected shape.",
            )
        return source

    def read_snapshot(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> tuple[protocol.RemoteRow, ...]:
        return _parse(
            protocol.parse_snapshot,
            self._send_signed(
                SNAPSHOT_PATH, "GET", b"", session_id, private_key, revision, now
            ),
        )

    def begin_recovery(
        self, *, private_key: bytes, request_id: str, issued_at: str
    ) -> protocol.RecoveryChallenge:
        """Caller persists request_id/issued_at BEFORE calling; retry uses both unchanged.

        No device ID is needed: a migrated V1 identity recovers by registered key.
        Freshness is checked by the server, not by changing the caller's timestamp.
        """
        spki = crypto.public_key_spki(private_key)
        preimage = crypto.recovery_initiation_preimage(
            self._origin, request_id, issued_at, spki
        )
        data = self._send(
            RECOVERY_PATH,
            "POST",
            _json(
                {
                    "protocol": 1,
                    "public_key_spki_b64url": crypto.public_key_spki_b64url(spki),
                    "request_id": request_id,
                    "issued_at": issued_at,
                    "initiation_signature": crypto.sign_request(private_key, preimage),
                }
            ),
            headers=None,
        )
        challenge = _parse(protocol.parse_recovery_challenge, data)
        if challenge.request_id != request_id:
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay response had an unexpected shape.",
            )
        return challenge

    def complete_recovery(
        self, *, private_key: bytes, challenge: protocol.RecoveryChallenge
    ) -> protocol.RecoveryResult:
        """Caller persists the challenge BEFORE calling; completion is one-use.

        Lost replies stay unknown. No hidden retry, consent change or key rotation;
        a proven conflict/revocation result requires explicit fresh-key setup.
        """
        protocol.parse_recovery_challenge({"protocol": 1, **asdict(challenge)})
        preimage = crypto.recovery_challenge_preimage(
            self._origin,
            challenge.challenge_id,
            challenge.nonce,
            crypto.public_key_spki(private_key),
        )
        path = f"{RECOVERY_PATH}/{quote(challenge.challenge_id, safe='')}/complete"
        return _parse(
            protocol.parse_recovery_result,
            self._send(
                path,
                "POST",
                _json(
                    {
                        "protocol": 1,
                        "nonce": challenge.nonce,
                        "recovery_signature": crypto.sign_request(
                            private_key, preimage
                        ),
                    }
                ),
                headers=None,
            ),
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
    ) -> dict:
        _opaque_session(session_id)
        protocol.integer(revision)
        issued_at = _issued_at(now if now is not None else datetime.now(UTC))
        body_sha256 = sha256(body).hexdigest()
        canonical = crypto.canonical_fleet_request(
            protocol=1,
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
        return self._send(path, method, body, headers=headers)

    def _send(
        self, path: str, method: str, body: bytes, *, headers: dict | None
    ) -> dict:
        request = urllib.request.Request(
            self._origin + path,
            data=(body or None),
            headers={"Content-Type": "application/json", **(headers or {})},
            method=method,
        )
        bound = (
            MAX_SNAPSHOT_RESPONSE_BYTES
            if path == SNAPSHOT_PATH and method == "GET"
            else MAX_RESPONSE_BYTES
        )
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                status = getattr(response, "status", 200)
                raw = response.read(
                    (bound if status == 200 else MAX_RESPONSE_BYTES) + 1
                )
        except urllib.error.HTTPError as exc:
            # HTTPError owns a response stream too. Bound even hostile error JSON
            # and close it on every path, including a read timeout. Suppress raw
            # exception chaining: urllib messages can contain URLs or echoed keys.
            try:
                raw = exc.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, urllib.error.URLError, http.client.HTTPException):
                raw = b""
            finally:
                # Cleanup is inside this handler, so sibling except clauses do
                # not catch it. A close failure must not replace the safe HTTP
                # classification with a raw transport traceback in the worker.
                with suppress(
                    OSError, urllib.error.URLError, http.client.HTTPException
                ):
                    exc.close()
            raise _status_error(path, method, exc.code, raw) from None
        except (
            TimeoutError,
            urllib.error.URLError,
            OSError,
            http.client.HTTPException,
        ):
            raise FleetRelayError(
                None, "transport_error", "Fleet relay could not be reached."
            ) from None
        if status != 200:
            raise _status_error(path, method, status, raw)
        if len(raw) > bound:
            raise FleetRelayError(
                status, "malformed_response", "Fleet relay response was too large."
            )
        parsed = _parse(protocol.decode_json, raw)
        if not isinstance(parsed, dict):
            raise FleetRelayError(
                status,
                "malformed_response",
                "Fleet relay response had an unexpected shape.",
            )
        if type(parsed.get("protocol")) is not int or parsed["protocol"] != 1:
            raise FleetRelayError(
                status,
                "protocol_mismatch",
                "Fleet relay response used an unsupported protocol.",
            )
        return parsed


def _opaque_session(value: object) -> str:
    # Existing signing callers and migrated V1 state treat session IDs as opaque.
    # New recovery results additionally require canonical 32-byte tokens.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Fleet relay session has an unexpected shape.")
    return value


def _json(value: dict) -> bytes:
    return json.dumps(value).encode("utf-8")
