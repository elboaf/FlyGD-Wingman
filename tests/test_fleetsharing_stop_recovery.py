"""Explicit source-Stop recovery through the actual bridge and durable owner."""

from dataclasses import replace

import pytest

from tests.test_api_fleetsharing import displayed_source, setup
from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, UUID, drive
from wingman.fleetsharing import protocol as p

SOURCE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.mark.parametrize(
    "generation,issued", [(1, "2026-09-07T11:58:00.000Z"), (0, DATE)]
)
def test_explicit_replacement_settles_expired_or_conflicted_stop(
    tmp_path, generation, issued
):
    original = p.SourceStop(SOURCE, generation, UUID, issued, None)
    api, worker, relay, store, mono, _ = setup(
        tmp_path, state=replace(PAIRED_STATE, pending_source_commands=(original,))
    )
    try:
        relay.source_views[SOURCE] = p.SourceView(
            SOURCE, 1, 1, "active", None, None, None
        )
        api.fleet_sharing_watch(True)
        drive(worker, mono, 20)
        shown = displayed_source(api, SOURCE)
        assert api.fleet_sharing_stop_source(SOURCE, shown["binding"], shown)["queued"]
        drive(worker, mono, 20)
        assert store.load().pending_source_commands == (original,)
        assert relay.source_views[SOURCE].state == "active"
        shown = displayed_source(api, SOURCE)
        assert api.fleet_sharing_replace_stop(SOURCE, shown["binding"], shown)["queued"]
        queued = displayed_source(api, SOURCE)
        # A freshly displayed queued replacement cannot supersede a predecessor
        # which has not become durable yet; doing so loses both queued choices.
        assert not api.fleet_sharing_replace_stop(SOURCE, queued["binding"], queued)[
            "queued"
        ]
        # A second old confirmation must not replace the newly queued identity.
        assert not api.fleet_sharing_replace_stop(SOURCE, shown["binding"], shown)[
            "queued"
        ]
        drive(worker, mono, 100)
        assert relay.source_views[SOURCE].state == "ended"
        assert store.load().pending_source_commands == ()
    finally:
        api.shutdown_fleet_sharing()


@pytest.mark.parametrize("case", ["no_pending", "unknown", "ended", "stale"])
def test_replacement_requires_exact_original_stop_and_displayed_current_source(
    tmp_path, case
):
    original = p.SourceStop(SOURCE, 1, UUID, "2026-09-07T11:58:00.000Z", None)
    api, worker, _relay, store, mono, _ = setup(
        tmp_path, state=replace(PAIRED_STATE, pending_source_commands=(original,))
    )
    try:
        api.fleet_sharing_watch(True)
        drive(worker, mono, 12)
        status = worker.status()
        source = p.SourceView(
            SOURCE, 2, 1, "ended" if case == "ended" else "active", None, None, None
        )
        # Use real typed status ingress; never invent a bridge authorization token.
        from wingman.fleetsharing.worker import PendingSourceStatus

        status = replace(
            status,
            sources=p.Sources((source,), ()),
            pending_sources=()
            if case == "no_pending"
            else (PendingSourceStatus(SOURCE, "stop", None, "persisted", original),),
        )
        if case == "unknown":
            status = replace(status, sources=None)
        api._receive_fleet_sharing_status(replace(status, order=status.order + 1))
        shown = displayed_source(api, SOURCE)
        if case == "stale":
            changed = replace(source, generation=3)
            api._receive_fleet_sharing_status(
                replace(
                    status, order=status.order + 2, sources=p.Sources((changed,), ())
                )
            )
        assert not api.fleet_sharing_replace_stop(SOURCE, shown["binding"], shown)[
            "queued"
        ]
        assert store.load().pending_source_commands == (original,)
    finally:
        api.shutdown_fleet_sharing()
