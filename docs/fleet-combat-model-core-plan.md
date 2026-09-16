# Local combat model core — approved isolated implementation slice

## Authorization and boundary

The user asked the coordinator to continue remaining implementation in parallel.
Independent contract review `fd8a5001-e203-4ba` found the shared contract needs
revision, but explicitly separated this model slice. The coordinator approves the
internal handoff below for local-model core implementation only. This is not
approval of wire fields, Unicode limits, server migrations or automatic controls,
and does not apply any of the six shared-contract review findings.

Authoritative behavior: `fleet-telemetry-v2-design.md` sections 2–3. Source base:
Wingman `62e1645cf9f49f11ea9af83ffe4ad619a9de5bdf`. The coordinator branch adds plans,
not production changes. The broader model draft remains evidence for deferred
steps, not authorization to implement them now.

## Frozen internal interface

Use frozen dataclasses in `wingman/telemetry/model.py`:

```python
from dataclasses import dataclass
from uuid import UUID

ObservationId = tuple[UUID, int]

@dataclass(frozen=True)
class EffectObservation:
    kind: str
    expires_at_mono: float
    observation_id: ObservationId
    name: str | None = None

@dataclass(frozen=True)
class CombatActivity:
    expires_at_mono: float | None = None
    observation_id: ObservationId | None = None
    observations: tuple[EffectObservation, ...] = ()
```

Append `combat: CombatActivity | None = None` to `FleetRow`, and
`sampled_at_mono: float | None = None` to `FleetSnapshot`, preserving every existing
positional field. Do not yet add parser attribution fields: they belong to the
later name-extraction slice.

New pure `telemetry/combat.py` supplies:

```python
def read_combat(row: FleetRow, *, now_mono: float) -> CombatActivity | None: ...
def combat_row_visible(row: FleetRow, *, now_mono: float) -> bool: ...
def next_combat_transition(rows: tuple[FleetRow, ...], *, now_mono: float) -> float | None: ...
```

These signatures describe real readers to implement, not stubs. Readers preserve
row deadlines/IDs even after expiry and filter independently expired observations
without mutating their input. They never resample UTC, create identities, renew
observations or do transport work. `combat=None`
is absent evidence; `CombatActivity()` is supported but inactive. The visibility
helper is a local-row predicate: unexpired activity plus available local metrics.
The current producer supplies both directions when bound, neither when NO LOG;
this predicate must not become an assumed wire/remote nullable-metric contract.

C's transport proposal and U's projection proposal consume immutable deadlines
and IDs; neither needs server-origin mapping inside metrics. Retained transport
clock origins remain outside this lane. Internal source lifetime tokens and
sequence values are never sent to the page or relay.

Allocate a fresh opaque lifetime token on actual source/session invalidation or
state recreation; preserve it through unchanged active rebinds. Accepting evidence
that strictly advances a row deadline changes its row ID to `(token, sequence)`.
Equal/older deadlines keep the prior ID. Rejected facts change neither. Full
reset/recreation cannot reuse a token. Row lifetime fencing must ship with row
activity, not wait for named-effect implementation.

## Owned files

- `wingman/telemetry/model.py`, new `wingman/telemetry/combat.py`.
- `wingman/telemetry/metrics.py`.
- New `tests/test_telemetry_combat.py`, existing `tests/test_fleet_metrics.py`.
- `tests/test_telemetry_coordinator.py` only if additive metadata requires explicit
  expected-value updates; preserve its lifecycle/Alert assertions and report why.

No parser, gamelog, Alert, transport, UI, authGD, schema or runtime-owner edits.
No names, Unicode tables, bounded named retention or effect-producer replacement
until the shared validation artifact is approved. The existing EWAR tag behavior
remains an intermediate implementation boundary, not the final feature behavior.

## Task 1 — immutable values and pure readers

1. Add failing tests for immutability, positional defaults, inactive/absent evidence,
   repeated reads and deadline boundaries. A row active to 50 with supplied effects
   expiring at 30/40 must retain only the latter at 30, neither at 40, and disappear
   at 50; transitions advance 30 → 40 → 50 → none.
2. Implement the types and readers. Return surviving observations in established
   SCRAM/POINT/NEUT order, stable within each kind. Preserve original snapshot
   values and identities; transitions ignore expired deadlines.
3. Run `uv run --no-sync python -m pytest tests/test_telemetry_combat.py -q`, verify
   the intended RED then GREEN, inspect diff and commit this task normally.

## Task 2 — row activity, real sampling time and lifecycle IDs

1. Test incoming/outgoing one-point damage: DPS rounds to zero, activity survives
   at 29.999s and expires at 30s, while complete roster rows remain collected.
   Test 15s-delayed hits: activity with 15s remainder, no ten-second DPS contribution.
2. Test literal zero damage and incoming EWAR as qualifying accepted events;
   misses, malformed/rejected facts, chatter and snapshots never renew activity.
   Preserve the existing damage and EWAR future-timestamp policies.
3. Test independent row deadlines/IDs and full reset, retirement, replacement and
   unchanged rebind behavior. A rejected sequence remains available for a valid
   correction; stale queued facts cannot resurrect activity.
4. Implement separate row-activity state alongside existing EWAR state. Do not
   change old EWAR hold behavior in this partial slice. Snapshot real sampling
   time once while computing metrics; repeated reads of an exported snapshot do
   not rewrite that time. Keep ten-second directional DPS/rounding and complete
   sorted NO LOG roster rows.
5. Run focused metrics/core/coordinator tests; demonstrate behavioral RED/GREEN
   without removing the tests during the control. Commit only owned changes.

## Verification and handoff

Run from a dedicated linked model worktree with its own locked dev environment:

```sh
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py -q
# After implementation:
uv run --no-sync python -m pytest tests/test_telemetry_combat.py tests/test_fleet_metrics.py tests/test_telemetry_coordinator.py tests/test_telemetry_parsing.py tests/test_telemetry_gamelogs.py -q
uv run --no-sync python -m pytest tests/ -k alert -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

A baseline failure is a blocker to investigate, not permission for unrelated
edits. Task commits require independent review before integration; finishing the
core does not complete the model lane or permit a release. Named attribution,
independent effect production, shared transport, presentation, automatic mode and
full integrated verification remain open. No push, merge into coordinator/main,
deployment, real credentials or installed-app actions are authorized for this lane.
