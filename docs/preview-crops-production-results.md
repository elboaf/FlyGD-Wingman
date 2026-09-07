# Production crop verification — release BLOCKED

This is new evidence for the production one-crop-per-character implementation,
not a revision of the checkout-only probe results. No visible Windows app,
native picker/crop, installer or EVE interaction was launched for this pass.
No real EVE client geometry was changed.

**Production hardening SHA:** `1b61f64fa98e6f3915d01f89d6623d70b14d155b`
(`test: harden production crop lifecycle and bridge fidelity`).
**Latest full-suite SHA:** `6111c5b3dba2701285d69f35f2949a2c291fba51`
(`test: isolate EVE settings fixtures from running clients`). The later revision
changes only three tests plus intervening documentation, not production code.
Documentation is committed separately to avoid self-referential evidence hashes.
The implementation cap remains **eight, provisional**; no stage has passed the
production hardware release gates.

## Latest full-suite verification at 6111c5b

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

### Distribution collection

`uv build --wheel` produced `wingman-5.1.1-py3-none-any.whl` (686868 bytes):

```text
SHA-256 a4bc659e87ff7367cde3079b1027ab0fd8d92c139789b95af3c8b4b59ed2a3d7
```

`crops.py`, `cropstore.py`, `cropwindow.py`, `croppicker.py` and
`cropcontroller.py` were byte-compared with the tested checkout and imported
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
| Native lifecycle and geometry | Close, source exit/logout/return, capture theft, lock/visibility, rescue, source/picker resize, negative coordinates, occlusion and primary alert pulses | NOT RUN |
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
