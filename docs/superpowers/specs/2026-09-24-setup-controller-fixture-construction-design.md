# Setup controller fixture construction optimization — design

## Status

Approved design. Implementation is test-only and requires a separate reviewed
plan. It must preserve all 188 `tests/test_ui_setup_controller.py` testcase
identities and every production-strength persistence boundary exercised after
fixture construction.

## Purpose

Remove redundant durability work from the initial construction of synthetic
profiles used by the setup-controller test fixture without weakening codec,
filesystem, controller, or publication coverage.

The optimization is deliberately narrow:

- `seed_profile()` remains atomic by default for schema, profile, integration,
  native-codec, and every other caller;
- only the `setup` fixture in `tests/test_ui_setup_controller.py` explicitly
  requests a test-only publisher for its four newly created DAT files;
- encoding and encode-output readback verification still run through
  `codec.write_document()`;
- controller create operations still use the real atomic staging, rewrite,
  preference-copy, publication, and selection-persistence paths.

This design makes a structural work claim only: 136 setup-fixture cases create
four initial DAT files each, so the explicit fixture path removes 544
fixture-construction fsync calls. It makes no Windows, Linux, suite, job,
runner-efficiency, critical-path, or wall-clock speedup claim.

## Authority and measured baseline

The source baseline is merged `main` commit `c23788e3` (`Consolidate generated
verifier and Alerts tests (#287)`). The relevant authorities are:

- `AGENTS.md`;
- `tests/setup_fixtures.py`;
- `tests/test_ui_setup_controller.py`;
- `tests/test_ui_setup_schema.py`;
- `wingman/evesettings/codec.py`;
- `wingman/evesettings/setup_profile.py`;
- `wingman/evesettings/profilecopy.py`;
- `wingman/atomicio.py`;
- the successful Stage 3 artifacts at
  `/tmp/wingman-stage3-{windows,ubuntu}`.

`PRODUCT.md` and `DESIGN.md` do not govern this change because it alters no
product behavior or rendered interface.

### Hosted hotspot evidence

The successful Stage 3 artifacts are PR #287 run `35994945673`, attempt 2:

- Ubuntu job `107621270623`;
- Windows job `107621270652`;
- synthetic merge `ab2028f55f080e6067d7cc62002451f96171fa68`;
- PR head `db2185768b919331c54370d3532215e53d5583bd`;
- base `8d5b93058d9de3def9c17d222ba2d665eb0ba87b`.

Direct parsing of the downloaded JUnit and timing JSON gives:

| Observation | Ubuntu | Windows |
|---|---:|---:|
| Complete identities | 16,605 | 16,605 |
| Passed | 16,591 | 16,538 |
| Intentional platform skips | 14 | 67 |
| Failures / errors | 0 / 0 | 0 / 0 |
| Setup-controller identities | 188 | 188 |
| Setup-controller skips | 0 | 0 |
| Setup-controller testcase sum | 3.185s | 42.301s |
| Cases using the `setup` fixture | 136 | 136 |
| Those cases' testcase sum | 2.964s | 40.384s |
| Other controller cases' sum | 0.221s | 1.917s |

The complete Ubuntu and Windows identity sets are equal. Each platform's skip
list matches the already-published Stage 3 comparator record; the two platforms
are not expected to have equal skip lists because the suite contains explicit
platform-only coverage.

The timings identify a Windows-specific hotspot and motivate examining repeated
filesystem work. They are observations from one hosted run only. They do not
establish that this design will save any particular duration.

## Existing construction and persistence boundaries

The controller `setup` fixture currently:

1. installs the lossless test codec transport;
2. calls `seed_profile()` for a source profile;
3. calls `seed_profile()` for a recipient profile;
4. builds the real profiles controller and points its selected context at the
   source.

Each `seed_profile()` call constructs two nonexistent DAT files through
`codec.write_document()`. The codec path:

1. JSON-serializes the `Document` envelope including `had_crc`;
2. runs codec encode;
3. rejects empty or wrong-signature output;
4. decodes that exact encoded output;
5. requires the decoded envelope to equal the input envelope;
6. computes the content revision from the verified output bytes;
7. invokes backup;
8. publishes the bytes.

The default publisher is `atomicio.write_bytes_atomic`, which writes a temporary
file in the destination directory, flushes it, fsyncs it, and replaces the
destination with sharing-violation retries. Because each destination is new and
has no predecessor, the controller fixture currently pays that durability cost
four times before the test body starts.

The test bodies exercise different persistence work and must remain unchanged:

- `profilecopy.stage_copy()` uses `atomicio.copy_atomic()` for recognized DATs;
- `setup_profile.stage_setup()` uses `copy_atomic()` for recipient-local YAML
  and INI files;
- rewritten staged DATs use the default atomic `codec.write_document()` path
  with expected revisions;
- `profilecopy.publish_new()` performs the final new-directory publication;
- controller selection persistence continues through the real settings update;
- codec, staging, publication, cleanup, and settings failures remain injectable;
- external-writer and destination-creation races remain observable.

The optimization may change construction only. It may not suppress fsync,
replace, retry, or publication behavior process-wide or for the controller body.

## Design

### 1. Add one named test-only fresh-file publisher

Add a private, clearly named publisher in `tests/setup_fixtures.py`, such as
`_publish_fresh_file(path, data)`. It is test support, not a general-purpose
atomic I/O API.

Its contract is exact:

- the destination must not exist;
- open it with exclusive creation (`O_CREAT | O_EXCL | O_WRONLY`, plus
  `O_BINARY` where available);
- use a regular standalone file, never a hardlink, reflink, symlink, copied
  session template, or shared backing object;
- use a mode consistent with the atomic temporary-file path where the platform
  exposes meaningful mode bits;
- loop until every byte has been written, handling legal partial writes;
- treat a zero-byte write as failure rather than looping forever;
- close the descriptor before returning;
- if writing or closing fails, close what remains open, remove the partial
  destination when possible, and re-raise the original failure;
- do not call fsync;
- do not create a temporary neighbor;
- do not call `os.replace` or `atomicio.replace_with_retry`;
- do not create or consult a shared template.

Exclusive creation is load-bearing. The helper is valid only for fixture files
whose containing profile was just created and whose DAT paths are known to be
absent. A duplicate destination must fail rather than overwrite or merge.

The helper must accept the same `(Path, bytes)` shape expected by the
`publish` keyword of `codec.write_document()`. It must not encode a document
itself.

### 2. Keep `seed_profile()` atomic by default

Extend `seed_profile()` with an optional keyword-only initial-DAT publisher.
The ordinary call shape and result remain unchanged. Conceptually:

```python
def seed_profile(
    tmp_path,
    *,
    case="recipient",
    name="Base",
    initial_dat_publish=None,
) -> ProfileFixture:
    # Existing profile construction remains unchanged.
```


When `initial_dat_publish` is absent, call `codec.write_document()` without a
`publish` argument. That preserves its existing atomic default exactly.

When it is explicitly supplied, pass it only as:

```python
codec.write_document(
    path,
    document,
    backup=lambda path: None,
    publish=initial_dat_publish,
)
```

Do not bypass `codec.write_document()`, pre-encode fixture bytes, skip the
verifying decode, or compute revisions separately. The lossless codec transport
continues to replace subprocess transport only; codec validation and filesystem
publication remain real.

Avoid binding an atomic or fast publisher as the `seed_profile()` default
argument. An eager function default would obscure whether the atomic default is
still being exercised and would make later monkeypatch/instrumentation behavior
depend on import time. `None` means “omit the override and use the codec's
existing default.” The production codec signature and its current default are
not changed by this design.

### 3. Opt in only from the controller `setup` fixture

The `setup` fixture in `tests/test_ui_setup_controller.py` passes the named
fresh-file publisher to both calls:

- source account DAT;
- source character DAT;
- recipient account DAT;
- recipient character DAT.

No other fixture or caller opts in. In particular, these remain on the default
atomic path:

- `tests/test_ui_setup_schema.py`;
- `tests/test_ui_setup_profile.py`;
- `tests/test_ui_setup_integration.py`;
- native codec tests;
- every schema/profile/integration caller found by repository search;
- production callers.

The pytest fixture signature remains exactly `setup(tmp_path, monkeypatch)`.
`tests/fixtures/ui_setup_page.cjs` imports it and calls
`setup.__wrapped__(Path(temp), patch)` in a direct Python subprocess. Adding a
fixture parameter, requiring pytest injection, or changing positional order
would break that Node boundary even if ordinary pytest collection stayed green.

### 4. Preserve all fixture bytes and identities

Fast construction must produce the same files as atomic construction:

- identical encoded DAT bytes;
- identical decoded documents;
- identical Python/JSON value types and mapping/list order;
- identical `had_crc` values;
- identical SHA-256 content revisions;
- identical source and recipient account/character IDs;
- identical filenames and relative paths;
- identical YAML and INI bytes, including source LF and recipient CRLF line
  endings;
- identical tree discovery results after path normalization;
- identical setup profile manifests after path normalization;
- identical pytest node IDs and collection order.

The fresh publisher changes publication mechanics only. It must not change
fixture data, file names, document factories, source/recipient distinctions,
codec transport, profile names, or controller settings.

### 5. Preserve per-case isolation

Every test invocation continues to build source and recipient profiles in its
own fresh `tmp_path`. There is no session-scoped profile, shared byte template
on disk, hardlink fan-out, or mutable cache.

Isolation checks must establish:

- separate atomic and fast fixture roots do not alias;
- every regular fixture file has one link;
- corresponding files are not `samefile()` aliases;
- mutating one fast fixture cannot alter another;
- source and recipient profiles remain distinct within one fixture;
- trying to create the same profile twice still fails.

The duplicate-profile failure may occur at exclusive profile-directory
creation before DAT publication. The contract is that duplicate construction
never silently reuses or mutates the existing profile.

## Acceptance tests

All new executable evidence stays in the two authorized test files. Existing
schema, profile, integration, and codec tests remain unchanged and provide
independent regression coverage.

### A. Atomic-versus-fast parity

Construct equivalent source and recipient profiles in independent fresh roots,
once through the default atomic path and once through the explicit fresh-file
publisher. Compare:

1. the complete relative file inventory and every file's bytes;
2. decoded account and character `Document` values;
3. `had_crc` for each document;
4. JSON representations that retain key order and distinguish JSON boolean and
   numeric types;
5. content revisions from `codec.read_snapshot()`;
6. normalized `tree.discover()` output;
7. normalized `setup_profile.capture_manifest()` output.

Normalization may remove only the deliberately different temporary root prefix.
It must retain server/profile/file names, kind, IDs, order, sizes, hashes, and
all other semantic fields.

### B. Source/recipient and local-preference distinctions

The parity evidence also pins the distinctions already asserted by schema tests:

- source IDs `10` / `11` versus recipient IDs `20` / `30`;
- source `had_crc=True` versus recipient `had_crc=False` where defined by the
  fixture documents;
- source YAML and INI use their exact LF byte strings;
- recipient YAML and INI use their exact CRLF byte strings;
- source and recipient private sentinels remain different;
- document and manifest ordering remain unchanged.

### C. Isolation, link, and duplicate witnesses

Create at least two fast fixtures under independent directories and prove:

- no corresponding file is a hardlink or shared file identity;
- `st_nlink == 1` for each regular fixture file where reported;
- changing bytes in one fixture does not change the other;
- no session template path exists;
- duplicate profile creation is refused and leaves the original bytes intact.

### D. Construction fsync witness

Instrument `wingman.atomicio` without replacing or suppressing the process-wide
`os.fsync` function. Patch the module's `os` binding to a delegating proxy whose
`fsync()` records the call and then invokes the real function. Do not mutate the
shared `os` module object. Setting `atomicio.os.fsync` by attribute changes
`os.fsync` for every importer in the process.

Using equivalent source-plus-recipient construction:

- the default atomic path records exactly four fsync calls;
- the explicit fresh-file path records zero fsync calls;
- encoded bytes and all parity checks remain equal.

This is a work-count witness, not a duration benchmark. It must not assert an
elapsed-time threshold.

### E. Controller-body persistence witness

Build the real controller fixture with the fast publisher, then reset or phase
tag the construction instrumentation before running a representative successful
review/create operation.

The test must prove separately that:

- fixture construction used the fast path and contributed zero fsync calls;
- the controller body subsequently invoked real atomic file persistence;
- staged DAT copies remain atomic;
- staged YAML/INI copies remain atomic;
- both rewritten DATs remain atomic and revision guarded;
- `profilecopy.publish_new()` performs the final publication;
- selection persistence still runs after publication;
- the created profile contains the expected complete bytes;
- construction counts and body counts are reported/asserted as different
  phases rather than merged into one total.

The witness may wrap publication to observe it, but must delegate to the real
publisher. It may instrument the atomic functions or the delegated `os` binding,
but must not replace controller-body publishers with non-atomic writes.

### F. Existing failure and race coverage

The complete existing controller file must remain green, including:

- codec read and write failures;
- staging and cleanup failures;
- selected-file and full-manifest changes;
- external writers during encoding/staging;
- a destination created immediately before final publication;
- publication boundary error codes;
- preference-file changes and removals;
- selection persistence false/raise/I/O paths;
- controller start, worker, and completion failures;
- closed-client probes at every boundary;
- offer consumption/restoration and replay prevention.

The relevant schema, profile, integration, native-codec, codec, profile-copy,
and atomicio suites must also remain green. Their unchanged default calls are
part of the proof that atomic fixture construction still exists outside the one
controller hotspot.

## Mutation qualification

All mutants are temporary and uncommitted. Restore the changed source exactly
after each probe, run the intended witness, and verify the final diff contains
no mutation or witness-only support.

A red test counts only when it fails at the intended assertion. An unrelated
codec error, cleanup error, collection error, or later controller assertion is
not sufficient.

### 1. Make the fast publisher atomic

Temporarily implement the fresh publisher by delegating to
`atomicio.write_bytes_atomic()` or add an fsync to it.

Required result: the construction work-count witness fails because fast
construction records nonzero fsync work. Byte parity is expected to remain
green and does not qualify this mutant by itself.

### 2. Bypass a representative controller-body atomic publisher

Temporarily route one representative body write—preferably one rewritten staged
DAT—through the fresh publisher or another non-atomic write while leaving
fixture construction unchanged.

Required result: the controller-body persistence witness fails in the body
phase. The fixture work-count witness alone must not kill or qualify this
mutant.

### 3. Alter direct bytes, order, or line endings

Apply independent temporary defects to the fast construction path:

- change one encoded DAT byte or substitute a different document;
- disturb representative document/list or mapping order;
- change source LF or recipient CRLF preference bytes.

Required result: atomic-versus-fast byte parity, decoded document/type/order,
content-revision, discovery, or manifest assertions fail at the specific
boundary. A broad later controller failure is not the intended witness.

### 4. Share or hardlink a template

Temporarily publish a DAT via a shared file or hardlink, or make two fast
fixtures alias one on-disk source.

Required result: the isolation/link witness fails through `samefile`, link
count, mutation isolation, or the no-template assertion. Byte equality alone
must not allow this mutant to survive.

## Identity and hosted acceptance

### Local identity contract

Before implementation, freeze the complete ordered 188-node controller
inventory. After implementation require:

- exactly 188 unique controller node IDs;
- identical ordered IDs before and after;
- no added, removed, renamed, or reordered controller case;
- exactly 136 cases still using the `setup` fixture;
- no collection or runtime skip in the controller file;
- the Node direct invocation remains executable with the unchanged wrapped
  fixture signature.

The structural calculation remains:

```text
136 setup-fixture cases × 2 profiles × 2 DATs = 544 initial DAT publications
```

The optimized path changes those 544 publications from fsynced atomic replace
to exclusive fresh-file publication while preserving codec work. It does not
change the number of testcases or controller operations.

### Full local verification

Run with Node available and the built release settings codec installed:

- focused new parity, isolation, work-count, and body-persistence witnesses;
- `tests/test_ui_setup_controller.py`;
- `tests/test_ui_setup_schema.py`;
- `tests/test_ui_setup_profile.py`;
- `tests/test_ui_setup_integration.py`;
- `tests/test_evesettings_codec.py`;
- `tests/test_evesettings_profilecopy.py`;
- `tests/test_atomicio.py`;
- the executable setup-page Node boundary containing the direct
  `setup.__wrapped__` invocation;
- full pytest with complete skip inspection;
- `node scripts/js_smoke.js`;
- the applicable setup-page Node harness tests;
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`;
- Ruff check and Ruff format check;
- `git diff --check`;
- exact changed-path allowlist and protected-path audit.

No Node or settings-codec availability skip is acceptable full-suite evidence.

### Hosted comparison

The implementation results document must compare a successful hosted run with
the pinned Stage 3 artifacts in `/tmp/wingman-stage3-{windows,ubuntu}` and
record:

- branch head, synthetic merge, base, workflow run, job IDs, and artifact IDs;
- exact Windows and Ubuntu complete identity sets;
- exact 188-controller identity sets and ordering;
- pass/failure/error counts;
- each platform's normalized skip tuples compared with its Stage 3 tuples;
- confirmation that controller tests have no skips;
- per-file controller testcase sums;
- the 136 setup-fixture-case sums where artifact data permits;
- Windows testcase observations, including the slowest retained controller
  identities;
- job and Test-step duration as observations only;
- proof of no production, workflow, dependency, configuration, marker, or
  selection change.

Windows and Ubuntu complete identity sets must remain equal. Skip lists are
compared within platform against the baseline, not forced to equal each other.
Any new availability skip, failure, error, identity drift, or unexplained skip
change is a stop.

No hosted timing result, favorable or unfavorable, may be described as a
speedup from a single run. The accepted claim remains only the verified removal
of 544 fixture-only fsync calls.

## Exact committed scope

The complete implementation tranche may commit only:

- `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`;
- `docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md`;
- `docs/ci-setup-controller-fixture-construction-results.md`;
- `tests/setup_fixtures.py`;
- `tests/test_ui_setup_controller.py`.

The two test files own both the helper change and its acceptance/mutation
witnesses. Do not modify `tests/test_ui_setup_schema.py` merely to relocate
coverage; its unchanged default-path assertions are part of acceptance.

Explicitly forbidden without a new design review:

- any file under `wingman/`, including `codec.py`, `setup_profile.py`,
  `profilecopy.py`, and `atomicio.py`;
- other test modules or Node fixtures;
- `.github/` workflows;
- `pyproject.toml`, `uv.lock`, dependencies, or packaging;
- pytest configuration, markers, selectors, budgets, or shard manifests;
- test deletion, consolidation, renaming, or parameter reduction;
- shared/session fixture templates or persistent general-purpose fast I/O
  support.

The existing `publish` keyword on `codec.write_document()` is sufficient. If
implementation discovers that a production change or persistent helper outside
the two authorized test files is required, stop and redesign rather than
broadening scope.

## Alternatives rejected

### Direct fixture serializer

Rejected. Writing `b"\x7d" + json_payload` or storing pre-encoded DAT bytes
would duplicate codec behavior in test support and bypass the encode/readback
verification that protects document type, order, CRC, signature, and revision
semantics. A fixture optimized by no longer exercising the codec would weaken
the controller suite rather than remove only redundant durability work.

### Session-scoped profile template

Rejected. Constructing one source/recipient profile pair and copying, cloning,
reflinking, or hardlinking it into each test introduces shared-mutation and
filesystem-identity risks, changes creation/discovery metadata, complicates
Windows behavior, and can make duplicate construction or isolation bugs
invisible. The approved design keeps fresh per-test directories and files.

### Global fsync suppression

Rejected. Patching `os.fsync`, replacing `atomicio` publishers for the whole
fixture lifetime, or using an autouse switch would also weaken controller-body
persistence and unrelated tests. The explicit publisher is passed only to four
initial DAT writes, and instrumentation delegates to the real fsync.

### Production fast-path API

Rejected. Production writes may replace existing EVE settings and must retain
backup, retry, fsync, and atomic replacement behavior. The optimization is
valid only because the four targeted files are synthetic, nonexistent,
per-test fixture destinations. No product/runtime API is needed.

## Risks and mitigations

### Default-bound publisher behavior

Function defaults are evaluated at definition time. Binding the fast helper—or
an atomic function intended to be patched later—as a `seed_profile()` default
would make call behavior depend on import order and could silently change the
meaning of “default.” Use `None`, omit `publish` for ordinary calls, and pass the
fresh publisher only at the controller fixture call sites.

The production codec's existing bound default is unchanged. Tests that need to
observe it should instrument the function's module dependencies, not assume
that replacing `atomicio.write_bytes_atomic` after import rewrites the codec's
stored default.

### OS metadata drift

Atomic replacement publishes a tempfile's metadata; direct exclusive creation
publishes the destination file's metadata. Use an explicit creation mode
compatible with the tempfile path and test regular-file/link properties. Do not
claim preservation of unsupported timestamps or platform-specific birth time.
The product contract for these synthetic fixtures is bytes, identity, regular
file status, path, and isolation; any discovered permission or metadata
difference that affects discovery, manifests, native codec behavior, or hosted
Windows execution is a stop.

### Partial writes and close failures

`os.write()` may legally write fewer bytes than requested. A one-call publisher
would risk truncated but apparently successful fixture files. Loop over a
memory view until complete, reject zero progress, and include close in the
success boundary. On failure, remove the partial destination where possible and
preserve the original exception.

### Exclusive creation assumptions

The helper is unsafe for an existing destination by design. Keep it private to
test fixtures, require `O_EXCL`, and test duplicate creation. It must never grow
into a replacement helper.

### Monkeypatching the shared `os` module

Python modules share the same `os` object. Patching `atomicio.os.fsync` by
attribute mutates global `os.fsync` and can suppress or count unrelated writes.
For instrumentation, replace only `atomicio`'s module binding with a delegating
proxy. The proxy calls the real fsync and records calls; it does not alter the
shared module.

### Node's direct wrapped-fixture invocation

The setup-page harness bypasses pytest injection and directly invokes
`setup.__wrapped__(Path(temp), patch)`. Preserve the fixture's two-argument
signature and keep all new opt-in behavior internal to its body. The relevant
Node scenario must be run explicitly; ordinary pytest collection cannot prove
this boundary.

### A fast fixture can hide body regressions

A global or overly broad publisher override could make all create operations
fast and leave ordinary success assertions green. The phase-separated body
witness and body-publisher mutant are mandatory. They must show zero
construction fsyncs and real body atomic persistence in the same controller
flow.

## Stopping rules

Stop implementation and return to design review if any of these occurs:

1. preserving codec encode/readback verification requires production changes;
2. the fast publisher must support existing-file replacement;
3. any caller other than `test_ui_setup_controller.setup` must opt in;
4. a session/shared template, hardlink, reflink, or persistent cache is needed;
5. controller-body atomic writes or selection persistence must be weakened;
6. the fixture's `setup(tmp_path, monkeypatch)` signature must change;
7. any of the 188 controller identities changes;
8. mutation evidence requires another test module, Node fixture, or production
   helper change;
9. source/recipient bytes, line endings, CRC, order, revisions, discovery, or
   normalized manifests differ;
10. local or hosted Node/codec availability skips appear;
11. Windows and Ubuntu complete identities diverge;
12. a workflow, dependency, configuration, marker, selector, budget, or shard
    change appears necessary;
13. evidence can support only a duration assertion rather than the structural
    544-fsync work count.

## Required implementation self-review

Before publication, the results document must record a final review covering:

- placeholder scan — no unfinished marker, omitted-body placeholder, debug
  output, or mutation-only note remains;
- arithmetic — `136 × 4 = 544`, while total controller identities remain 188;
- parity — atomic and fast bytes, documents, types/order, CRC, revisions,
  paths, discovery, and normalized manifests agree;
- distinctions — source/recipient IDs and exact LF/CRLF preference bytes remain
  different as designed;
- isolation — no shared file identity, hardlink, or template exists;
- persistence — default seed construction records four fsyncs, fast records
  zero, and controller-body atomic writes/publication remain observable;
- mutation restoration — all four mutation classes fail at intended assertions
  and every temporary edit is restored;
- identity/skip consistency — local and hosted inventories and platform skip
  comparisons match their baselines;
- scope — only the three approved documents and two approved test files are in
  the tranche diff;
- protected paths — no production, workflow, dependency, configuration,
  packaging, marker, selector, budget, shard, or Node fixture change;
- claim discipline — report testcase/job timings only as observations and make
  no performance or speedup claim.

## Follow-up boundary

Successful implementation proves only that one synthetic controller fixture can
publish four brand-new verified DAT files without atomic durability work while
all real controller persistence remains intact. It does not authorize broader
fixture caching, production I/O changes, test selection changes, workflow tiers,
budgets, or Windows sharding.
