# Task 1 report — Fleet activation generation stamping

## Scope
Implemented Task 1 from the Fleet character visibility brief: stamp Fleet activations at the telemetry coordinator boundary and expose the requested generation so later consumers can reject stale callbacks.

## What changed

### `wingman/telemetry/model.py`
- Added `FleetSnapshot.activation_generation: int = 0`.
- Kept the field last with a default so existing positional constructors and older snapshot callers continue to work.
- The default `0` preserves the required synthetic/pre-publication and disabled snapshot semantics.

### `wingman/telemetry/coordinator.py`
- Extended `_FleetMode` to carry `generation` alongside `enabled`.
- Added coordinator state for:
  - `_fleet_requested_generation`
  - `_fleet_active_generation`
- Changed `reconcile()` to return the currently requested Fleet generation.
- Added `requested_fleet_generation()` as a thread-safe accessor.
- Moved Fleet generation reservation ahead of dispatcher startup so a failed start still records the requested generation.
- Kept generation stable across idempotent reconciles and incremented it on every Fleet mode transition.
- Changed `_apply_fleet_mode()` to receive the full control item and record the active generation on the dispatcher thread.
- Stamped every published `FleetSnapshot` with the active generation using `dataclasses.replace(...)`.
- Reset active generation to `0` when the dispatcher is finalized so disabled and pre-publication snapshots remain generation `0`.

### `tests/test_telemetry_coordinator.py`
Added focused generation-contract coverage for:
- reserving a generation even when dispatcher startup fails,
- idempotent reconciliation reusing the same generation,
- each Fleet-mode transition reserving a new generation,
- preserving the reserved generation through a later successful reconcile,
- keeping empty and disabled snapshots at generation `0`,
- stamping a published snapshot with the activated generation.

## TDD evidence

### RED
Focused red run against the new generation contract:

```bash
uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py::TestFleetGeneration -v
```

Exact failures observed before implementation:
- `test_fleet_generation_is_reserved_even_when_dispatcher_cannot_start`: `assert None == 1`
- `test_idempotent_reconcile_reuses_requested_fleet_generation`: `assert None == 1`
- `test_each_fleet_mode_transition_reserves_a_new_generation`: `assert (None, None, None) == (1, 2, 3)`
- `test_failed_start_keeps_the_reserved_generation_for_a_later_reconcile`: `assert (None, None) == (1, 1)`
- `test_empty_and_disabled_snapshots_keep_generation_zero`: `AttributeError: 'FleetSnapshot' object has no attribute 'activation_generation'`

### GREEN
After the implementation, the same slice passed:

```bash
uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py::TestFleetGeneration -v
```

Result:
- `6 passed in 0.93s`

## Verification performed

- `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py::TestFleetGeneration -v` — `6 passed in 0.93s`
- `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py -v` — `62 passed in 1.53s`
- `uv run --no-sync python -m pytest tests/test_fleet_bar.py -v` — `20 passed in 2.60s`
- `uv run --extra dev ruff check wingman/telemetry/model.py wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py tests/test_fleet_bar.py` — `All checks passed!`
- `uv run --extra dev ruff format --check wingman/telemetry/model.py wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py tests/test_fleet_bar.py` — `4 files already formatted`

## Notes / residual risk

- This task only stamps and exposes the activation generation. It does not implement the later API-side rejection/handoff logic described in the spec.
- The generation field defaults to `0`, so legacy constructors and disabled/pre-publication snapshots stay truthful without extra migration work.
- I kept the change bounded to the coordinator/model/test surfaces for Task 1 only.

## Fix round 1

### What changed
- Fixed the late-dead-dispatcher startup path in `wingman/telemetry/coordinator.py` so a dead worker finalized during `reconcile()` cannot drain the just-reserved Fleet activation generation without putting the same `_FleetMode` back on the queue.
- Updated the coordinator public-interface docstring to `reconcile() -> int`.
- Added a regression test, `test_late_dead_dispatcher_preserves_the_reserved_fleet_generation`, based on the existing late-dead-worker setup.

### Evidence
- RED: `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py::TestFleetGeneration::test_late_dead_dispatcher_preserves_the_reserved_fleet_generation -v`
  - Failed before the fix with `AssertionError: assert 0 == 1` on `len(h.snapshots)`.
- GREEN: the same targeted test passed after the fix.
- Full verification:
  - `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py tests/test_fleet_bar.py tests/test_fleet_metrics.py -v`
  - Result: `119 passed in 4.14s`
- Ruff:
  - `uv run --extra dev ruff check wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py`
  - `uv run --extra dev ruff format --check wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py`
  - Result: both passed.

## Fix round 2

### What changed
- Added a deterministic regression for the retained-dead-worker case where the replacement dispatcher thread fails to start after finalizing the dead worker.
- Taught `TelemetryCoordinator` to remember that dead-worker finalization happened and to restore the reserved Fleet generation even when the replacement `start()` raises, instead of only restoring on the successful-start path.
- Kept the initial startup refusal path unchanged: if dispatcher startup fails without finalizing a dead worker, the reserved generation is still just returned and no restoration is synthesized.

### Evidence
- RED: `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py::TestFleetGeneration::test_late_dead_dispatcher_preserves_the_reserved_fleet_generation -v`
  - Failed before the fix with `AssertionError: assert (1, 2) == (1, 1)` on the second reconcile generation.
- GREEN: the same targeted test passed after the fix.
- Full verification:
  - `uv run --no-sync python -m pytest tests/test_telemetry_coordinator.py tests/test_fleet_bar.py tests/test_fleet_metrics.py -v`
  - Result: `119 passed in 4.98s`
- Ruff:
  - `uv run --extra dev ruff check wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py`
  - `uv run --extra dev ruff format --check wingman/telemetry/coordinator.py tests/test_telemetry_coordinator.py`
  - Result: both passed.
