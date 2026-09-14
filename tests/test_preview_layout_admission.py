"""Completion, not successful posting, owns primary-layout admission."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event


def test_exclusive_waits_for_ordinary_completion():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    ordinary = gate.try_begin(exclusive=False)
    assert ordinary is not None
    assert gate.try_begin(exclusive=True) is None
    gate.finish(ordinary)
    batch = gate.try_begin(exclusive=True)
    assert batch is not None
    assert gate.try_begin(exclusive=False) is None
    gate.close()
    assert not gate.wait_idle(timeout=0)
    gate.finish(batch)
    assert gate.wait_idle(timeout=0)
    assert gate.try_begin(exclusive=True) is None


def test_shared_leases_finish_independently_and_ids_do_not_reuse():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    first = gate.try_begin(exclusive=False)
    second = gate.try_begin(exclusive=False)
    assert gate.snapshot().shared_count == 2
    gate.finish(first)
    gate.finish(first)
    assert not gate.owns(first) and gate.owns(second)
    assert gate.snapshot().shared_count == 1
    gate.finish(second)
    third = gate.try_begin(exclusive=True)
    assert third.operation_id > second.operation_id > first.operation_id
    assert gate.snapshot().exclusive
    gate.finish(third)


def test_timed_out_wait_retains_closed_owner_until_real_completion():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    lease = gate.try_begin(exclusive=False)
    entered, release = Event(), Event()

    def work():
        entered.set()
        assert release.wait(5)
        gate.finish(lease)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(work)
        assert entered.wait(5)
        try:
            gate.close()
            assert gate.snapshot().closed
            assert not gate.wait_idle(timeout=0.01)
            assert gate.owns(lease)
            assert gate.try_begin(exclusive=False) is None
        finally:
            release.set()
        assert gate.wait_idle(timeout=5)
        future.result(5)


def test_foreign_lease_cannot_retire_an_owner_with_the_same_id():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate, other = PrimaryLayoutAdmission(), PrimaryLayoutAdmission()
    owned = gate.try_begin(exclusive=False)
    foreign = other.try_begin(exclusive=False)
    assert owned.operation_id == foreign.operation_id
    assert not gate.owns(foreign)
    gate.finish(foreign)
    assert gate.owns(owned)
    gate.finish(owned)
    other.finish(foreign)
