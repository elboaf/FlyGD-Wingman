# Pre-jump prime handoff: Wingman writes to Wanderer via server-side consume

The Wanderer integration has been read-only by design (map polling for preview
metadata; AGENTS.md and `docs/wanderer-preview-overlay-plan.md` both state "no
map mutations"). Issue #281 adds the first write path: Set Root on a single
selected bookmark primes a bounded **pre-jump record** (system J-code + flags
`e`/`/`/`c`/`f` parsed by the AHK engine) that is pushed to a new narrow
staging endpoint on Wanderer and consumed atomically by the server when the
tracked character's location update creates a new connection.

## Decisions

- **Direction:** Wingman → Wanderer push; the server consumes inside
  `MapServer.CharactersImpl.update_location`. No inbound control surface into
  Wingman; no client-side apply logic.
- **Credential:** a separate, narrowly-scoped prime token (a second
  credential), stored DPAPI-protected alongside the existing `wmi_` token.
  Existing integration tokens remain read-only and are not broadened.
- **Settings UX:** an optional "Prime token" field on the existing Wanderer
  connection card; an empty field is the feature's off switch.
- **Capture:** only a single selected bookmark qualifies (no-selection and
  whole-list Set Root keep today's behavior and prime nothing). The AHK
  engine parses the flags (it already owns the vocabulary) and relays a
  bounded prime field via `eve_status.json`; Python joins it with telemetry
  (EVE character ID + current solar system ID, extending telemetry if
  needed) and POSTs. Python never reads the clipboard.
- **Contract semantics:** the prime binds to character (EVE character ID) +
  map + expected source system. One active prime per character+map,
  newest-wins replacement, 15-minute TTL, expires harmlessly. Consumed
  **only** when the movement creates a new connection; the destination
  system's name is set only when the system itself is new. Omitted flags
  leave fields at defaults. The `e` tag maps to the 4-hour `time_status`
  bucket.
- **Transport:** bounded HTTPS on the existing wanderer client/worker lane,
  3 attempts with short backoff, then silent give-up. Failures never disturb
  the clipboard or preview flows.
- **Delivery:** Wanderer changes target an upstream PR to `elboaf/wanderer`
  from a branch off `guarzo/zoo`.

## Consequences

- The documented read-only/no-map-writes boundary is deliberately reversed
  for this one narrow pipeline; all other Wanderer interactions remain
  read-only. Update AGENTS.md and the plan doc when the Wingman slice lands.
- The feature is inert unless the user supplies a prime token, and inert for
  any Set Root that is not a single-bookmark selection.
- An already-mapped destination never has its name or flags touched.
