# Fleet Bar Character Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users persistently hide selected known characters from the floating Fleet Bar through Settings while leaving telemetry collection, Previews, Alerts, and the display-only Fleet window independent.

**Architecture:** Extend the existing `fleet_bar` settings section with remembered and hidden name lists. Stamp coordinator snapshots with a Fleet activation generation, then let `Api` own a revisioned presentation boundary that rejects retired callbacks, derives Settings state, persists roster transitions sparsely, and filters only the auxiliary-window payload. The Settings page consumes only the dedicated revisioned Fleet state; the floating page remains non-interactive and distinguishes no clients from all clients hidden.

**Tech Stack:** Python 3.11+, dataclasses, threads/locks, pytest, plain HTML/CSS/ES5 JavaScript, pywebview 6.2.1, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-fleet-character-visibility-design.md`

## Global Constraints

- Windows-only runtime, but all changed Python modules must remain importable and testable on Linux.
- The Fleet Bar remains display-only and full-surface draggable; add no buttons, inputs, row actions, or context menu to `fleetbar.html`.
- Fleet visibility filters presentation only; discovery, gamelog reading, Fleet Metrics, Previews, Alerts, and preview keybinds retain the complete roster.
- Preview exclusion and Fleet exclusion remain independent settings.
- Existing installations show every character by default; no explicit migration marker or version bump.
- Settings fields commit independently and do not commit before their first authoritative payload.
- Generated checkboxes use `.check` / `.box`, have character-specific accessible names, and preserve keyboard focus.
- Never render Fleet controls from unrevisioned generic `wm:settings` state.
- Never hold the settings save lock and Fleet presentation lock at the same time.
- Existing lock order remains `shutdown_lock` → `_fleetbar_lifecycle_lock`; the new presentation lock is never held across pywebview calls or settings writes.
- The page has no automated DOM runtime. Python behavior is tested directly; JavaScript and CSS contracts are tested lexically and exercised through the manual smoke checklist.
- No new dependency, package, build step, or bundler.

---

### Task 1: Stamp Fleet Activations at the Coordinator Boundary

**Files:**
- Modify: `wingman/telemetry/model.py:93-105`
- Modify: `wingman/telemetry/coordinator.py:121-135, 199-220, 305-345, 422-435, 483-501, 755-780, 844-865`
- Test: `tests/test_telemetry_coordinator.py`

**Interfaces:**
- Produces: `FleetSnapshot.activation_generation: int`
- Produces: `TelemetryCoordinator.reconcile() -> int`
- Produces: `TelemetryCoordinator.requested_fleet_generation() -> int`
- Changes: `_FleetMode(enabled: bool, generation: int)`
- Consumed later by: `Api` generation handoff in Task 3

- [ ] **Step 1: Write failing generation-contract tests**

Add focused tests to `tests/test_telemetry_coordinator.py` proving that generations are reserved before fallible startup, remain stable for idempotent reconciliation, and stamp publications:

```python
def test_fleet_generation_is_reserved_even_when_dispatcher_cannot_start(tmp_path):
    h = _harness(tmp_path, fleet=True)
    h.coordinator._start_dispatcher = lambda: False

    generation = h.coordinator.reconcile()

    assert generation == 1
    assert h.coordinator.requested_fleet_generation() == 1
    assert h.coordinator._fleet_requested is True


def test_idempotent_reconcile_reuses_requested_fleet_generation(tmp_path):
    h = _harness(tmp_path, fleet=True)

    first = h.coordinator.reconcile()
    second = h.coordinator.reconcile()

    assert first == second == 1


def test_each_fleet_mode_transition_reserves_a_new_generation(tmp_path):
    h = _harness(tmp_path, fleet=True)
    first = h.coordinator.reconcile()
    h.flags["fleet"] = False
    second = h.coordinator.reconcile()
    h.flags["fleet"] = True
    third = h.coordinator.reconcile()

    assert (first, second, third) == (1, 2, 3)


def test_published_snapshot_carries_the_activated_generation(tmp_path):
    h = _harness(tmp_path, fleet=True)
    generation = h.coordinator.reconcile()
    h.coordinator.dispatch_once(0)  # applies _FleetMode
    h.coordinator.dispatch_once(0)  # publishes

    assert h.coordinator.snapshot().activation_generation == generation
```

Adapt these snippets to the file's existing harness names rather than creating a duplicate harness. Add a case where a failed first dispatcher start is followed by a successful unrelated reconcile; the queued Fleet mode must activate the already-reserved generation rather than allocating another.

- [ ] **Step 2: Run the focused tests and confirm the intended failures**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_telemetry_coordinator.py \
  -k 'generation or dispatcher' -v
```

Expected: failures because `FleetSnapshot` has no activation generation, `reconcile()` returns `None`, and `_FleetMode` carries only `enabled`.

- [ ] **Step 3: Add the generation to the immutable model**

Append a compatibility default so pure `FleetMetrics` and existing direct test constructors remain valid until the coordinator stamps them:

```python
@dataclass(frozen=True)
class FleetSnapshot:
    rows: tuple[FleetRow, ...]
    stream_health: StreamHealth
    metric_error: str | None = None
    activation_generation: int = 0
```

`0` means “not stamped by an active coordinator,” never a valid enabled activation accepted by `Api`.

- [ ] **Step 4: Reserve Fleet mode before fallible infrastructure startup**

Change `_FleetMode` and coordinator state:

```python
class _FleetMode(NamedTuple):
    enabled: bool
    generation: int

# __init__
self._fleet_requested = False
self._fleet_requested_generation = 0
self._fleet_active_generation = 0
```

Make `_request_fleet_mode()` atomically reserve and return the generation:

```python
def _request_fleet_mode(self, enabled: bool) -> int:
    with self._lock:
        if enabled == self._fleet_requested:
            return self._fleet_requested_generation
        self._fleet_requested = enabled
        self._fleet_requested_generation += 1
        generation = self._fleet_requested_generation
    self._queue.put(_FleetMode(enabled, generation))
    return generation


def requested_fleet_generation(self) -> int:
    with self._lock:
        return self._fleet_requested_generation
```

In `reconcile()`, call `_request_fleet_mode(fleet_enabled)` immediately after reading predicates and before `_start_dispatcher()`. Return the reserved generation from every exit, including dispatcher-start refusal. Keep expected infrastructure failures contained and logged so delayed activation retains the same generation.

- [ ] **Step 5: Activate and publish the queued generation**

Change `_apply_fleet_mode()` to receive the whole control item and set `_fleet_active_generation` on the dispatcher thread. Stamp snapshots with `dataclasses.replace` rather than teaching pure `FleetMetrics` about coordinator lifecycle:

```python
snapshot = dataclasses.replace(
    self._metrics.snapshot(self._sequence, health),
    activation_generation=self._fleet_active_generation,
)
```

Ensure `snapshot()` returns the stamped latest publication when one exists. Its
synthetic empty result before the first publication, and its disabled result,
retain activation generation `0`; `Api` must not mistake either for an
authoritative current roster.

- [ ] **Step 6: Run coordinator and metrics tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_telemetry_coordinator.py \
  tests/test_fleet_metrics.py -v
```

Expected: all pass. Confirm existing pure metric snapshots still use generation `0` until the coordinator stamps them.

- [ ] **Step 7: Commit the coordinator contract**

```bash
git add wingman/telemetry/model.py wingman/telemetry/coordinator.py \
  tests/test_telemetry_coordinator.py
git commit -m "feat: identify fleet telemetry activations"
```

---

### Task 2: Extend and Validate Fleet-Bar Persistence

**Files:**
- Modify: `wingman/settings.py:305-311, 707-723`
- Modify: `tests/test_fleet_bar_settings.py`
- Modify: `tests/test_settings.py:115-135, 230-245`

**Interfaces:**
- Produces persisted shape: `fleet_bar.{enabled,x,y,seen,hidden}`
- Reuses: `wingman.preview.roster.deserialize(raw, cap=64)`
- Consumed later by: Task 4 backend state and mutation

- [ ] **Step 1: Update expected defaults and write failing validation tests**

Change existing exact-dictionary assertions to include `seen` and `hidden`, then add:

```python
def test_fleet_bar_validates_character_rosters():
    value = settings.validated_fleet_bar(
        {
            "enabled": True,
            "seen": ["Alice", "", 4, "hwnd:0x1", "Alice", "Bravo"],
            "hidden": ["Bravo", None, "Bravo", "Carol"],
        }
    )
    assert value["seen"] == ["Alice", "Bravo"]
    assert value["hidden"] == ["Bravo", "Carol"]


def test_fleet_bar_character_rosters_are_capped():
    names = [f"Character {index}" for index in range(70)]
    value = settings.validated_fleet_bar({"seen": names, "hidden": names})
    assert value["seen"] == names[:64]
    assert value["hidden"] == names[:64]
```

Also update save-normalization tests to assert the complete five-key section.

- [ ] **Step 2: Run the settings tests and confirm they fail**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar_settings.py \
  tests/test_settings.py -k 'fleet_bar or save_then_load' -v
```

Expected: exact-shape and roster-validation failures.

- [ ] **Step 3: Implement defaults and validation**

Change the defaults to:

```python
def _fleet_bar_defaults() -> dict:
    return {
        "enabled": False,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }
```

In `validated_fleet_bar()`, retain the current scalar validation and add:

```python
section["seen"] = preview_roster.deserialize(raw.get("seen"))
section["hidden"] = preview_roster.deserialize(raw.get("hidden"))
```

Do not reuse `preview.excluded`; only reuse the pure character-name validation rule.

- [ ] **Step 4: Run the full settings slice**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar_settings.py tests/test_settings.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit the schema change**

```bash
git add wingman/settings.py tests/test_fleet_bar_settings.py tests/test_settings.py
git commit -m "feat: persist fleet character visibility"
```

---

### Task 3: Make API Fleet Lifecycle Generation-Safe

**Files:**
- Modify: `wingman/ui/api.py:590-620, 4065-4120, 3750-3885`
- Modify: `tests/test_fleet_bar.py`
- Modify: test telemetry fakes in `tests/test_fleet_bar.py`

**Interfaces:**
- Consumes: `TelemetryCoordinator.reconcile() -> int`
- Consumes: `TelemetryCoordinator.requested_fleet_generation() -> int`
- Consumes: `FleetSnapshot.activation_generation`
- Produces private state: `_fleet_presentation_lock`, `_fleet_expected_generation`, `_fleet_presentation_revision`, `_fleet_roster_signature`, `_fleet_pending_seen`
- Produces: `_receive_fleet_snapshot(snapshot)` rejection before state mutation

- [ ] **Step 1: Upgrade the Fleet telemetry fake and write failing lifecycle tests**

Give `FakeTelemetry` deterministic generation and latest-snapshot behavior:

```python
class FakeTelemetry:
    def __init__(self):
        self.reconciled = 0
        self.generation = 0
        self.latest = FleetSnapshot(
            rows=(),
            stream_health=StreamHealth(state="stopped"),
            activation_generation=0,
        )

    def reconcile(self):
        self.reconciled += 1
        self.generation += 1
        return self.generation

    def requested_fleet_generation(self):
        return self.generation

    def snapshot(self):
        return self.latest
```

Add tests that force:

```python
def test_snapshot_from_retired_activation_is_rejected(api):
    api._fleet_expected_generation = 2
    stale = FleetSnapshot(
        rows=(FleetRow("Old Session", 99),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._receive_fleet_snapshot(stale)
    assert api._fleet_snapshot is None


def test_callback_during_toggle_handoff_cannot_restore_old_snapshot(api):
    stale = FleetSnapshot(
        rows=(FleetRow("Old Session", 99),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._fleet_expected_generation = 1
    api._telemetry.generation = 1

    def reconcile():
        api._receive_fleet_snapshot(stale)
        api._telemetry.generation = 2
        return 2

    api._telemetry.reconcile = reconcile
    api.toggle_fleet_bar(False)

    assert api._fleet_expected_generation == 2
    assert api._fleet_snapshot is None


def test_failed_toggle_persistence_restores_prior_acceptance(api, monkeypatch):
    from wingman.ui import api as api_mod

    prior = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._fleet_expected_generation = 1
    api._fleet_snapshot = prior
    api._fleet_roster_signature = ("Alice",)

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", fail_save)
    result = api.toggle_fleet_bar(True)

    assert result["applied"] is False
    assert api._fleet_expected_generation == 1
    assert api._fleet_snapshot is prior
    assert api._fleet_roster_signature == ("Alice",)


def test_persisted_enabled_startup_installs_generation_before_latest_snapshot(api):
    latest = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._state.settings["fleet_bar"]["enabled"] = True
    api._telemetry.generation = 1
    api._telemetry.latest = latest

    api.start_previews_if_enabled()

    assert api._fleet_expected_generation == 1
    assert api._fleet_snapshot is latest


def test_unexpected_reconcile_error_uses_requested_generation(api):
    api._telemetry.generation = 2

    def fail_reconcile():
        raise RuntimeError("unexpected")

    api._telemetry.reconcile = fail_reconcile
    result = api.toggle_fleet_bar(True)

    assert result["applied"] is True
    assert api._fleet_expected_generation == 2
    assert api._fleet_snapshot is None
```

Use events/barriers for the callback-during-handoff case; do not rely on sleeps.

- [ ] **Step 2: Run the lifecycle tests and confirm they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py \
  -k 'generation or handoff or persistence or startup' -v
```

Expected: failures because `Api` has no presentation generation or closed handoff.

- [ ] **Step 3: Add private presentation state and lock-order comments**

In `Api.__init__`, initialize:

```python
self._fleet_presentation_lock = threading.Lock()
self._fleet_expected_generation = None  # rejecting sentinel
self._fleet_presentation_revision = 0
self._fleet_roster_signature = None
self._fleet_pending_seen = []
```

Document these rules beside the fields:

```text
shutdown_lock -> _fleetbar_lifecycle_lock -> _fleet_presentation_lock
settings save lock and _fleet_presentation_lock are never nested
evaluate_js is never called while _fleet_presentation_lock is held
```

- [ ] **Step 4: Implement the closed generation handoff**

Factor one internal helper used by startup and actual Fleet mode transitions:

```python
def _reconcile_fleet_generation(self, *, transition: bool) -> int | None:
    # If transition: save and clear prior acceptance under presentation lock.
    # Call telemetry.reconcile() with no presentation lock held.
    # Install returned/requested generation under presentation lock.
    # Route telemetry.snapshot() through _receive_fleet_snapshot().
    # On pre-reconcile settings failure, caller restores saved acceptance.
```

Have `_reconcile_eve_runtime()` return the coordinator generation. Do not close
acceptance for Preview-, Alert-, or folder-only reconciliation. Initialize
persisted-enabled startup through the same handoff in
`start_previews_if_enabled()`. Sample `telemetry.snapshot()` only when Fleet is
enabled; a generation-`0` synthetic result is rejected by the ordinary receive
path. On disable, keep `_fleet_snapshot=None` so remembered characters remain
Known instead of being labelled Offline.

In `_receive_fleet_snapshot()`, compare `snapshot.activation_generation` with `_fleet_expected_generation` while holding the presentation lock. Return before changing any field when they differ.

- [ ] **Step 5: Preserve toggle rollback behavior**

Wrap the enabled-setting write and generation handoff so:

- write failure restores the saved generation/snapshot/signature and returns refusal;
- successful persistence plus expected infrastructure refusal retains the reserved generation and shows WAITING;
- unexpected reconciliation failure installs `requested_fleet_generation()` in `finally`;
- window-creation failure still persists `enabled=False`, reconciles that new transition, destroys the failed window, and pushes the off state.

Do not hold `_fleetbar_lifecycle_lock` while waiting for a callback to run; the handoff samples `telemetry.snapshot()` rather than waiting.

- [ ] **Step 6: Run focused Fleet lifecycle tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py -v
```

Expected: all pass, including existing create/show/hide/restore/shutdown cases.

- [ ] **Step 7: Commit generation-safe API lifecycle**

```bash
git add wingman/ui/api.py tests/test_fleet_bar.py
git commit -m "fix: reject retired fleet snapshots"
```

---

### Task 4: Derive, Persist, Mutate, and Filter Fleet Visibility

**Files:**
- Modify: `wingman/ui/api.py:3750-3810`
- Modify: `tests/test_fleet_bar.py`
- Modify: `tests/test_fleet_bar_settings.py` if a shared cap constant is exported

**Interfaces:**
- Produces: `Api.fleet_bar_settings() -> {enabled, x, y, seen, hidden, revision, characters}`
- Produces: `Api.set_fleet_bar_character_visible(name, visible) -> {applied, persisted, error, state}`
- Produces display payload fields: `rows`, `running_count`, `revision`, `stream_health`, `metric_error`
- Consumed later by: Settings UI in Task 5 and floating page in Task 6

- [ ] **Step 1: Write failing payload and roster-memory tests**

Add tests covering exact semantic payloads:

```python
def test_fleet_settings_groups_running_offline_and_hidden(api):
    api._state.settings["fleet_bar"].update(
        seen=["Bravo", "Alice", "Offline"], hidden=["Bravo"]
    )
    api._fleet_expected_generation = 3
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Bravo", 0), FleetRow("Alice", 10)),
            stream_health=StreamHealth(state="active"),
            activation_generation=3,
        )
    )
    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": True, "visible": True},
        {"name": "Bravo", "running": True, "visible": False},
        {"name": "Offline", "running": False, "visible": True},
    ]


def test_fleet_settings_reports_unknown_when_consumer_is_inactive(api):
    api._state.settings["fleet_bar"]["seen"] = ["Alice"]
    api._fleet_snapshot = None
    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": None, "visible": True}
    ]
```

Add tests for current → pending → persisted ordering, duplicate removal, successful pending clear, failed-write retention, no retry on metric-only publication, and retry on the next roster transition. Patch the settings update context manager with real rollback semantics for failure tests.

- [ ] **Step 2: Write failing mutation and concurrency tests**

Cover:

```python
def test_hide_filters_only_fleet_payload(api):
    result = api.set_fleet_bar_character_visible("Alice", False)
    assert result["applied"] is True
    assert "Alice" not in [row["character"] for row in api.fleet_bar_snapshot()["rows"]]
    assert api._state.settings["preview"].get("excluded", []) == []


def test_visibility_write_failure_refuses_and_rolls_back(api, monkeypatch):
    # settings.update raises OSError after mutating its temporary live section.
    result = api.set_fleet_bar_character_visible("Alice", False)
    assert result["applied"] is False
    assert "Alice" not in api._state.settings["fleet_bar"]["hidden"]
    assert result["state"]["characters"][0]["visible"] is True


def test_concurrent_hides_at_limit_do_not_lose_or_silently_truncate(api):
    original = [f"Hidden {index}" for index in range(63)]
    api._state.settings["fleet_bar"].update(
        seen=["Alice", "Bravo"], hidden=original
    )
    start = threading.Barrier(3)
    results = {}

    def hide(name):
        start.wait()
        results[name] = api.set_fleet_bar_character_visible(name, False)

    threads = [
        threading.Thread(target=hide, args=("Alice",)),
        threading.Thread(target=hide, args=("Bravo",)),
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(5)

    hidden = api._state.settings["fleet_bar"]["hidden"]
    assert all(not thread.is_alive() for thread in threads)
    assert len(hidden) == 64
    assert set(original) <= set(hidden)
    assert sorted(result["applied"] for result in results.values()) == [False, True]
```

Also assert an unchanged request performs no write, restoring is allowed at the cap, unknown/invalid names are refused, all-hidden payload has `rows=[]` and positive `running_count`, and restoring returns accumulated metric values.

- [ ] **Step 3: Run the new backend tests and confirm failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py \
  -k 'settings or seen or pending or visible or hidden or concurrent' -v
```

Expected: failures because the schema is not yet derived, snapshots are unfiltered, and the mutation endpoint does not exist.

- [ ] **Step 4: Implement immutable revisioned payload builders**

Under `_fleet_presentation_lock`, build complete Python dictionaries rather than exposing mutable settings sections. Use helpers with explicit locked naming, for example:

```python
def _next_fleet_revision_locked(self) -> int:
    self._fleet_presentation_revision += 1
    return self._fleet_presentation_revision


def _fleet_characters_locked(self, section: dict) -> list[dict]:
    snapshot = self._fleet_snapshot
    running = None if snapshot is None else {row.character for row in snapshot.rows}
    names = set(section.get("seen") or ())
    names.update(section.get("hidden") or ())
    names.update(self._fleet_pending_seen)
    if running is not None:
        names.update(running)
    hidden = set(section.get("hidden") or ())
    ordered = sorted(
        names,
        key=(lambda name: (name.casefold(), name))
        if running is None
        else (lambda name: (name not in running, name.casefold(), name)),
    )
    return [
        {
            "name": name,
            "running": None if running is None else name in running,
            "visible": name not in hidden,
        }
        for name in ordered
    ]


def _fleet_settings_payload_locked(self, section: dict, revision: int) -> dict:
    payload = {
        "enabled": bool(section.get("enabled")),
        "x": section.get("x"),
        "y": section.get("y"),
        "seen": list(section.get("seen") or ()),
        "hidden": list(section.get("hidden") or ()),
        "revision": revision,
    }
    payload["characters"] = self._fleet_characters_locked(section)
    return payload
```

Implement `_fleet_display_payload_locked(snapshot, section, revision)` with the
same copy-only rule: filter rows by the exact hidden-name set, retain global
health/error state, and return `running_count=len(snapshot.rows)`.

The character union is latest accepted rows + pending names + `seen` + `hidden`. Sort by `(not running, name.casefold(), name)` when running is known and by `(name.casefold(), name)` when it is unknown. Copy lists and nested dictionaries into payloads.

Filter display rows against an exact-name hidden set, preserve global health/error fields, and include unfiltered `running_count` plus `revision`.

- [ ] **Step 5: Implement sparse remembered-roster persistence**

On an accepted snapshot whose running-name signature changed:

1. update `_fleet_snapshot` and the signature under the presentation lock;
2. copy current and pending names, then release the lock;
3. construct current → pending → persisted tiers inside `settings.update()`;
4. write only when the normalized candidate differs;
5. after success, clear only pending names included in the saved candidate;
6. after `OSError`, retain pending names and log once for that transition;
7. reacquire the presentation lock to build any semantic main-page payload;
8. perform page pushes after releasing all locks.

Do not push main-page state when only DPS, EWAR, health detail, or metric error changed. Continue pushing every accepted display snapshot to the Fleet window.

- [ ] **Step 6: Implement the transactional visibility endpoint**

Inside one `settings.update()` block:

```python
section = dict(doc.get("fleet_bar") or {})
hidden = list(section.get("hidden") or [])
if not visible and name not in hidden:
    if len(hidden) >= 64:
        raise FleetVisibilityRefused("Show a hidden character before hiding another.")
    hidden.append(name)
elif visible:
    hidden = [item for item in hidden if item != name]
section["hidden"] = hidden
doc["fleet_bar"] = section
```

Use a private refusal exception that is caught outside the transaction, or compute the refusal result without raising after inspecting the live section. Ensure the no-op branch exits without invoking `settings.update()` by using a safe preliminary check, but repeat the decisive no-op/limit checks inside the transaction so concurrency cannot invalidate them.

After success, allocate one revision and build both authoritative payloads under the presentation lock. Push outside locks and return:

```python
{
    "applied": True,
    "persisted": True,
    "error": None,
    "state": settings_payload,
}
```

On `OSError` or limit refusal, return the same envelope with `applied=False`, `persisted=False`, an exact concise error, and freshly derived authoritative `state`.

- [ ] **Step 7: Run backend Fleet tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar.py tests/test_fleet_bar_settings.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit the backend feature**

```bash
git add wingman/ui/api.py tests/test_fleet_bar.py tests/test_fleet_bar_settings.py
git commit -m "feat: filter fleet characters persistently"
```

---

### Task 5: Add the Settings Character Disclosure

**Files:**
- Modify: `wingman/web/index.html:989-1005`
- Modify: `wingman/web/previews.js:1-56`
- Modify: `wingman/web/style.css` near existing Preview disclosure styles
- Modify: `wingman/web/dev.js:20, 1400-1410, 1520-1532`
- Modify: `tests/test_fleet_bar.py:380-440`
- Modify: `tests/test_page_conventions.py` only if the new generated-checkbox convention is not already covered

**Interfaces:**
- Consumes: revisioned `fleet_bar_settings()` and `onFleetBarState` payloads
- Calls: `set_fleet_bar_character_visible(name: str, visible: bool)`
- Preserves: existing `toggle_fleet_bar(enabled)` calls from both quick controls

- [ ] **Step 1: Write failing lexical contract tests**

Extend `tests/test_fleet_bar.py` with assertions that the source contains:

```python
assert 'id="fleetbar-characters"' in html
assert 'id="fleetbar-character-list"' in html
assert "set_fleet_bar_character_visible" in js
assert "document.addEventListener('wm:settings'" not in fleet_iife_source
assert "data-fleet-character" in js
assert "Show " in js and " in Fleet Bar" in js
assert "lastRevision" in js
assert "document.activeElement" in js
assert "document.body" in js
assert "fleet-characters:not([open])" in css
```

Extract only the first Fleet-control IIFE before asserting that its generic settings listener is absent; `previews.js` legitimately uses `wm:settings` later for Preview-specific settings.

- [ ] **Step 2: Run the lexical tests and confirm failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py \
  -k 'settings_and_status or character_controls or disclosure' -v
```

Expected: failures because the disclosure and character renderer do not exist.

- [ ] **Step 3: Add semantic markup**

Add beneath `fleetbar-enabled-status`:

```html
<details class="fleet-characters" id="fleetbar-characters">
  <summary>Characters</summary>
  <div class="fleet-character-list" id="fleetbar-character-list"></div>
  <p class="hint fleet-character-empty" id="fleetbar-characters-empty">
    Characters appear here after Wingman sees them running.
  </p>
  <p class="field-msg" id="fleetbar-characters-status" role="status" hidden></p>
</details>
```

Use one static disclosure so rerenders cannot reset its open state.

- [ ] **Step 4: Implement the revisioned keyed renderer**

Replace the first IIFE's Fleet state handling with these responsibilities:

```javascript
var lastRevision = -1;
var hydrated = false;
var pending = Object.create(null);

function accept(section) {
  var revision = Number(section && section.revision);
  if (!isFinite(revision) || revision < lastRevision) return false;
  lastRevision = revision;
  hydrated = true;
  return true;
}
```

- Remove the Fleet IIFE's `wm:settings` listener entirely.
- Hydrate only from `WM.send('fleet_bar_settings')`.
- Route both hydration and `onFleetBarState` through `accept()`.
- Keep the existing enable checkbox and status-strip button synchronized.
- Reconcile rows by `data-fleet-character`, updating and moving existing nodes rather than clearing the host.
- Render Running/Offline groups for boolean `running`, or one Known characters group when it is `null`.
- Build every checkbox in `.check` / `.box` order and set `aria-label` to `Show <name> in Fleet Bar`.
- Do not send a visibility mutation until `hydrated` is true.

- [ ] **Step 5: Implement pending, response ordering, and focus restoration**

For each character mutation:

```javascript
var token = (pending[name] || 0) + 1;
pending[name] = token;
var restoreFocus = document.activeElement === input;
input.disabled = true;
WM.send('set_fleet_bar_character_visible', name, input.checked).then(function (res) {
  if (pending[name] !== token) return;
  delete pending[name];
  if (res && res.state) render(res.state);
  var current = findCharacterInput(name);
  if (current) current.disabled = false;
  if (restoreFocus && document.activeElement === document.body && current) {
    current.focus();
  }
  renderCommitMessage(res);
});
```

Use the same terminal cleanup for bridge failure and stale responses. Never steal focus if it moved to another control. Keep status copy concise: refusal shows `error`; no message on success.

- [ ] **Step 6: Add restrained disclosure styles**

Follow the existing `.preview-group-manager` native-details pattern. Include:

```css
.fleet-characters > summary:focus-visible { /* shared focus token/rule */ }
.fleet-characters:not([open]) > .fleet-character-list,
.fleet-characters:not([open]) > .fleet-character-empty,
.fleet-characters:not([open]) > .field-msg { display: none; }
```

Use existing tokens only. Do not add cards inside the Fleet card, colored side borders, or a second scroll container. Keep group headings quieter than character names.

- [ ] **Step 7: Update browser development fixtures**

Extend `fleetBar` with `seen`, `hidden`, `revision`, and derived character fixtures containing at least one running visible, running hidden, and offline character. Implement the mutation stub transactionally enough to exercise success and the 64-name refusal, increment revision, call `onFleetBarState`, and return `{applied, persisted, error, state}`.

- [ ] **Step 8: Run Settings-page contract tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar.py tests/test_page_conventions.py \
  tests/test_settings_page.py tests/test_dev_harness.py -v
```

Expected: all pass.

- [ ] **Step 9: Commit the Settings UI**

```bash
git add wingman/web/index.html wingman/web/previews.js \
  wingman/web/style.css wingman/web/dev.js \
  tests/test_fleet_bar.py tests/test_page_conventions.py
git commit -m "feat: manage fleet character visibility"
```

---

### Task 6: Render Revisioned All-Hidden Fleet State

**Files:**
- Modify: `wingman/web/fleetbar.js:60-120`
- Modify: `tests/test_fleet_bar.py:420-440`

**Interfaces:**
- Consumes display payload: `{rows, running_count, revision, stream_health, metric_error}`
- Preserves: `window.onFleetSnapshot`, `fit_fleet_bar`, `fleet_bar_ready`

- [ ] **Step 1: Write failing payload/source tests**

Add Python payload assertions for unfiltered `running_count` and monotonic revision. Add lexical page checks:

```python
assert "running_count" in js
assert "lastRevision" in js
assert "All running characters are hidden." in js
assert js.index("All running characters are hidden.") < js.index("return fit();")
```

Retain the existing assertion that `fleetbar.html` has no buttons or inputs.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py \
  -k 'snapshot_payload or fleet_page or all_hidden or revision' -v
```

Expected: failures for the new payload fields and page branches.

- [ ] **Step 3: Reject stale display payloads and choose truthful empty copy**

In `fleetbar.js`:

```javascript
var lastRevision = -1;

function render(payload) {
  payload = payload || {};
  var revision = Number(payload.revision);
  if (isFinite(revision) && revision < lastRevision) {
    return Promise.resolve(null);
  }
  if (isFinite(revision)) lastRevision = revision;

  var rows = Array.isArray(payload.rows) ? payload.rows : [];
  var runningCount = Number(payload.running_count) || 0;
  empty.textContent = runningCount > 0
    ? 'All running characters are hidden.'
    : 'Waiting for EVE clients\u2026';
  // Existing row, health, and diagnostic rendering remains unchanged.
  return fit();
}
```

The stale branch must not refit an older payload. Every accepted state,
including both empty variants, still calls `fit()` so the native window shrinks
to its current content.

- [ ] **Step 4: Run all Fleet tests**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar.py tests/test_fleet_bar_settings.py \
  tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit the auxiliary-page behavior**

```bash
git add wingman/web/fleetbar.js tests/test_fleet_bar.py
git commit -m "feat: show all-hidden fleet state"
```

---

### Task 7: Document and Verify the Complete Feature

**Files:**
- Modify: `PRODUCT.md:167-177`
- Modify: `docs/smoke-checklist.md:2898-2975`
- Review: `docs/superpowers/specs/2026-09-04-fleet-character-visibility-design.md`
- Review: all files changed since `c5912cc`

**Interfaces:**
- Produces no new runtime interface.
- Verifies every acceptance criterion from the spec.

- [ ] **Step 1: Update durable product behavior**

Amend the Fleet Bar paragraph in `PRODUCT.md` to say that users may persistently
hide individual known characters from the bar in Settings, while collection and
Preview/Alert behavior remain unchanged. Keep the prose at product level; do
not copy schema or generation mechanics into `PRODUCT.md`.

- [ ] **Step 2: Extend the Windows smoke checklist**

Add concrete checks for:

- Running, Offline, and Fleet-off Known characters grouping.
- Hide/restore first, middle, and final visible rows.
- All-running-hidden copy and drag behavior.
- Hide during live DPS/tackle and restore without metric reset.
- Restart persistence and offline restoration.
- Keyboard focus after success, refusal, bridge failure, stale response, and row movement.
- Disclosure staying closed/open correctly in WebView2.
- Preview exclusion, alerts, and keybinds remaining independent.
- 100%, 125%, 150%, and 200% display scaling.

Do not mark these manual checks complete unless they are actually run on Windows.

- [ ] **Step 3: Run focused automated verification**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleet_bar.py \
  tests/test_fleet_bar_settings.py \
  tests/test_telemetry_coordinator.py \
  tests/test_fleet_metrics.py \
  tests/test_page_conventions.py \
  tests/test_settings_page.py \
  tests/test_dev_harness.py -v
```

Expected: all pass.

- [ ] **Step 4: Run repository-wide CI gates**

Run:

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: all tests pass with only the repository's documented platform skips; Ruff lint and format checks exit 0.

- [ ] **Step 5: Inspect the final diff and run scope checks**

Run:

```bash
git diff --check c5912cc..HEAD
git diff --stat c5912cc..HEAD
rg -n 'console\.log|window\.(confirm|prompt|alert)' \
  wingman tests PRODUCT.md docs/smoke-checklist.md
```

Inspect every changed file. Confirm there are no unrelated refactors, no new
public non-method `Api` attributes, no direct EVE-window move/resize behavior,
no generic `wm:settings` Fleet renderer, and no unsupported claim that the
Windows smoke pass was performed.

- [ ] **Step 6: Run the required polish and fresh verification workflow**

Load and run `polish-core --fix` against changes since `c5912cc`. Inspect every
edit it makes, rerun Steps 3 and 4, then use `change-explainer` for the reviewer
write-up. Do not claim the Windows smoke items passed unless they were exercised
on real Windows/WebView2.

- [ ] **Step 7: Commit documentation and final integration changes**

```bash
git add PRODUCT.md docs/smoke-checklist.md wingman tests
git commit -m "docs: cover fleet character visibility"
```

If polish changed source after the preceding task commits, include those
reviewed fixes in this final commit rather than amending already reviewed task
commits.
