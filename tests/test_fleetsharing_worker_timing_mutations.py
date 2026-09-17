"""In-memory S4-C mutation witnesses: no edited production files or live operations."""

import inspect
import sys
import textwrap
from pathlib import Path
from types import FunctionType, ModuleType

import pytest

from tests import test_fleetsharing_cadence as cadence
from tests import test_fleetsharing_worker_timing as cases
from tests.test_fleetsharing_worker import _worker
from wingman.fleetsharing import timing
from wingman.fleetsharing import worker as production

WORKER_MUTANTS = [
    (
        "no_public_closure",
        "        with self._lock:\n            clear = self._fence_timing_locked(reason)",
        "        return\n        with self._lock:\n            clear = self._fence_timing_locked(reason)",
        "test_public_loss_synchronously_closes_timeproof_and_orders_fixed_loss_after_http",
        {"reason": "db_continuity_lost"},
        "public signal left B proof open",
    ),
    (
        "missing_synchronous_B_proof_closure",
        "        self._control_time_fenced = True",
        "        self._control_time_fenced = False",
        "test_public_loss_closes_existing_db_proof_before_blocked_lane_can_supersede_on",
        {"reason": "elapsed_reset"},
        "public loss left DB proof usable",
    ),
    (
        "cutoff_sampled_at_drain",
        "context._publisher_lost_continuity(cutoff=notice.cutoff)",
        "context._publisher_lost_continuity(cutoff=self._clock())",
        "test_public_loss_synchronously_closes_timeproof_and_orders_fixed_loss_after_http",
        {"reason": "db_continuity_lost"},
        "loss cutoff moved after its first signal",
    ),
    (
        "missing_final_timing_generation_gate",
        "            if not self._timing_open_locked(fence):\n                return",
        "            if False:\n                return",
        "test_fence_during_real_expensive_projection_discards_the_whole_candidate",
        {},
        "late candidate installed diagnostic",
    ),
    (
        "thread_restart_clears_retained_loss",
        "                self._restart_requested = True",
        "                self._restart_requested = True\n                self._timing_context._timing_loss = None",
        "test_public_loss_synchronously_closes_timeproof_and_orders_fixed_loss_after_http",
        {"reason": "db_continuity_lost"},
        "restart reopened timing",
    ),
    (
        "second_worker_reopens_B_proof",
        "self._control_time_fenced = timing_context._timing_loss is not None",
        "self._control_time_fenced = False",
        "test_fenced_context_cannot_reopen_with_another_worker",
        {"reason": "elapsed_reset"},
        "second worker reopened B proof",
    ),
    (
        "transparent_scope_rebinding",
        "            if context._authenticated_scope is None:",
        "            if True:",
        "test_different_authenticated_origin_refuses_old_timing_without_rebinding",
        {},
        "new origin reidentified retained timing",
    ),
    (
        "remote_requires_local_submission",
        "            and timing_allowed\n",
        "            and timing_allowed and self._latest is not None\n",
        "test_current_shared_read_without_submit_publishes_exact_immutable_payload",
        {},
        None,
    ),
    (
        "independent_clock",
        "self._clock = timing_context._clock",
        "self._clock = lambda: 1000.0",
        "test_current_shared_read_without_submit_publishes_exact_immutable_payload",
        {},
        None,
    ),
    (
        "worker_discards_elapsed_reset_classification",
        "clear = self._fence_timing_locked(candidate.reason)",
        'clear = self._fence_timing_locked("clock_inconsistent")',
        "test_automatic_contradiction_preserves_elapsed_trust_classification",
        {"fault": "receipt_before_start"},
        "detected local regression fabricated comparable F",
    ),
    (
        "late_callback_crosses_clear",
        "                if obsolete:\n                    break",
        "                if False:\n                    break",
        "test_loss_clear_overtakes_blocked_replace_callback_without_reopening_display",
        {},
        None,
    ),
]


@pytest.mark.parametrize(
    "name,old,new,test,args,message",
    WORKER_MUTANTS,
    ids=[case[0] for case in WORKER_MUTANTS],
)
def test_runtime_barrier_kills_worker_mutant(
    tmp_path, monkeypatch, name, old, new, test, args, message
):
    source = Path(production.__file__).read_text(encoding="utf-8")
    assert source.count(old) == 1, name
    mutant = ModuleType("wingman.fleetsharing._worker_timing_mutant")
    monkeypatch.setitem(sys.modules, mutant.__name__, mutant)
    exec(
        compile(source.replace(old, new), production.__file__, "exec"), mutant.__dict__
    )
    monkeypatch.setitem(
        _worker.__globals__, "FleetSharingWorker", mutant.FleetSharingWorker
    )
    regression = getattr(cases, test)
    kwargs = {"tmp_path": tmp_path, **args}
    if "monkeypatch" in inspect.signature(regression).parameters:
        kwargs["monkeypatch"] = monkeypatch
    with pytest.raises(AssertionError, match=message):
        regression(**kwargs)


TIMING_MUTANTS = [
    (
        "diagnostic_discards_elapsed_reset_evidence",
        "_evaluate_diagnostic",
        'return _ClockContradiction(state, "elapsed_reset")',
        "return _ClockContradiction(state)",
        "test_automatic_contradiction_preserves_elapsed_trust_classification",
        {"fault": "start_before_last_receipt"},
        "detected local regression fabricated comparable F",
    ),
    (
        "obsolete_contradiction_poison",
        "_evaluate_diagnostic",
        "        return _ClockContradiction(state)\n    exchange = _Exchange",
        "        self._inconsistent = True\n        return _ClockContradiction(state)\n    exchange = _Exchange",
        "test_obsolete_contradiction_during_detached_evaluation_cannot_poison_context",
        {},
        "obsolete contradiction poisoned context",
    ),
    (
        "partial_anchor_before_receiver_capacity",
        "_evaluate_snapshot",
        '    if len(records) > LIMITS["receiver_capacity"]:',
        '    self._state = diagnostic.state\n    if len(records) > LIMITS["receiver_capacity"]:',
        "test_snapshot_refusal_never_partially_installs_anchor_history_or_payload",
        {"fault": "overflow"},
        "refusal partly committed timing",
    ),
]


@pytest.mark.parametrize(
    "name,method,old,new,test,args,message",
    TIMING_MUTANTS,
    ids=[case[0] for case in TIMING_MUTANTS],
)
def test_runtime_barrier_kills_detached_timing_mutant(
    tmp_path, monkeypatch, name, method, old, new, test, args, message
):
    original = getattr(timing.TimingContext, method)
    source = textwrap.dedent(inspect.getsource(original))
    assert source.count(old) == 1, name
    namespace = dict(original.__globals__)
    exec(
        compile(source.replace(old, new), original.__code__.co_filename, "exec"),
        namespace,
    )
    # Keep the original module globals so the regression's actual projection/
    # arithmetic barrier still intercepts the production seam, not a copied clock.
    mutant = FunctionType(namespace[method].__code__, original.__globals__)
    monkeypatch.setattr(timing.TimingContext, method, mutant)
    with pytest.raises(AssertionError, match=message):
        getattr(cases, test)(tmp_path=tmp_path, monkeypatch=monkeypatch, **args)


@pytest.mark.parametrize(
    "operation",
    ["fetch_automatic", "fetch_eligibility", "fetch_sources", "read_snapshot"],
)
def test_known_scenario_classes_detect_even_never_serviced_operations(
    tmp_path, monkeypatch, operation
):
    work = production.FleetSharingWorker._work

    def omit(self, enabled):
        choices = work(self, enabled)
        if self._clock() >= 1030:
            return tuple(w for w in choices if w.operation != operation)
        return choices

    monkeypatch.setattr(production.FleetSharingWorker, "_work", omit)
    with pytest.raises(AssertionError, match="eligible class starved"):
        cadence.test_current_receiver_matches_exact_freshness_without_local_publication(
            tmp_path, phase=0.5, watch=True, latency=0.08
        )


def test_expiry_coverage_detects_refresh_stopping_after_three_successes(
    tmp_path, monkeypatch
):
    work = production.FleetSharingWorker._work
    accept = production.FleetSharingWorker._accept
    successes = []

    def observed(self, choice, result, *args):
        accepted = accept(self, choice, result, *args)
        if choice.operation == "fetch_eligibility":
            successes.append(self._clock())
        return accepted

    def stop_refresh(self, enabled):
        choices = work(self, enabled)
        if len(successes) >= 3:
            return tuple(w for w in choices if w.operation != "fetch_eligibility")
        return choices

    monkeypatch.setattr(production.FleetSharingWorker, "_accept", observed)
    monkeypatch.setattr(production.FleetSharingWorker, "_work", stop_refresh)
    with pytest.raises(
        AssertionError, match="eligible proof coverage does not reach scenario end"
    ):
        cadence.test_expiring_proof_refresh_progress_is_independent_of_local_publication(
            tmp_path, period=5, phase=0, skew=0.5
        )
    assert len(successes) == 3


@pytest.mark.parametrize(
    "mutation", ["global_minimum", "missing_margin", "premature_withdrawal"]
)
def test_external_trace_oracle_kills_wrong_projection(tmp_path, monkeypatch, mutation):
    original = timing.TimingContext._evaluate_snapshot
    source = textwrap.dedent(inspect.getsource(original))
    old, new = {
        "global_minimum": ("minima[bisect_left(endpoints, x)]", "minima[0]"),
        "missing_margin": ('Fraction(LIMITS["clock_margin_ms"], 1000)', "Fraction(0)"),
        "premature_withdrawal": ("for row in snapshot.rows", "for row in ()"),
    }[mutation]
    assert source.count(old) == 1
    namespace = dict(original.__globals__)
    exec(
        compile(source.replace(old, new), original.__code__.co_filename, "exec"),
        namespace,
    )
    mutant = FunctionType(namespace[original.__name__].__code__, original.__globals__)
    monkeypatch.setattr(timing.TimingContext, original.__name__, mutant)
    message = (
        "premature receiver withdrawal"
        if mutation == "premature_withdrawal"
        else "exact external origin mismatch"
    )
    with pytest.raises(AssertionError, match=message):
        cadence.test_bad_postlock_interval_does_not_bias_genuinely_new_origins(tmp_path)


def test_external_trace_oracle_is_independent_of_display_classification(
    tmp_path, monkeypatch
):
    from wingman.ui import remotefleet

    # In-memory only: if the actual store silently changes 3s to 4s, the oracle
    # must disagree rather than borrowing the store's classification constant.
    monkeypatch.setattr(remotefleet, "STALE_AFTER_S", 4)
    with pytest.raises(AssertionError, match="exact external freshness mismatch"):
        cadence.test_current_receiver_matches_exact_freshness_without_local_publication(
            tmp_path, phase=0.5, watch=True, latency=0.08
        )
