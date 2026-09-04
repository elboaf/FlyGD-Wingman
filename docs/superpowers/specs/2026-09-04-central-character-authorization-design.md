# Central Character Authorization Design

**Status:** Approved in conversation; pending written-spec review

**Date:** 2026-09-04

## Summary

Move EVE character authorization into a canonical **Settings › Characters** section. Every authorization requests the complete Skills-and-Fittings scope set, so a character signs in once for both current EVE capabilities rather than once per feature.

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

Settings › Characters provides one **Authenticate character…** action. It starts generic EVE SSO authorization for an explicit `FULL_AUTH_CAPABILITIES` tuple containing exactly `SKILLS` and `FITTINGS`. The requested scopes are derived by taking the union of those two capabilities' declarations:

- `esi-skills.read_skills.v1`;
- `esi-skills.read_skillqueue.v1`;
- `esi-fittings.read_fittings.v1`; and
- `esi-fittings.write_fittings.v1`.

The four scope strings are not retyped in authorization logic, but the two product capabilities included in full authorization are explicit. Adding an unrelated future capability to `CAPABILITY_SCOPES` must not silently widen EVE consent.

Every new authorization and reauthorization uses this complete Skills-and-Fittings set. The UI does not offer a Skills-only or Fittings-only choice.

### Returned identity decides the row

Wingman opens a generic EVE SSO page without first selecting a local character. After the callback:

1. The access token is validated using the existing issuer, audience, signature, expiry, scope, subject, and owner checks.
2. If the returned character ID is unknown, both required feature-cleanup slots must confirm that no orphan state blocks that ID before Wingman adds it to shared authority.
3. If the returned character ID already exists and both stored and returned owner hashes are present and equal, Wingman replaces that character's grant and clears its reauthentication state.
4. If the returned character ID exists and both owner hashes are present but differ, Wingman refuses the replacement and instructs the user to forget the existing character first. The previous authority and derived state remain unchanged.
5. If either owner hash is absent, Wingman preserves compatibility by matching the validated character ID. It retains the existing non-empty owner hash or establishes the returned non-empty hash; it never replaces a known hash with an empty one. This has weaker transfer detection than two known hashes and is an explicit compatibility tradeoff for migrated and defensively parsed grants.
6. Authority persistence completes before feature controllers reconcile the resulting roster.

There is no wrong-character callback for this flow because Wingman made no row-specific promise before opening EVE. The exact-character capability-upgrade behavior in the previous Fittings design is retired along with the per-character upgrade action. A proven owner replacement is deliberately not folded into generic reauthorization: it crosses a security boundary and uses the explicit global-forget cleanup path first.

### Existing partial grants

Existing Skills-only grants remain valid for Skills. They are not revoked or migrated merely because new authorizations request the full scope set.

Settings shows their recorded authorization state, for example **Skills: Authorized** and **Fittings: Sign in**. To upgrade one, the user chooses **Authenticate character…** and selects that character in EVE. The returned character ID matches and replaces the existing grant with the complete scope set.

This is the only upgrade path. There is no per-row **Enable fittings** action.

### Single-flight and cancellation

Authorization remains globally single-flight because it uses one fixed loopback listener. While it is active:

- Settings shows **Waiting for EVE sign-in…** and **Cancel** above the roster;
- every control that could start another authorization is disabled;
- no character row is marked pending because Wingman does not know which character the user will choose;
- cancellation stops the listener and prevents any later exchange result from committing; and
- timeout or refusal leaves authority state unchanged and produces a bounded actionable message.

Each authorization attempt has an immutable attempt ID and a cancellation generation guarded by the authority's authorization-state lock. Commit has one linearization point under that same lock, after token validation and after acquiring the returned character's lifecycle gate, immediately before authority persistence:

- if Cancel increments the cancellation generation first, that attempt cannot persist or reconcile, even if token exchange later returns;
- if commit passes the linearization point first, persistence completes and Cancel reports that the attempt already finished rather than claiming it was cancelled.

A token exchange already in progress may finish at the network layer, but its result is discarded when cancellation won the linearization race. Tests control the worker at exchange, validation, lifecycle-gate, and pre-save boundaries rather than relying on timing.

The browser wait and token exchange remain outside character lifecycle gates. Authorization commit reacquires the returned character's gate and retains character generation checks so a stale callback cannot resurrect forgotten authority.

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

Starting a new attempt clears the prior terminal notice and transitions activity to `waiting`. Completion transitions activity and notice together: success returns to `idle` with no stale notice; cancellation returns to `idle` without an error; refusal, timeout, exchange failure, validation failure, owner mismatch, blocked re-add, and persistence failure return to `idle` with a bounded terminal notice. Each transition publishes the same semantic authority-change event used for roster changes. This is runtime UI state, not persisted account state.

It does not contain refresh tokens, access tokens, owner hashes, raw JWT claims, or a second persisted copy of granted scopes.

Rows are sorted by case-insensitive character name with character ID as a stable tie-breaker. Counts and capability states are derived from the returned roster, not maintained separately.

### Mutations

The shared bridge exposes actions for:

- starting full authorization;
- cancelling the active authorization; and
- globally forgetting one character.

The synchronous authorization-start result reports only whether the worker and listener flow were accepted. It does not claim that a later grant was persisted. Terminal browser-flow outcomes arrive through the authority activity/notice state above.

Global forget preserves `{applied, persisted, error}` so Settings can distinguish refusal, partial cleanup, persistence failure, and success according to `DESIGN.md`. Participant cleanup hooks become result-bearing rather than swallowing their own persistence failures:

- `applied=False` means preflight refused removal and authority remains;
- `applied=True, persisted=True` means authority removal and every participant cleanup persisted;
- `applied=True, persisted=False` means authority removal persisted but at least one participant cleanup did not.

An incomplete cleanup blocks re-adding that character ID. The current process retains the blocked ID. On startup, result-bearing participant reconciliation rebuilds the block from orphan Skills or Fittings rows that could not be pruned from their durable documents.

Skills and Fittings are required cleanup-verification slots independent of whether their controllers constructed successfully. Normal controllers fill those slots with result-bearing reconciliation. A controller build failure, unreadable or unrecovered feature document, or missing slot implementation reports **unverified**, never clean. Before committing authorization for an otherwise unknown ID, authority retries or verifies orphan cleanup and accepts the character only after both required slots explicitly confirm that no prior-owner state remains for that ID. If either required slot is unavailable and cannot inspect its document, every unknown returned ID is blocked because Wingman cannot distinguish a new character from a previously forgotten one. Existing same-character reauthorization may proceed under the owner rules above because it does not cross from absent authority back into a potentially stale identity.

The persisted orphan rows are the durable evidence from which startup reconstructs exact blocked IDs when feature documents are readable. Unavailability is a separate fail-closed condition, so no credential, owner hash, or duplicate block list is copied into Settings.

The old page-facing targeted capability-upgrade methods and `AuthorityController.enable_capability` are removed after their callers are removed. The generic Skills-only authentication delegate is replaced by full authorization. Internal capability checks and declarations remain because Skills and Fittings still require them when obtaining access tokens.

### Semantic updates

Every observable authority transition publishes the same semantic authority-change event: authorization starts, terminal outcome becomes available, a grant commits, forget completes or partially completes, and token health changes. Activity, notice, and roster mutation are updated under authority locks before the event, so a re-read cannot observe a terminal notice paired with stale activity.

Settings responds by re-reading the shared character state. Skills and Fittings reconcile from authority through their controller interfaces rather than consuming a Settings payload. The event does not push credentials, a whole character document, or screen-specific widgets. A Settings section entered after a completed off-screen change also performs a fresh read through the normal section-enter contract.

## Settings › Characters

### Navigation and layout

Add an EVE-gated **Characters** entry to the Settings rail. The section uses the established Settings surface and tokens, with a compact roster sized for the authority limit of 50 characters.

The section's first surface is headed **EVE authorization**, avoiding a card heading that merely repeats the **Characters** rail entry. Its header contains:

- the derived authority-roster count, including partial and reauthentication-required rows; and
- **Authenticate character…**.

Below it:

- an authorization progress or error area that collapses when empty;
- a character filter; and
- a dense roster with **Character**, **Skills**, and **Fittings** columns.

The roster scrolls within the available section height. It does not render each character as a multi-line card.

### Capability presentation

Capability cells use concise text plus existing semantic tokens:

- **Authorized**: local authority records a refresh-token blob or live memory token, does not require reauthentication, and records every scope required by the capability;
- **Sign in**: the row requires reauthentication, has no recorded token, or lacks one or more required scopes.

**Authorized** describes Wingman's recorded grant, not proof that EVE has not revoked it or that DPAPI decryption has been exercised during this read. Definitive revocation is discovered on token refresh. A refresh-token decryption failure transitions the authority row to reauthentication-required, persists that transition when possible, emits the authority event, and changes both capability cells to **Sign in** instead of leaving a permanently unusable row marked **Authorized**. A completely unavailable authority is a section-level error rather than a fabricated per-row state.

The row carries one bounded persistence or authority error when present. The screen does not duplicate feature snapshot freshness. Skills and Fittings remain responsible for showing whether their own remote data is current.

### Row actions

Each row ends with an overflow button. Its menu contains **Forget character…**.

The overflow does not contain authorization, capability toggles, feature refresh, or a generic details view. It is the quiet home for a rare destructive action and preserves the roster's scanning density.

Forget remains global. Confirmation states that Wingman removes the stored EVE authorization and character-specific Skills and Fittings snapshots, while consolidated fitting-library entries remain. Existing participant preflight is retained: unresolved fitting writes refuse forget with instructions to reconcile them first.

### Accessibility and behavior

- The filter has a programmatic label.
- Column headings identify capability state.
- Overflow buttons have row-specific accessible names, `aria-haspopup="menu"`, and synchronized `aria-expanded`.
- The menu has an accessible label tied to its character, uses menu/menuitem semantics, supports Arrow Up, Arrow Down, Home, End, Enter, and Space, closes on Escape and outside interaction, and restores focus to its trigger.
- Forget confirmation uses Wingman's app-owned dialog and never a browser-native dialog.
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
- Participant cleanup failure after durable forget is reported as `applied=True, persisted=False`; the character ID remains blocked from re-add until result-bearing reconciliation confirms cleanup.
- An ownership mismatch is refused in place and directs the user through global forget before reauthorization.
- Unresolved Fittings write intents continue to block forget.
- Authority load or migration warnings remain visible and actionable; the Settings section does not manufacture an empty healthy roster from an unavailable authority.

Errors are bounded, sanitized, and contain no token or raw claim material.

## Compatibility

Existing authority and feature documents remain valid. Existing Skills-only grants continue to serve Skills. Users upgrade them through one generic full authorization round trip per character when they want Fittings or need to reauthenticate.

The previous Fittings design's exact-row capability-upgrade requirement is superseded by this design. Its security goals remain, but the UI no longer promises a row-specific flow that EVE cannot present. The generic returned identity is accepted only after full validation and is reconciled by character ID. A proven owner change, meaning two present and unequal owner hashes, is refused until global cleanup completes.

The registered EVE application must permit every scope in the explicit Skills-and-Fittings full authorization set. If deployment configuration does not permit those scopes, the release must not present full authorization as available.

## Testing

### Authority and API

- The full authorization capability set is exactly Skills and Fittings; adding a future capability does not widen it implicitly, and the derived scope union is exactly the four named scopes.
- New-character authorization stores a full grant.
- Authorizing an existing same-owner character replaces its grant and clears reauthentication state.
- An existing Skills-only grant continues to serve Skills before upgrade and serves both capabilities after full authorization.
- An existing character with two present, unequal owner hashes is refused unchanged and instructed to complete global forget first.
- Stored-blank, returned-blank, and both-blank owner-hash cases accept the validated character-ID match and preserve or establish any non-empty hash.
- Lifecycle generation change, cancellation, timeout, validation failure, persistence failure, and single-flight refusal preserve their documented behavior.
- Cancellation wins or loses at the specified linearization point; controlled tests pause during exchange, after validation, after lifecycle-gate acquisition, and immediately before save.
- Refresh-token decryption failure transitions the row to reauthentication-required.
- The shared payload contains display-safe fields and no credentials, owner hashes, or raw claims.
- Authorization activity and terminal failures update through bounded in-memory state without claiming synchronous completion.
- Global forget aggregates result-bearing participant cleanup, reports partial persistence accurately, and blocks same-ID re-add until in-session or startup reconciliation succeeds.
- Required Skills and Fittings cleanup slots report exact blocked IDs when readable; controller construction failure, unreadable state, and unavailable slots are unverified and block every unknown-ID authorization commit.
- A partial Forget followed by restart cannot re-add the ID while either feature cleanup remains failed or unverified.
- Semantic authority events cover activity and terminal outcomes as well as roster changes, with atomic payload state.

### Web contracts

- Settings rail and section declarations remain one-to-one.
- Characters is hidden by the EVE-tools gate and obeys section enter/leave behavior.
- Skills and Fittings link to Settings › Characters.
- Removed per-character authorization actions and the Fittings Characters overlay do not remain as dead markup, handlers, controller methods, or bridge methods.
- README, smoke checks, controller errors, comments, tests, and dev APIs use the centralized full-authorization model and contain no stale **Enable fittings** or row-level reauthentication instructions.
- The roster filter, overflow menu, menu ARIA state and keyboard movement, confirmation, focus restoration, Escape behavior, live regions, hidden overrides, and focus-visible treatment follow page conventions.
- The bridge allowlist, literal Python pushes, and page handlers agree.
- Dev fixtures are generated only in `dev.js` and represent full, partial, reauthentication, warning, empty, authorization-in-progress, partial-cleanup, and maximum-50-character states.

### Layout and manual verification

- Lexical tests pin shared two-pane geometry for Skills and Fittings and far-edge primary-action alignment.
- Screenshot tooling captures Settings › Characters and the repaired Fittings route.
- At the 840x625 floor, a 50-character Settings roster remains usable, including an open overflow menu on the last visible row; the Fittings rail, gap, heading, filters, empty state, pager, and copy action remain visible without overflow.
- A Windows/WebView2 smoke pass covers keyboard and pointer navigation, filtering, complete menu keyboard operation, forget confirmation/refusal/partial cleanup, blocked re-add, authorization start/cancel/success/failure, new and existing returned characters, known owner mismatch, missing-owner compatibility, partial-grant upgrade, route handoff, and supported display scaling.

`docs/smoke-checklist.md` is updated as part of the change. Browser or lexical tests do not substitute for the Windows/WebView2 pass.

## Delivery boundaries

Implementation should proceed in testable slices:

1. Shared full-scope authorization and safe shared character-state API.
2. Settings › Characters route, roster, progress, overflow, and forget flow.
3. Skills and Fittings handoff to the canonical Settings section, followed by removal of obsolete controls and APIs.
4. Shared two-pane geometry and Fittings primary-action alignment repair.
5. Dev fixtures, screenshots, documentation, packaging checks, and Windows smoke coverage.

No slice duplicates authority into Settings state, weakens lifecycle checks, or changes fitting-copy behavior. Each behavior change begins with a failing test and ends with focused and full verification.