# Preview Character Markers (#215) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, manually assigned color marker inside each primary preview's existing character-name label, editable for known online and offline characters.

**Architecture:** Store global assignments by exact character name alongside existing Preview preferences, never in layouts. Read only committed settings on the existing pump; extend the existing label measurement, bitmap cache and overlay. Put one discrete selector inside the existing Configure disclosure, using the current per-character interaction lifecycle and per-field acknowledgements.

**Tech Stack:** Python 3.11+, existing Pillow/Inter renderer, existing Win32 overlay, ES5/HTML/CSS and Node DOM harnesses; no new dependency.

**Spec:** [Approved shared design](preview-identification-design.md), especially “#215 — per-character recognition”; #214's settled containment remains authoritative. Measurements and planning-only verification: [implementation notes](preview-character-markers-implementation-notes.md).

## Global Constraints

- “Add an optional small static color marker inside the character-name label, using a curated palette and a None/reset choice.”
- “Keep the actual character name and text contrast unchanged. The marker supplements text rather than replacing it.”
- “Allow assignment and reset for known offline characters. Retain configured identities through roster pruning.”
- “No override preserves the existing appearance. The marker follows Show labels and the owner's visibility.”
- “Keep selection and alert rings unchanged. Do not add colored full-preview borders, animation, thickness controls, or per-character selection colors.”
- “Reuse #214's settled measurement/cache behavior and the same existing overlay.” No new native windows, custom styling editor, role/ship inference, per-character sizes or #217 work.
- Appearance stays global, outside saved layouts. Preserve global Standard/Large/Extra large = 17/20/23 and all-preset secondary-then-whole-pill omission. Never resize a real EVE window.
- Work only in `.worktrees/preview-character-markers`, branch `feature/preview-character-markers`, base `2404917a1eb7771649e9473103f3561bd618cd37`. Do not alter or re-review #214.
- Coordinator preflight is complete and the assigned worker is authorized to implement this single issue. Scoped local commits require explicit dispatch authorization; no push/PR/merge/issue action is authorized. Coordinator owns mandatory `/polish --fix` and an actual CodeRabbit review before a #215 PR.
- Screenshot fixtures remain local-only. Marker controls and callbacks must not submit real mutations or let fixture values contaminate retained live marker acknowledgements. Preserve the existing screenshot/live-state boundary without refactoring unrelated fixture machinery.

---

### Task 1: Deliver #215 end to end — persisted assignment, retained roster, label marker and Configure selector

**Files and ownership (planned changes, not made yet):**

| Files | Responsibility |
|---|---|
| Create `wingman/preview/labelmarkers.py` | Pure palette, exact owner boundary, forgiving persisted-map validation and derived choices; no native/UI imports. |
| Modify `wingman/settings.py` (`_preview_defaults`, `validated_preview`) | Fresh empty map and round-trip normalization, including unrelated writes; no defaults-version bump. |
| Modify `wingman/preview/store.py` (`LayoutStore._protected`) | Include marker owners in the existing protection union for both flush and clear. Do not change `roster.py`'s cap or layout format. |
| Modify `wingman/ui/api.py` (`get_preview_hotkey_state`, new setter beside label size) | One per-character field transaction and committed marker payload; no new controller framework or handler. |
| Modify `wingman/__main__.py` (`build_preview_host`) and `wingman/preview/host.py` (constructor, primary creation, `_restyle`) | Inject/read committed marker map, apply each owner's key on the pump. |
| Modify `wingman/preview/chrome.py`, `wingman/preview/window.py` | Marker-aware width measurement/render/cache; visibility, native count, font and height rules unchanged. |
| Modify `wingman/web/previews.js`, `wingman/web/style.css` | Configure-only selector and scoped status/width rules; retain existing five-column scan line. |
| Modify `wingman/web/dev.js` | Fake assignments, choices and real-shaped setter receipt; only this production file fabricates data. |
| Tests: create `tests/test_preview_labelmarkers.py`, `tests/test_preview_labelmarkers_page.py`, `tests/fixtures/preview_labelmarkers.cjs` | Pure validation/palette tests; real page listeners with deferred bridge replies. Reuse `screenshot_dom.cjs` and `PageTree`, not a second DOM framework. |
| Tests: extend `tests/test_settings.py`, `tests/test_settings_preview.py`, `tests/test_settings_committed_preview.py`, `tests/test_preview_store.py`, `tests/test_preview_wiring.py`, `tests/test_preview_host.py`, `tests/test_preview_chrome.py`, `tests/test_preview_window.py` | Defaults, transactions/retention, committed reads, rendering and cache/visibility regressions. |
| Tests: extend `tests/test_bridge_contract.py`, `tests/test_page_conventions.py`, `tests/test_dev_harness.py` | Endpoint/signature, detail-only control, derived/asserted palette choices and dev parity. Keep existing Node/tab/capture gates. |
| Docs: this plan's implementation notes; append a #215 section to `docs/smoke-checklist.md` during implementation | Actual evidence and explicitly outstanding native acceptance. Do not rewrite #214 docs/spec. |

**Interfaces and schema — coordinator-approved local choices:**

```python
# labelmarkers.py — RGB values are opaque when drawn; absence means no prefix.
MARKER_PALETTE = {
    "cyan": ("Cyan", (86, 180, 233)),
    "orange": ("Orange", (230, 159, 0)),
    "green": ("Green", (0, 158, 115)),
    "purple": ("Purple", (204, 121, 167)),
    "yellow": ("Yellow", (240, 228, 66)),
    "blue": ("Blue", (0, 114, 178)),
}
def valid_owner(name: object) -> bool:
    return (isinstance(name, str) and bool(name) and name == name.strip()
            and name.isprintable() and not name.startswith("hwnd:"))

def validated_markers(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {name: key for name, key in raw.items()
            if valid_owner(name) and isinstance(key, str) and key in MARKER_PALETTE}

def marker_choices() -> list[dict[str, str]]:
    return [{"key": "", "label": "None"}] + [
        {"key": key, "label": value[0]} for key, value in MARKER_PALETTE.items()]

# Global persisted example; an absent key defaults to a fresh {}.
# preview.label_markers = {"Alice": "cyan", "Weekend Alt": "orange"}

# Bridge: empty string resets; None/null is invalid input, not a reset alias.
# Api.set_preview_character_marker(self, name, marker) -> dict
# Receipt: {"applied": bool, "persisted": bool, "error": str | None,
#           "marker": str}  # committed value for this owner, "" when absent
# Existing get_preview_hotkey_state/onPreviewHotkeys adds:
# {"label_markers": dict[str, str], "marker_choices": list[dict[str, str]]}

# Existing constructors gain optional keyword-only parameters:
# PreviewHost.__init__: add label_markers=None, callable () -> dict[str, str].
# PreviewWindow.__init__ and .create: add label_marker=None after label_size.
# Existing parameters retain their order/defaults; label_marker is str | None.
# Host helper _current_label_markers() -> dict[str, str], like _current_label_size.
# Existing chrome signatures gain marker=None after max_h (keyword-only):
# label_layout(label, max_w, font_size=LABEL_FONT, secondary=None, *, max_h=None, marker=None)
# label_size(label, max_w, font_size=LABEL_FONT, secondary=None, *, max_h=None, marker=None)
# render_label(label, max_w, font_size=LABEL_FONT, secondary=None, *, max_h=None, marker=None)
# Keep label_layout's existing ((w, h), primary, secondary) | None result.
```

`valid_owner` uses the existing crop-owner contract: nonempty printable string, already stripped, not `hwnd:`. Discovery already strips the title suffix; do not casefold, trim onto another owner, substitute a character ID, or migrate other name tables. Keep this small marker boundary local rather than refactoring shared identity code. Unknown/non-string palette values and malformed owners are dropped individually on load, but refused explicitly by the setter. Persist only palette keys, never hex/native identities or empty/reset entries.

The assignment map is not capped by the recent-roster CAP=64: configured identities must remain editable. `rows()` adds its keys using the existing null-prototype dedup set. Add its keys to `LayoutStore._protected`; normalization still caps `seen`, so protection alone is insufficient. The setter accepts exact names from committed `seen`, direct binds, group assignments, crop definitions, existing markers, or currently authorized host characters. Do not broaden Copy's `_preview_known_characters()` semantics or treat old geometry-only sources as new marker targets. Reset removes only this map entry; it does not erase history/layout/binds. A marker-only identity already absent from `seen` can cease to have a row after reset, matching crop-only removal and existing focus fallback.

**Geometry decision:** an opaque 8×8 rounded square (radius 2), at x=`LABEL_PAD_X`=8, centered in the unchanged primary pill height (`y=(font_size+14-8)//2`). Reserve 5px after it: primary x=21, width budget `max_w - 16 - 13`. Secondary keeps x=8 and its existing independent width budget. Overall width is `16 + int(max(primary_text_width + 13, secondary_text_width))`; heights remain 31/34/37 or 47/53/59. A marker with empty primary or an ellipsis-only primary returns no pill; never draw a marker alone or shrink a font. The `marker=None` branch must preserve old measurement, ellipsis and pixel bytes exactly, including old ellipsis-only behavior. Shape evidence and measured contrast are in the notes.

**Test-first steps (one deliverable, not separate subsystem tasks):**

- [ ] **1. Pin the base before implementation.** Use the dedicated environment and verify the source still matches the recorded clean baseline; repeat baseline tests only if it changed. Capture base renderer dimensions and bytes before edits (the planning artifact has 2,430 cases). Make None-path regression evidence independent and portable: no Linux-only pixel-hash oracle in cross-platform tests, `/tmp`, `.git`, or sibling-worktree dependency, and no comparison that merely calls the future production renderer twice. A narrowly scoped test-local expected-image builder using bundled font drawing and explicitly pinned baseline geometry/colors is acceptable; do not duplicate the whole production renderer or add a second rendering framework. Read the shared spec and these notes.

- [ ] **2. Write failing model/default/retention tests.** Create the pure test file; extend existing settings/store tests. Include strict bad-value inputs (`None`, bool, list, hex, wrong-case key), normalized identity, independent defaults, reset omission, >64 marker owners across save/reload/unrelated write, and both `flush`/`clear` with other existing protected sources. Example assertions:

```python
from wingman.preview import labelmarkers
from wingman import settings

def test_marker_map_keeps_exact_owners_and_drops_bad_entries():
    assert labelmarkers.validated_markers({
        "Alice": "cyan", "alice": "blue", " Alice ": "green",
        "hwnd:0x1": "orange", "Bad": "#56B4E9", "Reset": "",
    }) == {"Alice": "cyan", "alice": "blue"}

def test_marker_assignments_are_not_recent_roster_history():
    owners = {"Pilot" + str(i): "cyan" for i in range(70)}
    p = settings.validated_preview({"label_markers": owners, "seen": list(owners)})
    assert p["label_markers"] == owners
    assert len(p["seen"]) == 64
```

- [ ] **3. Run RED, then add only the model/settings/store implementation.** Run `python -m pytest tests/test_preview_labelmarkers.py tests/test_settings_preview.py tests/test_preview_store.py -q` through the dedicated `uv run --no-sync`; confirm failures name the missing marker behavior. Implement the interfaces above, derive choices with `[{'key': '', 'label': 'None'}] + [{'key': key, 'label': value[0]} for key, value in MARKER_PALETTE.items()]`, reconstruct the map in `validated_preview`, and union its keys into `_protected`. Rerun those tests GREEN plus `tests/test_settings.py` for the exact-default fixture.

- [ ] **4. Write failing bridge/committed-read tests.** Use `make_api` and `FakeHost` in `test_preview_wiring.py`, and the blocked `_save_locked` Event pattern in `test_settings_committed_preview.py`. Cover live/offline/excluded/Preview-off/Show-labels-off; marker-only retained owner; unknown/whitespace/HWND refusals; per-key concurrent merges; successful no-op; reset; and failed persistence preserving RAM, disk, committed reads and zero restyles. Assert runtime effects begin only after commit, never startup/rebind/layout operations.

```python
# In tests/test_preview_wiring.py; imports/helpers already exist there.
def test_offline_marker_is_committed_before_restyle(tmp_path):
    from wingman import settings
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    with settings.update(api._state.settings) as doc:
        doc["preview"]["seen"] = ["Alice"]
    reader = settings.committed_preview(api._state.settings)
    expected, observed = ["cyan"], []
    def restyle():
        actual = reader.get("label_markers", {}).get("Alice", "")
        assert actual == expected[0]
        observed.append(actual)
    host.restyle = restyle
    assert api.set_preview_character_marker("Alice", "cyan") == {
        "applied": True, "persisted": True, "error": None, "marker": "cyan"}
    expected[0] = ""
    assert api.set_preview_character_marker("Alice", "")["marker"] == ""
    assert observed == ["cyan", ""]
```

Run the new tests RED before adding the endpoint/wiring.

- [ ] **5. Implement the narrow transaction and committed host read; run GREEN.** Validate outside the transaction, then re-check persisted known sources and mutate only `label_markers[name]` inside `settings.update`; sample authorized online names without native calls. Use the existing `_SettingUnchanged` rollback/no-write pattern for no-op. Refuse with `{applied:false,persisted:false,error,marker:committed_value}` on validation/save failure. Only successful commit/no-op may call `host.restyle()`; build receipts and the new payload fields from `self._preview_config`, not tentative raw settings. No whole-settings push. Inject `label_markers=lambda: preview_config.get('label_markers', {})`; read one map for a restyle and set each window's `label_marker` before `set_labels`. Pass the selected key on creation; character-select fallback titles never receive markers. Preserve existing epoch/native admission checks and callback failure logging/default-to-empty behavior.

- [ ] **6. Write failing renderer/cache tests.** Parameterize every palette key × 17/20/23 × inset 2/6 × one/two lines. Cover 320×210 and minimum 120×90, width 0/8/16/20/32/48 and legacy heights just below/at each primary and two-line boundary. Assert measured/rendered size equality, independent ellipsis, opaque marker pixels wholly inside the pill, unchanged text RGBA, no blank secondary allocation, and no primary → no marker. Pin measured ≥3:1 marker/background contrast over black and white composites; retain ≥4.5:1 text checks. Add a real missing/explicit-None/reset-to-None comparison to the captured base reference.

```python
@pytest.mark.parametrize("font_size", [17, 20, 23])
@pytest.mark.parametrize("inset", [2, 6])
def test_marker_does_not_grow_or_outlive_primary(font_size, inset):
    w, h = 120 - inset * 2, 90 - inset * 2
    image = chrome.render_label("W" * 60, w, font_size, "HOME", max_h=h, marker="cyan")
    assert image.width <= w and image.height == 2 * font_size + 13
    assert chrome.label_size("W" * 60, w, font_size, "HOME", max_h=h, marker="cyan") == image.size
    assert chrome.render_label("", w, font_size, "HOME", max_h=h, marker="cyan") is None
    assert chrome.render_label("Pilot", w, font_size, max_h=font_size + 13, marker="cyan") is None
```

In `test_preview_window.py` use `_overlay_window`: color-only changes invalidate just that label bitmap, never main chrome/alert frames; unchanged labels and layout-equivalent moves reuse their bitmap; reset restores base bytes. Cover both alert inset transitions, hidden owner, Show labels off/on, metadata changes/expiry, tiny-height omission/restoration and recreated windows after EVE off/on. Update narrow chrome-call doubles for the optional keyword, without weakening their assertions. Run targeted new cases RED.

- [ ] **7. Implement marker measurement/drawing/cache; run GREEN.** Define `LABEL_MARKER_SIZE=8`, `LABEL_MARKER_GAP=5`, `LABEL_MARKER_RADIUS=2` in `chrome.py`; derive the 13px primary prefix from size + gap only when a marker is present. Draw with `d.rounded_rectangle([LABEL_PAD_X, marker_y, LABEL_PAD_X + LABEL_MARKER_SIZE - 1, marker_y + LABEL_MARKER_SIZE - 1], radius=LABEL_MARKER_RADIUS, fill=(*rgb, 255))`, where `marker_y` uses the primary height formula above. Add marker key/resolved RGB and geometry constants to the existing label cache key. Do not put marker state in main chrome or alert-frame keys. Keep `max_h` omission order, overlay positioning/visibility and None-path draw operations unchanged. Rerun renderer/window/host/committed-read tests.

- [ ] **8. Write the failing real-page harness and contracts.** Load production `app.js` and `previews.js` via existing `PageTree`/`screenshot_dom.cjs` patterns with deferred `WM.send`. Supply choices derived in Python, and compare actual dev choices to that same table. Assert no extra collapsed-row cell; online/offline/marker-only rows; exactly one select inside Configure; accessible named options; zero setter calls before hydration; assignment/reset receipts; invalid/null/rejected promises; unrelated owner errors; and prototype-like names (`constructor`, `__proto__`) using own-property reads/null-prototype maps. Example event/bridge assertion after hydrating Alice and opening Configure:

```javascript
const select = document.querySelector('[data-preview-detail-control="marker"]');
select.value = 'cyan';
select.dispatchEvent({type: 'change', target: select});
assert.deepEqual(calls.filter(c => c[0] === 'set_preview_character_marker'),
                 [['set_preview_character_marker', 'Alice', 'cyan']]);
assert.equal(select.disabled, true);
```

Exercise a stale roster push before and after acknowledgement, a blocked second change for the same owner, another owner's allowed write, navigating to another Configure/tab/section while pending, capture → Configure, Copy modal Escape/focus return, and a crop push preserving the marker control's focus. Exercise `WM.previewCropScreenshot` entry/exit: fixture marker controls cannot send a real setter call, fixture state cannot overwrite live accepted marker baselines, and delayed real receipts remain associated with their live owner rather than fixture content. Run `tests/test_preview_labelmarkers_page.py` RED plus lexical contract tests for the new endpoint/control.

- [ ] **9. Implement the Configure field and fake; run GREEN.** Add `makeMarkerSelect(characterName)` inside a `.preview-detail-field` labelled “Identification marker”, with `aria-label="Identification marker for NAME"`, `data-preview-detail-control="marker"`, scoped inline error and `aria-describedby`. Populate text-only options from `marker_choices`; no HTML injection, color-coded text, inline hex styles or palette/theme rewrite. Keep it enabled while offline/excluded/labels-off; disable only its own pending write (and before initial hydration). No new dialog, row column, settings tab or global Settings save owner.

Use a null-prototype per-owner receipt state `{busy, accepted, error, version}`; bump the local version on submission/settlement. Initialize the accepted value from hydration; serialize that field by disabling it while busy. On success adopt only its returned `marker`; on refusal/null restore its last accepted value and report inline. A failed retry must not erase another owner's error. Preserve acknowledged per-owner values across later unrelated/stale roster payloads, including a reset tombstone `""`; this field has one production writer, the new setter. Do not replace whole hotkey/marker tables from a reply or trust `pushes` alone to order persistence. Merge these owned baselines after incoming roster snapshots, never inventing an assignment before acknowledgement. On existing section-entry `refresh()`, sample idle owners' versions before its getter; let its returned committed values rebase only owners still idle at that same version. This permits recovery after a lost receipt without allowing an older getter to overwrite a later submission; no additional read is introduced. Test this recovery and stale-getter case. Extend `rows()` for retained owners using the effective map. Reuse `rememberDetailFocus`, `detailInteraction`, `requestRender`, and existing tab/section cancellation; never focus a detached/hidden control or rearm capture. Keep defaults/missing fields backward-compatible in handlers and dev fixtures.

- [ ] **10. Verify the integrated deliverable and hand it to the coordinator.** Run the recorded baseline plus all new tests and modified dev/contract tests; run `ruff check .`, `ruff format --check .`, and `node scripts/js_smoke.js` in the dedicated environment. Inspect the final diff against this one-task scope. Append #215 acceptance items without changing #214 evidence: browser floors 840×625 / 839×621, populated/offline Configure and pending/refusal navigation; separate Windows/WebView2/live-EVE checks for useful marker recognition at typical/minimum sizes, all presets, bright content, both insets, labels/owner visibility, click-through, movement and restart. No app/EVE/user-profile actions without coordinator authorization. Full pytest requires Node and the documented release-codec setup; Cargo is a separate regression gate. Do not call the bounded run full-suite coverage. Update notes with exact commands/counts/skips and outstanding risks. Coordinator performs `/polish --fix`, inspects edits, reruns verification, obtains actual CodeRabbit review, and authorizes any commit/PR.
