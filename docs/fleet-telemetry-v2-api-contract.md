# Common v2 vocabulary — reviewed contract

This annex is the single cross-lane framing dictionary, not a new API or signing
scheme. Detailed DTOs remain in fleet-telemetry-v2-contract.md and
fleet-telemetry-v2-automatic-contract.md; the sole disk schema is fleet-telemetry-v2-cutover-contract.md
§4. Earlier resolution reports record their author's pass, not competing authority.
**Status: contract reviewed; implementation/lane/platform/deployment gates remain.**

## Versions, identity and framing

- `API_VERSION=2`, literal `/api/fleet/v2/` routes and JSON `protocol:2`.
  `SIGNING_SCHEME_VERSION=1`, canonical prefix `fleet-v1`, unchanged existing
  Ed25519 primitive/proof/key-encryption domains. `STATE_VERSION=4` is independent.
- Signed headers are exactly X-Fleet-Session, X-Fleet-Issued-At, X-Fleet-Revision,
  X-Fleet-Body-Sha256, X-Fleet-Signature. Sign the exact method/path/body bytes;
  persist the attempted revision before HTTP. Signed revision is int4, not consent
  revision. GET is empty, has no query or Transfer-Encoding, Content-Length absent
  or decimal zero. One serialized lane and existing pacing survive all retries.
- Signed success: exactly one `X-Fleet-Request-Binding` = lowercase hex SHA256 of
  UTF8("fleet-api-v2\n") followed by canonical request bytes, no appended newline.
  No new attempt header on signed calls. Pairing/recovery POSTs instead use fresh
  per-HTTP `X-Fleet-Attempt` and the distinct pre-session hash in automatic annex §6;
  immutable pairing/recovery proofs remain unchanged. No pre-session clock anchor.
- Correlation is trusted-TLS response binding, NOT a service/server signature.
  Browser Off is an existing authenticated account Server Action, neither of the
  desktop schemes. Never import its response as a desktop signed receipt.
- Every envelope is closed (required explicit nulls; no extra/duplicate keys,
  NaN, bool-as-integer). All replies/errors no-store. Wrong version/correlation,
  redirects/HTML or malformed payload never settle work or provide a clock anchor.
  Only the combat annex's device/snapshot DB-time fields can establish anchors.
- New automatic command/reservation/publication IDs use lowercase UUIDv4 U.
  Existing source/device/link/account/pre-session UUIDs retain ExistingUuid (v1–8
  plus nil/max, original spelling retained, case-insensitive identity comparison).
  New automatic sources happen to be U; manual source IDs need not be U.
  Token is canonical base64url32 bytes, 43 chars. T is valid round-tripping UTC
  YYYY-MM-DDTHH:mm:ss.sssZ. Every date addition must remain representable; unsupported
  DB time is service_unavailable, never wrapped/clamped dates or minted authority.
- N=0..2147483647, N+=1..2147483647; source mutation expected_generation max2147483646.
  G=0..9007199254740991 (safe consent/candidate/claim counters), ID=1..Gmax.
  All arithmetic checked; no counter reset/reuse. On reserves its later terminal
  revision (expected revision <=Gmax-2, generation <Gmax). See automatic §1/5.
- Capabilities are exactly [], [shared-source-v1], or [shared-source-v1,combat-v2].
  No inferred approval. D/C/K remain separate. V2 identity display names use the
  frozen profile's category table and existing 200-scalar rule, not host Unicode.

## Operation-specific byte ceilings (decoded UTF-8 entity bytes)

| Operation | Request | Success response |
| --- | ---: | ---: |
| snapshot PUT | 524288 | 1048576 (v2 response reader; actual DTO tiny) |
| snapshot GET | 0 | 67108864, canonical compact UTF-8 JSON.stringify |
| automatic GET/PUT and receipt GET | 0 / 2048 / 0 | 16384 |
| sources GET/PUT | 0 / 2048 | 1048576 |
| four pre-session POSTs | 2048 | 65536 |
| other signed device/catalogue/session/participation/eligibility | existing per-route raw limits | 1048576 |
| all error envelopes | — | 65536 |

This operation-specific table is authoritative for v2 response bounds. Current W
uses a 64KiB response reader for every operation except snapshot GET; the
non-snapshot increases here are intentional v2 client/server changes, not current
behavior.

Automatic PUT's 2048 does not override combat PUT's 512KiB. Snapshot GET's 64MiB
never becomes a generic control limit. Bound raw input before parse and output
before commit/issuance; no partial catalogue/source/snapshot success. Apply limits
to the decoded entity, not only compressed bytes. Shared signed client JSON keeps
its actual escaping/spaces; immutable command values never change across attempts.

## One error dictionary, operation-specific subsets

`Error={protocol:2,error:code}`. HTTP400: bad_headers, bad_request, update_required,
invalid_intent, invalid_key (pairing begin only); 401 unauthorized; 403 forbidden,
capability_required, fleet_read_required (manual Start only), not_verified
(existing relay admission only); 404 receipt_not_found (automatic receipt),
not_found (pre-session ID); 405 method_not_allowed (+exact Allow); 409 conflict,
request_id_conflict, revision_replayed, not_completable (pairing complete only);
429 rate_limited, receipt_capacity (new automatic On only); 503 feature_disabled,
service_unavailable. No arbitrary provider strings or permission diagnosis inferred
from generic errors. Route subsets in automatic §1/6 are closed; browser errors
are its own closed action union. Off never returns receipt_capacity. Existing
common FleetCode keeps not_verified while adding these literals, not a string type.

V1 rejection wins before method/auth/body/service admission: HTTP400
{protocol:2,error:"update_required"}, no read or mutation (HTTP HEAD has no entity
by HTTP semantics). V2 method refusal is 405. Explicit unsupported integer JSON
version is update_required; missing/noninteger version is bad_request. Unsupported
routes/old-success/malformed errors preserve journals; no v1 probe/fallback.
