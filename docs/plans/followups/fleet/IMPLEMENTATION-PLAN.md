# Fleet Creation Identity Implementation Plan

> **For agentic workers:** Use executing-plans for inline Python work and a bounded TDD subagent for independent JS work. Track the checkboxes below; no further routine approval gate is needed under U-01/F-01.

**Goal:** Prevent all five predecessor Fleet callbacks from reading or affecting a replacement creation.
**Architecture:** Python owns a creation token alongside the concrete window; lifecycle owns admission and native work, with only short presentation sections for publication. Fleet JS captures the fragment token once and sends it first without changing its boot promises.
**Tech Stack:** Python, ES5 production JS, Node node:test/VM harness, pytest; pinned pywebview 6.2.1.
**Spec:** [PROPOSAL.md](PROPOSAL.md), approved by coordinator U-01/F-01 and the user implementation continuation prompt.

## Global constraints

- Worktree `.worktrees/followup-fleet-design`, branch `design/followup-fleet-identity`, base `ab06a6efde9ade0f40791d812d922356e8e6c16f`; never rebase/reset/recreate.
- Creation lifetime only; correlation, not authentication. No epoch, positive fit/ready acknowledgement or native invisibility fix.
- All five token-first signatures/defaults are those in the approved spec. Reject snapshot with None; invalid mutations no-op. Disabled-current snapshot/save/ready remain admitted; fit/move stay enabled-gated.
- Shutdown → lifecycle → short presentation; never JS, native calls, persistence or joins under presentation. Already-entered lifecycle-owned work may finish. No worker/telemetry/schema redesign.
- Only the ten source/test files listed in the approved spec plus lane documentation may change. Keep real-worker and startup headless corrections.
- No desktop/native app or global-hook launches, real user state, uploads/ESI, push/PR/merge/release. Native smoke stays deferred.
- Main #185's character title tooltip in fleetbar.js is a known overlap; do not import it here or erase it in later integration.

## Task 1 — Python callback admission and retry capture

Files: `wingman/ui/api.py`, `tests/test_fleet_bar.py`, direct callback fixtures/calls in `tests/test_fleet_presentation_worker.py`, and `tests/test_bridge_contract.py`.

- [x] Add parameterized stale/invalid/missing identity tests with native and settings effects observed. For behavior-level base-red, a test-only signature adapter drops the token only when executing the old interface; a separate signature guard pins the new contract.
- [x] Add controlled fit-sleep replacement and disabled-ready/off-on tests; run them on base and record actual behavioral failures.
- [x] Add `_fleetbar_page_id = None`, a private lifecycle-held admission helper, and token-first defaults. Snapshot holds lifecycle then presentation only while building its payload. Save remains save-only under lifecycle; move keeps native+save under lifecycle; fit captures bar once and revalidates token/bar on every retry with sleep outside lifecycle.
- [x] Adapt existing fake page installations and direct calls to matched identities, preserving real worker ownership. Run focused Fleet/worker/bridge tests.

Representative behavioral assertion (real endpoint through the test adapter):
```python
before = dict(api._state.settings['fleet_bar'])
assert page_call(api, 'save_fleet_bar_pos', 'a' * 64, 30, 40) is None
assert api._state.settings['fleet_bar'] == before
```

## Task 2 — Creation and shutdown lifetime

Files: `wingman/ui/fleetbar.py`, Fleet lifecycle sections of `wingman/ui/api.py` and `wingman/__main__.py`; tests in `tests/test_fleet_bar.py`, `tests/test_startup.py`, `tests/test_fleet_presentation_worker.py`.

- [x] Add base-red creation/style barriers showing retirement before construction and no publication before style; observe all five early callbacks and no presentation lock across native work. Cover None create, style/publication failure, cleanup failure and rollback failure through toggle and restore.
- [x] Add shutdown token retirement assertions before detach/stop/destroy, destroy-fails-once retry ownership, and a blocked admitted move whose native+save may complete before shutdown obtains lifecycle.
- [x] Implement attempt-local `secrets.token_hex(32)` and `#fleet-page=<token>`, hidden create/style, then short atomic window/token/unready publication. Retire before attempt-owned cleanup, including a None create result. Keep existing best-effort cleanup and rollback; no orphan registry.
- [x] Implement token/readiness retirement on stop before unsubscribe/join, preserving failed-destroy target; align successful Fleet destruction bookkeeping under lifecycle → presentation. Ordinary activation close/off/on does not revoke.
- [x] Run focused Python suite and inspect failure/lock-order tests before the candidate checkpoint.

## Task 3 — Executable standalone JS identity

Files: `wingman/web/fleetbar.js`, new `scripts/test_fleetbar_runtime.js`, new `tests/test_fleetbar_runtime.py`.

- [x] Write a real-script VM harness first, with DOM cells/measurements, controlled bridge-ready, font/snapshot/fit promises, timers and mouseup. Record base-red argument/identity assertions (not lexical failures).
- [x] Cover separate A/B documents; fragment changes after capture; invalid/absent fragment; delayed fit→clamp→ready, initial hydration and timer; null/rejected outcomes and revision ordering. Explicitly preserve same-URL reload limitation.
- [x] Capture exactly one validated 64-lowercase-hex fragment token inside IIFE and prepend it in Fleet-local send; malformed capture resolves null without bridge calls. Leave all existing method-name literals and render/boot behavior intact.
- [x] Run `node --test scripts/test_fleetbar_runtime.js`, wrapper pytest and all-page smoke. Parent reviews exact diff before integration with Python work.

## Task 4 — Reviewable checkpoint, polish and final verification

- [x] Establish independent lane environment (`UV_PROJECT_ENVIRONMENT=/tmp/wingman-fleet-identity-venv uv sync --locked --extra dev`). Build the locked release codec in this worktree and install into its ignored packaging/bin per AGENTS prerequisites; verify Node and codec availability.
- [x] Run focused Fleet/startup/bridge/runtime/page guards, JS smoke/syntax, Ruff lint/format and full pytest `-rs` with skips inspected; run locked Cargo test independently. Any unsupported interactive Windows/native case is deferred, not launched.
- [ ] Record red/green evidence and limitations in lane implementation-notes; commit the reviewed candidate locally with normal hooks. No amendments or out-of-lane edits.
- [ ] Run polish-core `--fix ab06a6efde9ade0f40791d812d922356e8e6c16f` over the committed candidate, inspect all proposed safe edits/findings, add scoped corrections only, and rerun fresh verification. Do not treat an empty committed range as review.
- [ ] Use change-explainer and return exact commits/diff inventory, test evidence, reload/fit/native limits and #185 overlap. Stop for coordinator acceptance.

## Plan coverage check

Tasks 1/2 implement each interface, lifetime and concurrency clause; Task 3 proves actual delayed JS arguments/boot behavior; Task 4 handles environments, gates and review. No extra subsystem or new user decision is needed. Source/test writes start only after this approved-spec-based plan is saved.
