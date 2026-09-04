# Central Character Authorization Design

**Status:** Approved in conversation; pending written-spec review

**Date:** 2026-09-04

## Summary

Move EVE character authorization into a canonical **Settings › Characters** section. Every authorization requests all EVE scopes Wingman currently supports, so a character signs in once for Skills and Fittings rather than once per feature.

The EVE SSO page decides which character is authorized. Wingman does not ask the user to select a local character row before opening a generic EVE login that cannot carry that choice. The validated character ID returned by EVE determines whether Wingman adds a new character or replaces an existing character's grant.

Skills and Fittings remain task-focused destinations. Both link to Settings for character management. Neither offers per-character authorization controls.

This change also repairs the Fittings route spacing visible in the released screen by sharing the complete two-pane workspace geometry with Skills, not only its child classes.

## Goals

- Give EVE authorization one visible and architectural home.
- Request Skills and Fittings scopes in one authorization round trip.
- Remove the false affordance that Wingman can direct EVE SSO to a selected local character.
- Show current authentication and capability state for every authority character.
- Preserve existing credential security, lifecycle coordination, and global forget semantics.
- Keep Skills and Fittings focused on plan readiness and fitting curation respectively.
- Repair the Fittings route's missing outer inset, fixed rail, pane gap, and primary-action alignment.

## Non-goals

- Direct EVE SSO to a specific character or account. The current authorization protocol supplies no such supported identity selection.
- Add per-capability disable controls. One OAuth grant carries a scope set; Wingman has no safe feature-specific token removal operation.
- Merge Profile account-character links, Preview character names, or local EVE settings identities into the OAuth authority roster.
- Change fitting refresh, skill refresh, fitting-copy, plan evaluation, or profile-copy semantics.
- Migrate or duplicate authority data into the settings document.
- Redesign unrelated Settings sections or the visual language of Skills and Fittings.

## Product placement

Authorization is configuration: users visit it to connect or repair EVE access, then leave. It belongs in Settings under the destination-versus-configuration rule in `PRODUCT.md` and `DESIGN.md`.

Skills remains a destination because users work there to compare characters against plans. Fittings remains a destination because users curate and distribute fittings there. Their feature-specific refresh controls remain on those destinations because refreshing remote data is part of each task, not authorization setup.

## Authorization model

### One full authorization action

Settings › Characters provides one **Authenticate character…** action. It starts generic EVE SSO authorization with the union of all scopes in `eveauth.application.CAPABILITY_SCOPES`. With the current product this is:

- `esi-skills.read_skills.v1`;
- `esi-skills.read_skillqueue.v1`;
- `esi-fittings.read_fittings.v1`; and
- `esi-fittings.write_fittings.v1`.

The scope union is derived from the capability declaration. It is not repeated as another hand-maintained constant.

Every new authorization and reauthorization uses this complete set. The UI does not offer a Skills-only or Fittings-only choice.

### Returned identity decides the row

Wingman opens a generic EVE SSO page without first selecting a local character. After the callback:

1. The access token is validated using the existing issuer, audience, signature, expiry, scope, subject, and owner checks.
2. If the returned character ID is unknown, Wingman adds it to shared authority.
3. If the returned character ID already exists, Wingman replaces that character's grant and clears its reauthentication state.
4. If an existing character's owner identity changed, Wingman keeps the current security behavior: the old grant and character-specific derived state are invalidated before the replacement is reconciled.
5. Authority persistence completes before feature controllers reconcile the resulting roster.

There is no wrong-character callback for this flow because Wingman made no row-specific promise before opening EVE. The exact-character capability-upgrade behavior in the previous Fittings design is retired along with the per-character upgrade action.

### Existing partial grants

Existing Skills-only grants remain valid for Skills. They are not revoked or migrated merely because new authorizations request the full scope set.

Settings shows their actual state, for example **Skills: Ready** and **Fittings: Sign in**. To upgrade one, the user chooses **Authenticate character…** and selects that character in EVE. The returned character ID matches and replaces the existing grant with the complete scope set.

This is the only upgrade path. There is no per-row **Enable fittings** action.

### Single-flight and cancellation

Authorization remains globally single-flight because it uses one fixed loopback listener. While it is active:

- Settings shows **Waiting for EVE sign-in…** and **Cancel** above the roster;
- every control that could start another authorization is disabled;
- no character row is marked pending because Wingman does not know which character the user will choose;
- cancellation stops the listener and prevents any later exchange result from committing; and
- timeout or refusal leaves authority state unchanged and produces a bounded actionable message.

Cancellation is checked after the callback wait and again immediately before commit. A token exchange already in progress may finish at the network layer, but its result is discarded after cancellation and cannot replace authority.

The browser wait remains outside character lifecycle gates. Authorization commit reacquires the returned character's gate and retains generation checks so a stale callback cannot resurrect forgotten authority.

### Persistence and token safety

`eveauth.AuthorityController` remains the sole runtime and persistent owner of:

- character identity;
- granted scopes;
- encrypted refresh tokens;
- in-memory access tokens;
- authentication timestamps;
- reauthentication state;
- persistence warnings;
- authorization single-flight state; and
- character lifecycle gates and generations.

The new Settings section is a projection of this state. It never writes tokens, owner hashes, or scopes into the settings document and never receives them across the bridge.

Existing guarantees remain:

- a failed authorization save leaves the prior durable grant in use;
- a rotated refresh token that cannot be persisted remains memory-only with a visible persistence warning;
- tokens remain DPAPI-protected at rest and redacted from logs;
- feature endpoint failures do not independently invalidate a grant; and
- only validated SSO outcomes and identity checks alter shared authority.

No authority-state or settings-schema migration is required.

## Shared character-management interface

### Authority payload

Add a shared, read-only character-management payload owned by the authority/API boundary rather than borrowing the Skills or Fittings workspace payload.

It contains only display-safe data:

- `available`;
- `auth_configured`;
- authorization activity (`idle` or `waiting`);
- a bounded, in-memory terminal authorization notice when the last attempt failed;
- bounded authority warnings;
- for each character: ID, display name, authenticated time, Skills capability status, Fittings capability status, reauthentication state, and bounded persistence error.

Starting a new attempt clears the prior terminal notice. A successful attempt also leaves no stale failure notice. Cancellation returns to idle without being presented as an error. Refusal, timeout, exchange failure, validation failure, and persistence failure set the bounded terminal notice and publish the same semantic authority-change event used for roster changes. This is runtime UI state, not persisted account state.

It does not contain refresh tokens, access tokens, owner hashes, raw JWT claims, or a second persisted copy of granted scopes.

Rows are sorted by case-insensitive character name with character ID as a stable tie-breaker. Counts and capability states are derived from the returned roster, not maintained separately.

### Mutations

The shared bridge exposes actions for:

- starting full authorization;
- cancelling the active authorization; and
- globally forgetting one character.

The synchronous authorization-start result reports only whether the worker and listener flow were accepted. It does not claim that a later grant was persisted. Terminal browser-flow outcomes arrive through the authority activity/notice state above.

Global forget preserves `{applied, persisted, error}` so Settings can distinguish refusal, partial cleanup, persistence failure, and success according to `DESIGN.md`.

The old page-facing targeted capability-upgrade method is removed after its callers are removed. Internal capability checks and declarations remain because Skills and Fittings still require them when obtaining access tokens.

### Semantic updates

A successful authority mutation publishes one semantic authority-change event. Settings responds by re-reading the shared character state. Skills and Fittings reconcile from authority through their controller interfaces rather than consuming a Settings payload.

The event does not push credentials, a whole character document, or screen-specific widgets. A Settings section entered after a completed off-screen change also performs a fresh read through the normal section-enter contract.

## Settings › Characters

### Navigation and layout

Add an EVE-gated **Characters** entry to the Settings rail. The section uses the established Settings surface and tokens, with a compact roster sized for the authority limit of 50 characters.

The header contains:

- **Characters**;
- the derived authority-roster count, including partial and reauthentication-required rows; and
- **Authenticate character…**.

Below it:

- an authorization progress or error area that collapses when empty;
- a character filter; and
- a dense roster with **Character**, **Skills**, and **Fittings** columns.

The roster scrolls within the available section height. It does not render each character as a multi-line card.

### Capability presentation

Capability cells use concise text plus existing semantic tokens:

- **Ready**: local authority has an encrypted or live refresh token, does not require reauthentication, and records every scope required by the capability;
- **Sign in**: the row requires reauthentication, has no usable stored token, or lacks one or more required scopes.

**Ready** means locally eligible. It is not proof that EVE has not revoked the refresh token since Wingman last used it; definitive revocation is discovered on the next token refresh and then changes the row to **Sign in**. A completely unavailable authority is a section-level error rather than a fabricated per-row state.

The row carries one bounded persistence or authority error when present. The screen does not duplicate feature snapshot freshness. Skills and Fittings remain responsible for showing whether their own remote data is current.

### Row actions

Each row ends with an overflow button. Its menu contains **Forget character…**.

The overflow does not contain authorization, capability toggles, feature refresh, or a generic details view. It is the quiet home for a rare destructive action and preserves the roster's scanning density.

Forget remains global. Confirmation states that Wingman removes the stored EVE authorization and character-specific Skills and Fittings snapshots, while consolidated fitting-library entries remain. Existing participant preflight is retained: unresolved fitting writes refuse forget with instructions to reconcile them first.

### Accessibility and behavior

- The filter has a programmatic label.
- Column headings identify capability state.
- Overflow buttons have row-specific accessible names.
- Menus are keyboard reachable, close on Escape and outside interaction, restore focus to their trigger, and never use browser-native dialogs.
- Empty, unavailable, and no-filter-results states name the next usable control.
- Authorization and mutation messages use mounted or correctly exposed live regions according to the existing page conventions.

## Skills changes

Remove authorization ownership from the Skills destination:

- remove **Add character**;
- remove row-level **Re-authenticate**;
- remove row-level **Forget character**;
- add **Manage characters…** in the rail, navigating to Settings › Characters; and
- update the empty state to point to **Manage characters…**.

Keep:

- Skills refresh;
- plan and group selection;
- character filtering;
- readiness, requirements, queue timing, and training estimates; and
- Skills-specific errors and snapshot freshness.

A character whose grant needs attention remains visible in Skills with its non-actionable status. The recovery instruction sends the user to Settings rather than opening SSO from the row.

## Fittings changes

Remove the Fittings **Characters…** overlay and all authorization and global-forget controls it owns.

The rail contains:

- the character count relevant to the fitting workspace;
- **Refresh characters** for Personal Fittings snapshots; and
- **Manage characters…**, navigating to Settings › Characters.

The empty state tells the user to authenticate in Settings, then return and refresh. Copy-target selection may explain that a character is unavailable, but it does not offer authorization controls.

Remove obsolete Fittings-specific page bridge calls for enabling a character, cancelling authorization, and forgetting a character after the shared Settings actions are wired and verified.

## Fittings spacing repair

The released Fittings route reuses Skills child classes without reusing the parent route geometry. That causes the rail to size from content, removes the 12px outer inset and pane gap, and places the main heading flush against the rail.

Extract or share the complete two-pane workspace geometry so both routes receive:

- a 214px rail;
- `minmax(0, 1fr)` main content;
- a 12px outer inset;
- a 12px pane gap; and
- correct minimum-height behavior at the 840x625 viewport floor.

Likewise, make primary-action alignment a shared workspace rule so **Copy selected** occupies the far edge of the Fittings heading as **Copy plan** does in Skills.

This is a focused geometry correction requested alongside the authorization redesign because both defects shipped in the same new Fittings surface. It is behaviorally independent and should land as its own implementation slice or commit. It does not authorize unrelated styling changes to either destination.

## Failure behavior

- Missing EVE application configuration disables authorization and states that the build is not configured.
- A concurrent authorization attempt is refused without starting another listener.
- Browser refusal, callback timeout, cancellation, token exchange failure, and token validation failure leave the prior authority document unchanged; a result that arrives after cancellation is discarded before commit.
- A failed new-grant persistence leaves the previous durable grant active and reports that the sign-in was not saved.
- A live rotated token that cannot be saved retains the existing in-memory persistence-risk warning.
- A forgotten or generation-changed character cannot be resurrected by a late callback.
- Participant cleanup failure after durable forget is reported as partial completion.
- Unresolved Fittings write intents continue to block forget.
- Authority load or migration warnings remain visible and actionable; the Settings section does not manufacture an empty healthy roster from an unavailable authority.

Errors are bounded, sanitized, and contain no token or raw claim material.

## Compatibility

Existing authority and feature documents remain valid. Existing Skills-only grants continue to serve Skills. Users upgrade them through one generic full authorization round trip per character when they want Fittings or need to reauthenticate.

The previous Fittings design's exact-row capability-upgrade requirement is superseded by this design. Its security goals remain, but the UI no longer promises a row-specific flow that EVE cannot present. The generic returned identity is accepted only after full validation and is reconciled by character ID.

The registered EVE application must permit every scope in the derived complete scope set. If deployment configuration does not permit those scopes, the release must not present full authorization as available.

## Testing

### Authority and API

- The full authorization scope set is derived from all declared capabilities.
- New-character authorization stores a full grant.
- Authorizing an existing character replaces its grant and clears reauthentication state.
- An existing Skills-only grant continues to serve Skills before upgrade and serves both capabilities after full authorization.
- Owner change, lifecycle generation change, cancellation, timeout, validation failure, persistence failure, and single-flight refusal preserve their documented behavior.
- Cancellation after callback receipt but before commit discards the exchange result.
- The shared payload contains display-safe fields and no credentials, owner hashes, or raw claims.
- Authorization activity and terminal failures update through bounded in-memory state without claiming synchronous completion.
- Global forget retains the three-way Settings result contract.
- Semantic authority changes refresh Settings and reconcile feature controllers.

### Web contracts

- Settings rail and section declarations remain one-to-one.
- Characters is hidden by the EVE-tools gate and obeys section enter/leave behavior.
- Skills and Fittings link to Settings › Characters.
- Removed per-character authorization actions and the Fittings Characters overlay do not remain as dead markup, handlers, or bridge methods.
- The roster filter, overflow menu, confirmation, focus restoration, Escape behavior, live regions, hidden overrides, and focus-visible treatment follow page conventions.
- The bridge allowlist, literal Python pushes, and page handlers agree.
- Dev fixtures are generated only in `dev.js` and represent full, partial, reauthentication, warning, empty, and authorization-in-progress states.

### Layout and manual verification

- Lexical tests pin shared two-pane geometry for Skills and Fittings and far-edge primary-action alignment.
- Screenshot tooling captures Settings › Characters and the repaired Fittings route.
- At the 840x625 floor, the Settings roster remains usable and the Fittings rail, gap, heading, filters, empty state, pager, and copy action remain visible without overflow.
- A Windows/WebView2 smoke pass covers keyboard and pointer navigation, filtering, the overflow menu, forget confirmation and refusal, authorization start/cancel/success/failure, new and existing returned characters, partial-grant upgrade, route handoff, and supported display scaling.

`docs/smoke-checklist.md` is updated as part of the change. Browser or lexical tests do not substitute for the Windows/WebView2 pass.

## Delivery boundaries

Implementation should proceed in testable slices:

1. Shared full-scope authorization and safe shared character-state API.
2. Settings › Characters route, roster, progress, overflow, and forget flow.
3. Skills and Fittings handoff to the canonical Settings section, followed by removal of obsolete controls and APIs.
4. Shared two-pane geometry and Fittings primary-action alignment repair.
5. Dev fixtures, screenshots, documentation, packaging checks, and Windows smoke coverage.

No slice duplicates authority into Settings state, weakens lifecycle checks, or changes fitting-copy behavior. Each behavior change begins with a failing test and ends with focused and full verification.