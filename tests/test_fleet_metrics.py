"""Thread-free Fleet Metrics -- tests.

Every test injects a deterministic UTC wall clock (a list holding the
current instant, mutated between calls) and a deterministic monotonic clock
(a list holding the current float), following the pattern already used by
``test_telemetry_gamelogs.py``.
"""

import datetime
import json
from dataclasses import replace
from fractions import Fraction
from math import inf, nextafter
from pathlib import Path
from uuid import UUID

import pytest

from wingman.combatprofile import LIMITS
from wingman.telemetry.combat import combat_row_visible, read_combat
from wingman.telemetry.metrics import NO_LOG, TACKLE_TAG, FleetMetrics
from wingman.telemetry.model import (
    ClientSessionId,
    CombatActivity,
    CombatFact,
    EffectObservation,
    RosterClient,
    RosterSnapshot,
    SourceId,
    SourceLifecycle,
    StreamHealth,
    TelemetryEnvelope,
)

UTC = datetime.UTC
NOW = datetime.datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

HEALTH = StreamHealth(state="active")


def _session(character, *, hwnd=1, pid=100, generation=1):
    return ClientSessionId(
        hwnd=hwnd, pid=pid, character=character, first_seen_generation=generation
    )


def _roster(*sessions, generation=1):
    clients = tuple(
        RosterClient(
            hwnd=s.hwnd,
            pid=s.pid,
            title=s.character,
            character=s.character,
            session=s,
        )
        for s in sessions
    )
    return RosterSnapshot(generation=generation, clients=clients)


def _source_id(path="C:/logs/alice.txt", session_start=NOW):
    return SourceId(normalized_path=path, session_start_utc=session_start)


def _lifecycle(character, *, generation=1, source_id=None, available=True, active=True):
    return SourceLifecycle(
        character=character,
        generation=generation,
        source_id=source_id if source_id is not None else _source_id(),
        available=available,
        active=active,
    )


def _damage(
    character,
    amount,
    occurred_at,
    *,
    source_generation=1,
    source_id=None,
    kind="outgoing_damage",
):
    return CombatFact(
        character=character,
        source_generation=source_generation,
        source_id=source_id if source_id is not None else _source_id(),
        occurred_at=occurred_at,
        kind=kind,
        amount=amount,
    )


def _tackle(character, occurred_at, *, source_generation=1, source_id=None):
    return _ewar(
        character,
        "incoming_scram",
        occurred_at,
        source_generation=source_generation,
        source_id=source_id,
    )


def _ewar(
    character,
    kind,
    occurred_at,
    *,
    amount=None,
    source_generation=1,
    source_id=None,
    observed_name=None,
):
    return CombatFact(
        character=character,
        source_generation=source_generation,
        source_id=source_id if source_id is not None else _source_id(),
        occurred_at=occurred_at,
        kind=kind,
        amount=amount,
        observed_name=observed_name,
    )


def _metrics(now=NOW, mono=0.0):
    """FleetMetrics with mutable injected clocks: returns (metrics, utc_box,
    mono_box) so a test can advance either clock independently."""
    utc_box = [now]
    mono_box = [mono]
    metrics = FleetMetrics(_clock=lambda: mono_box[0], _utc_now=lambda: utc_box[0])
    return metrics, utc_box, mono_box


def _env(sequence, payload):
    return TelemetryEnvelope(sequence=sequence, payload=payload)


def _row(snapshot, character):
    return next(r for r in snapshot.rows if r.character == character)


def test_reset_clears_sessions_metrics_and_diagnostics():
    metrics, _, _ = _metrics()
    metrics.consume(_env(1, _roster(_session("Alice"))))
    metrics.consume(_env(2, _lifecycle("Alice")))
    metrics.consume(_env(3, _damage("Alice", 100, NOW + datetime.timedelta(seconds=3))))
    assert metrics.snapshot(4, HEALTH).metric_error

    metrics.reset()

    snapshot = metrics.snapshot(5, HEALTH)
    assert snapshot.rows == ()
    assert snapshot.metric_error is None


# ---------------------------------------------------------------------------
# Roster/source binding
# ---------------------------------------------------------------------------


class TestBinding:
    def test_row_starts_unbound_no_log(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        row = _row(metrics.snapshot(2, HEALTH), "Alice")
        assert row.dps is None
        assert row.log_status == NO_LOG
        assert row.ewar == ()

    def test_lifecycle_at_session_first_roster_sequence_does_not_bind(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(5, _roster(_session("Alice"))))
        # Same sequence as the session's first roster envelope: must NOT bind.
        metrics.consume(_env(5, _lifecycle("Alice")))
        row = _row(metrics.snapshot(6, HEALTH), "Alice")
        assert row.dps is None
        assert row.log_status == NO_LOG

    def test_lifecycle_after_session_first_roster_sequence_binds(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(5, _roster(_session("Alice"))))
        metrics.consume(_env(6, _lifecycle("Alice")))
        row = _row(metrics.snapshot(7, HEALTH), "Alice")
        assert row.dps == 0
        assert row.log_status is None

    def test_stale_roster_envelope_does_not_roll_back(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(10, _roster(_session("Alice", hwnd=1))))
        metrics.consume(_env(11, _lifecycle("Alice")))
        assert _row(metrics.snapshot(12, HEALTH), "Alice").dps == 0
        # An older roster envelope describing a DIFFERENT session must not
        # be applied -- it is stale relative to sequence 10.
        metrics.consume(_env(3, _roster(_session("Alice", hwnd=2))))
        assert _row(metrics.snapshot(13, HEALTH), "Alice").dps == 0

    def test_stale_source_lifecycle_does_not_roll_back(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice", generation=1)))
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        assert _row(metrics.snapshot(4, HEALTH), "Alice").dps == 10
        # An older lifecycle envelope (sequence 2 already applied at seq 2;
        # this one is sequence 2 exactly again, i.e. not newer) must not
        # unbind or otherwise roll the state back.
        metrics.consume(_env(2, _lifecycle("Alice", generation=1, active=False)))
        assert _row(metrics.snapshot(5, HEALTH), "Alice").dps == 10

    def test_unknown_character_lifecycle_and_fact_are_ignored(self):
        metrics, _, _ = _metrics()
        # No roster ever mentioned "Ghost" -- nothing to bind against.
        metrics.consume(_env(1, _lifecycle("Ghost")))
        metrics.consume(_env(2, _damage("Ghost", 50, NOW)))
        snap = metrics.snapshot(3, HEALTH)
        assert snap.rows == ()

    def test_changed_client_session_clears_damage_and_tackle(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice", hwnd=1))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        metrics.consume(_env(4, _tackle("Alice", NOW)))
        metrics.consume(_env(5, _damage("Alice", 250, NOW, kind="incoming_damage")))
        snap = metrics.snapshot(6, HEALTH)
        row = _row(snap, "Alice")
        assert row.dps == 10
        assert row.incoming_dps == 25
        assert row.ewar == (TACKLE_TAG,)

        # A relog: same character name, new session (different hwnd).
        metrics.consume(_env(7, _roster(_session("Alice", hwnd=2))))
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.dps is None
        assert row.incoming_dps is None
        assert row.log_status == NO_LOG
        assert row.ewar == ()

        # The OLD source's facts, actually consumed AFTER the session
        # already changed, must be rejected outright -- there is no bound
        # source for the new session yet, so neither direction can
        # silently reappear once one binds.
        metrics.consume(_env(9, _damage("Alice", 999, NOW)))
        metrics.consume(_env(10, _damage("Alice", 999, NOW, kind="incoming_damage")))
        row = _row(metrics.snapshot(11, HEALTH), "Alice")
        assert row.dps is None
        assert row.incoming_dps is None
        assert row.log_status == NO_LOG

        # Rebinding the new session must start from a clean deque/deadline:
        # a fact for the OLD source generation/identity must stay rejected,
        # and the OLD facts consumed above must not have been queued for
        # later delivery once binding happens.
        metrics.consume(_env(12, _lifecycle("Alice", generation=2)))
        row = _row(metrics.snapshot(13, HEALTH), "Alice")
        assert row.dps == 0
        assert row.incoming_dps == 0
        assert row.ewar == ()

    def test_changed_source_generation_clears_damage_and_tackle(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice", generation=1)))
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        metrics.consume(_env(4, _tackle("Alice", NOW)))
        metrics.consume(_env(5, _damage("Alice", 250, NOW, kind="incoming_damage")))
        row = _row(metrics.snapshot(6, HEALTH), "Alice")
        assert row.dps == 10
        assert row.incoming_dps == 25

        # Same character/session, but a NEW source generation (e.g. file
        # rotation/relog at the log level, roster session unchanged).
        metrics.consume(_env(7, _lifecycle("Alice", generation=2)))
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.dps == 0
        assert row.incoming_dps == 0
        assert row.ewar == ()
        assert row.log_status is None

    def test_retirement_clears_source_before_same_source_rebind(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        source_id = _source_id()
        metrics.consume(_env(2, _lifecycle("Alice", generation=1, source_id=source_id)))
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        metrics.consume(_env(4, _tackle("Alice", NOW)))
        metrics.consume(_env(5, _damage("Alice", 250, NOW, kind="incoming_damage")))
        snap = metrics.snapshot(6, HEALTH)
        row = _row(snap, "Alice")
        assert row.dps == 10
        assert row.incoming_dps == 25
        assert row.ewar == (TACKLE_TAG,)

        # The source retires (folder loss, character logged out of the
        # gamelog stream, etc.) -- same generation/source_id, just inactive.
        metrics.consume(
            _env(
                7,
                _lifecycle("Alice", generation=1, source_id=source_id, active=False),
            )
        )
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.dps is None
        assert row.incoming_dps is None
        assert row.log_status == NO_LOG
        assert row.ewar == ()

        # A later active lifecycle reuses the EXACT SAME generation/source_id
        # (a legitimate request_source republish, not a bug). Because
        # source_generation/source_id were cleared on retirement, the
        # "changed source" check still fires and the old damage/tackle
        # cannot leak through as if they belonged to this fresh bind.
        metrics.consume(_env(9, _lifecycle("Alice", generation=1, source_id=source_id)))
        row = _row(metrics.snapshot(10, HEALTH), "Alice")
        assert row.dps == 0
        assert row.incoming_dps == 0
        assert row.ewar == ()
        assert row.log_status is None

    def test_removed_client_clears_row_and_state(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        assert _row(metrics.snapshot(4, HEALTH), "Alice").dps == 10

        # Alice logs out: roster no longer mentions her.
        metrics.consume(_env(5, _roster()))
        snap = metrics.snapshot(6, HEALTH)
        assert snap.rows == ()

        # She logs back in: a brand-new session must start clean, NO LOG.
        metrics.consume(_env(7, _roster(_session("Alice", hwnd=9))))
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.dps is None
        assert row.log_status == NO_LOG

    def test_unnamed_client_produces_no_row(self):
        metrics, _, _ = _metrics()
        unnamed = RosterClient(
            hwnd=1, pid=1, title="Select Character", character=None, session=None
        )
        metrics.consume(_env(1, RosterSnapshot(generation=1, clients=(unnamed,))))
        assert metrics.snapshot(2, HEALTH).rows == ()

    def test_rows_sorted_case_insensitively(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("bob"), _session("Alice"))))
        snap = metrics.snapshot(2, HEALTH)
        assert [r.character for r in snap.rows] == ["Alice", "bob"]

    def test_metric_only_updates_keep_existing_membership_order(self):
        metrics, _, _ = _metrics()
        metrics.consume(_env(1, _roster(_session("bob"), _session("Alice"))))
        metrics.consume(_env(2, _lifecycle("bob")))
        metrics.consume(_env(3, _lifecycle("Alice")))
        before = [r.character for r in metrics.snapshot(4, HEALTH).rows]

        metrics.consume(_env(5, _damage("bob", 500, NOW)))
        metrics.consume(_env(6, _damage("Alice", 50, NOW, kind="incoming_damage")))
        after = [r.character for r in metrics.snapshot(7, HEALTH).rows]

        assert before == ["Alice", "bob"]
        assert after == before


# ---------------------------------------------------------------------------
# Fixed-window DPS
# ---------------------------------------------------------------------------


class TestDps:
    def _bound(self, metrics_and_boxes):
        metrics, utc_box, mono_box = metrics_and_boxes
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc_box, mono_box

    def test_half_up_rounding(self):
        metrics, _, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 105, NOW)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 11  # 105 / 10 = 10.5 -> half-up -> 11

    def test_exact_ten_seconds_old_excluded(self):
        metrics, utc_box, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        utc_box[0] = NOW + datetime.timedelta(seconds=10)
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 0

    def test_just_inside_ten_seconds_included(self):
        metrics, utc_box, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        utc_box[0] = (
            NOW + datetime.timedelta(seconds=10) - datetime.timedelta(microseconds=1)
        )
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 10

    def test_exactly_now_included(self):
        metrics, _, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 10

    def test_fixed_denominator_ten(self):
        metrics, _, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 20, NOW)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 2  # 20 / 10, not 20 / 1

    def test_one_second_snapshot_decay(self):
        metrics, utc_box, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        assert _row(metrics.snapshot(4, HEALTH), "Alice").dps == 10
        utc_box[0] = NOW + datetime.timedelta(seconds=1)
        assert _row(metrics.snapshot(5, HEALTH), "Alice").dps == 10
        utc_box[0] = NOW + datetime.timedelta(seconds=10, microseconds=1)
        assert _row(metrics.snapshot(6, HEALTH), "Alice").dps == 0

    def test_zero_versus_none_preserved(self):
        metrics, _, _ = self._bound(_metrics())
        # Bound, no damage yet: a real observed zero.
        assert _row(metrics.snapshot(3, HEALTH), "Alice").dps == 0

        metrics2, _, _ = _metrics()
        metrics2.consume(_env(1, _roster(_session("Bob"))))
        # Never bound: unmeasured, not zero.
        row = _row(metrics2.snapshot(2, HEALTH), "Bob")
        assert row.dps is None
        assert row.log_status == NO_LOG

    def test_damage_more_than_ten_seconds_old_rejected_at_ingestion(self):
        metrics, _, _ = self._bound(_metrics())
        old = NOW - datetime.timedelta(seconds=30)
        metrics.consume(_env(3, _damage("Alice", 100, old)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 0

    def test_future_within_two_seconds_is_clamped(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=2)
        metrics.consume(_env(3, _damage("Alice", 100, future)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        # Clamped to "now" -- fully inside the window, contributes fully.
        assert row.dps == 10
        assert metrics.snapshot(5, HEALTH).metric_error is None

    def test_future_more_than_two_seconds_is_rejected_with_metric_error(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=2, microseconds=1)
        metrics.consume(_env(3, _damage("Alice", 100, future)))
        snap = metrics.snapshot(4, HEALTH)
        row = _row(snap, "Alice")
        assert row.dps == 0
        assert snap.metric_error is not None

    def test_later_accepted_timestamp_clears_metric_error(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _damage("Alice", 100, future)))
        assert metrics.snapshot(4, HEALTH).metric_error is not None
        metrics.consume(_env(5, _damage("Alice", 50, NOW)))
        assert metrics.snapshot(6, HEALTH).metric_error is None


# ---------------------------------------------------------------------------
# Incoming DPS: independent accumulation/decay from outgoing
# ---------------------------------------------------------------------------


class TestIncomingDps:
    def _bound(self, metrics_and_boxes):
        metrics, utc_box, mono_box = metrics_and_boxes
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc_box, mono_box

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
        metrics, _, _ = self._bound(_metrics())
        # Bound row: a real observed zero in both directions.
        row = _row(metrics.snapshot(3, HEALTH), "Alice")
        assert row.dps == 0
        assert row.incoming_dps == 0

        metrics2, _, _ = _metrics()
        metrics2.consume(_env(1, _roster(_session("Bob"))))
        # Never bound: unmeasured in both directions, not zero.
        row = _row(metrics2.snapshot(2, HEALTH), "Bob")
        assert row.dps is None
        assert row.incoming_dps is None
        assert row.log_status == NO_LOG

    def test_incoming_half_up_rounding(self):
        metrics, _, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 105, NOW, kind="incoming_damage")))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.incoming_dps == 11  # 105 / 10 = 10.5 -> half-up -> 11

    def test_incoming_exact_ten_seconds_old_excluded(self):
        metrics, utc_box, _ = self._bound(_metrics())
        metrics.consume(_env(3, _damage("Alice", 100, NOW, kind="incoming_damage")))
        utc_box[0] = NOW + datetime.timedelta(seconds=10)
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.incoming_dps == 0

    def test_incoming_future_within_two_seconds_is_clamped(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=2)
        metrics.consume(_env(3, _damage("Alice", 100, future, kind="incoming_damage")))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.incoming_dps == 10
        assert metrics.snapshot(5, HEALTH).metric_error is None

    def test_incoming_future_more_than_two_seconds_is_rejected_with_direction_specific_error(
        self,
    ):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=2, microseconds=1)
        metrics.consume(_env(3, _damage("Alice", 100, future, kind="incoming_damage")))
        snap = metrics.snapshot(4, HEALTH)
        row = _row(snap, "Alice")
        assert row.incoming_dps == 0
        assert snap.metric_error is not None
        assert "incoming" in snap.metric_error

        metrics2, _, _ = self._bound(_metrics())
        metrics2.consume(_env(3, _damage("Alice", 100, future, kind="outgoing_damage")))
        outgoing_error = metrics2.snapshot(4, HEALTH).metric_error
        assert outgoing_error is not None
        assert outgoing_error != snap.metric_error

    def test_accepted_incoming_clears_metric_error_from_future_outgoing(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _damage("Alice", 100, future, kind="outgoing_damage")))
        assert metrics.snapshot(4, HEALTH).metric_error is not None
        metrics.consume(_env(5, _damage("Alice", 50, NOW, kind="incoming_damage")))
        assert metrics.snapshot(6, HEALTH).metric_error is None

    def test_accepted_outgoing_clears_metric_error_from_future_incoming(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _damage("Alice", 100, future, kind="incoming_damage")))
        assert metrics.snapshot(4, HEALTH).metric_error is not None
        metrics.consume(_env(5, _damage("Alice", 50, NOW, kind="outgoing_damage")))
        assert metrics.snapshot(6, HEALTH).metric_error is None

    def test_accepted_ewar_clears_metric_error_from_future_incoming(self):
        metrics, _, _ = self._bound(_metrics())
        future = NOW + datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _damage("Alice", 100, future, kind="incoming_damage")))
        assert metrics.snapshot(4, HEALTH).metric_error is not None
        metrics.consume(_env(5, _tackle("Alice", NOW)))
        assert metrics.snapshot(6, HEALTH).metric_error is None


# ---------------------------------------------------------------------------
# Fact sequencing: staleness/duplication independent of lifecycle binding
# ---------------------------------------------------------------------------


class TestFactSequencing:
    def _bound(self, metrics_and_boxes):
        metrics, utc_box, mono_box = metrics_and_boxes
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc_box, mono_box

    def test_duplicate_fact_sequence_does_not_double_count_dps(self):
        metrics, _, _ = self._bound(_metrics())
        duplicate_envelope = _env(3, _damage("Alice", 100, NOW))
        metrics.consume(duplicate_envelope)
        # The exact same envelope (same sequence) delivered twice -- a
        # redelivery, not a new fact.
        metrics.consume(duplicate_envelope)
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.dps == 10  # not 20

    def test_out_of_order_fact_does_not_roll_back_ewar_activity(self):
        metrics, _, mono_box = self._bound(_metrics(mono=100.0))
        # Sequence 5 is accepted first with a full activity window.
        metrics.consume(_env(5, _tackle("Alice", NOW)))
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == (TACKLE_TAG,)

        # An OLDER-sequence fact arrives late (e.g. a delayed filesystem
        # read) carrying a much shorter remaining lifetime. Even though its
        # sequence (4) is newer than the lifecycle bind (2), it is not newer
        # than the last ACCEPTED fact (5) and must be rejected -- it must
        # not roll the deadline backward to its own, shorter, remainder.
        stale_occurred_at = NOW - datetime.timedelta(seconds=29)  # ~1s if applied
        metrics.consume(_env(4, _tackle("Alice", stale_occurred_at)))

        # Past when the rejected stale fact would have expired, but well
        # before the accepted activity window ends at mono 130.0.
        mono_box[0] = 101.5
        assert _row(metrics.snapshot(7, HEALTH), "Alice").ewar == (TACKLE_TAG,)

    def test_rejected_future_fact_does_not_consume_sequence(self):
        metrics, _, _ = self._bound(_metrics())
        # Rejected: more than two seconds in the future.
        far_future = NOW + datetime.timedelta(seconds=3)
        metrics.consume(_env(5, _damage("Alice", 999, far_future)))
        row = _row(metrics.snapshot(6, HEALTH), "Alice")
        assert row.dps == 0
        assert metrics.snapshot(7, HEALTH).metric_error is not None

        # A corrected fact reusing the SAME sequence number is still
        # accepted: the rejected far-future fact never advanced
        # last_fact_sequence, so this is the chosen behaviour, not an
        # accident of a coincidentally-higher sequence.
        metrics.consume(_env(5, _damage("Alice", 100, NOW)))
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.dps == 10
        assert metrics.snapshot(9, HEALTH).metric_error is None

    def test_rejected_future_incoming_fact_does_not_consume_sequence(self):
        metrics, _, _ = self._bound(_metrics())
        # Rejected: more than two seconds in the future.
        far_future = NOW + datetime.timedelta(seconds=3)
        metrics.consume(
            _env(5, _damage("Alice", 999, far_future, kind="incoming_damage"))
        )
        row = _row(metrics.snapshot(6, HEALTH), "Alice")
        assert row.incoming_dps == 0
        assert metrics.snapshot(7, HEALTH).metric_error is not None

        # A corrected incoming fact reusing the SAME sequence number is
        # still accepted: the rejected far-future fact never advanced
        # last_fact_sequence.
        metrics.consume(_env(5, _damage("Alice", 100, NOW, kind="incoming_damage")))
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.incoming_dps == 10
        assert metrics.snapshot(9, HEALTH).metric_error is None


# ---------------------------------------------------------------------------
# Incoming tackle
# ---------------------------------------------------------------------------


class TestTackle:
    def _bound(self, metrics_and_boxes):
        metrics, utc_box, mono_box = metrics_and_boxes
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc_box, mono_box

    def test_remaining_lifetime_from_occurred_at(self):
        metrics, _, mono_box = self._bound(_metrics(mono=100.0))
        occurred_at = NOW - datetime.timedelta(seconds=3)  # 27s remaining
        metrics.consume(_env(3, _tackle("Alice", occurred_at)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.ewar == (TACKLE_TAG,)
        mono_box[0] = 100.0 + 26.999
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == (TACKLE_TAG,)
        mono_box[0] = 100.0 + 27.001
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == ()

    def test_non_positive_remainder_ignored(self):
        metrics, _, _ = self._bound(_metrics(mono=100.0))
        occurred_at = NOW - datetime.timedelta(seconds=30, milliseconds=1)
        metrics.consume(_env(3, _tackle("Alice", occurred_at)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.ewar == ()

    def test_future_event_never_exceeds_thirty_seconds(self):
        metrics, _, mono_box = self._bound(_metrics(mono=100.0))
        occurred_at = NOW + datetime.timedelta(seconds=3)
        metrics.consume(_env(3, _tackle("Alice", occurred_at)))
        mono_box[0] = 100.0 + 29.999
        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == (TACKLE_TAG,)
        mono_box[0] = 100.0 + 30.001
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_accepted_refresh_moves_the_deadline(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _tackle("Alice", NOW)))
        mono_box[0] = 120.0
        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == (TACKLE_TAG,)

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        metrics.consume(_env(5, _tackle("Alice", utc_box[0])))

        mono_box[0] = 130.001
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == (TACKLE_TAG,)
        mono_box[0] = 149.999
        assert _row(metrics.snapshot(7, HEALTH), "Alice").ewar == (TACKLE_TAG,)
        mono_box[0] = 150.001
        assert _row(metrics.snapshot(8, HEALTH), "Alice").ewar == ()

    def test_expiry_without_another_fact(self):
        metrics, _, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _tackle("Alice", NOW)))
        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == (TACKLE_TAG,)
        mono_box[0] = 130.001
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_fact_for_unbound_or_wrong_source_is_ignored(self):
        metrics, _, _ = self._bound(_metrics(mono=100.0))
        wrong_source = _source_id(path="C:/logs/other.txt")
        metrics.consume(_env(3, _tackle("Alice", NOW, source_id=wrong_source)))
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.ewar == ()

    def test_valid_tackle_clears_metric_error_from_future_damage(self):
        metrics, _, _ = self._bound(_metrics(mono=100.0))
        future = NOW + datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _damage("Alice", 100, future)))
        assert metrics.snapshot(4, HEALTH).metric_error is not None

        metrics.consume(_env(5, _tackle("Alice", NOW)))
        snap = metrics.snapshot(6, HEALTH)
        assert snap.metric_error is None
        assert _row(snap, "Alice").ewar == (TACKLE_TAG,)


class TestSpecificEwarAndActivity:
    def _bound(self, metrics_and_boxes):
        metrics, utc_box, mono_box = metrics_and_boxes
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc_box, mono_box

    def test_scram_point_and_neut_are_distinct_and_can_coexist(self):
        metrics, _, _ = self._bound(_metrics(mono=100.0))

        metrics.consume(_env(3, _ewar("Alice", "incoming_point", NOW)))
        metrics.consume(_env(4, _ewar("Alice", "incoming_scram", NOW)))
        metrics.consume(_env(5, _ewar("Alice", "incoming_neut", NOW, amount=0)))

        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == (
            "SCRAM",
            "POINT",
            "NEUT",
        )

    def test_ewar_clears_after_thirty_seconds_without_combat_activity(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_point", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=29, milliseconds=999)
        mono_box[0] = 129.999
        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == ("POINT",)

        utc_box[0] = NOW + datetime.timedelta(seconds=30)
        mono_box[0] = 130.0
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_outgoing_damage_does_not_refresh_observed_ewar(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(_env(4, _damage("Alice", 100, utc_box[0])))

        mono_box[0] = 130.0
        row = _row(metrics.snapshot(5, HEALTH), "Alice")
        assert row.ewar == ()
        assert row.combat.expires_at_mono == 150.0
        assert combat_row_visible(row, now_mono=149.999)
        assert not combat_row_visible(row, now_mono=150.0)

    def test_incoming_damage_does_not_refresh_observed_ewar(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(
            _env(4, _damage("Alice", 100, utc_box[0], kind="incoming_damage"))
        )

        mono_box[0] = 130.0
        # Damage in either direction must not extend the SCRAM deadline to 150.
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_delayed_ewar_uses_event_time_not_ingestion_time(self):
        metrics, _, mono_box = self._bound(_metrics(mono=100.0))
        occurred_at = NOW - datetime.timedelta(seconds=5)
        metrics.consume(_env(3, _ewar("Alice", "incoming_neut", occurred_at)))

        mono_box[0] = 124.999
        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == ("NEUT",)
        mono_box[0] = 125.0
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_damage_outside_dps_window_still_refreshes_combat_activity(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_point", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(
            _env(
                4,
                _damage(
                    "Alice",
                    100,
                    NOW + datetime.timedelta(seconds=5),
                ),
            )
        )

        assert _row(metrics.snapshot(5, HEALTH), "Alice").dps == 0
        mono_box[0] = 134.999
        row = _row(metrics.snapshot(6, HEALTH), "Alice")
        assert row.ewar == ()
        assert row.combat.expires_at_mono == 135.0
        assert combat_row_visible(row, now_mono=134.999)
        assert not combat_row_visible(row, now_mono=135.0)

    def test_delayed_fact_does_not_shorten_newer_combat_activity(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(_env(4, _damage("Alice", 100, utc_box[0])))
        metrics.consume(
            _env(
                5,
                _ewar(
                    "Alice",
                    "incoming_neut",
                    NOW + datetime.timedelta(seconds=5),
                ),
            )
        )

        mono_box[0] = 130.0
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == ("NEUT",)
        mono_box[0] = 135.0
        row = _row(metrics.snapshot(7, HEALTH), "Alice")
        assert row.ewar == ()
        assert row.combat.expires_at_mono == 150.0
        assert combat_row_visible(row, now_mono=149.999)

    def test_new_combat_after_unobserved_expiry_does_not_resurrect_old_ewar(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        # No snapshot observes the 30-second expiry before a later fight starts.
        utc_box[0] = NOW + datetime.timedelta(seconds=40)
        mono_box[0] = 140.0
        metrics.consume(_env(4, _damage("Alice", 100, utc_box[0])))

        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ()

    def test_new_ewar_after_unobserved_expiry_keeps_only_the_new_kind(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_point", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=40)
        mono_box[0] = 140.0
        metrics.consume(_env(4, _ewar("Alice", "incoming_neut", utc_box[0])))

        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ("NEUT",)

    def test_ewar_older_than_activity_window_is_ignored(self):
        metrics, _, _ = self._bound(_metrics(mono=100.0))
        metrics.consume(
            _env(
                3,
                _ewar(
                    "Alice",
                    "incoming_neut",
                    NOW - datetime.timedelta(seconds=30),
                ),
            )
        )

        assert _row(metrics.snapshot(4, HEALTH), "Alice").ewar == ()


# ---------------------------------------------------------------------------
# Row activity and lifetime fencing
# ---------------------------------------------------------------------------


class TestRowActivity:
    def _bound(self):
        metrics, utc, mono = _metrics(mono=100.0)
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc, mono

    @pytest.mark.parametrize("kind", ["incoming_damage", "outgoing_damage"])
    @pytest.mark.parametrize("amount", [0, 1])
    def test_zero_dps_still_has_thirty_second_activity(self, kind, amount):
        metrics, utc, mono = self._bound()
        metrics.consume(_env(3, _damage("Alice", amount, NOW, kind=kind)))
        metrics.consume(
            _env(4, _roster(_session("zulu"), _session("Alice"), _session("bob")))
        )
        snapshot = metrics.snapshot(5, HEALTH)
        row = _row(snapshot, "Alice")
        assert (row.dps, row.incoming_dps) == (0, 0)
        assert row.combat is not None
        token, sequence = row.combat.observation_id
        assert isinstance(token, UUID)
        assert sequence == 3
        assert row.combat == CombatActivity(130.0, (token, 3))
        assert combat_row_visible(row, now_mono=129.999)
        assert not combat_row_visible(row, now_mono=130.0)

        utc[0] = NOW + datetime.timedelta(seconds=30)
        mono[0] = 130.0
        expired = metrics.snapshot(6, HEALTH)
        assert [r.character for r in expired.rows] == ["Alice", "bob", "zulu"]
        assert _row(expired, "Alice").combat == row.combat
        for name in ("bob", "zulu"):
            missing = _row(expired, name)
            assert (missing.dps, missing.incoming_dps, missing.log_status) == (
                None,
                None,
                NO_LOG,
            )
            assert missing.combat == CombatActivity()
            assert not combat_row_visible(missing, now_mono=100.0)

    @pytest.mark.parametrize("kind", ["incoming_damage", "outgoing_damage"])
    @pytest.mark.parametrize(
        "age, deadline", [(10, 120.0), (15, 115.0), (29.999, 100.00099999999999)]
    )
    def test_delayed_damage_has_only_event_time_remainder(self, kind, age, deadline):
        metrics, _, _ = self._bound()
        metrics.consume(
            _env(
                3,
                _damage("Alice", 100, NOW - datetime.timedelta(seconds=age), kind=kind),
            )
        )
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert (row.dps, row.incoming_dps) == (0, 0)
        assert row.combat is not None
        assert row.combat.expires_at_mono == deadline
        assert combat_row_visible(row, now_mono=deadline - 0.0001)
        assert not combat_row_visible(row, now_mono=deadline)

    @pytest.mark.parametrize(
        "kind, tag",
        [
            ("incoming_scram", "SCRAM"),
            ("incoming_point", "POINT"),
            ("incoming_neut", "NEUT"),
        ],
    )
    @pytest.mark.parametrize(
        "age, deadline", [(15, 115.0), (-3, 130.0), (-3600, 130.0)]
    )
    def test_accepted_ewar_produces_independent_effect_observations(
        self, kind, tag, age, deadline
    ):
        metrics, _, _ = self._bound()
        metrics.consume(
            _env(3, _ewar("Alice", kind, NOW - datetime.timedelta(seconds=age)))
        )
        row = _row(metrics.snapshot(4, HEALTH), "Alice")
        assert row.ewar == (tag,)
        assert row.combat is not None
        assert row.combat.expires_at_mono == deadline
        assert row.combat.observation_id[1] == 3
        assert row.combat.observations == (
            EffectObservation(tag, deadline, row.combat.observation_id),
        )
        assert combat_row_visible(row, now_mono=deadline - 0.001)
        assert not combat_row_visible(row, now_mono=deadline)

    @pytest.mark.parametrize("kind", ["incoming_damage", "outgoing_damage"])
    def test_damage_future_policy_applies_before_row_activity(self, kind):
        metrics, _, _ = self._bound()
        metrics.consume(
            _env(
                3,
                _damage(
                    "Alice",
                    100,
                    NOW + datetime.timedelta(seconds=2, microseconds=1),
                    kind=kind,
                ),
            )
        )
        rejected = metrics.snapshot(4, HEALTH)
        assert _row(rejected, "Alice").combat == CombatActivity()
        assert (
            rejected.metric_error
            == f"future {kind.removesuffix('_damage')} damage timestamp for Alice"
        )
        metrics.consume(
            _env(
                3, _damage("Alice", 100, NOW + datetime.timedelta(seconds=2), kind=kind)
            )
        )
        corrected = metrics.snapshot(5, HEALTH)
        row = _row(corrected, "Alice")
        assert row.combat is not None
        assert row.combat.expires_at_mono == 130.0
        assert row.combat.observation_id[1] == 3
        assert (row.dps, row.incoming_dps) == (
            (10, 0) if kind == "outgoing_damage" else (0, 10)
        )
        assert corrected.metric_error is None

    @pytest.mark.parametrize(
        "fact",
        [
            _damage("Alice", None, NOW),
            _damage("Alice", None, NOW, kind="incoming_damage"),
            _damage("Alice", 1, None),
            _damage("Alice", 1, None, kind="incoming_damage"),
            _tackle("Alice", None),
            _damage("Alice", 100, NOW - datetime.timedelta(seconds=30)),
            _damage(
                "Alice",
                100,
                NOW - datetime.timedelta(seconds=30),
                kind="incoming_damage",
            ),
            _tackle("Alice", NOW - datetime.timedelta(seconds=30)),
            _ewar("Alice", "incoming_miss", NOW),
            _ewar("Alice", "outgoing_miss", NOW),
            _ewar("Alice", "warp", NOW),
            _damage("Alice", 100, NOW, source_generation=99),
            _damage("Alice", 100, NOW, source_id=_source_id("other.txt")),
            "chatter",
        ],
    )
    def test_rejected_facts_do_not_renew_or_consume_correction_sequence(self, fact):
        metrics, _, _ = self._bound()
        metrics.consume(
            _env(3, _damage("Alice", 0, NOW - datetime.timedelta(seconds=5)))
        )
        before = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert before is not None
        assert before.expires_at_mono == 125.0
        metrics.consume(_env(5, fact))
        assert _row(metrics.snapshot(6, HEALTH), "Alice").combat == before
        metrics.consume(_env(5, _damage("Alice", 0, NOW)))
        corrected = _row(metrics.snapshot(7, HEALTH), "Alice").combat
        assert corrected == CombatActivity(130.0, (before.observation_id[0], 5))

    def test_ids_advance_only_with_deadline_and_stay_independent_per_row(self):
        metrics, utc, mono = self._bound()
        metrics.consume(_env(3, _roster(_session("Alice"), _session("bob"))))
        metrics.consume(_env(4, _lifecycle("bob")))
        metrics.consume(_env(5, _damage("Alice", 0, NOW)))
        metrics.consume(_env(6, _damage("bob", 0, NOW - datetime.timedelta(seconds=5))))
        before = metrics.snapshot(7, HEALTH)
        alice = _row(before, "Alice").combat
        bob = _row(before, "bob").combat
        assert alice is not None and bob is not None
        assert alice.expires_at_mono == 130.0
        assert bob.expires_at_mono == 125.0
        assert alice.observation_id[0] != bob.observation_id[0]
        metrics.consume(_env(8, _tackle("Alice", NOW)))  # Equal deadline.
        metrics.consume(
            _env(9, _damage("Alice", 0, NOW - datetime.timedelta(seconds=1)))
        )
        utc[0] = NOW + datetime.timedelta(seconds=10)
        mono[0] = 110.0
        metrics.consume(
            _env(9, _damage("Alice", 0, utc[0]))
        )  # Already accepted sequence.
        metrics.consume(_env(8, _damage("Alice", 0, utc[0])))  # Out of order.
        unchanged = metrics.snapshot(10, HEALTH)
        effects = (EffectObservation("SCRAM", 130.0, (alice.observation_id[0], 8)),)
        assert _row(unchanged, "Alice").combat == replace(alice, observations=effects)
        assert _row(unchanged, "bob").combat == bob
        metrics.consume(_env(11, _damage("Alice", 0, utc[0])))
        after = metrics.snapshot(12, HEALTH)
        assert _row(after, "Alice").combat == CombatActivity(
            140.0, (alice.observation_id[0], 11), effects
        )
        assert _row(after, "bob").combat == bob
        assert not combat_row_visible(_row(after, "bob"), now_mono=125.0)
        assert combat_row_visible(_row(after, "Alice"), now_mono=125.0)

    @pytest.mark.parametrize("age", [0, 15])
    def test_incoming_row_activity_does_not_extend_effects(self, age):
        metrics, utc, mono = self._bound()
        metrics.consume(_env(3, _tackle("Alice", NOW)))
        utc[0] = NOW + datetime.timedelta(seconds=20)
        mono[0] = 120.0
        metrics.consume(
            _env(
                4,
                _damage(
                    "Alice",
                    0,
                    utc[0] - datetime.timedelta(seconds=age),
                    kind="incoming_damage",
                ),
            )
        )
        utc[0] = NOW + datetime.timedelta(seconds=30)
        mono[0] = 130.0
        row = _row(metrics.snapshot(5, HEALTH), "Alice")
        assert row.ewar == ()
        assert row.combat is not None
        assert row.combat.expires_at_mono == (150.0 if age == 0 else 135.0)
        assert combat_row_visible(row, now_mono=130.0)

    @pytest.mark.parametrize("kind", ["outgoing_damage", "incoming_scram"])
    def test_unchanged_roster_and_active_rebind_preserve_lifetime(self, kind):
        metrics, utc, mono = self._bound()
        metrics.consume(_env(3, _damage("Alice", 100, NOW, kind=kind)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None
        metrics.consume(_env(5, _roster(_session("Alice"))))
        metrics.consume(_env(6, _lifecycle("Alice")))
        metrics.consume(_env(5, _lifecycle("Alice", active=False)))
        utc[0] = NOW + datetime.timedelta(seconds=1)
        mono[0] = 101.0
        metrics.consume(_env(6, _damage("Alice", 100, utc[0], kind=kind)))
        row = _row(metrics.snapshot(7, HEALTH), "Alice")
        assert row.combat == original
        assert row.dps == (10 if kind == "outgoing_damage" else 0)
        if kind == "incoming_scram":
            assert original.observations == (
                EffectObservation("SCRAM", 130.0, original.observation_id),
            )
        metrics.consume(_env(8, _damage("Alice", 0, utc[0], kind=kind)))
        new_id = (original.observation_id[0], 8)
        effects = (
            (EffectObservation("SCRAM", 131.0, new_id),)
            if kind == "incoming_scram"
            else ()
        )
        assert _row(metrics.snapshot(9, HEALTH), "Alice").combat == CombatActivity(
            131.0, new_id, effects
        )

    @pytest.mark.parametrize(
        "change",
        [
            "retire",
            "generation",
            "source",
            "hwnd",
            "pid",
            "session_generation",
            "remove",
            "reset",
        ],
    )
    @pytest.mark.parametrize("kind", ["outgoing_damage", "incoming_scram"])
    def test_invalidation_clears_activity_and_fences_stale_facts(self, change, kind):
        metrics, _, _ = self._bound()
        metrics.consume(_env(3, _damage("Alice", 100, NOW, kind=kind)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None
        if kind == "incoming_scram":
            assert original.observations == (
                EffectObservation("SCRAM", 130.0, original.observation_id),
            )
        generation, source_id = 1, _source_id()
        if change == "retire":
            metrics.consume(_env(10, _lifecycle("Alice", active=False)))
        elif change in ("generation", "source"):
            generation = 2 if change == "generation" else 1
            source_id = _source_id("new.txt") if change == "source" else _source_id()
            metrics.consume(
                _env(
                    10, _lifecycle("Alice", generation=generation, source_id=source_id)
                )
            )
        else:
            if change == "reset":
                metrics.reset()
            elif change == "remove":
                metrics.consume(_env(9, _roster()))
            if change in ("reset", "remove"):
                assert metrics.snapshot(10, HEALTH).rows == ()
            session = _session(
                "Alice",
                hwnd=2 if change == "hwnd" else 1,
                pid=101 if change == "pid" else 100,
                generation=2 if change == "session_generation" else 1,
            )
            metrics.consume(_env(10, _roster(session)))
        cleared = _row(metrics.snapshot(11, HEALTH), "Alice")
        assert cleared.combat == CombatActivity()
        assert not combat_row_visible(cleared, now_mono=100.0)
        # A queued old fact is either unbound, wrong-source or behind the bind.
        metrics.consume(_env(9, _damage("Alice", 999, NOW, kind=kind)))
        metrics.consume(
            _env(12, _lifecycle("Alice", generation=generation, source_id=source_id))
        )
        metrics.consume(
            _env(
                11,
                _damage(
                    "Alice",
                    999,
                    NOW,
                    source_generation=generation,
                    source_id=source_id,
                    kind=kind,
                ),
            )
        )
        if change in ("generation", "source"):
            # Even a new envelope sequence cannot authorize an old source identity.
            metrics.consume(_env(13, _damage("Alice", 999, NOW, kind=kind)))
        rebound = _row(metrics.snapshot(13, HEALTH), "Alice")
        assert rebound.combat == CombatActivity()
        assert (rebound.dps, rebound.incoming_dps, rebound.ewar) == (0, 0, ())
        metrics.consume(
            _env(
                14,
                _damage(
                    "Alice",
                    0,
                    NOW,
                    source_generation=generation,
                    source_id=source_id,
                    kind=kind,
                ),
            )
        )
        new = _row(metrics.snapshot(15, HEALTH), "Alice").combat
        assert new is not None
        assert new.expires_at_mono == 130.0
        assert new.observation_id[0] != original.observation_id[0]
        assert new.observation_id[1] == 14
        if kind == "incoming_scram":
            assert new.observations == (
                EffectObservation("SCRAM", 130.0, new.observation_id),
            )
        assert original.expires_at_mono == 130.0  # Cached evidence stays detached.

    @pytest.mark.parametrize("kind", ["outgoing_damage", "incoming_scram"])
    def test_full_reset_cannot_reuse_id_even_with_same_source_and_sequence(self, kind):
        metrics, _, _ = self._bound()
        metrics.consume(_env(3, _damage("Alice", 0, NOW, kind=kind)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        metrics.reset()
        metrics.consume(
            _env(3, _damage("Alice", 999, NOW, kind=kind))
        )  # No roster: drop, never queue.
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        assert _row(metrics.snapshot(3, HEALTH), "Alice").combat == CombatActivity()
        metrics.consume(_env(3, _damage("Alice", 0, NOW, kind=kind)))
        new = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None and new is not None
        assert new.observation_id[1] == original.observation_id[1] == 3
        assert new.observation_id[0] != original.observation_id[0]
        if kind == "incoming_scram":
            assert original.observations == (
                EffectObservation("SCRAM", 130.0, original.observation_id),
            )
            assert new.observations == (
                EffectObservation("SCRAM", 130.0, new.observation_id),
            )

    def test_snapshot_samples_once_and_readers_never_rewrite_measurement_time(self):
        ticks = iter([123.0, 124.0, 125.0])
        metrics = FleetMetrics(_clock=lambda: next(ticks), _utc_now=lambda: NOW)
        metrics.consume(_env(1, _roster(_session("Alice"), _session("bob"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        first = metrics.snapshot(3, HEALTH)
        assert first.sampled_at_mono == 123.0
        row = _row(first, "Alice")
        assert read_combat(row, now_mono=500.0) == CombatActivity()
        assert not combat_row_visible(row, now_mono=500.0)
        second = metrics.snapshot(4, HEALTH)
        assert second.sampled_at_mono == 124.0
        assert first.sampled_at_mono == 123.0
        metrics.reset()
        empty = metrics.snapshot(5, HEALTH)
        assert empty.rows == ()
        assert empty.sampled_at_mono == 125.0


# ---------------------------------------------------------------------------
# Conservative producer deadlines — exercise ingestion, not a helper oracle.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", ["outgoing_damage", "incoming_damage", "incoming_scram"]
)
@pytest.mark.parametrize(
    "mono, remaining_us, deadline",
    [
        pytest.param(0.1, 30_000_000, 30.099999999999998, id="addition-up"),
        pytest.param(0.2, 30_000_000, 30.2, id="addition-down"),
        pytest.param(0.5, 30_000_000, 30.5, id="exact"),
        pytest.param(0.0, 29_800_000, 29.799999999999997, id="duration-up"),
        pytest.param(0.0, 29_900_000, 29.9, id="duration-down"),
        pytest.param(0.1, 29_876_543, 29.976543, id="delayed-microseconds"),
        pytest.param(100.0, 1_000, 100.00099999999999, id="last-millisecond"),
        pytest.param(0.0, 1, 0.000001, id="last-microsecond"),
        pytest.param(
            nextafter(2.0, -inf), 30_000_000, 31.999999999999996, id="below-32"
        ),
        pytest.param(2.0, 30_000_000, 32.0, id="at-32"),
        pytest.param(nextafter(2.0, inf), 30_000_000, 32.0, id="above-32"),
        pytest.param(
            nextafter(34.0, -inf), 30_000_000, 63.99999999999999, id="below-64"
        ),
        pytest.param(34.0, 30_000_000, 64.0, id="at-64"),
        pytest.param(nextafter(34.0, inf), 30_000_000, 64.0, id="above-64"),
        pytest.param(
            nextafter(2.1, -inf),
            29_900_000,
            31.999999999999996,
            id="delayed-below-32",
        ),
        pytest.param(2.1, 29_900_000, 32.0, id="delayed-above-32"),
        pytest.param(
            -29.0, 29_100_000, 0.09999999999999999, id="duration-cancellation"
        ),
    ],
)
def test_producer_deadline_is_greatest_float_not_after_exact_lifetime(
    kind, mono, remaining_us, deadline
):
    metrics, _, mono_box = _metrics(mono=mono)
    metrics.consume(_env(1, _roster(_session("Alice"))))
    metrics.consume(_env(2, _lifecycle("Alice")))
    remaining = datetime.timedelta(microseconds=remaining_us)
    occurred_at = NOW - datetime.timedelta(seconds=30) + remaining
    fact = (
        _tackle("Alice", occurred_at)
        if kind == "incoming_scram"
        else _damage("Alice", 100, occurred_at, kind=kind)
    )
    metrics.consume(_env(3, fact))
    snapshot = metrics.snapshot(4, HEALTH)
    row = _row(snapshot, "Alice")
    assert snapshot.metric_error is None
    assert snapshot.sampled_at_mono == mono
    assert row.combat.expires_at_mono == deadline
    assert row.combat.observation_id[1] == 3
    # Independent integer timedelta decomposition: total_seconds() is itself
    # rounded and cannot certify that the original lifetime was not extended.
    seconds, subsecond = divmod(remaining, datetime.timedelta(seconds=1))
    exact = Fraction(mono) + seconds + Fraction(subsecond.microseconds, 1_000_000)
    assert Fraction(deadline) <= exact < Fraction(nextafter(deadline, inf))
    if kind == "incoming_scram":
        assert row.combat.observations == (
            EffectObservation("SCRAM", deadline, row.combat.observation_id),
        )
    else:
        assert row.combat.observations == ()
    assert combat_row_visible(row, now_mono=nextafter(deadline, -inf))
    assert not combat_row_visible(row, now_mono=deadline)
    mono_box[0] = deadline
    expired = _row(metrics.snapshot(5, HEALTH), "Alice")
    assert expired.combat.expires_at_mono == deadline
    assert expired.combat.observation_id == row.combat.observation_id
    assert expired.combat.observations == ()
    assert expired.ewar == ()


# ---------------------------------------------------------------------------
# Independent effect retention
# ---------------------------------------------------------------------------


_NAME_VECTORS = {
    vector["id"]: vector
    for vector in json.loads(
        (Path(__file__).parent / "fixtures" / "fleet-combat-v2.json").read_text(
            encoding="utf-8"
        )
    )["names"]
}


def _advance(utc, mono, seconds):
    utc[0] = NOW + datetime.timedelta(seconds=seconds)
    mono[0] = float(seconds)
    return utc[0]


def _observe(metrics, sequence, kind, name, occurred_at=NOW, **kwargs):
    metrics.consume(
        _env(
            sequence,
            _ewar(
                "Alice",
                f"incoming_{kind.lower()}",
                occurred_at,
                observed_name=name,
                **kwargs,
            ),
        )
    )


def _effects(metrics):
    row = _row(metrics.snapshot(1000, HEALTH), "Alice")
    assert row.combat is not None
    effects = row.combat.observations
    assert all(e.expires_at_mono <= row.combat.expires_at_mono for e in effects)
    by_slot = {(e.kind, e.name): e for e in effects}
    assert len(by_slot) == len(effects)
    assert tuple(dict.fromkeys(e.kind for e in effects)) == row.ewar
    return by_slot


class TestEffectRetention:
    def _bound(self):
        metrics, utc, mono = _metrics()
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        return metrics, utc, mono

    @pytest.mark.parametrize("direction", ["outgoing_damage", "incoming_damage"])
    def test_named_scrams_and_damage_expire_at_30_40_50(self, direction):
        metrics, utc, mono = self._bound()
        _observe(metrics, 3, "SCRAM", "A")
        _observe(metrics, 4, "SCRAM", "B", _advance(utc, mono, 10))
        before = _effects(metrics)
        assert set(before) == {("SCRAM", "A"), ("SCRAM", "B")}
        token = before["SCRAM", "A"].observation_id[0]
        assert before == {
            ("SCRAM", "A"): EffectObservation("SCRAM", 30.0, (token, 3), "A"),
            ("SCRAM", "B"): EffectObservation("SCRAM", 40.0, (token, 4), "B"),
        }
        metrics.consume(
            _env(5, _damage("Alice", 0, _advance(utc, mono, 20), kind=direction))
        )
        assert _effects(metrics) == before
        cached = metrics.snapshot(6, HEALTH)
        row = _row(cached, "Alice")
        assert row.combat == CombatActivity(50.0, (token, 5), tuple(before.values()))
        for seconds, expected in (
            (29.999, before),
            (30, {("SCRAM", "B"): before["SCRAM", "B"]}),
            (40, {}),
            (50, {}),
        ):
            _advance(utc, mono, seconds)
            assert _effects(metrics) == expected
            assert read_combat(row, now_mono=seconds).observations == tuple(
                expected.values()
            )
            assert combat_row_visible(row, now_mono=seconds) is (seconds < 50)
        assert cached.sampled_at_mono == 20.0
        assert row.combat.observations == tuple(before.values())

    def test_same_name_point_scram_and_zero_neut_are_independent(self):
        metrics, utc, mono = self._bound()
        _observe(metrics, 3, "POINT", "A")
        _observe(metrics, 4, "SCRAM", "A", _advance(utc, mono, 5))
        _observe(metrics, 5, "NEUT", "A", _advance(utc, mono, 10), amount=0)
        before = _effects(metrics)
        assert [(e.kind, e.name, e.expires_at_mono) for e in before.values()] == [
            ("SCRAM", "A", 35.0),
            ("POINT", "A", 30.0),
            ("NEUT", None, 40.0),
        ]
        _observe(metrics, 6, "NEUT", "B", _advance(utc, mono, 15), amount=0)
        after = _effects(metrics)
        assert after["SCRAM", "A"] == before["SCRAM", "A"]
        assert after["POINT", "A"] == before["POINT", "A"]
        assert after["NEUT", None] == EffectObservation(
            "NEUT", 45.0, (before["NEUT", None].observation_id[0], 6)
        )
        for seconds, slots in (
            (30, {("SCRAM", "A"), ("NEUT", None)}),
            (35, {("NEUT", None)}),
            (45, set()),
        ):
            _advance(utc, mono, seconds)
            assert set(_effects(metrics)) == slots

    @pytest.mark.parametrize("kind", ["POINT", "SCRAM"])
    def test_unknown_does_not_gain_lifetime_from_new_named_aggressor(self, kind):
        metrics, utc, mono = self._bound()
        _observe(metrics, 3, kind, None)
        _observe(metrics, 4, kind, "B", _advance(utc, mono, 10))
        before = _effects(metrics)
        assert set(before) == {(kind, None), (kind, "B")}
        assert before[kind, None].expires_at_mono == 30.0
        assert before[kind, "B"].expires_at_mono == 40.0
        _advance(utc, mono, 30)
        assert _effects(metrics) == {(kind, "B"): before[kind, "B"]}
        _advance(utc, mono, 40)
        assert _effects(metrics) == {}

    def test_separate_named_caps_and_overflow_coalesce_without_eviction(self):
        metrics, utc, mono = self._bound()
        sequence = 2
        for kind in ("POINT", "SCRAM"):
            for i in range(LIMITS["named_per_tackle"]):
                sequence += 1
                _observe(metrics, sequence, kind, f"Pilot {i}")
        _observe(metrics, sequence + 1, "NEUT", "Ignored", amount=0)
        for i, kind in enumerate(("POINT", "SCRAM"), start=2):
            _observe(metrics, sequence + i, kind, "Overflow", _advance(utc, mono, 5))
        before = _effects(metrics)
        assert len(before) == LIMITS["observations_per_row"] == 19
        assert (
            sum(e.name is not None for e in before.values()) == LIMITS["named_per_row"]
        )
        assert list(dict.fromkeys(e.kind for e in before.values())) == list(
            LIMITS["effect_order"]
        )
        for kind in ("POINT", "SCRAM"):
            assert {e.name for e in before.values() if e.kind == kind} == {
                *(f"Pilot {i}" for i in range(LIMITS["named_per_tackle"])),
                None,
            }
        sequence += 5
        _observe(metrics, sequence, "SCRAM", "PILOT 0", _advance(utc, mono, 10))
        refreshed = _effects(metrics)
        assert refreshed["SCRAM", "Pilot 0"].expires_at_mono == 40.0
        assert refreshed["SCRAM", "Pilot 0"].observation_id[1] == sequence
        assert {k: v for k, v in refreshed.items() if k != ("SCRAM", "Pilot 0")} == {
            k: v for k, v in before.items() if k != ("SCRAM", "Pilot 0")
        }
        _observe(
            metrics, sequence + 1, "SCRAM", "Another overflow", _advance(utc, mono, 15)
        )
        overflow = _effects(metrics)
        assert overflow["SCRAM", None].expires_at_mono == 45.0
        assert {k: v for k, v in overflow.items() if k != ("SCRAM", None)} == {
            k: v for k, v in refreshed.items() if k != ("SCRAM", None)
        }
        _observe(metrics, sequence + 2, "SCRAM", None, _advance(utc, mono, 20))
        unknown = _effects(metrics)
        assert len(unknown) == LIMITS["observations_per_row"]
        assert unknown["SCRAM", None].expires_at_mono == 50.0
        assert {k: v for k, v in unknown.items() if k != ("SCRAM", None)} == {
            k: v for k, v in overflow.items() if k != ("SCRAM", None)
        }
        metrics.consume(
            _env(sequence + 3, _damage("Alice", 0, _advance(utc, mono, 25)))
        )
        assert _effects(metrics) == unknown
        _advance(utc, mono, 35)
        assert set(_effects(metrics)) == {("SCRAM", "Pilot 0"), ("SCRAM", None)}
        _advance(utc, mono, 40)
        assert set(_effects(metrics)) == {("SCRAM", None)}
        _advance(utc, mono, 50)
        assert _effects(metrics) == {}

    @pytest.mark.parametrize("kind", ["POINT", "SCRAM"])
    def test_expired_names_free_slots_before_admission_without_snapshot(self, kind):
        metrics, utc, mono = self._bound()
        for i in range(LIMITS["named_per_tackle"]):
            _observe(metrics, 3 + i, kind, f"Pilot {i}")
        sequence = 3 + LIMITS["named_per_tackle"]
        _observe(metrics, sequence, kind, "Overflow", _advance(utc, mono, 10))
        before = _effects(metrics)
        assert len(before) == LIMITS["observations_per_tackle"]
        _observe(metrics, sequence + 1, kind, "New", _advance(utc, mono, 30))
        effects = _effects(metrics)
        assert set(effects) == {(kind, None), (kind, "New")}
        assert effects[kind, None] == before[kind, None]
        assert effects[kind, "New"].expires_at_mono == 60.0

    @pytest.mark.parametrize(
        "vector_id",
        [
            "scratch-trim-nfc",
            "scratch-nbsp",
            "scratch-hangul-lvt",
            "scratch-internal-double-space",
            "scratch-sharp-s",
            "scratch-sigma",
            "scratch-64-supplementary",
            "raw-256-nfc-shrink",
            "unicode16-cyrillic-fold",
            "scratch-empty",
            "scratch-markup",
            "scratch-newline",
            "scratch-zwj",
            "scratch-surrogate",
            "scratch-private-use",
            "scratch-unassigned",
            "scratch-65-supplementary",
            "scratch-raw-cap",
        ],
    )
    def test_shared_name_vectors_normalize_before_key_or_keep_unnamed_effect(
        self, vector_id
    ):
        metrics, utc, mono = self._bound()
        vector = _NAME_VECTORS[vector_id]
        _observe(metrics, 3, "POINT", vector["input"])
        effects = _effects(metrics)
        slot = ("POINT", vector["normalized"])
        assert set(effects) == {slot}
        original = effects[slot]
        assert original.expires_at_mono == 30.0
        # Canonical folded spelling must refresh the normalized bucket, not add
        # a second name (or turn the original noncanonical input into null).
        _observe(metrics, 4, "POINT", vector["normalized_key"], _advance(utc, mono, 1))
        assert _effects(metrics) == {
            slot: EffectObservation(
                "POINT", 31.0, (original.observation_id[0], 4), vector["normalized"]
            )
        }

    def test_first_spelling_lives_until_expiry_then_next_spelling_is_admitted(self):
        metrics, utc, mono = self._bound()
        first = _NAME_VECTORS["scratch-sharp-s"]["input"]
        second = _NAME_VECTORS["scratch-sharp-s-equivalent"]["input"]
        _observe(metrics, 3, "SCRAM", first)
        _observe(metrics, 4, "SCRAM", second, _advance(utc, mono, 5))
        effects = _effects(metrics)
        assert set(effects) == {("SCRAM", "Straße")}
        assert effects["SCRAM", "Straße"].expires_at_mono == 35.0
        _observe(metrics, 5, "SCRAM", second, _advance(utc, mono, 35))
        assert set(_effects(metrics)) == {("SCRAM", "STRASSE")}

    @pytest.mark.parametrize(
        "vector_id",
        ["fold-expands-past-display-scalars", "fold-final-key-over256-bytes"],
    )
    def test_expanded_keys_remain_named_distinct_and_refreshable(self, vector_id):
        metrics, utc, mono = self._bound()
        vector = _NAME_VECTORS[vector_id]
        name = vector["input"]
        # A difference beyond the display-sized key prefix must not collide.
        other = name[:-1] + "A"
        _observe(metrics, 3, "SCRAM", name)
        _observe(metrics, 4, "SCRAM", other)
        effects = _effects(metrics)
        assert set(effects) == {("SCRAM", name), ("SCRAM", other)}
        _observe(metrics, 5, "SCRAM", name, _advance(utc, mono, 5))
        refreshed = _effects(metrics)
        assert set(refreshed) == set(effects)
        assert refreshed["SCRAM", other] == effects["SCRAM", other]
        assert refreshed["SCRAM", name].expires_at_mono == 35.0
        assert refreshed["SCRAM", name].observation_id[1] == 5

    @pytest.mark.parametrize("name", ["Pilot", None])
    def test_delayed_equal_and_older_evidence_keep_ids_and_only_later_deadline_changes(
        self, name
    ):
        metrics, utc, mono = self._bound()
        _observe(metrics, 3, "SCRAM", name)
        _observe(metrics, 4, "POINT", "Other")
        before = _effects(metrics)
        assert set(before) == {("SCRAM", name), ("POINT", "Other")}
        _advance(utc, mono, 10)
        _observe(metrics, 5, "SCRAM", name, NOW)  # Same deadline, later sequence.
        _observe(metrics, 6, "SCRAM", name, NOW - datetime.timedelta(seconds=5))
        assert _effects(metrics) == before
        # Accepted older evidence consumed sequence 6; it cannot be reused to renew.
        _observe(metrics, 6, "SCRAM", name, utc[0])
        _observe(metrics, 5, "POINT", "Stale", utc[0])
        assert _effects(metrics) == before
        _observe(metrics, 7, "SCRAM", name, utc[0])
        after = _effects(metrics)
        assert after["POINT", "Other"] == before["POINT", "Other"]
        assert after["SCRAM", name] == EffectObservation(
            "SCRAM", 40.0, (before["SCRAM", name].observation_id[0], 7), name
        )
        row = _row(metrics.snapshot(8, HEALTH), "Alice")
        assert row.combat.observation_id == after["SCRAM", name].observation_id
        assert row.combat.expires_at_mono == 40.0

    @pytest.mark.parametrize("age", [None, 30, 31])
    def test_rejected_effect_timestamp_keeps_correction_sequence_available(self, age):
        metrics, _, _ = self._bound()
        occurred_at = None if age is None else NOW - datetime.timedelta(seconds=age)
        _observe(metrics, 3, "SCRAM", "A", occurred_at)
        assert _effects(metrics) == {}
        _observe(metrics, 3, "SCRAM", "A")
        effects = _effects(metrics)
        assert set(effects) == {("SCRAM", "A")}
        assert effects["SCRAM", "A"].observation_id[1] == 3
        assert effects["SCRAM", "A"].expires_at_mono == 30.0

    def test_snapshots_and_pure_reads_ignore_utc_jumps_for_effect_lifetime(self):
        metrics, utc, mono = self._bound()
        fact = _ewar("Alice", "incoming_scram", NOW, observed_name="A")
        metrics.consume(_env(3, fact))
        _observe(metrics, 4, "POINT", "B", _advance(utc, mono, 10))
        before = _effects(metrics)
        assert len(before) == 2
        snapshot = metrics.snapshot(5, HEALTH)
        row = _row(snapshot, "Alice")
        for days in (100, -100):
            utc[0] = NOW + datetime.timedelta(days=days)
            mono[0] = 20.0
            assert _effects(metrics) == before
            assert _row(metrics.snapshot(6, HEALTH), "Alice").combat == row.combat
            assert read_combat(row, now_mono=30).observations == (before["POINT", "B"],)
        assert row.combat.observations == tuple(before.values())
        mono[0] = 30.0
        assert _effects(metrics) == {("POINT", "B"): before["POINT", "B"]}
        assert snapshot.sampled_at_mono == 10.0

    def test_ingestion_uses_one_utc_and_monotonic_sample_for_row_and_effect(self):
        utc = iter([NOW, NOW + datetime.timedelta(days=1)])
        mono = iter([100.0, 101.0])
        metrics = FleetMetrics(_clock=lambda: next(mono), _utc_now=lambda: next(utc))
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        _observe(metrics, 3, "SCRAM", "A")
        snapshot = metrics.snapshot(4, HEALTH)
        row = _row(snapshot, "Alice")
        assert snapshot.sampled_at_mono == 101.0
        assert row.combat.expires_at_mono == 130.0
        assert row.combat.observations == (
            EffectObservation("SCRAM", 130.0, row.combat.observation_id, "A"),
        )

    def test_two_owners_cannot_collide_and_quiet_full_roster_stays_available(self):
        tokens = []
        for _ in range(2):
            metrics, utc, mono = self._bound()
            metrics.consume(
                _env(3, _roster(_session("Alice"), _session("bob"), _session("zulu")))
            )
            metrics.consume(_env(4, _lifecycle("bob")))
            _observe(metrics, 5, "SCRAM", "A")
            effect = _effects(metrics)
            assert set(effect) == {("SCRAM", "A")}
            tokens.append(effect["SCRAM", "A"].observation_id[0])
            _advance(utc, mono, 30)
            snapshot = metrics.snapshot(6, HEALTH)
            assert [r.character for r in snapshot.rows] == ["Alice", "bob", "zulu"]
            assert [(r.dps, r.incoming_dps) for r in snapshot.rows] == [
                (0, 0),
                (0, 0),
                (None, None),
            ]
            assert all(r.combat.observations == () for r in snapshot.rows)
            assert all(not combat_row_visible(r, now_mono=30) for r in snapshot.rows)
            assert _row(snapshot, "zulu").log_status == NO_LOG
        assert tokens[0] != tokens[1]


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_stream_health_passed_through(self):
        metrics, _, _ = _metrics()
        health = StreamHealth(state="missing_folder", detail="X:/gone")
        snap = metrics.snapshot(1, health)
        assert snap.stream_health is health

    def test_metric_error_defaults_to_none(self):
        metrics, _, _ = _metrics()
        assert metrics.snapshot(1, HEALTH).metric_error is None
