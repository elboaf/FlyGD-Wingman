"""Leaf admission contracts; real producer/reset integration belongs to C2/C3."""

from dataclasses import FrozenInstanceError, fields, is_dataclass
from threading import Event, Thread

import pytest

from wingman.telemetry.admission import SourceAdmissionTicket, _SourceAuthority
from wingman.telemetry.model import FleetSnapshot, StreamHealth


def _ready():
    authority = _SourceAuthority()
    receipts = {
        lane: authority._begin(lane) for lane in ("roster", "stream", "control")
    }
    for receipt in receipts.values():
        authority._applied(receipt)
    return authority, receipts


def _ticket(authority):
    frontier = authority._capture()
    assert frontier is not None
    snapshot = FleetSnapshot((), StreamHealth("active"))
    ticket = authority._seal(frontier, snapshot)
    assert ticket is not None
    assert ticket.snapshot is snapshot
    return ticket


def test_old_roster_completion_cannot_acknowledge_later_reservation():
    authority = _SourceAuthority()
    roster = authority._begin("roster")
    stream = authority._begin("stream")
    control = authority._begin("control")
    newer = authority._reserve("roster", roster.lifetime)
    authority._applied(stream)
    authority._applied(roster)
    authority._applied(control)
    assert authority._capture() is None
    authority._applied(newer)
    complete = authority._capture()
    assert complete is not None
    authority._applied(roster)
    assert authority._capture() == complete
    ticket = _ticket(authority)
    calls = []
    assert ticket.admit_start(lambda: calls.append("start")) is True
    authority._reserve("stream", stream.lifetime)
    assert ticket.admit_start(lambda: calls.append("wrong")) is False
    assert calls == ["start"]


@pytest.mark.parametrize("lane", ["stream", "control"])
def test_delta_ack_cannot_skip_unapplied_predecessor(lane):
    authority, receipts = _ready()
    first = authority._reserve(lane, receipts[lane].lifetime)
    second = authority._reserve(lane, first.lifetime)
    authority._applied(second)
    assert authority._capture() is None
    authority._applied(first)
    assert authority._capture() is None
    # The dispatcher must prove ordered application, not rely on a max ACK.
    authority._applied(second)
    assert authority._capture() is not None


@pytest.mark.parametrize("lane", ["stream", "control"])
def test_reset_bound_full_restatement_supersedes_failed_predecessor(lane):
    from wingman.telemetry.admission import _Delivery

    authority, receipts = _ready()
    authority._reserve(lane, receipts[lane].lifetime)
    current = authority._reserve(lane, receipts[lane].lifetime)
    authority._poison("failed delta")
    boundary = authority._reset_started()
    _reseed(authority, receipts, boundary)
    operation = authority._operation(lane, current.lifetime)
    authority._record_application(operation)
    authority._applied(current)
    assert authority._reseeded(boundary) is False
    assert authority._restated(boundary, _Delivery(operation, current)) is True
    assert authority._reseeded(boundary) is True
    assert _ticket(authority).is_current()


def test_roster_full_snapshot_can_supersede_unapplied_predecessor():
    authority, receipts = _ready()
    first = authority._reserve("roster", receipts["roster"].lifetime)
    second = authority._reserve("roster", first.lifetime)
    authority._applied(second)
    assert authority._capture() is not None


def test_all_three_lanes_are_required_not_default_empty():
    authority = _SourceAuthority()
    assert authority._capture() is None
    for lane in ("roster", "stream"):
        authority._applied(authority._begin(lane))
        assert authority._capture() is None
    authority._applied(authority._begin("control"))
    assert authority._capture() is not None


def test_ticket_binding_is_frozen_and_guard_is_nonconsuming():
    authority, _ = _ready()
    ticket = _ticket(authority)
    original = ticket.snapshot
    with pytest.raises((FrozenInstanceError, AttributeError)):
        ticket._snapshot = FleetSnapshot((), StreamHealth("stopped"))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        ticket._token = object()
    calls = []
    assert ticket.is_current() is True
    assert ticket.admit_start(lambda: calls.append("start")) is True
    assert ticket.admit_start(lambda: calls.append("completion")) is True
    assert ticket.snapshot is original
    assert ticket.is_current() is True
    assert calls == ["start", "completion"]


def test_ticket_has_no_public_snapshot_restamping_constructor():
    authority, _ = _ready()
    ticket = _ticket(authority)
    with pytest.raises(TypeError):
        SourceAdmissionTicket(authority, ticket._token, ticket.snapshot)
    with pytest.raises(TypeError):
        SourceAdmissionTicket()


def test_validator_exception_identity_and_lock_release():
    authority, _ = _ready()
    ticket = _ticket(authority)
    error = ValueError("original validator failure")

    def validate():
        raise error

    with pytest.raises(ValueError) as caught:
        ticket.admit_start(validate)
    assert caught.value is error
    assert ticket.is_current() is True
    assert ticket.admit_start(lambda: None) is True


@pytest.mark.parametrize("change", ["reserve", "poison", "close", "stop"])
def test_revocation_refuses_validator_and_capture_seal_race(change):
    authority, receipts = _ready()
    frontier = authority._capture()
    ticket = _ticket(authority)
    if change == "reserve":
        authority._reserve("roster", receipts["roster"].lifetime)
    elif change == "poison":
        authority._poison("consume failed")
    elif change == "close":
        authority._close()
    else:
        authority._stop("roster", receipts["roster"].lifetime)
    assert ticket.is_current() is False
    assert ticket.admit_start(lambda: pytest.fail("stale validator")) is False
    assert authority._capture() is None
    assert authority._seal(frontier, ticket.snapshot) is None


def test_retired_lifetime_requires_confirmed_stop_before_replacement():
    authority, receipts = _ready()
    original = receipts["roster"]
    ticket = _ticket(authority)
    authority._stop("roster", original.lifetime)
    with pytest.raises(RuntimeError):
        authority._begin("roster")
    assert not ticket.is_current()
    authority._stopped("roster", original.lifetime)
    newer = authority._begin("roster")
    assert newer.lifetime is not original.lifetime
    assert authority._reserve("roster", original.lifetime) is None
    authority._applied(original)
    assert authority._capture() is None
    authority._applied(newer)
    current = _ticket(authority)
    authority._stop("roster", original.lifetime)
    authority._stopped("roster", original.lifetime)
    assert current.is_current()
    assert not ticket.is_current()


def test_begin_cannot_replace_live_owner_or_clear_poison():
    authority, receipts = _ready()
    with pytest.raises(RuntimeError):
        authority._begin("stream")
    authority._poison("failed reset")
    authority._stop("stream", receipts["stream"].lifetime)
    authority._stopped("stream", receipts["stream"].lifetime)
    newer = authority._begin("stream")
    authority._applied(newer)
    assert authority._capture() is None


def test_final_close_cannot_be_reopened():
    authority, receipts = _ready()
    ticket = _ticket(authority)
    authority._close()
    authority._close()
    for lane, receipt in receipts.items():
        authority._stop(lane, receipt.lifetime)
        authority._stopped(lane, receipt.lifetime)
        assert authority._begin(lane) is None
        assert authority._reserve(lane, receipt.lifetime) is None
        authority._applied(receipt)
    assert authority._capture() is None
    assert not ticket.is_current()


def test_foreign_ack_and_frontier_cannot_authorize():
    authority, receipts = _ready()
    other, foreign = _ready()
    newer = authority._reserve("stream", receipts["stream"].lifetime)
    foreign_newer = other._reserve("stream", foreign["stream"].lifetime)
    assert foreign_newer.order == newer.order
    authority._applied(foreign_newer)
    assert authority._capture() is None
    other._applied(foreign_newer)
    assert authority._seal(other._capture(), _ticket(other).snapshot) is None
    authority._applied(newer)
    assert authority._capture() is not None


def test_validator_holds_leaf_against_reservation_without_reverse_callback():
    authority, receipts = _ready()
    ticket = _ticket(authority)
    entered = Event()
    release = Event()
    attempting = Event()
    reserved = Event()
    results = []

    def validate():
        # Other owners' locks are acquired BEFORE this callback. It must never
        # call a lock-taking authority method, even an advisory ticket check.
        assert not authority._lock.acquire(blocking=False)
        entered.set()
        assert release.wait(2)

    def admit():
        results.append(ticket.admit_start(validate))

    def reserve():
        attempting.set()
        authority._reserve("stream", receipts["stream"].lifetime)
        reserved.set()

    starter = Thread(target=admit, daemon=True)
    invalidator = Thread(target=reserve, daemon=True)
    starter.start()
    try:
        assert entered.wait(2)
        invalidator.start()
        assert attempting.wait(2)
        assert not reserved.wait(0.05)
    finally:
        release.set()
        starter.join(2)
        if invalidator.ident is not None:
            invalidator.join(2)
    assert not starter.is_alive()
    assert not invalidator.is_alive()
    assert results == [True]
    assert reserved.is_set()
    assert ticket.admit_start(lambda: pytest.fail("reserved first")) is False


def test_unchanged_and_fact_only_operations_keep_ticket_but_not_compute_capture():
    authority, receipts = _ready()
    ticket = _ticket(authority)
    frontier = authority._capture()
    operation = authority._operation("stream", receipts["stream"].lifetime)
    assert operation is not None
    assert authority._capture() == frontier  # Unchanged/failed scan: no mutation.
    authority._record_application(operation)
    assert ticket.is_current()  # Ordinary fresh facts do not revoke old evidence.
    assert authority._seal(frontier, ticket.snapshot) is None  # Computation raced.
    assert _ticket(authority).is_current()


def test_original_operation_order_survives_later_reservation():
    authority, receipts = _ready()
    old = authority._operation("stream", receipts["stream"].lifetime)
    receipt = authority._reserve("stream", old.lifetime)
    newer = authority._operation("stream", old.lifetime)
    assert old.order < newer.order
    assert old.lifetime is receipt.lifetime
    with pytest.raises(FrozenInstanceError):
        old.order = newer.order
    authority._record_application(newer)
    authority._applied(receipt)
    ticket = _ticket(authority)
    authority._applied(receipts["stream"])  # Old ACK alone is harmless.
    assert ticket.is_current()
    authority._record_application(old)  # Actual old payload changes metrics.
    assert not ticket.is_current()
    assert authority._capture() is None
    authority._record_application(newer)
    authority._applied(receipt)
    assert authority._capture() is None


def test_retired_and_foreign_operations_poison_only_when_actually_applied():
    authority, receipts = _ready()
    old = authority._operation("stream", receipts["stream"].lifetime)
    authority._stop("stream", old.lifetime)
    assert authority._operation("stream", old.lifetime) is None
    authority._stopped("stream", old.lifetime)
    authority._applied(authority._begin("stream"))
    ticket = _ticket(authority)
    authority._record_application(old)
    assert not ticket.is_current()
    other, foreign = _ready()
    operation = other._operation("stream", foreign["stream"].lifetime)
    ticket = _ticket(other)
    other._record_application(old)
    assert not ticket.is_current()
    assert operation.authority is not old.authority


def _reseed(authority, receipts, boundary):
    assert authority._reset_applied(boundary) is True
    for lane, receipt in receipts.items():
        operation = authority._operation(lane, receipt.lifetime)
        authority._record_application(operation)
        authority._applied(receipt)


def test_same_lifetime_fact_crossing_successful_reset_poisons():
    authority, receipts = _ready()
    old_ticket = _ticket(authority)
    held = authority._operation("stream", receipts["stream"].lifetime)
    boundary = authority._reset_started()
    assert boundary.poison_serial == 0
    assert authority._capture() is None
    assert not old_ticket.is_current()
    _reseed(authority, receipts, boundary)
    assert authority._reseeded(boundary) is True
    ticket = _ticket(authority)
    authority._record_application(held)
    assert not ticket.is_current()
    # No changed receipt or lifetime was needed to identify pre-reset evidence.
    assert authority._capture() is None
    recovery = authority._reset_started()
    _reseed(authority, receipts, recovery)
    assert authority._reseeded(recovery) is True
    assert _ticket(authority).is_current()
    assert not old_ticket.is_current()
    assert not ticket.is_current()


def test_pre_reset_fact_poisons_before_any_newer_provenance_is_applied():
    authority, receipts = _ready()
    held = authority._operation("stream", receipts["stream"].lifetime)
    boundary = authority._reset_started()
    assert authority._reset_applied(boundary) is True
    authority._record_application(held)
    for lane, receipt in receipts.items():
        authority._record_application(authority._operation(lane, receipt.lifetime))
    assert authority._reseeded(boundary) is False
    assert authority._capture() is None


def test_operation_started_during_reset_is_also_before_successful_reset_cut():
    authority, receipts = _ready()
    boundary = authority._reset_started()
    held = authority._operation("stream", receipts["stream"].lifetime)
    _reseed(authority, receipts, boundary)
    assert authority._reseeded(boundary) is True
    ticket = _ticket(authority)
    authority._record_application(held)
    assert not ticket.is_current()


def test_reset_cannot_recover_without_successful_reset_and_each_reseed_lane():
    authority, receipts = _ready()
    authority._poison("consume failed")
    boundary = authority._reset_started()
    assert authority._reseeded(boundary) is False
    assert authority._reset_applied(boundary) is True
    for lane in ("roster", "stream"):
        authority._record_application(
            authority._operation(lane, receipts[lane].lifetime)
        )
        assert authority._reseeded(boundary) is False
    authority._record_application(
        authority._operation("control", receipts["control"].lifetime)
    )
    pending = authority._reserve("stream", receipts["stream"].lifetime)
    assert authority._reseeded(boundary) is False
    authority._applied(pending)
    assert authority._reseeded(boundary) is True
    assert authority._capture() is not None


@pytest.mark.parametrize("after_reset", [False, True])
def test_poison_during_inflight_reset_defeats_its_recovery_serial(after_reset):
    authority, receipts = _ready()
    authority._poison("old failure")
    boundary = authority._reset_started()
    if after_reset:
        _reseed(authority, receipts, boundary)
        authority._poison("later failure")
    else:
        authority._poison("later failure")
        _reseed(authority, receipts, boundary)
    assert authority._reseeded(boundary) is False
    assert authority._capture() is None
    newer = authority._reset_started()
    assert newer.poison_serial > boundary.poison_serial
    _reseed(authority, receipts, newer)
    assert authority._reseeded(boundary) is False
    assert authority._reseeded(newer) is True


def test_foreign_reset_cannot_certify_and_close_defeats_inflight_reseed():
    authority, receipts = _ready()
    other, _ = _ready()
    foreign = other._reset_started()
    assert authority._reset_applied(foreign) is False
    assert authority._capture() is None  # Actual unassociated reset is poison.
    boundary = authority._reset_started()
    _reseed(authority, receipts, boundary)
    authority._close()
    assert authority._reseeded(boundary) is False
    assert authority._reset_started() is None
    assert authority._operation("stream", receipts["stream"].lifetime) is None
    assert authority._capture() is None


def _retained_nodes(authority):
    # Count authority-owned records/containers, not caller-retained tickets or
    # integer magnitude. A receipt predecessor must be a coordinate, not a chain.
    seen = set()

    def visit(value):
        if id(value) in seen:
            return
        if isinstance(value, dict):
            children = value.values()
        elif isinstance(value, (tuple, list, set)):
            children = value
        elif is_dataclass(value):
            children = (getattr(value, field.name) for field in fields(value))
        else:
            return
        seen.add(id(value))
        for child in children:
            visit(child)

    visit(vars(authority))
    return len(seen)


def test_ten_thousand_operations_and_reservations_retain_three_fixed_slots():
    authority, receipts = _ready()
    warm_size = None
    for index in range(10_000):
        lane = ("roster", "stream", "control")[index % 3]
        operation = authority._operation(lane, receipts[lane].lifetime)
        receipt = authority._reserve(lane, receipts[lane].lifetime)
        authority._record_application(operation)
        authority._applied(receipt)
        if index % 100 == 99:
            boundary = authority._reset_started()
            _reseed(authority, receipts, boundary)
            assert authority._reseeded(boundary) is True
        if index == 99:
            warm_size = _retained_nodes(authority)
    assert len(authority._lanes) == 3
    assert _retained_nodes(authority) == warm_size
    assert warm_size < 30
    assert _ticket(authority).is_current()
