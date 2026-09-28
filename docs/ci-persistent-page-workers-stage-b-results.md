# Persistent page workers — Stage B results

**Current authority:** executable `a187a24b8729ef253e788ddbd06b3c2d61fe4c19`.
The **Final-review fix round — current local endpoint** section supersedes all
prior local executable/evidence freezes below. Earlier Task 1–6 records and
75/86-execution hashes remain historical. This evidence update is bound to the
direct documentation child with subject `test: refreeze cross-version worker evidence`;
its literal SHA is recorded locally after parent-owned creation. Publication
remains stopped.

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
one, exact A/poison/A run values, clean host and DOM prototypes,
input/prior-reply/module-export isolation, and Promise-then poison survival.
Cleanup success covered timeout, interval, immediate, listener,
unresolved-promise, async-global survival, all five console methods,
seven-source retention, and all six existing direct CJS paths (including both
saved-main terminal forms). The worker wraps the VM-local `createDOM`, and its
VM-only `trackElementClass` hook also wraps Fleet's actual custom Element class
after declaration. Both saved-main and Fleet observe positive real-listener
counts and zero after cleanup. A dedicated Fleet fault makes the actual removal
method throw: the worker emits no reply, exits, and only a later request starts a
new PID and again proves positive-to-zero cleanup. Synthetic timer removal is
likewise fatal. The direct Fleet CLI sees no hook and remains unchanged. Cleanup
failure covered ordinary and
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
diagnostics with exact methods, generated/stale IDs, Forward/Back/Clear suffixes,
rendered strings, and detached argument arrays on first and final A as well as the
poison request. Internal wrong-suffix and empty-argument counterexamples are both
rejected. The two dialog scenarios still execute exactly `12 + 132 = 144` inner
combinations. Marker cleanup is no longer asserted by a fixture global: the host
tracks actual contexts in a Set, releases before reply and again in `finally`,
derives `retained_realms: 0` independently, and clears the Set at shutdown.

After the Task 4 review correction, a fresh healthy run passed all 165 Node rows
in `23.95s` observation with exactly four process starts, one PID per family,
request ordinal sets `1..62`, `1..65`, `1..17`, and `1..21`, zero cleanup, 14
direct fsyncs, and one 19-fsync receipt for total 33. The four complete files
passed all 205 rows in `42.92s` observation with the same four business PIDs, 43
direct fsyncs, and 62 total production-case fsyncs. Their JUnit SHA-256 values
are `5236ab51b121d6fc4833331a89e9110c37f334a3135d605e28e825b925f65578`
and `b5a2c2d9890a7b9cc5b425189d904a58589a81f2956cb34e4b58c4e2797acd88`.

Fresh normal, reverse, seed-`20260926` shuffle, and cross-family round-robin runs
each passed all 165 rows with the same four starts, exact request sets, zero
cleanup, and 33 fsyncs. Their observations were `37.76s`, `34.28s`, `22.15s`,
and `21.42s`; their JUnit hashes are
`8a92078311b9f4c5549f6bfd4b4a661d3098e261a8f7e910e582421844d1edd6`,
`e11456eb1ba664934c640738c59f98cfe104246865ebace811d81d5369068b7b`,
`49c337160dc12df67750b21bf6a26024ac3734551b675e23d8df00e2b6efd99f`,
and `d236b52f2e2d4f4ab8af17c0227dd3e71e7f041d3dc38e2c81bb982c2e7933d9`.
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
After the Task 4 review correction, the deterministic registry manifest SHA-256
is `b4c00b009abd94e1cd1c44e1ccfa248b4ca36f85578cb91cbe92f2f20badcfed`.
The regenerated recursive artifact manifest is
`9a87d26c46d744238ac843e085cda3705c16d7ad0950c937f16a8e0913c7e7e1`,
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
Task 4's review correction then revalidated and executed its exact 16 canonical
recipes in declared order. The first six mutate real saved adapter selection,
Fleet prior-completion reuse, group source re-execution, the host marker-realm
release helper, business-failure retention, and fatal no-replay boundaries. The
Fleet mutation is caught by the real A-B-A fresh-output contract; the marker
mutation leaves the actual context in the host Set and fails before reply. No
fixture-only cached page or cleanup global remains. Four external fatal probes
independently launch one bad
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
`8b7cde0250aa0f3701e34018cf094315eee5bd91663e22e03c11ee8c5d3f3710`.
Exactly 16 names and 16 results exist. Eleven pytest restorations run the saved
`reversed` anti-mask either as owner or companion, and all 16 recipes report
exact restoration.

Task 5 qualification found 18 registry edit loci superseded by final Task 2–4
source: the three unmatched bool-ID recipes, `schema-bool-duration-discarded`,
`schema-missing-fields-discarded`, both new family source-reexecution recipes,
saved pristine-intrinsics, both failure-detachment recipes, all three
cleanup-resource recipes, all three rejection-boundary/reference recipes,
`cleanup-before-reply`, and `late-rejection-attribution`. Already-matching
host/module/context/missing-field/fatal mutations were also corrected so their
real defects reached the intended assertion rather than a timeout, undefined
name, or another sentinel. The String-poison qualification required matching
Task 3 saved-context/source attribution edits. No canonical recipe name, owner,
sentinel, order, kind, restoration rule, or cardinality changed.

Review then strengthened the affected witnesses. `moduleWasIsolated` now
accumulates over every CommonJS execution; the three family module mutants inject
the real host module into the business wrapper and no longer force the result.
Fleet Sharing and label-marker source mutants now bypass actual later-request
`runCommonJS` execution by reusing the prior cached completion. The host-import
mutant still reads every source and continues startup, then host-requires only
`screenshot_dom.cjs`; exact cache and `module.children` paths trigger the module
sentinel, while an unrelated startup `ENOENT` counterprobe remains a crash. The
poison completion now contains nested arrays, and two variants independently
replace the captured array-index String operation in `detachJson` and
`encodeJson`.

All 41 Task 5 recipes reran in declared order and produced 43 executions. Every
defect reached exactly its canonical sentinel, rejected other sentinels and
masking, restored exact bytes/hash/diff/status, and passed the registered
restored probe. The ordered Task 5 result SHA-256 is
`61c52d4dbae6d0cf9883685c4baec80404417e51945c2cb738456bffc613131f`.
The all-41 review invocation observed `814.32s`.

Because the final String poison changed executable source, Tasks 3 and 4 were
also rerun from the current tree rather than relying only on their historical
records. The current Task 3 and Task 4 result hashes are
`3737878be46a510d9572b7c258a459881d0b30b96b7658374f3f94b1baff6140`
and `097d53be5f8c362ee4041f3eecaf5d743af8db57e79a0a7b599ed77c81f5cb78`;
the review rerun observed `634.98s`. The exact aggregate is therefore 71
canonical recipes, partitioned `14/16/41`, and 75 actual executions. The seven
bounded representative executions have SHA-256
`b8e6126e422e383d4aecd6d53a73322718820c7c0f972fb2cd6cc094bcbf619f`.
The final deterministic registry, recursive artifact, and final-source manifest
SHA-256 values are respectively
`6896a03ba6c07d885117328dc9037d7440315ebf645b28d2924a6e3929350664`,
`4df54b2b2d4a3d3b03e9598494035d43aebf8da65cfe58d2b651d37a83ab7d79`,
and `f6ff96209f41b00c3c09a1f768d038569c44ecba170728fee0573b91b9b8429c`.
The final external tooling suites pass 61 checks.

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
Every property address is unique and helper rows own none. The latest Task 4
review-correction JUnit SHA-256 is
`3c901f2fcec5244946946c69001e6a6ca695eef7d7568a8badf9832413797de1`.

The review-final 225-row run passed in `31.70s` (`35.58s` process elapsed)
with raw JUnit SHA-256
`9bddfc33829928cc264e9e38da75e2bac10dbc9abe9b0d49d2ac45b1ad56eafd`
and testcase sum `26.757s`. The final auditor again found exactly four family
PIDs, ordinals `1..62/65/17/21`, direct sums `14/43`, receipt value `19`, healthy
totals `33/62`, qualification starts `1/1/1/1/1/3/0`, qualification fsyncs
`0/0/0/0/4/0/0`, and no missing, duplicate, unexpected-owner, or extra
`stage_b.*` property.

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
and then passed all 225 in a fresh `50.56s` observation. Its raw JUnit SHA-256
is `3c901f2fcec5244946946c69001e6a6ca695eef7d7568a8badf9832413797de1`.
A fresh complete collection also remained exactly 16,617 IDs and byte-equal to
the frozen Task 2 order; Task 4 did not execute or claim that complete-suite
outcome, which remained Task 5.

Task 5 reran all endpoint selections after the String-intrinsic correction. The
exact observations were:

| Selection/order | Outcome | Pytest time | Process elapsed | Raw JUnit SHA-256 |
|---|---:|---:|---:|---|
| Relevant | 225 passed | `31.70s` | `35.58s` | `9bddfc33829928cc264e9e38da75e2bac10dbc9abe9b0d49d2ac45b1ad56eafd` |
| Node collected/normal | 165 passed | `21.77s` | `25.28s` | `e751a3a2df8aca7065b9bf6397abbe640b3709e980e17c4626ac944a19895345` |
| Existing target | 205 passed | `22.09s` | `25.83s` | `837fc897bba28a8d48dc515acaa930454f0ae1f95ad011d08b63edb16239da1e` |
| Node reverse | 165 passed | `21.34s` | `24.83s` | `11c4e9800631b601cfce07befb56fd9df4a289ec5a7d89932c88fe0385ba78da` |
| Node seed-20260926 shuffle | 165 passed | `21.51s` | `25.08s` | `db6374565bea5f654e3fb58b98b673e7507b76581ad2c3dd7831b205784ab0b8` |
| Node cross-family | 165 passed | `21.72s` | `25.26s` | `e2876b0bd691996fc6f993c45ea45bae36d46c37c5939e9c39350915c8675827` |

The relevant and complete structured collection SHA-256 values are
`6578618090ba75bd3ae672ba630f7f7786ff4de096d213737d2e5b2b5bebaa7c`
and `2131c640d9377e3ccf86c331ea677d5f3afc38a964d3e58f142f28164e3f4408`.
Their ID files are byte-identical to the frozen Task 2 orders and retain hashes
`bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe`
and `d04dff36b8cb278dac3c410bca86e271e17899ce16272c9062886a48f28220c3`.
Every order had one PID per family, exact request sets, and the same 33-fsync
healthy Node total; the 205 run had the same 62-fsync target total.

The documented release prerequisite was built and installed before the complete
suite: `uv sync --locked --extra dev`, Node `v26.5.0`, and release codec SHA-256
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
The review-final exact 16,617-order complete suite passed as
`16,603 passed + 14 skipped` in `463.80s` pytest time and `469.73s` process
elapsed; testcase sum was `422.512s`. Raw JUnit and timing-summary SHA-256 values
are `40bc4e7d3dd502185f2620bd14b43713d58ce561076f0949f3b640606a88fec2`
and `04f289869f7bdb59476801e2207790b61a59e4b344bbdc6af6d7efe0e6c29b63`.
The 14 normalized skips exactly match accepted Linux Stage A: one clip sharing
rule, three profile-copy junction rows, two DPAPI/WinDLL rows, one real preview
message-pump row, three Win32 binding rows, one pystray Windows backend row, one
additional two-case UI-setup junction skip, and one Wanderer DPAPI row. No Node,
codec, target, qualification, or unexpected native skip occurred.

All ten JavaScript files passed `node --check`; the DOM suite passed 35 tests;
the six-entrypoint direct CLI matrix passed; and the previous-worker selection
passed 963 tests in `114.64s`. JS smoke passed directly and through all seven
pytest wrappers. Cargo passed its one regression test. Global Ruff lint and
format passed (`521` Python files format-clean).

The historical Task 5 candidate executable hashes are:

| Path | SHA-256 |
|---|---|
| `tests/test_preview_savedlayouts_page.py` | `aa609f34b95880a59875b6a8f29106dd137f55305f66035262968322b325eab3` |
| `tests/test_fleetsharing_hydration.py` | `f79391237114b15a64829cae29f6e0733b037d6399e31d0db3408d6146e4c3ce` |
| `tests/test_preview_group_backward.py` | `e904e5e6c2fa72fc5c3ab6655feacd5a19aa02bd84b27e9d2aba44299756f143` |
| `tests/test_preview_labelmarkers_page.py` | `ad19bb7c978dccf08a0c3fb90e622f7ddd47d172ce687a505341709bb5f49bbb` |
| `tests/fixtures/preview_savedlayouts.cjs` | `19c56f15b34ad9cd6c824456268c16d8f3900d68d13d2c3b8d5e128bd9bf15bf` |
| `tests/fixtures/preview_capture_sessions.cjs` | `25f872cf26769681dbce85e2809883190b0d76fd1f02e8147c0d32fd1f2d9691` |
| `tests/fixtures/preview_dev_capture.cjs` | `d1bb23f5d0dc4b1c33921819a5a12d6a6adb98f22f182ee58f1723530d36cdc5` |
| `tests/fixtures/fleetsharing_page.cjs` | `512a5736f31ea0f483ffe5037ba670a4c65ac6db0b1f7bd52497df643cb6f78a` |
| `tests/fixtures/preview_group_backward.cjs` | `2eddb4cb6d2aa7cbca3e5e304ebc74f4bbab7d40c4228bf28be7ef4e44a4be1b` |
| `tests/fixtures/preview_labelmarkers.cjs` | `b98469ca8c1a208ec9e6104cfb3e05bc415e5bf6351f0ba7a4e0cb08ed7221ee` |
| `tests/node_scenario_worker.py` | `d478a76f4c59f3a807fc56498f1c29269c5a7019f5b95eee6050751ff2bde0af` |
| `tests/test_node_scenario_worker.py` | `154ff76e9b2a71d32c3e8214fc184b612b79db3021a1eee65fcc5788867f76fa` |
| `tests/fixtures/page_scenario_worker.cjs` | `f4743bed1a64c9a83fdf6a9056f732d6afdcdfda15878df2c273a807583eb44a` |
| `tests/test_persistent_page_workers.py` | `d42deb08c0719101784416f0cb8fe5b39614bf1b291e8a4161a6dedcec052f32` |

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
Task 4's initial conversion added only the three remaining business modules,
their three CJS programs, the qualification module, and this ledger. Its review
correction changes the shared worker, Fleet fixture, qualification module, plan,
specification, and ledger: Fleet now supplies a real listener-removal method and
uses the VM-only tracking hook; retained-realm ownership is host-observed; group
diagnostics have exact persistent grammar; and the two circular fixture markers
are removed. No production, web, workflow, dependency, lockfile, configuration,
packaging, or `screenshot_dom.cjs` byte changed. The correction's current diff is
exactly seven approved paths, the full range remains the approved 17 paths, and
all 15 protected hashes remain exact.

Task 5 added one narrowly scoped executable qualification correction: the poison
request now mutates global `String`, and both manual array walks derive descriptor
keys through the already captured pristine `safeString`. This closes the exact
specification gap found by the pristine-intrinsics mutation; it does not alter a
business program, protocol, identity, property, or production path. The final
range remains exactly the approved 17 paths. The 15 protected hashes are still
byte-exact, and no diff exists under production, web, workflow, dependency,
lockfile, configuration, or packaging paths. CJS syntax, Python compilation,
global Ruff lint/format, documentation, packaging/version, structural
signature/decorator/body, diff-whitespace, restoration, registry, source, and
recursive-manifest gates all pass. The Task 6 local freeze and fresh evidence are
recorded below; independent maintainer review remains pending.

### Historical Task 6 polish, fresh verification, and local freeze

**Frozen executable head:** `a703f8d2b987a769979cd22d6daa680ab6e791ce`
(`test: strengthen persistent worker mutation witnesses`). The worktree was
clean when this head was frozen. All 14 executable files retain the SHA-256
values in the table above; Task 6 makes no executable or mutation-literal edit.

**Evidence-only head:** the direct documentation-only child of that frozen head
with subject `test: finalize persistent page workers Stage B` (this evidence
commit). Its full SHA is recorded literally in the local Task 6 completion report
after commit. A commit cannot embed its own content-addressed SHA; this exact
parent/subject binding avoids a fabricated hash or a self-referential evidence
amendment. The executable and evidence heads must not be conflated. Independent
review of this final range remains pending; the evidence commit does not claim
reviewed-head or hosted-candidate status.

`polish-core --fix` read every current file and the full 17-path cumulative diff,
loaded Python and JavaScript/CommonJS rules, and checked general quality, silent
failure, comments and interfaces locally. No high-confidence executable fix was
selected. CommonJS/direct CLI behavior, module-local fixture ownership, literal
mutation seams and cleanup ordering were intentionally retained. The only safe
corrections are documentation status: remove stale claims that the range is still
specification-only and distinguish completed local verification from pending
independent/hosted acceptance. No source movement, new identity, business-assertion
change, retry, target import, weakened cleanup, new receipt construction or Stage C
consolidation was introduced.

Fresh commands used `uv run --no-sync python -m pytest ... -q -rs` with raw JUnit;
the complete run additionally used `--durations=50`. Collections used the retained
`collect` plugin and explicit `ids-from-collection` conversion. Order commands
loaded only validated `.ids.txt` bytes through the same `validate_id_bytes` path
(shell array expansion was unavailable in this harness). Every run was a fresh
process; no failed test/order was retried to obtain green.

| Selection/order | Outcome | Pytest time | Process elapsed | Raw JUnit SHA-256 |
|---|---:|---:|---:|---|
| Helper | 13 passed | `9.09s` | `14.19s` | `fff4e2d13b8d35170c6a7d61ed863cb631f8d1c1a829bcbec5644cef5b862a9f` |
| Qualification | 7 passed | `12.16s` | `17.17s` | `675a0a33d7c15dba68af04e38cbf04bf62cdc51ed9a929bb760fda7d5bf9e83f` |
| Saved family | 62 passed | `9.03s` | `12.50s` | `85353045964ba5a2c3ed464bb6fa68d8821c01e4b476f8e8d0f00b1385c926bc` |
| Relevant | 225 passed | `55.16s` | `60.39s` | `a92f6781668b5d709b249a25ca5097de1ee2b9951ad6b7e28548ee8c438192ea` |
| Existing target | 205 passed | `43.50s` | `48.31s` | `f08e328b75594f1a3fe5ca41b63e2338fe7e7ab657c41e6ea8906ea7f644bf43` |
| Node normal | 165 passed | `39.52s` | `44.43s` | `166fe15fa5077050f79486c24576f6941ecd949e45ab3b5f3de1bede441b8015` |
| Node reverse | 165 passed | `33.90s` | `40.41s` | `3e7c51ea319d88b2d0e0c95de476b4ae1e94798afeac7ac7ff2c7637a30b698d` |
| Node seed-20260926 shuffle | 165 passed | `23.19s` | `26.88s` | `ac13d2bb1c088a7c073b39c42d8ea5b5f4a93b0291fc6b1e3dbc4f95a1a708b1` |
| Node cross-family | 165 passed | `23.06s` | `26.97s` | `a147529866467636fa1bd09ae926ca456b744782a4109a0ebbbda7055b470999` |
| Complete Linux | 16603 passed, 14 skipped | `471.10s` | `477.32s` | `93af14458a39a89ad436c408c94eba68b398087e7a7d5c336dc416d78e91f447` |

The fresh relevant/full collection bytes equal the frozen Task 2 reports and ID
files exactly: 225/16,617 unique IDs, unchanged ordered 217/16,609 subsequences,
and exactly eight approved additions. All 14 normalized Linux skips match Stage A;
no Node, codec, target, qualification or unexpected native skip occurred. Full
suite testcase sum is `428.904s`, XML suite time `470.847s`; these are distinct
from pytest time and process elapsed and remain observations only.

Raw-property audits passed on relevant, target, full and all four Node orders:
one positive PID per family, exact ordinal sets `1..62/65/17/21`, direct fsync
sums `14/43`, one receipt owner/value `19`, healthy totals `33/62`, qualification
starts `1/1/1/1/1/3/0`, qualification fsyncs `0/0/0/0/4/0/0`, and no missing,
duplicate, unexpected-owner or extra `stage_b.*` property. Supplementary fresh
runs passed saved reverse/shuffle (62 each), the other families alone (65/17/21),
both saved/qualification orders (69 each), and the qualification-first helper
aggregate (82); both 69-row orders and the 82-row run had exactly `14+19+4=37`
fsyncs. Seven representative single-ID processes each passed with ordinal one.
Four real family A-A-B-A sequences and the saved main/owner/capture/dev/main
sequence stayed in their family PID with source execution one and zero cleanup.
The seven-case/six-entrypoint direct CLI matrix retained all 21 success/missing-
argv/corrupt-input subprocess streams; exact terminal/dev/controlled diagnostic
checks passed. These disposable probes add no repository test identity.

The retained mutation authority was verified rather than relabeled as a fresh
mutation execution: all 71 names in the exact `14/16/41` partition, 75 executions,
seven representative executions, and 132 raw mutated/restored XML files passed
re-audit of owners, phase/outcomes, canonical sentinels, forbidden masking and
restored companions. All current match-once literals, 14 executable hashes,
registry/source/recursive manifests and prior result hashes are unchanged. The
61 collector/registry/restoration/manifest tooling tests passed fresh. Since no
executable byte or literal changed, the complete Task 5 mutation run remains the
applicable evidence; no replacement authority was generated.

Fresh additional gates: locked uv sync; Node `v26.5.0`; locked release codec
build/install/actual bundled-path availability and matching release/installed
SHA-256 `4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`;
Cargo `1 passed`; ten CJS syntax checks; DOM `35 passed`; direct JS smoke and
`7 passed` smoke wrappers; previous-worker selection `963 passed in 117.28s`;
packaging/version `110 passed`; global Ruff and format (`521` files); documentation
`7 passed`; Python compilation and external-tooling Ruff/format; exact six
signature substitutions and unchanged decorators; unchanged ASTs for the 12
nonconverted test functions (40 collected rows); byte-equivalent saved CJS bodies
outside their wrappers; numeric-validator-only helper change; exact 17-path scope
and all 15 protected hashes; final whitespace and leftover scans.

A local codec-path assertion initially called `.resolve()` on the documented
string return of `paths.codec_exe()`; wrapping it in `Path` corrected only the
probe and the unchanged installed binary passed. New local evidence scripts also
needed import-order/format cleanup. These local tooling corrections did not edit
repository executables or turn a failed business/order/full-suite run green.

### Reviewer-facing explanation and remaining boundary

The Python fixture retains the family process until pytest Session teardown,
including cross-module re-entry. Startup retains primitive source/markup text;
requests get fresh VM-owned wrappers, production script evaluation, DOMs,
intrinsics and decoded input. Polling carries primitive mailbox/completion data,
drains dispatched timer/rejection turns, removes real listeners and timers, then
releases the host-tracked realm before publication. Business failures detach and
retain the process; fatal protocol/cleanup failures emit no reply and require a
later separate restart. Late rejection preserves the attempted next-scenario
attribution and prior successful request context without replay.

The shared saved receipt is owned by the canonical pytest Session, not either
module-import identity. One real 19-fsync production sequence detaches immutable
bytes and restores environment, writer, legacy flag and reader ownership; every
main case decodes independently. Private coupling is limited to test process
observations and the existing production receipt seams; no public product API,
settings format or shipped runtime changes. Family-local duplication deliberately
avoids Stage C consolidation.

Self-review covered every specification invariant and stop condition. Prior
Task 1–5 review corrections are retained; no new independent Task 6 review is
claimed because subagents were explicitly prohibited. Maintainer review should
concentrate on the VM/rejection publication boundary, mutation-to-real-defect
binding, duplicate-import receipt ownership, direct CLI parity and raw-property
cardinality. Local verification is complete, but independent review and the
separately authorized logs-primary, rerun-aware Ubuntu/Windows hosted audit are
still open. No live browser or Windows smoke run was required or performed for
this test-only change. No timing or overall hosted acceptance claim is made.

## Final-review fix round — current local endpoint

**Frozen executable head:** `a187a24b8729ef253e788ddbd06b3c2d61fe4c19`
(`test: preserve assertions on older Node runtimes`). It follows the four-boundary
fix at `a5bcadf629755bd44863a8ed6471400f41727565`. A scoped independent
rereview found that invalid-Date equality changed between Node 22/24 and Node
26; the worker now derives that compatibility decision from native
`node:assert/strict` and passes only the primitive boolean into each VM. RegExp
flag access also ignores getters absent on older runtimes. The complete
assertion differential passes on installed Node 18, 20, 22, 24, 25, and 26.

**Evidence-only head binding:** the direct documentation-only child of that
executable head with subject `test: refreeze cross-version worker evidence`
(this evidence update). Its literal SHA is recorded locally after parent-owned
creation, avoiding a self-referential commit hash. No executable edit followed
the freeze or the verification below.

### Four Important findings closed

- **Callback checkpoint:** the scheduler selects one earliest-due callback, with
  registration-order ties, then yields before another callback. The exact
  `first, microtask, second` witness passes. A rejection created by the first
  callback and caught only in the next is attributed to the current request,
  business-fails it, and recovers in the same PID. A native Node subprocess
  independently observes `first, microtask, unhandled, second`.
- **Fatal terminal admission:** the first fatal synchronously closes admission,
  closes readline and pauses stdin. Buffered lines, execution, and publication
  check that state. Fatal stderr is bounded and single-write; an independent
  100 ms timer exits 70 if the write callback stalls. Malformed and invalid lines
  followed in the same buffered write by valid return/non-returning bodies emit
  no reply, do not launch the stuck body, and terminate/reap with status 70 while
  stdin remains open. No subsequent request is needed to exit.
- **Bounded completion:** after settlement, four polls each query the mailbox,
  advance the allowance, dispatch at most one callback and yield. The following
  poll consumes the final mailbox and cleans up without dispatching. Dispatch
  never resets the allowance. The nested rejection remains a current-request
  failure; recurring immediates and overdue intervals finish with positive
  pre-cleanup handles, zero cleanup and same-PID clean recovery. The defective
  recurrence witness stops itself after 16 callbacks so mutation RED is a
  specific failure rather than a process timeout.
- **Strict assertions:** VM-owned `equal` uses SameValue; the relevant deep
  comparisons check primitive SameValue, arrays/own enumerable keys/prototypes,
  object data descriptors, Date and RegExp values, and qualified cycles. The
  24-case native differential covers signed zero, NaN, Date, RegExp, extra array
  properties, holes, prototypes, symbols, cycles and nested fixture shapes.
  Accessor, Proxy, revoked Proxy and proxy-prototype controls prove no getter or
  trap is invoked. Host assertion functions/objects are never injected. All
  actual fixture assertions remain unchanged and execute under the stricter
  facade; the original direct entrypoints still use native assertions.

These are internal subcases in the existing seven qualifications. There are no
new pytest IDs, changed business assertions, timeouts, public interfaces or
production paths. The initial two qualification RED failures reached the exact
callback-order and callback-rejection assertions. Independent disposable RED
subcases also reproduced unbounded immediate/interval draining, weak strict
assertions and buffered fatal admission. Their restored qualifications passed.
The retained RED files are `/tmp/stage-b-final-fix-red.xml` and
`/tmp/stage-b-fix/red-subcases.json`; all fresh final records are under
`/tmp/stage-b-fix/`.

### Fresh Task 5/6 verification

Every run below was a fresh process on the frozen executable. Pytest commands
used `uv run --no-sync python -m pytest`, `-q -rs`, and raw JUnit; the complete
suite added `--durations=50`. Collection used the retained structured collector,
explicit ID conversion and byte equality with the frozen Task 2 files. Ordered
runs validated the canonical ID lists before passing them to pytest. Exact argv,
exit status, process elapsed and outputs are paired command JSON/log artifacts.
No failed business, order, full-suite or mutation run was retried to obtain green.

| Selection/order | Outcome | Pytest time | Process elapsed | Raw JUnit SHA-256 |
|---|---:|---:|---:|---|
| Helper | 13 passed | `5.27s` | `7.88s` | `7dbadc71d6c78efbc62ba1d4b317735447245c0432493fc9e8bea2131e0f445f` |
| Qualification | 7 passed | `10.52s` | `13.22s` | `fb8eab996450fe8837f4e1fee549185eeb0b92a8327d477fe5b5c276b1fe127d` |
| Saved family | 62 passed | `7.19s` | `9.85s` | `43d87bdefca6fb547f134afa6423a6345dac870800f1d1218238490e2c9e9db1` |
| Relevant | 225 passed | `37.89s` | not separately recorded | `a32feb784798e0e58aa9029f1bb2002e611f360d8e3494f4fcf0516376d8df94` |
| Existing target | 205 passed | `25.00s` | `27.74s` | `e997dbf428741d5e3454ba7d6ccf4c3d574416e31ea02d7499ef2438e6421eda` |
| Node normal | 165 passed | `21.31s` | `24.84s` | `3a723d19ee42316d9d35b9e2569e7b9d7a1eafe61a0d50227886cc743494f922` |
| Node reverse | 165 passed | `21.26s` | `24.78s` | `854f544902cb06684821a2cb7f923457871c047a56a8dce5dbe942d3a0c06f28` |
| Node seed-20260926 shuffle | 165 passed | `21.58s` | `25.12s` | `dc55f423b56fedbe3f017e3e6ae72e4aa5e09308d519b0ddbae8d3d300772695` |
| Node cross-family | 165 passed | `21.35s` | `24.88s` | `72ed27dac7b817100d0c3d9b3829c3c150e391aa2aecbdba924128a17275c2bb` |
| Complete Linux | 16603 passed, 14 skipped | `458.84s` | not separately recorded | `c694a28f4e72882b5642e511a18b04b0cd0b65eb3401ecd1ca20de57972f5a28` |

The relevant/full ordered ID hashes remain
`bf6e8470cc470cd747015f2772d243e90b064b756984b09d2f0076fde1c6fffe` and
`d04dff36b8cb278dac3c410bca86e271e17899ce16272c9062886a48f28220c3`.
Their structured reports and ID files are byte-equal to the frozen Task 2
225/16,617 orders; the 217/16,609 baseline subsequences and eight additions remain
exact. All 14 normalized Linux skips equal accepted Stage A. No Node, codec,
target, qualification or unexpected native skip occurred.

Raw-property audits passed on the relevant, full, target and every Node order:
four family PIDs, ordinal sets `1..62/65/17/21`, direct fsync sums `14/43`, one
receipt owner/value `19`, healthy totals `33/62`, qualification starts
`1/1/1/1/1/3/0`, qualification fsyncs `0/0/0/0/4/0/0`, and no duplicate,
missing, unexpected-owner or extra property. The final cross-version-fix XML
suite time is `458.616s`. Timing values are observations, not acceptance
thresholds or speedup/critical-path claims.

Supplementary fresh gates passed:

- saved reverse/shuffle (62 each), standalone sharing/group/marker (65/17/21),
  both saved/qualification orders (69 each), and qualification-first with helper
  (82); the latter three runs prove exactly `14+19+4=37` fsyncs;
- seven representative single-ID runs with request ordinal one; four family
  A-A-B-A sequences and saved main/owner/capture/dev/main, with one family PID,
  fresh source execution one and zero cleanup;
- seven-case/six-entrypoint direct matrix, retaining all 21 success/missing-argv/
  corrupt-input subprocess streams and exact terminal/dev diagnostics;
- locked uv sync, Node `v26.5.0`, locked release codec build/install and actual
  bundled-path availability; the assertion differential additionally passes on
  installed Node 18, 20, 22, 24, 25, and 26; installed/release SHA-256 remains
  `4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`;
- Cargo 1, DOM 35, JS smoke directly plus 7 pytest wrappers, previous-worker
  selection 963, packaging/version 110, global Ruff lint/format (521 files),
  documentation 7, ten CJS syntax checks, Python compilation and ID-loader checks;
- exact six signature substitutions, unchanged decorators, unchanged ASTs for
  the 12 nonconverted test functions / 40 rows, saved CJS bodies unchanged
  outside wrappers, numeric-validator-only helper change, all 15 protected
  hashes and exact 17-path cumulative scope.

### Current mutation and manifest authority

All 71 names were rerun in declared order, partitioned `14/16/41`, producing
`16/17/54 = 87` executions. Every execution reached its exact registered
sentinel, rejected masking, restored bytes/SHA-256/binary diff/NUL status and
passed its registered recovery command. The separate raw-result re-audit
covered 156 XML files; the seven representative executions remain exact.
The previous 75/86-execution evidence is historical, not reused for this runtime.

The existing final-drain recipe now shortens the real checkpoint allowance; the
boundary-turn recipe batches real due callbacks. Twelve added internal variants
cover buffered fatal admission, immediate/interval quiescence, callback order,
strict equal, primitive SameValue, Date values, runtime-native invalid-Date
parity, array extras, prototype identity, Proxy inspection and RegExp values. The canonical names, typed owners, partition,
anti-mask companions and restoration rules remain unchanged.

| Authority | SHA-256 |
|---|---|
| Task 3 mutation results | `86d4420300d6c635e6dec1d395d58a32a112658be19b650647270106d4ec77b1` |
| Task 4 mutation results | `799c658ff0a2142e3516a3357055c44279d63d1bd4469fd54a6a15c21a6e882a` |
| Task 5 mutation results | `e721994749e093ed69d9d0aa77b0ce060a7ebecb8757b1df228360cbe467913a` |
| Registry manifest | `38c981aeb3bc8fc1674e389649ae82ccf6d89a7e0f87afaf28e9b3b6c2c61181` |
| Source manifest | `54449ec9547baeb543df3e2e321d2943b662443dac3cfe64dbda9a562fcaf01b` |
| Recursive artifact manifest | `535d1336d73ca292c31849ec0e73d1dff7b35cdf52004eabb2ef8fc6e005da9c` |
| Representative executions | `3e07d99705451c19989331841afb71f4e2f4240c084258747b59ce09a7f2ee47` |
| Mutation summary / raw XML hashes | `a6e131c939e3b5f044f9af139d66afe4674a75758d96baab50857470dca274e1` |
| Full timing summary | `3f15e324acb77057b3ef901ab5a1507cf27c2455b089b34f10c3bf9ab9ad93b3` |

The final external collector/registry/restoration/manifest suites pass 61 checks.
The prior authorities are retained separately before the explicit manifest
regeneration. The attempted regex-containing registry command was denied without
execution; the implemented array-key recipe instead uses a numeric-key predicate,
not an encoded blocked character. Local script import ordering/formatting needed
cleanup, recorded in its failing lint log; these tooling-only changes did not
alter repository executables or mask a failed runtime gate.

### Current executable hashes

| Path | SHA-256 |
|---|---|
| `tests/fixtures/fleetsharing_page.cjs` | `512a5736f31ea0f483ffe5037ba670a4c65ac6db0b1f7bd52497df643cb6f78a` |
| `tests/fixtures/page_scenario_worker.cjs` | `6d84b944f1540e1e76a9e2cc9339c1d92544768829b4dd79581ecfdc7f459463` |
| `tests/fixtures/preview_capture_sessions.cjs` | `25f872cf26769681dbce85e2809883190b0d76fd1f02e8147c0d32fd1f2d9691` |
| `tests/fixtures/preview_dev_capture.cjs` | `d1bb23f5d0dc4b1c33921819a5a12d6a6adb98f22f182ee58f1723530d36cdc5` |
| `tests/fixtures/preview_group_backward.cjs` | `2eddb4cb6d2aa7cbca3e5e304ebc74f4bbab7d40c4228bf28be7ef4e44a4be1b` |
| `tests/fixtures/preview_labelmarkers.cjs` | `b98469ca8c1a208ec9e6104cfb3e05bc415e5bf6351f0ba7a4e0cb08ed7221ee` |
| `tests/fixtures/preview_savedlayouts.cjs` | `19c56f15b34ad9cd6c824456268c16d8f3900d68d13d2c3b8d5e128bd9bf15bf` |
| `tests/node_scenario_worker.py` | `d478a76f4c59f3a807fc56498f1c29269c5a7019f5b95eee6050751ff2bde0af` |
| `tests/test_fleetsharing_hydration.py` | `f79391237114b15a64829cae29f6e0733b037d6399e31d0db3408d6146e4c3ce` |
| `tests/test_node_scenario_worker.py` | `154ff76e9b2a71d32c3e8214fc184b612b79db3021a1eee65fcc5788867f76fa` |
| `tests/test_persistent_page_workers.py` | `a4882080ece4baa17df46f006023ecdd06ed2146c510556b861d13ee0a93d34f` |
| `tests/test_preview_group_backward.py` | `e904e5e6c2fa72fc5c3ab6655feacd5a19aa02bd84b27e9d2aba44299756f143` |
| `tests/test_preview_labelmarkers_page.py` | `ad19bb7c978dccf08a0c3fb90e622f7ddd47d172ce687a505341709bb5f49bbb` |
| `tests/test_preview_savedlayouts_page.py` | `aa609f34b95880a59875b6a8f29106dd137f55305f66035262968322b325eab3` |

### Polish, explanation and remaining boundary

Changed-diff `polish-core --fix` examined the full worker and qualifications,
relevant helper/lifecycle code, current plan/spec/results and mutation ownership,
with Python and CommonJS rules. No additional safe executable fix was selected.
The work remains test-only and preserves the real fixture bodies, direct CLI
contracts, existing Python worker lifecycle and canonical receipt ownership.
No consolidation, retry, target host-import or production change was introduced.

Reviewer focus was the one-callback yield, fourth-checkpoint/final-query cutoff,
fatal admission fence versus buffered input, and assertion/proxy inspection.
An independent evidence review approved the freeze. Independent whole-branch
review reproduced those four boundaries, then its scoped rereview identified the
remaining Node-version-dependent invalid-Date behavior. That residual was
corrected test-first and verified across installed Node 18, 20, 22, 24, 25, and
26 before the complete suite and mutation matrix were rerun. Hosted Ubuntu/Windows
acceptance, publication and timing attribution remain open. No remote/API
operation, push, PR, dispatch/rerun, merge, release or installation into the user
application was performed.

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
saved-family execution, one healthy saved PID, 62 requests, and the saved
`1,059 -> 33` fsync endpoint. Task 4 proves all four real families, four healthy
business PIDs, 165 requests, the all-205 62-fsync endpoint, exact order
independence, and its 16-recipe mutation slice. The historical Task 5 record proves
its then-current 71-recipe/75-execution mutation matrix, direct compatibility, exact local
16,617 outcome and skips, final properties, protected hashes, and exact 17-path
scope. Task 6 additionally records local polish, fresh verification, independent
evidence and whole-branch review, the resolved cross-version residual, and
frozen-head separation. It does not claim publication or Stage B hosted acceptance.

**LOCAL CONCLUSION:** Stage B preserves all 205 existing target identities and
all 12 existing helper identities, adds exactly eight approved identities,
serves the healthy 165 Node-owning rows through four family processes, and
reduces measured production-case persistence from 1,059 to 33 fsyncs for those
rows and from 1,088 to 62 fsyncs for all 205 rows. Qualification overhead is
reported separately. Timing values are observations only and establish no
speedup or critical-path effect.
