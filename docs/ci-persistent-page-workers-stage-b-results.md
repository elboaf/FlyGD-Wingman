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
`7de6f9afc355e9f495ed9074b4d5248a639e0fc422be27ff34ef45a87b9af7a1`).
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

Task 1 executed no Stage B implementation RED or GREEN. The exact 217-row source
baseline passed again (`217 passed`, no skip/failure/error); its refreshed JUnit
SHA-256 is
`008f257b0fe8e8e5b578c99b817e75c30a9ff4c965ea355da56af7ee0370e997`.
Task 2 RED/GREEN remains **not run in this task**.

## Worker schema, VM, cleanup, and recovery qualification

Not run in this task. Task 1 froze the eight planned identity owners and the
worker/schema/cleanup mutation metadata without executing a future recipe.

## Saved-layout receipt and family conversion

Not run in this task. The 55 current saved-main rows and their 1,045 fsync calls
are baseline observations only; no receipt provider or persistent family worker
exists yet.

## Remaining family conversion and order evidence

Not run in this task. Fleet Sharing, group backward, and label marker behavior
remains at the one-shot baseline.

## Mutation and restoration matrix

`/tmp/stage-b-baseline/mutations.py` contains one literal, ordered 71-recipe
registry partitioned exactly `14/16/41` across Tasks 3/4/5. Every recipe has one
unique literal sentinel and anchored regex, exact typed pytest/external/synthetic
owner, kind-specific masking rules, a literal edit with an explicit root, frozen
mutated/restored expectations, and an explicit `available_from_task`. The six
corrected owner mappings and three restored-only helper IDs are pinned explicitly.
The deterministic registry manifest SHA-256 is
`4af640d5d4ec0439c848bddc0b699a05ced7b5fc9d0464dd7b768acc8251edf5`.

Task 1 validates match-once cardinality only for the inputs available now:
`inventory-node-165`, `junit-property-cardinality`, and
`restoration-byte-integrity`. The inventory probe mutates and compares a real
copy of the frozen 165-ID input. The property probe parses real JUnit XML through
the shared unique-property auditor. Its one canonical recipe owns two ordered,
independent edit/probe/restoration cycles: duplicate then missing, recording
mutated cardinalities `[2, 0]` and restored cardinalities `[1, 1]` with exact
owner/key/value checks. The restoration probe checks exact fixture bytes.

External probe argv is a frozen template containing exactly one
`{mutation_root}` token, substituted by the typed runner on every mutated and
restored invocation. The receipt probe imports and calls the once-provider from
that root 55 times through a measured builder. Fatal protocol probes launch that
root's `page_scenario_worker.cjs`, inject the named invalid request, require a
fatal close with no valid reply, then launch a distinct recovery process and
require one valid reply. Task 1 countertests use a scratch worker with the same
interface and prove each guard mutation yields `[mutated=1, restored=0]`; a
static command independent of the mutation root is rejected. Generic dispatcher
tests likewise execute real scratch subprocesses or real JSON/XML parsing
functions. No probe accepts a sentinel through argv or turns a synthetic on/off
flag directly into the expected message.

Restored pytest validation now requires the complete registered restored-ID list
in exact order—selected IDs plus any recipe-owned restored-only IDs—once each,
with no wrong, missing, extra, duplicate, skipped, error, or failed row.
Dedicated tests cover every mismatch.

All future implementation recipes remain pending until their
`available_from_task` boundary. In particular, `receipt-once-construction`
targets the future once-provider assignment in
`tests/test_preview_savedlayouts_page.py`; it is not validated against a scratch
file, and the Task 3 hard gate must find that literal exactly once. The
negative-infinity edit is isolated to accepting `-Infinity` while still rejecting
finite negatives, NaN, and positive infinity; an in-memory validator mutant test
pins that distinction.

The corrected tooling suites pass 57 checks: 19 collector/identity checks, 36
registry/restoration/dispatcher checks, and two recursive-manifest checks.

This is dispatcher, parser, restoration, inventory, and manifest-integrity
evidence—not final persistent-worker defect qualification. The future Stage B
implementation recipes and their representative candidate executions are **not
run in this task**.

## JUnit property ownership

No candidate `stage_b.*` properties were produced in this task. Task 1 preserved
raw JUnit property elements as a list and exercised the actual unique-property
auditor against valid, missing, and duplicate-identical properties. A temporary
always-accepting auditor mutation fails at exact `stage_b property cardinality`.
Stage B property producers do not exist yet.

## Complete local endpoint

Not run in this task. No 16,617-case candidate collection or suite result is
claimed. The accepted 16,609 order was frozen only as an input for Task 2's
expected-order gate.

## Reviews, final scope, and frozen heads

Task 1 self-review found one tracked change: this results ledger. The approved
specification and repaired plan remained byte-unchanged. All source, test,
fixture, production, web, workflow, dependency, configuration, packaging, and
lockfile bytes remained unchanged. Final Stage B review, executable head, and
evidence head are **not run/frozen in this task**.

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
artifact, and evidence-tooling contracts. It does not prove the future
persistent-worker implementation, any recipe before its activation task,
candidate properties, final scope, complete-suite outcome, or hosted acceptance.
