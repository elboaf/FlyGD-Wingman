# Preview Cycle Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users create exclusive named character groups and bind one forward-only global cycle key to each while preserving the existing All forward/back cycle.

**Architecture:** Extend `preview.hotkeys` with ordered stable-ID groups and a character-to-group map. Validate persistence in `settings.py`, install one coherent active table beside Windows registrations in `PreviewHost`, serialize narrow API mutations, and render group controls inside the existing five-track Previews grid.

**Tech Stack:** Python 3.11, Win32 `RegisterHotKey`, pywebview 6.2.1, plain ES5 JavaScript, HTML/CSS, pytest, Ruff.

**Spec:** `docs/preview-cycle-groups-design.md`

## Global Constraints

- Existing `preview.hotkeys.cycle_next` and `cycle_prev` remain the migration-free All cycle.
- Every non-excluded running character is in All and may belong to at most one named group.
- Named groups have one forward-only global keybind; no named-group back key is added.
- Group assignment stays inside the existing Character cell; `#preview-binds` remains five tracks at the 840x625 floor.
- Character focus bindings retain duplicate-sharing behavior and outrank every cycle binding.
- Cycle ordering remains the existing case-sensitive `cycle.ordered()` order.
- Preview HWND and hotkey registration work stays on the preview thread.
- Every non-method `Api` attribute remains underscore-prefixed.
- Settings fields commit per operation; text never commits on blur.
- Never use `window.confirm`, `window.prompt`, or `window.alert`; use Wingman's page-owned dialogs.
- No code may move or resize a real EVE client window.
- No new dependency, framework, build step, or bundler.
- Every production behavior change is test-first, and the final UI requires generated screenshots plus a Windows/EVE smoke pass.

---

## Intended outcome

Settings > Previews shows **All forward**, **All back**, and one forward-cycle
keybind row per user-created group. A Manage groups disclosure creates,
renames, and deletes groups. When groups exist, each known character's existing
Character cell contains a select whose value is **All only** or one named group.

At runtime, each group cycle uses only currently running, non-excluded assigned
members. Foreground members anchor the step, foreground nonmembers start at the
first member, and cycling outside EVE resumes that group's process-local
history. Rapid mixed All, group, and direct-focus hotkeys preserve sequential
meaning but activate only the final client.

## Evidence and constraints

- `wingman/settings.py:_preview_defaults` explicitly reserves current flat
  cycle fields as the future default/All group.
- `wingman/preview/cycle.py:step` already handles changing sets by identity and
  should remain unchanged.
- `wingman/preview/host.py:plan_registrations` gives character-focus chords
  precedence and `_on_hotkeys` folds queued relative actions.
- `wingman/ui/api.py:set_preview_binds` currently replaces the complete hotkey
  object; it must preserve new group fields.
- `wingman/web/previews.js:requestRender` already defers table replacement while
  capture is armed.
- `wingman/web/style.css:#preview-binds` deliberately has five tracks and a
  bounded `minmax(150px, 260px)` Character track.
- `tests/test_page_conventions.py` derives the row/track count lexically; a
  group select must be appended inside `.lab`, not to the row.
- `PRODUCT.md` and `DESIGN.md` require a real rendered and Windows pass because
  pytest never executes this page or creates the production preview HWNDs.

## Decisions and tradeoffs

1. **Stable IDs plus a membership map:** rename-safe and structurally exclusive.
   Rejected group-name identity and per-group member arrays because rename would
   rewrite identity and arrays could disagree about exclusivity.
2. **Operation-specific group endpoints:** mutate the latest live document and
   avoid stale whole-table replacement. Rejected sending all groups back from
   JavaScript.
3. **One API writer lock:** preserve durable-write/host-apply order across
   pywebview threads. `settings._SAVE_LOCK` alone ends before host delivery.
4. **Applied hotkey snapshot in the host:** group membership must match the
   registrations currently installed, not a newer desired table waiting in the
   message queue.
5. **Select inside Character cell:** direct assignment without reopening group
   management and no sixth grid track. The accepted cost is taller character
   rows only after a group exists.
6. **`WM.prompt` for rename:** reuse the existing accessible dialog rather than
   inventing inline edit/focus behavior.

---

### Task 1: Validate and round-trip the cycle-group schema

**Files:**
- Modify: `wingman/settings.py:116-175, 420-445`
- Test: `tests/test_settings_preview.py`

**Interfaces:**
- Produces persisted `preview.hotkeys.groups: list[dict]` with `{id, name, cycle}`.
- Produces persisted `preview.hotkeys.group_by_character: dict[str, str]`.
- Preserves `characters`, `cycle_next`, and `cycle_prev` exactly as today's validator does.
- Later tasks consume this normalized table without revalidating its shape.

- [ ] **Step 1: Add failing default and compatibility tests**

Add tests proving fresh defaults contain empty group fields, old files keep All
bindings, defaults are still a fixed point, and separate defaults do not share
nested group state:

```python
def test_preview_cycle_groups_default_empty_and_are_not_shared():
    first = settings._preview_defaults()
    second = settings._preview_defaults()
    assert first["hotkeys"]["groups"] == []
    assert first["hotkeys"]["group_by_character"] == {}
    first["hotkeys"]["groups"].append({"id": "dps", "name": "DPS", "cycle": ""})
    assert second["hotkeys"]["groups"] == []


def test_legacy_preview_cycle_binds_survive_without_group_migration():
    result = settings.validated_preview({
        "hotkeys": {
            "characters": {"Alice": "Ctrl+F1"},
            "cycle_next": "Ctrl+Alt+Right",
            "cycle_prev": "Ctrl+Alt+Left",
        }
    })["hotkeys"]
    assert result["cycle_next"] == "Ctrl+Alt+Right"
    assert result["cycle_prev"] == "Ctrl+Alt+Left"
    assert result["groups"] == []
    assert result["group_by_character"] == {}
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings_preview.py -k "cycle_group or fixed_point" -v
```

Expected: failures because `groups` and `group_by_character` are absent.

- [ ] **Step 3: Add failing normalization tests**

Cover canonical gesture display, creation order, first-valid-wins duplicate
policy, malformed-entry isolation, case-insensitive duplicate names, unstable
character names, and dangling membership:

```python
def test_preview_cycle_groups_normalize_independently_and_membership_is_exclusive():
    hotkeys = settings.validated_preview({"hotkeys": {
        "groups": [
            {"id": "dps", "name": " DPS ", "cycle": "Alt+Ctrl+F2"},
            {"id": "bad", "name": "", "cycle": "Ctrl+F3"},
            {"id": "dup-name", "name": "dps", "cycle": "Ctrl+F4"},
            {"id": "logi", "name": "Logistics", "cycle": "nonsense"},
        ],
        "group_by_character": {
            "Alice": "dps", "Bob": "logi", "Carol": "missing",
            "hwnd:123": "dps",
        },
    }})["hotkeys"]
    assert hotkeys["groups"] == [
        {"id": "dps", "name": "DPS", "cycle": "Ctrl+Alt+F2"},
        {"id": "logi", "name": "Logistics", "cycle": ""},
    ]
    assert hotkeys["group_by_character"] == {"Alice": "dps", "Bob": "logi"}
```

Also pin duplicate IDs to first valid entry and reject non-list/non-dict inputs
without rebuilding unrelated preview settings.

- [ ] **Step 4: Implement group defaults and validation**

Extend the fresh hotkey default:

```python
"hotkeys": {
    "characters": {},
    "cycle_next": "",
    "cycle_prev": "",
    "groups": [],
    "group_by_character": {},
},
```

In `validated_preview`, preserve the current character and All-bind loops, then
normalize groups in input order. Track `seen_ids` and case-folded names; keep the
first valid occurrence. Treat an unparseable cycle as an empty binding so one
bad chord does not delete an otherwise valid group:

```python
groups = raw_hotkeys.get("groups")
valid_ids = set()
seen_names = set()
if isinstance(groups, list):
    for raw_group in groups:
        if not isinstance(raw_group, dict):
            continue
        group_id = raw_group.get("id")
        name = raw_group.get("name")
        if not isinstance(group_id, str) or not group_id:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        clean_name = name.strip()
        folded = clean_name.casefold()
        if group_id in valid_ids or folded in seen_names:
            continue
        parsed = preview_gestures.parse(raw_group.get("cycle"))
        section["hotkeys"]["groups"].append({
            "id": group_id,
            "name": clean_name,
            "cycle": preview_gestures.display(parsed) if parsed else "",
        })
        valid_ids.add(group_id)
        seen_names.add(folded)
```

Normalize membership only after `valid_ids` is complete, using
`preview_roster.deserialize` on the keys so `hwnd:` and duplicate constraints
stay owned by the roster module.

- [ ] **Step 5: Run settings tests and verify GREEN**

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings_preview.py tests/test_settings.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit the schema slice**

```bash
git add wingman/settings.py tests/test_settings_preview.py
git commit -m "feat: validate preview cycle groups"
```

---

### Task 2: Plan and fold group-specific cycle actions in PreviewHost

**Files:**
- Modify: `wingman/preview/host.py:116-170, 300-345, 1080-1275, 1935-1970`
- Test: `tests/test_preview_host.py:580-670, 960-1265, 2510-2565`
- Test: `tests/test_preview_cycle.py`

**Interfaces:**
- Consumes the normalized complete hotkey table from Task 1.
- Produces planner action `("cycle_group", group_id)`.
- Produces `PreviewHost._group_cycle_keys(group_id) -> list[str]`.
- Produces `_active_hotkeys` and `_last_group_cycled: dict[str, str]` runtime state.
- Leaves `cycle.step(keys, anchor, delta)` unchanged.

- [ ] **Step 1: Add failing planner tests**

Pin group action shape, creation-order precedence, canonical validation, and
collision dropping:

```python
def test_plan_carries_stable_id_for_named_group_cycles():
    plan = host.plan_registrations({
        "characters": {}, "cycle_next": "Ctrl+F1", "cycle_prev": "Ctrl+F2",
        "groups": [
            {"id": "dps-id", "name": "DPS", "cycle": "Ctrl+F3"},
            {"id": "logi-id", "name": "Logistics", "cycle": "Ctrl+F4"},
        ],
    })
    assert [entry[2] for entry in plan] == [
        ("cycle", 1), ("cycle", -1),
        ("cycle_group", "dps-id"), ("cycle_group", "logi-id"),
    ]
```

Add one duplicate test where a character chord beats a group, and one where All
beats a group using the same chord.

- [ ] **Step 2: Run planner tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_preview_host.py -k "plan and group" -v
```

Expected: group actions are missing.

- [ ] **Step 3: Extend `plan_registrations` minimally**

After the two existing All entries, append valid ordered group entries:

```python
groups = table.get("groups")
if isinstance(groups, list):
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries.append((group.get("cycle"), ("cycle_group", group.get("id"))))
```

Keep the existing claimed-chord loop authoritative so precedence follows entry
order and registration status remains honest.

- [ ] **Step 4: Add failing active-snapshot and group-key tests**

Verify `_apply_hotkeys` installs membership with the same generation as
`_registered`, `_group_cycle_keys` intersects live/non-excluded/assigned names,
and teardown clears the snapshot and group history:

```python
def test_group_cycle_keys_use_applied_membership_and_skip_excluded(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *a: None,
                         excluded=lambda: ["Excluded"])
    h._clients = {
        "Alice": _FakeClient("Alice", hwnd=1),
        "Bob": _FakeClient("Bob", hwnd=2),
        "Excluded": _FakeClient("Excluded", hwnd=3),
    }
    h._active_hotkeys = {
        "group_by_character": {
            "Alice": "dps", "Bob": "logi", "Excluded": "dps"
        }
    }
    assert h._group_cycle_keys("dps") == ["Alice"]
```

Add a test that mutates `_desired_hotkeys` to a newer membership without
applying it and proves dispatch still reads `_active_hotkeys`.

- [ ] **Step 5: Implement active table and group key resolution**

Initialize and clear:

```python
self._active_hotkeys = {}
self._last_group_cycled = {}
```

In `_apply_hotkeys`, install a defensive copy of the table in the same preview-
thread turn that replaces `_registered`. In `_teardown`, clear active table and
history. Add:

```python
def _group_cycle_keys(self, group_id: str) -> list:
    memberships = self._active_hotkeys.get("group_by_character") or {}
    return [name for name in self._cycle_keys()
            if memberships.get(name) == group_id]
```

Do not read `_desired_hotkeys` from dispatch.

- [ ] **Step 6: Add failing fold/history tests**

Extend `_batch_hotkey_host()` with group metadata and pin:

- foreground group member advances within that group;
- foreground nonmember starts at the group's first member;
- outside EVE resumes per-group history;
- All, DPS, and Logistics histories update independently in one batch;
- a later direct focus changes dispatch but not prior cycle histories;
- mixed DPS then Logistics uses the DPS virtual target as the Logistics anchor;
- mixed actions resolving to foreground perform no activation;
- empty group logs a group-specific no-op;
- capture receives a registered group chord instead of cycling.

Representative assertion:

```python
def test_mixed_group_cycles_keep_independent_histories(monkeypatch):
    h, libs = _batch_hotkey_host()
    h._active_hotkeys = {
        "group_by_character": {
            "Alice": "dps", "Bravo": "dps",
            "Carol": "logi", "Delta": "logi",
        }
    }
    h._registered = {
        1: ("cycle_group", "dps"),
        2: ("cycle_group", "logi"),
        3: ("cycle", 1),
    }
    h._on_hotkeys(libs, [1, 2, 3])
    assert h._last_group_cycled == {"dps": "Bravo", "logi": "Carol"}
    assert h._last_cycled == "Delta"
```

Derive expected names against the fixture's actual alphabetical roster before
finalizing the assertion; do not change `cycle.ordered()`.

- [ ] **Step 7: Implement group-aware folding**

Retain the current `target`, `resolved_cursor`, `cycle_seen`, and final dispatch
shape. Add per-scope pending histories:

```python
last_cycle_target = None
last_group_targets = {}
for _ident, action in registered:
    final_action = action
    kind, value = action
    if kind == "focus":
        target = self._pick_focus_target(value, resolved_cursor)
        if target is not None:
            resolved_cursor = target
        continue
    cycle_seen = True
    if kind == "cycle":
        keys = self._cycle_keys()
        history = self._last_cycled
        delta = value
    else:  # plan_registrations emits only focus, cycle, and cycle_group
        keys = self._group_cycle_keys(value)
        history = self._last_group_cycled.get(value)
        delta = 1
    if not keys:
        target = None
        continue
    target = cycle.step(keys, target or resolved_cursor or history, delta)
    if target is not None:
        resolved_cursor = target
        if kind == "cycle":
            last_cycle_target = target
        else:
            last_group_targets[value] = target
```

After folding, update every pending scope. Keep the existing global
`cycle_seen and target == foreground_key` no-op guard unchanged in meaning.
Delete stale history IDs after applying a table by intersecting with active
group IDs.

- [ ] **Step 8: Run host/cycle tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_preview_cycle.py tests/test_preview_host.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit the host slice**

```bash
git add wingman/preview/host.py tests/test_preview_host.py tests/test_preview_cycle.py
git commit -m "feat: cycle named preview groups"
```

---

### Task 3: Add serialized, operation-specific group API writes

**Files:**
- Modify: `wingman/ui/api.py:380-430, 3070-3290`
- Test: `tests/test_preview_wiring.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces public methods:
  - `create_preview_cycle_group(name) -> dict`
  - `rename_preview_cycle_group(group_id, name) -> dict`
  - `delete_preview_cycle_group(group_id) -> dict`
  - `set_preview_cycle_group_bind(group_id, gesture) -> dict`
  - `set_preview_character_group(name, group_id) -> dict`
- Each result contains `{applied, persisted, error, hotkeys}`; `hotkeys` is the
  authoritative normalized table on success or refusal.
- Existing `set_preview_binds(section) -> bool` keeps its public return contract.
- Later JavaScript calls these methods directly and never submits a complete
  group snapshot.

- [ ] **Step 1: Add failing construction and preservation tests**

Assert the lock is private, group creation uses injected `_id_factory`, and an
existing All/character bind write preserves group metadata:

```python
def test_set_preview_binds_preserves_cycle_groups(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    api._state.settings["preview"] = {"hotkeys": {
        "characters": {}, "cycle_next": "", "cycle_prev": "",
        "groups": [{"id": "dps", "name": "DPS", "cycle": "Ctrl+F3"}],
        "group_by_character": {"Alice": "dps"},
    }}
    assert api.set_preview_binds({
        "characters": {"Bob": "Ctrl+F2"},
        "cycle_next": "Ctrl+F1", "cycle_prev": "",
    }) is True
    hotkeys = api._state.settings["preview"]["hotkeys"]
    assert hotkeys["groups"][0]["id"] == "dps"
    assert hotkeys["group_by_character"] == {"Alice": "dps"}
```

- [ ] **Step 2: Run focused API tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_preview_wiring.py -k "cycle_group or preserves_cycle_groups" -v
```

Expected: missing methods/lock and group wipe.

- [ ] **Step 3: Add the writer lock and shared result helpers**

In `Api.__init__`:

```python
self._preview_hotkey_lock = threading.Lock()
```

Add private helpers that run only while that lock is held:

```python
def _preview_hotkeys(self) -> dict:
    return copy.deepcopy(
        self._state.settings.get("preview", {}).get("hotkeys") or {}
    )

@staticmethod
def _preview_group_result(applied, error, hotkeys) -> dict:
    return {
        "applied": bool(applied),
        "persisted": bool(applied),
        "error": error,
        "hotkeys": copy.deepcopy(hotkeys),
    }
```

Do not expose either as a public pywebview attribute.

- [ ] **Step 4: Change `set_preview_binds` to merge owned fields under the lock**

Keep its current parsing and Boolean return. Replace whole-object assignment
with latest-document mutation:

```python
with self._preview_hotkey_lock:
    try:
        with settings_mod.update(self._state.settings) as cfg:
            hotkeys = cfg.setdefault("preview", {}).setdefault("hotkeys", {})
            hotkeys["characters"] = table["characters"]
            hotkeys["cycle_next"] = table["cycle_next"]
            hotkeys["cycle_prev"] = table["cycle_prev"]
    except OSError:
        logger.exception("Could not persist preview hotkeys")
        return False
    applied = self._preview_hotkeys()
    if self._preview_host is not None:
        self._preview_host.set_hotkeys(applied)
return True
```

The host call remains inside `_preview_hotkey_lock` and after the successful
`settings.update()` exit.

- [ ] **Step 5: Add failing lifecycle and assignment tests**

Cover trimmed/case-insensitive name validation, stable rename, delete cleanup,
canonical bind parsing, invalid/stale IDs, offline stable names, `hwnd:`
rejection, All-only assignment via empty ID, no-host persistence, and host
handoff of the complete table.

Use deterministic IDs:

```python
def test_create_rename_assign_and_delete_cycle_group(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "group-id")
    created = api.create_preview_cycle_group(" DPS ")
    assert created["applied"] is True
    assert created["hotkeys"]["groups"] == [
        {"id": "group-id", "name": "DPS", "cycle": ""}
    ]
    assert api.set_preview_character_group("Alice", "group-id")["applied"]
    assert api.rename_preview_cycle_group("group-id", "Damage")["applied"]
    deleted = api.delete_preview_cycle_group("group-id")
    assert deleted["hotkeys"]["groups"] == []
    assert deleted["hotkeys"]["group_by_character"] == {}
```

- [ ] **Step 6: Implement narrow mutation endpoints**

For every method:

1. validate scalar input before mutation;
2. acquire `_preview_hotkey_lock`;
3. enter `settings_mod.update`;
4. resolve the latest group by stable ID;
5. mutate only the owned group or membership key;
6. let normal settings validation canonicalize;
7. deep-copy the resulting complete table;
8. call `host.set_hotkeys(table)` while still holding the writer lock;
9. return the authoritative result.

Use `_id_factory()` once for create and refuse the improbable collision rather
than looping forever under an injected constant test factory. Empty group ID in
`set_preview_character_group` removes the character mapping and means All only.
Use `_usable_preview_character(name)` for the same stable-name boundary as other
preview APIs.

- [ ] **Step 7: Add failing concurrency-order tests**

Use barriers/events in fake `settings_mod.update` or fake host delivery to prove
that two pywebview-style threads cannot deliver host tables in reverse durable
order, and that a stale rename cannot resurrect a deleted ID. Also prove a
failed persist never invokes `host.set_hotkeys`.

```python
def test_preview_hotkey_writer_keeps_host_delivery_in_persist_order(
    tmp_path, monkeypatch
):
    _no_disk(monkeypatch)
    first_delivery = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    deliveries = []

    class BlockingHost(FakeHost):
        def set_hotkeys(self, table):
            deliveries.append(copy.deepcopy(table))
            if len(deliveries) == 1:
                first_delivery.set()
                assert release_first.wait(1)

    api = make_api(tmp_path, preview_host=BlockingHost())
    api._state.settings["preview"] = {"hotkeys": {
        "characters": {}, "cycle_next": "", "cycle_prev": "",
        "groups": [{"id": "dps", "name": "DPS", "cycle": ""}],
        "group_by_character": {},
    }}
    first = threading.Thread(
        target=lambda: api.rename_preview_cycle_group("dps", "Damage")
    )

    def assign():
        api.set_preview_character_group("Alice", "dps")
        second_done.set()

    first.start()
    assert first_delivery.wait(1)
    second = threading.Thread(target=assign)
    second.start()
    assert not second_done.wait(0.05)
    assert api._state.settings["preview"]["hotkeys"]["group_by_character"] == {}
    release_first.set()
    first.join(1)
    second.join(1)
    assert [table["group_by_character"] for table in deliveries] == [
        {}, {"Alice": "dps"}
    ]
```

Add `copy` and `threading` to the test module imports if they are not already
present.

The final test must assert concrete observed write/delivery order, not only that
a lock attribute exists.

- [ ] **Step 8: Extend the hotkey-state payload tests**

Assert `get_preview_hotkey_state()` returns normalized `groups` and
`group_by_character` whether the host is running or absent, and
`push_preview_hotkeys()` carries the same fields.

- [ ] **Step 9: Run API tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_api.py -q
```

Expected: all pass.

- [ ] **Step 10: Commit the API slice**

```bash
git add wingman/ui/api.py tests/test_preview_wiring.py tests/test_api.py
git commit -m "feat: manage preview cycle groups"
```

---

### Task 4: Render group keybinds, management, and exclusive assignment

**Files:**
- Modify: `wingman/web/previews.js:1-140, 900-1290`
- Modify: `wingman/web/style.css:2220-2565`
- Modify: `wingman/web/index.html:980-1045` only if a shared status slot is needed
- Test: `tests/test_preview_wiring.py:1090-1190`
- Test: `tests/test_page_conventions.py:1640-1740, 1920-1950`

**Interfaces:**
- Consumes Task 3 payload fields and bridge methods.
- Produces no new Python-to-page handler; continues using `onPreviewHotkeys`.
- Produces helpers `groups()`, `makeGroupSelect`, `makeGroupManager`,
  `setGroupBind`, and `mutateGroup` within the existing IIFE.

- [ ] **Step 1: Add failing lexical tests for group rows and clashes**

Tests must prove:

- `clashes()` counts every `groups[*].cycle` against All and character chords;
- group rows are rendered after All rows and before the character divider;
- group binding uses `set_preview_cycle_group_bind`, not full `send(next)`;
- Clear remains absent on empty group binds and Edit… remains available;
- capture is ended before rename/delete dialogs;
- rename uses `WM.prompt`, delete uses `WM.confirm`, and browser dialogs are absent.

Representative source assertion:

```python
def test_named_group_clashes_are_counted_with_all_cycle_chords():
    block = _web("previews.js").split("function clashes", 1)[1].split(
        "function makeRow", 1
    )[0]
    assert "state.hotkeys.groups" in block
    assert ".cycle" in block
```

- [ ] **Step 2: Run UI source tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_page_conventions.py -k "group or clashes or grid" -v
```

Expected: missing group rendering and bridge calls.

- [ ] **Step 3: Normalize page state and extend clash detection**

Every payload replacement must fill safe defaults:

```javascript
state.hotkeys.groups = state.hotkeys.groups || [];
state.hotkeys.group_by_character = state.hotkeys.group_by_character || {};
```

Add a helper returning ordered groups and extend `clashes(gesture)` so cycles
counts both All fields and matching group cycles. Keep shared character chords
non-conflicting exactly as today.

- [ ] **Step 4: Render All and named group keybind rows**

Change resting labels to **All forward** and **All back**, then append each group
through `makeRow(group.name, group.cycle, true, onSet)` before the unnamed
character divider. Because group rows have no character, they reuse the same
Preview and Geometry fillers as All rows and do not change track count.

`setGroupBind(groupId, gesture)` ends capture and calls
`set_preview_cycle_group_bind`. On refusal, refresh and send the specific error
to the existing alert path; on success, apply returned authoritative hotkeys
only if no newer push generation landed.

- [ ] **Step 5: Add failing assignment placement and state tests**

Lexically assert `makeGroupSelect` appends its select to `lab`, never to `row`,
and only when groups exist. Assert it offers All only first, uses stable IDs as
values, commits on `change`, stays enabled on offline/opted-out rows, and reverts
on refusal.

Extend the existing grid derivation test so the group-select helper cannot add a
cell-level `row.appendChild` while `makeRow`'s five-cell count still equals the
CSS tracks.

- [ ] **Step 6: Implement assignment inside `.lab`**

Inside `makeRow`, after `.lab-name` and only for real characters:

```javascript
if (character && groups().length) {
  lab.classList.add('has-group-select');
  lab.appendChild(makeGroupSelect(character));
}
```

`makeGroupSelect` creates a dark native select, begins with value `''` and label
`All only`, then appends group options in creation order. On change it disables
group mutation controls temporarily, calls
`set_preview_character_group(name, selectedId)`, and restores authoritative
state/focus after success or refusal. It does not inherit the keybind `off`
gate.

- [ ] **Step 7: Add scoped CSS without changing the grid template**

Keep `#preview-binds`'s current five tracks. Add only scoped character-cell
rules:

```css
#preview-binds .row > .lab.has-group-select {
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}
#preview-binds .preview-group-select {
  width: 100%; min-width: 0; max-width: 100%;
}
#preview-binds .lab.dim .preview-group-select {
  color: var(--text);
}
```

Use existing field/select tokens and focus-visible rules; do not hardcode a new
color. Confirm `[hidden]` overrides remain valid for any new display selector.

- [ ] **Step 8: Add failing lifecycle-management tests**

Assert the inline disclosure includes Add, Rename…, and Delete; Add commits by
button/Enter but not blur; group count is derived; delete copy includes group
name, exact member count, and All outcome; controls disable during a mutation;
and focus returns to a surviving control after repaint.

- [ ] **Step 9: Implement the Manage groups disclosure**

Build it inside `#preview-binds` after group key rows and before the character
separator, with a full-grid-span class. Use a labelled text field and ordinary
`.btn` for Add. Use `WM.prompt` for rename and `.btn.danger` plus `WM.confirm`
for delete. Derive member count from `group_by_character` before opening the
confirm. Call only Task 3's narrow endpoints.

Keep one `groupBusy` state. While a group write is pending, disable lifecycle and
assignment controls but never disable the keybind or control needed to leave the
Settings section. Clear busy state on both resolve and rejection.

- [ ] **Step 10: Run focused UI tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_page_conventions.py -q
```

Expected: all pass.

- [ ] **Step 11: Commit the web interaction slice**

```bash
git add wingman/web/previews.js wingman/web/style.css wingman/web/index.html tests/test_preview_wiring.py tests/test_page_conventions.py
git commit -m "feat: configure preview cycle groups"
```

---

### Task 5: Make the dev harness and screenshots exercise real group states

**Files:**
- Modify: `wingman/web/dev.js:751-870`
- Modify: `tests/test_dev_harness.py:450-510`
- Modify: `scripts/shoot_screens.py`
- Test: `tests/test_shoot_screens.py`

**Interfaces:**
- Produces a browser fixture with assigned, All-only, offline, opted-out, empty,
  and collision group states.
- Produces screenshot stages for normal and 840x625 layouts.

- [ ] **Step 1: Add failing fixture-contract tests**

Parse the `api.get_preview_hotkey_state` fixture and assert it visibly carries:

```python
def test_the_preview_groups_fixture_covers_real_states():
    block = _fixture_body("api.get_preview_hotkey_state")
    assert "groups:" in block
    assert "group_by_character:" in block
    assert "cycle: 'Ctrl+Shift+" in block
    assert "name: 'DPS'" in block
    assert "name: 'Empty group'" in block
    assert "All only" not in block  # UI label, not persisted data
```

Also extend the real-gesture-string test to inspect every group `cycle` value.

- [ ] **Step 2: Run harness tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py -k "preview and group" -v
```

Expected: fixture lacks group fields.

- [ ] **Step 3: Implement stateful dev API methods**

Seed at least DPS, Logistics, and an empty group with stable IDs. Assign one
online, one offline, and leave one All-only character; include an opted-out
assigned member and one deliberate collision. Add dev implementations of all
five Task 3 methods that mutate the in-memory fixture, return the production
result shape, and asynchronously call `window.onPreviewHotkeys`.

Do not hardcode derived member counts. JavaScript derives them from
`group_by_character`, just as production does.

- [ ] **Step 4: Add failing screenshot-stage tests**

Pin a named stage that opens Settings > Previews with populated groups and one
that captures 840x625. Assert stage names, route/section selection, dimensions,
and waits follow existing screenshot-script conventions.

- [ ] **Step 5: Implement screenshot stages**

Stage:

- complete populated Global keybinds card;
- Manage groups disclosure open;
- 840x625 character rows with long character/group names;
- a keybind collision treatment.

Use the existing script helpers and dev fixture; do not add browser-only mock
markup.

- [ ] **Step 6: Run harness and screenshot tests and verify GREEN**

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py tests/test_shoot_screens.py -q
```

Expected: all pass.

- [ ] **Step 7: Generate and inspect the screenshots**

Run the repository's documented screenshot command/stages from
`scripts/shoot_screens.py`. Open every generated PNG. Verify the select is dark,
inside the Character track, readable when offline, and horizontally contained
at 840x625; verify the management disclosure spans all tracks and no row after
it shifts columns.

If the environment cannot render WebView/browser captures, record that exact
limitation and do not claim visual verification.

- [ ] **Step 8: Commit the harness slice**

```bash
git add wingman/web/dev.js scripts/shoot_screens.py tests/test_dev_harness.py tests/test_shoot_screens.py
git commit -m "test: exercise preview cycle group UI"
```

---

### Task 6: Update living documentation and perform final verification

**Files:**
- Modify: `docs/smoke-checklist.md`
- Modify: `docs/ui-walkthrough.md`
- Modify: `docs/preview-roadmap.md`
- Modify: `wingman/web/style.css` comments that name resting labels
- Modify: `wingman/web/previews.js` comments that name resting labels
- Review: `docs/preview-cycle-groups-design.md`

**Interfaces:**
- No new runtime interface.
- Produces the manual release gate and reconciles the roadmap's deferred named-group item.

- [ ] **Step 1: Update existing resting-label references**

Change current references describing the UI from **Cycle forward/back** to
**All forward/back** in `docs/smoke-checklist.md`, `docs/ui-walkthrough.md`, and
live source/style comments. Do not rewrite immutable records under
`docs/history/`; historical wording remains historical.

- [ ] **Step 2: Add the reviewed Windows/EVE checks**

Copy the ten concrete cases from the design's **Windows and EVE smoke checks**
into the relevant preview-hotkeys section of `docs/smoke-checklist.md`. Preserve
its checkbox format and include the load-bearing cases: mixed batching,
foreground nonmember, browser history, opt-out retention, rename, populated
delete, login/logout churn, capture during roster push, and 840x625 layout.

- [ ] **Step 3: Reconcile the roadmap**

Mark named cycle groups complete or remove the now-satisfied deferred note while
leaving multiple full preview profiles and EVE-O/EVE-X import explicitly open.
Do not imply this feature implements profiles.

- [ ] **Step 4: Run focused verification**

```bash
uv run --no-sync python -m pytest tests/test_settings_preview.py tests/test_preview_cycle.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_shoot_screens.py -q
```

Expected: all pass.

- [ ] **Step 5: Run full automated gates**

```bash
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: pytest passes with only documented platform skips; Ruff and diff
checks exit 0.

- [ ] **Step 6: Run `polish-core --fix` and inspect every edit**

Load and run the repository-required `polish-core` workflow against the branch
base. Accept only high-confidence in-scope fixes. Inspect `git diff` afterward,
then rerun Step 4 and Step 5 from the changed tree.

- [ ] **Step 7: Run the Windows/EVE smoke gate**

Execute the updated preview cycle-group checklist on Windows with real EVE
clients. Record which checks were actually run. Do not claim completion if the
manual group hotkey or rendered-layout gate was not exercised.

- [ ] **Step 8: Inspect final scope and explain the change**

Inspect `git diff 04156dd..HEAD` plus uncommitted changes for accidental
profile work, backward group cycling, client geometry calls, debug output,
placeholders, or dead paths. Run the required `change-explainer` workflow after
fresh verification.

- [ ] **Step 9: Commit documentation and final safe fixes**

```bash
git add docs/smoke-checklist.md docs/ui-walkthrough.md docs/preview-roadmap.md \
  wingman/web/previews.js wingman/web/style.css
git commit -m "docs: cover preview cycle groups"
```

Only include source files here if the final comment/reference reconciliation
changed them; otherwise omit them from `git add`.

## Testing and verification strategy

- **Pure Linux behavior:** settings normalization, group planning, group roster
  filtering, mixed action folding, per-scope history, and teardown.
- **Bridge/concurrency:** narrow mutation ownership, failure rollback, no-host
  persistence, full-table handoff, and durable/apply ordering under threads.
- **Lexical web guards:** five-cell grid, select placement, dark control
  vocabulary, dialog/capture rules, clash coverage, and payload initialization.
- **Browser/dev harness:** real group states and interactive lifecycle methods,
  with generated normal and floor screenshots inspected manually.
- **Windows/EVE:** real `RegisterHotKey` acceptance/release, named-cycle target
  sets, rapid mixed folds, client churn, capture, and foreground behavior.
- **Full gates:** all 3331+ tests, Ruff check, Ruff format check, and diff check.

## Adaptation points

- If the Character cell becomes unreadably tall or the select cannot fit the
  bounded track at 840x625, stop and return to the approved layout decision;
  do not add a sixth column. A compact value button using the existing picker
  is the fallback requiring user review.
- If mixed group/All fold tests expose an ambiguous sequential target not
  settled by the design examples, stop and present the exact action sequence
  and candidate outcomes before changing semantics.
- If an operation-specific API still allows host application order to diverge
  from persistence order, strengthen the single writer boundary; do not move
  group ownership into JavaScript.
- If Windows refuses a named group chord, use the existing registration-status
  treatment. Do not add retry loops or synthesize input.
- If generated screenshots pass but native WebView2 renders the select
  differently, the Windows rendering is authoritative and the CSS must stay
  within existing tokens/components.

## Explicit exclusions

- Multiple named-group membership.
- Backward cycle keys for named groups.
- Fixed role templates, nested groups, colors, icons, and drag reordering.
- Group-specific preview geometry, visibility, alerts, locking, or minimize behavior.
- A runtime cycle button inside Wingman's window.
- Full preview profiles or EVE-O/EVE-X profile import.
- Cycle sort changes or hotkey notation changes.
- Preview switch-performance changes or any EVE client geometry call.
