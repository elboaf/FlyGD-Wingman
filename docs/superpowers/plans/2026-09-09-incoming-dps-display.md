# Incoming DPS Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calculate local incoming DPS and render incoming and outgoing DPS as exact values plus independently normalized split rails in the existing 420px Fleet Bar.

**Architecture:** The existing parser already emits `incoming_damage`; `FleetMetrics` will aggregate it in a second ten-second deque while retaining `FleetRow.dps` as outgoing for protocol-v1 compatibility. The bridge will expose explicit display names, and the standalone Fleet Bar page will normalize only the visible rows it receives. Fleet-sharing protocol v1 remains unchanged.

**Tech Stack:** Python 3.11, frozen dataclasses, pytest, plain ES5 JavaScript, HTML/CSS, Node `vm` runtime harness, pywebview 6.2.1.

**Spec:** `docs/superpowers/specs/2026-09-09-incoming-dps-display-design.md`

## Global Constraints

- Keep the Fleet Bar exactly 420 CSS pixels wide.
- Keep rows case-insensitively alphabetical; never sort by damage.
- Use the fixed event-time window `(now - 10 seconds, now]`, divide by ten, and round half-up for both directions.
- Incoming damage must not refresh the 30-second EWAR activity deadline.
- Preserve `FleetRow.dps` as outgoing and preserve protocol-v1 `{character_id, dps, ewar}` bytes and validation.
- Python filters hidden rows before presentation; JavaScript normalizes only the received rows.
- Values through `10,000,000` display in full; larger values display and announce as more than ten million.
- No new dependency, worker, thread, setting, route, or user preference.
- Colors are chosen only through existing `:root` tokens; positive incoming and active EWAR use `--warn`, not `--err` or `--danger`.
- Browser geometry is not Windows/WebView2 acceptance; record native smoke as separately verified or unverified.

---

### Task 1: Harden incoming amount parsing

**Files:**
- Modify: `wingman/telemetry/parsing.py`
- Modify: `tests/test_telemetry_parsing.py`

**Interfaces:**
- Consumes: an incoming combat line already recognized by `_is_incoming_damage(lower)`.
- Produces: `ParsedFact(kind="incoming_damage", amount=int | None, source=str)` without raising for malformed numeric text.
- Preserves: the recognized fact and source when `amount is None`, so `alerts.patterns.match_line()` still emits the existing combat alert.

- [ ] **Step 1: Write failing parser tests**

Add a helper that derives realistic incoming lines from `player_damage_and_miss.txt`, then pin valid and invalid grouping:

```python
def _incoming_with_amount(token: str) -> tuple[str, str]:
    who, line = _fixture_line("player_damage_and_miss.txt", "from</font>")
    line = re.sub(r"(<b>)[\d,]+(</b>)", rf"\g<1>{token}\g<2>", line, count=1)
    return who, line


@pytest.mark.parametrize(("token", "expected"), [("1234", 1234), ("1,234", 1234), ("12,345", 12345)])
def test_incoming_damage_accepts_metric_grade_amounts(token, expected):
    who, line = _incoming_with_amount(token)
    fact = parsing.parse_line(line, who).facts[0]
    assert fact.kind == "incoming_damage"
    assert fact.amount == expected
    assert fact.source


@pytest.mark.parametrize("token", ["1,,299", "12,34", ",,,"])
def test_incoming_damage_keeps_alert_fact_but_rejects_malformed_amount(token):
    who, line = _incoming_with_amount(token)
    fact = parsing.parse_line(line, who).facts[0]
    assert fact.kind == "incoming_damage"
    assert fact.amount is None
    assert fact.source
```

Import `re` in the test module. Add one absent-amount shape by replacing the amount token with an empty string and assert the same `amount is None` result.

- [ ] **Step 2: Run tests and verify the malformed cases fail safely**

Run:

```bash
uv run --no-sync python -m pytest tests/test_telemetry_parsing.py -q
```

Expected: the new malformed tests fail because current extraction accepts bad grouping or raises `ValueError`; all existing parser tests remain collected.

- [ ] **Step 3: Implement strict, non-throwing grouped integer parsing**

Keep recognition separate from amount validity:

```python
_GROUPED_INT_RE = re.compile(r"(?:\d+|\d{1,3}(?:,\d{3})+)\Z", re.ASCII)


def _parse_grouped_int(token: str) -> int | None:
    if _GROUPED_INT_RE.fullmatch(token) is None:
        return None
    return int(token.replace(",", ""))


def _extract_amount(line: str) -> int | None:
    match = _AMOUNT_RE.search(line)
    if match is None:
        return None
    return _parse_grouped_int(match.group("amount"))
```

Retain `_AMOUNT_RE`'s `[\d,]+` token capture so the tested malformed comma forms reach `_parse_grouped_int()`; do not make `_is_incoming_damage()` depend on amount validity. Apply `_parse_grouped_int()` to the plain outgoing fallback too, returning `None` rather than raising when its token is invalid.

- [ ] **Step 4: Verify parser and Alert compatibility**

Run:

```bash
uv run --no-sync python -m pytest tests/test_telemetry_parsing.py tests/test_alerts_patterns.py -q
```

Expected: PASS; malformed incoming values retain an `incoming_damage` fact, and existing combat-alert behavior remains unchanged.

- [ ] **Step 5: Commit**

```bash
git add wingman/telemetry/parsing.py tests/test_telemetry_parsing.py
git commit -m "fix: validate incoming damage amounts"
```

---

### Task 2: Aggregate incoming DPS independently

**Files:**
- Modify: `wingman/telemetry/model.py`
- Modify: `wingman/telemetry/metrics.py`
- Modify: `tests/test_fleet_metrics.py`

**Interfaces:**
- Produces: `FleetRow.incoming_dps: int | None` as a trailing defaulted field.
- Preserves: `FleetRow.dps` as outgoing, positional constructor compatibility, alphabetical order, source/session guards, and shared `metric_error` policy.
- Internal state: `_CharacterState.outgoing_damage` and `_CharacterState.incoming_damage`, each `deque[tuple[datetime, int]]`.

- [ ] **Step 1: Add failing incoming-DPS and compatibility tests**

Extend test helpers so `_damage(..., kind="outgoing_damage")` can create either direction. Add tests equivalent to:

```python
def test_directions_accumulate_and_decay_independently(self):
    metrics, utc_box, _ = self._bound(_metrics())
    metrics.consume(_env(3, _damage("Alice", 100, NOW, kind="outgoing_damage")))
    metrics.consume(_env(4, _damage("Alice", 250, NOW, kind="incoming_damage")))
    row = _row(metrics.snapshot(5, HEALTH), "Alice")
    assert row.dps == 10
    assert row.incoming_dps == 25
    utc_box[0] = NOW + datetime.timedelta(seconds=10)
    row = _row(metrics.snapshot(6, HEALTH), "Alice")
    assert (row.dps, row.incoming_dps) == (0, 0)


def test_bound_zero_and_unbound_unavailable_cover_both_directions(self):
    # Bound row: dps == incoming_dps == 0.
    # Unbound row: both are None and log_status == NO_LOG.


def test_incoming_damage_does_not_refresh_observed_ewar(self):
    metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
    metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))
    utc_box[0] = NOW + datetime.timedelta(seconds=20)
    mono_box[0] = 120.0
    metrics.consume(_env(4, _damage("Alice", 100, utc_box[0], kind="incoming_damage")))
    mono_box[0] = 130.0
    assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()
```

Also add tests for incoming half-up rounding, exact ten-second exclusion, two-second future clamp, direction-specific future error text, rejected incoming sequence reuse, accepted incoming/outgoing/EWAR clearing a prior diagnostic, and source retirement/replacement clearing both directions.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_metrics.py -q
```

Expected: FAIL because `FleetRow` has no `incoming_dps` and metrics ignores `incoming_damage`.

- [ ] **Step 3: Extend the row and state models**

Append the compatibility-safe field:

```python
@dataclass(frozen=True)
class FleetRow:
    character: str
    dps: int | None
    ewar: tuple[str, ...] = ()
    log_status: str | None = None
    incoming_dps: int | None = None
```

Replace the one state deque with two named deques. Change pruning to consume and return a deque rather than owning an entire state:

```python
def _prune_damage(damage, now):
    window_start = now - DPS_WINDOW
    return deque((at, amount) for at, amount in damage if at > window_start)
```

Every lifecycle clear that currently clears `state.damage` must clear both directional deques.

- [ ] **Step 4: Add direction-aware ingestion without changing EWAR policy**

Dispatch both kinds explicitly:

```python
if fact.kind == "outgoing_damage":
    accepted = self._ingest_damage(state, fact, incoming=False)
elif fact.kind == "incoming_damage":
    accepted = self._ingest_damage(state, fact, incoming=True)
```

In `_ingest_damage`, choose the deque and diagnostic label by `incoming`. Reuse timestamp validation and the future clamp. Only the outgoing branch calls `_refresh_activity`; an old incoming fact outside `DPS_WINDOW` returns `False`. A valid in-window fact appends to its selected deque and clears `_metric_error`.

In `snapshot()`, prune and sum each deque independently, emitting numeric zeroes for a bound row and two `None` values for an unbound row.

- [ ] **Step 5: Verify metrics, coordinator, and sharing projection**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py tests/test_fleetsharing_projection.py tests/test_fleetsharing_worker.py -q
```

Expected: PASS. Projection remains based on `row.dps`; incoming-only rows do not alter protocol-v1 publication.

- [ ] **Step 6: Commit**

```bash
git add wingman/telemetry/model.py wingman/telemetry/metrics.py tests/test_fleet_metrics.py
git commit -m "feat: calculate incoming fleet DPS"
```

---

### Task 3: Expose explicit local display fields

**Files:**
- Modify: `wingman/ui/api.py`
- Modify: `tests/test_fleet_bar.py`
- Verify unchanged: `wingman/fleetsharing/model.py`
- Verify unchanged: `wingman/fleetsharing/client.py`

**Interfaces:**
- Produces page rows with `outgoing_dps`, `incoming_dps`, `character`, `ewar`, and `log_status`.
- Does not produce a page-level `dps` alias.
- Does not change `PublishRow` or the protocol-v1 request JSON.

- [ ] **Step 1: Change the bridge contract test first**

Update `test_snapshot_payload_preserves_rows_status_and_diagnostics` to construct a live row with `incoming_dps=17`, and require:

```python
{
    "character": "Alice",
    "outgoing_dps": 43,
    "incoming_dps": 17,
    "ewar": ["SCRAM", "NEUT"],
    "log_status": None,
}
```

Require both display values to be `None` on the `NO LOG` row. Add a structural assertion that `dataclasses.fields(PublishRow)` remains exactly `{"character_id", "dps", "ewar"}` and retain the existing client serialization expectation with no `incoming_dps` key.

- [ ] **Step 2: Run tests and verify the payload mismatch**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py::test_snapshot_payload_preserves_rows_status_and_diagnostics tests/test_fleetsharing_projection.py::test_publish_row_carries_only_character_id_dps_and_ewar tests/test_fleetsharing_client.py -q
```

Expected: the Fleet Bar payload test fails on key names; sharing tests pass unchanged.

- [ ] **Step 3: Rename only the bundled page payload**

In `_fleet_display_payload_locked()` emit:

```python
{
    "character": row.character,
    "outgoing_dps": row.dps,
    "incoming_dps": row.incoming_dps,
    "ewar": list(row.ewar),
    "log_status": row.log_status,
}
```

Do not modify fleet-sharing projection, model, validation, or transport code.

- [ ] **Step 4: Verify bridge and wire compatibility**

Run:

```bash
uv run --no-sync python -m pytest tests/test_fleet_bar.py tests/test_fleet_presentation_worker.py tests/test_fleetsharing_projection.py tests/test_fleetsharing_client.py tests/test_fleetsharing_worker.py -q
```

Expected: PASS with explicit local display names and unchanged protocol-v1 requests.

- [ ] **Step 5: Commit**

```bash
git add wingman/ui/api.py tests/test_fleet_bar.py
git commit -m "feat: expose directional DPS to fleet bar"
```

---

### Task 4: Render and exercise the split Damage region

**Files:**
- Modify: `wingman/web/fleetbar.html`
- Modify: `wingman/web/fleetbar.js`
- Create: `scripts/test_fleetbar_runtime.js`
- Modify: `tests/test_fleet_bar.py`
- Modify: `tests/test_js_smoke.py`

**Interfaces:**
- JavaScript helpers: `readDps(row, key) -> number | null`, `maxDps(rows, key) -> number`, `fillRatio(value, maximum) -> number`, `displayDps(value) -> string`, and `damageCell(row, maxOutgoing, maxIncoming) -> HTMLElement`.
- DOM contract: OUT half, center axis, IN half inside one `role="cell"`; EWAR remains the following cell.
- Defensive bound: values above `10_000_000` use `>10m` and the accessible phrase `more than 10 million DPS`.

- [ ] **Step 1: Add failing HTML and runtime expectations**

Update lexical assertions to require `DAMAGE`, `OUT`, `IN`, and `EWAR`, and to reject the old standalone `DPS`/`INCOMING` headings. Create a stdlib-only Node harness that provides real recording elements for `fleet-rows`, `fleet-empty`, `fleet-health`, and `fleet-note`, evaluates `fleetbar.js` in `vm`, invokes `window.onFleetSnapshot()`, and emits JSON describing rendered rows.

The harness must exercise one payload containing:

```javascript
[
  {character:'Alice', outgoing_dps:100, incoming_dps:50, ewar:['SCRAM'], log_status:null},
  {character:'Bravo', outgoing_dps:25, incoming_dps:200, ewar:[], log_status:null},
  {character:'No Log', outgoing_dps:null, incoming_dps:null, ewar:[], log_status:'NO LOG'},
  {character:'Huge', outgoing_dps:10000001, incoming_dps:10000001, ewar:['SCRAM','POINT','NEUT'], log_status:null}
]
```

Assert OUT/IN DOM order, outgoing ratios `1` and `.25`, incoming ratios `.25` and `1`, one `NO LOG` Damage cell, neutral zero/unavailable classes, warm positive-IN class, `>10m`, and named accessible descriptions.

- [ ] **Step 2: Run the focused page tests and verify failure**

Run:

```bash
node scripts/test_fleetbar_runtime.js
uv run --no-sync python -m pytest tests/test_fleet_bar.py tests/test_js_smoke.py -q
```

Expected: the new harness/assertions fail because the current page renders one `dps` cell and has no split rails.

- [ ] **Step 3: Build the fixed three-region markup and styles**

Set the shared row grid to:

```css
grid-template-columns: minmax(0, 1fr) 160px 148px;
```

Add one nested Damage header with `DAMAGE`, `OUT`, and `IN`. Build each half from a value and a 3px track; OUT fill uses `transform-origin: right` and IN uses `transform-origin: left`. Set fill scale directly with `style.transform = 'scaleX(' + ratio + ')'`; do not add transitions. Positive IN and active EWAR use `var(--warn)`. Zero IN, OUT, tracks, axis, and unavailable states use existing neutral tokens. Keep every color decision in `:root` tokens already defined by `style.css`.

- [ ] **Step 4: Implement normalization and accessible rendering**

Before the row loop, compute independent maxima from finite, non-negative numeric values only. `fillRatio()` returns zero for unavailable values, zero values, or a zero maximum and clamps the result to `[0, 1]`.

`damageCell()` must:

- render a single `NO LOG` state when either row field is unavailable with `log_status`;
- otherwise render OUT, axis, then IN;
- display `0..10_000_000` as locale-independent decimal strings and larger values as `>10m`;
- set `aria-label` to `Outgoing N DPS, incoming N DPS`, substituting `more than 10 million` defensively;
- set nested visual children to presentation semantics so the cell is announced once.

Continue clearing and rebuilding rows once per snapshot; immediate fills match that lifecycle.

- [ ] **Step 5: Make the runtime harness a pytest/CI gate**

Add a Node-availability-marked pytest wrapper in `tests/test_js_smoke.py` that runs `node scripts/test_fleetbar_runtime.js`, requires exit zero, and reports stdout/stderr on failure. Keep `scripts/js_smoke.js` unchanged as the independent top-level module gate.

- [ ] **Step 6: Verify runtime, lexical contracts, and executable smoke**

Run:

```bash
node scripts/test_fleetbar_runtime.js
node scripts/js_smoke.js
uv run --no-sync python -m pytest tests/test_fleet_bar.py tests/test_js_smoke.py tests/test_packaging_completeness.py -q
```

Expected: PASS. The runtime harness proves handler-body behavior; the existing smoke gate proves all page modules still load.

- [ ] **Step 7: Measure browser geometry at 420px**

Load `wingman/web/fleetbar.html` in a browser harness with representative rows and record that:

- `document.documentElement.scrollWidth <= 420`;
- both `10,000,000` values render without ellipsis or overlap;
- `SCRAM · POINT · NEUT` remains fully visible;
- the long Character value truncates within the 92px remainder;
- ten rows fit the existing intended vertical work area.

If the measured 160/148 allocation fails, adjust only the Character/Damage/EWAR tracks while keeping total content width 400px and keeping Damage at least wide enough for both maximum supported values.

- [ ] **Step 8: Commit**

```bash
git add wingman/web/fleetbar.html wingman/web/fleetbar.js scripts/test_fleetbar_runtime.js tests/test_fleet_bar.py tests/test_js_smoke.py
git commit -m "feat: render split fleet damage rails"
```

---

### Task 5: Update product truth and complete verification

**Files:**
- Modify: `PRODUCT.md`
- Modify: `docs/smoke-checklist.md`
- Move after implementation: `docs/superpowers/specs/2026-09-09-incoming-dps-display-design.md` to `docs/history/2026-09-09-incoming-dps-display-design.md`
- Move after implementation: `docs/superpowers/plans/2026-09-09-incoming-dps-display.md` to `docs/history/2026-09-09-incoming-dps-display-plan.md`

**Interfaces:**
- Product statement distinguishes local incoming/outgoing DPS from protocol-v1 sharing, which remains outgoing-only.
- Smoke checklist records browser evidence separately from Windows/WebView2 evidence.

- [ ] **Step 1: Update user-facing product documentation**

Change the local Fleet combat bar description to “recent outgoing and incoming DPS” while retaining scram, point, and energy neutralization. Do not broaden the later fleet-sharing privacy statement beyond its current DPS and `SCRAM/POINT` protocol-v1 boundary.

Extend the existing Fleet Bar smoke section with checks for fixed ten-second incoming DPS, OUT-left/IN-right order, independent visible-row normalization, zero versus `NO LOG`, changing leaders without row movement, maximum supported values, full EWAR text, and all supported Windows scaling values.

- [ ] **Step 2: Run focused verification**

Run:

```bash
uv run --no-sync python -m pytest tests/test_telemetry_parsing.py tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py tests/test_fleet_bar.py tests/test_fleet_presentation_worker.py tests/test_fleetsharing_projection.py tests/test_fleetsharing_client.py tests/test_fleetsharing_worker.py tests/test_js_smoke.py tests/test_packaging_completeness.py -q
node scripts/js_smoke.js
node scripts/test_fleetbar_runtime.js
```

Expected: PASS with no skips for Node-backed tests.

- [ ] **Step 3: Run repository quality gates**

Run:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: both PASS.

- [ ] **Step 4: Run the full suite with required native prerequisite**

Follow `docs/overview-layout-sharing-verification.md#local-verification-prerequisites` to place the built release settings codec in `packaging/bin`, then run:

```bash
uv run --no-sync python -m pytest tests/ -rs
```

Expected: PASS with Node/native coverage present; inspect and report every skip.

- [ ] **Step 5: Record manual verification truthfully**

Run the browser geometry checks from Task 4 and the Fleet Bar section of `docs/smoke-checklist.md`. Run Windows/WebView2 checks at 100%, 125%, 150%, and 200% only when that environment is available. Mark unavailable native checks as `UNVERIFIED`; do not present Chromium evidence as WebView2 evidence.

- [ ] **Step 6: Move completed design and plan to history**

Move both documents only after implementation and verification are complete. Preserve their contents unchanged during the move, then update any live references to their history paths.

- [ ] **Step 7: Commit**

```bash
git add PRODUCT.md docs/smoke-checklist.md docs/history/2026-09-09-incoming-dps-display-design.md docs/history/2026-09-09-incoming-dps-display-plan.md
git commit -m "docs: document incoming fleet DPS"
```

---

## Final review gates

- Inspect `git diff main...HEAD` against every acceptance criterion in the spec.
- Run `polish-core --fix`, inspect every edit, and rerun affected tests.
- Run a different-family code review and address only verified findings.
- Run fresh focused tests, Ruff checks, formatting, JavaScript gates, and the full suite after polish.
- Use `change-explainer` for the reviewer-facing completion summary.
