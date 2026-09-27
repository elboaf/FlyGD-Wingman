# Persistent page workers — Stage B design

## Status

Approved for implementation, not yet implemented. This document records the
bounded Stage B design and the disposable feasibility evidence used to qualify
it. The implementation remains a later, separately reviewed change.

Stage B changes test architecture only. It replaces 165 one-shot Node launches
in four Python test files with four family-local, session-scoped workers and
builds one real saved-layout receipt for 55 existing page cases. It preserves
all 205 existing identities in those files, their parameters, markers,
assertions, scenario matrices, timeouts, and business behavior. Exactly seven
Stage B qualification identities and one narrowly scoped
`NodeScenarioWorker` contract identity are added. There is no production,
workflow, dependency, configuration, packaging, cadence, or Stage C change.

### External versioning authorization

The user explicitly approved all 165 Node-owning cases, the bounded helper
hardening in `tests/node_scenario_worker.py` and
`tests/test_node_scenario_worker.py`, and the resulting 17-path scope. The user
also authorized versioning this Stage B specification plus the future Stage B
implementation plan, results ledger, and evidence updates. This section records
that external authorization; the document does not grant, extend, or substitute
for permission. No local scratch probe, generated report, review note, or other
Superpowers artifact is included by that authorization. No push is authorized by
this design.

`PRODUCT.md` and `DESIGN.md` do not govern this tranche because no product
behavior or rendered screen changes. The existing tests, fixture programs,
persistent-worker contracts, production APIs used to create receipts, and
accepted Stage A evidence are the authorities.

## Decision

Implement four independent persistent page-worker families:

1. saved-layout page behavior, including its main, displayed-owner, capture, and
   dev programs;
2. Fleet Sharing hydration and control behavior;
3. Preview group-backward behavior; and
4. Preview label-marker behavior.

Each family owns one session-scoped `NodeScenarioWorker` process for the whole
pytest session, including when an explicit execution order leaves and later
re-enters its defining module. The common process implementation is one new
hardened CommonJS worker. Every request gets a new VM-owned realm, production
script execution, DOM, intrinsics, promises, errors, callbacks, listeners, and
virtual timers. A process may cache only primitive source and markup text.
There is no reusable page object, VM context, parsed payload, result object,
callback, timer handle, promise, error, or assertion object.

The 55 `test_saved_layout_page_ordering` rows consume one real production
receipt built once through the existing Api/controller/store/settings/atomicio
sequence. The receipt is detached to strict UTF-8 JSON before its temporary
environment and patches are restored, then freshly decoded for every request.
The other seven saved-family cases continue to build their own source-specific
real receipts because they exercise different production paths.

The existing `tests/node_scenario_worker.py` lifecycle remains the owner of
serialization, timeout, discard, restart, close, and late-exit behavior. Its
reply validator is deliberately hardened: `id` must have exact Python type
`int` (therefore not `bool`), and `duration_ms` must have exact type `int` or
`float` (therefore not `bool`), be finite, and be greater than or equal to zero.
Any violation follows the existing invalid-schema discard path. The existing
`tests/fixtures/screenshot_dom.cjs` is unchanged. A protocol or process failure
discards the process and fails the current request without retry; the next
request may start a clean process. A well-formed business failure returns a
detached stack, fails the current test, and leaves the process healthy. Expected
negative product outcomes remain successful test scenarios, not worker
failures.

Acceptance is structural and behavioral: exact identity preservation, exact
scenario coverage, fresh-realm isolation, deterministic cleanup and recovery,
one process per family on a healthy 165-case run, exact receipt and fsync
counts, and order independence. Hosted durations are observations only. This
design makes no speedup, critical-path, job-time, or runner-efficiency claim.

## Authority and frozen baseline

### Source baseline

The implementation baseline is merged `main` commit
`203d2068787cb3457916db6005afda0a7ce7a43a` (`Remove deterministic waste from
Windows CI tests (#291)`). The worktree branch is
`ci-persistent-page-workers-stage-b` and was clean when this design was written.

Relevant authorities inspected are:

- `AGENTS.md`;
- the Stage A design, implementation plan, local results, and accepted hosted
  audit;
- the persistent screenshot-worker design, plan, and results;
- `tests/node_scenario_worker.py` and `tests/test_node_scenario_worker.py`,
  including all 12 currently collected helper identities;
- `tests/fixtures/current_screenshot_pages.cjs`,
  `tests/fixtures/screenshot_pages.cjs`, and
  `tests/fixtures/screenshot_dom.cjs`;
- the four target Python modules and six target CommonJS programs listed below;
- `wingman/ui/api.py`, `wingman/settings.py`, `wingman/atomicio.py`, and the
  Preview saved-layout controller/store/model code used by the real receipt;
- `tests/test_api.py`, `tests/test_preview_owner_eligibility.py`, and Fleet
  Sharing fixture helpers; and
- `wingman/web/app.js`, `previews.js`, `panel.js`, `fleetsharing.js`, and
  `dev.js` as executed by the current programs.

The target files are byte-unchanged between accepted Stage A reviewed head
`3c3fe622f2a178805f4267d90d12aff61293b6d7` and this merged baseline. Their
baseline SHA-256 values are:

| Path | SHA-256 |
|---|---|
| `tests/test_preview_savedlayouts_page.py` | `489c462588d174b56c1e774134adfaee366febfa21986a80f14b8fdbd49a7e2a` |
| `tests/test_fleetsharing_hydration.py` | `fc9517f0736b111cb7018bc8159a8c5597397d73bfec0dc9944ae2316e5db7a1` |
| `tests/test_preview_group_backward.py` | `4f1462a2ff1b0f2b41b5af232e6c2346d390fed5273241b991c7c73c43b6bc21` |
| `tests/test_preview_labelmarkers_page.py` | `cddf1093392468c6ff2dff1d5eaddd7f0e2b62d34e4828351b3500e54ae3c5e9` |
| `tests/fixtures/preview_savedlayouts.cjs` | `93e9f31b3cc8a6e4b118da5b487f4a75ca5bf5fdfa5212b9afc990f280a6ad60` |
| `tests/fixtures/preview_capture_sessions.cjs` | `80b386e8ec40cbc186a2778930c8f512dc452e52b1ed1028d9aecc02e70d74e0` |
| `tests/fixtures/preview_dev_capture.cjs` | `f972042bcf5d20ffc25dbd215497ea3cf07708122de9a3be68fc160f46ca931b` |
| `tests/fixtures/fleetsharing_page.cjs` | `b0b7571375a9418ab385f307b2577b8958c7c05fb0b5567ff0887f28fc110374` |
| `tests/fixtures/preview_group_backward.cjs` | `c082be0f70d53d0d0897a510b5787e7170cf7516a7dcfcb8620bf73c8b6cd4c4` |
| `tests/fixtures/preview_labelmarkers.cjs` | `0454164b2947e2f2064c5415b071dd7c1991be8c10db01aec0c234d9ca8430dd` |
| `tests/node_scenario_worker.py` | `bfd4930fe1f9d1ce6f91ddd8f4bfef527211fcca4b7156a77e13e9d98a099790` |
| `tests/test_node_scenario_worker.py` | `dc8a2e9966f39efe5da2fee32e6af7072a925ca4ec624da50865e5139fa62aee` |
| `tests/fixtures/screenshot_dom.cjs` | `c25e99234bb1e9856d8aa2d8c6cb910f1b68a55eb0c0a528508ab4a7c4eb5a8d` |

### Accepted Stage A hosted observation

The accepted evidence is PR #291 workflow run `36258907685`, attempt `1`, under
`/mnt/c/dev/flygd-wingman/tmp/stage-a-hosted-36258907685`. Its hosted audit is
PASS for reviewed head `3c3fe622f2a178805f4267d90d12aff61293b6d7`, frozen executable head
`83bd018b6eeb29e159741258e8d979c7481d7d01`, and synthetic checkout
`5e9adb83e8ac175756b987da25eeec657c4d1a4d`.

Both platforms contain 16,609 unique ordered identities with final-newline hash
`f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
Ubuntu is 16,595 passed plus 14 skipped; Windows is 16,542 passed plus 67
skipped. There are no failures, errors, Node skips, codec skips, or unexpected
native-availability skips.

The Stage B target observations are additive JUnit testcase sums, not wall
clock and not causal evidence:

| Platform | Four complete files / 205 | Node-owning rows / 165 |
|---|---:|---:|
| Ubuntu | `20.521s` | `20.454s` |
| Windows | `62.945s` | `62.674s` |

Per-file observations are:

| File | Existing IDs | Node IDs | Ubuntu all / Node | Windows all / Node |
|---|---:|---:|---:|---:|
| saved layouts | 62 | 62 | `6.353s / 6.353s` | `31.472s / 31.472s` |
| Fleet Sharing | 66 | 65 | `3.829s / 3.828s` | `10.194s / 10.191s` |
| group backward | 56 | 17 | `8.050s / 7.984s` | `16.603s / 16.335s` |
| label markers | 21 | 21 | `2.289s / 2.289s` | `4.676s / 4.676s` |

No difference between these values and any future candidate value may be called
a speedup or attributed to Stage B from one hosted sample.

### Frozen target inventory

The four files currently collect exactly 205 unique IDs when selected in this
order: saved layouts, Fleet Sharing, group backward, then label markers. Their
ordered final-newline SHA-256 is
`7337d36844ca94b21a0af2c4568ede5828f81df882d2899ca28aa9a505b69343`.
Exactly 165 own a Node launch; their ordered final-newline SHA-256 under that
same file order is
`60a253410671d0ac475c414940f007943ff96f4faebc30f0f1aaef9009e549fc`.
The other 40 IDs remain byte-for-behavior untouched by Stage B.

The 165 mappings are exact.

#### Saved-layout family — 62

`test_saved_layout_page_ordering` retains these 55 parameters, in this order,
and maps them to program `preview_savedlayouts.cjs`, protocol `saved-main`:

```text
reversed
bulk
keybind
retry
draft
early
named
staging
staging-roundtrip
copy-dialog-navigation
copy-dialog-subpage
copy-dialog-staging
copy-dialog-configure
copy-dialog-attempt
copy-dialog-capture
copy-admitted-subpage
copy-detail-fit
copy-detail-truncated
copy-detail-clipped
copy-detail-legacy
copy-detail-unmeasurable
copy-detail-resize
copy-detail-typography
copy-detail-default
dialog-focus-history
dialog-owned-cancel
geometry-detail-focus
geometry-detail-dialog
geometry-ack
geometry-getter
geometry-keybind
geometry-staging
geometry-dialog-navigation
geometry-dialog-capture
controls-empty
controls-select
controls-save
controls-apply
controls-update
controls-rename
controls-remove
controls-cancel
controls-errors
controls-pending
controls-staging
controls-capture
controls-busy
row-feedback
row-rejected
controls-unhydrated
controls-unavailable
controls-failed-save
controls-incomplete
controls-reopen
controls-staged-receipt
```

`test_displayed_owner_controls_use_real_api_receipts` retains `saved`,
`retained`, and `excluded`; all three map to program
`preview_savedlayouts.cjs`, protocol `saved-owner`, while retaining the
program's business scenario `owner-controls`.

`test_capture_session_page_ordering` retains:

| Parameter | Program | Protocol |
|---|---|---|
| `reversed` | `preview_capture_sessions.cjs` | `saved-capture` |
| `local` | `preview_capture_sessions.cjs` | `saved-capture` |
| `boundary` | `preview_capture_sessions.cjs` | `saved-capture` |
| `dev` | `preview_dev_capture.cjs` | `saved-dev` |

#### Fleet Sharing family — 65

`test_sharing_watch_runtime` retains these parameters, in this order, all
mapped to `fleetsharing_page.cjs`, protocol `fleet-sharing`:

```text
missing-worker
null
error-no-state
reject
leave
reenter
newer-push
stale-state
failed-refresh-during-on
rejected-admission
scope-copy
overview-unknown
overview-pairing
overview-preference
overview-verification
overview-read-fences
pending-worklists
eligibility-readiness
verification-scope
mixed-history
ended-only
ended-prerequisites
pending-precedence
local-results
retained-unknown
failed-refresh-history
binding-invalidation
inflight-stop
bridge-source-rejection
inflight-start-leave
inflight-binding-reply
stable-history-focus
visibility-ownership
retained-local-result
concurrent-stop-replies
inflight-reenter
stale-preference-after-failed-refresh
equal-preference-after-failed-refresh
boss-selection-across-unknown
replace-stop-original
replace-stop-route
control-capture-on-generation
control-capture-on-queued
control-capture-stop-generation
control-capture-stop-automatic
control-capture-stop-pending
control-dialog-binding
control-dialog-route
control-dialog-screenshot
control-dialog-off
control-dialog-on-route
control-dialog-on-binding
control-missing-authority
dev-control-authority
control-setup-combat
control-setup-automatic
control-setup-stale
control-setup-route
control-setup-off-overtakes
control-legacy-empty
control-preference-feedback-pushes
control-preference-feedback-retry
control-preference-feedback-off
control-preference-feedback-binding
control-preference-feedback-screenshot
```

The file's one non-Node capacity-helper identity remains unchanged.

#### Group-backward family — 17

`test_group_backward_page` retains these parameters, in this order, all mapped
to `preview_group_backward.cjs`, protocol `group-backward`:

```text
dev
rows
conflicts
writes
stale
cancel
marker
focus-clearance
focus-draft
focus-lifecycle
focus-ownership
focus-stable
focus-own-dialog
focus-dialog-owners
focus-fixture-draft
focus-fixture-unhydrated
focus-crop-direction
```

The file's other 39 pure Python/API identities remain unchanged.

#### Label-marker family — 21

`test_marker_page_ownership` retains these parameters, in this order, all mapped
to `preview_labelmarkers.cjs`, protocol `label-markers`:

```text
hydration
receipts
owners
retention
exclusions
refresh
navigation
screenshot
copy
reset-copy
reset-draft
reset-headings
reset-headings-off
reset-capture
reset-owner-capture
capture-entry-pointer
capture-entry-focus
capture-entry-pointer-deferred
capture-entry-focus-deferred
capture-entry-before-arm
screenshot-deferred
```

## Stage B invariants

Every implementation decision is subordinate to these invariants:

1. all 205 existing IDs remain unique, ordered, named, parameterized, marked,
   and behaviorally equivalent; their frozen ordered hash remains exact;
2. the 165 Node-owning IDs retain the exact mappings above and their frozen
   ordered hash;
3. exactly seven Stage B qualification IDs and the one exact helper-contract ID
   named below are added, producing 16,617 complete-suite outcomes from the
   accepted 16,609 baseline;
4. a healthy 165-case target run starts exactly four Node processes, one per
   family, from the current 165 one-shot launches;
5. the four request timeouts remain saved `25s`, Fleet Sharing `20s`, group
   backward `30s`, and label markers `30s`;
6. each request executes in a newly created VM realm and re-executes its family
   program and production web source; only primitive source/markup text may be
   cached across requests;
7. no host constructor, promise, error, callback, DOM object, timer handle, or
   mutable result/input object is reachable from request code;
8. every request completes cleanup before a reply is published; timeout or
   protocol failure destroys the entire process;
9. business failure does not poison or restart the process, while protocol
   failure is never retried for the current test;
10. expected product rejection/error scenarios remain passing business tests;
11. one real saved-layout receipt supplies exactly the 55 main cases, is
   detached before exposure, and retains every current production operation,
   ID, revision, acknowledgement, warning, and pending-state observation;
12. the healthy 165 Node-owning baseline/candidate fsync count is exactly
    `1,059 -> 33`, while the complete 205-case baseline/candidate count is
    exactly `1,088 -> 62`; the shared receipt contributes 19 of the candidate
    calls, and qualification overhead is observed and reported separately;
13. `NodeScenarioWorker` changes only at the approved numeric reply-validation
    boundary; its lifecycle contract and `screenshot_dom.cjs` remain unchanged;
14. an active request owns rejection capture through its realm, never retains a
    raw reason or promise, and cannot publish success before its rejection and
    timer-dispatch boundary is drained;
15. one-shot invocation of every existing CJS program remains supported with
    the same argv order, exit behavior, exact PASS text, and diagnostics;
16. no production, web, workflow, dependency, lockfile, configuration,
    packaging, cadence, marker, timeout, or Stage C behavior changes;
17. Node and the release settings codec remain mandatory full-suite
    prerequisites; no new skip masks missing prerequisites; and
18. timing evidence remains observational and is not an acceptance threshold.

## Worker topology and lifecycle

### Four family-local session fixtures

Each target Python module defines one `scope="session"` fixture:

| Fixture | Defining module | Family argument | Manifest pages |
|---|---|---|---|
| `saved_layout_page_worker` | `test_preview_savedlayouts_page.py` | `saved-layouts` | `text`, `structural` |
| `fleetsharing_page_worker` | `test_fleetsharing_hydration.py` | `fleet-sharing` | `sharing` |
| `group_backward_page_worker` | `test_preview_group_backward.py` | `group-backward` | `structural` |
| `labelmarkers_page_worker` | `test_preview_labelmarkers_page.py` | `label-markers` | `structural` |

A session fixture defined in a test module remains alive until session teardown,
not until pytest first leaves that module. Therefore an explicitly interleaved
cross-module run may leave and re-enter a module without constructing a second
family process. Each fixture closes its worker in `finally`. Direct selection of
one case constructs only its family and closes it. Missing Node fails as a
missing prerequisite; it does not create a new skip.

The process command is:

```text
node tests/fixtures/page_scenario_worker.cjs --worker FAMILY WEB_ROOT MANIFEST_PATH
```

The manifest is generated once with `tmp_path_factory`, encoded UTF-8 with
`allow_nan=False`, and contains only versioned JSON markup trees. The worker
reads it and relevant source files at startup as primitive text. It never caches
a parsed page.

Family source caches are exact unions of existing reads:

| Family | Programs | Production JS text |
|---|---|---|
| saved layouts | saved layouts, capture sessions, dev capture | `app.js`, `previews.js`, `fleetsharing.js`, `panel.js`, `dev.js` |
| Fleet Sharing | Fleet Sharing page | `app.js`, `fleetsharing.js`, `dev.js` |
| group backward | group backward | `app.js`, `previews.js`, `panel.js`, `dev.js` |
| label markers | label markers | `app.js`, `previews.js`, `panel.js` |

The worker also copies `DOM_FACTORY_SOURCE` from `screenshot_dom.cjs` as a
primitive string where needed, then releases the host module object. The Fleet
Sharing program retains its specialized DOM semantics, but those classes are
constructed inside each request VM rather than the worker host.

### Program extraction and one-shot compatibility

Each of the six existing CJS files is split internally into:

- a primitive `PROGRAM_SOURCE` string containing its request-realm entry;
- a guarded current CLI path; and
- no persistent host object or callback export.

The persistent worker copies only the primitive source string and drops the
transient module export and `require.cache` entry. It does not invoke a
host-realm fixture function. The CLI guard delegates one input to the same
hardened single-request runner and renders its detached output/diagnostics to
the current streams.

These existing forms remain exact:

```text
preview_savedlayouts.cjs DATA WEB_ROOT
preview_capture_sessions.cjs DATA WEB_ROOT
preview_dev_capture.cjs DATA WEB_ROOT
fleetsharing_page.cjs DATA SCENARIO WEB_ROOT
preview_group_backward.cjs DATA WEB_ROOT
preview_labelmarkers.cjs DATA WEB_ROOT
```

A one-shot business failure sets a nonzero exit and emits its detached stack as
before. Successful one-shot stdout and stderr are exact, not merely substring
compatible:

| Adapter | Exact terminal stdout line |
|---|---|
| `saved-main` | `PASS <scenario>` |
| `saved-owner` | `PASS owner-controls` |
| `saved-capture` | `PASS <scenario>` |
| `saved-dev` | `PASS dev` |
| `fleet-sharing` | `PASS <scenario>` |
| `group-backward` | `PASS group backward <scenario>` |
| `label-markers` | `PASS marker page <scenario>` |

Except for the two dev cases below, successful one-shot programs emit exactly
that one stdout line. Their stderr is empty; Fleet Sharing's controlled bridge
errors remain captured assertions and do not leak to stderr. Worker mode prints
no diagnostic text to stdout because every stdout line is NDJSON. Its detached
`output` field is exactly the terminal line from this table, without a trailing
newline; PASS is not duplicated into `diagnostics`.

### Existing Python worker contract

`NodeScenarioWorker` already supplies the required serialized request lock,
monotonic IDs, lazy startup, UTF-8 line transport, reply/schema/ID/scenario
validation, bounded stderr tail, request timeout, process discard, terminate to
kill escalation, reader joins, late-exit attribution, and idempotent close.
Stage B uses those contracts rather than copying them. The sole helper change is
inside `_validate_reply`: use `type(value) is int` for `id`; for
`duration_ms`, require `type(value) in (int, float)` and `value >= 0`, then apply
`math.isfinite(value)` when its exact type is `float`. This rejects Python's
`bool` subclassing and its permissive `json.loads` acceptance of
`NaN`/`Infinity` without coercing arbitrarily large integers to float; every
other helper lifecycle branch is byte-for-behavior unchanged.

In particular:

- malformed JSON/schema, wrong ID/scenario, EOF, write failure, timeout, and
  process death discard the process and raise `NodeScenarioCrash` or
  `NodeScenarioTimeout`;
- the failed request is not replayed;
- a later request starts a new process only after the failure has been surfaced;
- a valid `ok:false` reply raises `NodeScenarioFailure` with detached stack and
  reply while retaining the process;
- an exit after a successful reply is attributed to that successful request at
  the next request or close, not silently replaced; and
- stderr remains bounded to 40 lines of at most 400 characters.

No other change to this class is anticipated. If Stage B needs a different
lifecycle, that is a design conflict and stop condition, not permission to
broaden the approved validator edit.

## NDJSON protocol

Transport is primitive NDJSON only. Here “primitive” means a finite, detached
JSON value tree—objects and arrays composed solely of null, booleans, finite
numbers, strings, arrays, and string-keyed objects—not a live Python or
JavaScript object identity.

### Startup

Worker startup accepts no NDJSON command and emits no readiness line. Reader
threads becoming live is the existing Python startup boundary. Before reading
stdin, the process validates the family argument against exactly
`saved-layouts`, `fleet-sharing`, `group-backward`, and `label-markers`, reads
the manifest/source bytes, and stores only immutable primitive strings. An
unknown/missing family, malformed manifest, unreadable source, or other startup
error emits no stdout reply, writes bounded context to stderr, closes stdin
service, and exits nonzero; the first request receives the existing crash
classification.

### Request

Python sends the existing `NodeScenarioWorker` envelope:

```json
{"id":1,"scenario":"preview-saved-layouts/page/reversed","payload":{"protocol":"saved-main","input":{}}}
```

The exact labels are:

```text
preview-saved-layouts/page/<scenario>
preview-saved-layouts/owners/<source>
preview-saved-layouts/capture/<scenario>
preview-saved-layouts/dev/dev
fleet-sharing/page/<scenario>
preview-group-backward/page/<scenario>
preview-label-markers/page/<scenario>
```

Labels are globally unambiguous even where business parameters repeat, such as
saved `reversed` and capture `reversed`. `payload.protocol` must be one of the
family's declared adapters. `payload.input` contains JSON values only. Paths,
functions, Python objects, nonfinite numbers, and host handles are forbidden.
The request envelope has exactly the keys `id`, `scenario`, and `payload`;
`id` is a positive safe integer, `scenario` is a nonempty string matching one of
the frozen labels for the startup family, and `payload` is an object with exactly
`protocol` and `input`. `protocol` is the adapter assigned to that label and
`input` is an object containing finite JSON only. Malformed NDJSON, an invalid
envelope or payload schema, a label from the wrong family, unknown protocol, or
unknown scenario is a fatal protocol error: emit no valid reply, write bounded
context to stderr, close the process, and let `NodeScenarioWorker` discard it.
There is no fallback to another program. By contrast, a recognized scenario with
a structurally valid but semantically invalid business input executes its
adapter, returns a detached `ok:false` business payload, and leaves the process
retainable. Qualification pins both sides of this boundary.

The Node host parses the line only to validate primitive envelope fields and
select the primitive program source. It immediately reserializes the payload to
text with finite-JSON enforcement. The parsed host object is never assigned into
a VM. The VM freshly parses that text and the startup manifest text.

### Reply

Every healthy request emits exactly one line:

```json
{
  "id": 1,
  "scenario": "preview-saved-layouts/page/reversed",
  "ok": true,
  "duration_ms": 12.5,
  "output": "PASS reversed",
  "error": "",
  "stack": "",
  "diagnostics": [],
  "cleanup": {
    "host_timer_handles": 0,
    "host_callbacks": 0,
    "active_rejection_listeners": 0,
    "pending_rejection_records": 0,
    "retained_realms": 0
  }
}
```

`id`, `scenario`, `ok`, `duration_ms`, `error`, and `stack` retain the existing
required schema. `id` is an exact integer, never a boolean. `duration_ms` is an
exact integer or float, never a boolean, finite, and nonnegative. The Python
helper applies those checks before ID/scenario matching; any invalid reply schema
discards the process. `output`, `diagnostics`, and `cleanup` are additive fields.
`duration_ms` is worker observation only and has no test threshold.

A business failure has `ok:false`, empty output, a defensively detached error
message and stack, detached diagnostics, and the same zero cleanup receipt. The
worker remains available. A cleanup failure, double completion, serializer
failure, or inability to prove detachment is a protocol failure: do not emit a
success reply and do not continue serving.

### Diagnostics

VM-local `console.log/info/debug/warn/error` records detached diagnostic entries
with level, rendered text, and safely serialized primitive arguments. A
successful expected diagnostic is not a global failure. In worker mode these
records stay inside the reply; in one-shot mode they are rendered to the same
stdout/stderr roles as today.

Preserve these observed contracts exactly. Saved-layout dev stdout is this
ordered sequence before its terminal `PASS dev`:

```text
DEV api.get_preview_hotkey_state()
DEV api.get_preview_hotkey_state()
DEV api.list_rows()
DEV api.get_settings()
DEV api.theme_state()
DEV api.set_bind_capture(true)
DEV api.set_bind_capture(false)
DEV api.get_preview_hotkey_state()
DEV api.set_bind_capture(true)
DEV api.set_bind_capture(false)
DEV api.set_bind_capture(true)
DEV api.set_bind_capture(true)
DEV api.set_bind_capture(false)
DEV api.set_bind_capture(false)
DEV api.set_bind_capture(false)
DEV api.get_preview_hotkey_state()
DEV api.set_bind_capture(false)
DEV api.set_bind_capture(true)
DEV api.get_settings()
DEV api.get_preview_hotkey_state()
DEV api.get_preview_hotkey_state()
```

It also makes exactly one stderr/diagnostic `error` call whose rendered first
line begins `onTheme handler failed TypeError: Cannot read properties of
undefined (reading 'apply')` and whose detached third argument is the theme
payload.

Group-backward dev stdout is this ordered sequence, where `<id>` is one generated
ID equal across all three appearances, before its terminal
`PASS group backward dev`:

```text
DEV api.create_preview_cycle_group( Backward test )
DEV api.set_preview_cycle_group_bind( <id> Ctrl+F2 )
DEV api.set_preview_cycle_group_prev_bind( <id> Ctrl+F3 )
DEV api.set_preview_cycle_group_prev_bind( stale Ctrl+F4 )
DEV api.set_preview_cycle_group_prev_bind( <id>  )
```

Its stderr is empty.

- Fleet Sharing `reject` retains exactly one `error` diagnostic with rendered
  prefix `bridge: fleet_sharing_watch failed` and message
  `controlled bridge failure`;
- Fleet Sharing `bridge-source-rejection` retains exactly two `error`
  diagnostics, in order, with rendered prefixes
  `bridge: fleet_sharing_start_source failed` and
  `bridge: fleet_sharing_stop_source failed`, and messages
  `controlled Start failure` and `controlled Stop failure`; and
- every other Fleet Sharing scenario retains zero controlled bridge errors.
- Fleet Sharing `reject` retains exactly one `error` diagnostic with rendered
  prefix `bridge: fleet_sharing_watch failed` and message
  `controlled bridge failure`;
- Fleet Sharing `bridge-source-rejection` retains exactly two `error`
  diagnostics, in order, with rendered prefixes
  `bridge: fleet_sharing_start_source failed` and
  `bridge: fleet_sharing_stop_source failed`, and messages
  `controlled Start failure` and `controlled Stop failure`; and
- every other Fleet Sharing scenario retains zero controlled bridge errors.

The worker diagnostics preserve level, order, rendered text, and detached
primitive arguments. One-shot rendering preserves the existing stdout/stderr
split. Stacks and generated dev IDs may contain platform/Node-specific values;
acceptance pins the counts, relations, exact stable prefixes/methods/messages,
and terminal PASS strings, not incidental stack locations or generated digits.

## Fresh request realm

### No host-realm execution

For every line the worker creates `vm.createContext(Object.create(null))`. Only
primitive source, payload, manifest, family, and protocol strings enter the
context. The bootstrap captures VM-owned pristine intrinsics, deletes the seed
properties, constructs all helpers in the VM, parses input there, constructs a
new DOM there, and indirectly evaluates the selected family and production
sources there.

Request code receives no `require`, `process`, `module`, `exports`, `Buffer`,
host `Promise`, host `Error`, Node assert object, host DOM instance, host
function, or native timer. Assertions, `CustomEvent`, `URLSearchParams`, console,
and the fixture-specific DOM are VM-owned implementations. Production scripts
execute in that same fresh realm; there is no nested host-created page context.

The initial VM bootstrap returns one VM-owned poll function to the host. The
host calls it only with a primitive monotonic timestamp and primitive JSON for
pending rejection/dispatch records, and receives only `null` or a primitive JSON
string. The VM poll parses that mailbox and owns the final query; the poll
function is never injected back into the VM global, so request code cannot
enumerate or call a host completion bridge. No host callback is exposed to the
VM.

### Timers and asynchronous completion

VM-local `setTimeout`, `setInterval`, `setImmediate`, and clear functions retain
VM callbacks and primitive due times in a request-local scheduler. The host
polls/drains that scheduler at event-loop turns; it never receives a VM callback
or gives the VM a native handle. This preserves the real microtask-before-next-
turn behavior required by Fleet Sharing and the existing `tick` helpers without
sharing host timers.

The async request body writes its result into lexical VM state and uses
`async`/`await`, not mutable `Promise.prototype.then`, for finalization. After the
selected program settles it drains VM microtasks and one request-owned zero-delay
timer turn, then queries already-primitive unhandled-rejection and timer-dispatch
failure records. That query occurs before a primitive success completion can be
published. The host poll sees completion only after:

1. the selected program settles;
2. the microtask/request-timer rejection boundary is drained and queried;
3. diagnostics and error/reason are detached;
4. every request-local timer/interval/immediate is canceled;
5. request-local listener roots and callback registries are released;
6. the reply is serialized with captured pristine intrinsics; and
7. no host callback, timer handle, raw rejection, promise, or VM realm is
   retained by process state.

Unresolved promises do not delay completion when the business program has
settled; they become unreachable with the realm. If the business program itself
never settles, the Python request timeout discards the process.

### Unhandled rejection ownership and completion boundary

The final worker follows `current_screenshot_pages.cjs`'s hardened realm-side
serializer and primitive-completion shape, while closing its remaining
raw-reference window. Because requests are serialized, exactly one request may
own an active `unhandledRejection` listener. The listener is installed before
VM launch. On notification it ignores the promise argument and immediately
serializes the reason through the active originating realm's captured serializer
to one bounded primitive `{name,message,stack}` record. Temporary realm slots are
deleted in `finally`; neither the raw reason nor promise is ever appended to a
host array, retained by a closure, inspected with host getters/coercion, or
carried into another request. Timer-dispatch failures use the same immediate
origin-realm serialization path. A serialization failure is fatal protocol
failure, not a reason to retain the raw value.

The VM request body owns the final query. After its business body settles it
allows microtasks and one request-owned timer turn to run, then synchronously
queries the primitive mailbox supplied on the host's poll call for the already-
detached rejection/dispatch records before it can send primitive success
completion. A rejection observed before or at that
boundary replaces success with a detached `ok:false` business failure and the
same process remains usable after listener/timer/realm cleanup. The active
listener is removed and the realm is released before reply publication.

A process-level fail-fast backstop owns any rejection observed with no active
request. The serial read loop includes a post-reply turn before admitting the
next line. Therefore a rejection after a published success is a protocol/late-
exit defect: it emits no second reply, exits the process, and is attributed by
`NodeScenarioWorker` to the prior successful request on the next request or
`close()`. It is never converted into a business failure for, or otherwise
charged to, the next request. After that crash is surfaced, a subsequent request
may start one clean process under the existing no-retry contract.

Permanent witnesses cover: a rejection before business settlement; a rejection
at the final timer boundary; omission/ignoring of captured records; querying one
turn too early; retaining a request listener or its realm/reason; and a late
post-success rejection followed by a next-request probe. The first two
business-fail and recover in the same PID. The late case returns the original
success, then produces the existing prior-request late-exit error without
executing the next scenario. Disposable mutants for ignored records and an early
query must fail those exact witnesses. `current_screenshot_pages.cjs` is the
reviewed model for VM-side serialization and primitive completion; it is not the
Stage B runner and is not modified by this tranche.

### Defensive detachment

The wrapper captures pristine VM-owned operations before evaluating family or
production code. Detachment must remain correct when request code:

- changes `JSON.stringify`, `String`, `Object`, `Reflect`, `Error`, or their
  prototypes;
- replaces `Promise.prototype.then`;
- throws an `Error`, a primitive, `null`, an object with throwing getters, or a
  Proxy whose traps throw;
- mutates its decoded input, DOM classes, result object, diagnostic arguments,
  or nested prototypes;
- leaves promises unresolved;
- returns an object with `toJSON`, getters, cycles, or poisoned prototypes; or
- mutates a previously returned Python reply before the next request.

Error detachment reads name/message/stack independently under guarded captured
operations. A hostile field becomes a bounded placeholder rather than causing a
second failure. Diagnostics have bounded rendering. Business reply data is
converted to finite JSON while the request realm is still owned, then the realm
is discarded. No raw VM error or promise crosses to the host, and no host error
is injected into a later realm.

## Family adapters

Each adapter constructs the exact page shape and API seams currently owned by
its CJS program. Refactoring may remove argv/fs/vm plumbing but may not rewrite
scenario assertions or replace production scripts with a second
implementation.

### Saved layouts

The session manifest contains one `TextPageTree` root and one `PageTree` root
built from the current `index.html`. `saved-main` and `saved-owner` use the text
root. `saved-capture` and `saved-dev` use the structural root. Each request gets
a fresh decode and DOM.

The four program routes retain current assertions:

- main: all 55 ordering, staging, copy-dialog/detail, geometry, controls, row,
  and receipt scenarios;
- owner: real `saved`/`retained`/`excluded` Api receipts and marker/visibility/
  copy owner controls;
- capture: reversed/local/boundary session ownership; and
- dev: real dev fixture execution and capture ownership, including expected
  diagnostics.

### Fleet Sharing

The session manifest uses the current `SharingPageTree`. Python continues to
build `missing`, `live`, `older`, rejection, and preference-case inputs with the
current capacity helpers. The adapter inserts the scenario into the VM-owned
input rather than exposing it as host argv state. All 65 branches and their
internal matrices remain in the existing program.

The specialized select/focus/text behavior remains exact. Its `errors` capture
becomes the common VM-local diagnostic collector, preserving and strengthening
the current count assertion with stable method/message assertions.

### Group backward

The session manifest uses `PageTree`; each request receives current
`marker_choices()`. The dev source slices execute in one fresh VM realm so
lexical fixture declarations remain shared inside that request but disappear
before the next. All 17 scenario branches and internal focus/draft/crop matrices
remain exact.

### Label markers

The session manifest uses `PageTree`; each request receives current
`marker_choices()`. Conditional `panel.js` execution for `copy` and `reset-copy`
remains scenario-owned. All 21 hydration, receipt, owner, retention, exclusion,
refresh, navigation, screenshot, reset, capture-entry, and deferred branches
remain exact.

## One real saved-layout receipt

### Construction boundary

Add one process-local once-provider and one session-scoped receipt fixture in
`test_preview_savedlayouts_page.py`. The fixture and the qualification module
both call the plain private provider, which memoizes only the detached JSON and
immutable qualification metadata. This avoids importing a pytest fixture across
modules—pytest would register a second fixture definition—while guaranteeing one
construction whether the qualification ID or a main page ID runs first. It uses
`tmp_path_factory`, never a function-scoped `tmp_path` or `monkeypatch`, and
performs these steps before returning anything:

1. record the current `LOCALAPPDATA`, `paths._use_legacy`,
   `settings._save_locked`, `os.fsync`, and committed-reader registry baseline;
2. enter one bounded `pytest.MonkeyPatch.context()`;
3. set `LOCALAPPDATA` to a unique session temporary state root, force
   `paths._use_legacy = False`, and install a counting `os.fsync` wrapper that
   delegates every call to the exact captured function;
4. create the existing real `AppState`/`Api`, attach `FakeWindow`, initialize
   seen names through real `settings.update`, and use the real layout store;
5. execute the unchanged operation sequence below;
6. perform the failed-save step inside a nested bounded
   `MonkeyPatch.context()` and prove `_save_locked` is restored immediately;
7. validate the durable settings file as UTF-8 JSON, the committed reader, and
   first-Apply pending observation before leaving isolation;
8. serialize the exact 22-value receipt with `ensure_ascii=False`,
   `allow_nan=False`, and compact separators;
9. shut down Api-owned Preview resources, release bound methods/readers, and
   prove no new committed-reader registry entry remains;
10. restore `paths._use_legacy` in `finally`, exit the outer patch, and prove the
    environment, `os.fsync`, and patched attributes equal their baselines; then
11. expose only the receipt JSON string plus detached qualification metadata.

No `Api`, controller, store, settings document, reader, path, monkeypatch,
window, callback, or mutable receipt object escapes.

### Exact production sequence

The once-only sequence remains the current test body:

1. persist `seen=["Alice", "Bob"]`;
2. replace Alice geometry with real `Entry(Rect(1, 2, 500, 300))`;
3. read `initial`;
4. exclude Alice (`hidden`), exclude Bob (`both`);
5. create `Hidden` (`created`) and retain its production ID/revision;
6. show Bob, then show Alice (`visible`);
7. replace only the controller apply port with the existing pending sampler,
   call first Apply (`bulk`), and retain the emitted pending presentation
   (`pending`) before native completion;
8. hold the real exclusive admission, capture refused visibility (`refused`),
   finish it, and retry (`retry`);
9. set Alice size (`size_ack`), Apply again (`geometry_apply`), then retain
   `newer_geometry` after a newer size;
10. replace Bob geometry, copy Alice to Bob, and retain `newer_copy`;
11. reset working layouts and retain `newer_reset`;
12. attempt case-insensitive duplicate `HIDDEN` (`duplicate`);
13. Apply with stale revision (`stale`);
14. update, retain its production revision, rename to `__proto__`, retain the
    new revision, and remove it (`updated`, `renamed`, `removed`);
15. patch only `settings._save_locked` to raise `OSError("Disk unavailable")`,
    attempt create `Refused` (`failed_save`), and restore the writer;
16. replace only the visibility refresh port with the current incomplete live
    result and capture `incomplete`; and
17. build the current empty Api and capture `unavailable`.

The first Apply pending capture is load-bearing. It must continue to show
`operation.action == "apply"` and `operation.pending is True` while the final
Apply receipt remains persisted. Named IDs/revisions come only from production
results; they are never synthesized or normalized by the fixture.

### Exact 22 values

The serialized receipt has exactly these 22 top-level primitive JSON value
trees—transitively only finite JSON types—and keys in this order:

```text
initial
hidden
both
visible
bulk
pending
refused
retry
created
duplicate
stale
updated
renamed
removed
size_ack
geometry_apply
newer_geometry
newer_copy
newer_reset
failed_save
incomplete
unavailable
```

`scenario` and `page` are not receipt values. Each of the 55 tests calls
`json.loads(receipt_json)` afresh, adds its own scenario, and lets the worker
add freshly decoded startup markup inside the VM. Mutating one decode or one
reply cannot affect another case.

The three owner rows retain their own `owner_api` setup. The four capture rows
retain their own production inputs. They share the family process, not the main
receipt.

### Exact persistence arithmetic

Disposable instrumentation of the current code counted:

```text
55 main saved-layout cases × 19 fsyncs = 1,045
owner cases                               10
capture/dev cases                          4
saved-layout file total                1,059
unchanged group/API cases                 29
all four files total                   1,088
```

After Stage B:

```text
one main receipt                           19
owner cases                                10
capture/dev cases                           4
saved-layout file total                    33
unchanged group/API cases                  29
all four files total                       62
```

Fleet Sharing and label-marker files contribute zero fsyncs. The exact
shared-main subcomponent is `1,045 -> 19`. The acceptance comparisons
are the healthy 165 Node-owning rows, `1,059 -> 33`, and all 205 existing rows,
`1,088 -> 62`. Qualification/helper-test processes, qualification fsyncs, and
mutation-probe overhead are measured and reported in separate fields, never
folded into either production-case count.

## Exact new identities

Add `tests/test_persistent_page_workers.py` with exactly these seven Stage B
qualification IDs:

```text
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[saved-layouts]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[fleet-sharing]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[group-backward]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[label-markers]
tests/test_persistent_page_workers.py::test_request_cleanup_after_success
tests/test_persistent_page_workers.py::test_request_cleanup_after_business_failure
tests/test_persistent_page_workers.py::test_saved_layout_receipt_is_durable_and_detached
```

The four realm rows use exact representative business scenarios:

| Parameter | Representative |
|---|---|
| `saved-layouts` | `saved-main / reversed` |
| `fleet-sharing` | `fleet-sharing / missing-worker` |
| `group-backward` | `group-backward / dev` |
| `label-markers` | `label-markers / hydration` |

Each performs A-poison-A in one process. A executes the real family program. The
poison request also executes the real program, then mutates global state,
Object/Array/Promise/Error and DOM prototypes, `Promise.prototype.then`, decoded
input, a returned nested object, console arguments, and a cached-result
sentinel. The final A proves all poison absent, the source execution counter is
one in the new realm, the normal output/diagnostics are exact, and a Python-side
mutation of the earlier reply did not return. Each row records one PID.

`test_request_cleanup_after_success` registers timeout/interval/immediate
callbacks, DOM/window listeners, and an unresolved promise, then returns
success. The reply is withheld until cleanup is zero. A later clean request in
the same PID proves no callback fires and no listener/timer/result is retained.

`test_request_cleanup_after_business_failure` repeats cleanup with, as internal
non-parametrized subcases, an Error, thrown primitive, object with hostile
getters, throwing Proxy, a recognized scenario with invalid business data, an
unhandled rejection before settlement, and an unhandled rejection at the final
request-timer boundary. It proves detached message/stack behavior and a clean
business request after every business failure in the same PID. It then induces
one ordinary protocol/process failure and one late post-success rejection. Each
trigger is surfaced without retry; the late rejection is attributed to the
prior success rather than charged to or executed as the next scenario; and only
the request after the surfaced crash starts exactly one new PID and succeeds.
The success/failure cleanup identities also pin the listener baseline, zero raw
rejection/promise retention, zero retained realm, and query-before-success
receipt.

`test_saved_layout_receipt_is_durable_and_detached` imports and calls the
saved-layout module's plain private once-provider with its `tmp_path_factory`.
It receives the same memoized detached receipt used by the session fixture,
regardless of which module runs first, and proves exact key order/count, strict
finite JSON, 19 fsyncs, valid durable JSON, restored environment/legacy
flag/writer/readers, production ID/revision continuity, first-Apply pending
semantics, 55 independent fresh decodes, and no alias after mutating one decode.
It does not rebuild the receipt.

Qualification worker starts and fsyncs from deliberate fault injection are
reported separately from the healthy 165-case four-process and 33-fsync
contract.

The approved helper hardening adds exactly one further identity:

```text
tests/test_node_scenario_worker.py::test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration
```

That one non-parametrized test iterates exact controls and defects without
multiplying collection IDs. It proves `id: true` is rejected; integer `0` and
float `1.5` durations are accepted; duration `true`, a negative finite number,
and raw JSON `NaN`, `Infinity`, and `-Infinity` are rejected. For every rejected
reply it proves the current process is discarded, no invalid reply is returned,
and the following clean request starts a distinct PID and preserves monotonic
request IDs. The existing 12 helper IDs remain exact, including
`test_invalid_reply_schema_discards_process_with_context_and_restarts[wrong-duration-type]`.
The helper module therefore collects 13 IDs, Stage B adds eight IDs in total,
and the implementation-relevant selection contains 225 IDs: 205 existing
targets, seven Stage B qualifications, and 13 helper-contract IDs.

## Mutation and contract matrix

Every temporary mutation is applied in disposable space or a bounded context,
is tied to the named assertion, has an explicit restoration check, and is
followed by a clean anti-masking run. A failure caused only by leaving the probe
installed is not evidence.

| Boundary | Temporary defect | Required witness and anti-masking check |
|---|---|---|
| Host leakage | inject a host DOM object and host `Promise` into a reused VM | mutation reaches host `Object.prototype`/`Promise.prototype`, reproducing the naïve defect; delete both properties and prove host pristine before candidate run |
| Fresh realm | reuse one context for A-poison-A | each family realm ID/prototype assertion fails; restore fresh construction and the same A-poison-A passes |
| Program execution | cache A output or skip second source evaluation | execution counter is not one/fresh and representative assertion fails; restored implementation passes normal, reverse, and A-B-A |
| Input detachment | assign parsed host payload directly into VM | VM mutation changes host/Python-visible nested input or next request; restored stringify/fresh-parse preserves both originals |
| Result detachment | retain/return a prior VM result object | Python mutation reappears or cached-result sentinel survives; restored JSON detachment passes |
| Intrinsics | expose host constructors or use mutable global serializer | prototype poison reaches host or reply serialization changes; host cleanup assertion plus pristine serializer witness fail specifically |
| Promise completion | finish via mutable `Promise.prototype.then` | poison request hangs/fails to clean; async/await lexical completion survives and next request passes |
| Error detachment | read `error.message`/`stack` naively | hostile getter/Proxy causes protocol crash; guarded per-field placeholders keep a business failure and same PID |
| Thrown primitive | assume every rejection is Error-shaped | primitive failure loses message or crashes serializer; detached failure then clean request fails |
| Timers | omit cancellation or expose native handles | callback fires after reply, cleanup receipt is nonzero, or next request observes it; restored run records zero |
| Listeners | retain DOM/window root or callback outside VM | old callback fires/realm remains reachable after reply; restored cleanup and fresh-DOM witness pass |
| Unresolved promises | await every created promise or retain its realm | success/failure cleanup times out or retained-realm count is nonzero; restored request completes and next stays clean |
| Rejection ignored | discard a captured primitive rejection record | before/boundary rejection incorrectly succeeds; restored runner business-fails the owning request |
| Rejection query too early | query before the request-owned timer turn | boundary rejection incorrectly succeeds; restored boundary witness fails before success completion |
| Rejection raw retention | append raw reason/promise or keep listener/realm after cleanup | hostile getter/Proxy or listener/retained-realm witness exposes the leak; restored record is primitive and cleanup zero |
| Rejection next-charge | leave a late rejection for the next active listener | next scenario runs or receives `ok:false`; restored runner exits after prior success and existing late-exit attribution fires before next execution |
| Invalid request | reply to malformed NDJSON/schema, wrong family/protocol, or unknown scenario | valid reply is observed or process survives; restored runner emits no reply and closes |
| Invalid business payload | make recognized semantic invalidity fatal | PID changes; restored adapter returns detached `ok:false` and the clean next request retains PID |
| Protocol recovery | retry the crashing request automatically | side-effect/request counter exceeds one; restored contract raises once and only the following request restarts |
| Business recovery | discard process on `ok:false` | PID changes after detached failure; restored Error/primitive/Proxy/rejection/business-input matrix retains PID |
| Late exit | silently restart after valid reply | existing `test_node_scenario_worker.py` late-exit attribution fails; no Stage B masking wrapper is allowed |
| Diagnostics | merge console error into global failure or omit it | dev/reject/source-rejection count/order/text assertions fail; restored one-shot and worker forms both pass |
| Saved mapping | omit owner/capture cases (the 158-case subset) | exact 165 inventory/hash and per-program counts fail |
| Receipt sequence | omit/reorder one real operation or synthesize ID/revision | exact 22-key receipt and existing 55 scenario assertions fail at the owning branch |
| Pending observation | sample only final Apply state | `pending.operation.pending` witness fails although final receipt persists; restored blocked boundary captures both |
| Durable state | detach before durable validation or use a fake writer | settings-file/readback/reader assertions fail; restored real atomicio path records 19 fsyncs |
| Failure patch | let `_save_locked` patch escape | identity restoration assertion fails before receipt exposure; subsequent clean save is the anti-mask |
| Environment | leak `LOCALAPPDATA` or `_use_legacy` | baseline equality and post-fixture real path assertions fail; context/finally restoration passes |
| Reader lifetime | expose Api/reader or retain registry entry | weak registry differs after GC/shutdown; restored detached text leaves baseline keys |
| Worker count | use per-case or per-program process | JUnit properties for the healthy 165 rows differ from four family/PID pairs or request counts `62/65/17/21` |
| Fsync count | rebuild main receipt per row | deduplicated receipt plus per-case JUnit evidence differs from target-165 `33` or full-205 `62`; baseline comparators remain `1,059` and `1,088` |
| One-shot CLI | remove guarded CLI or alter argv/streams | six direct CJS invocations fail their existing PASS and diagnostic contracts |
| Order | retain request state | reverse, shuffle, repeat, A-B-A, or cross-family order differs from collected order |

## Order and structural qualification

Freeze the 165-ID list and run the following separately with worker-start,
request, PID, cleanup, and fsync instrumentation:

1. collected order;
2. exact reverse order;
3. deterministic seed-`20260926` shuffle;
4. cross-family round-robin interleaving that repeatedly leaves and re-enters
   modules;
5. each family alone;
6. representative single IDs in fresh pytest invocations;
7. repeated identical requests; and
8. A-B-A and failed-then-clean sequences in one PID.

For each of the first four healthy 165-case orders require:

- exactly 165 unique expected IDs and 165 passing outcomes;
- family request counts `62/65/17/21`;
- exactly four process starts and one PID per family;
- no restart, retry, protocol error, or late exit;
- zero host timer handles, host callbacks, active rejection listeners, pending
  rejection records, and retained realms after every reply;
- one saved receipt construction and exactly 19 receipt fsyncs;
- exactly 33 fsyncs across the 165 Node-owning rows and, in the complete
  205-case selection, exactly 62 fsyncs; and
- exact output/diagnostic equivalence with the one-shot baseline.

No workflow edit is needed to make those counts hosted evidence. The target test
modules append these exact testcase JUnit properties through
`request.node.user_properties`:

```text
stage_b.worker_family = saved-layouts|fleet-sharing|group-backward|label-markers
stage_b.worker_pid = <positive integer>
stage_b.worker_request = <1-based family request ordinal>
stage_b.direct_fsync_calls = <nonnegative integer>
stage_b.receipt_build = saved-layout-main-v1:19
```

Every one of the 165 Node-owning cases records the first three. Every one of the
205 existing target cases records `stage_b.direct_fsync_calls`; the 55 main saved
rows also record the literal receipt build value above. Test-local wrappers
delegate to the captured real `os.fsync` and each defining module asserts its
frozen per-case counts; the once-provider separately asserts one construction
and 19 calls. A JUnit audit requires four `(family,pid)` pairs with request
ordinals exactly `1..62`, `1..65`, `1..17`, and `1..21`; the receipt value on all
55 main rows, counted once as 19; direct fsync sums of 14 for the 165 set and 43
for the 205 set; and therefore candidate totals 33 and 62. The same assertions
print this exact compact, sorted-key line for the complete 205 selection as a
human log fallback:

```text
STAGE_B_EVIDENCE {"fsync_full_205":62,"fsync_node_165":33,"fsync_receipt":19,"requests":{"fleet-sharing":65,"group-backward":17,"label-markers":21,"saved-layouts":62},"worker_starts":4}
```

Qualification cases use only
`stage_b.qualification.worker_starts` and
`stage_b.qualification.fsync_calls`, report their observed integer values, and
never share the healthy receipt value or sums. The existing workflow already
uploads `pytest-result.xml`, so `.github/workflows/ci.yml` and the timing
summarizer stay unchanged.

The seed-shuffle input itself is frozen by final-newline SHA-256
`44823cd4ec00d5e92da597845ac3c2e16b8de6c0edf3cac521b7dc4605fbe39c`.
Disposable reverse and cross-family inputs had hashes
`2dff54f5b75dcc262527eedb319b5bf6a7d3def17dae212261b0696529caa718`
and `183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1`.
The collected input has the frozen 165-ID hash above.

Run the seven Stage B qualification IDs and 13 helper IDs separately when
asserting four starts or the 33/62 candidate fsync totals; their deliberate
faults, restarts, and qualification fsyncs are overhead, not a violation of the
production-case arithmetic. Then run all 225 implementation-relevant IDs
together for outcome and isolation coverage without reusing the four-start
claim from the focused 165 run.

## Disposable feasibility evidence

No repository implementation was made during design qualification. Disposable
files lived under `/tmp`; only this specification belongs in the versioned
worktree.

The completed probes established:

- the current four files pass all 205 IDs and launch Node exactly 165 times;
- one-shot program counts are saved layouts 58, capture sessions 3, dev capture
  1, Fleet Sharing 65, group backward 17, and label markers 21;
- current fsync instrumentation records exactly 1,059 across the 165
  Node-owning baseline rows and 1,088 across all 205 existing rows;
- a disposable persistent overlay passed all 205 current IDs, but that overlay
  is only feasibility evidence: it is not the final runner and did not establish
  the hardened rejection-completion, fatal-request, or JUnit-evidence contracts
  specified here;
- the exact 165 Node IDs passed in collected, reverse, seed-`20260926` shuffle,
  and cross-family round-robin orders;
- each of those four 165-case runs recorded request counts `62/65/17/21`, one
  PID per family, zero nonzero timer reports, successful A-B-A replay, no replay
  error, and clean close;
- four representative poison/pristine runs stayed in one PID per family and
  passed real scenarios after global, built-in, DOM, and `Promise.then` poison;
- a separate naïve VM probe proved injecting a host object and host `Promise`
  lets request code poison host `Object.prototype` and `Promise.prototype`, then
  restored both exactly;
- a standalone real saved-layout construction produced exactly 22 detached
  values, 19 fsyncs, valid durable UTF-8 JSON, 55 independent decodes, and 55
  passing persistent requests in one PID;
- that receipt probe restored environment, `_use_legacy`, `_save_locked`, and
  the committed-reader registry before exposure, and retained the first-Apply
  pending observation;
- cleanup qualification registered one timer, one listener, and an unresolved
  promise, then reported zero host timer handles before reply and passed the
  next clean request in the same PID;
- Error, primitive, and hostile-Proxy business failures each preserved the PID
  and were followed by a clean pass;
- disposable boundary probes established Node's unhandled-rejection ordering
  across microtasks and a zero-delay request timer, and mutations that ignored
  the primitive queue or queried it before that turn missed the owning failure;
- malformed NDJSON, request/family/protocol/scenario defects closed the
  disposable process without a valid reply, while recognized semantic input
  failure returned `ok:false` and retained its PID;
- one protocol crash was surfaced without retry and only the next request
  started a distinct PID; a separate late-rejection probe returned success,
  exited with prior-request context before the next scenario executed, then
  restarted cleanly on the following call with no retained listener;
- direct baseline probing confirmed the current helper accepts `id: true` and
  negative, `NaN`, and infinite durations; a disposable strict-helper copy
  rejected those plus boolean duration, discarded after each invalid reply, and
  restarted cleanly without changing the repository helper;
- current one-shot diagnostics were observed directly: saved dev has 21 DEV
  stdout lines plus PASS and one `onTheme handler failed` stderr event; group dev
  has five DEV lines plus PASS and no stderr; controlled Fleet Sharing errors
  remain internal asserted diagnostics; and
- every temporary host mutation was deleted and every disposable process was
  closed.

Disposable local durations are diagnostics only and support no local or hosted
performance claim.

## Implementation sequence

1. Freeze the 205/165 ID lists, mappings, one-shot outputs/diagnostics, launch
   counts, fsync counts, and target hashes.
2. Add the one helper-contract ID and harden only numeric reply validation;
   prove invalid schema discard/restart while all 12 existing helper IDs remain.
3. Add the seven Stage B qualification IDs and make them fail against an unsafe
   reusable/host-owned realm, ignored/early rejection boundaries, retained
   listeners, and invalid request handling while preserving existing collection.
4. Add `page_scenario_worker.cjs` with primitive startup caches, fresh VM
   bootstrap, poll-driven VM timers, immediate origin-realm rejection
   serialization, pre-success boundary drain/query, fatal invalid-request paths,
   defensive detachment, diagnostics, cleanup, and the exact NDJSON schema.
5. Refactor the six fixture programs to primitive request-realm entries while
   retaining each guarded one-shot CLI and all scenario assertions.
6. Add each module-local session manifest/worker fixture and convert only its
   mapped subprocess calls, retaining literal timeouts and exact PASS assertions.
7. Build the one real saved-layout receipt under bounded isolation, detach it,
   and switch only the 55 main rows to fresh decodes.
8. Add test-owned JUnit worker/PID/request/fsync properties and their selected-set
   assertions without changing workflow or timing-summary code.
9. Run focused realm, poison, rejection-boundary, invalid-request,
   cleanup, failure/restart, one-shot, diagnostics, receipt, worker-count, fsync,
   and order witnesses after each family.
10. Run the complete verification matrix, inspect skips and final diff, then
    write the separately authorized results ledger with evidence actually
    observed.

## Verification and hosted acceptance

### Focused local checks

At minimum run:

```text
node --check tests/fixtures/page_scenario_worker.cjs
node --check tests/fixtures/preview_savedlayouts.cjs
node --check tests/fixtures/preview_capture_sessions.cjs
node --check tests/fixtures/preview_dev_capture.cjs
node --check tests/fixtures/fleetsharing_page.cjs
node --check tests/fixtures/preview_group_backward.cjs
node --check tests/fixtures/preview_labelmarkers.cjs
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -v
uv run --no-sync python -m pytest tests/test_persistent_page_workers.py -v
uv run --no-sync python -m pytest tests/test_preview_savedlayouts_page.py tests/test_fleetsharing_hydration.py tests/test_preview_group_backward.py tests/test_preview_labelmarkers_page.py tests/test_persistent_page_workers.py -rs
node scripts/js_smoke.js
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
cargo test --manifest-path packaging/settings-codec/Cargo.toml
```

Also run the existing DOM/helper tests used by the four modules, all six direct
one-shot CLIs, and the instrumented order/mutation matrix. Syntax checks do not
replace execution. A plain-browser/web smoke pass is not required because no
production web source changes, but the executable JS smoke gate remains
mandatory.

### Complete local suite

Install the built release settings codec in `packaging/bin`, keep Node on PATH,
and run:

```text
uv run --no-sync python -m pytest tests/ -rs
```

Expected complete collection is exactly 16,617 unique IDs: the accepted 16,609
ordered baseline identities plus the seven exact Stage B qualification IDs and
one exact helper-contract ID. Inspect all skips. Node/native/codec skips are not
acceptable full-suite evidence.

### Hosted evidence

A later hosted run must bind exact PR head, base, synthetic checkout, attempt,
jobs, logs, and artifacts as Stage A did. Acceptance requires:

- checks, Ubuntu, and Windows success;
- exactly one audited attempt unless every attempt is separately explained;
- existing 16,609-ID ordered subsequence unchanged and all eight new IDs exact;
- expected outcomes Ubuntu 16,603 passed plus the same 14 skips, and Windows
  16,550 passed plus the same 67 skips;
- normalized existing skip arrays unchanged;
- no target, qualification, Node, codec, or unexpected native skip;
- exact source scope and protected-file hashes;
- instrumented four-worker/receipt/fsync evidence from both platforms; and
- all elapsed values labeled single-run observations with no timing attribution.

The implementation results ledger freezes candidate full-order hashes only
after collection; this design does not invent them.

## Exact implementation scope

Implementation and its authorized artifacts are limited to these 17 paths:

```text
tests/test_preview_savedlayouts_page.py
tests/test_fleetsharing_hydration.py
tests/test_preview_group_backward.py
tests/test_preview_labelmarkers_page.py
tests/fixtures/preview_savedlayouts.cjs
tests/fixtures/preview_capture_sessions.cjs
tests/fixtures/preview_dev_capture.cjs
tests/fixtures/fleetsharing_page.cjs
tests/fixtures/preview_group_backward.cjs
tests/fixtures/preview_labelmarkers.cjs
tests/fixtures/page_scenario_worker.cjs
tests/test_persistent_page_workers.py
tests/node_scenario_worker.py
tests/test_node_scenario_worker.py
docs/superpowers/specs/2026-09-26-persistent-page-workers-stage-b-design.md
docs/superpowers/plans/2026-09-26-persistent-page-workers-stage-b.md
docs/ci-persistent-page-workers-stage-b-results.md
```

The current documentation-only commit contains only the specification path.
The plan and results paths are future separately reviewed artifacts covered by
the user's external authorization.

## Rejected alternatives

- **One global worker:** rejected because a poison or lifecycle defect could
  cross families and one family failure would discard unrelated state. Four
  family-local processes keep ownership and diagnostics explicit.
- **One worker thread or VM worker per request:** rejected because it preserves
  most startup waste and adds a second lifecycle beside the existing Python
  process owner.
- **Reuse one VM/DOM per family:** rejected because request-order dependence is
  the primary safety risk this design must remove.
- **A generic wrapper around unchanged CJS programs:** rejected. Disposable
  inspection confirmed the current fixtures create/inject host-realm DOM,
  Promise, timer, and callback objects. A naïve reusable context lets request
  code poison host intrinsics.
- **Cache parsed markup, payloads, receipts, or results:** rejected because
  mutable identity would cross cases. Only primitive text is reusable.
- **Use the 158 obvious page rows:** rejected because it omits the three owner
  and four capture/dev cases that also launch Node. The approved boundary is all
  165.
- **Leave `NodeScenarioWorker` numeric validation unchanged:** rejected because
  Python `bool` is an `int`, and `json.loads` accepts nonfinite numeric tokens by
  default. The approved change is limited to exact-type, finite, nonnegative
  reply validation plus its one contract identity; lifecycle broadening remains
  rejected.
- **Change `screenshot_dom.cjs`:** rejected because Stage B can evaluate its
  existing primitive factory source inside each fresh realm.
- **Add a dependency, workflow cache, xdist, or new CI shard:** rejected as
  unnecessary and out of scope.
- **Combine Stage C deletion/consolidation:** rejected. Persistent execution
  must first preserve every approved Stage B identity and assertion.
- **Use elapsed time as acceptance:** rejected because testcase sums, pytest
  wall time, workflow step time, and job time are different noisy surfaces.

## Stop conditions and adaptation points

Stop and request explicit scope/design review rather than silently expanding if:

- implementation requires any source path outside the exact 17 above;
- `tests/conftest.py`, a production/web module, workflow, dependency, lockfile,
  config, packaging file, or `screenshot_dom.cjs` appears necessary;
- `NodeScenarioWorker` needs any change beyond the exact numeric reply
  validation above, or its existing lifecycle semantics must change;
- any of the 205 existing IDs, parameters, markers, assertions, internal
  matrices, timeouts, or one-shot contracts must change;
- the healthy 165-case run cannot stay at exactly four processes;
- a host constructor/callback/promise/error/timer handle must enter a request
  realm;
- cleanup cannot complete before reply or a business failure cannot recover in
  the same process;
- the real receipt cannot be detached after exactly one 19-fsync construction
  with environment, writer, legacy flag, and readers restored;
- any platform gains a Node, codec, target, qualification, or unexplained native
  skip;
- the seven Stage B qualification IDs are insufficient, a second new helper ID
  is proposed, or the complete target would exceed 16,617; or
- Stage C behavior becomes entangled with Stage B.

Local reversible details may adapt only within these boundaries. Examples are a
private VM helper name, bounded diagnostic rendering limit, or manifest field
spelling, provided protocol tests pin the final choice and no observable
contract above changes. Any change to family count, failure classification,
receipt contents, source scope, or identity set requires renewed approval.

## Self-review and completion criterion

The accepted review corrections reconcile as follows:

- scope is exactly 17 paths: the prior 15 plus the helper and its tests;
- identity arithmetic is `16,609 + 7 + 1 = 16,617`, and focused relevant
  arithmetic is `205 + 7 + 13 = 225` with all 12 old helper IDs preserved;
- process arithmetic is exactly four healthy family workers serving
  `62 + 65 + 17 + 21 = 165` requests; qualification starts/restarts are
  separate;
- fsync arithmetic is baseline/candidate healthy-165 `1,059 -> 33` and
  baseline/candidate full-205 `1,088 -> 62`, with the candidate decomposition
  `19 shared receipt + 14 other Node-owning = 33` and `33 + 29 unchanged
  non-Node = 62`; qualification fsyncs are separate;
- malformed startup/NDJSON/request/family/protocol/scenario paths are fatal with
  no valid reply, while recognized semantic business-input failures are
  retainable `ok:false` replies;
- pre-boundary unhandled rejections belong to and business-fail the active
  request; late post-success rejections terminate the process and retain prior-
  request late-exit attribution rather than contaminating a next request;
- all one-shot PASS strings and dev/controlled diagnostic counts, order, and
  stable prefixes are explicit; and
- hosted worker/fsync evidence is emitted by test-owned JUnit properties and
  assertions, so the workflow and timing summarizer remain outside scope.

Stage B is complete only when the exact scoped implementation, seven Stage B
qualification IDs, one helper-contract ID, full local suite, mutation/order
matrix, one-shot compatibility, worker/fsync instrumentation, and hosted
provenance/outcome/skip evidence all pass, and the results ledger reports
concerns without timing causation. Until then this document is an approved
design, not evidence that the implementation exists or performs faster.
