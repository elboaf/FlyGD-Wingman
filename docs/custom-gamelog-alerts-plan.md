# User-configurable Gamelog Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users configure up to eight local, literal gamelog alerts without weakening built-in alert ownership, delaying unrelated telemetry, or publishing uncommitted settings.

**Architecture:** One thread-free Alerts controller owns custom-rule mutations and exposes the immutable alert projection of the existing committed Preview publication. The sole GameLogStream matches complete lines at the producer, delivers semantic facts and coalesced custom matches together, and the coordinator admits custom work through a separate bounded mailbox. One AlertPolicy arbitrates sounds across the complete coordinator batch; PreviewHost independently protects higher-severity visual admission.

**Tech Stack:** Existing Python 3.11+, pytest, plain HTML/CSS/ES5, Node runtime harnesses, pywebview 6.2.1/WebView2, bundled WAV playback through the current sound module. No new dependency, worker, package, build step, or network integration.

**Spec:** `docs/custom-gamelog-alerts-design.md` at **`2a22f640b09000dc49e6f1beb7b9b3852d7852bf`** (`docs: address preview design review`, branch `design/preview-growth`). The spec is not in this plan branch. Read it with `git show 2a22f64:docs/custom-gamelog-alerts-design.md`, or from the verified design worktree. Do not substitute an unverified later document. Its blob is `14ff223b755217178b80ce3366cd5d18338ca519`.

## Global Constraints

- “Settings > Alerts remains the only surface.” No destination or title-bar changes.
- “Support at most eight custom rules.” Every rule applies to every monitored Listener.
- “Matching is a case-insensitive literal substring over normalized visible text.” No user regex, wildcard, fuzzy, or case-sensitive mode.
- “Custom alerts have lower visual severity than every built-in alert.” Built-in parser semantics and PvE/ownership protections remain unchanged.
- “Custom rules use Wingman's bundled sound library.” Global volume applies.
- “Raw lines do not enter the coordinator queue.” No matching text in Fleet projections, normal logs, exception diagnostics, or history UI.
- “The bound is the stream's existing maximum of 64 sources times eight rules.” Derive the custom capacity from constants; do not copy a magic 512 into multiple owners.
- “A failed settings write leaves the old generation and matcher active.” Prepare before persistence; publish with one non-failing reference swap.
- “Existing settings without `custom_rules` normalize to an empty list, so no migration or defaults-version bump is required.” Preserve existing sound migration and unrelated settings.
- “Free text commits only through Enter or an explicit action, never on blur and never before the first payload renders.” A complete rule edit is atomic.
- “Test exercises sound and preview presentation using the edited rule's style, but does not insert a fake gamelog line or affect cooldowns.” It never persists or leaves a persistent ring.
- Preserve Windows-only native boundaries, dark theme, existing tokens, `.check`/`.radio` or existing swatch wrappers, `.lab` labels, explicit `[hidden]` overrides, 4.5:1 text / 3:1 focus contrast, and the logical 840x625 viewport floor (also measure 839x621 at the documented 200% rounding case).
- Never move/resize an EVE client, send gameplay input, add a second reader, or enable production fleet sharing as part of testing.

---

## 1. Approval, provenance, and intended outcome

**Status: written plan for review; implementation is not authorized.** Only this document is committed in the planning session. The two interpretations in §3.1 need explicit acceptance with this plan before implementation. They are not permission to rewrite the approved design or existing stream behavior silently.

- Source inspected: `b3f349f7ac97900799c8dde2f71161498c337eba`, `test: make crop toggle publication ordering deterministic (#200)`.
- Main and the design branch share that source baseline. `main..2a22f64` contains only three design documents; companion previews and Wanderer overlays are unrelated and excluded.
- Planning worktree: `/mnt/c/dev/flygd-wingman/.worktrees/custom-gamelog-alerts-plan`.
- Planning branch: `plan/custom-gamelog-alerts`.
- Plan path: `docs/custom-gamelog-alerts-plan.md`.
- Before execution, verify the source base, current design blob, and clean linked-worktree state again. If rebasing introduces changes in any ownership boundary below, revisit that task's interfaces rather than copying stale line numbers.

Observable result: a user adds a disabled rule, commits a valid search, enables it, and receives an attributed flash and at most one winning sound when new text arrives. The UI distinguishes reader availability, matching inactivity, waiting for a first invocation, and matcher degradation. Editing or removing a rule cannot turn an old queued match into an alert for the new query. Fleet-only operation remains unaffected when custom matching is off.

## 2. Blindspot pass — evidence and constraints

### Current understanding

This is a bounded alert extension across existing subsystems, not a new telemetry service. User authority is persisted configuration; matcher generation, activation epochs, queues, health and cooldowns are process-local runtime state. A wrong alert is worse than a missed one, so refusal, attribution and stale-work rejection matter more than maximizing delivery under pressure.

### Confirmed constraints

| Evidence at the inspected base | Consequence for the plan |
| --- | --- |
| `wingman/settings.py:891–937`, `_CommittedPreview`, `_prepare_preview_snapshot`, `committed_preview`; `:992–1052`, `update` | Registered Preview readers already get detached committed state, prepared before saving and published under writer serialization. Extend that publication; do not bolt on a post-save cache. |
| `tests/test_settings_committed_preview.py`, particularly blocked-save, preparation-failure, no-post-save-copy, document-scoping and direct-save tests | Producer and pump reads must finish while disk saving is blocked. Direct `save()` remains persistence-only. No nested acquisition of the non-reentrant `_SAVE_LOCK`. |
| `wingman/telemetry/gamelogs.py:173–244,408–459,476–618,640–750` | One owner tracks sources, partial lines and replay prevention. Operations enqueue ordered batches; callbacks run outside stream locks through one drainer. Add batch delivery to that mechanism. |
| `wingman/telemetry/gamelogs.py:82` defines module constant `MAX_FILES = 64`; `_rescan` deduplicates by Listener before applying the cap | Capacity is bounded by selected sources, not every log path in the folder. Retain the ordering and identity rules. |
| `wingman/telemetry/coordinator.py:610–616,751–848,944–957` | The general queue is unbounded and carries rosters, lifecycles and facts. Dispatch collects one batch and calls policy once. Bound only new custom admission, not this queue. |
| `wingman/alerts/service.py:56–99`, `AlertPolicy.handle` | Current playback happens inside the event loop. Changing to one audible winner per batch is an intentional behavior change, including built-in-only batches. |
| `wingman/alerts/patterns.py:16–25`; `wingman/alerts/state.py:83–128` | Built-ins have ranks scram=3, combat=2, decloak=1. Ring state looks up event severity directly. Add renderer kind `custom` at rank 0, but never add it to built-in `EVENTS` or `FILTERED_EVENTS`. |
| `wingman/preview/host.py:983–1010,2497–2532`; `tests/test_preview_host.py` capacity and teardown tests | Host admission currently keeps newest entries regardless of severity. Change its ten-entry mailbox policy, preserve native ownership, and update the old equal-severity eviction expectation explicitly. |
| `wingman/__main__.py:560–616,879–887`; `wingman/ui/api.py:3717–3809,3841–3889` | Startup and lazy telemetry construction must share the same controller/committed reader. Preview's runtime-enabled predicate also protects roster/session revocations during slow master writes; do not replace it indiscriminately. |
| `wingman/ui/api.py:5020–5210`; `wingman/web/alerts.js` `read`, `render`, `healthText`, `startPolling`, `stopPolling` | Built-in bridge contracts already exist. Alerts reads health every two seconds while visible; preserve that local exception to DESIGN.md's general no-polling guidance. No new push channel is needed. |
| `scripts/test_settings_runtime.js`; `tests/test_settings_runtime.py`; `tests/test_bridge_contract.py`; `scripts/js_smoke.js` | Deferred-reply testing patterns exist, but the Alerts dynamic list needs its own executing harness. Lexical guards and top-level smoke are complementary, not substitutes. |

### Likely blind spots and their treatment

- **Same-line sound race:** independently delivering custom callbacks from `_read_source` could sound before the same line's built-in facts leave `_poll`. Task 5 introduces ordered `StreamBatch` delivery; Task 6 makes producer admission indivisible at the coordinator batch cutoff.
- **A second unbounded queue hidden upstream:** producer matching must coalesce while reading, not first accumulate one custom object for every matching line. Keep custom pending storage bounded even when the stream drainer is stalled. Semantic storage retains its existing behavior.
- **Generation verification too early:** a rule can change after coordinator admission, during policy planning, or while the host mailbox is waiting. Verify at each delivery boundary, not only on input.
- **Master Off→On without a rule edit:** rule tokens alone cannot distinguish the old activation. Use a separate activation epoch; do not change rule generations on unrelated saves or master changes.
- **Health recovery that never ran a matcher:** a successful file read, settings save, zero-byte poll or old-generation callback is not matcher recovery. Task 5 tests actual invocation outcomes.
- **UI health accidentally overwrites drafts:** keep periodic reads health-only; correlate hydration and mutation responses with view/request identity and committed rule revision. Do not reuse the existing built-in `lastGood` object for custom rows.
- **Privacy through exception text:** matcher exceptions may contain the input line. Record a fixed health code and safe exception class, never `str(exc)`, traceback locals, raw lines or query text.
- **Unrelated normalization and API fakes:** normalization replaces nested dictionaries. Keep only the document/committed accessor; update affected tests to establish settings before registering readers or mutate through real `settings.update`, not direct post-registration dict edits.

### Checklist disposition

Assumptions, ownership, persisted data, compatibility, concurrency, failure isolation, observability, test limits and UX edge cases all apply and are covered above and below. Security/privacy applies locally and at Fleet projection boundaries; there is no new network or credential capability. Packaging needs import/content regression coverage, but no new subpackage or asset. Deployment remains the existing Windows app. Scope expansion risks are a generic event bus, universal settings framework, parser rewrite, custom history, arbitrary sound picker, and redesign of built-in controls; all are excluded.

### Recommended next step

Review this plan and the two explicit interpretation choices next. Do not implement until approved. If either choice is rejected, revise the affected tasks and tests first.

## 3. Decisions for review, ordered by risk

### 3.1 Spec conflicts — recommendations awaiting approval

1. **Disabled blank configuration versus unconditional empty-search rejection.** The User model requires a persisted blank default and clear-to-disable edit; Match semantics rejects empty normalized text. Interpret the former as the explicit exception: raw empty/space-only search is valid *disabled configuration*, never an executable query. Applying a clear sets `search=""` and `enabled=False` atomically; enabling it is refused. Nonblank input that normalizes to empty (for example `<b></b>`) is refused. Control characters remain refused even in otherwise blank input. This preserves both the intended add/edit workflow and the false-positive guard.
2. **Source replacement wording versus current replay behavior.** `_rescan` EOF-baselines initial paths, already-known paths and retired source IDs; a genuinely new path discovered after initial monitoring begins starts at byte zero. Truncation baselines the rewritten contents at EOF. Recommend preserving these exact tested rules for both built-in and custom parsing. A new-path replacement is not silently changed to EOF. The design says to retain current behavior, but its general replacement sentence is imprecise. If the intended rule is instead “EOF for every replacement,” that is a separate change to shared-reader semantics and needs revised design approval before Tasks 5–6.

No other unresolved design contradiction was found. Existing DESIGN.md's title-bar measurement question does not affect a Settings-only addition. The existing Alerts health polling exception is retained, not broadened.

### 3.2 Architecture and compatibility choices

- **One committed publication, not two authorities.** Extend `_CommittedPreview` with a prepared composite holding its existing detached Preview section and the immutable alert projection. Controller `runtime_snapshot()` reads that projection directly. Logical ownership remains in Alerts; settings is the transaction/publishing mechanism. Reject both per-line deep copies of the live settings dict and after-save controller callbacks.
- **Per-rule generation plus activation epoch.** A changed/new rule receives the next rules-revision integer as its token after successful persistence. An unchanged rule keeps its token, even when a sibling is edited or an earlier row is removed. Matching activation transitions advance a separate epoch. Runtime numbers never enter settings JSON.
- **Source-stamped custom records.** Carry Listener, SourceId/source generation, rule ID/rule generation and activation epoch. They contain neither raw text nor rule names/searches/styles. Dispatch resolves style from current committed authority.
- **Separate bounded admission.** Keep general queue semantics. Coalesce custom pending work by `(character, rule_id, generation)` and reject excess custom keys. Newer valid tokens supersede older tokens for the same character/rule; late older tokens cannot replace newer ones. Never evict a lifecycle, roster or combat fact.
- **One batch-wide audible winner.** Compute all eligible visual dispatches, then select one audible candidate across all characters. Rank built-ins over custom; preserve semantic order for built-in ties and use current list position then stable ID for custom ties. `sound="none"`, muted volume, focused targets and filtered/cooldown-suppressed events are not audible candidates; a silent high-severity visual does not silence an otherwise eligible lower-severity cue.
- **Pending work versus already-started presentation.** Revalidate queued custom work immediately before policy delivery and host arming. An edit does not retract a ring already armed or stop a sound already begun; the design does not request retrospective cancellation. Native calls already admitted at the last check may finish. Tests define the boundary explicitly rather than claiming atomic cancellation of Windows audio.

### 3.3 Bounded details selected for this plan

These fill unspecified local details without adding product options:

- Stable IDs generated with `uuid.uuid4().hex`. Persisted IDs must match ASCII `[A-Za-z0-9_-]{1,64}`. First valid entry for an ID survives; later duplicate entries are rejected individually, never merged. Duplicate names remain valid.
- Names are stripped, nonblank, at most **80 Unicode code points**, with Unicode category `Cc` controls rejected. Unknown entry keys are discarded. No name truncation.
- Search normalization: strip only an actual leading EVE timestamp shape; strip HTML-like tags while preserving adjacent visible text; decode HTML entities; collapse Unicode whitespace; trim; `casefold()`. Preserve category markers and non-timestamp bracketed text. Check control characters before normalization and after entity decoding. Validate the final folded search length **3–200 code points**, reject rather than truncate. Fixed internal regular expressions are allowed; user expressions are literal strings.
- Store canonical stripped display search separately from its prepared folded `needle`, so the editor does not rewrite the user's casing to demonstrate case-insensitive matching. The persisted search preserves markup supplied by the user; its executable meaning is the normalized needle.
- Reuse current style validators: `#rrggbb`, bundled sound IDs/legacy sound mapping, non-bool integer cooldown with existing 0–120 clamp. Persisted malformed style fields use current fallback behavior; interactive invalid style values refuse rather than report a successful edit that normalized to something else. Cooldown UI offers integers 0–120. Custom pulses are fixed at **3**, rate **normal**, derived into the existing renderer spec, not persisted or exposed as new controls.
- New defaults are exactly: `Custom alert`, blank search, disabled, `#ff8c42`, `none`, cooldown 8. Offer Orange in the custom palette without changing built-in defaults or palettes. Reuse the existing out-of-palette swatch treatment for valid hand-edited colours.
- One inline edit disclosure per selected row, not a new modal form system. A row-level **Apply** commits name/search together with current style; Enter does the same. It is not a whole-Settings Save button. Discrete style changes submit a complete rule using acknowledged name/search, never a half-typed text draft. Test may use unsaved style and does not commit pending text.

## 4. File ownership and interface ledger

The following are **proposed new interfaces**, not claims about symbols already present. Existing interfaces explicitly marked retained keep their callers. All production new modules live in the existing `wingman.alerts` package, already packaged.

### Domain types — new `wingman/alerts/custom.py`

Use frozen dataclasses and tuples; no mutable dict/list inside the public runtime projection.

```python
@dataclass(frozen=True)
class CustomRule:
    id: str
    name: str = "Custom alert"
    search: str = ""
    enabled: bool = False
    color: str = "#ff8c42"
    sound: str = "none"
    cooldown_s: int = 8

@dataclass(frozen=True)
class RuntimeRule:
    rule: CustomRule
    generation: int
    position: int
    needle: str

@dataclass(frozen=True)
class BuiltinRule:
    event: str
    enabled: bool
    color: str
    sound: str
    cooldown_s: int
    pulses: int
    flash_rate: str

@dataclass(frozen=True)
class AlertRuntimeSnapshot:
    preview_enabled: bool
    alerts_enabled: bool
    pve_filter: bool
    persist_until_selected: bool
    volume: int
    rules_revision: int
    activation_epoch: int
    builtins: tuple[BuiltinRule, ...]
    custom_rules: tuple[RuntimeRule, ...]
    executable: tuple[RuntimeRule, ...]
```

- `MAX_CUSTOM_RULES = 8`, `MAX_CUSTOM_NAME = 80`, `MIN_CUSTOM_SEARCH = 3`, `MAX_CUSTOM_SEARCH = 200`.
- `RuleValidationError(ValueError)`: fixed user-facing refusal, never include offending input.
- `normalize_visible(text: str) -> str`: pure folded visible text; line input tolerates whitespace, search validation adds the control/length boundary.
- `validate_search(search: object, *, allow_blank: bool) -> tuple[str, str]`: canonical display search and folded needle; raises `RuleValidationError` on invalid input.
- `validate_rule(raw: object, *, normalize_style: Callable[[dict], dict], strict_style: bool) -> CustomRule`: validates identity/name/search/enabled; blank forces disabled in edit/load mode. Enabling an existing blank rule is separately refused by the controller.
- `prepare_alert_snapshot(preview: dict, previous: AlertRuntimeSnapshot | None = None) -> AlertRuntimeSnapshot`: pure projection of normalized Preview settings. Reuse tokens for equal canonical rules, ignoring presentation-index shifts. Advance `rules_revision` only when the ordered authority list changes; new/changed rules get that revision. Advance `activation_epoch` only when effective executable activation changes between off/on. Initial revisions/epoch start at 1, not persisted.
- `match_line(line: str, snapshot: AlertRuntimeSnapshot) -> tuple[RuntimeRule, ...]`: immediate `()` when `executable` is empty, before normalizing; otherwise normalize once and perform at most eight literal `needle in visible` checks.
- `rule_is_current(snapshot: AlertRuntimeSnapshot, rule_id: str, generation: int, activation_epoch: int) -> bool`: requires current epoch and an enabled executable row with that ID/token.
- `presentation_spec(rule: CustomRule, *, persist: bool) -> dict`: fresh renderer dict with colour/sound/cooldown plus `enabled=True`, `pulses=3`, `flash_rate="normal"`, `persist_until_selected=persist`.

### Settings publication — modify `wingman/settings.py`

- `validated_custom_rules(raw) -> list[dict]`: rebuild valid siblings in input order, cap accepted entries at eight, strip unknown keys, serialize only `CustomRule` fields. Its style adapter calls existing `_validated_alert_event` with custom defaults. Add `custom_rules: []` to `_alerts_defaults` and call this validator in `validated_alerts`.
- `validate_custom_rule_edit(rule_id: str, draft: object) -> CustomRule`: strict interactive adapter using the same domain validator/style helper. No new style-validation implementation.
- `_PreparedPreview(section: dict, alerts: AlertRuntimeSnapshot)` is frozen; the detached private `section` is never exposed directly or mutated.
- Preserve `_prepare_preview_snapshot(data: dict) -> dict` as the detach seam used by existing tests. Add `_prepare_preview_publication(data: dict, previous: _PreparedPreview | None) -> _PreparedPreview`, which calls that seam and builds Alerts' projection before saving.
- `_CommittedPreview` holds one `_snapshot: _PreparedPreview`. Retained `get`/`snapshot` copy from `.section`; new `alerts_snapshot() -> AlertRuntimeSnapshot` returns `.alerts` without copying or locking. Initial `.section` retains today's detached-but-not-renormalized behavior; prepare its Alerts projection from `validated_preview(section)` without mutating that section. During `update`, the section is already normalized. This preserves pre-migration Preview reader behavior while making initial alert projection well-formed.
- `settings.update` prepares the composite before `_save_locked` and assigns only `reader._snapshot = prepared` after success, before releasing `_SAVE_LOCK`. Initialization uses the same preparation under registration lock. No controller imports, subscriber callbacks, new registry, or work after save that can fail.

### Controller — new `wingman/alerts/controller.py`

`AlertsController(settings: dict, *, ports: AlertsPorts)` registers and retains `settings_mod.committed_preview(settings)` before serving calls. It is thread-free; mutations serialize in `settings.update` and reread the current list inside that transaction. Do not hold a second controller mutex across the non-reentrant settings lock.

`AlertsPorts` is a frozen dataclass of named effects:

- `update_settings: Callable[[], AbstractContextManager[dict]]`
- `reader_state: Callable[[], dict]` — detached current reader state: `{running: bool, last_error: str | None, characters: list[str], gamelogs_folder: str | None}`; Api owns folder/retained-telemetry adapters.
- `matcher_health: Callable[[], CustomMatcherHealth]` — resolves current retained telemetry, or `waiting`/`inactive` when absent; no lazy construction as a side effect of a read.
- `preview_characters: Callable[[], tuple[str, ...]]`
- `preview_available: Callable[[], bool]`
- `raise_alert: Callable[[str, str, dict], None]`
- `play_sound: Callable[[str, int], None]`

Controller methods and one-line bridge facades:

| Api facade | Controller method | Result |
| --- | --- | --- |
| `get_custom_alert_state()` | `state()` | `CustomAlertState` dict |
| `add_custom_alert()` | `add()` | `CustomMutationResult` dict |
| `edit_custom_alert(rule_id, draft)` | `edit(rule_id: str, draft: object)` | `CustomMutationResult` |
| `set_custom_alert_enabled(rule_id, enabled)` | `set_enabled(rule_id: str, enabled: object)` | `CustomMutationResult` |
| `remove_custom_alert(rule_id)` | `remove(rule_id: str)` | `CustomMutationResult` |
| `test_custom_alert(rule_id, draft)` | `test(rule_id: str, draft: object)` | `{applied, persisted, error}` |

- `runtime_snapshot() -> AlertRuntimeSnapshot` delegates to the committed reader.
- `close_runtime() -> None` sets a thread-safe, one-way final-shutdown Event; it does not mutate settings or rule generations. `is_current(rule_id: str, generation: int, activation_epoch: int) -> bool` checks that Event before delegating to `rule_is_current`. Reserve `(generation, activation_epoch) == (0, 0)` for controller-created Test presentation only: it requires an existing rule ID and open runtime but not an enabled search. Normal runtime tokens always start at 1. Test endpoints refuse after close; queued Test presentation must also pass this predicate.
- `CustomAlertState`: `{revision: int, rules: list[dict], limit: int, previews_enabled: bool, alerts_enabled: bool, reader: dict, matcher: dict}`. `rules` contain only the persisted fields. `revision` is `rules_revision`; not every health poll increments it.
- Matcher UI dict: `{state: 'inactive'|'waiting'|'active'|'degraded', detail: str | None}`. Current committed inactivity outranks a retained degradation in display, without falsely recording recovery.
- `CustomMutationResult`: standard `{applied: bool, persisted: bool, error: str | None}` plus `state: CustomAlertState` and `rule_id: str | None`. State is captured after the transaction; it may include a later legitimate commit and its revision. The UI must not assume it is the exact submitted draft.
- `draft` is a complete object with exactly the editable persisted fields, excluding ID: `name`, `search`, `enabled`, `color`, `sound`, `cooldown_s`. Missing fields refuse. Unknown fields are discarded; supplied ID can never rename authority.
- Successful/no-op mutation: applied/persisted true. Refusal/save rollback: both false; old acknowledged state returned. Test: persisted false on every path; validate colour/sound independently of search so an unfinished disabled rule can test style. Test requires a still-existing ID, never creates/updates a rule.

### Producer records — extend `wingman/telemetry/model.py`

```python
@dataclass(frozen=True)
class CustomMatch:
    character: str
    source_generation: int
    source_id: SourceId
    rule_id: str
    generation: int
    activation_epoch: int

@dataclass(frozen=True)
class StreamBatch:
    events: tuple[SourceLifecycle | CombatFact, ...] = ()
    custom_matches: tuple[CustomMatch, ...] = ()

@dataclass(frozen=True)
class CustomMatcherHealth:
    state: str
    rules_revision: int = 0
    activation_epoch: int = 0
    detail: str | None = None
```

`GameLogStream.__init__` adds optional `custom_snapshot: Callable[[], AlertRuntimeSnapshot] | None = None`, `custom_matcher: Callable[[str, AlertRuntimeSnapshot], tuple[RuntimeRule, ...]] = custom.match_line`, and `on_matcher_health: Callable[[CustomMatcherHealth], None] | None = None`. `None` snapshot provider leaves all new machinery inert. `subscribe_batches(callback: Callable[[StreamBatch], None]) -> Callable[[], None]` is additive; existing `subscribe` continues to deliver only semantic events.

Health outcomes are retained by the stream and queryable through `custom_health() -> CustomMatcherHealth`; the dedicated callback reports changes only, outside locks and with its own exception guard. Coordinator exposes `custom_matcher_health() -> CustomMatcherHealth`. Neither uses `StreamHealth` or Fleet payload fields for matcher status. A previous `active` outcome for another revision/epoch projects as `waiting`, not active for the edited query. A retained `degraded` outcome remains degraded until an actual successful current invocation; changing settings alone cannot clear it. Current inactivity is displayed as inactive while preserving that recovery obligation internally.

### Coordinator, policy and host

- Add `custom_snapshot: Callable[[], AlertRuntimeSnapshot] | None = None` to `TelemetryCoordinator.__init__`. `_on_stream_batch(batch: StreamBatch, delivery_epoch: int) -> None` is a cheap producer handoff. Subscription closure captures the current stream-delivery epoch; old callbacks after detach are refused.
- `CUSTOM_PENDING_MAX = MAX_FILES * MAX_CUSTOM_RULES` in coordinator; stream uses the same constituent constants, not an import back from coordinator. `_custom_pending` is an ordered map keyed by `(character, rule_id, generation)`; `_custom_drain_queued` tracks one `_CUSTOM_DRAIN` sentinel.
- The coordinator keeps current source lifecycles for custom validation without requiring a live roster/preview. This is distinct from Fleet Metrics' roster-source join; an absent/excluded preview still permits sound.
- Retain `AlertPolicy(config, sound, focused, on_alert)` and its current `handle(events, now)`/returned list contracts. Add keyword-only `runtime_snapshot: Callable[[], AlertRuntimeSnapshot] | None = None` and `custom_current: Callable[[str, int, int], bool] | None = None` to construction, plus keyword-only `custom_matches: tuple[CustomMatch, ...] = ()` to `handle`. Production passes controller `runtime_snapshot` and `is_current`; custom eligibility must pass both current-snapshot and open-runtime checks. Compatibility-only callers without the provider keep working for built-ins. Add `forget_custom_character(character: str) -> None` for source retirement; it clears only that character's custom cooldowns.
- Retain `PreviewHost.raise_alert(character: str, event: str, spec: dict) -> None`. Pending entries become a private frozen record carrying character, event, copied spec, and rank. For runtime custom alerts, the fresh spec additionally carries `custom_rule_id`, `custom_generation`, `custom_activation_epoch`; never persist those keys. Test adds `custom_test=True` and the existing rule ID with reserved zero tokens, constructed only by the controller, never copied from bridge input.
- `PreviewHost.__init__` adds optional `custom_alert_current: Callable[[str, int, int], bool] | None = None`. The composition adapter delegates to controller `is_current`, including the final-shutdown gate. Recheck all custom entries immediately before `win.arm_alert`; zero tokens require `custom_test is True`, normal tokens require current executable authority, and malformed entries are refused. Host constructor callback setup happens before host start; it never acquires settings I/O locks.

## 5. Concurrency and admission algorithms

### Committed publication and lock ordering

```text
settings writer: _SAVE_LOCK -> normalize -> prepare composite -> durable save
                               -> single committed reference swap -> unlock
producer/policy/pump: capture committed reference -> pure reads (no _SAVE_LOCK)
controller effect ports: after transaction, with no settings lock held
```

A candidate snapshot can allocate and fail before saving. After saving, publication cannot validate, copy, call ports or acquire another subsystem's lock. A failed save exposes neither its candidate rule token nor activation epoch. Existing registered readers continue to share one document-scoped owner, with no registry leak.

### Producer batching and bounded staging

Match the same complete line that semantic parsing sees, but never send it downstream. Parse semantic facts unchanged; custom failure cannot skip those facts or later lines. Capture one immutable snapshot per invocation; no work when its executable tuple is empty.

While reading a poll, collect custom matches in a coalescing map bounded to `MAX_FILES * MAX_CUSTOM_RULES`; replace repeats, evict older rule generations for the same Listener/rule, refuse excess keys. Do not grow a list first and coalesce it afterward.

On stream enqueue, assign a monotonically increasing internal batch number. Keep `_dispatch_queue` entries as a private `_QueuedBatch(number: int, events: tuple[SourceLifecycle | CombatFact, ...])`; store custom matches in one bounded `_pending_custom` map whose values are `(owning_batch_number, CustomMatch)`. Replacing a repeated match also moves its owner number to the newer semantic batch. Under the existing dispatch-queue lock, the single drainer takes one semantic batch and extracts only custom entries owned by that batch or earlier; it then delivers one public `StreamBatch` outside locks. Never retain a custom tuple on every queued semantic batch. This concretely bounds pending custom storage even when the drainer is stalled, and a later duplicate cannot sound before its latest semantic batch. The current bounded poll/drain working sets are separate, each at most capacity; no count grows with the number of stalled polls.

Preserve semantic batches and their order; custom staging may drop/refuse excess work. Legacy subscribers see each semantic event exactly once. Stage health transitions in a single latest-outcome slot during reading; validate and deliver the dedicated health callback through the drainer outside `_op_lock`, `_lock` and `_dispatch_lock`. Custom callback exceptions never interrupt semantic delivery.

### Coordinator cutoff — no split same-line arbitration

Use one short ingress lock for `_on_stream_batch` to enqueue all semantic events, merge custom pending entries and enqueue the sole sentinel. This lock is not held across blocking queue waits, `_process`, metrics, policy, sound, native calls, source republication, or joins.

The dispatcher can obtain its first item with blocking `Queue.get` outside ingress. Each subsequent nonblocking queue read, including the final empty decision, occurs under ingress. Seeing `_CUSTOM_DRAIN` records that custom work is pending; it does not repeatedly extend an ordinary local list. At the final empty observation, under that same lock, take the bounded custom map exactly once and reset sentinel ownership. Work admitted after this cutoff belongs wholly to the next batch. Stop before policy discards the local custom tuple. This keeps per-iteration custom work bounded even if semantic traffic prolongs the current iteration.

```text
_on_stream_batch:
    lock ingress
    queue each semantic event unchanged
    if custom delivery epoch is current and custom admission is open:
        merge valid custom keys; ensure one sentinel
    unlock

coordinator batch cutoff:
    lock ingress
    if general queue is empty:
        take custom map (at most capacity); replace with empty map
        reset custom sentinel flag; batch is sealed
    unlock
    validate source/rule/activation, then call policy once
```

The initial blocking dequeue does not permit splitting a producer batch: the final empty decision cannot pass the producer's ingress lock before its facts and sentinel are fully admitted. No timeout, maxsize or drop behavior is added to unrelated queue traffic. Retain `_ALERT_RESET`, `_FLEET_REFRESH`, `_FleetMode`, stop checks and envelope sequencing. An alert reset also discards previously collected alert candidates from the retired alert activation rather than merely resetting cooldowns before dispatching those old candidates.

### Lifecycle and stale delivery

- Source lifecycle retirement/replacement invalidates matching source stamps before policy. Do not route custom records through Fleet Metrics to obtain that check.
- Rule edits/removes invalidate queued rule generations. Master transitions invalidate activation epochs. A successful unrelated save changes neither.
- Detach/stop fences the stream-delivery epoch and clears custom staging; delayed old producer callbacks cannot repopulate a new runtime. Clear source-validation state when the stream generation retires.
- `_close_eve_runtime` calls controller `close_runtime()` and closes custom coordinator admission before native teardown, outside settings locks. Add a coordinator `close_custom_admission() -> None` method that synchronously fences/clears only custom ingress and is called through the existing shutdown ownership path; no new join. `stop()` also fences its custom ingress. Ordinary reactivation after nonfinal stop opens a new delivery epoch; final API shutdown never reopens it.
- Preserve timed-out dispatcher/stream/host ownership and existing stop deadlines. No replacement owner starts just because a custom callback is stuck.
- Policy revalidates custom candidates before cooldown consumption and before visual delivery/sound selection; the host revalidates before arming. No locks are held while playing audio or calling PreviewHost. Already-admitted native effects are not retroactively canceled.

## 6. Ordered implementation tasks

Every task is an independently reviewable commit, not an independently releasable partial feature. Keep dormant optional seams until Task 8 connects production. Within each task, execute each named regression as a small red–green–refactor cycle rather than writing the entire feature before running tests. The examples below are representative executable tests/algorithm kernels; the enumerated cases are also required, not optional follow-up coverage.

### Task 1: Pure rule identity, normalization and matching

**Files:** Create `wingman/alerts/custom.py`, `tests/test_custom_alerts.py`. Read `wingman/telemetry/parsing.py` and the marked-up constants in `tests/test_telemetry_gamelogs.py`; do not change the built-in parser.

**Consumes:** approved matching semantics and §3.1 blank interpretation. **Produces:** all domain types, constants and pure functions in §4.

- [ ] Write a pure regression before implementation:

```python
def test_visible_literal_matching_preserves_categories_and_casefolds():
    from wingman.alerts.custom import normalize_visible, validate_search

    line = "[ 2026.08.25 11:30:00 ] (notify) <b>Straße</b> &amp;  fleet"
    assert normalize_visible(line) == "(notify) strasse & fleet"
    assert validate_search("STRASSE", allow_blank=False) == ("STRASSE", "strasse")
    assert normalize_visible("[Fleet] war<b>p</b>") == "[fleet] warp"
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alerts.py -q`; confirm missing module/function, then assertion failures as each function lands.
- [ ] Implement normalization and validation with fixed timestamp/tag rules, `html.unescape`, whitespace collapse and Unicode folding. Keep user text out of error messages. The matcher kernel is:

```python
def match_line(line, snapshot):
    if not snapshot.executable:
        return ()
    visible = normalize_visible(line)
    return tuple(row for row in snapshot.executable if row.needle in visible)
```

- [ ] Add/run isolated cases for actual `<color>`, `<font>`, `<fontsize>`, category markers, adjacent tags, entities, Unicode folding, literal regex metacharacters, NBSP, exact 2/3/200/201 folded lengths, casefold expansion across the maximum, raw/decoded controls, wrong input types, blank disabled versus markup-only, IDs and name boundaries. Assert no search truncation. Add token-preservation/order-shift tests for `prepare_alert_snapshot` and an instrumented normalizer that raises if called for an empty executable tuple.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_custom_alerts.py tests/test_alerts_patterns.py tests/test_telemetry_parsing.py -q`. Confirm built-in ownership parser outputs are unchanged. Refactor only shared custom pure logic.
- [ ] Commit: `git add wingman/alerts/custom.py tests/test_custom_alerts.py && git commit -m "feat(alerts): define bounded literal custom rules"`.

### Task 2: Settings normalization and atomic immutable publication

**Files:** Modify `wingman/settings.py`, `tests/test_settings_alerts.py`, `tests/test_settings_committed_preview.py`; create `tests/test_settings_custom_alerts.py`.

**Consumes:** Task 1 domain projection and validation. **Produces:** empty-list compatibility, strict edit adapter, `_PreparedPreview`, `alerts_snapshot()` and the existing single-swap transaction integration.

- [ ] Write failing compatibility and identity tests:

```python
def test_old_settings_gain_an_empty_custom_list_without_version_change():
    from wingman import settings

    old = settings._alerts_defaults()
    version = old["defaults_version"]
    old.pop("custom_rules", None)
    result = settings.validated_alerts(old)
    assert result["custom_rules"] == []
    assert result["defaults_version"] == version


def test_failed_write_cannot_publish_a_rule_or_generation(monkeypatch, tmp_path):
    import pytest
    from wingman import settings

    document = settings.load(tmp_path / "settings.json")
    reader = settings.committed_preview(document)
    before = reader.alerts_snapshot()

    def fail_save(data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(settings, "_save_locked", fail_save)
    with pytest.raises(OSError), settings.update(document):
        document["preview"]["alerts"]["custom_rules"] = [
            {"id": "r1", "name": "Fleet", "search": "fleet invite", "enabled": True}
        ]
    assert reader.alerts_snapshot() is before
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_settings_custom_alerts.py -q`.
- [ ] Implement list rebuilding, defaults and the strict edit adapter using the existing style validator. Preserve malformed sibling isolation and first-valid-ID policy. Prepare both projections before saving; the publication portion must remain only:

```python
if reader is not None:
    reader._snapshot = prepared
```

  Update `_CommittedPreview.get`/`snapshot` to copy `.section` and add the noncopying `.alerts_snapshot` accessor. All field construction belongs in `_prepare_preview_publication`, outside the post-save block.
- [ ] Extend the existing Event/ThreadPoolExecutor blocked-save tests: every alert reader returns the old composite while save is blocked; failed save and failed projection preparation keep file/document/token unchanged; successful commit swaps all gates/rules/built-in policy together. Assert post-save execution never deep-copies/validates. Test direct `save`, unrelated/category/layout/crop writes, registry lifetime/document isolation, nested mutation attempts, per-rule edit tokens, deletion/order shifts, no-op stability, effective-activation epochs, empty/oversized lists, malformed siblings/IDs/unknown keys, legacy sounds, and unchanged defaults versions.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_settings_custom_alerts.py tests/test_settings_alerts.py tests/test_settings_committed_preview.py tests/test_settings_transactions.py tests/test_settings_preview.py -q`.
- [ ] Commit: `git add wingman/settings.py tests/test_settings_custom_alerts.py tests/test_settings_alerts.py tests/test_settings_committed_preview.py && git commit -m "feat(alerts): publish custom rules with committed settings"`.

### Task 3: Controller transactions and style-only Test

**Files:** Create `wingman/alerts/controller.py`, `tests/test_custom_alert_controller.py`; modify `wingman/telemetry/model.py`. No bridge/UI wiring yet.

**Consumes:** Task 2 strict validator, committed accessor and real `settings.update`; domain types and `CustomMatcherHealth` contract (introduce that dataclass in `wingman/telemetry/model.py` in this task). **Produces:** controller/ports and exact result shapes in §4.

- [ ] Add a fixture constructing `AlertsController` with real temporary settings and ports backed by recording lists. The update port is `lambda: settings.update(document, path)`, reader/health ports return fixed detached state, and sound/raise ports append to lists. Do not replace `paths.settings_file` or mock `settings.update`.
- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alert_controller.py -q`. First regression:

```python
def test_add_is_disabled_and_enable_without_search_refuses(controller):
    added = controller.add()
    assert added["applied"] and added["persisted"]
    rule = added["state"]["rules"][0]
    assert rule["name"] == "Custom alert"
    assert rule["search"] == ""
    assert rule["enabled"] is False
    assert rule["color"] == "#ff8c42"
    assert rule["sound"] == "none"
    assert rule["cooldown_s"] == 8
    refused = controller.set_enabled(rule["id"], True)
    assert not refused["applied"] and not refused["persisted"]
    assert controller.state()["rules"] == added["state"]["rules"]
```

- [ ] Implement add/edit/enable/remove as serialized read-modify-write transactions. Normalize/compare canonical values inside the transaction; use a private exception for no-op/refusal so an unchanged transaction does not save. Build state after releasing the lock. Rule IDs are generated only by add. Test uses the existing rule ID and validated draft style, calls sound once at committed volume, calls host for each available character with `custom_test=True`, the rule ID, reserved zero tokens and persistence false; never inserts a match or consumes a cooldown. Recheck `is_current(rule_id, 0, 0)` before sound/presentation so final shutdown refuses pending Test effects as well.
- [ ] Add separate cycles for eight-rule capacity/concurrent adds; duplicate names; invalid/missing IDs; incomplete drafts; clear atomically disables; enable/no-op/unknown bool types; concurrent independent edits preserve both rows; rollback at add/edit/toggle/remove with the old snapshot object retained; blocked I/O exposes no candidate; actual file round-trip; returned state revision; unavailable preview versus no clients; no-sound/volume-zero Test truthfulness; edited style Test with blank/invalid search; Test ignores focus and master/rule enable as presentation-only behavior; final `close_runtime` refuses Test and makes both normal and reserved-token `is_current` false.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_custom_alert_controller.py tests/test_settings_custom_alerts.py -q`. Assert controller imports no `wingman.ui`, starts no thread, and holds no window.
- [ ] Commit: `git add wingman/alerts/controller.py wingman/telemetry/model.py tests/test_custom_alert_controller.py && git commit -m "feat(alerts): add transactional custom alert controller"`.

### Task 4: Protect PreviewHost admission and custom ring severity

**Files:** Modify `wingman/alerts/patterns.py`, `wingman/preview/host.py`, `tests/test_alerts_state.py`, `tests/test_preview_host.py`. Existing `wingman/preview/window.py:741` `arm_alert` is a consumer to verify, not a planned rewrite.

**Consumes:** rank 0 renderer event, current-rule predicate, §4 token payload. **Produces:** severity-aware ten-entry mailbox and custom arming through the existing ring state machine.

- [ ] Write failing pure ring and host-capacity tests. Reuse real `PreviewHost` with `_post` stubbed and current test natives, not a second mailbox implementation. Ring example:

```python
def test_custom_cannot_repaint_an_active_decloak():
    from wingman.alerts import state

    high = state.arm(None, "decloak", "#4dd2ff", 0.0,
                     duration_ms=1200, pulses=3, persist=False,
                     target_is_selected=False)
    actual = state.arm(high, "custom", "#ff8c42", 0.1,
                       duration_ms=1200, pulses=3, persist=False,
                       target_is_selected=False)
    assert actual.event == "decloak"
    assert actual.color == "#4dd2ff"
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_alerts_state.py tests/test_preview_host.py -k 'custom or alert_queue or pending_alert' -q` (also run each new named capacity test explicitly).
- [ ] Add `SEVERITY["custom"] = 0`, leaving parser `EVENTS` unchanged. Store severity in the private pending record. Admission kernel under the host lock:

```python
if len(pending) == PENDING_ALERTS_MAX:
    victim = next((i for i, old in enumerate(pending)
                   if old.severity < incoming.severity), None)
    if victim is None:
        return
    del pending[victim]
pending.append(incoming)
```

  Post the native wake only for accepted entries. Revalidate custom tokens, including the explicit zero-token Test convention, just before arming; false/raising predicates refuse custom only. Teardown still empties pending entries.
- [ ] Test custom-full→scram replaces oldest lower entry; built-in-full→custom refuses; equal-rank-full refuses newest and retains FIFO; mixed ranks replace the oldest *strictly lower* entry, not simply the lowest rank; payload copied on admission; stale after admission/edit/removal/off→on; expiry/persistence/focused timed-ring behavior; no-preview no-op and cleanup. Update the existing “keep newest” capacity test because this spec intentionally supersedes that behavior.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_alerts_state.py tests/test_preview_host.py tests/test_preview_alertframes.py tests/test_engine_invariants.py -q -rs`. Inspect Windows-only skips separately.
- [ ] Commit: `git add wingman/alerts/patterns.py wingman/preview/host.py tests/test_alerts_state.py tests/test_preview_host.py && git commit -m "feat(preview): protect built-in alert mailbox priority"`.

### Task 5: Producer matching, ordered batches and independent health

**Files:** Modify `wingman/telemetry/model.py`, `wingman/telemetry/gamelogs.py`, `tests/test_telemetry_gamelogs.py`; create `tests/test_custom_alert_stream.py`.

**Consumes:** immutable snapshot/matcher, `CustomMatcherHealth`, confirmed existing replay rules. **Produces:** `CustomMatch`, `StreamBatch`, additive `subscribe_batches`, independent `custom_health` and optional health callback.

- [ ] Extend the existing `_log`, `_stream`, `NOW`, marked-up line fixture pattern in a new focused file. Use actual temporary text files and `scan_once`, not invented cursor behavior. First test: baseline a preexisting matching line, append a partial match, assert zero custom deliveries, complete its newline, then assert exactly one source-stamped Listener match and no raw-line field.
  Start with this actual-file regression (the imported helpers already exist):

```python
def test_custom_lines_obey_eof_and_newline(tmp_path):
    from tests.test_telemetry_gamelogs import NOW, _log, _stream
    from wingman import settings
    from wingman.alerts.custom import prepare_alert_snapshot

    preview = settings.validated_preview({"enabled": True, "alerts": {
        "enabled": True, "custom_rules": [{"id": "r1", "name": "Fleet",
        "search": "fleet invite", "enabled": True}]}})
    snapshot = prepare_alert_snapshot(preview)
    path = _log(tmp_path, "Alice", "(notify) fleet invite\n")
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches = []
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert not [m for b in batches for m in b.custom_matches]
        with path.open("a", encoding="utf-8") as output:
            output.write("(notify) FLEET INVITE")
        stream.scan_once(NOW)
        assert not [m for b in batches for m in b.custom_matches]
        with path.open("a", encoding="utf-8") as output:
            output.write("\n")
        stream.scan_once(NOW)
        matches = [m for b in batches for m in b.custom_matches]
        assert [(m.character, m.rule_id) for m in matches] == [("Alice", "r1")]
        assert matches[0].generation == snapshot.custom_rules[0].generation
    finally:
        stream.stop()
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alert_stream.py -q`.
- [ ] Add matching beside semantic parsing with a separate exception guard, accumulating only bounded coalesced custom keys. Preserve existing `_op_lock` and drainer ownership. Introduce ordered batches for new subscribers, preserving legacy per-event delivery once. Health outcome kernel:

```python
try:
    matches = custom_matcher(line, snapshot)
except Exception:
    outcome = CustomMatcherHealth("degraded", snapshot.rules_revision,
                                  snapshot.activation_epoch,
                                  "Custom matching failed.")
    matches = ()
else:
    outcome = CustomMatcherHealth("active", snapshot.rules_revision,
                                  snapshot.activation_epoch)
```

  Only invoke this block for a nonempty executable tuple. Retain outcomes only if revision/epoch still match the current committed projection. Deliver changed health callbacks outside stream locks; callback failure is isolated. No `exc_info` or exception message on custom failure.
- [ ] Add tests for no normalization under each false master/all-custom-disabled with Fleet still reading; semantic facts survive matcher exception; success with zero matches recovers; stale success cannot clear a newer degradation; settings save/empty poll cannot clear it; initial waiting; inactive rendering; malformed timestamps versus visible matching; all Listener attribution and broadcast duplicates independent of parser target ownership/PvE filtering.
- [ ] Pin initial history, partial lines, truncation, known-path replacement, retired source, genuinely new-path replacement, source re-publication, no duplicate delivery, and start/stop/timed-out owner behavior. Block the drainer and submit repeated polls: custom staging remains bounded/coalesced, semantic lifecycle/fact count and order are unchanged, and no custom callback precedes its associated semantic batch.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_custom_alert_stream.py tests/test_telemetry_gamelogs.py tests/test_telemetry_parsing.py -q -rs`.
- [ ] Commit: `git add wingman/telemetry/model.py wingman/telemetry/gamelogs.py tests/test_custom_alert_stream.py tests/test_telemetry_gamelogs.py && git commit -m "feat(telemetry): match custom alerts in ordered stream batches"`.

### Task 6: Bounded coordinator admission without collateral drops

**Files:** Modify `wingman/telemetry/coordinator.py`, `tests/test_telemetry_coordinator.py`; create `tests/test_custom_alert_admission.py`.

**Consumes:** Task 5 batch API and source-stamped records; Task 2 committed predicate. **Produces:** bounded custom mailbox, one sentinel, atomic producer admission/cutoff, source/delivery-epoch verification and `close_custom_admission`.

- [ ] Extend current `FakeStream` with a recording `subscribe_batches` seam; update production coordinator subscription to batch-only (never subscribe both ways). Use `_noop_thread_factory`, recording metrics and `dispatch_once(0)` from the existing coordinator harness. Extend `FakePolicy.handle` to accept keyword-only `custom_matches=()` and record it. Introduce coordinator `_dispatch_alerts(alerts, custom_matches=())`: with custom candidates it calls the future policy contract `handle(alerts, now, custom_matches=...)`; with none it retains the current two-argument call. Production custom input remains dormant until Tasks 7–8, so this task is testable with the recording policy without a partial production policy. Test the retained legacy stream subscription separately in Task 5.
  Give `FakePolicy` a separate `custom_calls` list so old `calls` assertions retain their shape. The new callback epoch field is `_stream_delivery_epoch`. A first admission test is:

```python
def test_repeated_custom_keys_use_one_sentinel(tmp_path):
    from tests.test_telemetry_coordinator import FakePolicy, _harness, _lifecycle, _source_id
    from wingman import settings
    from wingman.alerts.custom import prepare_alert_snapshot
    from wingman.telemetry.model import CustomMatch, StreamBatch

    snapshot = prepare_alert_snapshot(settings.validated_preview({"enabled": True,
        "alerts": {"enabled": True, "custom_rules": [{"id": "r1", "name": "Fleet",
        "search": "fleet invite", "enabled": True}]}}))
    policy = FakePolicy()
    h = _harness(tmp_path, preview=True, alerts=True, alert_policy=policy,
                 custom_snapshot=lambda: snapshot)
    try:
        h.coordinator.reconcile()
        h.pump()
        sid = _source_id()
        match = CustomMatch("Alice", 1, sid, "r1", snapshot.custom_rules[0].generation,
                            snapshot.activation_epoch)
        epoch = h.coordinator._stream_delivery_epoch
        h.coordinator._on_stream_batch(
            StreamBatch((_lifecycle("Alice", source_id=sid),), (match,)), epoch)
        for _ in range(1000):
            h.coordinator._on_stream_batch(StreamBatch(custom_matches=(match,)), epoch)
        assert len(h.coordinator._custom_pending) == 1
        assert h.coordinator._queue.qsize() == 2  # lifecycle plus one sentinel
        h.pump()
        assert policy.custom_calls[-1] == (match,)
    finally:
        h.coordinator.stop()
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alert_admission.py -q`.
- [ ] Implement §5 ingress/cutoff algorithm. Gate custom work on current rule/activation snapshot, delivery epoch and closing state at ingress. Validate source stamps only after queued lifecycles have been processed at the batch cutoff; producer admission must not consult the dispatcher-only source map before a preceding activation arrives. Keep every semantic enqueue unchanged. At a saturated custom map, the refusal path is simply:

```python
if key not in pending and len(pending) >= CUSTOM_PENDING_MAX:
    return False
pending[key] = match
return True
```

  Execute superseded-generation pruning and current-token checking before this capacity check. A repeat replaces its pending value; an old generation never displaces a newer value. Detach/reset/stop clear only the custom state they own.
- [ ] Test capacity using **current valid** rule IDs/tokens (64×8), then a 65th character key before lifecycle cleanup; prove refusal rather than stale-validation rejection. Interleave roster, lifecycle, combat, Fleet refresh and mode payloads: all still reach their original consumers. Check one sentinel after thousands of repeats, newest generation replacement, stale older refusal, and bounded custom tuple at a prolonged batch cutoff.
- [ ] Add Event-based interleavings: pause producer admission after first semantic enqueue, attempt dispatcher cutoff, verify no policy call until batch admission completes; no lock is held when processing source republication; concurrent producer after cutoff belongs wholly to next batch; source retirement inside a collected batch drops old custom work; stop mid-batch/late callback after detach cannot sound or repopulate; timed-out owner retained. Assert semantic sequence order and absence of custom records in metrics/Fleet projection.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_custom_alert_admission.py tests/test_telemetry_coordinator.py tests/test_fleet_runtime_integration.py -q -rs`. Do not add a general queue limit, arbitrary batch time budget, or coalescing of unrelated payloads to make a stress test pass.
- [ ] Commit: `git add wingman/telemetry/coordinator.py tests/test_custom_alert_admission.py tests/test_telemetry_coordinator.py && git commit -m "feat(telemetry): bound custom alert admission independently"`.

### Task 7: Batch-wide sound arbitration and custom policy

**Files:** Modify `wingman/alerts/service.py`, `tests/test_alert_policy.py`, `tests/test_alerts_volume.py`, `wingman/telemetry/coordinator.py`, `tests/test_telemetry_coordinator.py`; create `tests/test_custom_alert_policy.py`.

**Consumes:** Task 6 sealed tuple of valid-source matches, immutable authority, host rank/token contract. **Produces:** one policy call and at most one playback per coordinator batch, all eligible visuals, per-rule cooldown identity.

- [ ] First RED regression uses the retained built-in API, proving the behavior change independently of custom wiring:

```python
def test_one_sound_winner_across_characters():
    from wingman.alerts.service import AlertPolicy
    from wingman.telemetry.coordinator import AlertEvent

    sounds, visuals = [], []
    cfg = {"events": {
        "combat": {"enabled": True, "sound": "system-fault", "color": "#ff4d4d"},
        "warp_scramble": {"enabled": True, "sound": "obey", "color": "#ffd24d"},
    }}
    policy = AlertPolicy(lambda: cfg, lambda sid, vol: sounds.append((sid, vol)),
                         lambda: None,
                         lambda char, kind, spec: visuals.append((char, kind)))
    policy.handle([AlertEvent("Alice", "warp_scramble", "Player"),
                   AlertEvent("Bob", "combat", "Player")], 10.0)
    assert sounds == [("obey", 100)]
    assert visuals == [("Alice", "warp_scramble"), ("Bob", "combat")]
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_alert_policy.py tests/test_custom_alert_policy.py -q`; confirm the sound-count assertion fails against current behavior.
- [ ] Refactor `handle` into eligibility planning, visual delivery and final audible selection. Capture committed configuration and focus once; use severity and deterministic tie keys, never queue/dict insertion order for custom ties. Suppressed custom entries burn no cooldown. Build renderer kind `custom` specs from current authority, add token metadata, and keep PvE filtering restricted to built-ins. Return the existing dispatch summary list shape. Coordinator calls `handle(..., custom_matches=sealed_matches)` once, even when built-in events are empty.
- [ ] Custom cooldown dictionary keys are `(character, rule_id, generation)`; prune deleted/old generations rather than accumulating every historical edit. Implement `forget_custom_character` and call it from coordinator source-retirement handling; extend `FakePolicy` with that explicit method. Source retirement clears that character's custom cooldowns, not other characters or built-ins. Built-in `(character,event)` keys stay unchanged. A visual still consumes cooldown when it loses sound arbitration; otherwise silent losers could flood the next batch.
- [ ] Test cross-character scram versus custom in both input orders; same-line built-in+multiple custom; built-in tie input order; custom tie presentation order then ID (reverse map insertion to prove it); focused timed flash/no sound; sound none/volume zero; global persistence; excluded/closed previews still sound; PvE custom bypass; disabled/no-valid-rule gates; cooldown exact boundary, edit invalidation and unaffected sibling; mutation during eligibility planning and before host admission; stale sound candidate dropped/reselect valid winner before playback. Keep sound replacement across *different* batches unchanged.
- [ ] GREEN/refactor: `uv run --no-sync python -m pytest tests/test_alert_policy.py tests/test_custom_alert_policy.py tests/test_alerts_volume.py tests/test_custom_alert_admission.py tests/test_telemetry_coordinator.py -q`.
- [ ] Commit: `git add wingman/alerts/service.py wingman/telemetry/coordinator.py tests/test_alert_policy.py tests/test_custom_alert_policy.py tests/test_alerts_volume.py tests/test_telemetry_coordinator.py && git commit -m "feat(alerts): arbitrate one sound per telemetry batch"`.

### Task 8: Startup/lazy composition and small bridge facades

**Files:** Modify `wingman/__main__.py`, `wingman/ui/api.py`, `tests/test_alerts_wiring.py`, `tests/test_bridge_contract.py`, `tests/test_settings_committed_preview.py`; create `tests/test_custom_alert_wiring.py`.

**Consumes:** controller, immutable reader, host predicate, stream/coordinator batch path. **Produces:** one shared production controller plus six facades, composed custom health, shutdown fencing and initial/lazy wiring.

- [ ] Use `tests.test_api.make_api` and existing fake host/telemetry seams to write failing facade signature/delegation tests and an actual controller round-trip through Api. Ensure every nonmethod Api attribute is private.
- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alert_wiring.py tests/test_bridge_contract.py -q`.
- [ ] Add optional keyword `alerts_controller=None` to the existing `Api.__init__` signature; when absent, `_build_alerts_controller()` uses named ports resolved against the currently retained host/telemetry. When supplied, retain that instance; do not build a duplicate. Add `build_alerts_controller(state, host, api_box) -> AlertsController` in `__main__.py`, reusing the existing `api_box` composition pattern rather than inventing another registry. Main constructs the committed reader and `api_box`, then PreviewHost, then the controller, policy, telemetry and Api, and finally assigns `api_box["api"]` before any start. Store the controller in `api_box["alerts"]` immediately after its construction; PreviewHost's constructor callback is `lambda rid, gen, epoch: api_box["alerts"].is_current(rid, gen, epoch)`, which is not invoked during construction. Late-bound reader/health ports call the private adapters on `api_box["api"]` only after composition. Extend `build_alert_policy(state, host, alerts_controller=None)` and `build_telemetry(state, host, alert_policy, alerts_controller=None)` compatibly. Main's initial call and lazy `telemetry_factory` pass the **same** controller.

  The six new facade bodies remain one-liners, for example:

```python
def edit_custom_alert(self, rule_id, draft) -> dict:
    return self._alerts_controller.edit(rule_id, draft)
```

  Keep existing built-in endpoint names/results. Change built-in policy config reads and Alerts-enabled telemetry predicates to the committed projection; preserve PreviewHost `runtime_enabled` for roster delivery. `set_alert_enabled` only reconciles after an applied result, never after rollback. The snapshot handles matcher activation on a rule mutation without restarting the stream; do not reconcile for each edit. Reads do not start threads.
- [ ] Add private `_custom_reader_state() -> dict` and `_custom_matcher_health() -> CustomMatcherHealth` adapters on Api for reader health/folder validity and current matcher health. Reuse them in `get_alert_state` and custom state where appropriate without changing legacy return keys. Build `get_alert_state`'s alert configuration/master fields from the committed reader, never from a tentative settings candidate. Use the existing `api_box` for late-bound production ports, assigning its targets before the controller becomes externally callable; no ports run in controller construction. The Api fallback factory binds its own private adapters directly. No additional global registry or mutable rule cache is needed. Fence the controller and custom ingress from `_close_eve_runtime` before native teardown.
- [ ] Test initial build, host absent, telemetry unavailable then lazy retry, shared reader/controller identity, no private tailer, Fleet-only stream still active with empty matcher, successful/failed masters, generation stability on built-in style/volume changes, no stream restart on custom edit, shutdown fencing/deadline/retained owners, old callback rejection, and real API save rollback. Update direct-mutation fixtures only where committed-read semantics require it; do not weaken production assertions.
- [ ] Extend lexical facade guards with exact argument lists and assert no new `WM.HANDLERS` entry or Alerts push. Runtime data continues to be read, not pushed. Run `uv run --no-sync python -m pytest tests/test_custom_alert_wiring.py tests/test_alerts_wiring.py tests/test_bridge_contract.py tests/test_api.py tests/test_settings_committed_preview.py tests/test_fleet_runtime_integration.py -q -rs`.
- [ ] Commit: `git add wingman/__main__.py wingman/ui/api.py tests/test_custom_alert_wiring.py tests/test_alerts_wiring.py tests/test_bridge_contract.py tests/test_settings_committed_preview.py && git commit -m "feat(alerts): wire committed custom runtime and bridge"`.

### Task 9: Dynamic Alerts card with executing Node coverage

**Files:** Modify `wingman/web/alerts.js`, `wingman/web/index.html`, `wingman/web/style.css`, `wingman/web/dev.js`, `tests/test_alerts_wiring.py`, `tests/test_page_conventions.py`, `tests/test_dev_harness.py`; create `scripts/test_alerts_runtime.js`, `tests/test_alerts_runtime.py`.

**Consumes:** six facade contracts/result shapes and existing Settings health polling. **Produces:** add/edit/enable/remove/Test UI, truthful health and acknowledged-draft ownership under real production JS execution.

- [ ] Build the focused Node harness first using `scripts/test_settings_runtime.js`'s deferred `WM.send`, explicit DOM behavior and microtask `turn` pattern. Load actual `alerts.js`; validate required static IDs against actual `index.html` instead of silently inventing every missing element. Support dynamic children, delegated events, focus, disclosure state and controlled intervals; unknown selectors fail loudly. The Python wrapper runs `node scripts/test_alerts_runtime.js` with a timeout and surfaces stdout/stderr. Node availability is mandatory for acceptance.
- [ ] Define harness `page()` with `enter()` (dispatch Settings/Alerts entry), `fire(id, type, extra)` (DOM event), `reply(method, result)` (resolve one deferred bridge promise and flush microtasks), `calls` (pending calls), and `rows()` (read actual rendered custom-row values). Begin with the following executing test; add pre-hydration Edit/Enter attempts once the dynamic editor exists:

```javascript
test('add waits for authority and renders only its acknowledgement', async () => {
  const p = page();
  p.enter();
  p.fire('custom-alert-add', 'click');
  assert.equal(p.calls.filter(c => c.method === 'add_custom_alert').length, 0);
  const state = {revision: 1, rules: [], limit: 8, previews_enabled: false,
    alerts_enabled: false, reader: {running: false, last_error: null,
      characters: [], gamelogs_folder: null},
    matcher: {state: 'inactive', detail: null}};
  await p.reply('get_custom_alert_state', state);
  p.fire('custom-alert-add', 'click');
  assert.equal(p.calls.filter(c => c.method === 'add_custom_alert').length, 1);
  assert.equal(p.rows().length, 0);
  const rule = {id: 'r1', name: 'Custom alert', search: '', enabled: false,
    color: '#ff8c42', sound: 'none', cooldown_s: 8};
  await p.reply('add_custom_alert', {applied: true, persisted: true, error: null,
    rule_id: 'r1', state: Object.assign({}, state, {revision: 2, rules: [rule]})});
  assert.equal(p.rows().length, 1);
  assert.equal(p.rows()[0].enabled, false);
});
```

- [ ] RED: `node scripts/test_alerts_runtime.js`; missing custom DOM/behavior must fail, not be silently skipped by the harness.
- [ ] Add `<section class="card" id="custom-alerts">` after built-in controls, before the Gamelogs folder card. Static IDs: `custom-alert-list`, `custom-alert-add`, `custom-alert-health`, `custom-alert-status`. Dynamic rows use `data-rule-id` and IDs prefixed `custom-alert-<id>-`; editor field suffixes are `name`, `search`, `color`, `sound`, `cooldown`, with named `enabled`, `edit`, `apply`, `cancel`, `test`, `remove` controls. Build user strings with `textContent`/`.value`, not HTML templates.
- [ ] Implement one inline disclosure with named labels, full-row errors and neutral Apply/Cancel/Test controls. Remove uses `.btn.danger` and page-owned `WM.confirm` naming the rule; cancellation does not call Python. Existing approved swatch treatment remains accessible; custom orange and valid out-of-palette colors render without being silently changed. Derive sound options from the existing built-in select, asserted against `settings.VALID_SOUNDS`, rather than another untested list. Derive Add capacity from `state.limit`; configuration remains editable with masters off, no folder or no characters.
- [ ] Introduce custom-only client state: view epoch, read serial/rendered serial, committed revision, per-rule acknowledged object, draft counter, FIFO mutation submissions, and removed-row tombstone/request identity. One in-flight mutation per row; serialize Add admission globally. State reads older than a rendered revision cannot resurrect deleted rows. Older acknowledgments may advance authority but cannot repaint a newer draft or steal focus. Null/rejected writes do not retry Add automatically (uncertain result could create a duplicate); perform an owned fresh read and show a reachability warning. Entry hydration must not overwrite a newer accepted mutation; status polling updates only health. Leave invalidates view ownership and stops timers, never cancels a committed backend mutation.

  The free-text event rule is explicit:

```javascript
nameInput.addEventListener('keydown', function (event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    applyButton.click();
  }
});
```

  Apply and Search Enter submit the complete captured draft. Blur never sends. Discrete colour/sound/cooldown changes submit full edits based on acknowledged text, preserve unsubmitted text drafts, and warn that those drafts still need Apply. Enable uses its dedicated endpoint and cannot enable an invalid committed search. Test submits edited style without changing the acknowledgment baseline.
- [ ] Compose custom health from reader and matcher: masters off → inactive preference note; reader unavailable/error → not watching with reason; no monitored characters → no characters; degraded → explicit custom failure while built-ins/Fleet remain independent; enabled but no invocation → waiting for a new line; healthy invocation → active with monitored names. Fix overall `healthText` so enabled custom rules with all built-ins disabled do not say “nothing can alert”; retain the existing no-events message only when both sets are disabled. Keep health distinct from per-row write failures and avoid repeating master-off notes eight times.
- [ ] Node cases: add up to eight/ninth disabled; empty list; duplicate names and stable-ID operations; edit Enter/Apply/blur; clear-to-disable; enable refusal; style/Test do not submit text drafts; remove confirm/cancel; successful edit then failed edit reverts to latest acknowledgment; typing during old success/refusal; queued edits/toggles; stale hydration after add/remove; reverse-order/null health responses; leaving/reentering during requests; deleted row cannot return; poll cannot overwrite editor; per-row errors independent; failed persistence versus Test's applied/nonpersisted result; two-second poll starts once/stops on section and route exit; literal markup text; orange/out-of-palette options; custom-only health, zero characters and matcher degradation/recovery.
- [ ] Extend dev.js with bounded mutable fake rules and all six methods, using existing sound/colour conventions. Keep fabricated data only there. Add custom card selectors and explicit `[hidden]` handling in scoped CSS; no unreachable floor breakpoint or whole-page redesign. UI checks must include keyboard focus after add/cancel/remove, accessible names despite duplicate display names, visible validation near the owning row, and scrolling eight rows at the floor.
- [ ] GREEN/refactor: `node scripts/test_alerts_runtime.js`; `node scripts/js_smoke.js`; `uv run --no-sync python -m pytest tests/test_alerts_runtime.py tests/test_alerts_wiring.py tests/test_page_conventions.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_js_smoke.py -q -rs`. Keep lexical guards, update only assertions intentionally superseded by custom-aware health.
- [ ] Commit: `git add wingman/web/alerts.js wingman/web/index.html wingman/web/style.css wingman/web/dev.js scripts/test_alerts_runtime.js tests/test_alerts_runtime.py tests/test_alerts_wiring.py tests/test_page_conventions.py tests/test_dev_harness.py && git commit -m "feat(alerts): add dynamic custom alert configuration"`.

### Task 10: End-to-end regressions, polish and acceptance record

**Files:** Create `tests/test_custom_alert_integration.py`; modify `docs/smoke-checklist.md`; create `docs/custom-gamelog-alerts-verification.md`. Update only feature-relevant tests/source if a reproduced regression requires it; each correction gets its own red–green commit.

**Consumes:** production wiring across all previous tasks. **Produces:** deterministic integrated behavior proof, complete verification record and a clearly separated Windows acceptance gate.

- [ ] Write end-to-end tests before declaring completion: real temporary settings and files → real controller/committed reader → GameLogStream → coordinator → policy → fake native/audio boundaries. No mocked parser/matcher/admission in this test. Start from a disabled default, configure/enable through Api, append a marked-up incoming scram matching two custom rules to multiple Listener files, then dispatch. Assert all valid visuals and one scram sound, with source-owner parsing still excluding unrelated built-in recipients.
  Define a local `live_alerts` pytest fixture with the actual runtime components just listed and explicit members `api`, `stream`, `coordinator`, `sounds` (recorded `(sound_id, volume)` tuples), `alice_log` (temporary path), and `now_utc` (the deterministic scan time). It commits Preview and Alerts masters on before constructing the readers, keeps built-in event defaults, starts/baselines the stream and drains startup control events before yielding, and stops coordinator/stream in `finally`. Use the existing no-op thread factories so only explicit scans/dispatches advance this fixture. One integrated stale-admission test is:

```python
def test_removal_invalidates_an_already_admitted_match(live_alerts):
    r = live_alerts
    added = r.api.add_custom_alert()
    rule_id = added["rule_id"]
    draft = dict(added["state"]["rules"][0])
    draft.pop("id")
    draft.update(search="fleet invite", enabled=True, sound="obey")
    assert r.api.edit_custom_alert(rule_id, draft)["applied"]
    with r.alice_log.open("a", encoding="utf-8") as output:
        output.write("(notify) fleet invite\n")
    r.stream.scan_once(r.now_utc)
    assert r.coordinator._custom_pending
    assert r.api.remove_custom_alert(rule_id)["applied"]
    r.coordinator.dispatch_once(0)
    assert r.sounds == []
```

- [ ] RED: `uv run --no-sync python -m pytest tests/test_custom_alert_integration.py -q`. If this integrated path already passes, first add the new interleaving assertion and prove it fails before correcting production code; never force an artificial failure to claim TDD. Correct composition defects only when a genuine failing assertion identifies them.
- [ ] Add blocked-save, matcher exception/recovery, edit/removal while queued, source rotation/truncation, master off→on with Fleet consumer retained, capacity pressure with unrelated Fleet payloads, and shutdown mid-batch traces using Events/barriers rather than sleeps. Capture logs and Fleet outputs and assert a sentinel raw query/matching line never appears. Assert no second stream/worker, no cooldown contamination by Test, and no production-sharing enablement.
- [ ] Run focused integration GREEN, then `polish-core --fix` against the named implementation base. Inspect every polish edit; reject unrelated cleanup. Rerun fresh gates below after the final edit, then use change-explainer for the implementation write-up. Record exact commits, commands, failures/retries, skip reasons and remaining acceptance; do not turn an unrun gate into a checked box.
- [ ] Add the Windows checklist in §7 to `docs/smoke-checklist.md` and record actual results in `docs/custom-gamelog-alerts-verification.md`. If Windows is unavailable, record the gate as open and stop short of release acceptance. Documentation is part of this task, not permission to mark manual checks passed.
- [ ] Commit verified integration tests/docs: `git add tests/test_custom_alert_integration.py docs/smoke-checklist.md docs/custom-gamelog-alerts-verification.md && git commit -m "test(alerts): verify custom alerts across runtime boundaries"`. Commit any earlier regression correction separately with its focused tests. No broad `git add .`.

## 7. Verification commands and Windows acceptance

### Execution setup and final automated gates

Run from the implementation linked worktree. On Linux, a `/tmp` venv/basetemp avoids Windows-mounted-filesystem overhead; retain assignment prefixes rather than using `env`.

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
uv run --no-sync python -m pytest tests/ -q -rs
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node --check wingman/web/alerts.js
node --check wingman/web/dev.js
node scripts/test_alerts_runtime.js
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff --check
```

Inspect all full-suite skips. Node/native-codec skips are not acceptable coverage. Linux Windows-only skips remain explicit, and CI must pass on both Ubuntu and Windows. No dependency or defaults-version bump is expected. Run packaging-completeness/import regression tests with the suite; new files are modules of an existing package, not a reason to change the explicit package list blindly.

### Browser evidence — useful, not native acceptance

Open the actual dev page, exercise zero/eight rules, expanded editor, long/duplicate names, validation/refusal, master-off and degraded states. Check DOM widths and scrollability at 840x625 and 839x621, keyboard flow, visible focus, color contrast and absence of console/resource errors. Record browser/version/viewport separately from Windows. No visual redesign or image-generation exercise is needed for this existing Settings card.

### Final Windows/WebView2 acceptance

Use a real Windows/WebView2 source or installed candidate with isolated test settings and controlled gamelog input. An operator can append synthetic lines to a dedicated local folder; never edit active EVE log files, live character profiles or client geometry to simulate the test. Restore the user's selected folder/settings after the authorized test.

- [ ] At 100%, 125%, 150%, and 200% display scaling, open Settings > Alerts at the actual minimum window size. Check all eight rows, open editor, long/duplicate names, scroll reachability, controls, Add-at-capacity note, no horizontal clipping, and unchanged title-bar drag/close controls.
- [ ] Add/edit via Enter and Apply, leave an uncommitted text draft, change style, Test, navigate away/back, and remove with Cancel/Confirm. Verify no blur write, no stale response overwrite, focus restoration and current acknowledged baseline after a refused write.
- [ ] Select bundled sounds and test volume 0/intermediate/100. Verify actual playback, one sound for several previews, real `winsound` replacement, and scram-versus-custom precedence across two characters in the same controlled batch.
- [ ] Focus the matched EVE client: timed flash without sound or persistence. Focus another client: configured sound/persistence applies. Confirm an excluded/closed preview can still sound without drawing a different client's ring.
- [ ] Verify orange/custom ring rendering, higher built-in severity protection, persistent acknowledgment and timed expiry; test while built-in alerts are queued as well as already armed.
- [ ] Append timestamped marked-up matching lines to each Listener file, including a fleet-broadcast line. Confirm custom attribution to each Listener without claiming built-in ownership of every broadcast target.
- [ ] Confirm no startup/history replay, no partial-line match before newline, known/new source replacement semantics approved in §3.1, and truncation EOF behavior.
- [ ] While lines arrive, commit a changed query, clear it, remove a row, toggle Alerts and Preview off/on, and force a save refusal in isolated settings. Verify old queued generations do not arm and failed edits leave the prior matcher/configuration effective.
- [ ] With only Fleet Bar keeping telemetry active, prove custom controls report inactive and no custom sounds occur; re-enable alerts without restarting a second reader. Exercise missing folder/no characters and injected matcher-degraded/recovery state; reader/Fleet health stays independent.
- [ ] Exit during queued custom work and a pending edit. Confirm no post-close custom sound/ring, no hanging process and no replacement native owner after a timeout. No EVE client moved/resized and no gameplay input sent.

## 8. Coverage self-review and adaptation points

| Approved design requirement | Implementation / verification |
| --- | --- |
| Settings-only, eight rules, all monitored characters, bundled sound, stable IDs/defaults | Tasks 1–3, 8–9; Windows layout/playback |
| Timestamp/markup/whitespace normalization, literal Unicode folding, 3–200 lengths/controls | Task 1; Task 5 real-source fixtures |
| Newly observed complete lines, history/rotation/truncation compatibility | Task 5; integration and Windows replay checks; §3.1 approval |
| Immutable committed snapshot, off-state zero match work, no stream restart | Tasks 1–2, 5, 8; blocked-save and Fleet-only tests |
| Bounded custom admission/coalescing, one sentinel, no unrelated drop | Tasks 5–6; blocked drainer/admission and capacity tests |
| Priority-aware host admission, unique lowest visual rank | Task 4; ring/capacity tests and Windows rendering |
| One process-wide audible winner per coordinator batch | Tasks 6–7; paired-line interleaving and multi-character sound tests |
| Independent matcher degraded/recovery health | Tasks 5, 8–9; stale-outcome/no-invocation tests |
| Stale rule/activation/source generations, cooldown edit identity | Tasks 2, 4–8; blocked-save, cutoff, host and shutdown races |
| Focus, timed/persistent rings, excluded/closed preview sound, PvE bypass | Tasks 4, 7–8; Windows focus/preview checks |
| Per-entry malformed isolation, no defaults-version bump, settings rollback | Tasks 1–3; existing settings transaction/committed-reader regressions |
| Atomic edit, presentation-only Test, small controller facades | Tasks 3, 8; exact API shape/delegation tests |
| Dynamic UI, no early/blur write, stale acknowledgments, accessibility | Task 9 Node harness and lexical/smoke gates; browser and WebView2 |
| No raw match text in shared projections/logs/diagnostics | Tasks 5–6, 10; captured output tests |
| Real Windows/WebView2 acceptance | Task 10 / §7; not replaced by Linux/Node/browser evidence |

**Self-review checklist for the executor:** confirm exact interface names across tasks; frozen projections contain no mutable public members; all code/test snippets use defined types or explicitly introduced fixtures; do not add another controller cache or a second stream subscriber in production; confirm custom staging is bounded both before and after coordinator ingress; maintain shutdown fences and token checks after admission; compare the final diff against the explicit exclusions.

**Adaptation triggers:** changed source lifecycle/cursor semantics; changed settings publication mechanism; changed runtime construction/shutdown ownership; changed native alert payload contract; a real marked-up log shape contradicting normalization; rejection of either §3.1 interpretation. Stop and revise the specific affected contract/test before implementation, rather than silently weakening the requirement. Performance tests use bounded counts and deterministic synchronization, not machine-specific millisecond assertions; measure native latency separately.

**Explicit exclusions:** regex/wildcards/fuzzy/case toggles, per-character scope, user-selected sound files, import/export/rule packs, matched-line/history display, broadcast deduplication, built-in parser changes, new gamelog reader, generic queue redesign, companion previews, Wanderer overlays, unrelated Alerts/built-in UI refactoring, live fleet-sharing activation, broad settings migrations, and a release/version bump.

## 9. Planning-session verification (not feature acceptance)

Before writing this plan, the planning worktree was clean at the source baseline above. The supplied design file's hash matched the commit blob, and git history confirmed it is not merged into main. Project guidance, the full approved design, scoped source/tests and one structured read-only runtime blindspot pass were inspected.

Commands actually run from the planning worktree:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv sync --locked --extra dev
node --version
UV_PROJECT_ENVIRONMENT=/tmp/wingman-custom-alerts-plan-venv uv run --no-sync python -m pytest tests/test_alert_policy.py tests/test_alerts_patterns.py tests/test_alerts_state.py tests/test_alerts_wiring.py tests/test_alerts_volume.py tests/test_settings_alerts.py tests/test_settings_committed_preview.py tests/test_telemetry_gamelogs.py tests/test_telemetry_coordinator.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_js_smoke.py tests/test_settings_runtime.py -q -rs --basetemp=/tmp/wingman-custom-alerts-plan-baseline
```

Result: locked sync succeeded, Node **v26.5.0**, **577 passed in 23.65s, no skips**. These are existing-code baseline tests, not tests of the unimplemented feature. The full suite, native-codec build, new tests, browser rendering and Windows/WebView2 acceptance were not run in this documentation-only planning session.

Planning-author self-review completed against the entire approved spec: the coverage matrix accounts for each requirement; interface names, tokens, callback/result shapes and task dependencies were reconciled; the custom-only shutdown gate was checked not to drop semantic traffic; and no implementation or unrelated design file is staged. The two §3.1 interpretation choices remain for user review, not silently resolved facts.

Document checks performed: ten ordered tasks, balanced Markdown fences, no unfinished-marker phrases, **57 repository path references** verified against existing files/the design commit or **13 explicitly planned new files**, **16 Python code blocks** parsed with `ast.parse`, **2 JavaScript blocks** accepted by `node --check -`, and `git diff --cached --check` passed. Snippet syntax checks are not execution or type-checking of the unimplemented feature.
