# Shared preview runtime — Phase 1

## Approval and scope

The user approved basic feasibility and Phase 1 after the minimal tryout worked.
Exhaustive capacity qualification was removed entirely, not deferred. This change
starts from `f30d4636c3aa143f7b9ea691467b5df65f87a7bd`, including the custom-alerts
merge `04e9e9b9`, on `feature/companion-preview-runtime`. No probe/scaffold history
was imported. The approved runtime contracts and Phase 1 from planning commit
`96c88e63` guide this implementation; its superseded qualification requirements
do not apply.

This is the shared foundation only. Production companion demand stays false.
There are no companion settings, UI, source selection implementation, controller,
windows, budget, dependencies, or changes to source-window geometry/input policy.

## Ownership and decisions

- `PreviewRuntime` owns merged committed demands, producer revision high-water
  marks, full state, semantic errors, and the one selection lease. Its single
  lazy executor is the only production caller of host start/stop. Host callbacks
  carry only the three native epochs and an outcome. Callback publication and
  host calls run outside the runtime lock; timed-out cleanup retains the owner
  and executor. Completion wakes that executor, not a retry thread.
- `PreviewHost` remains one pump with separate EVE activation and cleanup.
  `runtime_enabled` is EVE authorization, not pump liveness. Callback binding
  opts into explicit composite demands before startup; standalone/manual
  `start()` retains its original EVE-only behavior.
- EVE-off immediately fences source ingress, detached alerts, queued native
  updates, foreground/primary callbacks, activation retries, and crop authority.
  OS hotkeys are drained before activation reuses registration IDs. Desired
  hotkeys and persisted layout/configuration remain editable while EVE is off;
  old roster, registration, capture, and source geometry do not authorize work.
- Accepted primary settings FIFO remains ahead of family freeze; controller-held
  crop configuration precedes host-held commands and the final storage barrier.
  Family-off uses reusable storage drain; final stop closes storage. Offline
  crop delivery follows EVE ownership rather than an unrelated live pump.
- Retained picker HWND/font cleanup blocks only EVE reactivation. The same pump
  continues dialog/completion dispatch and unrelated messages. Cleanup retries
  only at existing pump boundaries. A failed EVE activation keeps the companion
  pump alive, drains partial EVE ownership, and retries only on explicit demand.
  An exited pump retaining native resources cannot report successful cleanup.
- Api preserves its master-setting reservation and boolean receipts. Only a
  successful write advances its producer revision; unchanged settings can retry
  without saving. Asynchronous activation/revocation/failure callbacks reconcile
  the existing shared telemetry owner. Discovery is bound before first demand.
  Early close revokes runtime and crop/hotkey/bind publication before WebViews
  are destroyed. Fleet/sharing remain independent telemetry consumers.
- Selection leases reserve a prospective pump epoch, survive companion off/on,
  and cannot be acquired on a pump already committed to stopping. Terminal pump
  acknowledgments revoke the lease and close retirement admission immediately,
  without releasing the retained cleanup owner. Delayed acknowledgments/releases
  for the retired epoch cannot revoke a later lease. Final close also revokes
  admission immediately. Picker/token/deadline implementation is not included in
  Phase 1. Reserved companion message IDs have no empty processors.

## Verification record

All automated work here is Linux/headless with fake-native resources; no native
GUI was launched and no source window was manipulated.

- Test-first runtime truth table, independent/stale revisions, blocked startup
  and stop, retained timeout owner, callback threading, lease revocation,
  same-value failure retry, and old-epoch rejection.
- Fake-native tests exercise companion-only inactivity, same-HWND family
  roundtrips, retained picker/fonts and storage saves, detached native callbacks,
  pending activation revocation, real-runtime pump retirement/lease epochs,
  and custom-alert priority before and after family roundtrip.
Final fresh verification used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-runtime-venv uv run --no-sync`:

- `python -m pytest tests/test_preview_runtime.py -q --tb=short` — **18 passed**.
  The terminal-pump lease regression first failed for both failed/stopped
  outcomes, then passed with retained-cleanup and stale-epoch assertions.
- Focused pytest over `test_preview_runtime.py`, `test_preview_host.py`,
  `test_preview_wiring.py`, `test_api_crops.py`, `test_main.py`,
  `test_main_engine.py`, `test_fleet_runtime_integration.py`,
  `test_alerts_wiring.py`, `test_telemetry_coordinator.py`, and
  `test_custom_alert*.py` — **1,189 passed, 1 Windows-only skip**, 26.04 seconds.
- `python -m pytest tests/ -q -rs --tb=short` with a 900-second command timeout
  — **10,580 passed, 11 Windows-only skips**, 225.53 seconds. Skips require real
  Windows junctions, DPAPI/WinDLL, Win32 binding, or a native message pump.
  No Node or codec tests skipped. `codec_available()` separately returned true.
  An earlier 240-second command timeout was not counted as a completed run.
- `ruff check .` and `ruff format --check .` — **passed** (385 Python files).
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`
  — **1 passed**. `node scripts/js_smoke.js` — **all page modules loaded**.
- `git diff --check` — **passed**.

Remaining review: parent performs independent polish/review and prepared Windows
verification. Manual EVE on/off regression during alert/crop activity remains an
honest Windows smoke check, not a new capacity qualification requirement.
