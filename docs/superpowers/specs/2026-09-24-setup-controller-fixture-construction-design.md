# Setup controller fixture construction optimization — design

## Status

Approved design, revised after review. Implementation is test-only and requires
a separate reviewed plan. It must preserve all 188 existing
`tests/test_ui_setup_controller.py` testcase identities in their existing order,
add exactly two bounded witness identities, and preserve every
production-strength persistence boundary exercised after fixture construction.

## Purpose

Remove redundant durability work from the initial construction of synthetic
profiles used by the setup-controller test fixture without weakening codec,
filesystem, controller, or publication coverage.

The optimization is deliberately narrow:

- `seed_profile()` remains atomic by default for schema, profile, integration,
  native-codec, and every other caller;
- only the repeated `setup` fixture in `tests/test_ui_setup_controller.py`
  explicitly requests the test-only publisher for operational fixture
  construction; the two bounded witnesses invoke it only for qualification;
- encoding and encode-output readback verification still run through
  `codec.write_document()`;
- controller create operations still use the real atomic staging, rewrite,
  preference-copy, publication, and selection-persistence paths.

This design makes a structural work claim only: the same 136 existing
setup-fixture cases create four initial DAT files each, so the explicit fixture
path removes 544 fixture-construction fsync calls. The two new witnesses are
additional qualification coverage and do not consume the pytest `setup`
fixture, so they do not change that calculation. The design makes no Windows,
Linux, suite, job, runner-efficiency, critical-path, or wall-clock speedup
claim.

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
- use the module-level `os` binding in `tests.setup_fixtures` for `os.open`,
  `os.write`, `os.close`, and cleanup through `os.unlink` so behavior and
  failure paths are directly observable without mutating the shared `os`
  module object;
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

No other reusable fixture or existing caller opts in. The two approved witness
tests may call the helper or `seed_profile()` explicitly to compare and qualify
the path, but they do not change any reusable fixture. In particular, these
remain on the default atomic path:

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
- identical tree discovery results after the narrowly allowed normalization;
- identical setup profile manifests after path-root normalization;
- all 188 existing pytest node IDs preserved in their existing order, followed
  by exactly two bounded witness identities.

The fresh publisher changes publication mechanics only. It must not change
fixture data, file names, document factories, source/recipient distinctions,
codec transport, profile names, or controller settings.

### 5. Preserve per-case isolation

Every test invocation continues to build source and recipient profiles in its
own fresh `tmp_path`. There is no session-scoped profile, shared byte template
on disk, hardlink fan-out, or mutable cache.

Isolation checks must establish:

- separate atomic and fast fixture roots do not alias;
- every fast-published file is an ordinary regular file, remains writable, and
  has exactly one link;
- corresponding files are not `samefile()` aliases;
- mutating one fast fixture cannot alter another;
- source and recipient profiles remain distinct within one fixture;
- stable ordinary metadata—file identity, file type, size, permission/mode
  bits, and link count—does not change across codec readback, discovery, and
  manifest capture;
- trying to create the same profile twice still fails.

Do not compare volatile access/change/birth timestamps or require atomic and
fast publication to have identical filesystem timestamps. The duplicate-profile
failure occurs at profile-directory creation and proves only that profile
construction does not silently reuse an existing directory. It is separate
from, and insufficient for, the publisher's required existing-file/O_EXCL
contract.

## Acceptance tests

All new executable evidence stays in the two authorized test files. Add exactly
two non-parameterized witness tests to the end of
`tests/test_ui_setup_controller.py` so the ordered baseline 188-node inventory
remains an exact prefix:

1. one comprehensive publisher/parity/isolation/failure-contract witness;
2. one construction-versus-controller-body persistence witness.

Exercise the helper's failure branches inside the comprehensive test with a
loop and precise per-branch assertion messages rather than parametrizing them
into additional pytest identities. Neither new test requests the pytest
`setup` fixture; each constructs only the state its witness needs. Existing
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

Discovery normalization may remove only the deliberately different temporary
root/path prefix and `tree.Profile.modified`, whose value is the profile
directory's volatile `st_mtime`. Preserve every other `Tree`, `Server`,
`Profile`, and `SettingsFile` field, including list order, names, keys, kinds,
IDs, and file counts. Manifests contain no timestamp field: normalize only the
temporary path root and then require the complete `ProfileManifest` and every
`FileRevision` name, size, hash, and order to match exactly.

### B. Source/recipient and local-preference distinctions

The parity evidence also pins the distinctions already asserted by schema tests:

- source IDs `10` / `11` versus recipient IDs `20` / `30`;
- source `had_crc=True` versus recipient `had_crc=False` where defined by the
  fixture documents;
- source YAML and INI use their exact LF byte strings;
- recipient YAML and INI use their exact CRLF byte strings;
- source and recipient private sentinels remain different;
- document and manifest ordering remain unchanged.

### C. Isolation, metadata, duplicate, and direct publisher failure witnesses

Create at least two fast fixtures under independent directories and prove:

- no corresponding file is a hardlink or shared file identity;
- each fast file is regular, writable, and has `st_nlink == 1`;
- the ordinary stable metadata named above survives readback/discovery/manifest
  observation;
- changing bytes in one fixture does not change the other;
- no session template path exists;
- duplicate profile creation is refused and leaves the original bytes intact.

In the same comprehensive witness, call the fresh publisher directly with
module-level `os` proxies and exercise all of these executable contracts:

1. an existing destination is refused by `O_EXCL` and its bytes are unchanged;
2. repeated partial `os.write` results are looped until the complete payload is
   present before close;
3. zero write progress raises, closes the descriptor, and removes the partial
   destination;
4. a sentinel exception after an earlier partial write closes and removes the
   partial destination while preserving that original exception;
5. a sentinel close exception removes the destination and preserves that
   original close exception.

For failure cleanup, assert both path absence and the exact original exception
identity or sentinel. The duplicate-profile `mkdir` refusal is not evidence for
any of these publisher-level branches.

### D. Construction fsync witness

Capture the real `os` module first, then replace both module bindings with
separate delegating proxies:

- `tests.setup_fixtures.os` observes direct helper calls, including any
  accidental direct `fsync`, while delegating `open`, `write`, `close`,
  `unlink`, and all other attributes to the real module;
- `wingman.atomicio.os` observes atomic-writer `fsync` calls while delegating to
  that same real module.

Never set an attribute on either imported `os` object: Python importers share
that object, so attribute mutation would alter process-wide behavior. Replace
only each owning module's `os` binding, and make both proxies call the real
operation rather than suppressing it.

Using equivalent source-plus-recipient construction:

- the default atomic path records exactly four fsync calls through the
  `atomicio` proxy and zero through the `setup_fixtures` proxy;
- the explicit fresh-file path records zero fsync calls through both proxies;
- encoded bytes and all parity checks remain equal.

The separate channels are load-bearing mutation evidence: adding `os.fsync`
directly to the fresh helper must be detected by the `setup_fixtures` proxy,
while delegating the helper to `atomicio.write_bytes_atomic` must be detected by
the `atomicio` proxy. Qualify those two mutants independently; one detector may
not stand in for the other.

This is a work-count witness, not a duration benchmark. It must not assert an
elapsed-time threshold.

### E. Controller-body persistence witness

Build the real controller fixture with the fast publisher, then reset or phase
tag the construction instrumentation before running a representative successful
review/create operation.

The test must prove separately that:

- fixture construction used the fast path and contributed zero fsync calls on
  both proxy channels;
- the controller body subsequently invoked real atomic file persistence;
- exactly two staged DAT copies use `copy_atomic`;
- exactly two staged YAML/INI copies use `copy_atomic`;
- exactly two rewritten DAT publications use `write_bytes_atomic` after normal
  codec verification and revision checks;
- exactly one selection-settings publication uses `write_atomic`;
- the body therefore performs exactly seven categorized atomic fsyncs for the
  unmodified representative flow;
- `profilecopy.publish_new()` performs the final directory publication;
- selection persistence runs after publication;
- the operation completes successfully and the created profile contains the
  expected complete bytes;
- construction counts and body counts are phase-tagged rather than merged into
  one total.

Observe categories by wrapping the relevant atomic functions/publish callbacks
and delegating to the real functions. Account for the codec's definition-time
publisher default explicitly rather than assuming a later module-attribute
patch changes it. The witness may wrap `profilecopy.publish_new`, but it must
delegate to the real publisher. No controller-body write may be replaced by a
non-atomic write in the committed test.

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

### 1. Add direct fsync to the fresh helper

Temporarily call `os.fsync` from the fresh helper after writing and before
close, without delegating to `atomicio`.

Required result: the comprehensive construction witness fails because the
`tests.setup_fixtures.os` proxy records direct helper fsync work. The
`atomicio.os` channel must remain zero. An atomic-channel failure or byte-parity
failure does not qualify this mutant.

### 2. Delegate the fresh helper to the atomic writer

Temporarily replace the helper body with
`atomicio.write_bytes_atomic(path, data)`.

Required result: the comprehensive construction witness fails because the
`wingman.atomicio.os` proxy records atomic fsync work. The direct-helper channel
must remain zero. The direct-fsync mutant and this delegation mutant require
separate runs, intended assertions, and restoration records.

### 3. Bypass one rewritten body DAT atomically

After the normal codec encode, signature check, readback verification, and
revision checks, temporarily publish one rewritten staged DAT with a
replacement-capable direct writer such as `Path.write_bytes(data)` instead of
`write_bytes_atomic`. Do not use the exclusive fresh-file helper here: the
staged DAT already exists, so that would stop at `FileExistsError` and would not
exercise a completed non-atomic body operation.

Required result: setup creation still completes and final profile publication
still occurs, but the body witness fails its exact rewrite category/count:
rewritten-DAT atomic publications fall from two to one and total categorized
body fsyncs fall from seven to six. Failure through `FileExistsError`, codec
verification, revision validation, or publication refusal does not qualify this
mutant. The fixture construction count alone also does not qualify it.

### 4. Alter direct bytes, order, or line endings

Apply independent temporary defects to the fast construction path:

- change one encoded DAT byte or substitute a different document;
- disturb representative document/list or mapping order;
- change source LF or recipient CRLF preference bytes.

Required result: atomic-versus-fast byte parity, decoded document/type/order,
content-revision, discovery, or manifest assertions fail at the specific
boundary. A broad later controller failure is not the intended witness.

### 5. Share or hardlink a template

Temporarily publish a DAT via a shared file or hardlink, or make two fast
fixtures alias one on-disk source.

Required result: the isolation/link witness fails through `samefile`, link
count, mutation isolation, or the no-template assertion. Byte equality alone
must not allow this mutant to survive.

### Mutation-to-witness mapping

| Temporary mutant | Required witness identity | Intended failure |
|---|---|---|
| Direct helper `os.fsync` | Comprehensive publisher/parity/isolation/failure witness | `tests.setup_fixtures.os` channel changes from 0; atomic channel stays 0 |
| Delegate helper to atomic writer | Comprehensive publisher/parity/isolation/failure witness | `wingman.atomicio.os` channel changes from 0; direct channel stays 0 |
| Replacement-capable direct body DAT publication | Construction-versus-body persistence witness | operation publishes, rewritten atomic category changes `2 → 1`, body total `7 → 6` |
| Alter bytes, type/order, or line endings | Comprehensive publisher/parity/isolation/failure witness | exact bytes/document/revision/discovery/manifest distinction fails |
| Shared or hardlinked template | Comprehensive publisher/parity/isolation/failure witness | file identity/link/mutation-isolation assertion fails |

The five direct publisher failure branches are executable contracts within the
comprehensive witness, not extra parameter identities and not substitutes for
the mutation ledger above.

## Identity and hosted acceptance

### Local identity contract

Before implementation, freeze the complete ordered 188-node controller
inventory. After implementation require:

- exactly 190 unique controller node IDs;
- the baseline ordered 188 IDs are present byte-for-text, with no removal,
  rename, or relative reorder;
- because the two witnesses are appended, the baseline ordered 188 IDs remain
  the exact prefix and the two approved witness IDs are the only suffix;
- exactly two IDs are added: one comprehensive
  publisher/parity/isolation/failure witness and one construction-versus-body
  persistence witness;
- neither witness is parameterized into multiple identities;
- exactly the original 136 cases still use the pytest `setup` fixture;
- no collection or runtime skip in the controller file;
- the Node direct invocation remains executable with the unchanged wrapped
  fixture signature.

The structural calculation remains:

```text
136 existing setup-fixture cases × 2 profiles × 2 DATs = 544 initial DAT publications
188 existing controller IDs + 2 bounded witnesses = 190 controller IDs
16,605 hosted baseline IDs + 2 bounded witnesses = 16,607 intended full-suite IDs
```

With unchanged platform skips, the full-suite pass-count projections are 16,593
passed plus 14 skipped on Ubuntu and 16,540 passed plus 67 skipped on Windows.
These are identity projections, not timing or runtime claims.

The optimized path changes those 544 publications from fsynced atomic replace
to exclusive fresh-file publication while preserving codec work. The two new
witnesses disclose additional qualification work but do not alter the 136-case
fixture calculation.

Do not publish an anticipated controller or full-suite node-ID hash in the
design or plan. During implementation, write actual collection-order node IDs,
one complete ID per line with a final newline, and compute SHA-256 from those
files for the 188-controller baseline, 190-controller result, 16,605 full-suite
baseline, and actual full-suite result. Record the exact two-ID addition and
zero removals/renames/reorders. A projected hash must not become a target that
masks collection drift.

### Full local verification

Run with Node available and the built release settings codec installed:

- the two focused witnesses, including every direct publisher failure branch,
  both independent fsync channels, exact seven-body-fsync categorization, and
  successful publication;
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
- exact Windows and Ubuntu complete identity sets, expected at 16,607 only if
  the qualified implementation adds exactly the two approved witnesses;
- proof that the complete 16,605-ID Stage 3 baseline set is a subset and the
  after-minus-baseline set contains exactly those two witnesses;
- the exact 190-controller identity list and proof that the ordered baseline
  188 list is its unchanged prefix;
- the exact two-ID addition, zero removals, zero renames, and no baseline
  reorder;
- hashes computed from actual implementation collections, never a design-time
  projected node hash;
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
Any addition beyond the two approved witnesses, baseline identity
removal/rename/reorder, new availability skip, failure, error, cross-platform
identity difference, or unexplained skip change is a stop.

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
compatible with the tempfile path and separately prove that fast files are
ordinary, writable, single-link files whose stable metadata does not change
through observation. Do not compare publication timestamps across paths.

`tree.Profile.modified` is the profile directory's `st_mtime` and is expected
to differ as files are created, so it is the one non-path field removed from
discovery parity. No timestamp exists in `ProfileManifest`; its normalized
comparison remains exact. Any other discovery or manifest difference, or any
permission/metadata difference that affects native codec behavior or hosted
Windows execution, is a stop.

### Partial writes and close failures

`os.write()` may legally write fewer bytes than requested. A one-call publisher
would risk truncated but apparently successful fixture files. Loop over a
memory view until complete, reject zero progress, and include close in the
success boundary. On write or close failure, use the module-level `os.close`
and `os.unlink` cleanup path, remove the partial destination where possible,
and preserve the original exception. The comprehensive witness executes
partial success, zero progress, mid-write failure, and close failure directly;
ordinary success tests are not substitutes.

### Exclusive creation assumptions

The helper is unsafe for an existing destination by design. Keep it private to
test fixtures and require `O_EXCL`. Test the helper itself against an existing
file and assert unchanged bytes; the separate duplicate-profile `mkdir` refusal
is insufficient. The helper must never grow into a replacement API.

### Monkeypatching the shared `os` module

Python modules share the same `os` object. Patching either imported module's
`os` attributes mutates global behavior and can suppress or count unrelated
writes. Capture the real module, then replace `tests.setup_fixtures.os` and
`wingman.atomicio.os` with separate delegating proxies. Both proxies invoke real
operations; the first owns direct-helper evidence and the second owns atomic
writer evidence.

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
3. any reusable fixture or existing caller other than
   `test_ui_setup_controller.setup` must opt in, excluding only the two approved
   direct qualification witnesses;
4. a session/shared template, hardlink, reflink, or persistent cache is needed;
5. controller-body atomic writes or selection persistence must be weakened;
6. the fixture's `setup(tmp_path, monkeypatch)` signature must change;
7. any baseline controller identity is removed, renamed, or reordered, or more
   than the two approved witness identities are added;
8. helper failure branches require parameterization into additional identities;
9. mutation evidence requires another test module, Node fixture, or production
   helper change;
10. source/recipient bytes, line endings, CRC, order, revisions, discovery
    fields other than normalized paths/`Profile.modified`, or exact normalized
    manifests differ;
11. local or hosted Node/codec availability skips appear;
12. Windows and Ubuntu complete identities diverge;
13. a workflow, dependency, configuration, marker, selector, budget, or shard
    change appears necessary;
14. evidence can support only a duration assertion rather than the structural
    544-fsync work count.

## Required implementation self-review

Before publication, the results document must record a final review covering:

- placeholder scan — no unfinished marker, omitted-body placeholder, debug
  output, or mutation-only note remains;
- arithmetic — `136 × 4 = 544`, `188 + 2 = 190`, and `16,605 + 2 = 16,607`;
- identity — the baseline ordered 188 IDs are the exact after-collection prefix,
  exactly two non-parameterized witnesses follow, and actual collection hashes
  are recorded without a design-time projected hash;
- parity — atomic and fast bytes, documents, types/order, CRC, revisions, paths,
  all nonvolatile discovery fields, and exact timestamp-free normalized
  manifests agree;
- distinctions — source/recipient IDs and exact LF/CRLF preference bytes remain
  different as designed;
- isolation/metadata — no shared identity, hardlink, or template exists and
  fast files are ordinary, writable, single-link files with stable ordinary
  metadata;
- failure contracts — O_EXCL, partial writes, zero progress, mid-write failure,
  and close failure all execute with exact byte/cleanup/exception assertions;
- persistence — default construction records four atomic-channel fsyncs, fast
  construction records zero on both channels, and the body records six staging
  fsyncs (`2 + 2 + 2`) before directory publication plus the seventh
  selection-persistence fsync after publication;
- mutation restoration — direct-fsync, atomic-delegation, replacement-capable
  body bypass, bytes/order/line-ending, and shared-template mutants fail at
  their intended assertions and every temporary edit is restored;
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
