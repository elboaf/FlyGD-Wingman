# Persistent page workers — Stage B results

## Authority and exact source baseline

Task 1 froze the merged PR #291 source at base
`203d2068787cb3457916db6005afda0a7ce7a43a` and the repaired implementation
plan at `ecfbe219e49626c0c8419484dbf3225b685a7d1d`. The merge base and
`origin/main` were both exactly `203d2068787cb3457916db6005afda0a7ce7a43a`.
The starting worktree was clean, and the pre-Task-1 range contained only the
approved Stage B specification and plan.

The 13 source authorities matched their approved SHA-256 values:

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

`/tmp/stage-b-baseline/source-hashes.json` also freezes all test signatures,
decorators, collected markers, CJS argv/PASS sites, and the 15 protected
read-only hashes from the plan. Its SHA-256 is
`2930fc121405abab6c45048dde5da0bec3d661c262e55a2d2df0d40bab376dc7`.
No executable or protected source byte was changed in Task 1. The corrected,
recursive 58-file external evidence inventory is
`/tmp/stage-b-baseline/artifact-manifest.json` (SHA-256
`0dc19626d5b7278d5e051154734c21240ca952a0504a43953aaec16497896286`).
It includes the five canonical files under `scratch-fixtures/` by relative path
and content hash, including the worker-compatible fatal-probe program and request
fixture. Manifest generation is an explicit freeze command; subsequent
verification is read-only and byte-compares the existing JSON and hash authority.

## Accepted Stage A provenance and artifact hashes

The read-only re-audit at `/tmp/stage-b-baseline/hosted.json` passed for PR
`291`, workflow run `36258907685`, attempt `1`, reviewed head
`3c3fe622f2a178805f4267d90d12aff61293b6d7`, frozen executable head
`83bd018b6eeb29e159741258e8d979c7481d7d01`, base
`463bccb07077325e64b6ad7f7ce4e9c100d2fcd6`, and synthetic checkout
`5e9adb83e8ac175756b987da25eeec657c4d1a4d`.

The three successful jobs were checks `108450833147`, Ubuntu `108450833121`,
and Windows `108450833027`. The uniquely selected artifacts were Ubuntu
`10911184052` and Windows `10911469146`. Their retained-byte checks were:

| Retained path | SHA-256 |
|---|---|
| `api/artifacts.json` | `49e8931d000f8c69041309136da481f86691c8f3fbca38093d5d4c4dd4c200f6` |
| `api/jobs-attempt-1.json` | `dc477778b1e728ef6b13f445cc80ab4a3889a20574fa59a3206ed068c7949cf6` |
| `api/pr.json` | `a1ee26101fa0d57d54c68cb0b61580a8870630c07c5004ebe10d7d3a42bdca7a` |
| `api/run-attempt-1.json` | `e9c1038e3a0d71f4f24585ef259914b2450477da0f92ff64e542086a686bccec` |
| `api/run.json` | `d96d9edc7ba138023378678be970650ae48bb524e6c88cbdd278470cff16ad3c` |
| `artifacts/downloads/ubuntu.zip` | `6b6420e809e68479fac3d09f977ee357d17ddacc4a8ed13ecf6bc2aee8745de1` |
| `artifacts/downloads/windows.zip` | `87ddd048aa4fce06cd0d8600b0e7435a4bf92be5240477f2b190259eccf5b1a1` |
| `artifacts/ubuntu/pytest-result.xml` | `d424fc56070656e88e6c1791e34de59c5aeaea81527c456c18c1d5321291acf6` |
| `artifacts/ubuntu/pytest-timing.json` | `e41f9a0992dc1acfe028a92ebf02d6d057efd61e03d072315b92b9044c3cf6b7` |
| `artifacts/windows/pytest-result.xml` | `ee15029ce8a392d7af526c39093c8781cc0ebcf0b0e643d8d860ca0e77f4f6d7` |
| `artifacts/windows/pytest-timing.json` | `f3b12200796084c028c11ae99f3115d48931c08880ca65379171054581afbce1` |
| `audit/audit.json` | `c8da8682fb2eed9329f38c092de55012e6d92b85b15d548206e454ce0bcc0cea` |
| `audit/audit-output.json` | `c8da8682fb2eed9329f38c092de55012e6d92b85b15d548206e454ce0bcc0cea` |
| `audit/audit_stage_a.py` | `dc08f0bfe6a9a410fd32da8ccac9d8cfd100ab3d7d1f3d6f94df0e9593f49e83` |
| `hosted-report.md` | `9a4a809d770b9cb3783b00faeedbf6a1a4955bf3dd2f49304479ab65a9a6edb5` |
| `logs/attempt-1/108450833027.txt` | `87cdc86e19823232ab03bfe552861ff6cb92fbecaa8e1912aa2a7bc7878fdd17` |
| `logs/attempt-1/108450833121.txt` | `26092ec07eac667843a36cd69c0d95fd87e900af7f8b19500f8647898a2bbf28` |
| `logs/attempt-1/108450833147.txt` | `041aa76d780fb56ecf3026fcf65130f1e368424e49bf5b9fa63809288599768b` |

The retained manifest is `/tmp/stage-b-baseline/artifact-hashes.json`.
Both ZIPs contained exactly `pytest-result.xml` and `pytest-timing.json`, and
member bytes equaled the extracted files.

Both platforms had the same 16,609 unique ordered identities, with final-LF
SHA-256 `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
Ubuntu had 16,595 passes and 14 skips; Windows had 16,542 passes and 67 skips.
Normalized skip manifests are retained separately for both platforms.

## Exact 205/165/12 identities and mappings

The collection-first gate wrote structured reports and separately validated
ID-only lists. The exact counts and final-LF ID hashes are:

| Set | Count | SHA-256 |
|---|---:|---|
| Existing target | 205 | `7337d36844ca94b21a0af2c4568ede5828f81df882d2899ca28aa9a505b69343` |
| Node-owning target | 165 | `60a253410671d0ac475c414940f007943ff96f4faebc30f0f1aaef9009e549fc` |
| Existing helper | 12 | `0363084c60146b443d3b9065f682cc77d0fce6b0d5fee8fa79dbc3219d92da1a` |
| Baseline target plus helper | 217 | `8e0a60759a2d205faa46d0a4460d56d518d429b317465c4dfefd1d8c9bf930ed` |

The baseline 217 order is exactly the target 205 followed by the helper 12.
All IDs are unique, and all eight approved Task 2 IDs are absent. The Node map
has exact family counts `62/65/17/21`, exact approved scenario order, explicit
saved owner/capture/dev selection, and exact program, protocol, label, and
timeout fields.

The frozen expected Task 2 ID orders are:

| Expected set | Count | Final-LF SHA-256 |
|---|---:|---|
| Relevant | 225 | `bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe` |
| Complete | 16,617 | `d04dff36b8cb278dac3c410bca86e271e17899ce16272c9062886a48f28220c3` |

The helper ID is inserted after the existing `wrong-duration-type` row. The
seven qualification IDs are appended after the target-plus-helper relevant
sequence and inserted between complete-suite modules `test_paths_engine.py` and
`test_poll_tick.py`.

## One-shot streams, launches, and timeouts

The instrumented 205-row run passed all 205 cases and captured exactly 165 Node
launches. Program counts were saved main/owner `58`, capture `3`, saved dev `1`,
Fleet Sharing `65`, group backward `17`, and label markers `21`; every process
exited zero.

All ordinary programs emitted exactly one expected PASS line and empty stderr.
Saved dev emitted the exact 21 DEV lines followed by `PASS dev`, plus its one
known `onTheme handler failed TypeError: Cannot read properties of undefined
(reading 'apply')` stderr diagnostic. Group dev emitted five exact DEV lines,
reused one generated ID in all three required positions, ended with `PASS group
backward dev`, and had empty stderr. Fleet Sharing `reject` and
`bridge-source-rejection` emitted only their PASS stdout in one-shot mode.

The frozen request timeouts are saved layouts `25.0s`, Fleet Sharing `20.0s`,
group backward `30.0s`, and label markers `30.0s`.

## Baseline persistence arithmetic

The delegated `os.fsync` probe observed exactly:

```text
55 saved-main rows       1,045
three saved-owner rows      10
capture/dev rows              4
Node-owning 165 total     1,059
unchanged non-Node rows      29
all 205 total             1,088
```

No call was suppressed by instrumentation. Candidate `33/62` persistence values
were not run in this task.

## TDD RED and GREEN record

Task 1 executed no Stage B implementation RED or GREEN. Task 2 first added the
one helper identity and ran it against the old validator in an isolated pytest
process. It collected normally and failed in the call phase at exactly
`numeric-schema bool-id: invalid reply was accepted`; malformed JSON, setup,
collection, and absent-scenario failures were excluded. After changing only
`_validate_reply`, all 13 helper identities passed. The missing-fields row now
pins exact `_ProtocolError` text and process discard, while the existing four
late-exit phase witnesses remain unchanged.

The seven qualification IDs were then collected before GREEN and executed one at
a time against a runnable unsafe worker/receipt seam. All seven failed in the
call phase at their unique approved sentinel; no collection, import, fixture,
timeout, or framing failure satisfied RED. The unsafe seam was replaced rather
than retained. Final focused outcomes are `13 passed`, `7 passed`, and a combined
`20 passed`; the preserved baseline selection also passed `217/217` with no
skip, failure, or error.

## Worker schema, VM, cleanup, and recovery qualification

`page_scenario_worker.cjs` now validates exact startup argv, family, manifest,
request envelope, protocol, and scenario ownership; reads all seven target CJS
files as UTF-8 source before service; and retains no target entry in
`require.cache` or `module.children`. Qualification requests execute synthetic
source, DOM, CommonJS, timers, listeners, promises, errors, and assertions in a
fresh VM context. The host receives only the VM poll function and primitive JSON
completion. Explicit startup seed globals are removed before program execution;
request-installed globals survive real Promise/timer awaits and are removed only
during cleanup. Malformed protocol is fatal with no reply; detached business
failure retains the process.

Reply, diagnostic, and failure serialization now use bounded manual walks over
captured own data descriptors and scalar quoting rather than mutable
`JSON.stringify` or `toJSON`. The permanent witnesses poison Object, Array,
Error, Promise, and JSON behavior, attempt completion-envelope forgery, and use
hostile getters/Proxy traps without changing the reply or escaping a raw reason.
The request rejection listener is active before VM launch. Real
`Promise.reject` calls before settlement and at the final timer boundary become
the current request's business failure; the actual post-success rejection exits
70, emits no second reply, and remains attributed to the prior request when the
next call observes it.

The four A-poison-A realm rows passed in one PID each with fresh execution count
one, clean host and DOM prototypes, input/prior-reply/module-export isolation,
and Promise-then poison survival. Cleanup success covered timeout, interval,
immediate, listener, unresolved-promise, async-global survival, all five console
methods, seven-source retention, and all six existing direct CJS paths (including
both saved-main terminal forms). Dedicated cleanup-failure workers proved
listener and timer removal exceptions are fatal before reply and that a later
call, not the failing call, starts recovery. Cleanup failure covered Error,
poisoned Error, primitive, null, hostile getters, Proxy, semantic business input,
before/boundary rejection, one fatal missing-input request, and late post-success
exit. Its observed sequence was exactly three process starts, with the attempted
`T` attributed to `before the next request` and recovery using request `N+2`.

## Saved-layout receipt and family conversion

The process-local once-provider builds one detached 22-key receipt through the
existing production Api/controller/store/settings/atomicio sequence. It isolates
`LOCALAPPDATA` with a session temporary root, forces and restores `_use_legacy`,
delegates every `os.fsync`, restores `_save_locked`, validates durable strict
UTF-8 JSON and the committed reader, shuts both Api objects down, clears created
owners, returns through a nested construction frame, runs GC, and proves every
Stage-B-created Api/state/document/controller/reader weak reference is dead and
no newly retained reader remains. The observed build
used exactly 19 fsync calls, preserved production ID/revision continuity, captured
the first Apply as pending, and retained the later persisted Apply. Fifty-five
independent decodes had no alias.

No saved business row was converted in Task 2. The original 55 per-row receipt
builds and all 165 one-shot Node calls remain until Tasks 3 and 4; candidate
`33/62` production-case fsync totals are therefore not claimed here. The
qualification-only owner/capture setup observed exactly four fsync calls.

## Remaining family conversion and order evidence

Fleet Sharing, group backward, label-marker, and saved-layout business callers
remain on their original one-shot paths. Task 2 adds only the shared worker
foundation and synthetic qualification interfaces; real-family acceptance and
four-process evidence remain pending Tasks 3 and 4.

## Mutation and restoration matrix

`/tmp/stage-b-baseline/mutations.py` contains one literal, ordered 71-recipe
registry partitioned exactly `14/16/41` across Tasks 3/4/5. Every recipe has one
unique literal sentinel and anchored regex, exact typed pytest/external/synthetic
owner, kind-specific masking rules, a literal edit with an explicit root, frozen
mutated/restored expectations, and an explicit `available_from_task`. The six
corrected owner mappings and three restored-only helper IDs are pinned explicitly.
The deterministic registry manifest SHA-256 is
`77803e6959f3d3e85b2a7ff2bb894bb91642d330c2d84f2981079fa76f9b2b24`.
The regenerated recursive artifact manifest is
`58939eb6cbd9fe83d2f19427762b3da4bb1eac5eaa3e21a22ae639152f5eae33`,
and the refreshed Task 2 identity-gate record is
`7ccf650d6af664a7087345cab21d182a8e36b05aaab6919db3efb904409ee515`.
It also freezes the read-only external adapter at SHA-256
`fb26c59c39029b5cebed6db086c8ca1bc1d9e1864081f169ab146e56ab50ca5c`.

Task 1 validates match-once cardinality only for the inputs available now:
`inventory-node-165`, `junit-property-cardinality`, and
`restoration-byte-integrity`. The inventory probe mutates and compares a real
copy of the frozen 165-ID input. The property probe parses real JUnit XML through
the shared unique-property auditor. Its one canonical recipe owns two ordered,
independent edit/probe/restoration cycles: duplicate then missing, recording
mutated cardinalities `[2, 0]` and restored cardinalities `[1, 1]` with exact
owner/key/value checks. The restoration probe checks exact fixture bytes.

External probe argv is one frozen, phase-identical template containing exactly
one `{mutation_root}` token, substituted by the typed runner on every mutated and
restored invocation. Each registry entry declares the exact target paths. The
adapter hashes deterministic path/length/bytes records for the files it opens;
the runner independently recomputes the phase-specific digest from the supplied
root and rejects missing or mismatched evidence. Adapter path, mode, target-list
position, and remaining mode-specific arguments are allowlisted.

The receipt probe imports and calls the once-provider from that root 55 times
through a measured builder and covers its owning Python file in the root digest.
Fatal protocol probes launch that root's `page_scenario_worker.cjs` with pipes,
write and flush one invalid request, and deliberately keep stdin open. A passing
worker must exit from fatal handling within one second; only after that observed
exit are streams read and reaped. Timeout is the intended mutant failure and its
finally path terminates or kills and reaps the child before reporting. The probe
then launches a distinct recovery process and requires one valid reply.

Task 1 countertests use a scratch worker with the same interface and prove each
guard mutation yields `[mutated=1, restored=0]`. A separate EOF-dependent worker
mutation sets only `exitCode`, stays alive while stdin remains open, and is
rejected and reaped. An arbitrary static command is rejected even when its argv
contains `{mutation_root}`; allowlisted fabricated adapters with missing or wrong
root digests are also rejected and restore exact bytes. Generic dispatcher tests
likewise execute real scratch subprocesses or real JSON/XML parsing functions.
No probe accepts a sentinel through argv or turns a synthetic on/off flag
directly into the expected message.

Restored pytest validation now requires the complete registered restored-ID list
in exact order—selected IDs plus any recipe-owned restored-only IDs—once each,
with no wrong, missing, extra, duplicate, skipped, error, or failed row.
Dedicated tests cover every mismatch.

At the end of Task 1 every implementation recipe remained pending until its
real target existed. Task 2 materialized the shared worker and once-provider, so
the first 14-name slice could be activated as recorded below. The
negative-infinity edit remains isolated to accepting `-Infinity` while still
rejecting finite negatives, NaN, and positive infinity; its helper execution is
reserved for the later schema slice.

The corrected tooling suites pass 60 checks: 19 collector/identity checks, 39
registry/restoration/dispatcher checks, and two recursive-manifest checks.

Task 2 additionally activated the canonical 14-name first implementation slice
from the corrected registry. The six realm recipes now perform real context
cache/reuse, source-result reuse, host-parsed input injection, prior-reply alias,
host `require`/module injection, and mutable Promise completion. The receipt
recipes now alter the actual pending capture, production ID source, durable read,
`os.fsync` delegation, writer/environment restoration, reader ownership, and
once-provider construction; no recipe inverts its own assertion or uses a
mutation-only worker flag. All 14 edits ran through the typed dispatcher: 13
pytest probes and the external receipt-count probe each produced their exact
sentinel, rejected masking, restored exact bytes/hash/diff/status, and passed the
registered restored probe. The ordered result file is
`/tmp/stage-b-task2-mutations.json`, SHA-256
`b76dd920aab5014c43ab70783d8c6f727dede106aaced7df74be403c881a78f5`. The provider's `pending_receipt` literal is unique, so no
unconverted business caller needed a temporary source edit.

This is real foundation/receipt defect qualification, not real-family conversion
acceptance. The later 16/41 slices and final 71-recipe aggregate remain pending.

## JUnit property ownership

The combined 20-ID JUnit contains exactly two qualification properties on each
of the seven qualification owners and none on helper IDs. Worker starts are
`1/1/1/1/1/3/0`; qualification fsync values are `0/0/0/0/4/0/0`, in declared ID
order. Each `(node ID, property name)` occurs once. Qualification values are not
folded into baseline or future candidate production-case arithmetic.

## Complete local endpoint

Task 2 collected the actual relevant selection as exactly 225 unique IDs and the
complete suite as exactly 16,617 unique IDs. Both ID files are byte-for-byte
equal to the frozen expected orders. Their final-newline hashes are respectively
`bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe`
and `d04dff36b8cb278dac3c410bca86e271e17899ce16272c9062886a48f28220c3`.
The actual structured collection hashes are
`6578618090ba75bd3ae672ba630f7f7786ff4de096d213737d2e5b2b5bebaa7c`
and `2131c640d9377e3ccf86c331ea677d5f3afc38a964d3e58f142f28164e3f4408`.
`verify_task2_identities.py` passed exact owner, marker, insertion-order,
baseline-subsequence, frozen-subset/hash, report/ID agreement, and empty
symmetric-difference checks. This task did not run or claim the complete
16,617-case outcome; that remains Task 5.

## Reviews, final scope, and frozen heads

Task 2 self-review found only its six original approved implementation/result
paths plus the authoritative plan correction: strict helper and helper contract,
shared worker, seven-ID qualification module, receipt provider added without
converting a business caller, this ledger, and the corrected Task 2 plan text. No production, web,
workflow, dependency, lockfile, configuration, packaging, existing CJS adapter,
or `screenshot_dom.cjs` byte changed. Protected hashes, Ruff, formatting, docs,
syntax, focused tests, baseline 217, collection gates, diff checks, and canonical
restoration were rerun before the Task 2 commit. Final Stage B review,
real-family conversion, executable head, and evidence head remain pending.

## Publication stop and hosted evidence

The accepted Stage A hosted evidence was re-audited read-only and classified
PASS. No Stage B candidate was pushed, no PR was created or updated, no workflow
was dispatched or rerun, and no candidate artifact was downloaded. Stage B
publication and candidate hosted evidence are **not run in this task**.

## Concerns and claim boundary

The local 217-row and 205-row executions and accepted hosted durations are
single-run observations only. Accepted Stage A target testcase sums were Ubuntu
`20.521s` for 205 / `20.454s` for 165 and Windows `62.945s` for 205 / `62.674s`
for 165. They establish no speedup, slowdown, lower bound, throughput, runner
efficiency, job effect, or critical-path causation.

Task 1 proves baseline identity, source, stream, launch, persistence, provenance,
artifact, and evidence-tooling contracts. Task 2 proves the strict helper,
synthetic shared-worker foundation, detached receipt, qualification properties,
and exact post-creation identity orders. It does not prove real execution for any
of the four business families, the healthy four-process/33/62-fsync endpoint,
the complete-suite outcome, final Stage B scope, or hosted acceptance.
