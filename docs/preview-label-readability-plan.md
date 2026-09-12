# Preview Label Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver #214 as one end-to-end change: a global named label-size preference that improves primary-preview identification without changing character identity, placement, contrast, visibility or EVE source geometry.

**Architecture:** Add one small pure preset table and one normalized `preview.label_size` field. Reuse Settings' existing serialized per-field writer, the bridge's preview transaction helper, committed configuration callbacks, the host's existing restyle message and the existing measured/cached click-through overlay. Do not add a controller, native window, cache service, timer or dependency for this field.

**Tech Stack:** Python 3.11+, Pillow/bundled Inter, existing Win32/DWM preview host, pywebview 6.2.1, plain HTML/CSS/ES5, pytest and Node boundary harnesses.

**Spec:** `docs/preview-identification-design.md` — read this maintainer-approved document before executing the plan.

## Global Constraints

The following requirements are quoted from the Spec and apply to the whole task:

- “Add one global label-size preference with a small set of named presets. Preserve the current rendered size as the default; existing settings must retain the current appearance wherever the current label fits. The legacy-size containment exception below is explicitly approved.”
- Apply height containment to all presets, including Standard on undersized restored previews: omit the secondary line first, then hide the pill if the primary line cannot fit. Restore content when it fits. This compatibility exception was explicitly approved by the maintainer.
- “Keep the character name first and the optional Wanderer system name smaller and secondary.”
- “Retain top-left placement, existing high-contrast text and backgrounds, and Show labels behavior.”
- “Do not add custom names, text colors, font selection, free positioning, or per-character size overrides.”
- “Use the existing click-through label overlay and measurement/render cache. Add no additional native windows, polling, or dependencies.”
- “A size setting must not introduce label pixels outside the owning preview or change any real EVE window geometry.”
- “Settings transactions must preserve truthful applied/persisted outcomes, and the control must obey hydration and per-field ownership rules. Do not apply runtime effects after a refused persistence transaction.”
- “Preserve move/resize positioning, alert inset handling, runtime off/on, hiding and click-through behavior. Scope cache invalidation to affected labels.”
- “Label-size preferences and per-character identification assignments remain global. They are not switched by #213's saved layouts.”
- “Implement #214 first; review it before starting #215.”

#215's optional static per-character markers, #217, saved-layout implementation,
and every other backlog lane are **excluded**. No preparatory marker fields,
palettes, persistence or renderer abstractions. Read `AGENTS.md`, `PRODUCT.md`,
`DESIGN.md` and the relevant `docs/smoke-checklist.md` items. The header's worker
recommendation does not override coordinator authorization. The planning pass
made no production changes. The coordinator now authorizes the dispatched worker
to implement this single task without subagents. Commits require explicit
coordinator authorization; pushes, PRs, merges and issue edits remain prohibited.

---

## Discovery / blind-spot pass

### Current understanding

This is configuration under **Settings → Previews → Windows → Appearance**, not
a destination or a new appearance editor. It applies to existing primary EVE
preview labels and their optional Wanderer line. Crops and companions keep their
existing presentation. The single deliverable includes normalization, persistence,
committed runtime delivery, rendering/cache behavior and the Settings control.

### Confirmed constraints and evidence

| Constraint | Evidence at base `d0a24655b36438100076854e9b26243817ed1dd2` |
| --- | --- |
| Current primary is 17px; secondary is primary minus 3; pads are 8px horizontal / 5px vertical | `wingman/preview/chrome.py:170–245` |
| One-line height is `font_size + 14`; two-line height is `2 * font_size + 13` when both strings fit | `chrome.label_layout`; exercised in implementation notes |
| Ordinary minimum is 120×90; normal inset 2, alert inset 6 | `preview/window.py:28–29`, `preview/alertframes.py:38`, API size setters and `geometry.lock_to_aspect` |
| Saved layouts accept any positive dimensions; restoring does not enlarge them | `preview/layout.py:32–59`, `PreviewHost._resolve_rect:3757–3788` |
| Overlay is an owned `STATIC` layered/click-through/no-activate window; identity is `client.character or client.title` | `PreviewWindow._label_text`, `_ensure_label_overlay`, `_sync_label` |
| Cache compares text, clipped layout, font and palette; move still pushes at the new position | `window.py:603–641`; equal-size ellipsis regressions in `tests/test_preview_window.py:1321–1455` |
| Persistence normalizes and rolls back under one save lock; pump readers use detached committed state | `settings.validated_preview`, `settings.update`, `settings.committed_preview`; `tests/test_settings_committed_preview.py` |
| Generic `restyle()` posts one existing signal, reads callbacks on the pump and uses the current alert inset | `host.py:1771–1782`, `4067–4125`; `tests/test_preview_host.py` restyle cases |
| The main Settings IIFE owns `hydrated`, `FIELD_KEYS`, `current`, `pending`, `setField` and serialized `commit` | `web/settings.js:182–299,330–438`; `scripts/test_settings_runtime.js` |
| Static select choices checked against a Python table is established practice | `tests/test_page_conventions.py` alert sound/speed option tests |
| `get_settings()` already includes the nested preview document | `Api._settings_payload:1132–1187`; no new payload wrapper or push handler required |

### Likely blind spots

- Minimum **height** cannot be inferred from the normal drag minimum for every
  restored rectangle. Current rendering bounds width only. A 120×30 saved
  preview already overflows with the 17px default; this is a baseline defect,
  not evidence that the new presets fail at the supported 120×90 minimum.
- More pixels mean earlier horizontal ellipsis. At the alert minimum, a 23px
  primary fits only three W characters plus ellipsis; large names cannot all
  become fully visible merely by increasing type size.
- Neighboring Show labels/opacity endpoints restyle even after refusal; their
  standalone JS listeners also lack the main IIFE's complete ownership guard.
  Follow the better existing transaction/field machinery, not those details.
  Do not repair or migrate siblings in this task.
- Restyle's existing thumbnail/crop/visibility calls are not a new label cache
  invalidation. Preserve them; do not add a label-specific native message just
  to avoid existing idempotent work.
- Callback reads must come from `committed_preview`, not a mutable settings
  candidate. A blocked disk write must not alter a pump-rendered label.
- New `max_h` arguments will require extending explicit-signature renderer doubles
  in the existing tests. Preserve their equal-dimension/different-text assertions.
- The bridge sweep does not recognize Settings' `commit(..., ['method', ...])`
  wrapper (`tests/test_bridge_contract.py:724–754`). Add a focused contract test
  for this new call rather than claiming the existing broad sweep covers it or
  expanding the parser to unrelated Settings methods.
- Browser/Node evidence cannot establish native overlay/DWM, DPI or EVE safety.
  Native smoke remains an explicit, separately authorized gate.

Checklist assessment: assumptions/geometry, ownership, persistence/migration,
compatibility, concurrency/refusal, test limitations and UX edge cases all apply
and are addressed above/below. Security/privacy adds no credential or network
surface; only a small enum crosses the bridge. Deployment adds one module to an
existing explicitly packaged subpackage, not a new package or dependency.
Observability reuses existing save-error and callback-fallback logging. No new
telemetry is needed. Scope expansion is guarded by the exclusions above.

### Decisions that could materially change implementation

**Resolved before source work:** the maintainer explicitly approved correcting
legacy-size overflow with "yes, lets apply the correction" after the coordinator
explained its effect on Standard as well as the larger presets.

**Approved contract used by all code below:** bound every preset to the current
interior. Omit the secondary line if it cannot fit; omit the whole pill if even
its primary line cannot fit. Restore omitted content when space permits. Do not
partially crop glyphs, reduce the chosen font, or resize previews/source windows.
Standard is pixel-identical wherever its existing pill fits, including all
supported 120×90 cases; already-overflowing legacy rectangles deliberately change.
Do not retain a default-only overflow exception.

The coordinator approved the additive enum schema/API below and the measured
17/20/23px presets as conservative implementation choices. No migration, marker
reservation or additional endpoint is required. The legacy-height decision is
now incorporated into the approved Spec; no open product decision blocks this
task.

### Recommended next step

Coordinator has reviewed the enum/API and the maintainer resolved the narrow
legacy-height boundary. Execute the single task below. The task is not split into backend
and UI deliveries: neither is a reviewable #214 feature without the other.

## Preset choice and geometry evidence

Proposed authoritative table:

| Persisted key | UI name | Primary / secondary px | One / two line height |
| --- | --- | --- | --- |
| `standard` | Standard | **17 / 14** | **31 / 47** |
| `large` | Large | 20 / 17 | 34 / 53 |
| `extra_large` | Extra large | 23 / 20 | 37 / 59 |

These are Pillow/preview screen-pixel sizes, not Settings CSS pixels or new DPI
scaling factors. At 120×90 the normal interior is 116×86 and alert interior is
108×78. Every complete two-line preset fits vertically; the largest leaves 19px
inside the alert interior. At the ordinary 320×210 default there is substantially
more space. The read-only bundled-Inter probe and exact results are in
`docs/preview-label-readability-implementation-notes.md`.

Three modest steps are preferable to a free slider or a very large fourth size.
Only four distinct font sizes are needed (`14,17,20,23`), within the existing
`_font` LRU bound of eight. Preserve that bound. Do not flush it on a size change.
Preserve `LABEL_FONT` as the default-compatible renderer constant, deriving its
value from the table rather than keeping another hand-maintained 17.

## File map

Paths/ranges describe the base; use the named functions as anchors after edits.
Only these implementation surfaces are expected; additions require a scoped reason.

| File | Responsibility / expected change |
| --- | --- |
| Create `wingman/preview/labelsize.py` | Pure preset/default constants only; no Pillow, UI, native or settings imports |
| `wingman/settings.py:146–270,468–640` | Add default and strict enum normalization inside preview validation |
| `wingman/ui/api.py:5314–5368` | One small `set_preview_label_size` method using `_write_preview_setting`; guarded restyle only on accepted persistence |
| `wingman/__main__.py:396–558` | One committed `label_size` callback in `build_preview_host` |
| `wingman/preview/host.py` constructor, `_sweep`, live-read helpers, `_restyle` | Callback/default handling, creation keyword and pump-local assignment before label synchronization |
| `wingman/preview/chrome.py:170–245` | Derived `LABEL_FONT`; optional height bound shared by measurement, size and render |
| `wingman/preview/window.py` constructor/create, `_sync_label` | Named preset state; resolve font; pass height budget; retain existing overlay/cache/lifetime |
| `wingman/web/index.html:862–900` | Label size select/status next to Show labels in existing Appearance disclosure |
| `wingman/web/settings.js` main IIFE | New field registered in existing hydration/baseline/commit machinery, not a standalone IIFE |
| `wingman/web/dev.js:438,2058` | Stub endpoint and explicit fixture value; no fabricated data elsewhere |
| `tests/test_settings_preview.py` | Defaults, malformed values, normalization/save/load/update preservation |
| `tests/test_settings_committed_preview.py` | Extend existing blocked-save callback parametrization |
| `tests/test_preview_wiring.py` | New endpoint success/refusal/no-host and real build callback wiring |
| `tests/test_preview_host.py` | Default/throwing callback, creation, restyle and epoch/lifecycle compatibility |
| `tests/test_preview_chrome.py` | Font hierarchy, complete/default compatibility, containment and independent ellipsis |
| `tests/test_preview_window.py` | Size/cache/height transitions, visibility, inset and label-only invalidation |
| `scripts/test_settings_runtime.js` | New select DOM seam and delayed per-field acknowledgement cases |
| `scripts/test_settings_tabs_runtime.js` | Real markup/route owner test for pending label change across subpages |
| `tests/test_page_conventions.py` | Assert HTML preset keys/names/default against Python table and field placement |
| `tests/test_bridge_contract.py` | Focused signature/literal-commit assertion, since the generic call sweep does not see Settings' `commit` wrapper |
| `tests/test_settings_runtime.py`, `scripts/js_smoke.js` | Run existing gates; no new bridge handler or harness architecture |
| `docs/smoke-checklist.md` | Add #214-specific native/browser acceptance checks without rewriting old historical results |
| `docs/preview-label-readability-implementation-notes.md` | Record actual implementation choices, red/green evidence and acceptance classes |

No expected changes to `web/previews.js`, CSS, `preview/geometry.py`,
`preview/layout.py`, store/runtime ownership, Wanderer networking, companion/crop
renderers or packaging configuration. The new module lives in the existing
`wingman.preview` package; keep the package list unchanged.

### Task 1: Ship #214 from persisted preset to Settings and the existing overlay

**Files:** The complete file map above is this one task's scope.

**Interfaces — consumes existing contracts:**

- `settings.validated_preview(raw) -> dict`, `_preview_defaults() -> dict`,
  `settings.update(data, path=None)` context manager, and
  `settings.committed_preview(data).get(key, default=None)`.
- `Api._write_preview_setting(path: tuple, value) -> dict`, `_field_ok()`,
  `_field_refused(message)`, `PreviewHost.restyle() -> None`.
- `PreviewWindow._label_text() -> str`, `set_labels(shown: bool) -> None`,
  `_sync_label() -> None`, `_sync_label_visibility() -> None`.
- `chrome.label_layout(...) -> ((w,h), primary, secondary) | None`,
  `label_size(...) -> (w,h) | None`, `render_label(...) -> RGBA image | None`.
- Main Settings `commit(slot, args, key, value, revert, onApplied)`, `pending(key)`,
  `setField(id,value)`, and `wm:settings` hydration. No new `WM.HANDLERS` entry.

**Interfaces — produces:**

- `labelsize.DEFAULT_LABEL_SIZE: str == "standard"` and
  `labelsize.LABEL_SIZE_PRESETS: dict[str, tuple[str,int]]` as shown below.
- Persisted `preview.label_size: str`; absent/wrong-type/unknown values normalize
  to Standard. Existing `defaults_version` remains **2**. Layout and other
  preview keys retain their existing schemas and values.
- `Api.set_preview_label_size(value) -> dict` accepts only exact table keys.
  Invalid input: `{applied:false,persisted:false,error:"Choose a listed label size."}`.
  Failed save: existing `_write_preview_setting` refusal, no restyle. Success
  (including a valid no-op): `{applied:true,persisted:true,error:null}` and the
  existing restyle signal if a host exists. This acknowledges committed config,
  not synchronous native painting; Off remains Off and consumes the setting on
  the next authorized primary creation.
- `PreviewHost(..., label_size=None)` optional callable returning a preset key;
  `_current_label_size() -> str`, default/failure fallback Standard. Existing
  constructor call positions remain compatible.
- `PreviewWindow.__init__` and `.create` gain trailing keyword-only
  `label_size=DEFAULT_LABEL_SIZE`; retain `label_size` as pump-owned state (also
  a class-level default like `snap`, for existing lightweight test subclasses).
  Host writes `win.label_size` before `win.set_labels(show_labels)` in `_restyle`.
  No separate setter/service is necessary: `set_labels` already synchronizes it.
- All three chrome functions gain trailing keyword-only `max_h=None` after the
  existing `(label,max_w,font_size=LABEL_FONT,secondary=None)` arguments. `None`
  preserves the existing pure-render call contract. `_sync_label` supplies
  `max(0, rect.h - 2 * inset)`; primary/full-secondary fitting is as specified.
- DOM ids `preview-label-size` and `preview-label-size-status`; field-owner key
  `preview_label_size` is page-local, **not** another persisted setting.

- [ ] **1. Confirm the execution boundary.** Re-read the Spec, this plan and notes;
  verify the requested linked worktree/branch/base and preserve the supplied
  Spec. The legacy-height exception is approved above and recorded in the notes;
  apply it consistently to every preset. No changes to enum keys after persistence without review. The current
  planning baseline is 400 passed/no skips and JS smoke PASS; it is not #214
  verification.

- [ ] **2. Write failing schema tests before the preset/setting implementation.**
  Add these representative cases to `tests/test_settings_preview.py`, then extend
  its existing round-trip tests to retain layouts, hotkeys, crops, alerts,
  Show labels, width/height and opacity through a label-size/unrelated write.

  ```python
  @pytest.mark.parametrize("key", ["standard", "large", "extra_large"])
  def test_label_size_round_trips(key, tmp_path):
      path = tmp_path / "settings.json"
      live = settings.load(path)
      with settings.update(live, path) as doc:
          doc["preview"]["label_size"] = key
      assert settings.load(path)["preview"]["label_size"] == key
      with settings.update(live, path) as doc:
          doc["channel_title"] = "Unrelated change"
      assert settings.load(path)["preview"]["label_size"] == key

  @pytest.mark.parametrize("raw", [None, True, 17, 20.0, [], {}, "", "Large", "huge"])
  def test_bad_label_size_falls_back_without_resetting_other_fields(raw):
      result = settings.validated_preview({"label_size": raw, "show_labels": False})
      assert result["label_size"] == "standard"
      assert result["show_labels"] is False

  def test_missing_label_size_keeps_the_existing_default():
      assert settings.validated_preview({})["label_size"] == "standard"
      assert settings._preview_defaults()["defaults_version"] == 2
  ```

- [ ] **3. Run the schema RED gate.** From the worktree run:
  `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_settings_preview.py -q -k label_size`.
  Expected: missing/dropped `label_size` failures, not dependency/import failures.
  Record the actual failures before implementation.

- [ ] **4. Add the shared table and minimal normalization, then run schema GREEN.**
  Create the only new production module, `preview/labelsize.py`:

  ```python
  """Global primary-preview label sizes, shared by settings and rendering."""

  DEFAULT_LABEL_SIZE = "standard"
  LABEL_SIZE_PRESETS = {
      "standard": ("Standard", 17),
      "large": ("Large", 20),
      "extra_large": ("Extra large", 23),
  }
  ```

  Import the constants into `settings.py`; add
  `"label_size": DEFAULT_LABEL_SIZE` beside `show_labels`. Inside
  `validated_preview`, after the raw-dict check:

  ```python
  label_size = raw.get("label_size")
  if isinstance(label_size, str) and label_size in LABEL_SIZE_PRESETS:
      section["label_size"] = label_size
  ```

  Run all of `tests/test_settings_preview.py`, not only the new cases. Do not
  change `_PREVIEW_DEFAULTS_VERSION`, saved layouts or any defaults for other
  fields.

- [ ] **5. Write renderer RED cases, retaining the existing default/contrast tests.**
  In `tests/test_preview_chrome.py`, use both insets and every table entry;
  verify text drawing records the primary font and smaller secondary, separate
  ellipsis, `label_size == render_label.size`, blank secondary byte equality,
  empty primary/no window and too-narrow width/no overflow. Core height cases:

  ```python
  import pytest
  from wingman.preview.labelsize import LABEL_SIZE_PRESETS

  @pytest.mark.parametrize("font_size", [preset[1] for preset in LABEL_SIZE_PRESETS.values()])
  @pytest.mark.parametrize("inset", [2, 6])
  def test_label_presets_fit_the_supported_minimum(font_size, inset):
      from wingman.preview.window import MIN_SIZE
      max_w, max_h = (dimension - 2 * inset for dimension in MIN_SIZE)
      image = chrome.render_label("W" * 60, max_w, font_size,
                                  "HOME", max_h=max_h)
      assert image is not None
      assert image.width <= max_w and image.height <= max_h
      assert image.height == 2 * font_size + 13

  def test_height_budget_keeps_primary_before_secondary():
      assert chrome.label_layout("Pilot", 116, 20, "HOME", max_h=53)[2] == "HOME"
      one = chrome.label_layout("Pilot", 116, 20, "HOME", max_h=52)
      assert one == chrome.label_layout("Pilot", 116, 20, max_h=52)
      assert one[0][1] == 34
      assert chrome.render_label("Pilot", 116, 20, "HOME", max_h=33) is None
      assert chrome.render_label("Pilot", 116, 20, max_h=0) is None

  @pytest.mark.parametrize("secondary", [None, "HOME", "W" * 60])
  def test_default_height_budget_does_not_change_fitting_pixels(secondary):
      legacy = chrome.render_label("Pilot", 108, secondary=secondary)
      bounded = chrome.render_label("Pilot", 108, secondary=secondary, max_h=78)
      assert bounded.size == legacy.size
      assert bounded.tobytes() == legacy.tobytes()
  ```

  Also pin default table value to existing `chrome.LABEL_FONT == 17`, verify all
  requested sizes resolve to real bundled Inter, and record pre-change default
  images for same-environment byte comparison. Do not hard-code the Linux pixel
  hashes in cross-platform tests; FreeType rasterization may differ on Windows.
  Run `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py -q`;
  expected RED is the missing `max_h` contract, not a changed palette.

- [ ] **6. Implement shared height fitting and run renderer GREEN.** In `chrome.py`
  derive `LABEL_FONT = LABEL_SIZE_PRESETS[DEFAULT_LABEL_SIZE][1]`. Preserve the
  existing width ellipsis and return tuple. Immediately after computing the
  current primary `height`, return `None` when it exceeds a non-None `max_h`.
  Before secondary measurement, admit it only if its complete height fits:

  ```python
  height = font_size + LABEL_PAD_Y * 2 + 4
  if max_h is not None and height > max_h:
      return None
  second = ""
  small_size = max(1, font_size - 3)
  if secondary and (max_h is None or height + small_size + 2 <= max_h):
      small_font = _font(small_size)
      second = _ellipsize(probe, secondary, small_font, max_w - LABEL_PAD_X * 2)
      if second:
          width = max(width, probe.textlength(second, font=small_font))
          height += small_size + 2
  ```

  Both `label_size` and `render_label` call
  `label_layout(label,max_w,font_size,secondary,max_h=max_h)`. Preserve all
  draw coordinates, colors, radius, padding, `_font(maxsize=8)`, and the existing
  `None` result behavior. Run `tests/test_preview_chrome.py` GREEN. No auto-shrink,
  bitmap cropping or preview geometry changes.

- [ ] **7. Add failing transaction and committed-delivery tests.** Use real
  `settings.update`, not the `_no_disk` helper for rollback/normalization. In
  `tests/test_preview_wiring.py` (already imports `make_api`, `FakeHost`, `copy`):

  ```python
  def test_label_size_refusal_does_not_restyle(tmp_path, monkeypatch):
      host = FakeHost()
      api = make_api(tmp_path, preview_host=host)
      before = copy.deepcopy(api._state.settings)
      def fail(*args, **kwargs):
          raise OSError("read-only settings")
      monkeypatch.setattr("wingman.settings._save_locked", fail)
      result = api.set_preview_label_size("large")
      assert result["applied"] is False and result["persisted"] is False
      assert result["error"]
      assert api._state.settings == before
      assert host.restyles == 0
  ```

  Add valid-key round trips through `Api`/`settings.load`, invalid types/keys
  with no save attempt, no host, previews Off (no start), and valid no-op (no
  disk write, accepted restyle). Assert `get_settings()["settings"]["preview"]`
  includes the accepted field without emitting a whole-settings push. Extend
  `test_settings_committed_preview.py`'s callback cases with:

  ```python
  ("label_size", {"label_size": "large"}, "standard", "large"),
  ```

  Its existing blocked-save test proves non-blocking old value while pending,
  new value only after commit, and old value after rollback. Run
  `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_settings_committed_preview.py -q -k label_size`;
  expected RED: missing endpoint/callback. Preserve surrounding lifecycle tests.

- [ ] **8. Implement the endpoint and committed host callback.** `api.py` imports
  the small table/default as needed, not `chrome` for validation. Add:

  ```python
  def set_preview_label_size(self, value) -> dict:
      if not isinstance(value, str) or value not in LABEL_SIZE_PRESETS:
          return self._field_refused("Choose a listed label size.")
      result = self._write_preview_setting(("label_size",), value)
      if result["applied"] and result["persisted"] and self._preview_host is not None:
          self._preview_host.restyle()
      return result
  ```

  In `build_preview_host`, define/pass this callback using the already-retained
  `preview_config`, never `state.settings`:

  ```python
  def label_size():
      return preview_config.get("label_size", DEFAULT_LABEL_SIZE)
  ```

  Extend `PreviewHost`'s constructor with an optional trailing `label_size=None`
  callback and store it as `_label_size`. Add `_current_label_size()` following
  `_labels_shown`: missing callback → Standard; callable exception → existing
  logger.exception pattern and Standard; non-string/unknown result → Standard;
  otherwise return its key. No lock/disk access on the pump. Run the two step 7
  files GREEN; do not alter generic writer or sibling endpoints.

- [ ] **9. Add host/window RED tests for creation, live application and cache scope.**
  Extend `_config_sweep_host` creation assertions in `test_preview_host.py` to
  capture `kw["label_size"]`; add callback default/invalid/raising cases and live
  restyle from Standard to each size using `_RestyleWindow`. Assert assignment
  happens before `set_labels` sees the value. Keep existing epoch/off-on and
  alert-inset tests; off/on/newly discovered windows read the latest key.

  In `test_preview_window.py`, use `_overlay_window`, real Pillow and recorded
  `layered.push`. A core cache test can use the existing `set_labels` method:

  ```python
  def test_label_size_changes_only_the_label_cache(monkeypatch):
      rendered = []
      render = window.chrome.render_label
      def record(*args, **kwargs):
          image = render(*args, **kwargs)
          rendered.append(image)
          return image
      monkeypatch.setattr(window.chrome, "render_label", record)
      monkeypatch.setattr(window.layered, "push", lambda *args: None)
      w, libs = _overlay_window()
      w._thumb = _FakeThumb()
      w._ensure_label_overlay()
      first = w._label_img
      frames = object()
      w._frames = frames
      chrome_key = w._chrome_cache_key
      w.label_size = "large"
      w.set_labels(True)
      assert w._label_img.height == 34 and w._label_img is not first
      assert len(rendered) == 2 and len(libs.created) == 1
      w.set_labels(True)
      assert len(rendered) == 2
      assert w._frames is frames and w._chrome_cache_key == chrome_key
      assert w._thumb.calls == []
  ```

  Add size changes with Show labels Off (no overlay creation), owner hidden (no
  `SW_SHOWNOACTIVATE`), independent system-name changes, pure move/width changes
  with identical effective layout (no new bitmap), equal-sized changed ellipsis
  (new bitmap), and height transitions across full/two-line → primary-only →
  absent → restored. Test at `(120,90)`, `(320,210)`, and synthetic restored
  `(120,30)` with both insets. Every pushed image must fit inside the owner and
  ride `(rect.x+inset,rect.y+inset)`; when no image fits, an old visible pill must
  hide. Keep original overlay style/close tests and assert no new source HWND
  geometry call. Run both files RED and record actual failing assertions.

- [ ] **10. Thread the key into the existing overlay and run runtime GREEN.** Add
  default-compatible `label_size` to `PreviewWindow` class/constructor/create,
  forwarding by keyword so old positional callers retain their meaning. Pass
  `label_size=self._current_label_size()` in primary creation. In `_restyle`
  read the callback once alongside opacity/show_labels, then assign
  `win.label_size = label_size` immediately before `win.set_labels(show_labels)`.
  Leave the restyle lifecycle and its existing work alone.

  In `_sync_label`, resolve and pass the effective font/budget:

  ```python
  font_size = LABEL_SIZE_PRESETS[self.label_size][1]
  max_w = self.rect.w - self._inset * 2
  max_h = max(0, self.rect.h - self._inset * 2)
  layout = chrome.label_layout(label, max_w, font_size,
                               self._system_name, max_h=max_h)
  ```

  Keep the existing cache tuple but replace its constant font member with
  `font_size`. Keep both original strings, effective layout and palette/padding
  members. Do **not** add raw width/height: changes that leave the effective
  bitmap unchanged must reuse it. On cache miss call
  `chrome.render_label(label,max_w,font_size,self._system_name,max_h=max_h)`.
  Preserve `None`/visibility handling and position pushes. No cache clearing of
  fonts, alert frames or chrome, no new native object on preset change. Update
  explicit-signature test doubles to accept/forward `max_h` without weakening
  their assertions. Run step 9 files plus chrome, wiring, committed-preview,
  preview metadata and runtime tests GREEN.

- [ ] **11. Write the Settings UI RED gates before adding the control.** In
  `test_page_conventions.py`, use its existing `HTML`/`re` pattern to check the
  complete choice set, names and default against the shared table:

  ```python
  def test_label_size_choices_match_the_shared_presets():
      from wingman.preview.labelsize import DEFAULT_LABEL_SIZE, LABEL_SIZE_PRESETS
      select = re.search(r'<select\b[^>]*id="preview-label-size"[^>]*>(.*?)</select>',
                         HTML, re.DOTALL)
      assert select is not None
      options = re.findall(r'<option value="([^"]+)"([^>]*)>([^<]+)</option>',
                           select.group(1))
      assert [(key, text) for key, attrs, text in options] == [
          (key, value[0]) for key, value in LABEL_SIZE_PRESETS.items()
      ]
      assert [key for key, attrs, text in options if "selected" in attrs] == [DEFAULT_LABEL_SIZE]
      assert options[0][0] == DEFAULT_LABEL_SIZE
  ```

  Assert the select is under `preview-group-appearance`, associated with a `.lab`,
  and has its own described status slot. Add this scoped test to
  `tests/test_bridge_contract.py`; its existing `WEB` constant locates the source:

  ```python
  def test_label_size_commit_matches_the_bridge_signature():
      from inspect import signature
      from wingman.ui.api import Api
      source = (WEB / "settings.js").read_text(encoding="utf-8")
      assert re.search(
          r"commit\('preview-label-size-status',\s*\['set_preview_label_size',\s*field\.value\]",
          source,
      )
      assert tuple(signature(Api.set_preview_label_size).parameters) == ("self", "value")
  ```

  Add an assertion against `dev.js`'s preview fixture that its `label_size` equals
  `DEFAULT_LABEL_SIZE`, alongside the checked HTML choices. Add
  the two ids to `scripts/test_settings_runtime.js`'s focused DOM seam and expose
  the select's default option (derive its value from the actual markup tree
  supplied on stdin, rather than inventing a production options API). Preserve
  existing fake element behavior. Add delayed-ack tests using `page`, `submit`,
  `reply`, `accepted` and `refused`:

  ```javascript
  test('label size serializes and rolls back to the acknowledged key', async () => {
    const p = page();
    await p.submit('preview-label-size', 'large');
    await p.submit('preview-label-size', 'extra_large');
    assert.equal(p.calls.filter(c => c.method === 'set_preview_label_size').length, 1);
    await p.reply('set_preview_label_size', accepted, ['large']);
    assert.equal(p.el('preview-label-size').value, 'extra_large');
    await p.reply('set_preview_label_size', refused, ['extra_large']);
    assert.equal(p.el('preview-label-size').value, 'large');
    assert.ok(p.el('preview-label-size-status').textContent);
  });
  ```

  Cover change before initial hydration (zero writes), initial non-default and
  missing-key hydration, focused refusal, null bridge response, stale hydration
  while pending, retry clearing only this field's error, unrelated field errors,
  and preferences remaining editable with Preview/Show labels Off. In
  `test_settings_tabs_runtime.js`, use real `page({settings:true})`, select Large,
  dispatch `input` then `change`, switch to Characters and deliver the reply;
  assert no extra `get_settings`, no focus theft and the accepted value survives
  return to Windows. Run `tests/test_settings_runtime.py` and the new page
  convention case RED. Missing element/handler must be made explicit assertions,
  not mistaken for meaningful lifecycle coverage.

- [ ] **12. Add the select and wire the existing field owner; run UI GREEN.** In
  Appearance, immediately after Show labels/status, insert:

  ```html
  <div class="row">
    <label class="lab" for="preview-label-size">Label size</label>
    <select class="field" id="preview-label-size" aria-describedby="preview-label-size-status">
      <option value="standard" selected>Standard</option>
      <option value="large">Large</option>
      <option value="extra_large">Extra large</option>
    </select>
  </div>
  <p class="field-msg" id="preview-label-size-status" hidden></p>
  ```

  In the **main** Settings IIFE add
  `'preview-label-size': 'preview_label_size'` to `FIELD_KEYS`. Add to `render`'s
  values the nested preference, defaulting from the first (checked Standard)
  HTML option rather than another JS key table:

  ```javascript
  preview_label_size: (s.preview || {}).label_size
                      || WM.el('preview-label-size').options[0].value
  ```

  Use the existing pending-aware `current` update. On the first payload assign
  this select's value directly from `current.preview_label_size`, even if it
  received focus/interaction before hydration; no prior edit could have committed.
  On later hydration call `setField('preview-label-size', current.preview_label_size)`.
  The existing `hydrated = true` stays last. Register:

  ```javascript
  WM.el('preview-label-size').addEventListener('change', function () {
    var field = WM.el('preview-label-size');
    commit('preview-label-size-status', ['set_preview_label_size', field.value],
           'preview_label_size', field.value,
           function () { field.value = current.preview_label_size; });
  });
  ```

  No blur handler, Save button, separate settings read, Settings push or
  Preview/Show-labels disabling predicate. Existing `#preview-depends` owns the
  Off explanation; do not repeat it. Add the endpoint to `dev.js`'s existing
  `{applied,persisted,error}` stub list and `label_size: 'standard'` to its preview
  settings fixture; the convention test/checks keep the fixture default aligned.
  Run Settings runtime, page conventions, bridge contract and JS smoke GREEN.

- [ ] **13. Complete focused regression and normal engineering gates.** Keep
  `UV_PROJECT_ENVIRONMENT` on every uv invocation. Run from the linked worktree:

  ```bash
  UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_preview_metadata.py tests/test_preview_runtime.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_settings_runtime.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_settings_page.py tests/test_dev_harness.py -q -rs --basetemp=/tmp/wingman-preview-label-readability-focused
  UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync ruff check .
  UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync ruff format --check .
  node scripts/js_smoke.js
  git diff --check
  ```

  Expected: all applicable focused tests pass; inspect/report actual skips
  (a real Windows pump test may skip on Linux). Missing Node is not acceptable.
  Stop on unrelated baseline failures instead of repairing them. If claiming
  broader/full-suite coverage, first execute the release-codec build/install
  recipe in `docs/overview-layout-sharing-verification.md` with this environment,
  then run `UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/ -q -rs` and the independent
  `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml`.
  Record exact commands/counts/skip reasons; never call focused results a full suite.

- [ ] **14. Document and execute separately authorized acceptance gates.** Add
  #214 checks to `docs/smoke-checklist.md` without changing historical statuses:
  browser-render the actual Settings page at 840×625 and 839×621; verify the
  select/status remains reachable, no horizontal overflow, keyboard focus,
  hydration/refusal and tab-return behavior. Record browser evidence separately.
  For Windows/WebView2/native acceptance, use the matrix below, including
  installed bundled Inter and 100/125/150/200% plus mixed-monitor scaling. Do not
  launch/change the user's live app/settings or EVE without coordinator/operator
  authorization. When unavailable, mark these gates **NOT RUN**, not passed.

- [ ] **15. Polish, rerun verification, and hand off this one deliverable.** Run
  `polish-core --fix` against the specified base, inspect every resulting edit and
  keep fixes scoped to #214. Rerun step 13 after all edits. Inspect the final diff
  for unintended schema/default changes, source HWND geometry calls, extra
  cache invalidation, marker features, debug output and untested paths. Update
  implementation notes with the approved legacy-height decision and actual
  results; use `change-explainer` for the coordinator-facing completion summary.
  Coordinator owns independent review/integration. Do not commit, push, open a
  PR, amend a commit or change issues without explicit authorization.

## Acceptance gates for the single task

| Gate | Required evidence / pass condition |
| --- | --- |
| Scope/schema | Only `preview.label_size` and its bounded presentation are added; exact enum/default agreed; no version bump, migration or per-character/layout appearance data |
| Compatibility | Absent/malformed key uses 17px; fitting Standard one-/two-line bytes unchanged on the same environment; baseline sub-minimum overflow and the coordinator-approved exception explicitly recorded |
| Persistence | API valid/invalid/no-op/no-host tests; real rollback preserves RAM/disk/committed callback; refusal never posts restyle; blocked save cannot affect labels |
| Minimum geometry | All presets at 120×90 and 320×210 with inset 2/6; long/short/empty primary and secondary; independent ellipsis, secondary strictly smaller; no image/pixels outside owner |
| Legacy tiny geometry | Synthetic restored positive rectangles below minimum; measured primary-first/absent behavior exactly matches approved decision; old visible image hides when no new pill fits; geometry never changed |
| Cache and native lifetime | Same key/move/layout-equivalent width/height changes reuse bitmap; changed font/text/clipped layout invalidates only affected label; no global clear, new native window per setting change, or extra cache owner |
| Existing runtime behavior | Creation, Show labels Off/on, hidden owner, metadata updates/expiry, move/resize, alert inset/pulses, selection/opacity, EVE runtime off/on and shutdown preserve existing contracts |
| UI runtime/contracts | Hydration gate, serialized writes, latest-ack rollback, newer drafts, independent error slots, tab-return behavior; checked preset options; bridge/page/JS smoke gates green |
| Browser-render | Actual markup at both known CSS floors, keyboard and status layout checked; recorded as browser evidence only |
| Windows automated | Relevant tests on Windows recorded independently from Linux/Node; no inference from Linux pure-render success |
| Windows/WebView2/native smoke | One-/two-line overlay at min/default sizes for every preset; long independent lines, bright/dark game content, installed Inter; scaling/mixed monitors; click through label activates the same source, no focus theft or detached labels |
| Source safety | Size changes do not call source `SetWindowPos`, `MoveWindow`, resize/maximize or change source styles/input; authorized native observations confirm EVE window bounds unchanged. Existing activation exceptions remain untouched |
| Final review | Focused gates and normal Ruff gates rerun after polish; remaining manual gates stated; coordinator independent review before integration/issue closure |

## Plan self-review (performed during preparation)

- **Spec coverage:** #214's global presets/default, character/Wanderer hierarchy,
  placement/contrast/Show labels, overlay reuse, minimum geometry, transaction
  outcomes, UI ownership and bounded caches map to Task 1 steps 2–12 and the
  acceptance table. Runtime/lifecycle, no-source-geometry and verification
  distinctions map to steps 9–15. #215 is deliberately not implemented. The
  surfaced legacy-height/default boundary was subsequently approved by the
  maintainer and incorporated into this plan and the Spec.
- **Placeholder scan:** no unfinished implementation placeholders; code steps
  include concrete interfaces/logic/tests and exact commands. Future acceptance
  remains unchecked because preparation did not execute it.
- **Type/interface consistency:** `label_size` is a persisted string and host/window
  key; `preview_label_size` is JS owner state only; `font_size` is the resolved
  integer. `max_h` is keyword-only and shared by all three renderer functions.
  Named defaults/options share one checked table. Existing bridge payload/handler
  contracts and constructor positional arguments remain intact. A focused test
  covers the new literal Settings commit, outside the generic call sweep's reach.
- **Scope/size:** exactly one end-to-end task; no independent scaffolding task,
  no new controller, generic style model, resource manager or marker support.

**Handoff status:** coordinator preflight complete; Task 1 is authorized for the
assigned implementation worker. Baseline evidence lives in the implementation
notes. The legacy-height behavior is approved. #215 remains queued for a separate
plan after #214 review.
