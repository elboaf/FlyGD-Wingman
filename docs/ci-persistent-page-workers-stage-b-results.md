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

No call was suppressed by instrumentation. Task 4's final delegated property
audits measured the candidate values exactly: `14` direct Node-row calls plus
the one `19`-call receipt equals `33` across the healthy 165 rows; `43` direct
calls plus that receipt equals `62` across all 205 existing rows. Qualification
fsyncs remain separate.

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
than retained. After the final bound correction, fresh focused outcomes are
`13 passed in 3.29s`, `7 passed in 7.44s`, and a combined `20 passed in 12.88s`.
The preserved target selection passed `205/205 in 38.87s` with no skip, failure,
or error. An independent wrapper repeated the long escaped native-Error failure,
field lengths, retained frame, and same-PID recovery and passed `1/1 in 5.03s`.

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

Reply and ordinary JSON serialization use bounded manual walks over captured own
data descriptors and scalar quoting rather than mutable `JSON.stringify` or
`toJSON`. Failure serialization additionally captures the pristine VM Error
prototype, `isPrototypeOf`, `Reflect.get`, standard native Error prototypes, and
bounded string operations. Native inherited, own, and accessor-backed
`name/message/stack` fields are read independently and capped at named limits
256/8192/32768. The encoded envelope has the separately derived and asserted
247331-character maximum: six times the sum of all three decoded limits plus the
35-character JSON object syntax. `parseBoundedFailureJson` therefore accepts the
worst-case escaped bounded fields without treating the stack limit as an envelope
limit, while rejecting anything larger before parsing. Ordinary messages and
frames survive, poisoned Error/Reflect globals cannot forge the heading, and
hostile accessors or Proxy traps become bounded unreadable placeholders.
Diagnostics use the same native-Error detachment, so each of
`log/info/debug/warn/error` retains a primitive TypeError
`{name,message,stack}` argument and rendered message/frame, while hostile
accessor and Proxy controls remain unserializable.

The request rejection listener is active before VM launch. Every poll that
dispatches at least one due timer now resets the completion boundary and returns
without a reply. The host turn can therefore capture its rejection, and the next
poll consumes that mailbox before publication; future timers that are not due
remain canceled by normal cleanup. Real `Promise.reject` calls before settlement,
at the original timer boundary, and from a three-level nested final timer become
the current request's business failure and recover in the same PID. The separate
actual post-success rejection still exits 70, emits no second reply, and remains
attributed to the prior request when the next call observes it.

The four A-poison-A realm rows passed in one PID each with fresh execution count
one, clean host and DOM prototypes, input/prior-reply/module-export isolation,
and Promise-then poison survival. Cleanup success covered timeout, interval,
immediate, listener, unresolved-promise, async-global survival, all five console
methods, seven-source retention, and all six existing direct CJS paths (including
both saved-main terminal forms). Dedicated cleanup-failure workers proved
real fixture-DOM listener and synthetic timer removal exceptions are fatal before
reply and that a later call, not the failing call, starts recovery. The worker
wraps the VM-local `createDOM`, instruments every actual Element prototype once,
observes nonzero real saved-main listeners, and proves their listener maps empty
before reply; the raw-`createDOM` mutation fails this witness. Cleanup failure
covered ordinary and
accessor-backed native Errors, hostile native accessors, poisoned Error/Reflect
intrinsics, primitive, null, hostile object getters, Proxy, semantic business
input, before/boundary/nested-final-timer rejection, a recursively built native
TypeError whose escaped 8192-character message and escaped/newline/control-heavy
32768-character stack retain a real frame, one fatal missing-input request, and
late post-success exit. The long failure and its next clean request use the same
PID. Its primary observed sequence remained exactly three process starts, with
the attempted `T` attributed to `before the next request` and recovery using
request `N+2`. A dedicated uncounted fault-injection worker replaces the private
serializer with a 300000-character value; the host rejects that over-limit
envelope fatally without a reply, keeps stderr bounded, and recovers only in a
new process.

## Saved-layout receipt and family conversion

The once-provider stores its cache, lock, successful construction count, and one
cleanup registration on the canonical pytest `Session`. Both
`test_preview_savedlayouts_page` and `tests.test_preview_savedlayouts_page`
therefore share one immutable-byte receipt, while cleanup removes the attributes
so another pytest invocation cannot reuse stale state. It builds the detached
22-key receipt through the existing production
Api/controller/store/settings/atomicio sequence. It isolates
`LOCALAPPDATA` with a session temporary root, forces and restores `_use_legacy`,
delegates every `os.fsync`, restores `_save_locked`, validates durable strict
UTF-8 JSON and the committed reader, shuts both Api objects down, clears created
owners, returns through a nested construction frame, runs GC, and proves every
Stage-B-created Api/state/document/controller/reader weak reference is dead and
no newly retained reader remains. The observed single build used exactly 19
fsync calls, preserved production ID/revision continuity, captured
the first Apply as pending, and retained the later persisted Apply. Fifty-five
independent decodes had no alias. Permanent duplicate-import witnesses exercise
both provider orderings against one Session and require one object, one
construction, one cleanup registration, and 19 receipt fsyncs. The external
mutation probe repeats both orderings on two fresh Session owners, runs cleanup,
and proves a new owner receives a new object.

Task 3 converted all 62 saved-family rows to one session-scoped worker. The 55
main rows now decode immutable receipt bytes afresh and no longer construct
state, Api objects, page trees, input files, or subprocesses. The three owner
rows and four capture/dev rows retain their per-case production setup and
assertions. Their direct fsync counts remain `10 + 4 = 14`; combined with the
once receipt's 19 calls, the saved-family candidate total is exactly 33 instead
of the baseline 1,059. Raw JUnit proves the healthy family used one positive PID
and request ordinals `1..62`, reducing its business Node starts from 62 to one.
The qualification-only owner/capture setup remains a separately owned four
fsync calls. Saved-only remains exactly 33; combined saved plus qualification is
exactly `19 + 14 + 4 = 37` in either module order.

## Remaining family conversion and order evidence

Saved layouts now execute all four real programs through `saved-main`,
`saved-owner`, `saved-capture`, and `saved-dev`. The unchanged one-shot entrypoints
also pass the seven-case direct matrix, including both saved main terminal forms,
missing-argv failures, corrupt-input failures, 21 ordered saved-dev log lines,
and the one expected detached theme error. The saved realm qualification now
runs real `saved-main/reversed` before its poison and on final A; every execution
reports source count one and stays in one PID.

The exact 62-ID normal, reverse, and seed-`20260926` shuffle files passed in fresh
pytest processes. Their final-newline SHA-256 values are respectively
`6f11fa999a776f3861f3ae7495ddfd5ed00516127189d7b6268f1ad7817c7726`,
`f1aac69a97ca0db28adaf793a20d6171df275ebb9a0d496394fce08f220ff1e2`,
and `6d0a4a3a2868b89bf8e8a6717b12ef1807d937f6d6348f3e9ef1db1dcca95a30`.
Each run passed 62 rows with one PID, request ordinals `1..62`, zero cleanup,
and 33 total saved-family fsyncs. Fresh single-process invocations of main,
owner, capture, and dev each passed with request ordinal one. Separate repeated
A-A and `main/reversed -> owner/saved -> capture/boundary -> dev/dev ->
main/reversed` checks stayed in one PID, reported source execution count one for
every request, zero cleanup, and stable A output apart from the deliberately
fresh realm token.

Task 4 converted the remaining 65 Fleet Sharing, 17 group-backward, and 21
label-marker Node rows to their module-local session workers. Fleet retains its
real Python setup and both shutdown assertions; group and marker retain a fresh
finite-JSON copy of production `marker_choices()` on every request. Their
per-row page files, tree construction, and Node subprocesses are gone. The three
CJS programs remain direct CLIs and now expose the same scenario completion only
when evaluated by the worker. Fleet's one-shot path still suppresses controlled
bridge diagnostics, while worker replies pin one Watch error or ordered Start/
Stop errors only in their expected scenarios. Group dev retains five ordered log
diagnostics and one generated ID in positions two, three, and five. The two
dialog scenarios still execute exactly `12 + 132 = 144` inner combinations.

The final healthy normal run passed all 165 Node rows in `21.24s` observation
with exactly four process starts, one PID per family, request ordinal sets
`1..62`, `1..65`, `1..17`, and `1..21`, zero cleanup, 14 direct fsyncs, and one
19-fsync receipt for total 33. The four complete files passed all 205 rows in
`24.79s` observation with the same four business PIDs, 43 direct fsyncs, and
62 total production-case fsyncs. Their JUnit SHA-256 values are
`f3352a2d93933be8e56bcf554eb7ecc94a7723b0c7ca55122967e19779c2322b`
and `e40afd7cae3e08736edb539d73aef55a385cfcf632e32875ccbc9a514e18fe2b`.

Fresh reverse, seed-`20260926` shuffle, and cross-family round-robin runs each
passed all 165 rows with the same four starts, exact request sets, zero cleanup,
and 33 fsyncs. Their observations were `21.04s`, `21.04s`, and `22.29s`; their
JUnit hashes are `1b34eb8e310df4d76c4c00ad1fe36e23cd7f5480dfd043f73c5f373cd896bcd7`,
`f1a6b9c351023f056d48b6be37029660fbcc5c825b482512e6be439deebfd24c`,
and `66e79821243117ecd33d2e13c349836cf8dbdfe80d03e02b267e6081fc6956a8`.
The final-newline argument-list hashes remain collected
`60a253410671d0ac475c414940f007943ff96f4faebc30f0f1aaef9009e549fc`,
reverse `2dff54f5b75dcc262527eedb319b5bf6a7d3def17dae212261b0696529caa718`,
shuffle `44823cd4ec00d5e92da597845ac3c2e16b8de6c0edf3cac521b7dc4605fbe39c`,
and cross-family `183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1`.
The cross-family first cycle is exactly Fleet Sharing, group backward, label
markers, and saved layouts. The four real A-poison-A qualification rows supply
same-PID repeated/A-B-A execution and no host, realm, input, result, module,
diagnostic, or cached-execution poison.

## Mutation and restoration matrix

`/tmp/stage-b-baseline/mutations.py` contains one literal, ordered 71-recipe
registry partitioned exactly `14/16/41` across Tasks 3/4/5. Every recipe has one
unique canonical sentinel and anchored regex, exact typed
pytest/external/synthetic owner, kind-specific masking rules, one or more literal
edits with an explicit root, frozen mutated/restored expectations, and an
explicit `available_from_task`. Ordered internal variants carry their own exact
sentinel/regex and restoration cycle without increasing the recipe count. The six
corrected owner mappings and four restored-only IDs are pinned explicitly; exact
saved-main `reversed` belongs to every Task 3 pytest restored command and every
Task 4 pytest restoration unless it is already the selected owner, while the
three helper IDs remain owned only by late-rejection restoration.
After the synchronized Task 4 literal/probe correction, the deterministic
registry manifest SHA-256 is
`6cdaf58e982decaf9256246b34a3dc68ec75f611e254514a231f4a8bf8e92c44`.
The regenerated recursive artifact manifest is
`6460134c11c3d6b481ecbcf11cefcecfec5797d47118fa2a7119ae09548420b0`,
and the refreshed Task 2 identity-gate record is
`7ccf650d6af664a7087345cab21d182a8e36b05aaab6919db3efb904409ee515`.
It also freezes the read-only external adapter at SHA-256
`4d8e99bf87cb07196f458e693a5cd97b3a5a9aa97630e772ab434591463a359b`.

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

The receipt probe imports both saved-module identities from that root and calls
them in both orders, 55 calls per fresh fake Session, through one measured
builder. It requires one build and one cleanup registration per Session, runs
the cleanup, proves all cache attributes absent, and proves the second Session
does not reuse the first object. The cache-bypass edit must fail this probe. The
owning Python file remains covered by the root digest.
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
from the corrected registry. Runtime review replaced three superseded synthetic
realm recipes with real regressions: suppressing the post-dispatch final drain,
dropping a native Error stack, and reverting native Error diagnostic arguments
to ordinary object detachment. The native-stack recipe now owns two ordered
pytest variants: stack omission and shrinking the encoded envelope ceiling to
the decoded stack ceiling. The latter reaches only the dedicated long-stack
same-PID sentinel. The remaining realm recipes perform real context cache/reuse,
source-result reuse, and host-parsed input injection. The receipt recipes alter
the actual pending capture, production ID source, durable read, `os.fsync`
delegation, writer/environment restoration, reader ownership, and once-provider
construction; no recipe inverts its own assertion or uses a mutation-only worker
flag. The partition remains exactly `14/16/41`. All 14 Task 2 recipes ran through
the typed dispatcher as 15 mutation executions: 14 pytest executions and the
external receipt-count probe. Each produced its exact sentinel, rejected masking,
restored exact bytes/hash/diff/status, and passed the registered restored probe.
The ordered result file is `/tmp/stage-b-task2-mutations.json`, SHA-256
`aefe90925275ee0a2a17795dd99f1f49e400e7d24358b5f50166977abb32c464`.
The provider's `pending_receipt` literal is unique, so no unconverted business
caller needed a temporary source edit.

Task 3 revalidated the exact current 14-name `TASK3_RECIPES` partition after the
real saved conversion, then ran all 14 names in declared order (16 mutation
executions because the native-stack and saved-context recipes each own two
variants). The added saved-context variant returns raw untracked `createDOM` and
fails only the real-listener witness. Every mutation failed at its registry-owned
sentinel, rejected masking, restored exact bytes/SHA-256/binary diff/NUL-delimited
status, and passed its registered restored probe. All 15 restored pytest
executions included and passed exact saved-main `reversed`; the external receipt
probe supplied the sixteenth execution. The ordered result is
`/tmp/stage-b-task3-mutations.json`, SHA-256
`eb0e752901d09ef5e99601881f077169accdea6a19d162b6e88cf672c8cd2774`.
Task 4 then validated and executed its exact 16 canonical recipes in declared
order. The first six mutate real adapter selection/isolation, group source
re-execution, marker root release, business-failure retention, and fatal
no-replay boundaries. Four external fatal probes independently launch one bad
process and one recovery process for malformed NDJSON, wrong family, unknown
protocol, and unknown scenario; this overhead is not included in the permanent
cleanup-failure property's exact value three. The final six pin Fleet diagnostic
content/order, both group dialog matrix dimensions, deferred marker roster, and
the exact 165-ID inventory. Every pytest restoration also passed saved-main
`reversed` as an anti-mask companion unless that recipe already owned the saved
realm row. All defects reached their unique sentinel without masking, then
restored exact bytes, SHA-256, binary diff, and NUL-delimited status before their
registered recovery probe. The ordered result is
`/tmp/stage-b-task4-mutations.json`, SHA-256
`c5668ea8a66769f191c62b50a5b417aa88e3199ee1421600b5dc527fd499f311`.
Exactly 16 names and 16 results exist. The final Task 5 41-recipe slice and final
71-recipe aggregate remain pending.

## JUnit property ownership

The combined 20-ID JUnit contains exactly two qualification properties on each
of the seven qualification owners and none on helper IDs. Worker starts are
`1/1/1/1/1/3/0`; qualification fsync values are `0/0/0/0/4/0/0`, in declared ID
order. Each `(node ID, property name)` occurs once. Qualification values are not
folded into baseline or production-case arithmetic.

The Task 3 saved-family JUnit contains exactly one worker family, PID, request,
and direct-fsync property on each of 62 rows. It has one positive PID, request
ordinals `1..62`, direct fsync sum 14, and exactly one receipt owner: saved main
`reversed` with build `saved-layout-main-v1` and receipt fsync value 19. The
candidate saved total is therefore exactly 33. The final saved-only XML is
SHA-256 `328c539e1b89ce7a9ffd1310d72b4a85b5838f7721e3105786b41a419059309f`.
Saved-first and qualification-first 69-row runs each reported exactly 14 direct,
19 receipt, and four qualification fsyncs for total 37; their XML hashes are
`791f014f769c54fea5a5912a047e8a59a9862e94234b8120cbe493f71fc1b0b1`
and `3bd52095da83c6da2ef626caf3cd72d33314beb06e1de58e94c7b2c7701fc517`.
The qualification-first aggregate including all 13 helper rows passed 82 tests
with the same 37-fsync arithmetic (XML SHA-256
`90ef98d5f530d5b2a2083f31aef376e3f8f6b57cb288889e7a15fc7948b32acd`).
Normal, reverse, shuffle, and cross-family artifacts all passed the same
cardinality and aggregate audit. The final relevant JUnit contains exactly 225
passes: 205 existing target rows, 13 helper rows, and seven qualification rows.
Its existing target properties prove four business PIDs, request counts
`62/65/17/21`, direct fsync sums 14 for the Node subset and 43 for all target
rows, one receipt value 19, and totals 33/62. Qualification starts remain
`1/1/1/1/1/3/0` and qualification fsync values remain `0/0/0/0/4/0/0`.
Every property address is unique and helper rows own none. The JUnit SHA-256 is
`cc3895d8b4b2010a77864f3b3666cee07a17dc2aa8d018a69a0e8114b65b5085`.

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
symmetric-difference checks. Task 3 reran fresh relevant and complete collection
before editing: exact counts remained 225/16,617, and the actual ID files matched
both frozen actual and expected files byte-for-byte with hashes
`bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe` and
`d04dff36b8cb278dac3c410bca86e271e17899ce16272c9062886a48f28220c3`.
Task 3 review repeated those fresh collections after the ownership correction
with the same counts, byte equality, and hashes. The 62 saved IDs and their
decorator ASTs remained exact after conversion; only the three approved
saved-function signature substitutions occurred. Task 4 again collected the
relevant selection as exactly 225 unique IDs,
byte-for-byte equal to the frozen Task 2 order with final-newline SHA-256
`bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe`,
and then passed all 225 in `31.39s` observation. Task 4 did not run or claim the
complete 16,617-case outcome; that remains Task 5.

## Reviews, final scope, and frozen heads

Task 2 self-review found only its six original approved implementation/result
paths plus the authoritative plan correction: strict helper and helper contract,
shared worker, seven-ID qualification module, receipt provider added without
converting a business caller, this ledger, and the corrected Task 2 plan text.
The follow-up runtime reviews found and closed four defects in the worker's
completion/detachment boundary: same-poll publication after a due callback,
native Error stacks lost as accessors, diagnostic Error objects reduced to `{}`,
and an encoded-envelope parser ceiling incorrectly equal to the smaller decoded
stack ceiling. Task 3 then activated the already-declared real saved adapters:
the worker replaces primitive page selectors with fresh VM-side manifest
decodes, provides the VM-owned assertion and dev URL/Event seams used by the
existing programs, requires an exported completion, extracts exactly one
terminal PASS from diagnostics, and exposes real-program realm evidence for the
saved qualification. Review then moved receipt ownership from duplicate module
globals to the canonical pytest Session and moved DOM/listener observation from
the bootstrap-only DOM to every actual fixture-created DOM. The three saved
fixture files changed only at their CommonJS completion wrappers; their scenario
bodies and assertions are unchanged. No production, web, workflow, dependency,
lockfile, configuration, packaging, or `screenshot_dom.cjs` byte changed.
Task 4 added only the three remaining business modules, their three CJS
programs, the qualification module, and this ledger. The shared worker needed no
new committed change: Fleet's fixture supplies its missing assertion fallbacks,
and marker root release is proved inside the marker program. All 15 protected
hashes from the plan remain exact. Final Stage B review, executable head, and
evidence head remain pending.

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
and exact post-creation identity orders. Task 3 additionally proves real
saved-family execution, one healthy saved PID,
62 requests, and the saved `1,059 -> 33` fsync endpoint. Task 4 proves all four
real families, four healthy business PIDs, 165 requests, the all-205 62-fsync
endpoint, exact order independence, and its 16-recipe mutation slice. It does not
claim the complete-suite outcome, Task 5's remaining mutations, final Stage B
scope review, or hosted acceptance.
