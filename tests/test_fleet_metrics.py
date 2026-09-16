"""Thread-free Fleet Metrics -- tests.

Every test injects a deterministic UTC wall clock (a list holding the
current instant, mutated between calls) and a deterministic monotonic clock
(a list holding the current float), following the pattern already used by
``test_telemetry_gamelogs.py``.
"""

import datetime
from uuid import UUID

import pytest

from wingman.telemetry.combat import combat_row_visible, read_combat
from wingman.telemetry.metrics import NO_LOG, TACKLE_TAG, FleetMetrics
from wingman.telemetry.model import (
    ClientSessionId,
    CombatActivity,
    CombatFact,
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
):
    return CombatFact(
        character=character,
        source_generation=source_generation,
        source_id=source_id if source_id is not None else _source_id(),
        occurred_at=occurred_at,
        kind=kind,
        amount=amount,
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

    def test_outgoing_damage_refreshes_observed_ewar_activity(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(_env(4, _damage("Alice", 100, utc_box[0])))

        mono_box[0] = 149.999
        assert _row(metrics.snapshot(5, HEALTH), "Alice").ewar == ("SCRAM",)
        mono_box[0] = 150.0
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == ()

    def test_incoming_damage_does_not_refresh_observed_ewar(self):
        metrics, utc_box, mono_box = self._bound(_metrics(mono=100.0))
        metrics.consume(_env(3, _ewar("Alice", "incoming_scram", NOW)))

        utc_box[0] = NOW + datetime.timedelta(seconds=20)
        mono_box[0] = 120.0
        metrics.consume(
            _env(4, _damage("Alice", 100, utc_box[0], kind="incoming_damage"))
        )

        mono_box[0] = 130.0
        # Had incoming damage refreshed activity like outgoing does, the
        # SCRAM tag observed at mono 100 would still be visible here (its
        # deadline would have moved to 150). It must not.
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
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == ("POINT",)

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

        mono_box[0] = 149.999
        assert _row(metrics.snapshot(6, HEALTH), "Alice").ewar == (
            "SCRAM",
            "NEUT",
        )

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
        "age, deadline", [(10, 120.0), (15, 115.0), (29.999, 100.001)]
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
    def test_accepted_ewar_qualifies_without_producing_effect_observations(
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
        assert row.combat.observations == ()
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
        assert _row(unchanged, "Alice").combat == alice
        assert _row(unchanged, "bob").combat == bob
        metrics.consume(_env(11, _damage("Alice", 0, utc[0])))
        after = metrics.snapshot(12, HEALTH)
        assert _row(after, "Alice").combat == CombatActivity(
            140.0, (alice.observation_id[0], 11)
        )
        assert _row(after, "bob").combat == bob
        assert not combat_row_visible(_row(after, "bob"), now_mono=125.0)
        assert combat_row_visible(_row(after, "Alice"), now_mono=125.0)

    @pytest.mark.parametrize("age", [0, 15])
    def test_incoming_row_activity_does_not_extend_legacy_ewar(self, age):
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

    def test_unchanged_roster_and_active_rebind_preserve_lifetime(self):
        metrics, utc, mono = self._bound()
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None
        metrics.consume(_env(5, _roster(_session("Alice"))))
        metrics.consume(_env(6, _lifecycle("Alice")))
        metrics.consume(_env(5, _lifecycle("Alice", active=False)))
        utc[0] = NOW + datetime.timedelta(seconds=1)
        mono[0] = 101.0
        metrics.consume(_env(6, _damage("Alice", 100, utc[0])))
        row = _row(metrics.snapshot(7, HEALTH), "Alice")
        assert row.combat == original
        assert row.dps == 10
        metrics.consume(_env(8, _damage("Alice", 0, utc[0])))
        assert _row(metrics.snapshot(9, HEALTH), "Alice").combat == CombatActivity(
            131.0, (original.observation_id[0], 8)
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
    def test_invalidation_clears_activity_and_fences_stale_facts(self, change):
        metrics, _, _ = self._bound()
        metrics.consume(_env(3, _damage("Alice", 100, NOW)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None
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
        metrics.consume(_env(9, _damage("Alice", 999, NOW)))
        metrics.consume(
            _env(12, _lifecycle("Alice", generation=generation, source_id=source_id))
        )
        metrics.consume(
            _env(
                11,
                _damage(
                    "Alice", 999, NOW, source_generation=generation, source_id=source_id
                ),
            )
        )
        rebound = _row(metrics.snapshot(13, HEALTH), "Alice")
        assert rebound.combat == CombatActivity()
        assert (rebound.dps, rebound.incoming_dps, rebound.ewar) == (0, 0, ())
        metrics.consume(
            _env(
                14,
                _damage(
                    "Alice", 0, NOW, source_generation=generation, source_id=source_id
                ),
            )
        )
        new = _row(metrics.snapshot(15, HEALTH), "Alice").combat
        assert new is not None
        assert new.expires_at_mono == 130.0
        assert new.observation_id[0] != original.observation_id[0]
        assert new.observation_id[1] == 14

    def test_full_reset_cannot_reuse_id_even_with_same_source_and_sequence(self):
        metrics, _, _ = self._bound()
        metrics.consume(_env(3, _damage("Alice", 0, NOW)))
        original = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        metrics.reset()
        metrics.consume(
            _env(3, _damage("Alice", 999, NOW))
        )  # No roster: drop, never queue.
        metrics.consume(_env(1, _roster(_session("Alice"))))
        metrics.consume(_env(2, _lifecycle("Alice")))
        assert _row(metrics.snapshot(3, HEALTH), "Alice").combat == CombatActivity()
        metrics.consume(_env(3, _damage("Alice", 0, NOW)))
        new = _row(metrics.snapshot(4, HEALTH), "Alice").combat
        assert original is not None and new is not None
        assert new.observation_id[1] == original.observation_id[1] == 3
        assert new.observation_id[0] != original.observation_id[0]

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
