# Probe formation sharing: verification record

## Status and scope

**2026-09-06 — coverage/documentation checkpoint; not release-ready.** Independent
implementation-wide polish reviews and post-review verification are still pending.
Windows/WebView2, real OS clipboard and live-EVE acceptance/restoration remain
**unverified**. Passing Linux tests do not satisfy those gates.

Task base: `227397f61c143a8f378555f3f973d5b8d8314c76`.
Implementation-wide polish base: `3d77b738cc7758933b44401eb4164a6028ecdde6`.
All repository commands below ran in
`/mnt/c/dev/flygd-wingman/.worktrees/settings-sharing-design` on
`design/settings-sharing`. Python 3.11.15, uv 0.11.3, Node v26.5.0, Cargo 1.91.0;
Linux test scratch used ordinary `/tmp` and tool caches. No user/EVE files, other
checkout, real clipboard, push, merge, amend or hook bypass was used.

The checkpoint adds tests and smoke documentation only. Tests passed when added;
this is **added coverage, not a claimed RED/GREEN production fix**.

## Cross-account production-API coverage

`tests/test_api_evesettings.py` now exercises:

- `eve_settings_formations` on source A and recipient B, then export → parse with
  B's actual names → explicit rename → validate → guarded Save → decode.
- Source IDs 900/901 cannot become recipient authority. Recipient IDs 2/17 stay
  intact; additions receive 18/19; selected ID 17, scratch ID −4, unrelated keys
  and all probe values survive. A's bytes remain unchanged throughout.
- Existing `STRASSE` conflicts with incoming `Straße` via Python casefold. Only
  the explicit rename resolves it. Export has exactly the portable allowlisted
  fields. Reads/export/review/validation create no file write or backup.
- Content revisions equal SHA-256 of the bytes actually read/published. An external
  B mutation is refused without changing its new bytes or making a backup.
- Real backup-first publication writes a restorable archive of B's pre-save bytes,
  not A. A pruning exception after publication leaves `ok: true`, the committed
  revision and an explicit warning. The real backup restore function restores
  only the test-owned B; this does not certify the Windows Backups UI.
- Both read and save reject an outside-root account and an in-root symlink to it,
  using real `require_under` resolution, valid codec bytes and real workers.
  Rejection leaves outside bytes unchanged, makes no backup, and releases the lock.

There are 48 lifecycle cases (eight numeric fixtures × three outcomes × two codec
transports), plus four containment cases. One transport substitutes only codec
`_run` with a lossless signature/JSON filter; all application logic, hashing,
backup and atomic publication remain real. The other uses the locally built native
codec without substituting codec calls. Windows discovery/ESI are external seams;
the injected prune exception tests the real API's housekeeping boundary.

The numeric fixtures include minimum/maximum ranges and their supported neighbors:
`149597.8707`, `149597.87070000003`, `9804046054195200`, and
`9804046054195198` meters; the page lifecycle's `187.25000012345 * 149597870700`
and `18469.135803 * 149597870700` meter ranges; another fractional range
`184688731163.59283`; ±10^16-meter coordinates and supported neighbors;
and fractional positions. These are not only integer/binary-exact geometry.
Every native fixture passed exact encode/verify/decode equality; no codec guard
was relaxed and no native refusal was hidden. This is evidence for these fixtures,
not a claim of universal codec fidelity or EVE acceptance of all supported ranges.

The existing 72 executable formation-page scenarios consume production HTML via
`tests/html_tree.py:PageTree` and run actual `formations.js`. Their strict
parse/validate responses come from Python, not a JS copy of validation. Copy
success/error replies and file responses/IDs in that harness are controlled
fixtures, not evidence of real export or file publication. Node controls DOM
mechanics and asynchronous delivery. The new API integration exercises real
export and publication; the browser pass below also uses Python's real exporter. Existing tests cover retained-edit second saves,
late/stale callbacks, clipboard failures, atomic Add/cancel, Unicode and numeric
bounds, and ordinary reload normalization. Sharing keeps supported fractional
ranges; ordinary editor reads still normalize ranges to six decimal AU places.

## Commands and observed results

| Command | Observed result |
| --- | --- |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_codec.py tests/test_evesettings_formation_sharing.py tests/test_formations_page.py -q` before changes/build installation | 827 passed, 1 skipped in 63.45s; codec absent |
| `cargo build --offline --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir .superpowers/sdd/probe-formation-sharing-plan/codec-target` | Exit 0; release build completed in 5.03s |
| `mkdir -p packaging/bin` then `cp .superpowers/sdd/probe-formation-sharing-plan/codec-target/release/wingman-settings-codec packaging/bin/wingman-settings-codec` | Exit 0; only generated native binary installed into ignored location |
| `uv run --no-sync python -m pytest tests/test_evesettings_codec.py -q -rs` | 72 passed in 1.14s; real-codec round-trip ran |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py -k 'shared_formation_lifecycle or shared_formation_account_boundary' -q -rs` | Initial smaller matrix: 16 passed, 234 deselected in 3.64s; expanded matrix: 52 passed, 234 deselected in 7.27s |
| `uv run --no-sync ruff format tests/test_api_evesettings.py` | 1 file reformatted; no production edits |
| `uv run --no-sync ruff check tests/test_api_evesettings.py` | All checks passed |
| `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_codec.py tests/test_evesettings_formation_sharing.py tests/test_formations_page.py -q -rs` | 880 passed in 68.73s; no skips, including Node and native codec |
| `uv sync --locked --extra dev` | Exit 0; resolved 55 packages, checked 38 packages |
| `uv run --no-sync python -m pytest tests/ -q -rs` | First full pass: 6,119 passed, 9 skipped in 145.83s; final checkpoint pass after distinct recipient-geometry assertions: 6,119 passed, 9 skipped in 144.08s |
| `uv run --no-sync ruff check .` | All checks passed |
| `uv run --no-sync ruff format --check .` | 284 files already formatted |
| `node --check wingman/web/formations.js` | Exit 0 |
| `node --check wingman/web/dev.js` | Exit 0 |
| `node --check tests/fixtures/formations_page.cjs` | Exit 0 |
| `git diff --check` | Exit 0 |
| `cargo test --offline --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir .superpowers/sdd/probe-formation-sharing-plan/codec-target` | 1 passed: `large_float_survives_the_json_and_marshal_round_trip_exactly`; exit 0 |

The first copy attempt found `packaging/bin` absent (`cp: cannot create regular
file 'packaging/bin/wingman-settings-codec': No such file or directory`). Creating
that ignored directory resolved the artifact-installation issue; it was not a
codec failure. Cargo source, lockfile and dependencies were not edited. Both the
target directory and binary were confirmed ignored with `git check-ignore`.
Generated binary SHA-256:
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.

The nine full-suite skips were three real Windows junction cases in
`test_evesettings_profilecopy.py`, two real DPAPI/WinDLL cases in
`test_eveskills_dpapi.py`, one real window-station/message-pump case in
`test_preview_host.py`, and three native user32/gdi32/dwmapi cases in
`test_preview_win32.py`. No Node or codec test skipped in this local full run.

CI's Ubuntu/Windows matrix is unchanged. Current `.github/workflows/ci.yml` does
not explicitly provision Node; runtime tests skip when Node is absent. No remote
CI run was verified here, so runtime coverage there is not claimed. CI runs pytest
before its separate Cargo tests and does not install a native codec into
`packaging/bin` for pytest; the availability-gated Python/native integration cases
will skip without that artifact. No JS package, build pipeline or CI change was
added as part of this task.

## Fresh isolated Linux Chromium evidence

After inspecting the prior task's script, ran `node /tmp/task5-browser.cjs` against
this worktree's `file://.../wingman/web/index.html?dev=1&formations-share=...`.
**PASS**, no page errors. The script created a new tab and closed it in `finally`;
it did not modify existing tabs, profiles or browser processes. Clipboard writes
were captured in that page only; clipboard reads threw without consulting the OS.
Strict export/parse/validate replies came from actual Python API calls. Dev account
reads/saves remained visual fixtures, not real accounts.

Fresh checks: invalid/conflict/slow/empty/stale/unsaved visual states; native rename
blur then checkbox toggle without replacing the control; Copy including the unsaved
name; keyboard open/Review/rename/preview/Add; Cancel/focus preservation after a
Python parse error; maximum 32 long-name rows; Python rejection of 129 supplementary
code points, acceptance of 128; markup-shaped names remaining text; delayed Add
reply discarded after route exit; repeated Add producing one validation request;
and no Save or clipboard read during the tested Add/Cancel interactions.

| Viewport | Document scroll width | Review/Add/Cancel vertical bounds | Status bounds |
| --- | ---: | --- | --- |
| 840 × 625 | 840 | y=507–538 | x=238–828, y=542–560 |
| 839 × 621 | 839 | y=503–534 | x=238–827, y=538–556 |

The same measurements held with 32 long names and a code-point error. The ordinary
work/commit panes computed to `display: none`; review content scrolled independently.
These are Linux Chromium layout/native-event observations, not WebView2, Windows
scaling or screen-reader observations. The scratch script is not a shipped test;
its observed results are retained here even if `/tmp` is later cleaned.

## Controller rulings retained from the execution ledger

The following decisions were recorded in the ignored `progress.md`; their rationale
must survive scratch cleanup:

1. **Share the actual-markup test parser.** Task 2 review found duplicate HTML
   parser ownership. The controller authorized one test-only
   `tests/html_tree.py:PageTree` consumed by Formations and Fittings instead of the
   plan-mandated duplicate. The requirement was actual-markup execution, not two
   copies of the parser. This is the smallest durable fix; its cost is coupling
   the two wrappers, so both suites must be rerun. It is reversible and authorized
   no production restructuring.
2. **Allow normal Linux scratch/cache semantics.** Earlier wording forced tests
   onto `/mnt/c`, causing permission/case/timestamp failures unrelated to product
   behavior. The controller authorized ordinary test-owned `/tmp` scratch and tool
   caches while keeping repository/persistent-user-state changes inside the
   worktree. The cost is disposable test/cache files outside the worktree, not
   authorization to touch persistent user/EVE data. Full tests must run normally,
   rather than accepting those environmental failures.

## Unverified gates and remaining release obligations

- **UNVERIFIED — independent polish roles and final post-review verification.**
  Controller checkpoint at Phase 3i is intentional. Main analysis found no
  high-confidence in-scope auto-fix; independent code-reviewer,
  silent-failure-hunter, comment-analyzer and type-design-analyzer are still needed.
- **UNVERIFIED — packaged Windows/WebView2.** No Windows application launch,
  100/125/150/200% scaling, actual Windows junction handling for these new tests,
  keyboard/platform integration or screen-reader pass ran here.
- **UNVERIFIED — real OS clipboard.** Linux checks used page-local boundaries only;
  permission behavior and transfer through real Windows clipboard still need a
  deliberate manual test.
- **UNVERIFIED — two-account live EVE.** No real profile was opened or modified.
  With authorization and prepared unrelated-account copies/backups, verify actual
  probe geometry/ranges, selected formation, unrelated settings, source integrity,
  EVE-closed refusal and Backups-manager restoration as specified in the
  [Probe formations smoke checklist](smoke-checklist.md#probe-formations-profiles--edit-formations).
- **KNOWN LIMIT — optimistic stale checks.** Another process can still write after
  the final hash check; this is not an atomic compare-and-swap. EVE must remain
  closed and external editors idle during Save. No force-save or automatic merge
  is provided.
