# Character Fittings Management Design

**Status:** Approved in conversation; pending written-spec review

**Date:** 2026-09-03

## Summary

Add a separate **Fittings** destination that consolidates Personal Fittings from a user's authorized EVE characters into a persistent local library. Equivalent loadouts appear once even when characters use different names or numbered slot ordering. The user curates preferred metadata and collections, then explicitly copies selected fittings to selected characters.

The first release is intentionally additive. It never deletes or replaces a fitting on a character, never runs background synchronization, and never retries an ambiguous create request.

Alliance fittings enter through an explicit in-game step: the user copies them into one character's Personal Fittings, refreshes that character in Wingman, and files the imported entries into an `Alliance` collection. The official ESI API has no corporation or alliance fitting endpoint and cannot preserve that provenance.

## Goals

- Consolidate Personal Fittings across tracked characters.
- Deduplicate functionally equivalent loadouts while retaining source aliases.
- Preserve a curated fitting after it disappears from every character.
- Organize fittings in user-created, many-to-many collections.
- Copy selected fittings additively to selected characters.
- Keep existing Skills-only authorization working until a user explicitly enables Fittings for a character.
- Make partial failures, stale data, throttling, and ambiguous writes explicit.
- Establish app-wide ownership of EVE character identity and authorization for reuse by Skills and Fittings.

## Non-goals

The first release will not:

- Read corporation or alliance fittings directly; ESI exposes no such route.
- Import or export EFT text.
- Automatically synchronize, replace, or delete character fittings.
- Keep collections continuously deployed.
- Infer that every fitting on a designated character came from an alliance.
- Edit modules in a fitting inside Wingman.
- Retry a mutating ESI request whose outcome is unknown.
- Add a Fittings-only character flow; characters continue to enter Wingman through the existing Skills authorization flow and can then opt into Fittings.

## Product placement

Fittings is a destination, not a Settings section. Consolidating, curating, comparing, and distributing fittings is fleet-preparation work that a user visits to perform, like Skills.

It is a fourth title-bar destination and remains subject to the measured chrome constraints in `DESIGN.md`. Before the route is considered complete, the title bar must be measured at the 840 CSS-pixel floor at supported display scaling. If it does not fit, destination navigation must be redesigned; the drag region and window controls must not be clipped or silently compressed.

Fittings is controlled by the existing EVE-tools gate. Disabling EVE tools must remove every route into it and repair both the current and remembered destination.

## External ESI contract

The design was checked against ESI's OpenAPI document at `/meta/openapi.json` using Wingman's compatibility date `2026-08-12`.

- `GET /characters/{character_id}/fittings` requires `esi-fittings.read_fittings.v1`.
- `POST /characters/{character_id}/fittings` requires `esi-fittings.write_fittings.v1`.
- `DELETE /characters/{character_id}/fittings/{fitting_id}` exists but is not used in the first release.
- Create names are 1–50 characters.
- Create descriptions are at most 500 characters.
- A create payload contains 1–512 item rows.
- The read endpoint advertises a five-minute server and client cache.
- The fitting rate-limit group advertises 150 tokens per 15 minutes, bucketed by application and character. Current ESI policy charges by response class: two tokens for 2xx, one for 3xx, five for 4xx other than 429, and zero for 5xx. Wingman reads the remaining, used, and retry headers dynamically.
- One copy operation is still limited to 20 creates as a conservative UX and worst-case-rejection bound, not because every request costs five tokens or because all characters share one fitting bucket.
- The schema does not publish a per-character fitting-capacity limit. ESI remains authoritative for capacity failures.

These facts must be represented by named constants and contract tests rather than retyped independently into logic and UI copy.

## Architecture

### Shared EVE character authority

Introduce `wingman/eveauth/` as the sole owner of:

- character ID, name, and owner hash;
- granted scopes and capability status;
- the DPAPI-protected refresh token;
- in-memory access tokens and expiry;
- per-character token-refresh gates;
- the fixed-port, globally single-flight browser authorization flow;
- exact-character checks during capability upgrades;
- ownership-change handling; and
- global character removal.

`eveskills` and `evefittings` become consumers. They request an access token for a named capability and do not read, refresh, rotate, or delete credentials themselves.

A tracked character is an app-wide identity with one OAuth grant. **Forget character** means remove that character from Wingman, not disable one feature. It removes the credential first, then asks Skills and Fittings to remove character-specific derived state. Persistent library entries learned from the character survive; only that character's presence records are removed.

### Capability scopes

Capabilities declare their required scopes:

- Skills: `esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`.
- Fittings: `esi-fittings.read_fittings.v1` and `esi-fittings.write_fittings.v1`.

Existing grants remain valid for the capabilities their scopes satisfy. Missing fitting scopes must not set a grant-wide reauthorization flag or delete a token that remains valid for Skills.

**Enable fittings** reauthorizes the selected character for the union of Wingman's scopes required by its enabled capabilities. The callback must identify the exact character whose row initiated the upgrade. Selecting another EVE character is refused and reported; it must not silently add or upgrade that character.

Capability state comes from validated token claims, not from interpreting one ESI endpoint response as an OAuth verdict. Missing fitting scopes disable only Fittings. An ESI 401 or 403 never deletes the shared refresh token by itself; a 403 received despite the required claim is a capability or operation error. Only definitive SSO outcomes such as `invalid_grant`, a validated identity mismatch, or an owner-hash change invalidate the grant globally and remove character-specific snapshots.

A fitting-upgrade save failure leaves the previous Skills-capable authority intact and does not mark Fittings enabled. If SSO rotates a refresh token and the new token cannot be persisted, the new token remains live in memory with a persistent-risk warning; Wingman must not roll back to a token known to have rotated away. Global-forget cleanup begins only after removal from shared authority has been persisted successfully.

### Per-character lifecycle coordination

Shared authority owns a per-character re-entrant lifecycle gate and generation number. Fitting refresh, final copy preflight, intent persistence, the one-attempt POST, outcome persistence, and global forget coordinate through that gate. A copy batch acquires it separately for each pair and rechecks character existence, capability, snapshot freshness, conflicts, and unresolved intents before sending, so forgetting a character between pairs prevents every later write.

A fitting refresh holds the gate from its final authority check through remote GET and atomic snapshot commit. It cannot race a fitting POST, forget, or another fitting refresh. Pending and unknown write intents are an overlay on authoritative presence, not fields replaced wholesale by refresh; only a post-cache-horizon authoritative response may reconcile them.

Global forget waits for an active fitting request to leave the gate. A surviving `in_flight` intent is first converted to Unknown. Any unresolved `in_flight` or Unknown intent then refuses forget with an instruction to reconcile the character; Wingman must not discard the evidence or remove the credential needed to resolve it. Once no unresolved intent exists, forget persists authority removal while holding the gate, increments the lifecycle generation, and only then prunes Skills and fitting presence.

The browser authorization wait does not hold the lifecycle gate. A capability upgrade captures the expected character ID and lifecycle generation before opening EVE SSO, then reacquires the gate and rechecks both before committing. Forget invalidates that generation, so a late callback cannot resurrect or upgrade a forgotten character. Existing Skills GET commits retain their current membership recheck; shared token refresh and rotation also use the lifecycle gate re-entrantly so they cannot race authority removal.

### Component boundaries

- `eveauth`: shared identity, authorization, tokens, capabilities, and global forget.
- `evefittings.model`: validation, deployment templates, normalization, fingerprints, aliases, collections, and supersession rules.
- `evefittings.store`: bounded state, atomic writes, backup recovery, and schema normalization.
- `evefittings.names`: rebuildable type-ID-to-name enrichment cache.
- `evefittings.controller`: refresh, import, curation, preflight, serialized copy operations, cancellation, and progress.
- `ui/api.py`: thin bridge methods and semantic events.
- `web/fittings.js`: page-owned rendering, selection, overlays, and route lifecycle.

Every non-method `Api` attribute remains underscore-prefixed. The new Python packages must be added to the explicit setuptools package list.

## Persistence and migration

### Documents

Use three independently bounded, atomically replaced durable documents, each with a sibling backup and corruption preservation:

1. Shared character identities, scopes, and credentials.
2. Skills snapshots, groups, plan selection, and Skills-specific ETags/errors.
3. Fitting library, collections, supersession, per-character fitting snapshots, and fitting-specific ETags/errors.

Type-name enrichment is rebuildable cache data and is stored separately with strict bounds; losing it must not lose or block fitting data.

Each durable document has one writer. All read-modify-write operations and their save occur under that writer's re-entrant lock. Controllers coordinate through explicit events or service calls rather than editing one another's state.

Bounds are refusal boundaries, never silent eviction boundaries. A remote snapshot exceeding fitting, item, alias, or file limits is non-authoritative and leaves prior presence unchanged. Collection and metadata mutations beyond local limits are refused without changing state. Curated fittings, collections, and presence are never pruned to make room. Alias retention is deterministic and never removes preferred metadata or the only deployment provenance. Operation records and result history have named count and age caps; completed history may be pruned oldest-first, but unresolved write intents may not. Exact constants are fixed from representative fixtures before implementation, and page/result payload limits are named constants rather than UI literals.

### Migration from the current Skills document

The current `eve_skills.json` combines character credentials and Skills data. Migration must be resumable and prioritize never losing or resurrecting a credential:

1. Read the legacy document through a migration-specific loader that returns both normalized state and a structured disposition: genuinely absent, authoritatively loaded, recovered from backup, or failed.
2. Treat access errors, unrecoverable corruption, an unreadable primary and backup, and any current-loader warning that means the returned empty roster is only a fallback as **failed**, not as an empty authoritative state.
3. Only a genuinely absent, authoritatively loaded, or successfully recovered source may proceed. On failure, preserve the legacy files, write neither shared authority nor a completion marker, disable EVE identity features with an actionable recovery error, and retry migration on a later launch.
4. Atomically write the new shared character-authority document first.
5. Rewrite Skills state without credentials and record that authority migration completed.
6. If interrupted between writes, restart from the valid shared authority and finish stripping legacy credential fields.
7. Once shared authority exists—or a migration-complete marker exists—never recreate credentials from legacy Skills fields.
8. If the shared authority document is corrupt, preserve it and surface recovery failure; do not fall back to stale legacy credentials.
9. Reconcile feature-specific character rows against the shared roster on every startup.

Global forget removes the shared credential before pruning Skills snapshots and fitting presence. A crash can therefore leave harmless orphan metadata but never a usable orphan credential. Startup reconciliation completes the pruning.

## Fitting library model

### Stable identity

Each fitting has a stable, locally generated ID. A content fingerprint is a versioned derived lookup key, not the persistent record ID. This lets digest formats evolve without losing preferred metadata, collections, or supersession history.

A fingerprint-version migration that changes only serialization recomputes the index while preserving IDs. A canonicalization-rule change can merge or split entries and therefore requires an explicit, separately tested state migration; it may not silently recanonicalize the catalog at load time.

A matching digest is not sufficient on its own: Wingman compares complete canonical content before merging entries.

### Canonical content

Identity includes:

- ship type ID;
- item type ID;
- normalized rack or exact non-rack location; and
- quantity.

Numbered slots normalize to rack classes:

- `HiSlot0…7` → high;
- `MedSlot0…7` → medium;
- `LoSlot0…7` → low;
- rig, subsystem, and service slots normalize to their respective rack classes.

Cargo, DroneBay, and FighterBay remain distinct and quantity-sensitive. Charges and scripts remain content and therefore distinguish loadouts. Duplicate canonical rows are aggregated before deterministic sorting and hashing.

Validation rules differ by trust boundary. An authoritative ESI snapshot is all-or-nothing: an invalid fitting or item makes the complete refresh non-authoritative, retains prior presence, and reports malformed remote data. Tolerant per-entry dropping applies only while recovering a locally stored corrupt document, where losing one bad record is safer than losing every valid one.

A flag outside the pinned compatibility-date schema makes an ESI snapshot malformed and non-authoritative. The schema-defined `Invalid` flag is retained as distinct canonical content rather than silently dropped, but the resulting library entry is visibly non-deployable because ESI would discard that row during create and fail to reproduce the stored content.

### Deployment template

Canonicalization deliberately discards numbered slot order, while ESI creation requires exact numbered flags. Every library entry retains a mandatory `source_template` with its observed exact flags. A deployable entry additionally retains an optional, validated `deployment_template`.

The first accepted source layout becomes the source template and, when every row is accepted by the create schema and reproduces canonical content, the deployment template. Later equivalent layouts remain provenance but do not silently change deployment behavior. Both templates remain after all remote sources disappear. Entries containing schema-defined `Invalid` retain their source template but have no deployment template, remain readable and curatable, and classify as Unavailable for copy. Module editing and template switching are outside the first release.

### Curated metadata

A fitting entry stores:

- stable local ID;
- canonical ship and item IDs;
- fingerprint version and digest;
- mandatory exact source template;
- optional validated deployment template;
- editable preferred name and description;
- bounded source aliases, including source descriptions;
- collection IDs;
- optional `superseded_by` ID;
- created and updated timestamps.

The first observed alias initializes preferred metadata. Users may edit it thereafter. Preferred metadata is constrained to ESI's create limits so the library never promises a value it cannot deploy.

Source aliases are metadata, not identity. Equivalent fits with different names or descriptions merge into one entry while retaining those aliases for inspection.

### Collections and supersession

Collections have stable IDs and editable names. A fitting may belong to multiple collections. `Unfiled` is a derived view meaning an entry belongs to no collections; it is not a reserved mutable collection.

A supersession edge identifies the newer library entry. It is allowed only between entries for the same ship type and may not form a cycle. Supersession changes filtering and presentation only. It never deletes, replaces, or recopies a character fitting.

A library entry cannot be permanently deleted while any character still has it. Once no presence remains, deletion is explicit. If the same content later appears remotely, it is imported as a new entry; the first release does not persist suppression tombstones.

## Character fitting snapshots

For each fittings-enabled character, retain the last authoritative snapshot:

- remote fitting ID;
- local library ID;
- source name and description;
- exact source template;
- per-presence `first_seen_utc` and bounded `discovered_batch_id`;
- last-confirmed time;
- ETag;
- refresh error and stale status; and
- locally known, awaiting-remote-confirmation creates.

Remote fitting IDs identify presence on one character, not library identity. A delete-and-recreate may produce a new ID for the same canonical content.

Only a complete, schema-valid successful GET may add or remove authoritative presence. Snapshot validation is all-or-nothing; Wingman never drops one malformed remote fitting and then treats the truncated remainder as authoritative. A valid `304 Not Modified` confirms retained snapshot data and advances freshness without replacing it, except that it cannot resolve a pending or unknown create until a request made after the prior five-minute cache horizon returns authoritative content. A failed, malformed, unauthorized, oversized, or interrupted fetch retains the previous snapshot and marks it stale.

A newly observed character/content pair receives the refresh's batch ID and first-seen time even when its content merges into an older library entry. Presence that survives later refreshes retains those values. Authoritative removal or global forget removes the presence and its discovery metadata; a later reappearance is a new discovery. This makes recent/source filtering independent of entry creation and curation timestamps.

A character transfer or global forget removes that character's snapshot and presence links while retaining independent library content.

## Import and curation flow

Opening Fittings reads local state only. It does not poll ESI or push fitting state at application startup.

The character roster shows:

- Fittings enabled;
- Skills only / Enable fittings;
- reauthorization required;
- refreshing;
- last refreshed or stale; and
- a bounded actionable error.

Refresh may target one character or every enabled character. Character refreshes are sequential and single-flight. For each complete snapshot, Wingman:

1. validates and bounds the ESI payload;
2. canonicalizes each fitting;
3. matches complete canonical content against the fingerprint index;
4. attaches exact matches as character presence and retains aliases;
5. creates persistent entries for unmatched content;
6. removes prior presence no longer returned; and
7. commits the whole character snapshot atomically.

New entries appear automatically in `Unfiled`. Every refresh has a bounded unique batch ID, and each newly observed character/content presence stores that ID and `first_seen_utc`. The UI's recent-import and source-character filters query those presence facts, so an equivalent fitting merged into an older entry still appears in the batch that discovered it.

### Alliance ingestion

The supported workflow is:

1. In EVE, copy alliance fittings into one character's Personal Fittings.
2. Refresh that character in Wingman.
3. Filter by recent import and source character.
4. Select the entries and add them to an `Alliance` collection.
5. Edit preferred names and descriptions as needed.

Wingman does not designate the source character as an alliance collector or automatically classify all of its fittings.

### Type-name enrichment

Type IDs are authoritative. A separate bounded ESI-backed cache resolves display names in batches. Imports and fingerprints succeed even when enrichment fails. Until resolved, the UI displays a bounded fallback such as `Type 12345` and retries enrichment independently.

Names never participate in identity and are rendered as untrusted text.

## Copy and synchronization flow

“Sync” in the first release means an explicit additive copy operation. It does not mean continuous convergence.

### Selection and preflight

The user selects library fittings, chooses target characters, and asks Wingman to preflight. A target must have both fitting scopes and a sufficiently fresh authoritative snapshot. Execution revalidates because the game may change between preview and confirmation.

Each fitting/character pair is classified as:

- **Already present:** equivalent canonical content exists; skip regardless of name.
- **Name conflict:** the preferred name matches different content after NFC normalization and Unicode `casefold`; require an alternate name or skip that target.
- **Ready:** content is absent and the name is available.
- **Unavailable:** missing capability, stale inventory that cannot be refreshed, invalid deployment template, unresolved prior write intent, or known capacity problem.

An alternate name is validated against ESI's 50-character limit and against that target's current names. No “replace” option is offered.

The summary states selected pairs, creates, skips, conflicts, unavailable pairs, and the exact number of remote writes. Confirmation states that real write count before anything is sent.

One operation is limited to 20 creates. A larger selection is refused with instructions to split it into additional explicit batches; work is not queued invisibly.

### Execution

- Only one fitting-copy operation runs at a time.
- Targets and fittings are processed sequentially.
- Each create uses the stored exact-slot template and chosen name/description.
- Before every POST, Wingman persists a bounded operation record and per-pair `in_flight` intent. If that intent cannot be saved, nothing is sent.
- The mutation transport performs exactly one network attempt and reports separately whether an HTTP response was received. It never folds a no-response failure into an ordinary synthetic status.
- Only a schema-valid `201` response with a fitting ID is definite success.
- A validated, deterministic 4xx rejection is Failed, except authorization and throttle statuses, which keep their specific meanings.
- Timeout, no response, `408`, or `5xx` is Unknown unless ESI documents that the response guarantees non-creation.
- Success transitions the intent to locally known presence awaiting ESI confirmation. A deterministic rejection records Failed. Unknown remains unresolved.
- An ordinary rejection is recorded per pair and processing continues.
- A legacy-global `420` stops the remaining operation. A fitting-bucket `429` also stops the whole batch as a deliberately conservative product policy, even though fitting buckets are per application and character.
- Cancellation takes effect before the next request. Completed writes remain completed.
- Shutdown requests cancellation and waits only for a bounded in-flight request; the final result must not claim unattempted work completed.

Every surviving `in_flight` intent is treated as Unknown on startup. Unknown target/content pairs are unavailable for preflight and cannot be retried until an authoritative refresh after the prior cache horizon reconciles them. A `304` against a representation that may predate the attempt does not resolve uncertainty.

After each response, Wingman persists the outcome before advancing. If saving a known success fails, the batch stops and leaves the already-persisted intent unresolved, because the remote fitting exists but local state cannot safely prove it after restart.

No successful write is rolled back because another pair failed. The result groups Success, Already present, Conflict/Skipped, Failed, Unknown, Unattempted due to throttle, and Cancelled.

## Fittings workspace

The route uses a two-pane layout at the 840px floor.

### Collection rail

The left rail contains:

- All fittings;
- Unfiled;
- Superseded;
- user-created collections;
- collection counts; and
- quiet actions to create, rename, and delete collections.

Deleting a collection removes grouping only, never fittings.

### Library pane

The main pane contains:

- search;
- ship-type filter;
- current collection heading and count;
- refresh status;
- a `Characters…` management control;
- a paginated fitting list; and
- a bulk-action bar.

Rows show selection, preferred name, ship, collections, and character-presence count. Expanding one row shows rack-grouped modules, cargo, drones, fighters, preferred description, source aliases, character presence, stale or pending confirmation state, supersession, and editing/organization actions.

**Copy selected** is the route's one accent action. Target characters are selected in an app-owned overlay so the roster does not consume permanent width. The overlay identifies unavailable characters before preflight.

`Characters…` opens a focused roster overlay for enabling Fittings, refreshing snapshots, and globally forgetting characters. Page-initiated confirmations use Wingman's own overlay APIs, never browser dialogs.

### Paging and bridge payloads

The route must not send or rebuild the full library after every event.

- Initial state returns collection summaries, character summaries, current filters, and one bounded page.
- Library queries return bounded summary rows.
- Detail queries return one expanded fitting.
- Copy preflight receives selected stable fitting IDs and target character IDs.
- Progress pushes semantic operation counts and bounded per-pair outcomes.

Search, collection selection, sorting, and pagination are backend queries because the catalog may contain thousands of entries. Page-owned row selection crosses the bridge only when Python must compute preflight or perform a curation operation.

The route follows the standard enter/leave contract. All new push names must agree across literal Python pushes, `WM.HANDLERS`, and `WM.handle` registrations.

## Failure semantics

User-visible states distinguish:

- authorization required;
- refresh failed while showing stale last-known data;
- malformed remote fitting rejected;
- type-name enrichment unavailable;
- copy name conflict;
- create rejected by ESI;
- global throttling and stopped remainder;
- cancellation after a stated completed count;
- unknown create outcome requiring reconciliation; and
- local mutation applied but not persisted.

A failed refresh never clears valid snapshots, library entries, aliases, or presence. A failed local save must not be presented as durable. An unresolved write intent is durable safety state, not disposable result history, and blocks a repeat create until reconciliation. Errors are bounded, sanitized, token-redacted, and attached to the character or operation they affect.

Copy results carry an operation ID so logs and UI outcomes can be correlated without logging bearer tokens or full user-controlled descriptions.

## Security and privacy

- Refresh and access tokens remain DPAPI-protected at rest and redacted from logs.
- Authorization headers are never forwarded across redirects.
- Authenticated paths remain structurally validated against authority-changing input.
- OAuth upgrades bind to the expected character ID and owner hash.
- ESI, local-state, collection, alias, and description text is length- and count-bounded.
- Web rendering uses text properties, not HTML interpolation.
- Nothing is uploaded except explicit fitting creates requested in a confirmed batch.
- There is no telemetry.

## Testing

### Shared authority and migration

- Lossless migration of every current valid Skills-state shape.
- A genuinely absent legacy document may create empty authority, while access failure, unreadable primary and backup, or unrecoverable corruption writes no authority or completion marker.
- Interrupted migration after shared-authority write.
- Corrupt shared authority never resurrects legacy tokens.
- Existing Skills-only grants continue refreshing.
- Fitting scope absence affects only Fittings.
- Definitively revoked grants affect all capabilities.
- Row-specific upgrades reject a different returned character.
- Refresh-token rotation is serialized across consumers.
- A late capability callback cannot resurrect a forgotten or generation-changed character.
- Fitting refresh, create, and forget serialize through the per-character lifecycle gate.
- Copy rechecks authority and capability for every pair, including when forget occurs between pairs.
- Unresolved intents refuse forget and survive restart until reconciliation.
- A concurrent refresh preserves pending/unknown overlays and cannot resolve them before the cache horizon.
- Global forget removes authority first and startup reconciliation prunes orphans.

### Fitting domain and persistence

- Equivalent numbered-slot order produces the same canonical content.
- Different racks, cargo, drones, fighters, charges, scripts, or quantities remain distinct.
- A schema-unknown remote flag rejects the complete snapshot; schema-defined `Invalid` remains distinct and produces no deployment template.
- Duplicate canonical rows aggregate deterministically.
- Malformed IDs, booleans, quantities, flags, counts, and oversized payloads cannot produce valid-looking fits.
- Digest matches still require canonical-content equality.
- Stable local IDs survive fingerprint-version changes.
- Deployment templates retain exact valid flags.
- Collection rename uses IDs; many-to-many membership remains intact.
- Supersession is same-hull and acyclic.
- Atomic save, backup recovery, bounded read, tolerant per-entry normalization, and save-failure reporting.

### Refresh and copying

- Complete GET imports, merges, records per-presence discovery batch/time, and removes presence atomically.
- Equivalent content newly seen on another character remains discoverable by that refresh batch despite merging into an older entry.
- `304` confirms retained data.
- Failure or malformed data retains stale prior presence.
- Type-name failure does not block import.
- Preflight covers present, conflict, ready, and unavailable pairs.
- Execution revalidates stale preflight decisions.
- Operation and write-count bounds are enforced without silently truncating authoritative data.
- Intent is durably saved before send; save failure prevents the POST.
- The mutation transport makes exactly one attempt and preserves response-received versus no-response outcomes.
- Timeout, no response, `408`, and `5xx` are Unknown; only a valid `201` is definite success.
- A success-result save failure stops the batch and leaves a recoverable unresolved intent.
- Startup converts surviving `in_flight` intents to Unknown.
- Success, rejection, ambiguous transport failure, cancellation, throttling, and partial results are distinct.
- A `420` or `429` stops the remainder under the documented policies.
- Unknown outcomes require post-cache-horizon authoritative refresh before retry.

### Integration and UI contracts

- EVE route gating covers current and remembered destinations.
- Bridge allowlist agrees in both directions.
- API exposes no public non-method attributes.
- New Python packages are included in installed and frozen builds.
- `?dev=1` is the only source of fabricated page data.
- Lexical page-convention tests cover generated controls, hidden overrides, focus, and dialog rules.
- Screenshot inventory and smoke checklist include Fittings states.

## Manual verification

A Windows/WebView2 smoke pass must cover:

- fourth-destination chrome at the 840px floor at supported scaling;
- keyboard and focus behavior for the route and overlays;
- existing Skills-only character behavior after migration;
- exact-character fitting authorization and cancellation;
- import, duplicate consolidation, alias preservation, and slot-order equivalence;
- alliance ingestion through in-game Personal Fittings;
- collection curation and supersession;
- successful copy, already-present skip, name conflict, partial rejection, cancellation, and throttling;
- ambiguous create messaging and cache-delayed reconciliation;
- global forget while preserving library content; and
- restart after each meaningful persisted mutation.

`docs/smoke-checklist.md` is part of the feature change, not post-release paperwork.

## Delivery constraints

Implementation should proceed in vertical, testable slices:

1. Shared authority and migration while preserving existing Skills behavior.
2. Measure the four-destination title bar at the 840px floor before investing in the full route.
3. Fitting domain model, persistence, durable write intents, and representative sanitized ESI fixtures.
4. Read-only refresh, automatic import, deduplication, and type-name enrichment.
5. Fittings destination, paging, details, collections, and curation.
6. Scope upgrade, one-attempt mutation transport, preflight, bounded additive copy, and result reconciliation.
7. Packaging, dev fixtures, screenshots, documentation, and Windows smoke verification.

No slice may widen authorization or enable ESI writes before its capability-specific tests and user-visible consent path exist. Before release, Wingman's registered EVE application must also be configured to permit both fitting scopes; a source change alone cannot widen the scopes accepted by the registered application.
