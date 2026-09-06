"""Signed HTTP transport for authGD's fleet-relay protocol boundary.

A pure protocol boundary only: pairing (unauthenticated by design,
matching authGD's own `pairing-requests` routes) and the three signed
device requests Wingman's sparse projection actually needs -- fetching
the device's authenticated character catalogue, publishing a snapshot,
and renewing the device's own session in place. Nothing here polls,
retries, subscribes to the telemetry coordinator, tracks a revision
counter across calls, or reads/renders a remote row: those belong to a
later coordinator-wiring task. Every request is exactly one attempt --
a signed publish carries a strictly increasing revision, so silently
retrying a request whose delivery is unknown would risk exactly the
duplicate-write hazard `wingman.eveesi.EsiClient.post_once` documents
for ESI mutations.

authGD's fleet-v1 protocol shares ONE monotonic revision counter and ONE
cadence bucket per session across every signed request kind -- catalogue,
snapshot, and session renewal alike (`docs/fleet-protocol.md`, authGD
repo). That means a caller must never have more than one signed request
for the same device in flight at once: this module is a stateless
transport with no queue of its own, so the caller
(`wingman.fleetsharing.worker.FleetSharingWorker`) is what enforces that
rule by running every signed request for one device strictly
sequentially, one at a time.

Every response is required to be `protocol: 1`-flagged JSON, matching the
design's "explicit major integer" compatibility rule: an unsupported
major, a non-JSON body, or an unexpected shape are all rejected the same
way a caller would want to know about them, never silently guessed at.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import quote, urlsplit

from . import crypto, projection
from .model import CatalogueCharacter, FleetCatalogue, PublishRow

TIMEOUT_S = 5.0
MAX_RESPONSE_BYTES = 64 * 1024

CATALOGUE_PATH = "/api/fleet/v1/catalogue"
SNAPSHOT_PATH = "/api/fleet/v1/snapshot"
PAIRING_REQUESTS_PATH = "/api/fleet/v1/pairing-requests"
SESSION_PATH = "/api/fleet/v1/session"


class FleetRelayError(Exception):
    """Every relay-client failure.

    `message` and `str(exception)` never embed a request body, signature,
    or session value -- only a fixed classification derived from the
    HTTP status (or its absence). `status` is the real numeric status
    when a response was actually received, and `None` when it was not:
    either a transport-level failure (`code == "transport_error"`) or a
    field-shape defect discovered only after parsing, where the numeric
    status is no longer meaningful to report.
    """

    def __init__(self, status: int | None, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on every relay request.

    Ported whole from `wingman.eveauth.sso`'s identical handler: a signed
    request's headers authenticate one exact method+path, and following a
    3xx would resend them -- or, on the unsigned pairing calls, a
    device's own public key material -- to wherever Location points.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def _issued_at(now: datetime) -> str:
    """RFC3339 millisecond-precision UTC, `Z`-suffixed -- the exact shape
    authGD's fixture and route header parser expect
    (`tests/fixtures/fleet-signature-v1.json`'s own `issued_at`).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# A pairing id is an opaque server-issued token (authGD's actual shape is
# a UUID, `tests/fixtures/fleet-pairing-v1.json`); restricting it to the
# URL-unreserved charset (RFC 3986) before it is ever spliced into a
# request path refuses a hostile or corrupted value -- an embedded "/",
# "..", or newline -- outright, rather than relying solely on
# `urllib.parse.quote` (applied afterwards, in `complete_pairing`) to make
# it harmless.
_PAIRING_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _validate_pairing_id(pairing_id: str) -> str:
    if not isinstance(pairing_id, str) or not _PAIRING_ID_RE.fullmatch(pairing_id):
        raise ValueError("Fleet relay pairing id has an unexpected shape.")
    return pairing_id


def _classify_status(status: int) -> str:
    """A fixed, non-oracle classification. Deliberately coarse: the
    server's own JSON `error` field is never read for this -- reading an
    arbitrary server-controlled string into a caller-visible exception is
    exactly the class of leak the "redacted errors" requirement guards
    against, and a numeric HTTP status is already enough for a caller to
    decide whether to back off, refuse, or surface a disconnected state.
    """
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 409:
        return "conflict"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "server_error"
    return "bad_request"


@dataclass(frozen=True)
class PairingBegin:
    pairing_id: str
    approval_url: str
    expires_at: str


@dataclass(frozen=True)
class PairingComplete:
    session_id: str
    catalogue: FleetCatalogue


def _require_str(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise FleetRelayError(
            None, "malformed_response", f"Fleet relay response was missing '{key}'."
        )
    return value


def _parse_catalogue(data: object) -> FleetCatalogue:
    if not isinstance(data, dict):
        raise FleetRelayError(
            None, "malformed_response", "Fleet relay catalogue was not an object."
        )
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise FleetRelayError(
            None, "malformed_response", "Fleet relay catalogue had an invalid revision."
        )
    raw_characters = data.get("characters")
    if not isinstance(raw_characters, list):
        raise FleetRelayError(
            None, "malformed_response", "Fleet relay catalogue had no character list."
        )
    characters = []
    for entry in raw_characters:
        if not isinstance(entry, dict):
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay catalogue had a malformed character entry.",
            )
        character_id = entry.get("character_id")
        character_name = entry.get("character_name")
        if (
            isinstance(character_id, bool)
            or not isinstance(character_id, int)
            or character_id <= 0
        ):
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay catalogue had an invalid character id.",
            )
        if not isinstance(character_name, str) or not character_name:
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay catalogue had an invalid character name.",
            )
        characters.append(
            CatalogueCharacter(character_id=character_id, character_name=character_name)
        )
    return FleetCatalogue(revision=revision, characters=tuple(characters))


class FleetRelayClient:
    """One authGD relay origin.

    Stateless past its own opener/timeout: the caller supplies every
    session id, revision, and key on every call. This is a transport
    primitive, not a finished Wingman settings/pairing UI, and not a
    subscriber to anything -- `wingman.fleetsharing.client` never imports
    `wingman.telemetry`.
    """

    def __init__(self, origin: str, *, transport=_default_transport):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Fleet relay origin must be a bare https:// origin.")
        self._origin = f"https://{parsed.netloc}"
        self._transport = transport

    def _validate_approval_url(self, raw_url: str) -> str:
        """Refuse an `approval_url` that is not this exact relay origin.

        A Member opens `approval_url` in their own browser to approve a
        pairing request (a later task's concern) -- this client is the
        only place that ever sees the raw server-supplied string, so it
        is the only place that can refuse a relay response trying to
        redirect that browser to an attacker-controlled origin (a
        malicious or compromised relay, or a response-shape bug).
        authGD's own route actually returns a bare same-origin path
        (`/fleet/pair/<id>`, Task 6's `pairing-requests/route.ts`), which
        this resolves against the configured origin; an absolute URL is
        accepted only when it is `https`, carries no userinfo, and
        resolves to this exact configured origin.
        """
        parsed = urlsplit(raw_url)
        if parsed.scheme == "" and parsed.netloc == "":
            if not raw_url.startswith("/"):
                raise FleetRelayError(
                    None,
                    "malformed_response",
                    "Fleet relay approval URL was not a same-origin path.",
                )
            return self._origin + raw_url
        if parsed.scheme != "https":
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay approval URL was not https.",
            )
        if parsed.username is not None or parsed.password is not None:
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay approval URL carried userinfo.",
            )
        if parsed.netloc.casefold() != urlsplit(self._origin).netloc.casefold():
            raise FleetRelayError(
                None,
                "malformed_response",
                "Fleet relay approval URL was not the configured relay origin.",
            )
        return raw_url

    # -- pairing: unauthenticated by design, matching authGD's own routes --

    def begin_pairing(self, public_key_spki: bytes) -> PairingBegin:
        """POST /api/fleet/v1/pairing-requests.

        Carries no browser cookie and no signed headers -- there is no
        session yet. Returns only the pairing id and approval URL; a
        Member approves the pairing request in a browser out of this
        method's scope entirely.
        """
        body = json.dumps(
            {
                "protocol": crypto.PROTOCOL_VERSION,
                "public_key_spki_b64url": crypto.public_key_spki_b64url(
                    public_key_spki
                ),
            }
        ).encode("utf-8")
        data = self._send(PAIRING_REQUESTS_PATH, "POST", body, headers=None)
        approval_url = self._validate_approval_url(_require_str(data, "approval_url"))
        return PairingBegin(
            pairing_id=_require_str(data, "pairing_id"),
            approval_url=approval_url,
            expires_at=_require_str(data, "expires_at"),
        )

    def complete_pairing(
        self, pairing_id: str, challenge: bytes, private_key: bytes
    ) -> PairingComplete:
        """POST /api/fleet/v1/pairing-requests/:id/complete.

        Proves possession of the pairing request's own public key by
        signing *challenge* (`crypto.pairing_challenge_preimage(pairing_id)`)
        with *private_key*. Persists nothing itself -- returns only the
        opaque device session id and catalogue authGD hands back; the
        caller decides whether/how to persist them
        (`wingman.fleetsharing.state`).
        """
        pairing_id = _validate_pairing_id(pairing_id)
        signature = crypto.sign_request(private_key, challenge)
        body = json.dumps(
            {"protocol": crypto.PROTOCOL_VERSION, "completion_signature": signature}
        ).encode("utf-8")
        path = f"{PAIRING_REQUESTS_PATH}/{quote(pairing_id, safe='')}/complete"
        data = self._send(path, "POST", body, headers=None)
        return PairingComplete(
            session_id=_require_str(data, "session_id"),
            catalogue=_parse_catalogue(data.get("catalogue")),
        )

    # -- signed device requests --

    def fetch_catalogue(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> FleetCatalogue:
        """GET /api/fleet/v1/catalogue, signed with all five headers."""
        data = self._send_signed(
            CATALOGUE_PATH, "GET", b"", session_id, private_key, revision, now
        )
        return _parse_catalogue(data)

    def publish_snapshot(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        rows: tuple[PublishRow, ...],
        now: datetime | None = None,
    ) -> None:
        """PUT /api/fleet/v1/snapshot, signed with all five headers.

        Sends *rows* as an atomic, complete replacement of this device's
        projection, matching the design's "Publication" rule -- an empty
        *rows* is a normal withdrawal, not a special case.

        Validated against authGD's own wire limits
        (`projection.validate_publish_batch`) before any network call: at
        most 32 rows, unique `character_id`s, `0 <= dps <= 10_000_000`, and
        `ewar` exactly `()` or `("SCRAM/POINT",)`. This is defence in
        depth against a corrupted or hand-built batch, never a case
        `project_snapshot` itself produces for any single valid input --
        raises `ValueError` before this method ever touches the
        transport, exactly the same as the origin/pairing-id validation
        elsewhere in this class.
        """
        projection.validate_publish_batch(rows)
        body = json.dumps(
            {
                "protocol": crypto.PROTOCOL_VERSION,
                "rows": [
                    {
                        "character_id": row.character_id,
                        "dps": row.dps,
                        "ewar": list(row.ewar),
                    }
                    for row in rows
                ],
            }
        ).encode("utf-8")
        self._send_signed(
            SNAPSHOT_PATH, "PUT", body, session_id, private_key, revision, now
        )

    def renew_session(
        self,
        *,
        session_id: str,
        private_key: bytes,
        revision: int,
        now: datetime | None = None,
    ) -> str:
        """PUT /api/fleet/v1/session, signed with all five headers.

        Extends this device's OWN currently-valid session in place -- no
        new browser approval, and no new session id either: authGD's own
        `renewFleetDeviceSession` never rotates, because
        `fleet_publisher_lease`/`fleet_telemetry_row` both cascade on
        `fleet_device_session`, and rotating would cascade-delete this
        device's own live telemetry the instant it renews. Carries an
        EMPTY signed body, the same convention `fetch_catalogue` uses.

        Consumes a revision from the SAME shared sequence every other
        signed request for this session uses (`docs/fleet-protocol.md`,
        authGD repo) -- never a sequence of its own. Returns the new
        `expires_at` (RFC3339 UTC) authGD reports back; this client does
        not interpret it any further than requiring it be present and a
        string -- deciding WHEN to renew again is
        `wingman.fleetsharing.worker.FleetSharingWorker`'s job, on its own
        fixed cadence, not something this stateless transport tracks.
        """
        data = self._send_signed(
            SESSION_PATH, "PUT", b"", session_id, private_key, revision, now
        )
        return _require_str(data, "expires_at")

    # -- shared transport --

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
        now = now if now is not None else datetime.now(UTC)
        issued_at = _issued_at(now)
        body_sha256 = sha256(body).hexdigest()
        canonical = crypto.canonical_fleet_request(
            protocol=crypto.PROTOCOL_VERSION,
            method=method,
            path=path,
            session_id=session_id,
            issued_at=issued_at,
            revision=revision,
            body_sha256=body_sha256,
        )
        signature = crypto.sign_request(private_key, canonical)
        headers = {
            "X-Fleet-Session": session_id,
            "X-Fleet-Issued-At": issued_at,
            "X-Fleet-Revision": str(revision),
            "X-Fleet-Body-SHA256": body_sha256,
            "X-Fleet-Signature": signature,
        }
        return self._send(path, method, body, headers=headers)

    def _send(
        self, path: str, method: str, body: bytes, *, headers: dict | None
    ) -> dict:
        url = self._origin + path
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url, data=(body or None), headers=request_headers, method=method
        )
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                status = getattr(response, "status", 200)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            classification = _classify_status(exc.code)
            raise FleetRelayError(
                exc.code,
                classification,
                f"Fleet relay returned status {exc.code} ({classification}).",
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            # No response at all -- nothing here retries: a signed publish
            # carries a strictly increasing revision, and retrying a
            # request whose delivery is unknown risks a duplicate write.
            raise FleetRelayError(
                None, "transport_error", "Fleet relay could not be reached."
            ) from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise FleetRelayError(
                status, "malformed_response", "Fleet relay response was too large."
            )
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FleetRelayError(
                status, "malformed_response", "Fleet relay response was not valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise FleetRelayError(
                status,
                "malformed_response",
                "Fleet relay response had an unexpected shape.",
            )
        protocol = parsed.get("protocol")
        if isinstance(protocol, bool) or protocol != crypto.PROTOCOL_VERSION:
            raise FleetRelayError(
                status,
                "protocol_mismatch",
                "Fleet relay response used an unsupported protocol.",
            )
        return parsed
