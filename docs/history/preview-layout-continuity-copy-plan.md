# Preview placement continuity and geometry copy plan

## Intended outcome

- A preview already associated with Character A keeps its current size and location when that same EVE HWND and process returns to character selection.
- The client remains semantically unidentified at character selection. Character A is not reported online and does not receive character-specific hotkeys or alerts.
- Character B receives B's saved geometry, or the normal default placement, as soon as B is positively identified in the same client.
- A user can copy only x/y/w/h from any character with usable saved geometry, including an offline character, to an online or offline target.
- Manual keybind entry remains discoverable through `Edit…`.
- The Previews settings information architecture stays intact. This change adds no top-level setting and does not redesign unrelated sections.

## Evidence and constraints

- `discovery.list_clients()` keys named clients by character and unidentified clients by `hwnd:0x...` (`wingman/preview/discovery.py`).
- `PreviewHost._sweep()` reconciles `_windows` by those keys. A named-to-unidentified title transition is therefore one removal plus one addition, and `_resolve_rect()` defaults the new HWND key (`wingman/preview/host.py`).
- `build_preview_host()` correctly refuses to persist an `hwnd:` layout key (`wingman/__main__.py`). Generic titles must remain non-durable.
- The current preview rectangle can be newer than settings because `LayoutStore` debounces writes for one second (`wingman/preview/store.py`, `test_a_layout_change_updates_the_in_session_cache`). The host cache can also be older: the offline branches of `set_preview_size` and `reset_preview_layouts` write settings without updating `_saved`, and the same host survives disable/enable. There is no safe unconditional "host always wins" merge until those writers synchronize the cache (`wingman/ui/api.py`, `wingman/preview/host.py`).
- `PreviewHost` is constructed while disabled and keeps its startup `_saved` map. Existing offline layout writes must update that dormant cache or enabling previews later in the same session reads stale geometry (`wingman/__main__.py:355-528`).
- `_resolve_rect()` and `geometry.clamp_to_monitors()` are the existing monitor-safety path. They deliberately rescue a rectangle for display without rewriting its durable coordinates, so reconnecting a monitor can restore the original arrangement.
- Effective lock state is stored in `preview.locked`; `layouts[*].locked` is a legacy round-tripped field and must not be copied from the source (`wingman/preview/host.py`, `wingman/preview/layout.py`).
- The character table was deliberately reduced to five cells in PR #133. Lock and Never minimize now live under their global controls (`docs/previews-character-table-design.md`).
- `Edit…` is the manual-entry escape hatch for keyboard layouts where browser `event.code` does not represent the intended key (`wingman/web/previews.js`, `tests/test_bookmarks_validate.py`).
- Settings commit per operation and use `{applied, persisted, error}`. There is no Save button (`DESIGN.md`).
- Page-owned dialogs must use Wingman's overlay. An armed keybind capture must be ended before opening an input-bearing overlay (`DESIGN.md`, `wingman/web/panel.js`, `tests/test_page_conventions.py`).
- Nothing in pytest executes the page. UI correctness requires lexical guards plus Windows screenshots and a manual smoke pass.
- The current Previews section measures 1,476px tall in a 504px pane at 840x625, and 1,458px in a 679px pane at 1280x800. Its grouping is clear; the density is mostly legitimate controls and explanatory hints.

## Decisions for review

### 1. Transient continuity is keyed by HWND and PID, but carries no character semantics

Maintain a host-only map from `(hwnd, pid)` to the last positively identified character while that physical client remains present in consecutive sweeps.

For a named-to-unidentified transition on the same pair:

1. Capture the old preview's current rectangle before reconciliation closes it.
2. Clamp that rectangle directly and create the generic preview there. This continuity path deliberately bypasses `_resolve_rect()`'s `restore_preview_positions` gate: the client is continuing on screen, not reopening from a saved layout.
3. Keep the generic discovery key in `_clients` and `_windows`.
4. Preserve the existing guarantees that `characters()` excludes it, character focus hotkeys and alerts cannot target it, cycle does not stop on it, and its label falls back to the generic EVE title.

The transient owner is consulted only for:

- current-rectangle handoff; and
- preview exclusion, so an opted-out Character A does not suddenly acquire a generic preview at character selection.

It is not consulted for online state, keybind routing, cycling, alerts, labels, lock, or never-minimize. Tests distinguish the two new behaviors (rectangle handoff and exclusion inheritance) from regression coverage for the existing generic-client guarantees.

The map is pruned whenever a physical `(hwnd, pid)` is absent from a sweep and cleared during teardown. A reused HWND with a different PID cannot inherit it. A cold-start unidentified client has no map entry and uses normal default placement.

**Rejected:** treating Character A as still online. That would route stale hotkeys and alerts after identity was lost.

**Rejected:** persisting HWND associations. HWNDs are reusable and there is no durable evidence connecting a cold-start selection screen to a character.

**Rejected:** re-keying and retaining the existing `PreviewWindow` object. Its neighbour and resize-all callbacks capture the creation key. Rebinding all of those callbacks broadens the interaction regression surface merely to avoid a small thumbnail recreation.

### 2. Direct A-to-B transitions retain existing behavior

When B is positively identified, no transient alias is used for placement. B opens through `_resolve_rect("B", ...)`:

- saved B geometry when `restore_preview_positions` is on;
- the default stack when it is off or B has no layout;
- the existing monitor clamp in either path.

The map is then updated to B for a later B-to-selection transition.

### 3. The host and LayoutStore provide one ordered geometry mutation path

Protect every `_saved` read and replacement with `PreviewHost._lock`. Copy-on-write replacement remains useful for stable snapshots, but it happens under that lock so a bridge-thread copy and preview-thread drag cannot lose one another's keys.

Make the host cache authoritative only after closing its known stale paths:

- after the offline `set_preview_size` branch persists an entry, synchronize that key into `_saved`;
- after the offline `reset_preview_layouts` branch persists the clear, clear `_saved` too;
- use the host snapshot whenever a host exists, running or stopped;
- fall back to deserialized settings only when preview-host construction failed or the platform has no host.

Add `LayoutStore.replace(stable_key, entry) -> bool` for immediate per-key replacement. It will serialize with `_write()` and `clear()` through a dedicated write-order lock, remove or replace any pending delta for the target under the existing pending lock, persist under `settings.update()`, and return failure on `OSError`. `record()` remains cheap and does not hold the write-order lock, so dragging does not block on disk. Acquiring the write-order lock before `_write()` snapshots pending data prevents an older timer from taking a target delta out of the queue and writing it after a completed copy.

Add a host `copy_layout(target, source)` operation:

- atomically re-read the source and target entries under `_lock`;
- reject a missing, malformed, identical, or transient `hwnd:` source/target;
- construct a target entry from source x/y/w/h while preserving the target's legacy `locked` field, or `False` when the target has no entry;
- call the injected `LayoutStore.replace` before changing host/window state;
- on persistence success, replace `_saved` under `_lock` and, when running, queue one preview-thread command;
- clamp through `geometry.clamp_to_monitors()` and move an open target with `PreviewWindow.move()`;
- leave a closed, stopped, or excluded target cached for its next opening;
- never move or resize the real EVE client.

`Api.copy_preview_layout(target, source)` will:

1. validate two distinct usable character names;
2. derive valid targets from the exact row-producing union: currently named characters, `preview.seen`, and character hotkeys;
3. delegate atomically to the host whenever one exists, so the latest undebounced source and target state is used;
4. use deserialized settings plus the nested preview writer only when no host exists;
5. return `{applied, persisted, error}` and refuse without moving the target when persistence fails.

Layout sources are a separate set from valid targets. They include every structurally valid, non-`hwnd:` saved entry, even if an old settings file has no corresponding roster row. Online/offline status comes only from currently named characters.

A copied rectangle from a detached monitor remains durable as copied. When displayed, it is rescued through the existing clamp without rewriting the durable coordinates, matching every other saved layout.

**Rejected:** unconditional host-over-settings precedence without synchronizing existing offline writers. The host is currently stale on those paths.

**Rejected:** copy-on-write without `_lock`. Two read-modify-replace writers can still drop an update.

**Rejected:** persisting through the API while leaving an older target delta pending in `LayoutStore`. Its later debounce can silently undo the copy on disk.

**Rejected:** calling Win32 monitor APIs from the bridge thread. HWND and monitor work remains on the preview thread.

**Rejected:** copying through `set_preview_size`. It cannot copy x/y and would create a second partial geometry path.

### 4. Add a compact choice mode to the existing page-owned dialog

Extend the existing overlay with `WM.choose(title, body, groups, confirmLabel)`, resolving to the selected value or `null`.

The choice mode will:

- show one labelled `<select>`;
- build options with DOM properties/text content, never HTML strings;
- support labelled Online and Offline `<optgroup>` groups;
- include the select in the focus trap;
- focus it on open;
- extend the existing Escape branch so choice cancels rather than resolving affirmatively;
- restore focus to the triggering Copy button when the row still exists;
- use the existing queue, overlay, buttons, and visual vocabulary.

`previews.js` must call `endCapture()` before opening it. This prevents the document-level keybind listener from consuming Tab or the first typed key.

**Rejected:** a per-row inline selector. The character list is a `display: contents` shared grid, and an inserted spanning row adds placement and repaint hazards while making an already long section longer.

**Rejected:** an always-visible selector. It adds one large control per character and worsens the reported clutter.

**Rejected:** a second screen-specific overlay. The existing overlay already owns focus trapping, queueing, Escape behavior, and focus restoration.

### 5. Keep keybind actions and make copy visibly about geometry

- Keep capture, conditional `Clear`, and `Edit…` unchanged.
- Rename the final column from `Size` to `Geometry`.
- Keep one grid cell and render `Size…` plus conditional `Copy…` inside it.
- Exclude the target from the picker.
- Offer only structurally valid saved layouts.
- Group sources by current online/offline status with text labels, not color.
- Do not render `Copy…` for a target with no eligible source.
- When no target has an eligible source, show one shared hint: `Move or resize another character's preview to make its placement available here.`
- After success, announce whether the open target moved now or the offline target will use the placement next time.
- If a source disappeared after the picker opened, close the overlay normally, report the endpoint's specific refusal, refresh state, then focus the rebuilt target character's Copy button. If that target or action no longer exists, use the dialog layer's normal enabled-control fallback rather than focusing a detached node.

A browser probe at 840x625 found that `Size…` plus `Copy…` still fits the current five-cell table with no host overflow; only the intentionally ellipsized long character name overflowed its own text box.

### 6. No broader Previews overhaul in this change

The small cleanup is the Geometry grouping and conditional affordance above. Do not split the section, hide existing explanatory text, or move global keybinds.

A future broader option would separate preview-window behavior from characters and keybinds. That reduces scroll depth but adds navigation state and hides relationships recently clarified by PRs #127 and #133. One user's clutter report is not enough evidence for that disruption.

## Data and compatibility

- No new persisted setting or schema version.
- No migration.
- Existing `preview.layouts` entries retain their shape.
- Source x/y/w/h are copied exactly; source keybinds, effective lock, exclusion, never-minimize, and every other preference remain untouched.
- Generic `hwnd:` keys remain excluded from durable layouts and rosters.
- All generated UI text uses text content, so character names cannot inject markup.

## Failure and concurrency behavior

- A discovery miss clears transient physical-client ownership rather than risking identity leakage. A client that reappears unidentified after a missed sweep uses the default path.
- A changed PID prevents rectangle or exclusion inheritance even if the HWND is reused.
- Source eligibility is recomputed atomically by the host when the API call arrives, not trusted from the open picker.
- Every `_saved` read/replacement is guarded by the host lock; every immediate store replacement, debounce write, and clear is ordered by the store write lock.
- `LayoutStore.replace` supersedes a pending target delta before reporting persistence, so an older drag or typed size cannot undo the copy at the next launch.
- A failed settings write refuses the copy and does not update the host cache or move the target.
- A stale-source refusal rebuilds rows and restores focus by target character identity, never by retaining a detached button node.
- A host command posted just before target closure updates the cache but safely finds no window to move.
- A target that opens before the queued command is processed receives the copied rectangle from the same cache.
- Existing optimistic limitations of posted host commands remain: the bridge cannot prove that a later Win32 move succeeded. Persistence remains authoritative for the next placement.

## Files and responsibilities

- `wingman/preview/host.py`
  - transient physical-client ownership and rectangle handoff;
  - locked layout snapshots, offline-writer synchronization, and atomic copy orchestration;
  - queued application of copied rectangles.
- `wingman/preview/store.py`
  - ordered immediate per-key replacement that supersedes pending target deltas.
- `wingman/preview/win32.py`
  - one distinct `WM_APP` command for applying a complete preview layout.
- `wingman/ui/api.py`
  - source payload, known-character validation, and `copy_preview_layout`.
- `wingman/web/previews.js`
  - Geometry actions, source grouping, picker flow, stable focus restoration, status and empty states.
- `wingman/web/panel.js`, `wingman/web/index.html`, `wingman/web/style.css`
  - reusable choice-mode overlay and its accessible states.
- `wingman/web/dev.js`
  - realistic online/offline saved-layout sources for browser and screenshot review.
- `scripts/shoot_screens.py`
  - staged copy-picker capture and a complete Previews-page capture.
- `DESIGN.md`
  - document the page-owned choice-dialog mechanism and focus requirements without changing unrelated conventions.
- `docs/smoke-checklist.md`
  - same-session selection transitions, copy states, manual-entry regression, and screenshot checks.
- `tests/test_preview_host.py`, `tests/test_preview_store.py`, `tests/test_preview_wiring.py`, `tests/test_api.py`, `tests/test_api_settings_fields.py`
  - host/store ordering, cache synchronization, API behavior, and public bridge invariants.
- `tests/test_page_conventions.py`, `tests/test_dev_harness.py`, `tests/test_shoot_screens.py`
  - update the existing `Size` heading/track/comment guards as well as adding Geometry, picker, focus, and screenshot coverage.

## Ordered implementation steps

1. Add failing host tests for A to selection to B, cold start, multibox isolation, closure, PID mismatch, opt-out, direct A-to-B, and monitor clamping. Pin restore-off explicitly: a named-to-generic continuation keeps the current rectangle even though a later B placement still defaults.
2. Implement transient `(hwnd, pid)` ownership and the explicit continuity-rectangle path in `PreviewHost._sweep()` with no discovery or persistence schema change.
3. Add failing store/host tests for write ordering, a pending target delta superseded by copy, locked snapshots, concurrent key preservation, stopped-host cache synchronization, queued open-target movement, offline targets, and clamp behavior.
4. Implement `LayoutStore.replace`, guard `_saved` with the host lock, synchronize the existing offline size/reset writers, and add the complete-layout host command.
5. Add failing API tests for source enumeration, exact target validation, online/offline flags, target exclusion from choices, `hwnd:` filtering, geometry-only copying, latest undebounced host geometry, newer offline settings geometry, malformed/stale sources, persistence failure, stopped host, open target, and excluded target.
6. Implement `copy_preview_layout` and extend the existing preview-state payload.
7. Update the existing page-convention assertions and stylesheet comments that name the `Size` heading/track, then add failing tests for the Geometry cell, retained `Edit…`, conditional Copy, capture disarming, grouped choice options, empty/stale/success states, Escape cancellation, focus trapping, stable post-refresh focus, and bridge/public-attribute contracts.
8. Implement `WM.choose`, including the choice-aware Escape/focus branches, then implement the picker flow, styles, and dev data in ES5-compatible JavaScript.
9. Add screenshot-tool tests, then stage a picker screenshot and complete Previews-page capture in `scripts/shoot_screens.py`.
10. Update `DESIGN.md` and `docs/smoke-checklist.md` with the new dialog and Windows-only behavior.
11. Run `polish-core --fix`, inspect every edit, and rerun all verification from a clean diff.

## Testing and verification strategy

### Focused Linux checks

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_discovery.py \
  tests/test_preview_host.py \
  tests/test_preview_store.py \
  tests/test_preview_wiring.py \
  tests/test_api.py \
  tests/test_api_settings_fields.py \
  tests/test_settings_preview.py \
  tests/test_bridge_contract.py \
  tests/test_page_conventions.py \
  tests/test_dev_harness.py \
  tests/test_shoot_screens.py
```

### Full gates

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

### Windows and rendered checks

Use `scripts/shoot_screens.py` for all approved captures. Open and inspect every generated PNG, with particular attention to:

- the complete Previews page at its normal screenshot viewport;
- the compact copy picker;
- the 840x625 table state;
- no table overflow with long names and both Size and Copy present;
- Online and Offline source grouping without color dependence;
- empty-source and persistence-error messaging;
- focus restoration and keyboard operation;
- `Edit…` manual keybind entry after the picker change.

Run the updated smoke checklist against real EVE clients for:

- A to character selection retaining the current rectangle;
- B taking B's saved/default rectangle;
- two or more clients transitioning independently;
- rapid logout/login;
- closure and a different PID on reused HWND;
- monitor disconnect/reconnect;
- excluded characters;
- restore positions on and off;
- online target moving immediately;
- offline target using the copied rectangle on next launch;
- confirmation that no real EVE client rectangle changes.

The current environment has no Windows interpreter able to import `webview` and `pystray`, so `scripts/shoot_screens.py` cannot currently run here. This remains a hard pre-PR gate; do not claim completion or open the PR until a suitable Windows interpreter is available and every generated PNG has been inspected.

## Adaptation points

- If a real transition briefly disappears from discovery rather than merely changing title, stop and instrument that sequence before extending transient ownership beyond consecutive sweeps. Retaining identity through absence would conflict with the closure guarantee.
- If Windows evidence shows PID reuse can occur inside one sweep with the same reused HWND in this workload, extend physical identity with process creation time. Do not add that syscall preemptively.
- If the compact choice mode cannot remain generic without preview-specific branches in `panel.js`, keep the common focus/queue layer there and move option composition back to `previews.js` rather than growing a broad dialog framework.
- If measured table width at 840x625 differs from the browser probe, keep one Geometry entry point and move Size/Copy into its compact menu rather than shrinking names or removing `Edit…`.
- If complete nested-scroll capture makes `shoot_screens.py` materially more complex, capture deterministic top/middle/table segments with manifest labels instead of introducing fragile image stitching.

## Explicit exclusions

- Durable HWND, account, launcher, or process-to-character associations.
- Solving cold-start character-selection identity.
- Copying keybinds, lock state, exclusion, never-minimize, or other preferences.
- Moving or resizing a real EVE client.
- Replacing or hiding manual keybind entry.
- A broad Previews settings reorganization.
- New dependencies, frameworks, bundlers, or a JavaScript test harness.
- Changes to unrelated Settings sections.
