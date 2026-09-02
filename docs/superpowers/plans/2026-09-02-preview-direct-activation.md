# Preview Direct Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace blocking attached-input preview switches with one direct foreground request followed by bounded, observe-only completion while preserving reliable fallback, latest-wins behavior, and exact outgoing-client minimization.

**Architecture:** `preview/window.py` owns direct and attached Win32 activation primitives and reports explicit activation states. `PreviewHost` owns the one pending switch, observes foreground state on its existing timer, rejects stale user intent, and invokes the attached fallback at most once after a monotonic deadline. Existing hotkey folding uses the pending target as its virtual cursor while Windows reports foreground `0`.

**Tech Stack:** Python 3.11+, ctypes Win32 APIs, pytest, Ruff; Windows/EVE smoke verification.

**Spec:** `docs/preview-direct-activation-design.md`

## Global Constraints

- Preview HWNDs, thumbnails, layered surfaces, and selection rendering remain owned by the preview thread.
- Never move, resize, maximize, or otherwise change an EVE client window's geometry.
- Do not change system-wide foreground policy or synthesize keyboard/mouse input.
- `GetForegroundWindow`, not `SetForegroundWindow`'s BOOL, remains the activation verdict.
- Every successful input-queue attachment has one reverse-order detach, including exceptions.
- Mark the target before asynchronously minimizing only the exact validated outgoing HWND.
- A newer request supersedes older pending intent; stale timer work cannot revive it.
- Preserve the existing 25 × 20ms minimized-target restore bound.
- Use a 250ms monotonic deadline for visible-target foreground observation.
- The unlocked left-click/left-drag gesture grammar is out of scope.

---

### Task 1: Production Direct and Attached Activation Primitives

**Files:**
- Modify: `wingman/preview/window.py`
- Test: `tests/test_preview_window.py`

**Interfaces:**
- Produces: `ActivationResult.PENDING_FOREGROUND`
- Produces: `activate(libs, hwnd) -> ActivationResult`, issuing one direct request for a visible non-foreground target
- Produces: `activate_attached(libs, hwnd, source_hwnd) -> ActivationResult`, bypassing the direct path
- Consumes: existing `win32.SW_RESTORE`, `AttachThreadInput`, `SetForegroundWindow`, `GetForegroundWindow`, and `SetFocus` bindings

- [ ] **Step 1: Keep behavioral tests and remove diagnostic-log assertions**

Retain tests equivalent to:

```python
def test_direct_activation_returns_activated_without_input_attachment(monkeypatch):
    calls = []
    libs = _activation_libs([FOREGROUND, TARGET], calls)
    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert not any(call[0] == "attach" for call in calls)
    assert not any(call[0] == "set_focus" for call in calls)


def test_direct_activation_returns_pending_for_transitional_zero(monkeypatch):
    calls = []
    libs = _activation_libs([FOREGROUND, 0], calls)
    assert window.activate(libs, TARGET) is window.ActivationResult.PENDING_FOREGROUND
    assert [call for call in calls if call[0] == "set_foreground"] == [
        ("set_foreground", TARGET)
    ]
    assert not any(call[0] == "attach" for call in calls)


def test_direct_activation_falls_back_when_source_remains_foreground(monkeypatch):
    calls = []
    libs = _activation_libs([FOREGROUND, FOREGROUND, TARGET], calls)
    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert [call[0] for call in calls].count("set_foreground") == 2
    assert ("set_focus", TARGET) in calls
```

Remove tests whose only contract is `[preview-switch-perf]` formatting.

- [ ] **Step 2: Run the focused tests and confirm diagnostic cleanup exposes missing production behavior**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_window.py::test_direct_activation_returns_activated_without_input_attachment \
  tests/test_preview_window.py::test_direct_activation_returns_pending_for_transitional_zero \
  tests/test_preview_window.py::test_direct_activation_falls_back_when_source_remains_foreground -q
```

Expected before the production cleanup is complete: at least one failure because behavior still depends on `WINGMAN_PREVIEW_DIRECT_ACTIVATE_PROBE`.

- [ ] **Step 3: Make direct-first behavior unconditional and keep fallback separate**

Implement this structure without timing instrumentation:

```python
class ActivationResult(Enum):
    ACTIVATED = auto()
    PENDING_RESTORE = auto()
    PENDING_FOREGROUND = auto()
    REFUSED = auto()


def activate(libs, hwnd):
    if libs.user32.IsIconic(hwnd):
        libs.user32.ShowWindowAsync(hwnd, win32.SW_RESTORE)
        return ActivationResult.PENDING_RESTORE

    source = libs.user32.GetForegroundWindow() or 0
    if source == hwnd:
        return ActivationResult.ACTIVATED

    libs.user32.SetForegroundWindow(hwnd)
    foreground = libs.user32.GetForegroundWindow() or 0
    if foreground == hwnd:
        return ActivationResult.ACTIVATED
    if foreground == 0:
        return ActivationResult.PENDING_FOREGROUND
    return activate_attached(libs, hwnd, source)
```

`activate_attached` must recheck `IsIconic`, attach distinct nonzero source/target thread IDs, call `SetFocus` only after observing target foreground, detach in reverse order in `finally`, and preserve the existing INFO refusal log.

- [ ] **Step 4: Run all preview-window tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_preview_window.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add wingman/preview/window.py tests/test_preview_window.py
git commit -m "fix: activate visible preview clients without blocking"
```

---

### Task 2: Observe-Only Pending Foreground State Machine

**Files:**
- Modify: `wingman/preview/host.py`
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: Task 1 `ActivationResult.PENDING_FOREGROUND` and `activate_attached`
- Produces: `_PendingSwitch.phase`, `_PendingSwitch.deadline`, and observe-only `_observe_pending_foreground`
- Preserves: existing `_arm_pending_activation`, `_clear_pending_activation`, and 25-turn restore timer behavior

- [ ] **Step 1: Write/retain tests for observation, stale cancellation, phase transitions, and deadline fallback**

Tests must assert:

```python
def test_pending_foreground_observation_issues_no_activation_calls(monkeypatch):
    h, libs, order = _switching_host(
        monkeypatch,
        foreground=0x1111,
        activation=host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    h._hwnd = 0x99
    monkeypatch.setattr(host.time, "monotonic", lambda: 10.0)
    h._activate_client(libs, h._clients["Bravo"])
    libs.user32._foreground = 0
    monkeypatch.setattr(
        host.window_mod,
        "activate",
        lambda *_args: pytest.fail("observer reissued activation"),
    )
    h._retry_pending_activation(libs)
    assert [entry for entry in order if entry[0] == "activate"] == [
        ("activate", 0x2222)
    ]


def test_different_foreground_cancels_stale_pending_switch(monkeypatch):
    h, libs, order = _switching_host(
        monkeypatch,
        foreground=0x1111,
        activation=host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    h._hwnd = 0x99
    monkeypatch.setattr(host.time, "monotonic", lambda: 10.0)
    h._activate_client(libs, h._clients["Bravo"])
    libs.user32._foreground = 0x9999
    h._retry_pending_activation(libs)
    assert h._pending_switch is None
    assert [entry for entry in order if entry[0] in {"ring", "show_async"}] == []


def test_deadline_uses_one_attached_fallback(monkeypatch):
    h, libs, order = _switching_host(
        monkeypatch,
        foreground=0x1111,
        activation=host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    h._hwnd = 0x99
    now = iter((10.0, 10.249, 10.250))
    monkeypatch.setattr(host.time, "monotonic", lambda: next(now))
    h._activate_client(libs, h._clients["Bravo"])
    attached = []
    monkeypatch.setattr(
        host.window_mod,
        "activate_attached",
        lambda _libs, hwnd, source: attached.append((hwnd, source))
        or host.window_mod.ActivationResult.ACTIVATED,
    )
    libs.user32._foreground = 0
    h._retry_pending_activation(libs)
    assert attached == []
    h._retry_pending_activation(libs)
    assert attached == [(0x2222, 0x1111)]
    assert ("ring", "Bravo", True) in order


def test_iconic_target_enters_restore_phase(monkeypatch):
    h, libs, _order = _switching_host(
        monkeypatch,
        foreground=0x1111,
        activation=host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    h._hwnd = 0x99
    monkeypatch.setattr(host.time, "monotonic", lambda: 10.0)
    h._activate_client(libs, h._clients["Bravo"])
    libs.user32.iconic = True
    monkeypatch.setattr(
        host.window_mod,
        "activate",
        lambda *_args: host.window_mod.ActivationResult.PENDING_RESTORE,
    )
    h._retry_pending_activation(libs)
    assert h._pending_switch.phase is host.window_mod.ActivationResult.PENDING_RESTORE
    assert h._pending_switch.attempts == 0
```

- [ ] **Step 2: Run the new state-machine tests and verify failures are behavior-specific**

Run the named tests with:

```bash
uv run --no-sync python -m pytest tests/test_preview_host.py -k \
  "pending_foreground or deadline or foreground_phase_after_restore" -q
```

Expected: failures for any missing stale cancellation, phase reset, deadline, or teardown behavior—not fixture or syntax errors.

- [ ] **Step 3: Implement explicit pending phase and monotonic deadline**

Use a frozen record with explicit state:

```python
@dataclass(frozen=True)
class _PendingSwitch:
    stable_key: str
    hwnd: int
    previous_key: str | None
    previous_hwnd: int
    minimize: bool
    attempts: int = 0
    phase: window_mod.ActivationResult | None = None
    deadline: float = 0.0
```

For `PENDING_FOREGROUND`, timer turns may call only `IsIconic` and `GetForegroundWindow` until deadline. Complete on target; remain pending on `0` or the unchanged source; cancel on another nonzero HWND. Use `time.monotonic() >= deadline`, never a timer-turn estimate.

At deadline, revalidate target stable key/HWND and the source key/HWND when source is an EVE client. Call `activate_attached` once. Handle `ACTIVATED`, `PENDING_RESTORE`, `REFUSED`, and exceptions explicitly; never classify `PENDING_RESTORE` as refusal.

- [ ] **Step 4: Run host and switching tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_host.py tests/test_preview_switching.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add wingman/preview/host.py tests/test_preview_host.py
git commit -m "fix: observe preview foreground transitions without blocking"
```

---

### Task 3: Preserve Latest-Wins Semantics During Foreground Zero

**Files:**
- Modify: `wingman/preview/host.py`
- Test: `tests/test_preview_host.py`
- Test: `tests/test_preview_cycle.py`

**Interfaces:**
- Consumes: Task 2 `_PendingSwitch`
- Produces: pending virtual cursor for `_on_hotkeys`
- Produces: inherited original outgoing key/HWND/minimize decision for superseding requests while live foreground is `0`

- [ ] **Step 1: Add failing rapid-supersession and cycle-anchor tests**

Add exact scenarios:

```python
def test_new_target_during_foreground_zero_keeps_original_outgoing_decision(
    monkeypatch,
):
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111)
    h._hwnd = 0x99
    h._clients["Carol"] = _FakeClient("Carol", hwnd=0x3333)
    h._windows["Carol"] = _RingWindow("Carol", order)
    results = iter(
        (
            host.window_mod.ActivationResult.PENDING_FOREGROUND,
            host.window_mod.ActivationResult.ACTIVATED,
        )
    )
    monkeypatch.setattr(host.window_mod, "activate", lambda *_args: next(results))
    h._activate_client(libs, h._clients["Bravo"])
    libs.user32._foreground = 0
    h._activate_client(libs, h._clients["Carol"])
    assert libs.user32.minimized == [0x1111]


def test_cycle_during_pending_foreground_anchors_on_pending_target(monkeypatch):
    h = host.PreviewHost(on_layout_changed=lambda *_args: None)
    h._clients = {
        "Alice": _FakeClient("Alice", hwnd=0x1111),
        "Bravo": _FakeClient("Bravo", hwnd=0x2222),
        "Carol": _FakeClient("Carol", hwnd=0x3333),
    }
    h._pending_switch = host._PendingSwitch(
        "Bravo", 0x2222, "Alice", 0x1111, False,
        phase=host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    user32 = _FakeUser32(foreground=0)
    activated = []
    monkeypatch.setattr(h, "_activate_client", lambda _libs, client: activated.append(client.stable_key))
    h._registered = {1: ("cycle", 1)}
    h._on_hotkeys(_FakeLibs(user32), [1])
    assert activated == ["Carol"]


def test_superseded_timer_resolves_only_current_target(monkeypatch):
    h, libs, order = _switching_host(monkeypatch, foreground=0x1111)
    h._hwnd = 0x99
    h._clients["Carol"] = _FakeClient("Carol", hwnd=0x3333)
    h._windows["Carol"] = _RingWindow("Carol", order)
    monkeypatch.setattr(
        host.window_mod,
        "activate",
        lambda *_args: host.window_mod.ActivationResult.PENDING_FOREGROUND,
    )
    h._activate_client(libs, h._clients["Bravo"])
    h._activate_client(libs, h._clients["Carol"])
    libs.user32._foreground = 0x3333
    h._retry_pending_activation(libs)
    assert h._selected_key == "Carol"
    assert not h._windows["Bravo"].selected
```

- [ ] **Step 2: Run the new tests and confirm they fail on lost pending context**

```bash
uv run --no-sync python -m pytest tests/test_preview_host.py \
  -k "foreground_zero or pending_target or superseded_timer" -q
```

Expected: failure because current code clears `_pending_switch` before deriving the new request's source/cursor.

- [ ] **Step 3: Carry pending context through resolution**

In `_on_hotkeys`, use the current pending target as `foreground_key` only when live foreground does not resolve to a client. Preserve normal real-foreground precedence.

In `_activate_client`, snapshot the pending record before clearing it. When live foreground is `0`, inherit `previous_key`, `previous_hwnd`, and `minimize` from that record for the new final target. If live foreground resolves normally, derive a fresh outgoing decision. Replacing pending state remains the sole generation switch; queued timer messages read only the current record.

- [ ] **Step 4: Run hotkey, cycle, host, and switching tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_host.py tests/test_preview_cycle.py \
  tests/test_preview_switching.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add wingman/preview/host.py tests/test_preview_host.py tests/test_preview_cycle.py
git commit -m "fix: preserve pending preview intent during rapid switches"
```

---

### Task 4: Remove Probe Instrumentation and Reconcile Documentation

**Files:**
- Modify: `wingman/preview/window.py`
- Modify: `wingman/preview/host.py`
- Modify: `tests/test_preview_window.py`
- Modify: `tests/test_preview_host.py`
- Modify: `docs/preview-direct-activation-design.md`
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Removes: `WINGMAN_PREVIEW_DIRECT_ACTIVATE_PROBE`, `DIRECT_ACTIVATE_PROBE`, `_switch_perf`, and all `[preview-switch-perf]` call sites
- Preserves: existing `WINGMAN_PREVIEW_PERF` drag-only diagnostics

- [ ] **Step 1: Remove all temporary switch tracing and diagnostic gating**

Delete switch-only trace calls around mouse input, activation, foreground hooks, alerts, selection, and outline rendering. Remove temporary `_click_started_at` state. Restore `WINGMAN_PREVIEW_PERF` to drag-only behavior. Direct activation remains unconditional.

- [ ] **Step 2: Prove no diagnostic artifacts remain**

```bash
rg -n "DIRECT_ACTIVATE_PROBE|WINGMAN_PREVIEW_DIRECT_ACTIVATE_PROBE|preview-switch-perf|_switch_perf|foreground_observation" \
  wingman tests docs --glob '!docs/preview-direct-activation-design.md'
```

Expected: no output. The design may retain historical evidence terms, but no executable diagnostic names.

- [ ] **Step 3: Update the smoke checklist with production acceptance cases**

Add explicit checks for:

- minimization off, locked and unlocked clicks;
- one direct request followed by prompt foreground/outline;
- rapid pending supersession and cycle anchoring;
- immediate keyboard/mouse input and held push-to-talk;
- minimized targets;
- browser/Search retained foreground;
- teardown with pending foreground;
- no late fallback focus steal.

- [ ] **Step 4: Run focused tests and lexical guards**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_window.py tests/test_preview_host.py \
  tests/test_preview_cycle.py tests/test_preview_switching.py \
  tests/test_preview_wiring.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add wingman/preview/window.py wingman/preview/host.py \
  tests/test_preview_window.py tests/test_preview_host.py \
  docs/preview-direct-activation-design.md docs/smoke-checklist.md
git commit -m "docs: lock preview activation performance checks"
```

---

### Task 5: Polish, Full Verification, and Windows Acceptance

**Files:**
- Inspect: all files changed since `20f2939`
- Modify only high-confidence findings in the files already in scope

**Interfaces:**
- Produces: review-ready production diff with no temporary probe code

- [ ] **Step 1: Run `polish-core --fix` against the branch diff**

Inspect every applied edit, especially activation exception paths, phase transitions, stale timer behavior, and comments that describe measured Win32 behavior.

- [ ] **Step 2: Run full Linux verification**

```bash
uv run --no-sync python -m pytest tests/ -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: all tests and checks pass.

- [ ] **Step 3: Run focused Windows tests**

```powershell
cd C:\dev\flygd-wingman-preview-switch-trace
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv run --no-sync python -m pytest tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_cycle.py tests/test_preview_switching.py tests/test_preview_wiring.py -q
```

Expected: all pass, including Windows ctypes binding checks.

- [ ] **Step 4: Perform Windows/EVE smoke acceptance**

Exercise every Windows verification item in `docs/preview-direct-activation-design.md`, with particular attention to minimization off, immediate input, rapid supersession, external-app cancellation, minimized targets, and exit with a pending transition.

Expected: switches complete promptly; no stale focus steal, late minimize, wrong outline, swallowed input, or leaked input-queue attachment.

- [ ] **Step 5: Inspect final scope and create the completion commit**

```bash
git status --short
git diff --stat 20f2939..HEAD
git diff --check 20f2939..HEAD
git log --oneline 20f2939..HEAD
```

Confirm the final branch contains the production activation behavior, behavioral regression tests, reviewed design, and smoke checklist only—no diagnostic flag or trace implementation.
