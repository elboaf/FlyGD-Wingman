# EVE skill plan readiness

Design. Base: `main` (b2bac93), 2026-08-24.

## Outcome

A fourth top-level route answering one question: **who can fly this?**

You authorise your EVE characters once each, drop skill plans as `.txt` files
in a folder, and the Skills tab shows every character grouped by whether they
meet the selected plan — ready, training with an ETA, trained-but-inactive,
missing N requirements. Expanding a character shows exactly what it still
needs, and is where you re-authenticate or forget it.

The capability exists today in TriffView (GPL-3.0-only, C#/.NET) as
TriffSkills. This is a port, not a rewrite.

Wingman is already GPL-3.0-only, which is what makes deriving from TriffView
lawful; `eve-preview-design.md:14-26` records that relicense and its two
consequences, and nothing here changes them. This is the second subsystem to
travel that road, and the licence now runs both ways: fixes made here can go
back to TriffView.

**Read `SkillPlanEvaluator.cs` before implementing anything.** The
Ready/Training/Locked/Missing/Unknown/Unscored precedence is the whole
semantic core of the feature, and every UI decision below is downstream of it.

## Decisions taken before this design

Five questions were settled first, because each could have changed the
architecture. They are recorded here rather than buried, since the reasoning
outlives the choice.

| # | Decision | Why |
|---|---|---|
| 1 | Wingman registers its own EVE application; the client id is a **plain source constant** | EVE's flow is PKCE public-client — `client_id` only, no secret. Unlike `credentials.py`'s Google secret there is nothing to protect, so the build-time injection precedent does not apply. TriffView does the same (`EveApplication.cs:12` is a plain const). |
| 2 | Refresh tokens live in **one JSON file, each token DPAPI-encrypted** | Keeps roster and tokens in one document, so forget is a single atomic write. See "Token storage" below for the two-store failure class this avoids. |
| 3 | The bridge grows **thin façade methods**, not a generic dispatcher | pywebview takes exactly one `js_api` object (`ui/window.py:141`), so a second bridge object is not available. Nine one-to-three-line delegating methods keep `api.py`'s growth to pure delegation while preserving its return conventions. |
| 4 | **Last-good data stays visible** and is marked stale | A transient ESI blip must not look like data loss. Ported verbatim from TriffView. |
| 5 | The subsystem gets **its own state files and no `settings.py` section** | `settings.save()` projects the complete document from `DEFAULTS` and already has three writers. See "Persistence". |

Two further decisions were taken during design and are argued where they land:
pure-Python RS256 verification rather than a new dependency ("Authentication"),
and conditional ESI requests rather than TriffView's unconditional refetch
("The ESI client").

## Architecture

```
bridge thread (pywebview services pywebview.api.*)
     │  Api.skills_* — nine façade methods, no logic
     ▼
SkillsController ──► worker thread (auth)      browser + loopback listener
     │                                          blocks up to 5 minutes
     ├────────────► worker thread (refresh)    N characters, sequential
     │                                          2 ESI calls each
     └─ _push("onSkills", …) / _push("onSkillsProgress", …)
```

No Scheduler, no timer, no message pump. Refresh is manual, as in TriffView.
A user who never opens the tab pays nothing — no thread, no poll, no hook.
That is the same "costs nothing when idle" posture that justifies
`eve_bookmarks` and `preview` being default-off in `settings.py`, reached here
without needing a flag to gate.

### Threading contract

There is no UI thread. `ui/api.py:16-18` states it plainly — *"`evaluate_js`
is safe to call from any thread; there is no UI thread to marshal onto"* — so
nothing here marshals, and unlike `preview/` this subsystem owns no HWNDs and
needs no pump of its own.

What it does need is to keep the network off the bridge thread:

- **Auth** runs on a worker. It launches the browser and then blocks on the
  loopback accept loop for up to five minutes. Running that on the thread
  servicing `pywebview.api.*` would freeze the window for the duration.
- **Refresh** runs on a worker, iterating characters **strictly
  sequentially**, two ESI calls each, pushing progress after every character.
  Sequential is not laziness: it bounds pressure on ESI's error-limit budget,
  and it is what TriffView does.
- **Single-flight latch.** A refresh requested while one is running sets a
  flag and returns rather than spawning a second worker; the running loop
  re-enters if the flag was set during teardown. Ported from
  `TriffSkillsController.cs:358`.
- **One interactive auth at a time**, via a non-blocking lock. Two concurrent
  authorisations would fight over the same fixed loopback port.

## Module boundaries

New package `obs_youtube_uploader/eveskills/`, split so the majority is pure
and testable on Linux — the discipline `preview/` already sets.

| Module | Responsibility | Platform |
|---|---|---|
| `application.py` | Client id, redirect URI, user agent, scopes | Pure constants |
| `plans.py` | Plan `.txt` grammar, roman numerals, caps | **Pure** |
| `evaluator.py` | Readiness scoring, status precedence | **Pure** |
| `planstore.py` | Plans folder: list, read, name validation | Pure + fs |
| `state.py` | Roster model, tolerant normalise, load/save | Pure + fs |
| `skillids.py` | Skill name → type id cache and its disk format | Pure + fs |
| `esi.py` | Path hardening, retries, error-limit backoff | Injectable transport |
| `sso.py` | PKCE, authorize URL, token exchange and refresh | Injectable transport |
| `loopback.py` | Callback listener and its strict request parser | Sockets |
| `jwt.py` | Claim and RS256 signature validation, JWKS cache | **Pure** given injected fetch |
| `tokens.py` | Token store, atomic forget | Pure + fs, injected crypt |
| `dpapi.py` | `CryptProtectData` / `CryptUnprotectData` | **Windows only** |
| `controller.py` | Orchestration, worker threads, pushes | Threads |

**`dpapi.py` is the only Windows-only module.** Everything else runs in CI on
Linux, including `loopback.py` — it is plain sockets, and TriffView's own
`EveSsoLoopbackIntegrationTests.cs` drives exactly that round trip with a stub
browser.

The SSO stack lives **inside** this package rather than in a shared
`obs_youtube_uploader/eve/`. TriffView factored `native/Eve/` because
TriffFleets and TriffSkills both needed it; in Wingman only Skills needs
authenticated ESI. A parallel effort porting EVE Settings resolves character
names over *unauthenticated* `/universe/names`, which is a twenty-line
`urllib` call and should stay its own — sharing a layer for it would couple
two subsystems that otherwise share nothing.

**`obs_youtube_uploader.eveskills` must be added to `packages` in
`pyproject.toml`.** Package discovery is enumerated by hand there
(`pyproject.toml:64-68`) and the surrounding comment states the consequence: a
missing entry "installs cleanly and fails at import time in the built
artifact, not in the checkout where the source tree makes it work anyway."
`tests/test_packaging_completeness.py` enforces it. This is a required step,
not a follow-up.

## The semantic core

### Readiness

Ported exactly from `SkillPlanEvaluator.cs`. Per requirement, first match wins:

| Order | State | Condition |
|---|---|---|
| 1 | `Unknown` | The skill name did not resolve to a validated category-16 type id |
| 2 | `Active` | `active_level >= required` |
| 3 | `TrainedInactive` | `trained_level >= required` |
| 4 | `Queued` | A skill-queue entry finishes at ≥ the required level |
| 5 | `Missing` | None of the above |

Per plan, the compact status is the worst requirement present:

**`Unknown` > `Missing` > `Locked` > `Training` > `Ready`**

plus `Unscored`, returned early with an empty requirement list whenever the
character has no successful fetch at all.

Three semantics are easy to get wrong and must not be:

- **`Locked` means trained-but-inactive** — the level is trained but the
  active level is lower, which is an inactive clone or a lapsed Omega. It is
  not a permissions concept, and it deliberately ranks *worse* than
  `Training`: a character who has already trained the skill but cannot use it
  is further from flying the plan than one who is actively training toward it.
- **`Unknown` is about the plan, not the character** — a skill *name* that
  never resolved. One unresolved name poisons the whole plan's readiness to
  `Unknown` for every character.
- **`Unscored` is the most common state a user will see.** Every newly
  authorised character is `Unscored` until its first refresh lands, and so is
  any character whose first refresh failed. It is not padding.

Two fidelity notes carried as comments rather than silently reproduced:

- `EarliestSufficientEntry` (`SkillPlanEvaluator.cs:121`) is misnamed. It
  sorts by *lowest sufficient finished level*, tie-broken by queue position —
  **never by date**. The port keeps the behaviour and renames it
  `lowest_sufficient_entry`, with a comment recording that the original name
  misleads.
- The ETA is the **latest** finish date across queued requirements, not the
  earliest: the plan completes when the last one does. It is populated only
  when readiness is exactly `Training` *and* no queued requirement lacks a
  finish date; otherwise the row reads "Training — timing unknown".

### The plan format

A plan is a UTF-8 `.txt` file whose name is its stem. Each line is a skill
name, whitespace, then a level as `I`–`V` (case-insensitive) or `1`–`5`.
Blank lines and `#` comments are skipped. The line is split at the **last**
whitespace, so interior spaces stay in the name.

Caps, all ported: 512 KiB of content, 5,000 lines, 512 characters per line,
2,000 requirements. Names are NFC-normalised, capped at 200 characters, and
rejected if they contain a control character. Duplicates are folded
case-insensitively keeping the **maximum** level, with the first spelling
winning. **Any diagnostic rejects the whole file** — there is no
partial-success mode.

**Three Python-specific traps, none of which exist in the C#.** The source
uses `int.TryParse(token, NumberStyles.None)`, which rejects signs,
whitespace, and separators. Python's `int()` accepts all three — `int("+1")`,
`int(" 1 ")`, and `int("1_0")` all succeed. And `str.isdigit()` returns `True`
for Unicode digits, so `"٥".isdigit()` passes. A naive port therefore
silently accepts `Navigation +5`, `Navigation 1_0`, and `Navigation ٥`. The
level parse guards with `token.isascii() and token.isdigit()` before `int()`,
and the tests state each trap in their docstrings.

## Skill id resolution

There is no bundled SDE. Skill names become type ids over ESI:

1. `POST /v3/universe/ids/` with a batch of ≤ 500 names, unauthenticated.
2. Per resolved name, `GET /v3/universe/types/{id}/` for its `group_id`.
3. `GET /v1/universe/groups/{group_id}/` for its `category_id`, memoised for
   the process lifetime.
4. The name enters the cache only if `category_id == 16` (Skill). Otherwise it
   is a failure with a specific reason, and its requirement scores `Unknown`.

Steps 2–3 fan out at a concurrency of 4, matching TriffView's
`SemaphoreSlim(4, 4)`.

The cache is keyed case-insensitively on the name and **never invalidates**.
That is a deliberate inheritance: EVE type ids do not change, so re-checking
would spend requests to learn nothing. The honest cost is that a name which
resolved wrongly stays wrong until the cache file is deleted.

One deliberate divergence: TriffView's `ValidatedSkillType` carries
`CategoryId = 16` as a constructor default, so a cache entry that *omits*
`categoryId` deserialises to 16 and passes its own validation
(`SkillIdCache.cs:110-121`). The port requires the field explicitly.

## The ESI client

Ported hardening, all of it load-bearing:

- **Path validation.** Must start with a single `/`; no `\`, `?`, `#`, or NUL;
  not absolute; every segment non-empty, not `.` or `..`, and restricted to
  `[A-Za-z0-9_-]`. Query strings are structurally impossible, which is worth
  knowing before anyone adds a paging parameter.
- **Headers.** `User-Agent`, `Accept: application/json`,
  `X-Compatibility-Date`, and `Authorization: Bearer …` when a token is given.
- **Retries.** At most 3 attempts, on `{408, 420, 429, 500, 502, 503, 504}`.
  `GET` always; `POST` only on the `universe/ids` route. Backoff is
  `Retry-After` → `X-Esi-Error-Limit-Reset` → `650ms × attempt`, capped at 30s.
- **Body caps.** 8 KiB for error bodies (truncated), 4 MiB for success bodies
  (oversize raises).
- **Redaction.** The access token is stripped from any error text before it
  can reach a log.
- **Exhaustion returns, it does not raise** — a synthetic 503 that did not
  necessarily come from ESI, which the caller must not mistake for one.

Transport and sleep are injected, matching `discord.py`'s
`transport=_default_transport` seam (`discord.py:196-197,224`). HTTP is
stdlib `urllib.request`: this app has no `requests` dependency and
`discord.py` shows the house pattern for doing without one.

### Conditional requests — a deliberate deviation

TriffView sends no `If-None-Match` and reads no cache headers. Every refresh
refetches every character's full skill list and queue. At forty characters
that is eighty unconditional requests per click, all of it charged against
ESI's error-limit budget to re-download data that mostly has not changed.

The port stores an ETag per (character, endpoint) in the state file and sends
`If-None-Match`; a `304` keeps the existing snapshot and advances
`fetched_utc` only. Roughly thirty lines and two state fields, and it is what
ESI's own guidance asks clients to do.

This is the one place the port knowingly improves on its source rather than
matching it. Recorded here so a future reader does not "fix" it back.

## Authentication

PKCE S256 against `https://login.eveonline.com/v2/oauth/{authorize,token}`,
requesting `esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`.
Read-only; nothing in this subsystem writes to ESI.

`state` and `code_verifier` are each 32 random bytes, base64url without
padding. The challenge is SHA-256 over the **ASCII bytes of the encoded
verifier**, which is what RFC 7636 specifies and what the source does.

### The loopback listener

A **raw socket, not `http.server`.** The strict parser is the entire point,
and `http.server` would happily accept duplicate query keys, non-ASCII bytes,
and an arbitrary `Host` — every one of which the source rejects on purpose.
Ported checks:

- Request line must be exactly `GET <target> HTTP/1.1`.
- Lines are ASCII-only, capped at 8 KiB each and 32 KiB of headers.
- `Host` must equal the redirect authority, and a duplicate `Host` is a
  rejection — this is the DNS-rebinding guard.
- The target must match the redirect's scheme, host, port, and **exact**
  path.
- Query parsing rejects **duplicate keys**, so no last-wins parameter
  smuggling.
- `state` is compared with `hmac.compare_digest`.
- On a state mismatch the listener serves the failure page and **keeps
  listening**. It does not abort: the real browser tab may still be coming.
- Per-connection timeout of 10 seconds; overall timeout of 5 minutes.
- The authorization code is filtered to `[A-Za-z0-9_-]` and truncated before
  it can reach a log or a message.

**The port is fixed and has no fallback**, because the redirect URI is
registered with CCP and must match exactly. A bind failure is reported
plainly rather than silently retried on another port. `51779` is proposed, to
sit clear of TriffView's `51777` so both applications can be installed
together — but the registered value is what governs, and
`application.py` is the single source of truth for it.

### Token validation

Claim validation is ported whole: issuer against the accepted set; audience as
a **conjunction** — `aud` must contain both the literal `"EVE Online"` *and*
the client id; optional `azp` which must equal the client id when present;
expiry with 2 minutes of skew; `sub` matching `CHARACTER:EVE:<id>`; and the
required scopes as a **subset** of those granted, with extras allowed.

Signature verification is **pure-Python RS256**, roughly sixty lines: decode
the JWKS modulus and exponent from base64url to ints, compute
`pow(sig, e, n)`, then check the PKCS#1 v1.5 padding and the SHA-256
`DigestInfo` prefix against `hashlib.sha256` of the signing input, comparing
with `hmac.compare_digest`.

No new dependency. That matters in a repo that does HTTP with stdlib `urllib`
and stores its Google token without `keyring` — and `cryptography`, which
`PyJWT[crypto]` would pull in, is a large binary wheel entering a release
workflow that already carries four post-build assertions because PyInstaller
exits 0 on a missing entry.

The `alg` must be exactly `RS256`, checked on the **unvalidated header before
key selection**. That is the `alg:none` and HMAC-confusion guard and its
ordering is not incidental. JWKS keys are cached for 5 minutes, refreshed
once on an unknown `kid`, and the cache is replaced only on a fully successful
fetch — so a failed refresh leaves the previous keys usable.

### Refresh and failure classification

An access token is refreshed when absent, when it expires within 30 seconds,
or when a caller forces it *and* the cached token equals the one ESI just
rejected. That last clause is the stampede fix: N concurrent 401s from one
stale token produce exactly one refresh, and the callers queued behind the
per-character lock find a token that no longer matches the rejected one.

Failures split two ways, and the split drives the UI:

| Class | Codes | Effect |
|---|---|---|
| **Definitive** | `invalid_grant`, identity mismatch, owner changed, ESI 401 after retry, ESI 403 | `needs_reauth`, stored token deleted, row shows a re-authenticate banner |
| **Transient** | everything else — 5xx, network, other OAuth codes | Error recorded, `needs_reauth` false, last-good data stays visible |

**Cached skill data is never discarded on a refresh failure.** A failed fetch
sets `error` and leaves `fetched_utc` untouched, which is exactly what makes
`stale` mean "you are looking at last-good data".

A third case is worth porting because it is easy to miss: a fetch that
*succeeds* but whose state save fails. The data is live in memory, the row is
flagged degraded, and the message says so — "fresh data is in memory but was
not saved for offline use".

## Token storage

One file, `eve_skills_tokens.json`, written `0600` via `os.open` with an
explicit mode. Each refresh token is wrapped with `CryptProtectData` before
writing; the roster metadata beside it is plaintext.

**Why one document rather than TriffView's Windows Credential Manager.** The
source splits tokens into Credential Manager and the roster into `state.json`,
and cannot update the two atomically. The cost is visible in its own error
strings — `TriffSkillsAuthentication.cs:103` reads *"Forget was rolled back
because state could not be saved"*, and `:108` *"State could not be saved and
credential rollback also failed"* — and in `RecoverOwnCredentials()`, which
exists only to enumerate Credential Manager by prefix and resurrect
placeholder rows for tokens whose state entry went missing. Roughly forty
lines of that file are the split, not the feature. One document makes forget a
single atomic write and makes the entire orphan class impossible rather than
recoverable.

**Why DPAPI rather than plain JSON.** `uploader.py:286-293` is explicit that
`os.chmod` on Windows only toggles the read-only attribute and that one must
*"not assume the exposure is closed there"*. The real protection for a
plaintext file is the `%LOCALAPPDATA%` directory ACL, which gives nothing at
rest — a stolen laptop, a disk image, a backup, or a `%LOCALAPPDATA%`
redirected into OneDrive all expose it. `CryptProtectData` is user-scoped and
closes that gap for about forty lines of ctypes.

**What DPAPI does not buy.** Against malware running as the same user, DPAPI,
Credential Manager, and a plain file are equivalent: `CryptUnprotectData`
succeeds for that user with no prompt. This is a defence against data at rest,
not against local code execution, and the design should not be read as
claiming otherwise.

The `protect`/`unprotect` callables are injected, so `tokens.py` — the store
logic, the atomic forget, the corruption handling — is fully testable on
Linux while only `dpapi.py` is Windows-only.

## Persistence

Four new zero-arg helpers in `paths.py`, matching its rule that every state
path is a function returning a `Path`, never a module constant:

| Path | Contents | Writer |
|---|---|---|
| `eve_skills_state.json` | Roster, snapshots, queue, ETags, selected plan | `atomicio.write_atomic` |
| `eve_skills_tokens.json` | DPAPI blobs, `0600` | `os.open` + `atomicio` |
| `eve_skills_cache.json` | Skill name → type id | `atomicio.write_atomic` |
| `skill_plans/` | Plan `.txt` files | User, plus a seeded starter plan |

**No `settings.py` section.** `settings.save()` projects the *complete*
document from `DEFAULTS` on every call (`settings.py:188`) and already has
three writers, one of them a background thread by deliberate choice. A
character's `active_levels` and `trained_levels` run to several hundred
entries each; forty characters is comfortably several hundred KB, and putting
that through a document rewritten every time someone saves a channel title
would be wrong on both size and contention. The existing `enabled` flags gate
a thread or a keyboard hook; this subsystem starts neither until you click, so
there is nothing to gate. The nav tab is always present, exactly as Bookmarks
and Previews are.

State is normalised tolerantly on load rather than versioned — characters
capped at 50, skill levels bounded to 0–5, queue entries to 500, malformed
entries dropped individually. That is the same posture `settings.py`'s
`validated_*()` functions take, and `preview/layout.py:1-6` states its
rationale: a partially-written file "should cost one preview's position, not
the launch."

### Corruption

Simpler than TriffView's two-tier scheme: preserve the bad file as
`.corrupt-<timestamp>`, start empty, surface a warning in the UI.

**No `.bak` recovery tier.** TriffView's `AtomicFile.Replace` leaves one as a
side effect; `atomicio.write_atomic`'s `os.replace` does not, and adding that
machinery is not worth it when both the state file and the id cache rebuild
completely from one refresh.

The honest exception, stated rather than glossed: the **token** file is the
one that does not rebuild. Losing it costs re-authorising every character.
That is recoverable and safe — no data is destroyed and no credential leaks —
but it is a worse outcome than the other two files and a reader should know it
before deciding the tier is unnecessary.

## UI integration

### The fourth route

Seven edits, all mechanical, and the last is the one that gets forgotten:

1. A `data-route="skills"` button inside `<nav id="routenav">`, a **sibling**
   of `.pywebview-drag-region` — `index.html:15-17` records that a clickable
   child of the drag region yields either dead buttons or an immovable window.
2. A `<div class="route" id="route-skills">` block.
3. `skills: 'route-skills'` in `WM.route`'s map (`app.js:91-94`).
4. `'skills'` added to the peer-destination list, so the gear returns to it.
5. `skills.js` as a new IIFE in the `<script>` list.
6. `onSkills` and `onSkillsProgress` added to `WM.HANDLERS` — an unlisted name
   throws at registration by design.
7. **`skills.js` added to the bundled-asset assertion in both `build.yml` and
   `release.yml`.** The two workflows carry deliberately mirrored steps and
   say so; PyInstaller exits 0 when a `datas` entry resolves to nothing, so a
   missing assertion ships a route whose script is absent.

Unlike `route-previews` this is not a settings form, so it does not wrap in
`<div class="settings"><section class="card">`. It is a two-pane workspace and
introduces that layout to `style.css`, built from Wingman's existing tokens.
TriffView's `--tv-*` variables do not come across. `min_size` is `(840, 625)`,
leaving 626px beside a 214px rail.

### Layout

Ported from TriffView's *shipped* design, which is smaller than its own design
doc describes. `docs/superpowers/specs/2026-08-21-skill-planner-usability-design.md`
specifies `Readiness` and `Train next` tabs, and the implementation plan has a
task for them, but `TriffSkills.tsx` renders a single roster with no tab
control — only a stale comment at line 453 remembers the second one. The
"fewest missing first" ordering that `Train next` existed to provide survives
as the sort inside the `Missing` group. **The port follows what shipped.**

The earlier plans-by-characters glyph grid is **not** ported, and the reason is
recorded in that same document:

> With 40 characters this produces 40 columns with vertically rotated names,
> forcing constant horizontal scrolling to find one character. The glyph fill
> was an appealing idea but does not carry information legibly at cell size.

**Left rail, 214px.** Counts, `Add character`, `Refresh characters`, then one
row per plan showing its ready ratio, then `Open plans folder` and
`Reload plans`. Seven plans fit without scrolling; forty characters never
enter the rail.

**Main pane.** The selected plan's name and requirement count, a notices strip
that collapses when empty, a filter box, then the roster: characters in
groups, ordered `Ready`, `Training`, `Locked`, `Missing` (fewest first),
`Unknown`, `Unscored`. Each group header carries a colour key and a count.
Rows read `Aiga Otsolen … Ready`, `Zuelo Parvi … Training — 2d 4h`,
`Gustav Oswaldo … Missing 6`.

Expanding a row reveals its outstanding requirements — `Active` ones filtered
out — the last successful fetch, any per-character error, a re-authenticate
banner when needed, and `Forget character` behind a two-step confirm.

### The lockout guard

**The roster is built by iterating characters, never by enumerating readiness
groups**, with a trailing catch-all bucket for any status the page does not
recognise.

This is not tidiness. The expanded row is the *only* surface for forgetting or
re-authenticating a character, so a character with no row is a character that
cannot be repaired. Since `Unscored` is the state of every character between
authorisation and first refresh, a roster driven by enumerating known groups
would strand exactly the characters most likely to need repair.

## The bridge contract

Nine façade methods, each one to three lines over `self._skills`, under a
`# ---- EVE skills ---` banner:

| Method | Kind | Returns |
|---|---|---|
| `skills_state()` | read | Full state payload |
| `skills_character_detail(character_id, plan_name)` | read | Requirement rows |
| `skills_add_character()` | mutation | `True`; auth runs on a worker |
| `skills_cancel_auth()` | mutation | `True` |
| `skills_forget_character(character_id)` | mutation | `True` / `False` |
| `skills_refresh()` | mutation | `True` |
| `skills_reload_plans()` | mutation | `True` |
| `skills_open_plans_folder()` | mutation | `True` |
| `skills_select_plan(plan_name)` | mutation | `True` |

Reads return; mutations return truthy and push. **Including the no-op paths** —
`ui/api.py` records that returning `None` from a no-op *was* the bug, because
`WM.send` resolves to `null` on a bridge failure and the page cannot otherwise
tell the two apart.

**No new error channel.** TriffView's `triffskills:error` becomes
`self._alert("warning", …)`, which already exists and already renders.
Per-character errors stay inside the state payload, where the row renders them
next to the data they describe.

Payload keys are **snake_case**, matching `webhook_status` and `video_id`
rather than importing TriffView's camelCase.

`onSkills` carries the whole world and is deduped against the last-pushed JSON
— it is the largest payload in the app and mutation handlers push it on both
success and failure paths, which is what re-syncs the page after a refused
write. `onSkillsProgress` is small and fires once per character during a
refresh. Both have exactly one owner, `skills.js`, per the one-owner-per-handler
rule; anything else needing them listens on a re-dispatched `wm:` event.

## Error, empty, loading, and stale states

- **No characters** — "No characters yet. Add one from the actions on the left."
- **No plans** — "No local plans yet. Drop a `.txt` plan in the plans folder,
  then reload." A starter plan is seeded on first run so this is rare.
- **Filter matches nothing** — a clear-filter action, shown only when a filter
  is actually active.
- **Loading** — `Refreshing…` on the button, `Refreshed n of m characters` in
  the notices strip, `Waiting for EVE SSO…` during auth with the add button
  becoming `Cancel sign-in`.
- **Stale is exception-only.** A `Stale` badge appears when a character has
  last-good data plus an error. There is no `Current` label: in the common case
  every row carried one, which was noise.
- **Plan file issues** roll up into a collapsed disclosure listing filename,
  message, and per-line diagnostics.

## Testing

Pure and Linux-testable in CI, which is the majority of the logic and where
the real bugs live:

| Module | What the tests pin |
|---|---|
| `plans.py` | The grammar, every cap, and the three Python parse traps by name |
| `evaluator.py` | The full precedence table, `Locked` above `Training`, ETA as max, `Unscored` on no snapshot |
| `jwt.py` | RS256 against fixed vectors; `alg:none` and HMAC confusion rejected; the `aud` conjunction |
| `state.py` | Tolerant normalisation, per-entry drops, corruption preservation |
| `skillids.py` | Category-16 enforcement, batching, the explicit-`category_id` divergence |
| `tokens.py` | Atomic forget, corruption, injected crypt |
| `loopback.py` | Duplicate query keys, wrong `Host`, wrong path, state mismatch keeps listening |
| `esi.py` | Path validation, retry set, backoff order, token redaction, synthetic 503 |

Plus `test_api_skills.py` for the façade, using the existing `FakeWindow` —
`tests/fakes.py` notes that a window recording `evaluate_js` is a complete
stand-in for WebView2, which is what lets all of this run on `ubuntu-latest`.

Structural tests, which this repo treats as first-class: the new subpackage
must appear in `pyproject.toml`'s `packages`
(`test_packaging_completeness.py` reads the manifest and asserts it), and
`skills.js` must appear in both workflows' asset lists.

`docs/smoke-checklist.md` takes what the suite cannot: a real SSO round trip
against CCP, the browser launch, the DPAPI round trip on Windows, and a
refresh against a live account with more than one character.

## Scope

### Shipped in this slice

PKCE SSO for N characters, DPAPI token storage, refresh with per-character
failure isolation, plans read from a folder, the evaluator and parser, the
skill-id cache, and the roster with all groups, filtering, in-row expansion,
forget, re-authenticate, stale badges, and the plan-issues rollup.

That is the complete "who can fly this?" loop.

### Deferred, additive, no rework implied

1. **Pins** — star a character so it surfaces above its readiness group.
2. **Character groups** — chips, rename, delete, membership from the expanded
   row.
3. **Clipboard export and import** — `Copy plan` prepending a `# name` title
   line, and an import that reads the clipboard directly. Note if this lands:
   the title line must be *stripped* on import, or every round trip
   accumulates another stale comment in the saved file.
4. **Textarea import** with collision detection and replace.

Pins and groups are what TriffView's redesign put in place of drag-to-reorder.
Deferring them leaves a forty-row roster navigable only by its filter box,
which is acceptable for a first slice and should not stay that way.

### Excluded permanently

**Cross-plan "cheapest to train" ranking.** The evaluator has no skill ranks
and no attribute multipliers, so distance can only ever be a count of missing
requirements, never a time or an ISK cost. Presenting a count as a cost would
be a lie the data cannot support.

**Anything that reads EVE process memory, injects input, performs OCR, or
automates gameplay.** This subsystem makes authenticated HTTPS reads against
CCP's public ESI and nothing else. `eve-preview-design.md:478-482` states that
boundary for the whole application; it applies here unchanged and should not
be quietly crossed.

**Writes to ESI.** The two scopes requested are read-only, and nothing in the
design has a reason to widen them.

## Risks and open questions

1. **The EVE application must be registered before anything can be tested.**
   Someone has to create it at developers.eveonline.com, choose the redirect
   URI, and put the client id in `application.py`. Nothing in the auth stack
   can be exercised end to end until that exists — though every module below
   it is testable with stubs.
2. **The fixed loopback port can be occupied.** There is no fallback, because
   the redirect URI is registered. If `51779` proves contended in practice the
   answer is to change the registration, not to add a fallback.
3. **CCP may rotate `X-Compatibility-Date` expectations.** The header is
   pinned to a date, as in the source. A stale value degrades to whatever ESI
   decides, which is a change this design cannot anticipate.
4. **Pure-Python RS256 is unusual enough to attract a well-meaning
   "simplification".** The tests and the comment in `jwt.py` should make the
   reason for it — and the reason `alg` is checked before key selection —
   hard to miss.
5. **A forty-character refresh is eighty sequential requests.** With ETags most
   return 304, but the first refresh after adding many characters will take
   visible time. Progress is pushed per character so it does not look hung; if
   it proves too slow, bounded concurrency is the lever, at the cost of
   error-limit headroom.
6. **The roster has no automated coverage in TriffView**, and its own design
   doc says so plainly: *"the logic most likely to regress here is the least
   protected."* The port's grouping and ordering is pure Python and **will**
   be tested — this is the one place the port should not inherit its source's
   posture.

## Sizing

Roughly 2,600 lines of C# plus five React components in the source. The
Python port of this slice lands near 2,000 lines across thirteen modules, of
which about 1,400 are pure and covered by CI, plus around 600 lines of
`skills.js` and CSS, and roughly 90 lines of delegation and wiring in
`api.py`, `paths.py`, `__main__.py`, and `pyproject.toml`.
