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

## Review-fix wave — base `7d497faf`

The twelve reproduced review findings are addressed together. Numbered
`test_review_XX_*` regressions in `tests/test_preview_runtime_review.py` identify
each boundary; all use controlled Events, real storage or fake-native pump
execution rather than an alternate lifecycle arbitrator.

| Finding | Change |
| --- | --- |
| 1 | Canceled unstarted EVE admission settles without launching a pump. An admitted offline submission retains its barrier until it completes, rather than either losing the write or wedging EVE. |
| 2 | Native/offline retirement clears prepared crop authority; reactivation opens a fresh store epoch. |
| 3 | Companion off admission is retained separately from latest desired state, producing stopped then active epochs across a coalesced off/on without revoking the lease. |
| 4–5 | An admitted-primary counter keeps cleanup behind actual FIFO delivery, including an older family wake and the early-close interval. Revoked resize/reset work performs persistence without native movement. |
| 6 | Failed HWND creation submits pre-window primary and crop intents through the offline path; completed barriers are preserved across repeated stop calls. |
| 7 | Failed hotkey/hook releases remain tracked. EVE stopped/replacement is withheld until release succeeds at an existing pump boundary; no spin repost or retry owner. |
| 8 | Offline barrier completion acknowledges actual no-native/no-storage ownership and wakes the existing runtime executor, including a timed-out final stop with no pump ever started. |
| 9 | A raised start schedules retained-owner retirement through stop before an explicit retry can launch again. |
| 10 | Preview-only delivery authorization is carried into the real push path and rechecked after serialization and before each WebView/mirror delivery. Other domains' push behavior is unchanged. |
| 11 | Active-ack floors exclude old authority without blindly reserving another cleanup transition after stopped was already observed. |
| 12 | One admission drainer runs outside the runtime lock and independently of executor joins. Pending work is bounded to latest demand plus latest off edge per family; concurrent producers cannot deliver a newer on ahead of an accepted off. |

No public runtime record/signature changed. No owner replacement, second
executor, companion feature, settings schema, or frontend was added. Push spies
were updated to forward the delivery guard or exercise real serialization.
Independent parent re-review of all twelve closures remains required.

## Verification record

No native GUI was launched and no source window was manipulated. Initial
implementation Linux full-suite evidence was 10,580 passed / 11 Windows-only
skips; the following fresh results include the review-fix wave and all existing
coverage.

Linux commands used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-runtime-venv uv run --no-sync`:

- Focused pytest over `test_preview_runtime_review.py`, `test_preview_runtime.py`,
  `test_preview_host.py`, `test_preview_wiring.py`, `test_api_crops.py`,
  `test_api_settings_fields.py`, `test_main.py`, `test_main_engine.py`,
  `test_fleet_runtime_integration.py`, `test_alerts_wiring.py`,
  `test_telemetry_coordinator.py`, and `test_custom_alert*.py`, with
  `-q -rs --tb=short` — **1,273 passed, 1 Windows-only skip**, 27.70 seconds.
- `python -m pytest tests/ -q -rs --tb=short`, 900-second command timeout —
  **10,600 passed, 11 Windows-only skips**, 231.57 seconds. No Node or codec
  tests skipped; actual release-codec availability was separately verified.
- `ruff check .` and `ruff format --check .` — **passed** (386 Python files).
- `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml` —
  **1 passed**. `node scripts/js_smoke.js` — **all page modules loaded**.
- `git diff --check` — **passed**.

Windows focused verification used the prepared
`C:\Users\tng\AppData\Local\Temp\wingman-preview-runtime-f30d\venv` and portable
Node 26.5.0, with actual Windows codec availability and checkout import path
verified. The same focused modules, with
`-k "not stop_from_another_thread_really_exits_the_pump"`, yielded
**1,273 passed, 1 deselected**, 20.22 seconds. That single real-pump test was
excluded solely to honor the no-native-GUI constraint; no test code was skipped
or weakened to hide failures.

The parent's Windows full run at `7d497faf` reported six unchanged
`WinError 1314` symlink-privilege failures in `test_setup_catalog.py` and
`test_ui_setup_controller.py`. Those environment failures were not changed,
suppressed, or addressed through elevation/Developer Mode. Windows full was
not rerun here. Manual EVE on/off regression during alert/crop activity remains
a Windows smoke check, not a capacity qualification requirement.
