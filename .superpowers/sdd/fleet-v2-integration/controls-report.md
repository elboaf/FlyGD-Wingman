# Displayed On / Stop continuation — controls report

Base: `bb7218fc8a6649a58904c58e215fc44936b990d0` (`docs(fleet): record bounded local integration checkpoint`). Branch: `integrate/fleet-v2-runtime`. Scope is the approved bridge/page continuation; no worker, protocol, state, producer, timing, native, HTML or CSS changes.

## What changed

- `wingman/ui/api.py`: explicit safe status projection plus detached `controls.participation` / `controls.sources` DTOs. No recursive serialization of automatic pending commands, cancellation commands, receipt bodies or history timestamps. The page receives a small automatic summary instead.
- Existing On/Off and Stop endpoints accept the original rendered DTO. A closed recursive comparison checks exact keys, native types and values against one captured immutable status. This deliberately does not compare delivery/presentation order. Trusted typed status supplies the protocol-valid UUID/integer domain; malformed external fields cannot equal that authority (including `True` versus integer `1`). No action registry, opaque proof, new persistence format or cached-CAS substitution was introduced.
- Bound On forwards the supplied CAS/binding and only the original typed pending participation that matched that observation. Missing/stale authority with an observed baseline refuses before settings/queue effects. An actually absent baseline retains the existing explicitly unbound preference behavior; it cannot acquire server consent.
- Off still reaches local inhibition before settings I/O. When supplied authority is stale or worker bound authentication refuses admission, the existing unbound Off port is used without an invented CAS or unseen supersedes. Conflicting durable history remains. Local preference and observed server choice remain separate.
- Stop handles observed sources, original unresolved Starts, and original pending Stops separately. Only unknown-source cancellation of an original Start uses generation zero / automatic None. A repeated pending Stop passes `supersedes=None` to the existing worker reuse path, preserving its request UUID, timestamp, CAS and durable command.
- The hide-EVE-tools guard includes typed automatic enabled/pending/queued/unknown authority, unresolved participation and cutover. Settled inert automatic history alone does not prevent hiding. Its refusal explicitly distinguishes local sharing Off from automatic verification consent.
- `wingman/web/fleetsharing.js`: controls retain detached authority at paint; click captures it before `WM.confirm`. On and Stop confirmations cannot adopt later state. Binding/route/visibility/screenshot ownership revokes obsolete dialog continuations; a newer Off also revokes an older On dialog and submits immediately. Keyed source rows, focus/disclosure handling and ES5 conventions remain.
- Persisted Start wording is now **“Start saved; outcome unconfirmed.”** Expired unresolved Starts remain journaled, are not replayed, and are not fabricated terminal results. Existing local-result precedence scenarios now use real `rejected` results rather than invented `expired` results.
- `wingman/web/dev.js` uses the new safe control DTO/signatures, refuses missing/stale On/Stop authority, permits conservative Off, and represents expired Start as unresolved persisted work. No private command objects are fabricated or exposed.

## Test migration and original 17 residuals

Every original failing case remains; no skip or deletion was used:

1. `test_owner_projection_restores_pending_uuid_and_never_exposes_keys_or_sessions`: rendered Stop authority and actual Start replacement.
2. `test_saved_new_binding_never_exposes_previous_owned_roster`: explicit test-only worker history acknowledgement permits the fresh fixture transition.
3–6. `test_bound_source_queued_after_pairing_keeps_saved_identity_at_ingestion`: all original six parameter cases remain; the four failed variants now use current Stop arguments and a permitted fresh transition. Newly bound commands are checked through bounded saved-stage progress, not a one-turn assumption.
7. `test_pairing_browser_is_current_explicit_persisted_action_once`: bounded stage/action assertions prove the approval URL was saved before opening.
8–9. `test_browser_launch_failure_is_visible_and_only_new_explicit_action_retries[pair-*]`: current persisted stages and real distinct UUID admissions, preserving both false-return and exception cases.
10–12. `test_old_browser_failure_cannot_overwrite_new_action_or_binding`: all action/binding × pair/grant cases remain. Actual binding change is asserted before judging obsolete callbacks.
13. `test_expired_start_is_correlated_to_exact_uuid_not_aggregate_status`: pins original durable Start and no replay; no fabricated expiry success/removal.
14. `test_one_source_ack_never_acknowledges_another_pending_uuid`: proves exact journal correlation independently of the later actual roster read. ACK correctly leaves `sources=None` until that read.
15. `test_pending_source_from_actual_json_is_stoppable_through_new_api`: preserved real JSON restart and original command authority.
16. `test_owned_grant_uses_exact_paired_origin_and_rejects_stale_binding`: genuinely changes binding using an explicitly acknowledged fixture transition before draining the old browser action.
17. `test_hot_api_submission_inside_pairing_save_preserves_reserved_batch`: preserved the real hot save, full batch, restart, stale status and terminal settlement barriers. Upgrade can refuse bound Off before the inhibit latch; the test proves conservative unbound local Off, waits for authenticated displayed observations, then explicitly confirms a new Off intent. It never silently rebases the old intent.

Pairing discovery: the existing fake returned `https://relay.test/approve` even when initial setup selected the configured default origin. The test setup now returns an approval URL at the actually saved origin. Production origin validation was not weakened.

**Fresh setup remains a distinct unfinished UI workflow.** Test-only `change_fixture_binding` explicitly acknowledges settled automatic history through the existing worker port. The production Fresh setup adapter/page does not acknowledge, discard or rewrite history. Retained automatic-Off history can therefore still refuse Fresh setup pending a separately designed/approved history-disposition UI. Fixture greenness is not full product-readiness evidence. No automatic-On control or consent grant was added.

## TDD and independent evidence

- Initial focused baseline: **17 failed, 102 passed**. All failures were reproduced before implementation, matching the checkpoint's independent evidence.
- New Python authority/privacy/hide-guard tests before adapter changes: **32 failed, 1 passed**. Missing observation arguments failed at the existing endpoint contract; populated history exposed private command timestamps; automatic authority could incorrectly be hidden.
- Delayed production-page confirmation tests before page changes: **10 failed**. The page submitted without confirmation/original authority and allowed missing control authority.
- Honest persisted-Start tests then failed on the old `saved, awaiting authGD` wording before it changed.
- The actual dev module was executed under the page harness; after completing DOM/browser seams, its new contract assertion failed because controls were missing. It now passes, including unresolved Start privacy and fail-closed mutations.
- Four in-memory mutants bypassing the displayed-authority comparison are killed by independent pending/attempted/queued-ID/order assertions. Active source files were never mutated for these controls.
- Additional positive tests pin original queued and durable Stop reuse; stale/malformed On/Stop; native boolean/integer distinctions; missing baseline; immediate conservative Off; no-telemetry and permanently timing-fenced Off/Stop terminal reconciliation; detached returned payloads; and populated automatic cancellation/completion/receipt privacy.

## Verification actually run

All commands ran from this linked worktree with local offline seams, no live service calls.

**Final fresh combined gate:** the union of the exact pytest file lists in items 1–3 below, in one `uv run --no-sync python -m pytest ... -q -rs --tb=short` invocation, completed with **833 passed in 48.86s, no skips**. The same command chain then passed repository-wide Ruff lint/format, all-page JS smoke and `git diff --check`. This is the final pre-commit source/test evidence.

1. `uv run --no-sync python -m pytest tests/test_api_fleetsharing.py tests/test_fleetsharing_reservation.py tests/test_fleetsharing_hydration.py tests/test_fleetsharing_page.py tests/test_fleetsharing_control_authority.py -q --tb=short`
   - **172 passed**, latest run 22.26s. Includes production `app.js` / `fleetsharing.js` with delayed confirmations, pushed authority changes, missing authority, route/binding/screenshot invalidation, newer Off, keyed-row and focus/disclosure regressions, and executed `dev.js`.
2. `uv run --no-sync python -m pytest tests/test_fleetsharing_worker_controls.py tests/test_fleetsharing_worker_state4.py tests/test_fleetsharing_worker_timing.py tests/test_fleet_timing_integration.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_js_smoke.py tests/test_dev_harness.py -q -rs --tb=short`
   - **569 passed**, 29.45s, no skips.
3. `uv run --no-sync python -m pytest tests/test_fleet_runtime_integration.py tests/test_api.py -q -rs --tb=short`
   - **92 passed**, 5.17s, no skips. This also verifies out-of-lane existing callers without changing them; no caller handoff was necessary.
4. `uv run --no-sync ruff check .` — **passed**.
5. `uv run --no-sync ruff format --check .` — **501 files already formatted**.
6. `node scripts/js_smoke.js` — **PASS every page module loaded** for main, fleetbar and sigbar documents.
7. `git diff --check` — **passed**.

A broader exploratory wildcard run (`tests/test_fleetsharing*.py` plus integration/bridge/page/dev gates) hit the **120-second command limit** after reporting passing progress, without a completed summary. It is not counted as passed coverage. The bounded 569-test explicit gate above completed afterwards. The prerequisite-complete whole repository suite was not run here; the parent owns that independent post-commit gate. No full-suite success or skip coverage is claimed.

## Polish / scope review

`polish-core --fix`, self-review only (no subagents), against the supplied base plus working changes. Python/ES5 project conventions take precedence over modern-JS suggestions. Reviewed adapter authority/privacy, no locks across worker effects, callback/refusal handling, comments and call sites. Safe fixes: formatter normalization, unused test binding cleanup, and callback indentation. Removed remaining impossible `source_results.stage="expired"` fixture evidence in favor of real rejection/unresolved cases, preserving each scenario's behavior assertions. No unrelated fixes or new architecture.

Final production scope is three files: `wingman/ui/api.py`, `wingman/web/fleetsharing.js`, `wingman/web/dev.js`. Tests are the four approved files plus the separately focused `tests/test_fleetsharing_control_authority.py`; no other test owners changed. No push, amend, external access, power operation, app launch or other-worktree operation was performed.

## Remaining risks / manual acceptance

- Full repository prerequisite-complete pytest/native codec/Cargo gates remain for the parent; the wildcard timeout is not a replacement.
- Node executes real page logic against DOM/bridge doubles, not rendered CSS or Windows/WebView2. No rendered-browser or Windows acceptance was performed. Manually verify On/Stop dialog focus, Off reachability while On is pending, switching route/binding before answering, keyed source settlement into history, and expired-Start wording.
- Fresh setup with retained state4 automatic history is deliberately not solved by this change. There is no UI history-disposition workflow or automatic-consent On control.
- Capture/validation is conservative: a changed relevant source observation or pending identity requires another explicit action; a repeated identical delivery does not. Worker admission/ingestion remains the final concurrency fence after the adapter releases its status lock.

## Reviewer focus / knowledge check

1. Why must stale or unauthenticated bound Off fall back without supplying unseen supersedes?
2. Why does repeated pending Stop pass `supersedes=None` rather than the saved Stop object?
3. Which participation identities besides server generation prevent an old On confirmation from overlooking a newer choice?
4. Why can a source ACK settle one UUID while returning no authoritative source roster?
5. Which fresh-pairing test acknowledgements are intentionally unavailable to the production page?
