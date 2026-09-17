"""Meaningful in-memory mutants replay existing production-path assertions.

No checked-in source is changed: each isolated module executes a single altered
copy of production state.py, then the same real-file regression exercises it.
Only assertion failures count as a kill; unrelated exceptions fail this harness.
"""

import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests import test_fleetsharing_state4 as current
from tests import test_fleetsharing_state4_capacity as capacity
from tests import test_fleetsharing_state4_migration as migration
from wingman.fleetsharing import state as production

MUTANTS = [
    (
        "unwrap_during_identity",
        '    _base64(d["protected_private_key_b64"], 8192)',
        '    unwrap_private_key(d["protected_private_key_b64"])\n    _base64(d["protected_private_key_b64"], 8192)',
        migration,
        "test_archive_is_deeply_detached_and_never_unwraps_key",
        {},
    ),
    (
        "archive_discard",
        "return replace(observations, cutover=archive)",
        "return observations",
        migration,
        "test_literal_migration_archives_exact_values_without_write_or_replay",
        {"version": 1},
    ),
    (
        "archive_rewrite_revision",
        'archive = Cutover(\n        _compact_utf8(raw).encode("utf-8"),',
        "archive = Cutover(\n        _compact_utf8({**raw, 'last_revision': 0}).encode(\"utf-8\"),",
        migration,
        "test_literal_migration_archives_exact_values_without_write_or_replay",
        {"version": 1},
    ),
    (
        "legacy_replay_session",
        "return replace(observations, cutover=archive)",
        "return replace(observations, cutover=archive, session_id=raw.get('session_id'), last_revision=raw.get('last_revision', 0))",
        migration,
        "test_literal_migration_archives_exact_values_without_write_or_replay",
        {"version": 1},
    ),
    (
        "legacy_promote_start",
        "return replace(observations, cutover=archive)",
        "return replace(observations, cutover=archive, pending_source_commands=tuple(protocol.SourceStart(c['source_id'], c['character_id'], c['character_link_epoch'], c['intent_created_at']) for c in raw['pending_source_commands'] if c['operation'] == 'start'))",
        migration,
        "test_literal_migration_archives_exact_values_without_write_or_replay",
        {"version": 3},
    ),
    (
        "missing_attempt_guard",
        "            or not attempted\n",
        "",
        current,
        "test_automatic_cancel_requires_attempted_on_and_distinct_bound_uuid",
        {"mutation": "cancel_unsent"},
    ),
    (
        "uuid_only_receipt_binding",
        "receipt.command != pending.command",
        "receipt.command.request_id != pending.command.request_id",
        current,
        "test_receipt_binding_is_whole_command_not_uuid_only",
        {"key": "intent_created_at", "value": "2026-09-07T11:59:59.999Z"},
    ),
    (
        "current_status_cas",
        "                receipt.result.generation,\n                receipt.result.revision,",
        "                state.automatic.observed_consent.generation,\n                state.automatic.observed_consent.revision,",
        current,
        "test_receipt_derives_off_from_exact_historical_result_not_current_consent",
        {},
    ),
    (
        "no_capacity_reserves",
        "def _check_capacity(raw: dict) -> None:\n",
        "def _check_capacity(raw: dict) -> None:\n    return\n",
        capacity,
        "test_empty_state_reserves_all_future_slots_and_terminal_components",
        {"check": "save", "partition": "active"},
    ),
    (
        "no_unused_slots",
        "(protocol.MAX_SOURCE_INTENTS - len(commands)) * MAX_SOURCE_COMMAND_BYTES",
        "0",
        capacity,
        "test_empty_state_reserves_all_future_slots_and_terminal_components",
        {"check": "check_control_capacity", "partition": "active"},
    ),
    (
        "no_non_source_growth",
        "        NON_SOURCE_RESERVE_BYTES\n        + command_bytes",
        "        0\n        + command_bytes",
        capacity,
        "test_empty_state_reserves_all_future_slots_and_terminal_components",
        {"check": "check_admission_capacity", "partition": "active"},
    ),
    (
        "no_automatic_terminal_growth",
        "        MAX_PENDING_AUTOMATIC_BYTES\n        + MAX_CONSENT_BYTES\n        + MAX_AUTOMATIC_COMPLETION_BYTES",
        "        0",
        capacity,
        "test_empty_state_reserves_all_future_slots_and_terminal_components",
        {"check": "load", "partition": "automatic"},
    ),
    (
        "partial_save_before_atomic_failure",
        "    atomicio.write_atomic(Path(path), _compact_utf8(raw))",
        "    Path(path).write_text(_compact_utf8(raw), encoding='utf-8')\n    atomicio.write_atomic(Path(path), _compact_utf8(raw))",
        current,
        "test_failed_derived_off_save_preserves_prior_on_and_cancel_bytes",
        {"failure": "replace"},
    ),
    (
        "quarantine_to_empty",
        'raise QuarantineError("Fleet state requires quarantine.") from None',
        "return EMPTY",
        migration,
        "test_bad_files_quarantine_not_empty",
        {"data": b"{"},
    ),
]


@pytest.mark.parametrize(
    "name,old,new,module,test,arguments", MUTANTS, ids=[v[0] for v in MUTANTS]
)
def test_regressions_kill_in_memory_state_mutant(
    tmp_path, monkeypatch, name, old, new, module, test, arguments
):
    source = Path(production.__file__).read_text(encoding="utf-8")
    assert old in source, f"Mutation site changed: {name}"
    mutant = ModuleType("wingman.fleetsharing._state4_mutant")
    monkeypatch.setitem(sys.modules, mutant.__name__, mutant)
    if name == "unwrap_during_identity":
        # The wrapper captures this inert default before the target test patches
        # dpapi.unprotect. Even the old test's missed call cannot reach real DPAPI.
        def inert_unprotect(_blob):
            raise OSError("In-memory DPAPI stand-in.")

        monkeypatch.setattr(production.dpapi, "unprotect", inert_unprotect)
    exec(
        compile(source.replace(old, new), production.__file__, "exec"), mutant.__dict__
    )
    monkeypatch.setattr(module, "s", mutant)
    kwargs = {"tmp_path": tmp_path, **arguments}
    if "monkeypatch" in getattr(module, test).__code__.co_varnames:
        kwargs["monkeypatch"] = monkeypatch
    # AttributeError for a deliberately missing cutover would be an incidental
    # failure. Archive discard is instead caught by an explicit value assertion.
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        getattr(module, test)(**kwargs)
