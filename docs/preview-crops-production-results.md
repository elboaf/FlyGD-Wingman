# Production crop verification — release BLOCKED

This is new evidence for the production one-crop-per-character implementation,
not a revision of the checkout-only probe results. No visible Windows app,
native picker/crop, installer or EVE interaction was launched for this pass.
No real EVE client geometry was changed.

**Initial hardening SHA:** `1b61f64fa98e6f3915d01f89d6623d70b14d155b`.
**Final-review production fix SHA:** `ea14411003a73ee860a5096a53e4c926f512e27c`.
**Latest full-suite / browser / wheel SHA:** `201917e74fecbadbfb3da6a6266fce97fea11c35`
(one subsequent test-ordering correction; production bytes unchanged).
Documentation is committed separately to avoid self-referential evidence hashes.
The implementation cap remains **eight, provisional**; no stage has passed the
production hardware release gates.

## Final consolidated review fixes — ea14411 / 201917e

All five final-review findings were reproduced and addressed together:

- Telemetry uses the host's committed runtime authorization, not a live settings
  value temporarily changed by a pending master transaction. A failed master-off
  save can no longer suppress renewed-session delivery and permit an old selection
  to persist. The regression uses the real API, settings lock, store, telemetry
  dispatcher and fake-native pump; no settings lock is held across native work.
- Candidate promotion checks current host ingress (runtime epoch, stop fence and
  full discovery session) after native preparation and old-window destruction,
  and again after the final DWM update before showing. Successful admitted saves
  remain real persisted outcomes; unauthorized candidates are discarded. Eight
  Event-barrier cases cover stop/session renewal at four promotion boundaries.
- A completed store drain does not imply native cleanup completed. The host now
  retains its controller/picker/pump until the picker releases its full bundle,
  including fonts. Cleanup retries on existing pump-message boundaries without
  a retry thread, timer, busy loop or worker wait. Ordinary/final stop tests hold
  fonts through confirmation and drain, prove timeout/restart refusal, then release
  them through a pump boundary and verify complete teardown.
- Failed capture acquisition resets the crop gesture after checking GetCapture;
  SetCapture's return is the previous owner, not success. Neither another owner's
  capture nor a late move/up may cause an unintended move, resize or activation.
- The loader and crop API share exact canonical-owner validation. Malformed rows
  drop individually; trimming/renaming must not overwrite a valid owner's crop.

The 19 new cases failed before their fixes and pass on both platforms. The first
full Windows run at ea14411 produced **6082 passed, 52 skipped, 1 failed**: an
existing crop-status test drained the store before proving its asynchronous host
command had been submitted. An Event-blocked-pump diagnostic established that
ordering gap. The only subsequent change, at 201917e, adds the missing pump
barrier before that drain; assertions and production behavior are unchanged.
The failed XML is retained, not replaced by a diagnostic pass.

| Fresh exercise at 201917e | Actual result | Boundary |
| --- | --- | --- |
| Full Linux pytest, Python 3.11.15 | **6124 passed, 11 skipped**, 85.10 seconds | All new regressions plus existing suite |
| Full Windows pytest, Python 3.12.10, Windows 11 build 26100 | **6083 passed, 52 skipped**, 83.45 seconds | Same isolated TEMP venv and APPDATA/LOCALAPPDATA; no blanket injection/exclusions |
| Ruff check / format check | Passed; 292 files formatted | No lint/format exemption |
| Current CI WebView2/build-action text checks; all 16 web JS syntax checks | Passed | No version or packaging contract change |
| Owned Linux Chrome dev-page exercise | **27 passed, 0 failed**; 32/32 handlers registered | 840×625 and 839×625; no unexpected runtime errors |
| Actual Api._push → generated JS → actual page handler | Passed | Own __proto__ key and configured controls preserved |
| Rebuilt wheel, ZIP imports and byte comparison | Passed | Five crop modules plus modified startup/host/API bytes; probes/tests absent |

Linux's separate `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`
passed **1 test** at ea14411. Windows Cargo/Rust were queried and are not on PATH;
that separate CI codec leg was not run or installed globally. No Rust source
changed. Full Windows pytest is green, not a claim that every Windows build gate
ran. The earlier full Linux run at ea14411 also passed 6124/11 in 81.05 seconds.

Fresh artifacts in the implementation workspace: `final-fix-linux-201917e.xml`,
`final-fix-windows-201917e.xml`, `final-fix-browser/` and `wheel-201917e/`.
Historical `final-fix-windows-ea14411.xml` records the test-ordering failure.
`final-fix-report.md` contains exact commands, RED/GREEN results and decisions.
Only owned, isolated Linux browsers were opened/closed; no unrelated browser or
Windows desktop was captured. Test timings are not crop performance measurements.
All native/frozen/performance/DPI/minimized release gates below remain BLOCKED;
cap eight remains provisional.

## Previous verification at 16b69b0 — pending-confirm cancellation

Review found that a confirmation waiting for selected-font cleanup remained
cancellable but could still be delivered after a later Disable or Remove. The
picker now converts only an **undelivered** confirmation to cancellation. The
terminal callback still waits for resource cleanup; an already-delivered
confirmation or admitted write is not undone.

Real-store/native-held-font regressions for both Disable and Remove failed
before the fix because the selection persisted. After the fix, each confirms
that selection never persists, only the later operation writes, Disable retains
the old source, no candidate is allocated, and cancellation is delivered once
after font cleanup. Reentrant/late cancellation after delivered confirmation
also remains a no-op. No worker, schema, API/browser or capacity change.

| Exercise at 16b69b0 | Actual result | Boundary |
| --- | --- | --- |
| Full Linux pytest, Python 3.11.15 | **6105 passed, 11 skipped**, 97.59 seconds | Fresh after fix commit |
| Full Windows pytest, Python 3.12.10, Windows 11 build 26100 | **6064 passed, 52 skipped**, 99.63 seconds | Same temporary venv and APPDATA/LOCALAPPDATA sandboxes; no blanket injection or extra exclusions |
| Ruff check / format check and current CI WebView2/build-action checks | Passed; 292 files formatted | Static/text contracts |
| Rebuilt wheel / byte comparison / direct ZIP imports | Passed | All five production modules, including corrected picker; all three probes absent |

New XML: `task-10-linux-16b69b0.xml`, `task-10-windows-16b69b0.xml`.
The wheel is identified below. Test execution times are not crop performance
measurements. API/browser code was unchanged by this fix: the browser evidence
remains attributed to **1b61f64**, not falsely reported as rerun at 16b69b0.

## Previous full-suite verification at 6111c5b

| Exercise | Actual result | Boundary |
| --- | --- | --- |
| Full Windows pytest, Python 3.12.10, Windows 11 build 26100 | **6062 passed, 52 skipped**, 116.82 seconds | Same temporary venv and APPDATA/LOCALAPPDATA sandboxes; no blanket diagnostic injection or exclusions |
| Full Linux pytest, Python 3.11.15 | **6103 passed, 11 skipped**, 117.44 seconds | Includes the real generated-script Node tests |
| Ruff check / format check | Passed; 292 files already formatted | Static checks |

The parent approved a narrow test-only isolation repair after inspecting the
three earlier failures: the two identification-success/ambiguity tests now
explicitly stub their instance's `_eve_client_running_strict` as False, and the
formation-save test replaces its obsolete weak-method stub with that strict
seam. All assertions and the separate running=True/strict-failure guards remain
unchanged. Temporary EVE roots/fake codec are retained. No production behavior
changed, no EVE client was closed or manipulated, and no global injection or
extra test exclusions were used for these fresh full runs.

New XML artifacts are `task-10-windows-6111c5b.xml` and
`task-10-linux-6111c5b.xml` in the implementation workspace. The earlier red run
and diagnostic remain below as history, not as the current Windows result.
These automated passes do not close visible native, frozen-build or performance
gates. Times are test execution times, not crop performance measurements.

## Earlier automated evidence at 1b61f64

| Exercise at the production hardening SHA | Actual result | Boundary |
| --- | --- | --- |
| Linux, Python 3.11: locked dev sync; full pytest | 6103 passed, 11 skipped | Python behavior and repository conventions; no EVE/DWM measurements |
| Ruff check / format check | Passed; 292 files already formatted | Static checks |
| Current version-derivation tests | 9 passed | No version bump; no obsolete three-literal version grep |
| Current CI WebView2 predicate and build-action invocation checks | Passed | Text contracts, not WebView2 startup |
| `node --check` on all 16 `wingman/web/*.js` files | Passed | Syntax only |
| Real `Api._push` scripts executed by Node | 6 passed | Own `__proto__` data keys; nested/root NaN and ±Infinity; ordinary JSON/string fidelity |
| Existing Task 9 browser exercise, isolated Linux Chrome 152.0.7977.82 | 27 passed, 0 failed | Actual dev page at 840×625 and 839×625; 32/32 handlers registered; no unexpected runtime errors |
| Actual Python `Api._push` → generated script → actual page handler in a separate isolated Chrome | Passed | `__proto__` owner remains an own key and renders configured controls |
| Windows 11 build 26100, Python 3.12.10: initial full pytest | **6059 passed, 52 skipped, 3 failed** | Historical red run; superseded by the fresh full suite at 6111c5b above |
| Windows focused crop/store/controller/host/wiring/API/native-declaration/packaging/invariant suite | 914 passed, 2 skipped | Includes synthetic message-only HWND pump and real Win32 declaration checks; no visible crop/picker |
| Actual wheel build and imports from that wheel | Passed | Five production modules collected and importable; all three probe modules absent; not a Windows frozen build |

The earlier Linux full suite ran after the hardening commit and took 91.30 seconds.
The initial Windows full suite took 143.25 seconds; its focused run took 6.53
seconds. These are **test execution times**, not crop performance measurements.

Windows used a separate temporary venv and process-level **APPDATA and
LOCALAPPDATA sandboxes set before imports**, protecting real Startup shortcuts
from autostart tests. The Linux `.venv` and global Windows Python were not
replaced or modified. PowerShell script execution was initially blocked;
setup/tests instead used direct Windows `uv.exe` with explicit environment
assignments carried by `WSLENV`, without changing execution policy. The initial
full run warned that the repository's Python 3.11 request differed from the
explicitly installed supported 3.12 interpreter; the focused run selected that
interpreter explicitly.

The three initial Windows failures exposed EVE-settings test isolation gaps:

- `test_identification_proposes_only_one_changed_account`
- `test_identification_never_guesses_between_changed_accounts`
- `test_save_backs_up_writes_and_reports_done`

They left `_eve_client_running_strict` native (the third stubbed the older
method), so this environment returned “watching” or refused a save before the
changed bridge assertion. A diagnostic with **only that seam injected as False**
gave **3 passed**, but was not counted as a green full suite. The parent-approved
per-test repair and fresh full Windows result are recorded above; no unrelated
production fix was made. Windows skips still include missing
Node (the six new serialization cases and 15 existing Node cases), unavailable
codec, POSIX/symlink cases and an intentionally excluded visible modal. Node
serialization evidence above is Linux evidence, not a claimed Windows pass.

### What the hardening regressions establish

- Worker callbacks are registered while an Event-blocked save is demonstrably
  pending, execute off the caller thread, and can acquire both locks and close
  the store. An in-memory callback-under-lock mutation was rejected.
- Every DWM registration attempt is counted independently of successful
  registration events. Extra initial/recovery attempts were rejected by an
  in-memory mutation; initial failure and bounded recovery keep their contracts.
- Failed RestoreDC explicitly reselects the previous font. Failed DeleteObject
  retains ownership; factory unwinding, the existing pump and stop retry cleanup
  before terminal callbacks. Injected enclosing-paint cases cover creation,
  font replacement, cancellation, confirmation/candidate allocation and stop.
- Reselection keeps an untouched monitor rescue out of saved geometry, while
  genuine movement before selection, while selecting/saving, after publication
  and after completion survives. Intentionally saved partial overhangs remain
  unchanged. Only initial defaults are fitted aspect-preservingly to one actual
  monitor, including tall/flat selections; loss of displays cancels cleanly.
- Successful replacement survives a later failed removal. Existing admission,
  session renewal/coalescing, hidden-at-birth, cap reservations, degraded
  recovery and late-shutdown regressions remain passing.
- Bridge payloads use JSON parsing rather than JavaScript object-literal
  semantics. Non-finite values are restored by exact encoded paths, **not
  sentinel strings or objects**, so ordinary user data cannot collide with a
  reserved marker. Existing semantic payloads/receipts and fan-out are unchanged.

## Distribution collection

At **201917e74fecbadbfb3da6a6266fce97fea11c35**, the fresh wheel
`wheel-201917e/wingman-5.1.1-py3-none-any.whl` is **688344 bytes**, SHA-256:

```text
8a69fc7f0011662d726cbb74850c4da35431e4f01fea8fccb985ba1c8856a3a5
```

All five crop modules were byte-compared and imported from the ZIP itself under
`python -I`. The changed `wingman/__main__.py`, `wingman/ui/api.py` and
`wingman/preview/host.py` also match the checkout byte-for-byte. All three probe
modules and the tests tree are absent. No native launch/import side effect was
used to inspect the wheel. The earlier ea14411 wheel remains separately stored
(688344 bytes, SHA-256 `632da9e2b177f65d2c49b5755e2d4c789433efe969caff3edc1ef740a452e1b8`).
This is Python wheel collection, not Windows frozen-build/installer acceptance.

At **16b69b01a97b610ca2000d4225673afa5a779f79** (historical), `uv build --wheel` rebuilt
`wheel-16b69b0/wingman-5.1.1-py3-none-any.whl` (687456 bytes) in the ignored
implementation workspace:

```text
SHA-256 56c55fcd6c85dcfcbb34db5a9c35e8e34118dbefab70825a06cb79d511c170d9
```

The earlier 1b61f64 wheel remains a historical artifact: 686868 bytes,
SHA-256 `a4bc659e87ff7367cde3079b1027ab0fd8d92c139789b95af3c8b4b59ed2a3d7`.
It is not evidence for the corrected pending-confirm cancellation path.

For that earlier wheel, `crops.py`, `cropstore.py`, `cropwindow.py`, `croppicker.py`
and `cropcontroller.py` were byte-compared with the 16b69b0 checkout and imported
from the ZIP itself in an isolated Python invocation. The wheel contains no
`preview_crop_harness.py`, `preview_crop_model.py`, `preview_crop_windows.py`
or `tests/` tree. No subpackage or hidden import was added. This proves Python
module collection only: **Windows PyInstaller collection, frozen launch and
installer verification were not performed**.

Reproducible commands and local artifacts (JUnit XML, browser scripts/results,
screenshots, wheel and mutation checks) are recorded in
`.superpowers/sdd/2026-09-06-production-cropped-previews/task-10-report.md` in the
implementation workspace. They are not shipped in the application.

## Unrun production release gates

Every hardware row below is **NOT RUN / BLOCKED**. There are no production
client counts, hardware specifications, monitor rectangles/scales, source
resolutions, baselines or stage measurements to report from this pass.
Historical probe numbers must not be copied into these rows.

| Required exercise | Predeclared acceptance | Status |
| --- | --- | --- |
| Stages 1/2/4/8, all intended crops visible, matching primary-only baselines | Record exact code SHA, clients, hardware, displays/scales and source sizes | NOT RUN |
| Source edges | Error ≤2 source pixels | NOT RUN |
| Click activation | ≤500 ms; p95 ≤baseline+50 ms | NOT RUN |
| Drag delivery | p95 gap ≤32 ms, max ≤100 ms; primary p95 increase ≤50% | NOT RUN |
| 60-second combined CPU | Delta ≤2 percentage points | NOT RUN |
| DWM GPU | Median delta ≤5 percentage points | NOT RUN |
| Working set | Delta ≤8 MiB + 4 MiB × active crops; same allowance during temporary-slot exercise | NOT RUN |
| Stage eight plus picker, then replacement/cancel/initial DWM failure/save failure | Peak thumbnail relationships ≤primary baseline+9; picker and candidate never overlap | NOT RUN |
| Native resource inventory/teardown | Count DWM register/unregister separately from top-level/owned/child HWNDs; return all to baseline | NOT RUN |
| Visible WebView2/picker | Keyboard, accessibility, dark paint, focus and 100/125/150/200% scaling | NOT RUN |
| Native lifecycle and geometry | Close, source exit/logout/return, capture theft, primary-lock independence and toggle, visibility, rescue, source/picker resize, negative coordinates, occlusion and primary alert pulses | NOT RUN |
| Source minimize/restore | Record live/frozen/black/stale behavior and restoration, with no retry storm | NOT RUN |
| Windows frozen distribution/installer | Collect, inspect and exercise the actual Windows build safely | NOT RUN |

**Minimized-source behavior is unmeasured.** This pass makes no promise that
minimized EVE sources remain live, freeze, turn black or become stale. Help
must be updated with the actual observation before release.

If stage eight fails, lower the cap to a fully tested passing stage and rerun
its temporary-slot exercise. If only the extra slot fails, implement and test
the approved strict-cap/free-slot reselection fallback. If one crop fails,
block release. No cap reduction or fallback was selected without measurements.
See the **Character crops** section of [the smoke checklist](smoke-checklist.md).
