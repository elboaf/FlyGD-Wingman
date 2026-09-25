# Windows resource memory probe — design

## Status

Approved design. Implementation is test-instrumentation only and requires a
separate reviewed plan. It replaces test-owned Windows `tracemalloc`
instrumentation around the Fleet maximum-response resource subprocess with the
current process's native peak working set. It does not change product code, test
selection, workflow topology, or any pass/fail memory ceiling.

## Purpose

The Fleet transport resource case constructs and decodes the maximum legal
response through the actual signed client, response reader, wire decoder, and
DTO parser in a subprocess. On Windows, its current memory observation starts
`tracemalloc`, which measures traced Python allocations rather than process
memory and surrounds the full 47,022,137-byte decode.

Replace that test-owned Windows observation with
`K32GetProcessMemoryInfo(GetCurrentProcess(), ...)` and report
`PROCESS_MEMORY_COUNTERS.PeakWorkingSetSize` as
`process_peak_working_set_bytes`. If tracing was enabled externally before the
Windows decode, fail before decoding rather than stop someone else's tracer or
publish misleading native-only evidence.

The intended claim is structural only: under the accepted environment, the
test no longer starts or uses `tracemalloc` instrumentation around the maximum
Windows decode. Hosted timing remains observational. This design does not claim
an overall, suite, job, runner, or case speedup.

## Authority and current state

The source baseline is merged `main` commit `cc48c887` (`Optimize setup
controller fixture construction (#288)`). The relevant authorities are:

- `AGENTS.md`;
- `docs/ci-test-budget-redesign.md`;
- `docs/ci-test-budget-fleet-tranche-results.md`;
- `tests/test_fleetsharing_transport_resources.py`.

`PRODUCT.md` and `DESIGN.md` do not govern this change because it alters no
product behavior or rendered interface.

The current test module has three identities:

1. maximum PUT escaping under 512 KiB;
2. non-`resource` traced-allocation fallback behavior;
3. the `resource`-marked maximum legal response subprocess.

The current complete inventory is 16,607 unique identities. This tranche adds
exactly two ordinary identities in the same module, projecting 16,609 unique
identities. It removes, renames, reorders, or parameter-expands no existing
identity.

The existing subprocess publishes exactly six JUnit resource properties:

- `resource.subprocess_wall_seconds`;
- `resource.memory_metric`;
- `resource.memory_peak`;
- `resource.raw_bytes`;
- `resource.rows`;
- `resource.observations`.

The `resource.*` schema is intentionally open. The existing timing summarizer
already preserves these properties, so no parser, timing test, workflow,
configuration, dependency, or marker change is required.

## Contract boundary

### Maximum-response resource contract

The resource test must preserve all current maximum-boundary behavior exactly:

- generate the full 47,022,137-byte response in memory;
- generate exactly 8,192 rows;
- derive and assert exactly 155,648 observations;
- close the construction buffer after extracting the payload bytes;
- execute the actual signed `FleetRelayClient.read_snapshot()` path;
- execute the actual response reader, JSON/wire decoder, and DTO parser;
- request exactly `67,108,865` bytes from the response reader;
- require the response object to be closed;
- run the measurement in a child Python subprocess;
- retain the parent subprocess timeout of 300 seconds;
- retain the parent wall budget of 75 seconds;
- retain the six JUnit resource properties listed above;
- retain exact assertions for payload bytes and row cardinality.

The memory change must not replace the real client with a direct parser call,
stream a smaller fixture, reduce rows or observations, change the read amount,
omit closure, or move the decode into the parent process.

### Independent decoder and parser crossings

Output cardinality cannot independently prove that the real wire decoder and
DTO parser were called: a bypass could fabricate the same result. During
`measure_response()`, install permanent low-overhead, child-local counting
wrappers around these exact module attributes:

- `protocol.decode_wire_json`;
- `protocol.parse_snapshot`.

Each wrapper increments its own integer counter and delegates all arguments and
the return value unchanged to the saved original. Install the wrappers only for
the measured client call, restore both original attributes in a `finally` block,
and then require exactly one call to each. Restoration is mandatory on success
and failure. The wrappers live only in the resource child and add no JUnit
property, pytest identity, production hook, or parent-process state.

The exact-one assertions independently reject bypass and duplicate decode or
parse work while the existing result/cardinality, read-amount, and closure
assertions retain their own contracts.

### Success-header boundary

The resource transport supplies valid content, cache, and request-binding
headers and continues through the actual client success path. It does not
independently own the negative or mutation semantics of
`client._validate_success_headers`: all supplied headers are valid, so bypassing
that validator can produce the same resource result.

Unchanged focused client tests continue to own success-header validation. The
five-path scope and production diff audit prove that this instrumentation change
does not alter that production path. This resource case must not claim that a
`_validate_success_headers` mutant is killed.

### Platform metric selection

`memory_probe()` remains private to
`tests/test_fleetsharing_transport_resources.py` and selects one metric:

| Child platform | Metric | Value semantics |
|---|---|---|
| Windows (`sys.platform == "win32"`) | `process_peak_working_set_bytes` | Native process-lifetime peak working set in bytes from `PeakWorkingSetSize` |
| macOS with `resource` | `process_peak_rss_bytes` | Existing `ru_maxrss` value, whose platform unit is bytes |
| Linux and other `resource` platforms | `process_peak_rss_kib` | Existing `ru_maxrss` value, whose expected unit is KiB |
| Generic non-Windows without `resource` | `traced_peak_bytes` | Existing `tracemalloc` fallback |

Windows has no trace fallback. Failure to load or call the required native API
is a failed test, not permission to switch measurement classes.

The existing fallback identity remains and is made explicitly non-Windows. It
continues to prove the generic non-Windows/no-`resource` traced fallback without
pretending that fallback is valid for Windows.

## Native Windows design

### Lazy binding

The test module must continue to import on Linux and macOS. `ctypes.WinDLL` is
therefore resolved only after the Windows platform branch is selected.

The Windows binding loads:

```text
ctypes.WinDLL("kernel32", use_last_error=True)
```

It resolves these exports from `kernel32`:

- `GetCurrentProcess`;
- `K32GetProcessMemoryInfo`.

No native DLL is loaded at module import time. Portable injected platform,
loader, last-error, and `WinError` seams are evaluated only when the matching
branch or failure path needs them. Tests can therefore exercise Windows
selection and ABI declarations on Linux without accessing a real Windows DLL.

Injected fake exports must be callable objects that permit writable `argtypes`
and `restype` attributes. Python function and lambda objects can satisfy that
contract because callers may attach those attributes; a wrapper class is
optional, not mandatory.

### Exact structure layout

Define the test-private `PROCESS_MEMORY_COUNTERS` with natural `ctypes.Structure`
layout and these exact fields in order:

1. `cb` — `ctypes.c_uint32`;
2. `PageFaultCount` — `ctypes.c_uint32`;
3. `PeakWorkingSetSize` — `ctypes.c_size_t`;
4. `WorkingSetSize` — `ctypes.c_size_t`;
5. `QuotaPeakPagedPoolUsage` — `ctypes.c_size_t`;
6. `QuotaPagedPoolUsage` — `ctypes.c_size_t`;
7. `QuotaPeakNonPagedPoolUsage` — `ctypes.c_size_t`;
8. `QuotaNonPagedPoolUsage` — `ctypes.c_size_t`;
9. `PagefileUsage` — `ctypes.c_size_t`;
10. `PeakPagefileUsage` — `ctypes.c_size_t`.

Do not set `_pack_`. Natural alignment is part of the ABI. Do not use
`ctypes.wintypes`: its aliases are not a reliable way to prove Windows pointer
width while the portable unit tests execute on Linux. Fixed-width DWORD fields
use `c_uint32`; pointer-sized counters and handles use `c_size_t` and
`c_void_p` as appropriate.

The success test must pin all layout evidence, not merely field names:

- exact field names, types, and order above;
- `cb.offset == 0` and `PageFaultCount.offset == 4`;
- the eight `c_size_t` fields have offsets
  `8 + index * ctypes.sizeof(ctypes.c_size_t)` for indexes zero through seven;
- `ctypes.sizeof(PROCESS_MEMORY_COUNTERS)` equals
  `8 + 8 * ctypes.sizeof(ctypes.c_size_t)`, which is 40 on a 32-bit width and
  72 on a 64-bit width;
- `ctypes.alignment(PROCESS_MEMORY_COUNTERS)` equals
  `ctypes.alignment(ctypes.c_size_t)` and is exactly 4 or 8;
- `_pack_` is not defined on the structure.

Each native sample must:

1. create a fresh `PROCESS_MEMORY_COUNTERS` instance;
2. set `counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)`;
3. obtain the current-process pseudo-handle;
4. call `K32GetProcessMemoryInfo` with that handle, a pointer to the fresh
   structure, and the same exact structure size;
5. return `counters.PeakWorkingSetSize` as a Python integer.

The value must not come from `WorkingSetSize`. Value evidence is conditional on
the interpreter's native `c_size_t` width:

- when `ctypes.sizeof(ctypes.c_size_t) == 8`, use a peak above `2**32` and a
  distinct current value, then require the full peak to survive;
- when `ctypes.sizeof(ctypes.c_size_t) == 4`, use distinct peak/current values
  high in the unsigned 32-bit range and require the peak to survive exactly
  without signed or narrower truncation.

A 32-bit interpreter is supported, not skipped or rejected for lacking a value
above its native width.

### Function signatures

Set explicit native signatures before use:

- `GetCurrentProcess.argtypes = []`;
- `GetCurrentProcess.restype = ctypes.c_void_p`;
- `K32GetProcessMemoryInfo.argtypes` is the exact current-process handle,
  pointer-to-`PROCESS_MEMORY_COUNTERS`, and `c_uint32` byte-size shape;
- `K32GetProcessMemoryInfo.restype = ctypes.c_int` for Win32 `BOOL`.

The process handle returned by `GetCurrentProcess` is a pseudo-handle. It must
not be passed to `CloseHandle`, and this test module must not resolve or call
`CloseHandle`.

### Failure behavior

The Windows branch fails closed:

- missing `kernel32` DLL — propagate a loud loader failure;
- missing `GetCurrentProcess` or `K32GetProcessMemoryInfo` export — propagate a
  loud export failure;
- `K32GetProcessMemoryInfo` returning zero — immediately capture the saved
  error through the injected `get_last_error` seam and raise the matching
  injected `WinError(saved_error)`.

The paired last-error operations are load/call-local. Do not perform unrelated
Python or native work between the zero return and `get_last_error()`, and do not
call `WinError()` without the captured code. The comprehensive failure test must
prove that the exact saved code reaches `WinError`.

None of these failures may start or stop `tracemalloc`, return
`traced_peak_bytes`, return zero, reuse a stale structure, or silently fall
through to the generic non-Windows branch.

### Pre-existing tracing guard

On the Windows child path, `measure_response()` imports `tracemalloc` and checks
`tracemalloc.is_tracing()` before the client decode. If it is already true, the
child fails before decoding or publishing evidence. The guard never calls
`tracemalloc.stop()`: externally enabled tracing is owned by its caller, and
silently disabling it would corrupt that caller's instrumentation.

When the guard passes, neither native setup, sampling, decode, nor cleanup calls
`tracemalloc.start()` or `tracemalloc.stop()`. The comprehensive success and
failure identities instrument both methods and require zero calls. The failure
identity also exercises the trace-active guard with an injected tracing seam so
this contract adds no pytest identity and does not run the 47 MB decode in an
ordinary unit test.

## Measurement semantics and data lifecycle

`PeakWorkingSetSize` is the largest physical working set observed for the
process during its lifetime up to the sample. It is not:

- the current working set;
- Python heap allocation;
- a decode-only allocation peak;
- a before/after delta;
- directly comparable to the old `tracemalloc` peak.

The child constructs the complete 47,022,137-byte payload before calling
`memory_probe()` and before taking `memory_before_client`. Consequently, the
first Windows sample already includes any process-lifetime working-set peak
reached while importing modules and constructing the payload.

`memory_before_client` and `memory_peak` remain absolute samples. The second
sample is taken after the actual client decode and reports the process lifetime
peak at that point. It may equal the first sample if payload construction or an
earlier process phase already established the high-water mark. No subtraction
is performed, and no assertion requires growth.

The resource case has no memory ceiling. The value is observability evidence
only. The 75-second wall budget remains the only resource-case performance
failure threshold in this tranche.

The raw payload, parsed DTO graph, response object, and measurement structures
remain child-process data. They are not persisted. The parent receives only the
existing compact JSON evidence and writes only the six existing JUnit
properties.

## Parent-process selection assertion

After decoding the child's JSON evidence, the parent resource test must assert:

```text
if evidence["platform"] == "win32":
    evidence["memory_metric"] == "process_peak_working_set_bytes"
```

This pins real hosted Windows execution to the native metric. It does not infer
Windows from the parent process or replace the child's reported platform.

Non-Windows resource executions retain their current metric behavior. No parent
assertion may force macOS, Linux, or generic fallback executions to report the
Windows metric.

## Test design and identity contract

Add exactly two ordinary, non-parameterized test identities. A loop inside the
failure test covers its cases without multiplying pytest identities.

### 1. Native success, selection, and ABI contract

One comprehensive identity, named to state that Windows uses the native peak
working set, must prove all of the following together:

- the Windows branch is selected even if a fake `resource` module is available;
- the metric name is exactly `process_peak_working_set_bytes`;
- the loader is evaluated lazily and called as
  `WinDLL("kernel32", use_last_error=True)`;
- both required exports receive explicit `argtypes` and `restype` declarations;
- the `GetCurrentProcess` pseudo-handle is passed unchanged to the memory API;
- no close function is resolved or called;
- the structure has the exact ten fields, types, order, natural offsets, exact
  size, and natural alignment specified above;
- `_pack_` is absent and `ctypes.alignment(PROCESS_MEMORY_COUNTERS)` is exactly 4
  or 8 as dictated by `c_size_t`;
- every sample receives a fresh structure rather than reusing one whose fields
  could retain old data;
- `cb` equals `ctypes.sizeof(PROCESS_MEMORY_COUNTERS)` on every sample;
- the API byte-size argument equals that same exact size;
- repeated probe calls perform repeated native samples;
- the returned value is `PeakWorkingSetSize`, not `WorkingSetSize`;
- on a 64-bit `c_size_t`, a distinct peak above `2**32` is returned intact;
- on a 32-bit `c_size_t`, distinct high unsigned peak/current values survive
  exactly within native width;
- `tracemalloc.start()` and `tracemalloc.stop()` are never called.

The fake DLL exports are callables with writable signature attributes; a Python
function, lambda, or wrapper object is acceptable. The fake memory API fills the
received pointed-to structure and records structure identities, handles, `cb`,
and byte-size arguments.

### 2. Native fail-closed contract

One comprehensive identity loops over these native scenarios without pytest
parameterization:

1. DLL load failure;
2. missing export failure;
3. API zero return with a known saved error.

For every native scenario it must prove:

- the failure escapes rather than selecting another metric;
- no probe value is returned;
- no `resource`/tracing fallback is consulted;
- `tracemalloc.start()` and `tracemalloc.stop()` are never called.

For the API-zero scenario it must additionally prove:

- the fake `get_last_error()` is called after the zero return;
- the exact saved error is supplied to the fake `WinError` constructor;
- the resulting exception is raised;
- a current or peak field written by the fake cannot be returned after failure.

The same identity exercises the Windows child tracing guard with
`is_tracing() == True`. It must fail before decode, call neither `start()` nor
`stop()`, and leave the externally owned tracer active.

State is reset between loop iterations so one failure mode cannot satisfy
another through stale calls.

### Existing fallback identity

Keep `test_memory_probe_falls_back_without_resource` as an existing ordinary
contract, but make the branch explicitly non-Windows through the portable
platform seam. It continues to assert that a one-MiB allocation grows the
generic fallback's `traced_peak_bytes` observation and always stops tracing in
cleanup.

The complete file therefore changes from three to five identities:

- two ordinary tests become four ordinary tests;
- one `resource` test remains one `resource` test;
- projected complete collection changes from 16,607 to 16,609;
- no existing node ID changes.

## Mutation qualification

All mutants are temporary and uncommitted. Restore the exact source after every
probe, run the intended witness, and inspect the final diff so no mutation or
witness-only support remains.

A red result counts only when the intended assertion fails. An unrelated import,
collection, subprocess, timeout, or cleanup failure is not sufficient.

### Windows selection and tracing mutants

Temporarily:

- allow the Windows branch to fall through to `resource`;
- allow the Windows branch to fall through to `tracemalloc`;
- call `tracemalloc.start()` or `tracemalloc.stop()` from native setup,
  sampling, or cleanup;
- ignore a true `is_tracing()` result and continue to decode;
- report the wrong metric name.

The success or fail-closed identity must fail at the branch, no-start/no-stop,
trace-active guard, or metric assertion. A temporary child invocation with
tracing pre-enabled must fail before decode and emit no resource evidence. The
resource parent assertion must independently reject a real child reporting a
non-native metric on `win32`.

### ABI and value mutants

Temporarily:

- return `WorkingSetSize` instead of `PeakWorkingSetSize`;
- omit or corrupt `cb`;
- pass the wrong structure byte size;
- on a 64-bit width, truncate the returned value to 32 bits;
- on either width, coerce the result through a signed or narrower type;
- reuse one structure across samples;
- omit an explicit function signature;
- alter a structure field type, order, offset, total size, `_pack_`, or natural
  alignment;
- close or replace the current-process pseudo-handle.

The comprehensive success identity must fail at the exact owned assertion. The
width-conditional value mutant must not reject a supported 32-bit interpreter
merely because it cannot represent a value above `2**32`.

### Failure mutant

Temporarily ignore a zero return, lose the saved error, call `WinError` with a
fresh/implicit error, or recover through tracing. The fail-closed identity must
fail at the return, error-pairing, or no-trace assertion.

### Maximum-response tripwires

Temporarily alter one boundary at a time:

- maximum rows;
- observations per row or total observations;
- exact raw payload size;
- `read(67_108_865)` request;
- response closure;
- bypass or duplicate `protocol.decode_wire_json`;
- bypass or duplicate `protocol.parse_snapshot`.

The exact output/cardinality, read, and closure assertions remain the witnesses
for their boundaries. The permanent child-local counters must reject decoder or
parser bypass and duplicate calls by requiring exactly one call each. Restore
both wrapped attributes in `finally`, and restore every temporary mutant before
any commit.

Do not include a `_validate_success_headers` mutation in this resource mapping.
Valid headers make that mutant observationally equivalent here; unchanged
focused client tests plus production diff/scope audit own that path.

## Compatibility

### Python and platform compatibility

The module must continue to import and run ordinary tests on Linux. No Windows
symbol is touched at import time. Portable fake DLLs and error seams provide
ordinary cross-platform contract coverage, while the hosted Windows resource
case owns the real ABI crossing. The tests branch on `ctypes.sizeof(c_size_t)`
and support both 32-bit and 64-bit interpreters; they do not skip or reject the
32-bit case for lacking an above-32-bit value.

The design uses only Python's standard library. No package, lockfile, build,
codec, or runtime dependency changes.

### Evidence compatibility

The six JUnit property names and value-string behavior remain unchanged.
`resource.memory_metric` changes value only for Windows child processes, from
`traced_peak_bytes` to `process_peak_working_set_bytes`. Existing Linux and
macOS metric names remain stable.

Because the `resource.*` schema is open and the summarizer already preserves
arbitrary properties, no `tests/test_ci_timing.py` or
`scripts/summarize_pytest_junit.py` change is authorized.

### Historical compatibility

Do not edit historical plans, results, or recorded hosted evidence. Prior
Windows `tracemalloc` values remain valid descriptions of those earlier runs.

Update only the current-state paragraph under `### Transport resources` in
`docs/ci-test-budget-redesign.md`: replace the present statement that Windows
`tracemalloc` peak is retained with the new native lifetime-peak working-set
observability semantics. Preserve the historical reference-run table row that
accurately describes the earlier 44.6-second run under `tracemalloc`.

## Security and failure posture

This is read-only process introspection of the current test subprocess. It:

- opens no external process;
- requests no process ID or elevated handle;
- uses the current-process pseudo-handle only;
- writes no native memory except the caller-owned counters structure;
- closes no pseudo-handle;
- sends no additional data outside the child/parent test boundary;
- adds no product runtime API or production DLL binding.

Failing closed is mandatory because silently changing metric classes would make
hosted evidence ambiguous. A missing DLL, export, or failed API call must fail
the test with native error context rather than produce plausible but unrelated
trace data.

## Observability and claim discipline

The child JSON continues to include:

- absolute pre-client memory sample;
- absolute post-client lifetime peak sample;
- metric name;
- platform and Python version;
- exact payload, row, and observation counts;
- client and reader timing observations.

Only the existing six fields are promoted to JUnit resource properties. No new
property or schema change is needed.

The implementation results may report hosted Windows and Ubuntu timing as
observations. They may make only this structural instrumentation statement:

> Under the accepted environment, the test no longer starts or uses
> `tracemalloc` instrumentation around the maximum Windows Fleet response
> decode. Pre-existing external tracing fails the contract before decode rather
> than being silently stopped or producing native-only evidence.

They must not attribute an overall runtime reduction, suite speedup, job
speedup, runner-efficiency improvement, critical-path reduction, or stable case
speedup to this change. One hosted sample is not sufficient for such a claim.

## Exact committed scope

The complete implementation tranche may commit only these paths:

- `docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md`;
- `docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md`;
- `docs/ci-windows-resource-memory-probe-results.md`;
- `docs/ci-test-budget-redesign.md`;
- `tests/test_fleetsharing_transport_resources.py`.

This design commit contains only the first path.

Explicitly forbidden without a new design review:

- any file under `wingman/`;
- `tests/test_ci_timing.py`;
- `scripts/summarize_pytest_junit.py` or another script;
- `.github/` workflows;
- `pyproject.toml`, `uv.lock`, dependencies, packaging, or configuration;
- pytest marker, selector, timeout, budget, or shard changes;
- product behavior, Fleet protocol, response limits, or client changes;
- edits to historical plans, results, or evidence.

If implementation requires any sixth path, workflow change, parser/schema
change, product change, or dependency/configuration change, stop and redesign
rather than broadening scope.

## Alternatives rejected

### Load `psapi.dll`

Rejected. Modern supported Windows exposes `K32GetProcessMemoryInfo` through
`kernel32`, avoiding a second DLL and keeping the binding at the same native
surface already used throughout the project. Loading `psapi.dll` and resolving
`GetProcessMemoryInfo` would add compatibility and test surface without a
contract benefit for this test-only probe.

### Retain Windows tracing as a fallback

Rejected. A native probe failure followed by `tracemalloc` would silently change
measurement classes and could reintroduce the instrumentation this tranche
removes. Windows either reports native process peak working set or fails loudly.
Likewise, a tracer enabled before the child decode is not a fallback: the child
fails before decode and never stops the externally owned tracer.

### Assert a working-set ceiling

Rejected. Process lifetime peak working set depends on interpreter, imports,
payload construction, allocator behavior, and hosted runner conditions. It is
useful evidence but not a stable memory budget, and it is not comparable to
traced Python allocations.

### Use current working set or a before/after delta

Rejected. The approved metric is the native lifetime high-water mark. Current
working set can fall before the sample, while subtracting two lifetime peaks
would imply decode attribution that the payload-before-sample lifecycle cannot
support.

### Move the probe into production support

Rejected. No product subsystem consumes this metric. Keeping the structure,
binding, seams, and tests private to the resource-test module avoids creating a
runtime API for test instrumentation.

## Verification requirements

### Local identity and focused verification

Before implementation, freeze the current three ordered node IDs in
`tests/test_fleetsharing_transport_resources.py` and the complete 16,607-ID
inventory. After implementation require:

- exactly five unique IDs in the target file;
- the original three IDs unchanged and in their original relative order;
- exactly the two approved new ordinary IDs;
- no parameterized suffixes on either new test;
- exactly one `resource`-marked identity;
- complete projected inventory of 16,609 unique IDs;
- zero removals, renames, or unrelated additions.

Run:

- both new ordinary Windows-probe tests on the non-Windows local host;
- the existing explicit non-Windows tracing fallback test;
- the complete target module with `-m "not resource"`;
- the resource case with JUnit output;
- the complete Fleet transport test area;
- full pytest with Node and the built release settings codec available;
- complete skip inspection;
- `node scripts/js_smoke.js`;
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`;
- Ruff check and Ruff format check;
- `git diff --check`;
- exact five-path allowlist and protected-path audit.

No Node, settings-codec, or unexpected native-availability skip is acceptable
full-suite evidence.

### Hosted Windows acceptance

A successful hosted Windows run must prove the real ABI rather than only the
portable fakes:

- the resource child reports `platform == "win32"`;
- `resource.memory_metric` is exactly
  `process_peak_working_set_bytes`;
- the maximum response passes with 47,022,137 bytes, 8,192 rows, and 155,648
  observations;
- child-local assertions require exactly one call each to
  `protocol.decode_wire_json` and `protocol.parse_snapshot`, and both originals
  are restored in `finally`;
- the response read amount and closure assertions pass;
- all six JUnit resource properties are present;
- the subprocess remains within timeout 300 and wall budget 75;
- the two ordinary native binding tests pass on the interpreter's actual
  `c_size_t` width;
- exact field order, offsets, size, and alignment are proved;
- the accepted Windows child starts with `tracemalloc.is_tracing() == False` and
  test-owned code calls neither `start()` nor `stop()`;
- no trace fallback or native-availability skip appears.

Success-header validation is accepted through unchanged focused client tests and
the production diff/scope audit, not through a claimed resource-case mutation
witness.

Record branch head, synthetic merge, base, workflow run, job IDs, artifact IDs,
platform/Python provenance, exact identities, normalized skips, resource
properties, testcase sums, Test-step duration, and job duration in the results
document. Timing values are observations only.

## Risks and mitigations

### Linux-hosted fake ABI can diverge from Windows

Portable tests prove field selection, layout intent, signatures, error pairing,
and branch behavior, but they cannot prove the deployed Windows ABI by
themselves. The hosted Windows maximum resource case therefore owns the real
DLL/export/calling-convention crossing.

### Structure packing or pointer width can be subtly wrong

A packed structure, a `c_uint32` pointer-sized counter, or a `wintypes` alias
whose Linux width differs can appear to work under fakes while corrupting real
calls. Pin exact fields, order, offsets, total size, natural alignment,
`c_size_t` counters, and the `c_void_p` handle. Use above-32-bit value evidence
only when `c_size_t` is 64 bits; use exact high unsigned values within width on a
32-bit interpreter.

### Last error can be overwritten

Calling Python helpers or another native API before `get_last_error()` can lose
the failure cause. Capture it immediately after a zero return and pass the saved
integer explicitly to `WinError`.

### Lifetime peak can be misread as decode allocation

Payload construction precedes the first sample, and process lifetime may contain
an even earlier peak. Document both samples as absolute high-water marks, never
subtract them, and make no memory-ceiling or decode-attribution claim.

### A fallback or external tracer can hide native evidence

Any Windows fallback would allow green resource evidence with the wrong metric.
The failure identity forbids tracing/resource recovery, and the parent resource
test pins the metric when the child reports `win32`. A pre-existing tracer would
also make a native-only result ambiguous, so the child fails before decode and
does not stop that external owner.

### A valid result can hide parser bypass

Exact rows and observations alone do not prove the production wire decoder or
DTO parser ran. The permanent low-overhead child wrappers count each exact
module attribute and require one call, while `finally` restoration prevents the
instrumentation from leaking into later child work.

Success-header validation has the opposite boundary: all resource headers are
valid, so this case cannot independently distinguish validation from bypass.
Keep that contract with unchanged focused client tests and the production
scope/diff audit rather than claiming a false mutation witness.

### Structural runtime improvement can be overclaimed

Removing test-owned tracing is a concrete instrumentation change, but hosted
durations are noisy and the process still builds and parses the full maximum
payload. Report only that, under the accepted environment, the test no longer
starts or uses `tracemalloc` around the Windows maximum decode; external tracing
fails before decode.

## Stopping rules

Stop implementation and return to design review if any of these occurs:

1. `K32GetProcessMemoryInfo` cannot be bound from `kernel32` on supported hosted
   Windows;
2. a Windows trace or `resource` fallback appears necessary;
3. the exact natural `PROCESS_MEMORY_COUNTERS` layout, including alignment,
   cannot be represented with `c_uint32` and `c_size_t` on either supported
   native width;
4. preserving the maximum response requires changing bytes, rows,
   observations, read amount, closure, exact-one decoder/parser crossings,
   subprocess timeout, or wall budget;
5. any existing JUnit resource property must be removed or renamed;
6. more than two test identities are required;
7. an existing test identity must be renamed, removed, reordered, or
   parameterized;
8. a production, workflow, summarizer, timing-test, dependency, configuration,
   marker, selector, budget, shard, or historical-document change is required;
9. any committed path outside the exact five-path allowlist is required;
10. hosted Windows cannot prove the native metric without a skip;
11. evidence supports only a memory ceiling, delta, or runtime-speedup claim
    rather than the approved structural test-owned no-tracing claim under the
    accepted environment.

## Required implementation self-review

Before publication, the results document must record a final review covering:

- placeholder scan — no `TODO`, `TBD`, `PENDING`, omitted-body marker, debug
  output, or mutation-only support remains;
- identity arithmetic — target module `3 + 2 = 5` and complete collection
  `16,607 + 2 = 16,609`;
- ABI — exact ten fields, order, offsets, natural size and 4-or-8 alignment,
  pointer widths, signatures, handle, `cb`, API byte size, fresh structures, no
  `_pack_`, and no close;
- metric — exact Windows name and `PeakWorkingSetSize`; above-32-bit distinct
  peak/current evidence on a 64-bit `c_size_t`, or exact high unsigned distinct
  values within width on a 32-bit `c_size_t`;
- failure — DLL, export, and zero-return cases fail loudly, preserve saved error,
  and call neither tracing start nor stop;
- fallback — the existing trace fallback is explicitly non-Windows and remains
  green;
- tracing ownership — Windows fails before decode when tracing is already active,
  never stops an external tracer, and accepted execution neither starts nor
  stops a tracer;
- maximum contract — exact bytes, rows, observations, read amount, closure,
  signed client, reader, exactly one wire-decoder call, exactly one DTO-parser
  call, timeout, budget, and six JUnit properties;
- header boundary — success-header validation remains owned by unchanged focused
  client tests and scope/diff evidence, with no unsupported resource mutant;
- mutation restoration — every selection, trace, current/peak, layout,
  alignment, `cb`, size, failure, metric, decoder/parser, and maximum-boundary
  mutant is restored exactly, as are both permanent wrappers in `finally`;
- compatibility — Linux import/tests, macOS/Linux metrics, and hosted Windows
  native execution remain valid;
- scope — only the approved spec, plan, results, current-state paragraph, and
  target test module are in the tranche diff;
- protected paths — no production, workflow, timing parser/test, dependency,
  configuration, marker, selector, budget, shard, or historical-doc change;
- claim discipline — no memory ceiling, traced-allocation comparison,
  decode-delta claim, or overall/runtime speedup attribution.

## Follow-up boundary

Successful implementation proves only that, under the accepted environment,
the Windows maximum Fleet response resource subprocess observes native
process-lifetime peak working set without starting or using test-owned
`tracemalloc` instrumentation, executes the real wire decoder and DTO parser
exactly once, and preserves the remaining maximum decode contract and evidence
schema. Externally active tracing fails before decode and is never stopped. This
does not authorize resource-schema expansion, memory ceilings, test-tier
changes, workflow edits, broader Windows profiling, or further CI runtime
claims.
