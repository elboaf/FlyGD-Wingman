# Floating Fleet DPS and EWAR Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent, always-on-top fleet bar that shows every running logged-in EVE character's fixed-window outgoing DPS and attributable incoming tackle without requiring preview thumbnails or Alerts.

**Architecture:** Extract one shared client-discovery service and one shared gamelog stream, serialize their generation-bearing events through a telemetry coordinator, and keep Preview rendering, Alert policy, and Fleet Metrics as independent consumers. A dedicated controller owns a hidden-until-fitted fleet WebView and receives targeted snapshots without extending the main bridge's generic fan-out.

**Tech Stack:** Python 3.11+, ctypes/Win32, threading and immutable dataclasses, pywebview 6.2.1, plain HTML/CSS/ES5 JavaScript, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-03-floating-fleet-dps-ewar-bar-design.md`

## Global Constraints

- Windows only; all pure logic and injected Win32 seams must remain importable and testable on Linux.
- Keep `pywebview==6.2.1`; upgrading it requires a separate full manual smoke pass.
- Add no runtime dependency, framework, build step, bundler, telemetry, or gameplay automation.
- Never move or resize a real EVE client window; only Wingman's own auxiliary window may be moved or resized.
- The fleet bar works while preview thumbnails and Alerts are disabled.
- Outgoing DPS is `sum(damage in (now - 10s, now]) / 10`, including NPC and player damage, rounded to a whole number.
- EVE line timestamps are timezone-aware UTC; malformed timestamps may suppress metrics but must not suppress existing Alerts.
- Incoming tackle displays the combined `SCRAM/POINT` label for only the unexpired portion of eight seconds from event time.
- Do not add `JAM` or any ECM parser unless a real successful-jam fixture proves success and target attribution. No such fixture exists at plan creation, so the planned release omits JAM.
- A real anonymized outgoing direct-damage fixture and drone-damage fixture are implementation gates; do not invent log markup.
- Keep all non-method `Api` attributes underscore-prefixed.
- Auxiliary WebViews must be destroyed before the main WebView; do not attach pywebview `shown` or `moved` handlers.
- Settings use immediate per-field persistence and standard `{applied, persisted, error}` outcomes. Checkboxes use `.check` and `.box` markup.
- The fleet page is not covered by a JS runtime test. Add lexical guards and complete the Windows smoke checklist before release.
- Every task ends with its focused tests passing and a commit. Run the full suite, Ruff check, and Ruff format check after the final task.

## File and Responsibility Map

### New production files

- `wingman/telemetry/__init__.py`: package boundary and intentionally small public exports.
- `wingman/telemetry/model.py`: immutable client, source, fact, envelope, health, and fleet snapshot types.
- `wingman/telemetry/parsing.py`: pure UTC timestamp and combat-line parsing; compatibility input for Alerts.
- `wingman/telemetry/gamelogs.py`: one source-aware gamelog cursor, lifecycle publication, health, and replay prevention.
- `wingman/telemetry/clients.py`: one scan context, stable client-session identities, generations, subscriptions, and immediate scan requests.
- `wingman/telemetry/metrics.py`: thread-free ten-second DPS and tackle state.
- `wingman/telemetry/coordinator.py`: runtime predicates, global telemetry sequencing, serialized delivery, one-second snapshots, and consumer attachment.
- `wingman/ui/fleetbar_geometry.py`: pure anchor/clamp logic plus the only monitor-work-area Win32 seam.
- `wingman/ui/fleetbar.py`: auxiliary-window lifecycle, readiness token, fit/reveal, targeted pushes, and position persistence.
- `wingman/web/fleetbar.html`: standalone fixed-column page and drag surface.
- `wingman/web/fleetbar.css`: fleet-page layout using existing root tokens.
- `wingman/web/fleetbar.js`: bridge readiness, rendering, fitting, retries, and drag-position save.

### Existing production files

- `wingman/settings.py`: independent `fleet_bar` defaults, validation, normalization, and save projection.
- `wingman/preview/discovery.py`: retained raw Win32 enumerator consumed by shared discovery.
- `wingman/preview/host.py`: pump-side application of external roster snapshots and preview reconciliation without discovery I/O.
- `wingman/preview/win32.py`: one new host message for pending roster application.
- `wingman/alerts/patterns.py`: compatibility adapter over pure telemetry parsing; retain NPC policy helpers.
- `wingman/alerts/service.py`: alert policy separated from its old private polling worker, then attached to shared facts.
- `wingman/ui/api.py`: fleet state/toggle/ready/fit/position endpoints and runtime reconciliation.
- `wingman/__main__.py`: construct coordinator/controller, restore after main-page show, and enforce shutdown order.
- `wingman/web/app.js`: allowlist `onFleetBarState` for the main page only.
- `wingman/web/previews.js`: Settings > Previews controls and state rendering.
- `wingman/web/index.html`: Previews card and adjacent status-strip button.
- `wingman/web/dev.js`: fleet endpoint doubles and representative state.
- `wingman/web/style.css`: quick-button fit/yield treatment only after real 839/840 measurement.
- `pyproject.toml`: explicitly package `wingman.telemetry`.
- `.github/actions/build-installer/action.yml`: assert frozen fleet web assets.
- `docs/smoke-checklist.md`: fleet matrix and correction of adjacent stale sig-bar checks.

### New focused tests

- `tests/test_fleet_bar_settings.py`
- `tests/test_telemetry_parsing.py`
- `tests/test_telemetry_gamelogs.py`
- `tests/test_client_discovery.py`
- `tests/test_fleet_metrics.py`
- `tests/test_telemetry_coordinator.py`
- `tests/test_fleet_bar_geometry.py`
- `tests/test_fleet_bar.py`
- `tests/test_fleet_bar_page.py`

Existing alert, preview, startup, bridge, settings, packaging, and smoke-source tests remain regression gates.

---

### Task 1: Add the Independent Fleet-Bar Settings Schema

**Files:**
- Modify: `wingman/settings.py:289-384, 675-789`
- Modify: `wingman/ui/api.py:2696-2729`
- Create: `tests/test_fleet_bar_settings.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_settings_eve_gate.py`

**Interfaces:**
- Produces: `settings._fleet_bar_defaults() -> dict`
- Produces: `settings.validated_fleet_bar(raw) -> dict`
- Produces persisted shape: `{"enabled": bool, "x": int | None, "y": int | None}`
- Keeps runtime behavior unchanged because the default is disabled.

- [ ] **Step 1: Write failing default, validation, isolation, and round-trip tests**

```python
# tests/test_fleet_bar_settings.py
from wingman import settings


def test_fleet_bar_defaults_off_with_no_position():
    assert settings.load()["fleet_bar"] == {
        "enabled": False,
        "x": None,
        "y": None,
    }


def test_fleet_bar_validation_rejects_bool_coordinates():
    value = settings.validated_fleet_bar(
        {"enabled": True, "x": True, "y": "12"}
    )
    assert value == {"enabled": True, "x": None, "y": None}


def test_fleet_bar_defaults_are_not_shared():
    first = settings._fresh_defaults()
    second = settings._fresh_defaults()
    first["fleet_bar"]["enabled"] = True
    assert second["fleet_bar"]["enabled"] is False
```

Extend the existing save/reload test in `tests/test_settings.py` with `fleet_bar={"enabled": True, "x": -320, "y": 48}` and assert exact round-trip preservation.

- [ ] **Step 2: Run the focused tests and verify the schema is absent**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_settings.py tests/test_settings.py -v
```

Expected: collection or assertions fail because `_fleet_bar_defaults`, `validated_fleet_bar`, and the top-level key do not exist.

- [ ] **Step 3: Implement defaults and normalization**

Add beside `_sig_bar_defaults()`:

```python
def _fleet_bar_defaults() -> dict:
    # Off by default: this starts shared discovery/log work and creates an
    # additional WebView2 host only after the user asks for it.
    return {"enabled": False, "x": None, "y": None}


def validated_fleet_bar(raw) -> dict:
    section = _fleet_bar_defaults()
    if not isinstance(raw, dict):
        return section
    if isinstance(raw.get("enabled"), bool):
        section["enabled"] = raw["enabled"]
    for key in ("x", "y"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            section[key] = value
    return section
```

Add `fleet_bar` to `DEFAULTS`, rebuild it in `_fresh_defaults()`, and assign `data["fleet_bar"] = validated_fleet_bar(raw.get("fleet_bar"))` in `_normalize()`.

- [ ] **Step 4: Extend the EVE-tools visibility guard test, then implementation**

Add a case in `tests/test_settings_eve_gate.py` setting `state.settings["fleet_bar"]["enabled"] = True`, call `api.set_show_eve_tools(False)`, and assert refusal plus unchanged visibility. Update `Api.set_show_eve_tools()` so Bookmarks, Previews, or Fleet Bar being enabled preserves access to the controls that can turn them off.

- [ ] **Step 5: Run focused settings and API tests**

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_settings.py tests/test_settings.py tests/test_settings_eve_gate.py tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add wingman/settings.py wingman/ui/api.py tests/test_fleet_bar_settings.py tests/test_settings.py tests/test_settings_eve_gate.py
git commit -m "feat: add fleet bar settings schema"
```

---

### Task 2: Introduce Immutable Telemetry Types and Pure Combat Parsing

**Files:**
- Create: `wingman/telemetry/__init__.py`
- Create: `wingman/telemetry/model.py`
- Create: `wingman/telemetry/parsing.py`
- Modify: `wingman/alerts/patterns.py:13-331`
- Create: `tests/test_telemetry_parsing.py`
- Create: `tests/fixtures/gamelogs/outgoing_direct.txt`
- Create: `tests/fixtures/gamelogs/outgoing_drone.txt`
- Modify: `tests/test_alerts_patterns.py`

**Interfaces:**
- Produces immutable `ClientSessionId`, `RosterClient`, `RosterSnapshot`, `SourceId`, `SourceLifecycle`, `ParsedFact`, `CombatFact`, `TelemetryEnvelope`, `StreamHealth`, `FleetRow`, and `FleetSnapshot`.
- Produces: `parse_timestamp(line: str) -> datetime.datetime | None`
- Produces: `parse_line(line: str, character: str) -> ParsedLine`
- Preserves: `alerts.patterns.match_line(line, character) -> Match | None`
- Does not produce any ECM/JAM symbol without a real fixture.

- [ ] **Step 1: Acquire and anonymize the required real outgoing fixtures**

Search the configured EVE Gamelogs folder for outgoing cyan combat lines and preserve the complete timestamp, color/font markup, amount formatting, direction, target shape, weapon text, and line ending. Replace only character, corporation, target, and ship names with the fixed fictional vocabulary `Aiga Otsolen`, `Mara Veld`, `OXWLD`, and `Sleepless Patroller`. Commit one direct-weapon line and one player-drone line as the two fixture files above.

If either shape is unavailable, stop this task and request a sample. Do not synthesize markup from the linked C# regex or from incoming fixtures. Inspect the fixture diff and verify every proper noun is from that fixed fictional vocabulary:

```bash
git diff -- tests/fixtures/gamelogs/outgoing_direct.txt tests/fixtures/gamelogs/outgoing_drone.txt
```

- [ ] **Step 2: Write failing model and timestamp tests**

```python
# tests/test_telemetry_parsing.py
import datetime

from wingman.telemetry import parsing

UTC = datetime.UTC


def test_eve_timestamp_is_aware_utc():
    line = "[ 2026.09.03 12:34:56 ] (combat) body"
    assert parsing.parse_timestamp(line) == datetime.datetime(
        2026, 9, 3, 12, 34, 56, tzinfo=UTC
    )


def test_timestamp_requires_fixed_numeric_fields():
    assert parsing.parse_timestamp("[ 2026.9.03 12:34:56 ] (combat) body") is None


def test_invalid_timestamp_does_not_discard_alert_body_fact():
    parsed = parsing.parse_line(
        "[ 2026.02.30 12:34:56 ] (combat) Sleepless Patroller misses you",
        "Aiga Otsolen",
    )
    assert parsed.occurred_at is None
    assert parsed.timestamp_error
    assert [fact.kind for fact in parsed.facts] == ["incoming_miss"]
```

Add fixture-driven tests asserting outgoing amount, `kind == "outgoing_damage"`, and target/source parsing for both direct and drone lines. Retain all existing tackle ownership tests through the compatibility adapter.

- [ ] **Step 3: Run parser tests and verify imports fail**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_parsing.py tests/test_alerts_patterns.py -v
```

Expected: FAIL because `wingman.telemetry` does not exist.

- [ ] **Step 4: Implement the frozen telemetry model**

Define focused frozen dataclasses in `model.py`:

```python
@dataclass(frozen=True)
class ClientSessionId:
    hwnd: int
    pid: int
    character: str
    first_seen_generation: int


@dataclass(frozen=True)
class SourceId:
    normalized_path: str
    session_start_utc: datetime.datetime


@dataclass(frozen=True)
class CombatFact:
    character: str
    source_generation: int
    source_id: SourceId
    occurred_at: datetime.datetime | None
    kind: str
    amount: int | None = None
    source: str = ""
```

Add the remaining types named in **Interfaces**. `FleetRow.dps` is `int | None`, where `None` means unavailable and `0` means observed zero. `TelemetryEnvelope[T]` carries `sequence: int` and `payload: T`. `FleetSnapshot` carries `metric_error: str | None` separately from `StreamHealth`, so future-timestamp rejection can be reported as fleet telemetry health without pretending the file reader failed.

- [ ] **Step 5: Implement parsing and the alert adapter**

Use one anchored timestamp regex for `[ YYYY.MM.DD HH:MM:SS ]`, construct with `tzinfo=datetime.UTC`, and return `None` plus a diagnostic string for malformed dates. Move or delegate existing markup, tackle target, source extraction, and miss logic rather than copying it.

`parse_line()` emits pre-policy `ParsedFact` values for incoming damage, misses, tackle, decloak, and verified outgoing damage. `alerts.patterns.match_line()` delegates to `parse_line()` and maps only alert-relevant facts back to existing `Match` values. Keep `is_likely_npc()` in Alerts because it is policy, not parsing.

- [ ] **Step 6: Run parser and all alert pattern tests**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_parsing.py tests/test_alerts_patterns.py tests/test_alerts_tailer.py -v
```

Expected: PASS with every existing alert shape unchanged. Confirm no ECM implementation exists:

```bash
! rg -n "incoming_jam|JAM|ecm" wingman/telemetry tests/test_telemetry_*.py
```

- [ ] **Step 7: Commit**

```bash
git add wingman/telemetry wingman/alerts/patterns.py tests/test_telemetry_parsing.py tests/test_alerts_patterns.py tests/fixtures/gamelogs/outgoing_direct.txt tests/fixtures/gamelogs/outgoing_drone.txt
git commit -m "feat: parse timestamped combat telemetry"
```

---

### Task 3: Separate Alert Policy Without Changing Behavior

**Files:**
- Modify: `wingman/alerts/service.py:32-327`
- Modify: `tests/test_alerts_service.py`
- Modify: `tests/test_alerts_wiring.py`

**Interfaces:**
- Produces: `AlertPolicy.handle(events, now: float) -> list[tuple[str, str, str]]`
- `AlertService` continues to own and run its existing `tailer.Tailer` in this task.
- Preserves exact event enablement, PvE filtering, cooldowns, volume, foreground sound suppression, persistence, and preview dispatch.

- [ ] **Step 1: Add failing extraction tests**

Instantiate `AlertPolicy` directly with the existing config, sound, focused-character, and dispatch fakes. Port one test each for cooldown separation, PvE filtering, foreground sound suppression, and persistent-versus-timed dispatch. Keep the existing `AlertService._handle()` tests until the compatibility delegation exists.

- [ ] **Step 2: Run the focused tests and verify `AlertPolicy` is absent**

```bash
uv run --no-sync python -m pytest tests/test_alerts_service.py tests/test_alerts_wiring.py -v
```

Expected: FAIL on the missing class/import.

- [ ] **Step 3: Extract policy state and delegate**

Move `_cooldowns`, `_focused_character()`, and `_handle()` decision logic into `AlertPolicy`. Give it only callables and pure event input. Keep `AlertService._handle()` as:

```python
def _handle(self, events, now):
    return self._policy.handle(events, now)
```

Do not change lifecycle, thread, folder, Tailer, health, or event shapes in this task.

- [ ] **Step 4: Run all alert tests**

```bash
uv run --no-sync python -m pytest tests/test_alerts_service.py tests/test_alerts_wiring.py tests/test_alerts_volume.py tests/test_preview_alertframes.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wingman/alerts/service.py tests/test_alerts_service.py tests/test_alerts_wiring.py
git commit -m "refactor: separate alert policy from polling"
```

---

### Task 4: Build the Source-Aware Shared Gamelog Stream

**Files:**
- Create: `wingman/telemetry/gamelogs.py`
- Create: `tests/test_telemetry_gamelogs.py`
- Reference regression behavior: `wingman/alerts/tailer.py`
- Reference regression tests: `tests/test_alerts_tailer.py`

**Interfaces:**
- Produces: `GameLogStream.subscribe(callback) -> Callable[[], None]`
- Produces: `GameLogStream.start(folder: Path) -> None`
- Produces: `GameLogStream.request_source(character: str) -> None`
- Produces: `GameLogStream.stop(timeout: float = 3.0) -> None`
- Produces: `GameLogStream.health() -> StreamHealth`
- Publishes `SourceLifecycle` before `CombatFact` for every source generation.

- [ ] **Step 1: Write failing source lifecycle and ordering tests**

Use temporary fixture logs and injected clock/thread seams. Assert:

```python
stream.scan_once(now_utc)
events = received.copy()
assert isinstance(events[0], SourceLifecycle)
assert events[0].active is True
assert all(fact.source_generation == events[0].stream_generation for fact in events[1:])
assert all(fact.source_id == events[0].source_id for fact in events[1:])
```

Cover one active source per character, first-scan EOF baseline, a genuinely new file read from zero, partial lines, rotation, and source retirement before replacement activation.

- [ ] **Step 2: Add replay and failure tests**

Test folder disappearance retires all sources and clears cursors. On folder recovery, files already present baseline at EOF and do not replay. Test cap eviction/reappearance and transient header/stat failure the same way. Assert one unreadable source does not suppress another, successful polling clears `last_error`, and subscriber exceptions do not stop later subscribers.

- [ ] **Step 3: Run tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_gamelogs.py tests/test_alerts_tailer.py -v
```

Expected: FAIL because `GameLogStream` is absent.

- [ ] **Step 4: Implement cursor and source generation state**

Port the proven selection rules from `Tailer`, but track retired source identities and whether the current folder generation has been baselined. `SourceId` combines normalized path and UTC header session start. Increment stream generation on source activation/replacement, dispatch lifecycle first, then wrap `ParsedFact` values as `CombatFact` with the exact generation and source identity.

Do not delete or production-wire `alerts/tailer.py` yet.

- [ ] **Step 5: Implement lifecycle and health**

Use one non-daemon worker, one stop event per generation, the existing one-second poll/five-second rescan cadence, bounded join, and callback isolation. Health states distinguish stopped, missing folder, running, stale/error, and active characters. Clear transient errors after a successful complete poll.

- [ ] **Step 6: Run stream and legacy tailer tests**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_gamelogs.py tests/test_alerts_tailer.py tests/test_combatlog.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add wingman/telemetry/gamelogs.py tests/test_telemetry_gamelogs.py
git commit -m "feat: add shared gamelog stream"
```

---

### Task 5: Build Shared Client Discovery With Stable Sessions

**Files:**
- Create: `wingman/telemetry/clients.py`
- Create: `tests/test_client_discovery.py`
- Reference unchanged enumerator: `wingman/preview/discovery.py`

**Interfaces:**
- Produces: `ClientDiscovery.subscribe(callback) -> Callable[[], None]`
- Produces: `start()`, `request_scan()`, `stop(timeout=5.0)`, and `snapshot()`.
- Consumes: `preview.discovery.list_clients() -> list[Client]`.
- Publishes `RosterSnapshot` with monotonically increasing generations and stable `first_seen_generation`.

- [ ] **Step 1: Write failing stable-session tests**

Use an injected enumerator sequence. Assert an unchanged `(hwnd, pid, character)` keeps the same session across generations; disappearance/return, HWND change, PID change, or generic-title transition creates a new session. Unnamed clients remain in the snapshot with `session is None`.

- [ ] **Step 2: Write fan-out, request, and isolation tests**

Assert one enumeration result reaches multiple subscribers, one failing callback does not block another, `request_scan()` wakes the owned context immediately, and preview exclusion settings are never consulted.

- [ ] **Step 3: Run tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_client_discovery.py tests/test_preview_discovery.py -v
```

Expected: FAIL because `ClientDiscovery` is absent.

- [ ] **Step 4: Implement the service**

Keep raw Win32 enumeration in `preview.discovery`. Own one worker context and condition/event wake-up. Increment the roster generation after every completed scan, retain a map from continuous `(hwnd, pid, character)` tuples to their first-seen generation, and prune it only when a tuple disappears.

- [ ] **Step 5: Run discovery tests**

```bash
uv run --no-sync python -m pytest tests/test_client_discovery.py tests/test_preview_discovery.py tests/test_evewindows.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add wingman/telemetry/clients.py tests/test_client_discovery.py
git commit -m "feat: add shared EVE client discovery"
```

---

### Task 6: Make PreviewHost Consume Generation-Bearing Rosters on Its Pump

**Files:**
- Modify: `wingman/preview/win32.py`
- Modify: `wingman/preview/host.py:190-476, 710-1003`
- Modify: `tests/test_preview_host.py`
- Modify: `tests/test_preview_wiring.py`

**Interfaces:**
- Produces: `PreviewHost.apply_roster(snapshot: RosterSnapshot) -> None`, safe from any thread.
- Produces pump-only: `PreviewHost._apply_pending_roster(libs) -> None`.
- Temporarily preserves `_sweep()` as a compatibility wrapper in this task.

- [ ] **Step 1: Write failing pump and stale-generation tests**

Add a fake message-post seam and assert `apply_roster()` stores only the newest pending snapshot and posts `WM_APP_ROSTER`. Drive `_host_proc()` and assert reconciliation executes on the test pump. Apply generation 4 then generation 3 and assert generation 3 cannot remove or recreate previews.

Update the existing contiguous custom-message/count invariant for the new `WM_APP_ROSTER` constant.

- [ ] **Step 2: Run focused host tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_preview_host.py tests/test_preview_wiring.py -v
```

Expected: FAIL on missing message and methods.

- [ ] **Step 3: Split discovery from reconciliation**

Extract the body of `_sweep()` after `list_clients()` into a pump-only reconciliation method consuming `RosterSnapshot.clients`. Preserve identity continuity, size sampling, exclusion, window creation/destruction, callbacks, selection, and visibility in their existing order.

`apply_roster()` may run on any thread but only swaps the pending immutable snapshot under a small lock and posts `WM_APP_ROSTER`. `_apply_pending_roster()` runs from `_host_proc()`, rejects `generation <= _last_roster_generation`, and calls reconciliation.

- [ ] **Step 4: Keep an intermediate compatibility wrapper**

For this commit, let `_sweep()` obtain raw clients, adapt them to one snapshot, and call the new pump-only method. Leave the current timer and foreground request path intact so production behavior has not migrated yet.

- [ ] **Step 5: Run preview regression tests**

```bash
uv run --no-sync python -m pytest tests/test_preview_host.py tests/test_preview_wiring.py tests/test_preview_cycle.py tests/test_preview_visibility.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add wingman/preview/win32.py wingman/preview/host.py tests/test_preview_host.py tests/test_preview_wiring.py
git commit -m "refactor: apply preview rosters on the host pump"
```

---

### Task 7: Implement Thread-Free Fleet Metrics

**Files:**
- Create: `wingman/telemetry/metrics.py`
- Create: `tests/test_fleet_metrics.py`

**Interfaces:**
- Consumes: `TelemetryEnvelope[RosterSnapshot | SourceLifecycle | CombatFact]`.
- Produces: `FleetMetrics.consume(envelope) -> None`.
- Produces: `FleetMetrics.snapshot(sequence: int, health: StreamHealth) -> FleetSnapshot`.
- Uses injected `monotonic()` and aware-UTC `utcnow()`.

- [ ] **Step 1: Write failing roster/source binding tests**

Assert a row starts `dps is None` and `no_log is True`; a source lifecycle envelope binds only when its telemetry sequence is greater than the session's first roster sequence. Assert stale roster/source envelopes do not roll state backward, and a changed client session or source generation clears damage and tackle.

- [ ] **Step 2: Write failing fixed-window DPS tests**

Use an injected UTC clock and exact event times. Assert:

```python
# 105 damage in the open/closed 10-second window => 10.5 => 11 half-up.
assert row.dps == 11
```

Cover exactly `now - 10s` excluded, exactly `now` included, fixed denominator ten, one-second snapshot decay, `0` versus `None`, damage more than ten seconds old rejected, up to two seconds future clamped, and more than two seconds future rejected with `FleetSnapshot.metric_error` populated. A later accepted timestamp clears that transient metric diagnostic.

Use `Decimal(...).quantize(..., ROUND_HALF_UP)` or an integer-equivalent helper; do not use Python banker's `round()`.

- [ ] **Step 3: Write failing tackle deadline tests**

Assert remaining lifetime is `occurred_at + 8s - utcnow`, non-positive events are ignored, future-clamped events never exceed eight seconds, accepted refreshes move the monotonic deadline, and expiry occurs without another fact.

- [ ] **Step 4: Run tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_fleet_metrics.py -v
```

Expected: FAIL because `FleetMetrics` is absent.

- [ ] **Step 5: Implement metrics state and snapshots**

Keep a private mutable state per active `ClientSessionId`; no thread or lock belongs in this module. Require fact sequence greater than bound lifecycle sequence and exact source identity/generation match. Prune the deque on consume and snapshot. Emit named rows only, sorted by `character.casefold()`.

Only add the `SCRAM/POINT` EWAR value. Do not leave dormant JAM constants or branches.

- [ ] **Step 6: Run metric tests**

```bash
uv run --no-sync python -m pytest tests/test_fleet_metrics.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add wingman/telemetry/metrics.py tests/test_fleet_metrics.py
git commit -m "feat: calculate fleet DPS and tackle state"
```

---

### Task 8: Add the Serialized Telemetry Coordinator

**Files:**
- Create: `wingman/telemetry/coordinator.py`
- Create: `tests/test_telemetry_coordinator.py`

**Interfaces:**
- Consumes: settings callables, `ClientDiscovery`, `GameLogStream`, `FleetMetrics`, optional Preview and Alert consumers.
- Produces: `reconcile()`, `request_discovery()`, `snapshot()`, `subscribe_fleet(callback)`, and `stop()`.
- Owns the sole cross-stream telemetry sequence and dispatcher queue/thread.

- [ ] **Step 1: Write failing predicate tests**

Table-test exact booleans:

```python
@pytest.mark.parametrize(
    "preview,fleet,alerts,want_discovery,want_stream,want_policy",
    [
        (False, False, False, False, False, False),
        (False, True, False, True, True, False),
        (False, False, True, False, False, False),
        (True, False, False, True, False, False),
        (True, False, True, True, True, True),
    ],
)
def test_runtime_predicates(...): ...
```

- [ ] **Step 2: Write failing sequencing and source-republication tests**

Assert coordinator envelope sequences strictly increase across interleaved roster/source/fact inputs. After a newly identified client session is queued, assert `GameLogStream.request_source(character)` runs and the resulting lifecycle envelope follows the roster envelope. Assert a callback failure cannot stop Preview, Alert, or fleet delivery.

- [ ] **Step 3: Write failing lifecycle and cadence tests**

Assert first/last consumer starts/stops each infrastructure service exactly once, repeated `reconcile()` is idempotent, and a one-second dispatcher timeout publishes a fresh decayed `FleetSnapshot` without a new fact.

- [ ] **Step 4: Run tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py -v
```

Expected: FAIL because `TelemetryCoordinator` is absent.

- [ ] **Step 5: Implement the coordinator**

Use one queue and one non-daemon dispatcher thread. Stamp payloads only on that thread. Feed Fleet Metrics before publishing a complete snapshot. Attach Alert policy only under `preview_enabled and alerts_enabled`. Post roster snapshots through `PreviewHost.apply_roster()` only while Preview is enabled. Catch and log each consumer failure independently.

All settings access remains callable-based; never retain nested settings dictionaries because normalization replaces them.

- [ ] **Step 6: Run coordinator tests**

```bash
uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py tests/test_fleet_metrics.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py
git commit -m "feat: coordinate shared EVE telemetry"
```

---

### Task 9: Migrate Preview and Alerts to Shared Infrastructure

**Files:**
- Modify: `wingman/preview/host.py:419-476, 710-1003`
- Modify: `wingman/alerts/service.py:32-239`
- Modify: `wingman/ui/api.py:2869-3077, 4089-4265`
- Modify: `wingman/__main__.py:355-596, 656-864`
- Modify: `tests/test_preview_host.py`
- Modify: `tests/test_alerts_service.py`
- Modify: `tests/test_alerts_wiring.py`
- Modify: `tests/test_preview_wiring.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes coordinator and extracted `AlertPolicy`.
- Removes production ownership of direct `Tailer` polling from `AlertService`.
- Removes production ownership of the 700 ms discovery timer/direct `list_clients()` call from `PreviewHost`.
- Preserves compatibility-facing Alert health and API wording.

- [ ] **Step 1: Write failing fleet-only and enabled-but-inert Alerts tests**

Construct runtime fakes through existing main/API helpers. Assert fleet enabled with Preview/Alerts disabled starts discovery and stream but creates no preview and dispatches no alert. Assert Alerts enabled while Preview disabled starts neither stream nor sound/flash behavior.

- [ ] **Step 2: Write failing Preview request and Alert mapping tests**

Assert foreground and settings-driven `PreviewHost.request_sweep()` call coordinator discovery request and still publish a roster even if client identities are unchanged. Assert shared facts map `incoming_damage`/`incoming_miss` to `combat`, `incoming_tackle` to `warp_scramble`, and `decloak` unchanged before `AlertPolicy.handle()`.

- [ ] **Step 3: Run migration-focused tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_alerts_wiring.py tests/test_preview_wiring.py tests/test_preview_host.py tests/test_main.py -v
```

Expected: FAIL because production still owns private loops.

- [ ] **Step 4: Rewire PreviewHost**

Inject `request_discovery` into the host. Remove the internal periodic discovery timer and direct production `_sweep()` call; keep all reconciliation on `WM_APP_ROSTER`. Foreground hooks and preview-setting changes request a shared scan. Preserve teardown of preview windows, hotkeys, hooks, and message host.

- [ ] **Step 5: Rewire AlertService as a policy/health adapter**

Remove its production Tailer thread and subscribe it to coordinator facts while eligible. Preserve `_handle()` compatibility for focused tests. Map shared stream health into the existing Alert state payload so current UI wording and tests remain stable. Gamelog folder changes now call coordinator `reconcile()`.

Do not delete `alerts/tailer.py` or its tests in this task; keep it as a compatibility reference until the final dead-code/caller check in Task 13.

- [ ] **Step 6: Build runtime components in `__main__.py`**

Construct one `ClientDiscovery`, `GameLogStream`, `FleetMetrics`, `AlertPolicy`, and `TelemetryCoordinator`, then pass private references into `Api`. Replace preview-specific reconcile calls with coordinator reconciliation while retaining compatibility wrappers if existing callers require them.

- [ ] **Step 7: Run all affected regression suites**

```bash
uv run --no-sync python -m pytest tests/test_alerts_service.py tests/test_alerts_wiring.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_main.py tests/test_poll_tick.py -v
```

Expected: PASS, including the existing test that Preview-off keeps Alerts inert.

- [ ] **Step 8: Commit**

```bash
git add wingman/preview/host.py wingman/alerts/service.py wingman/ui/api.py wingman/__main__.py tests/test_preview_host.py tests/test_alerts_service.py tests/test_alerts_wiring.py tests/test_preview_wiring.py tests/test_main.py
git commit -m "refactor: share discovery and gamelog telemetry"
```

---

### Task 10: Add Fleet-Bar Geometry, Controller, and API Handshake

**Files:**
- Create: `wingman/ui/fleetbar_geometry.py`
- Create: `wingman/ui/fleetbar.py`
- Modify: `wingman/ui/api.py:382-577, 2731-2851`
- Create: `tests/test_fleet_bar_geometry.py`
- Create: `tests/test_fleet_bar.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces geometry: `nearest_edges`, `fit_anchored`, `clamp_visible`, and `work_area_for_rect`.
- Produces `FleetBarController` lifecycle and targeted `publish(snapshot)`.
- Produces API methods: `fleet_bar_state`, `toggle_fleet_bar`, `fleet_bar_ready`, `fit_fleet_bar`, and `save_fleet_bar_pos`.

- [ ] **Step 1: Write failing pure geometry tests**

Cover nearest left/right and top/bottom edges, growth/shrink preserving edge distance, complete clamp, negative monitor origins, oversized top-left/cap behavior, and 32 by 32 fallback visibility. Inject monitor rectangles to test 100%, 125%, 150%, and 200% physical-to-logical conversion.

- [ ] **Step 2: Run geometry tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_geometry.py -v
```

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement pure geometry and the Win32 seam**

Use a small `Rect` named tuple. `work_area_for_rect()` alone binds `MonitorFromRect(..., MONITOR_DEFAULTTONEAREST)` and `GetMonitorInfoW().rcWork`; convert logical input to physical and physical work area back to logical using the injected system scale. Never call a client-window move/resize API.

- [ ] **Step 4: Write failing controller and API tests**

With fake pywebview windows, assert creation uses `frameless=True`, `on_top=True`, `easy_drag=False`, `hidden=True`, explicit minimum size, and the native background token. Assert:

- ready returns one boot token plus the latest complete snapshot;
- publish before readiness stores only the latest snapshot;
- fit rejects stale tokens;
- a matching fit resizes, anchors, clamps, moves, then shows;
- native-not-ready returns `{ready: False}` without showing;
- repeated bounded retries may succeed;
- terminal create/show/fit failure persists `enabled=False`, reconciles, and pushes honest main-page state;
- position save writes only integer `x/y`;
- targeted snapshot evaluation reaches only the fleet window;
- no public non-method `Api` attribute is added.

- [ ] **Step 5: Implement controller and endpoints**

Keep the window reference and error/readiness state inside `FleetBarController`; `Api` stores it as `_fleet_bar`. Use JSON serialization equivalent to `_push()` but evaluate only `window.onFleetSnapshot(...)` on the fleet window. Main-page `onFleetBarState` may use `_push()` because that handler is allowlisted there and harmlessly absent on auxiliary pages.

Return standard toggle outcomes:

```python
{"applied": bool, "persisted": bool, "error": str | None}
```

The default placement and opening dimensions are provisional constants used only before page measurement; do not claim final measured values in this task.

- [ ] **Step 6: Run controller/API tests**

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_geometry.py tests/test_fleet_bar.py tests/test_api.py tests/test_sig_bar.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add wingman/ui/fleetbar_geometry.py wingman/ui/fleetbar.py wingman/ui/api.py tests/test_fleet_bar_geometry.py tests/test_fleet_bar.py tests/test_api.py
git commit -m "feat: add fleet bar window controller"
```

---

### Task 11: Wire Fleet Restore and Ordered Shutdown

**Files:**
- Modify: `wingman/__main__.py:656-864`
- Modify: `tests/test_startup.py`
- Modify: `tests/test_api_quit.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes `FleetBarController` and coordinator from Tasks 8–10.
- Guarantees fleet and sig auxiliary windows are destroyed before the main WebView.
- Stops/join shared workers after runtime consumers detach.

- [ ] **Step 1: Write failing startup and shutdown-order tests**

Record events in fakes and assert persisted consumers reconcile before the main shown callback restores the hidden fleet bar. On quit assert strict order:

```python
assert calls.index("destroy:fleet") < calls.index("destroy:sig")
assert calls.index("destroy:sig") < calls.index("destroy:main")
assert calls.index("destroy:main") < calls.index("stop:telemetry")
```

The implementation order is fleet, then signature, then main; both auxiliary windows therefore satisfy the hard pywebview invariant.

- [ ] **Step 2: Run startup tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_startup.py tests/test_api_quit.py tests/test_main.py -v
```

Expected: FAIL because fleet restore/destroy is not wired.

- [ ] **Step 3: Implement restore and shutdown**

Restore the fleet controller from the main window's `shown` hook, hidden until its page handshake. In `on_quit`, destroy fleet and sig windows before main. After `window_mod.run()` returns, detach consumers and stop/join coordinator, stream, discovery, Alerts adapter, Preview host, hotkeys, tray, and Skills in the existing safe order.

- [ ] **Step 4: Run startup and existing lifecycle tests**

```bash
uv run --no-sync python -m pytest tests/test_startup.py tests/test_api_quit.py tests/test_main.py tests/test_hotkeys_lifecycle.py tests/test_alerts_wiring.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wingman/__main__.py tests/test_startup.py tests/test_api_quit.py tests/test_main.py
git commit -m "feat: restore and stop the fleet bar safely"
```

---

### Task 12: Build the Standalone Fleet Page and Main-Window Controls

**Files:**
- Create: `wingman/web/fleetbar.html`
- Create: `wingman/web/fleetbar.css`
- Create: `wingman/web/fleetbar.js`
- Modify: `wingman/web/index.html:684-761, 1995-2034`
- Modify: `wingman/web/app.js:50-79`
- Modify: `wingman/web/previews.js`
- Modify: `wingman/web/dev.js`
- Modify: `wingman/web/style.css:1963-2062`
- Create: `tests/test_fleet_bar_page.py`
- Modify: `tests/test_bridge_contract.py`
- Modify: `tests/test_page_conventions.py`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_preview_wiring.py`

**Interfaces:**
- Fleet page global: `window.onFleetSnapshot(payload)`.
- Main page handler: `WM.handle('onFleetBarState', renderFleetBarState)`.
- Page calls: `fleet_bar_ready`, `fit_fleet_bar`, and `save_fleet_bar_pos`.
- Main page calls: `fleet_bar_state` and `toggle_fleet_bar`.

- [ ] **Step 1: Write failing lexical fleet-page tests**

Assert the standalone page:

- loads `style.css`, `fleetbar.css`, and `fleetbar.js`, but not `app.js`;
- exposes one full-surface `.pywebview-drag-region`;
- registers `window.onFleetSnapshot`;
- waits for both `pywebviewready` and `document.fonts.ready`;
- performs ready, render, fit, and bounded retry in that order;
- renders fixed name/DPS/EWAR columns with tabular figures and ellipsis;
- distinguishes `0` from unavailable em-dash, per-row `NO LOG`, global degraded status, and `No active clients`;
- contains no clickable row action and disables text selection;
- saves `screenX/screenY` on mouseup;
- permits vertical wheel scrolling only in the oversized fallback.

- [ ] **Step 2: Write failing main-page control tests**

Assert `onFleetBarState` is in `WM.HANDLERS` and registered by `previews.js`; Settings markup uses `.check`/`.box`, status has `role="status"`, and the quick button is adjacent to `#btn-sigbar` with `aria-pressed`. Test no optimistic permanent state and authoritative repaint after success/refusal. Add dev doubles and representative enabled, missing-log, and visible states.

- [ ] **Step 3: Run web-source tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_preview_wiring.py -v
```

Expected: FAIL because pages and controls are absent.

- [ ] **Step 4: Implement the standalone page**

Use the approved fixed-column design: stable rows, compact effect tag, root color tokens, no card grid, no glass effects, and no animation of layout properties. Keep page-specific CSS focused on sizing/layout; all colors come from existing `:root` tokens. The bar remains dark-only and non-interactive.

- [ ] **Step 5: Implement Settings and quick-control synchronization**

Add a separate compact card under Settings > Previews, outside the preview master dependency block. In `previews.js`, render visible, waiting/no clients, missing folder, per-reader failure, and hidden states from authoritative payloads. Both controls call the same endpoint and repaint from returned/pushed state.

- [ ] **Step 6: Measure the 839/840 CSS-pixel status strip on Windows**

At 100% and 200% scaling, force both quick buttons visible, the full EVE segment populated with representative longest values, maximum representative status text, an active progress track, and percentage. Record physical and CSS viewport widths, available progress-track width, and whether EVE values partially clip.

If the full strip fits with a usable progress track, add a CSS comment with the measured minimum track width and no breakpoint. If it does not, add a reachable rule at the measured threshold at or above 840 that hides the complete `.evestat` only in the stressed upload state. Never reuse the unreachable 720px rule as evidence.

- [ ] **Step 7: Open the standalone page in the real app on Windows**

Verify initial hidden boot has no empty flash, fonts settle before fit, ten rows fit without scrolling on the smallest tested work area, names ellipsize, DPS columns do not move, drag persists, and disabled/missing-log/no-client states are legible. Record these checks in the new smoke section before considering the task green.

- [ ] **Step 8: Run web tests**

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_preview_wiring.py tests/test_shoot_screens.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add wingman/web/fleetbar.html wingman/web/fleetbar.css wingman/web/fleetbar.js wingman/web/index.html wingman/web/app.js wingman/web/previews.js wingman/web/dev.js wingman/web/style.css tests/test_fleet_bar_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_preview_wiring.py
git commit -m "feat: add fleet combat bar interface"
```

---

### Task 13: Package, Document, Audit, and Verify the Complete Feature

**Files:**
- Modify: `pyproject.toml:79-87`
- Modify: `.github/actions/build-installer/action.yml:342-379`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `docs/smoke-checklist.md:2711-2738` and append the fleet matrix
- Remove after caller verification: `wingman/alerts/tailer.py`
- Migrate unique coverage, then remove: `tests/test_alerts_tailer.py`

**Interfaces:**
- Packages `wingman.telemetry` and all three fleet web assets.
- Leaves no duplicate production gamelog reader or direct PreviewHost discovery loop.
- Records completed automated and required manual verification.

- [ ] **Step 1: Write failing package completeness tests**

Assert `wingman.telemetry` appears in `[tool.setuptools].packages`, and the frozen asset check names `fleetbar.html`, `fleetbar.css`, and `fleetbar.js`. Keep the existing whole-web-directory `uploader.spec` behavior unchanged.

- [ ] **Step 2: Run packaging tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py -v
```

Expected: FAIL on package/assets not yet declared.

- [ ] **Step 3: Add package and frozen-asset declarations**

Add `"wingman.telemetry"` to the explicit package list. Extend the installer action's post-build asset assertions with the three standalone files. Do not add redundant `uploader.spec` data entries because the whole `wingman/web` directory is already collected.

- [ ] **Step 4: Update the smoke checklist**

Add the approved matrix: independent Fleet/Preview/Alert switches; one through ten clients; login/logout/relog; observed zero versus `NO LOG`; DPS event-time window and decay; tackle ownership/expiry; both bars; hidden main window; OBS/EVE foreground; all supported scaling; monitor removal; missing/restored folder; and quit with both auxiliary windows visible.

Remove only the stale sig-bar color/opacity checks contradicted by the current fixed-background implementation. Preserve all still-valid sig-bar placement, drag, restore, and shutdown checks.

- [ ] **Step 5: Audit old readers and discovery callers, then remove the replaced reader**

```bash
rg -n "alerts\.tailer|tailer\.Tailer|Tailer\(" wingman tests
rg -n "list_clients\(|_sweep\(|WM_TIMER" wingman/preview wingman/telemetry tests
```

The search must show no production caller of `alerts/tailer.py` and no production path running a second gamelog cursor or PreviewHost discovery timer. Move every uniquely valuable rotation, partial-line, cap, and ownership case from `tests/test_alerts_tailer.py` into `tests/test_telemetry_gamelogs.py`; then delete `wingman/alerts/tailer.py` and `tests/test_alerts_tailer.py`. If a production caller remains, stop and remove that caller through the shared stream rather than retaining two readers.

- [ ] **Step 6: Run focused packaging and invariant tests**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py tests/test_no_tk.py tests/test_engine_invariants.py tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Run polish-core and inspect every edit**

Invoke the `polish-core` skill in fix mode against base commit `492b825` (equivalent prompt: `/polish 492b825 --fix`). Inspect `git diff` immediately. Keep only high-confidence corrections within the fleet feature; revert unrelated or speculative edits.

- [ ] **Step 8: Run all automated gates fresh**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check
```

Expected: all tests pass with only documented platform skips; Ruff and diff checks exit zero.

- [ ] **Step 9: Complete the Windows smoke matrix**

Execute every new checklist item on a real Windows machine. Record any unavailable outgoing-drone or tackle scenario honestly; do not mark it passed from fixture tests alone. Confirm the app exits cleanly with Fleet Bar, sig bar, main window, shared telemetry, Preview, and Alerts in the combinations required by the spec.

- [ ] **Step 10: Review final scope and commit**

Confirm the final diff contains no ECM/JAM implementation, guessed EWAR, client move/resize call, debug output, dormant duplicate reader, placeholder, or unrelated refactor.

```bash
git add -u
git add pyproject.toml .github/actions/build-installer/action.yml tests/test_packaging_completeness.py docs/smoke-checklist.md
git commit -m "chore: package and verify fleet combat bar"
```

- [ ] **Step 11: Prepare the completion explanation**

Use `change-explainer` against `492b825..HEAD`, citing the exact automated results and Windows smoke results actually performed. Call out fixture-gated omission of JAM and any remaining platform-only risk.
