# PR #276 Review Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring PR #276 onto current `main`, fix the confirmed companion, webhook, and keyboard regressions, clean the stale contracts, and produce a Windows-smoke-ready merge candidate without reusing the contaminated prior cleanup branch.

**Architecture:** Continue from PR head `603c6e4f` in a fresh isolated branch/worktree, merge current `origin/main`, and preserve both the PR's UX changes and v5.11's Archive feature. Keep companion source identity separate from visibility, preserve credential-bound webhook metadata across transient optional lookup failures, and make Character-menu Tab traversal explicit rather than relying on browser default behavior after synchronously hiding a portal. Land the pre-existing multi-companion visibility correction as its own independently reviewable commit.

**Tech Stack:** Python 3.11+, pytest, Ruff, plain HTML/CSS/ES5 JavaScript, Node runtime harnesses, Chromium/CDP, Windows WebView2 via pywebview 6.2.1.

**Spec:** PR #276 review findings captured in this plan, plus `PRODUCT.md`, `DESIGN.md`, `AGENTS.md`, and `docs/smoke-checklist.md`.

## Global Constraints

- Never use `ux/screenshot-review-fixes` (`6edebdd9`) as a base; it is unrelated to PR head and carries hundreds of unrelated deletions.
- Preserve current `main`'s Archive feature: `archive_folder`, `archive_selected`, `btn-archive`, `ctx-archive`, `f-archdir`, and their tests.
- Preserve PR #276's webhook revision fencing and URL/name atomic persistence.
- A focus-hidden companion remains bound to its verified source; visibility must not revoke source identity.
- A transient optional webhook-name lookup failure must not erase a valid name for an unchanged credential.
- Replacement webhook credentials must never inherit the previous credential's name.
- Character-menu Tab and Shift+Tab must each move exactly once in visible native order without scrolling the roster.
- Never move or resize a real EVE client window.
- Keep every non-method `Api` attribute underscore-prefixed.
- Add no framework, bundler, runtime dependency, worker pool, or pywebview upgrade.
- Follow TDD for every behavior change: failing test, observed expected failure, minimal implementation, passing focused tests, then commit.
- Do not claim Windows/WebView2 acceptance from Node, pytest, or headless Chromium.

## Final Interfaces and Invariants

```python
# wingman/preview/companionfamily.py
# A live binding is published for both visible and focus-hidden live states.
binding = live.binding if live is not None and status in {"live", "hidden-by-focus"} else None
```

```python
# wingman/ui/api.py
# _commit_webhook keeps its existing return shape.
def _commit_webhook(
    self,
    generation: int,
    previous: str,
    url: str,
    name: str,
) -> dict: ...
```

For an unchanged URL and an empty lookup result, `_commit_webhook` returns the retained safe name in `webhook_name` and `webhook_status`, emits no lookup warning, and does not rewrite the persisted pair. For a changed URL and an empty lookup result, it commits `(new_url, "")` and returns the existing warning.

```javascript
// wingman/web/characters.js
// Tab handling is explicit; it does not depend on a default action whose
// original target is synchronously hidden.
function moveFromCharacterMenu(backward) { /* focus one visible tab stop */ }
```

## Task 1: Establish a Clean, Current Integration Base

**Files:**
- Modify during conflict resolution: `docs/smoke-checklist.md`
- Verify auto-merged behavior: `wingman/settings.py`
- Verify auto-merged behavior: `wingman/ui/api.py`
- Verify auto-merged behavior: `wingman/web/index.html`
- Verify auto-merged behavior: `wingman/web/settings.js`
- Verify tests: `tests/test_settings.py`
- Verify tests: `tests/test_settings_page.py`
- Verify tests: `tests/test_api_settings_fields.py`

**Interfaces:**
- Consumes: PR head `603c6e4f`, current `origin/main` (reviewed at `78adb17a`).
- Produces: a fresh cleanup branch containing both PR #276 and current-main behavior, with no unresolved conflicts.

- [ ] **Step 1: Reconfirm the immutable starting points**

Run:

```bash
git fetch origin main pull/276/head:refs/remotes/origin/pr-276
git rev-parse origin/pr-276 origin/main ux/screenshot-review-fixes
git merge-base origin/pr-276 origin/main
git rev-list --left-right --count origin/pr-276...ux/screenshot-review-fixes
```

Expected:

- PR head resolves to `603c6e4f9446bbfab0c704b13133d9e9ed1c26d7` unless the PR was intentionally updated after this plan.
- `ux/screenshot-review-fixes` remains unrelated and is not checked out, rebased, merged, or cherry-picked.

If PR head changed, inspect `gh pr view 276 -R elboaf/FlyGD-Wingman` and `git log` before adapting this plan.

- [ ] **Step 2: Create a fresh isolated cleanup branch from the PR head**

Use the worktree workflow, with branch name:

```text
fix/pr-276-review-cleanup
```

Base it on `origin/pr-276`, not the existing PR worktree and not `ux/screenshot-review-fixes`.

- [ ] **Step 3: Merge current main without taking either side wholesale**

Run inside the new worktree:

```bash
git merge --no-ff origin/main
```

Resolve `docs/smoke-checklist.md` by retaining both:

- PR #276's screenshot UX acceptance sections.
- v5.11 Archive acceptance and uploader behavior.

Do not accept entire-file `ours` or `theirs` resolutions for any overlapping Settings, API, HTML, or test file.

- [ ] **Step 4: Verify the composed Archive and webhook surfaces lexically**

Run:

```bash
rg -n "archive_folder|discord_webhook_name" wingman/settings.py
rg -n "archive_selected|identify_discord_webhook|which == \"archive\"" wingman/ui/api.py
rg -n "btn-archive|ctx-archive|f-archdir|btn-webhook-identify" wingman/web/index.html
rg -n "TARGET_KEY|archive_folder|webhookRevision|acceptWebhook" wingman/web/settings.js
```

Expected: every Archive and webhook-identity symbol above is present.

- [ ] **Step 5: Run integration-focused tests before behavior fixes**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_settings.py \
  tests/test_settings_page.py \
  tests/test_api_settings_fields.py \
  tests/test_api_discord_webhook.py \
  tests/test_uploader_page.py \
  tests/test_bridge_contract.py \
  tests/test_js_smoke.py -q
node scripts/js_smoke.js
```

Expected: PASS. Any failure at this point is an integration defect, not one of the planned behavior changes; stop and correct the merge before proceeding.

- [ ] **Step 6: Commit the main integration**

```bash
git add docs/smoke-checklist.md tests wingman
git commit -m "Merge main into PR 276 cleanup"
```

## Task 2: Preserve Companion Binding While Focus-Hidden

**Files:**
- Modify: `wingman/preview/companionfamily.py:116-143`
- Test: `tests/test_companion_family.py:409-435`
- Test: `tests/test_companion_controller.py:372-404`
- Test: `tests/test_companion_controller.py:478-520`

**Interfaces:**
- Consumes: existing `CompanionEvent("status", ...)` payload and `SourceBinding`.
- Produces: `hidden-by-focus` status rows that retain the live `SourceBinding` without persisting or exposing it in the page snapshot.

- [ ] **Step 1: Change the family expectation to retain the binding**

Update the focused transition assertion:

```python
hidden = events[-1].payload[0]
assert hidden == dict(initial, status="hidden-by-focus", binding=BINDING)
```

Update the coalescing test to assert every hidden live row still carries its corresponding binding rather than asserting every binding is `None`.

- [ ] **Step 2: Change the controller expectation to retain internal authority**

In `test_hidden_focus_status_uses_existing_publication_without_persistence`, publish `facts.binding` for both `live` and `hidden-by-focus`:

```python
for status in ("live", "hidden-by-focus", "live"):
    event = CompanionEvent(
        "status",
        None,
        (dict(value, status=status, binding=facts.binding),),
    )
    h.controller.native_event(event)
    assert h.controller.drain().result(2)
    assert h.controller._rows[row["id"]]["binding"] == facts.binding
    assert h.path.read_bytes() == saved
```

Add a regression assertion after the hidden status showing that `reset_geometry()` uses `facts.binding.client_size`, not the `320×210` fallback.

- [ ] **Step 3: Run the focused tests and observe the expected failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_companion_family.py::test_focus_visibility_transitions_publish_status_once \
  tests/test_companion_controller.py::test_hidden_focus_status_uses_existing_publication_without_persistence -v
```

Expected before implementation: FAIL because the hidden status publishes or stores `None`.

- [ ] **Step 4: Publish the binding for both live visibility states**

Implement the minimal status predicate:

```python
binding=(
    live.binding
    if live is not None and status in ("live", "hidden-by-focus")
    else None
),
```

Do not broaden binding publication to `waiting`, `off`, `disabled`, `stopping`, or `source-unavailable`.

- [ ] **Step 5: Run companion verification**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_companion_family.py \
  tests/test_companion_controller.py \
  tests/test_companion_api.py \
  tests/test_companions_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the binding fix**

```bash
git add wingman/preview/companionfamily.py tests/test_companion_family.py tests/test_companion_controller.py
git commit -m "fix(companions): retain source while focus-hidden"
```

## Task 3: Preserve a Known Webhook Name on Same-URL Lookup Failure

**Files:**
- Modify: `wingman/ui/api.py:2137-2258`
- Test: `tests/test_api_discord_webhook.py`
- Test: `tests/test_settings_runtime.py` if returned warning/name presentation changes require a page assertion

**Interfaces:**
- Consumes: stored `(discord_webhook, discord_webhook_name)` pair and optional lookup result.
- Produces: unchanged-URL save receipts that retain a safe existing name; replacement saves still clear stale identity.

- [ ] **Step 1: Add the direct same-URL regression test**

Add:

```python
def test_failed_lookup_for_unchanged_url_preserves_existing_name(api):
    before = paths.settings_file().read_bytes()

    result = api.set_discord_webhook(OLD)

    assert result["applied"] is True
    assert result["persisted"] is True
    assert result["error"] is None
    assert not result.get("warning")
    assert result["webhook_name"] == "Old name"
    assert result["webhook_status"] == "Webhook: Old name"
    assert pair(api._state.settings) == (OLD, "Old name")
    assert paths.settings_file().read_bytes() == before
```

This deliberately allows a successful no-op receipt while requiring no settings rewrite.

- [ ] **Step 2: Correct the concurrent same-URL expectation**

In `test_newer_webhook_admission_fences_older_reply_even_for_same_url`, distinguish unchanged and replacement saves:

```python
if new_operation == "replacement-save":
    assert newest["warning"] == WARNING
    expected = (NEW, "")
elif new_operation == "save":
    assert not newest.get("warning")
    expected = (OLD, "Old name")
```

Keep the replacement test proving that a new credential never inherits `Old name`.

- [ ] **Step 3: Run the two tests and observe the expected failures**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_api_discord_webhook.py::test_failed_lookup_for_unchanged_url_preserves_existing_name \
  tests/test_api_discord_webhook.py::test_newer_webhook_admission_fences_older_reply_even_for_same_url -v
```

Expected before implementation: the direct test stores `""`, and the same-URL concurrency cases still return the warning.

- [ ] **Step 4: Retain only the same credential's validated name**

Inside `_commit_webhook`, after confirming the stored URL still equals `previous`, derive the committed name before the no-op comparison:

```python
committed_name = name
if url == previous and not committed_name:
    webhook, _ = discord.parse_webhook(url)
    committed_name = discord.safe_webhook_name(
        webhook, doc.get("discord_webhook_name", "")
    )

if (
    doc.get("discord_webhook", "") == url
    and doc.get("discord_webhook_name", "") == committed_name
):
    raise _SettingUnchanged

doc["discord_webhook"] = url
doc["discord_webhook_name"] = committed_name
```

Return `committed_name` from the receipt as `webhook_name`, use it for `copy_mod.webhook_status`, and in `set_discord_webhook` add the warning only when the applied receipt's `webhook_name` is empty:

```python
if result["applied"] and not result.get("webhook_name"):
    result["warning"] = "Webhook saved, but its name could not be identified."
```

Do not preserve a name when `url != previous`.

- [ ] **Step 5: Run all webhook and settings transaction tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_api_discord_webhook.py \
  tests/test_discord_identity.py \
  tests/test_settings.py \
  tests/test_settingssharing.py \
  tests/test_settings_runtime.py -q
```

Expected: PASS, including replacement, remove, persistence rollback, generation fencing, and secret-redaction cases.

- [ ] **Step 6: Commit the webhook fix**

```bash
git add wingman/ui/api.py tests/test_api_discord_webhook.py tests/test_settings_runtime.py
git commit -m "fix(settings): retain unchanged webhook identity"
```

Only add `tests/test_settings_runtime.py` if it actually changed.

## Task 4: Make Character-Menu Tab Traversal Explicit

**Files:**
- Modify: `wingman/web/characters.js:254-310`
- Modify: `wingman/web/characters.js:540-570`
- Test: `tests/test_characters_page.py:880-910`

**Interfaces:**
- Consumes: current `menuTrigger`, the rendered Character roster, filter control, and visible document tab order.
- Produces: one deterministic focus move after Tab or Shift+Tab, with the menu closed and no roster scroll.

- [ ] **Step 1: Strengthen the runtime test beyond synchronous close focus**

Replace the current assertion that focus merely returns to the trigger. The harness should require the intended destination:

```javascript
const triggers = roster.children
  .filter(row => row.className === 'characters-row')
  .map(row => findByClass(row, 'characters-menu-trigger'));
const owner = triggers[0];
owner.dispatchEvent({type: 'keydown', key: 'ArrowDown'});
assert.equal(document.activeElement, forget);

const event = {type: 'keydown', key: 'Tab', shiftKey: SHIFT};
menu.dispatchEvent(event);
assert.equal(event.defaultPrevented, true);
assert.equal(menu.hidden, true);
assert.equal(document.activeElement, SHIFT ? filter : triggers[1]);
```

Retain the assertion that the chosen focus call uses `{preventScroll: true}`.

- [ ] **Step 2: Run the test and observe the expected failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_characters_page.py::test_characters_menu_tab_rejoins_native_row_order_without_scroll_or_trap -v
```

Expected before implementation: FAIL because Tab is not prevented and focus remains on the owning trigger in the harness.

- [ ] **Step 3: Add a visible-tab-stop helper scoped to this fixed menu**

Implement a helper that closes the menu first, then derives visible enabled tab stops so hidden menu controls cannot participate:

```javascript
function moveFromCharacterMenu(trigger, backward) {
  closeMenu(false);
  var selector = 'button:not([hidden]):not(:disabled), '
    + 'input:not([hidden]):not(:disabled), select:not([hidden]):not(:disabled), '
    + 'textarea:not([hidden]):not(:disabled), [tabindex="0"]';
  var stops = Array.prototype.filter.call(document.querySelectorAll(selector), function (node) {
    return node.getClientRects().length
      && window.getComputedStyle(node).visibility !== 'hidden';
  });
  var index = stops.indexOf(trigger);
  var target = index === -1 ? null : stops[index + (backward ? -1 : 1)];
  if (target && target.focus) target.focus({preventScroll: true});
}
```

Use the trigger captured before `closeMenu()` clears `menuTrigger`:

```javascript
if (event.key === 'Tab') {
  event.preventDefault();
  var trigger = menuTrigger;
  moveFromCharacterMenu(trigger, event.shiftKey);
  return;
}
```

Do not wrap focus at the document ends and do not synthesize key events.

- [ ] **Step 4: Run Character page tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_characters_page.py -q
```

Expected: PASS.

- [ ] **Step 5: Verify real Chromium forward and backward traversal**

At `840×625`, open the first Character actions menu and verify with actual CDP keyboard input:

- Tab closes the menu and lands on the second row's actions trigger.
- Shift+Tab closes the menu and lands on the filter.
- Neither gesture changes the roster's `scrollTop`.
- One additional Tab continues from the new control, proving there is no hidden-menu trap.

Record browser version and results in the implementation notes or commit body; do not call this Windows/WebView2 acceptance.

- [ ] **Step 6: Commit the keyboard fix**

```bash
git add wingman/web/characters.js tests/test_characters_page.py
git commit -m "fix(ui): restore character menu tab order"
```

## Task 5: Fix the Pre-existing Multi-Companion Hide-Active Leak

**Files:**
- Modify: `wingman/preview/companionfamily.py:542-590`
- Test: `tests/test_companion_family.py`

**Interfaces:**
- Consumes: one sweep-level `global_hidden`, `hide_active`, `foreground`, and each live companion's source HWND.
- Produces: one independent `source_hidden` decision per companion.

- [ ] **Step 1: Add an insertion-order regression test**

Add a two-companion test with distinct HWNDs:

```python
def test_hide_active_hides_only_the_foreground_companion(family):
    native, events, windows, _, _, _ = family
    other = replace(DEFINITION, id="22222222222242228222222222222222")
    native.reconcile((spec(), spec(other)), 2)
    native.live[other.id].binding = replace(BINDING, hwnd=20)
    events.clear()

    native.apply_lost_focus_hidden(False, True, BINDING.hwnd)

    assert native.live[DEFINITION.id].window.hidden is True
    assert native.live[other.id].window.hidden is False
```

Also run the same assertion with reversed definition order so behavior cannot depend on insertion order.

- [ ] **Step 2: Run the regression test and observe the expected failure**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_companion_family.py::test_hide_active_hides_only_the_foreground_companion -v
```

Expected before implementation: the later companion is incorrectly hidden when the foreground companion is evaluated first.

- [ ] **Step 3: Separate sweep-level and source-level visibility**

Rename the input locally and stop overwriting it:

```python
global_hidden = hidden
for identity, live in tuple(self.live.items()):
    ...
    source_hidden = visibility.should_hide_source(
        global_hidden=global_hidden,
        hide_active=active,
        foreground=foreground,
        source_hwnd=live.binding.hwnd if active else 0,
    )
    live.window.set_active(
        self._ring_identity == identity and not source_hidden
    )
    was_hidden = live.window.hidden
    live.window.set_hidden(source_hidden, authorized=...)
```

Use `source_hidden` consistently for ring and window state. Do not alter the pure `visibility.should_hide_source` contract.

- [ ] **Step 4: Run companion visibility and runtime tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_companion_family.py \
  tests/test_companion_controller.py \
  tests/test_companion_backend_fixes.py \
  tests/test_companions_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit this independently droppable correction**

```bash
git add wingman/preview/companionfamily.py tests/test_companion_family.py
git commit -m "fix(companions): isolate per-source focus hiding"
```

## Task 6: Correct Stale Layout Contracts and Test Names

**Files:**
- Modify: `DESIGN.md:360`
- Modify: `docs/smoke-checklist.md:6815`
- Modify: `wingman/web/style.css:1832`
- Modify: `tests/test_page_conventions.py:2591-2615`

**Interfaces:**
- Consumes: implemented Preview track `minmax(200px, 260px)` and lexical CSS checks.
- Produces: documentation and test names that accurately state what is automated versus manually verified.

- [ ] **Step 1: Update present-tense Preview track references**

Change the current-state references from:

```text
minmax(150px, 260px)
```

to:

```text
minmax(200px, 260px)
```

Keep `DESIGN.md`'s explicitly historical Round 6 reference at 150px.

- [ ] **Step 2: Replace the retired Alerts hidden-row example**

At `wingman/web/style.css:1832`, remove references to deleted `#alerts-previews-off`, `#alerts-no-folder`, and `#alerts-depends`. Use current raised-only examples such as `#preview-binds-off` and `#eve-blockers`.

- [ ] **Step 3: Rename behaviorally overstated lexical tests**

Rename:

```python
def test_sticky_edges_declare_fractional_scrollport_boundary_cover(): ...
def test_nested_work_panes_declare_overscroll_containment(): ...
```

Keep their existing lexical assertions. Do not claim they paint pixels or dispatch wheel input. Leave the corresponding Windows/browser behavior open in `docs/smoke-checklist.md`.

- [ ] **Step 4: Run documentation and convention checks**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_page_conventions.py \
  tests/test_documentation.py \
  tests/test_product_contract.py -q
rg -n "minmax\(150px, 260px\)" DESIGN.md docs/smoke-checklist.md
```

Expected:

- Tests pass.
- Remaining 150px references are explicitly historical, not current acceptance criteria.

- [ ] **Step 5: Commit contract cleanup**

```bash
git add DESIGN.md docs/smoke-checklist.md wingman/web/style.css tests/test_page_conventions.py
git commit -m "docs(ui): align review contracts with measured layout"
```

## Task 7: Full Verification and Manual Acceptance Handoff

**Files:**
- Inspect: all changed files since the integration commit
- Update only with actual evidence: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: a clean, reviewable candidate with automated evidence and an explicit Windows acceptance remainder.

- [ ] **Step 1: Inspect the complete diff and branch ancestry**

Run:

```bash
git status --short
git log --oneline --decorate origin/pr-276..HEAD
git diff --stat origin/pr-276..HEAD
git diff --check origin/pr-276..HEAD
git diff origin/pr-276..HEAD
```

Verify:

- No unrelated deletions or old-history changes entered from `ux/screenshot-review-fixes`.
- Archive behavior remains in the merged result.
- No placeholders, debug output, real credentials, or generated browser artifacts are tracked.

- [ ] **Step 2: Run Ruff and executable JavaScript gates**

Run:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
node scripts/js_smoke.js
```

Expected: all commands exit 0.

- [ ] **Step 3: Run the rendered status-strip gate**

Run:

```bash
rm -rf /tmp/wingman-pr276-status-strip
node scripts/check_status_strip_layout.js \
  --chrome /usr/bin/google-chrome \
  --out /tmp/wingman-pr276-status-strip
```

Expected: all cases and assertions pass, including forced-colour paint checks.

- [ ] **Step 4: Run the complete pytest suite with prerequisites present**

Follow `docs/overview-layout-sharing-verification.md#local-verification-prerequisites`, then run:

```bash
uv run --no-sync python -m pytest tests/ -rs
```

Inspect every skip. Expected platform-only skips are acceptable on Linux; Node/native codec skips are not acceptable full-suite coverage.

- [ ] **Step 5: Perform the required installed Windows/WebView2 smoke pass**

Use `docs/smoke-checklist.md` and record the checkout/build plus 100%, 125%, 150%, and 200% scaling. At minimum verify:

- Focus-hidden companions retain working Reselect region, title validation, and source-sized Reset position.
- With two companions and hide-active enabled, only the foreground source's companion hides.
- Same-URL webhook Save during unavailable metadata lookup retains the cached name; replacement Save does not inherit it.
- Character menu Tab and Shift+Tab each move once in the expected direction without scrolling.
- Archive footer/context actions and Archive folder remain present after current-main integration.
- No changed screen overflows at the 840×625 CSS floor.

Mark checklist items passed only with actual installed Windows evidence.

- [ ] **Step 6: Run post-implementation polish and inspect its edits**

Use `polish-core --fix` against the integration base. Accept only high-confidence behavior-preserving fixes, inspect every edit, then rerun the affected focused tests and the full gates above if source changed.

- [ ] **Step 7: Produce the reviewer-facing change explanation**

Use `change-explainer` after fresh verification. Include:

- exact base and head SHAs;
- why hidden visibility retains binding;
- why same-URL failure preserves metadata while replacement clears it;
- the explicit Tab-order behavior;
- the separately scoped pre-existing multi-companion correction;
- automated results and remaining Windows-only risks.

- [ ] **Step 8: Quarantine the contaminated prior branch only after confirmation**

Before deleting anything, show:

```bash
git show -s --oneline ux/screenshot-review-fixes
git rev-list --left-right --count origin/pr-276...ux/screenshot-review-fixes
git worktree list
```

Request explicit confirmation before removing its linked worktree or deleting local/remote branches. It must not be merged into, rebased onto, or substituted for this cleanup branch.

## Self-Review Results

- **Spec coverage:** Every confirmed PR finding has a test-first task. Current-main integration, the contaminated branch, the pre-existing visibility leak, documentation drift, full automated verification, and Windows acceptance are separately covered.
- **Placeholder scan:** No TBD/TODO/fill-in-later steps remain. Optional file staging is conditional only where the plan explicitly says not to stage an unchanged file.
- **Type and contract consistency:** Existing `CompanionEvent`, `SourceBinding`, `_commit_webhook`, bridge receipt, and page-handler contracts remain unchanged. No new public API or persisted data key is introduced.
- **Scope boundary:** The multi-companion hidden-state defect is isolated in its own commit so a reviewer can reject it without blocking the PR-introduced fixes.
