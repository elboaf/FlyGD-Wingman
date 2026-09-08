"""Fleet presentation's real blocking boundaries and bounded handoff."""

import threading

import pytest

from tests.test_api import make_api
from tests.test_fleet_bar import FleetWindow

# Import the fixture too: importing FleetWindow alone does not register its
# module's headless helpers, and Windows then rejects the fake's missing HWND.
from tests.test_fleet_bar import (
    _headless_fleet_window_helpers as _headless_fleet_window_helpers,
)
from tests.test_telemetry_coordinator import _harness, _roster, _session
from wingman import settings
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth


@pytest.mark.parametrize("blocked", ["fleet", "main", "sig", "save"])
def test_blocked_presentation_does_not_stop_real_coordinator(
    tmp_path, monkeypatch, blocked
):
    harness = _harness(tmp_path, fleet=True)
    harness.metrics.rows = (FleetRow("Alice", 10),)
    api = make_api(tmp_path, telemetry=harness.coordinator)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleetbar_window = FleetWindow()
    api._sigbar_window = FleetWindow()
    entered = threading.Event()
    release = threading.Event()
    subsequent = threading.Event()
    next_iteration = threading.Event()
    original_save = settings._save_locked

    def stall(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        if blocked == "save":
            return original_save(*args, **kwargs)
        return None

    if blocked == "save":
        monkeypatch.setattr(settings, "_save_locked", stall)
    else:
        target = {
            "fleet": api._fleetbar_window,
            "main": api._window,
            "sig": api._sigbar_window,
        }[blocked]
        monkeypatch.setattr(target, "evaluate_js", stall)
    api._install_fleet_generation(harness.coordinator.reconcile())
    assert api._start_fleet_presentation()
    unsubscribe = api._fleet_unsubscribe
    harness.coordinator.subscribe_fleet(lambda _snapshot: subsequent.set())
    harness.discovery.publish(_roster(_session("Alice")))
    dispatcher = threading.Thread(target=harness.pump)
    dispatcher.start()
    try:
        assert entered.wait(5), "presentation never reached its blocking boundary"
        assert subsequent.wait(1), "Fleet presentation blocked the next subscriber"
        second = threading.Thread(target=lambda: (harness.pump(), next_iteration.set()))
        second.start()
        assert next_iteration.wait(1), "Fleet presentation blocked the next iteration"
        second.join(5)
    finally:
        release.set()
        dispatcher.join(5)
        unsubscribe()
        api.shutdown_previews()


@pytest.mark.parametrize("fail_at", ["factory", "start"])
def test_worker_start_failure_is_retryable_and_owns_no_thread(fail_at):
    from wingman.ui.fleetpresentation import FleetPresentationWorker

    attempts = []
    delivered = threading.Event()

    def spawn(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            if fail_at == "factory":
                raise RuntimeError("cannot allocate thread")

            class FailedThread:
                def start(self):
                    raise RuntimeError("cannot start thread")

            return FailedThread()
        return threading.Thread(**kwargs)

    worker = FleetPresentationWorker(delivered.set, thread_factory=spawn)
    worker.notify()
    assert worker.start() is False
    assert worker.start() is True
    try:
        assert delivered.wait(5)
        assert attempts[-1]["daemon"] is True
    finally:
        assert worker.stop(5)


def test_timed_out_stop_retains_owner_and_refuses_restart():
    from wingman.ui.fleetpresentation import FleetPresentationWorker

    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    threads = []

    def present():
        entered.set()
        assert release.wait(5)
        exited.set()

    def spawn(**kwargs):
        thread = threading.Thread(**kwargs)
        threads.append(thread)
        return thread

    worker = FleetPresentationWorker(present, thread_factory=spawn)
    assert worker.start()
    worker.notify()
    try:
        assert entered.wait(5)
        assert worker.stop(0) is False
        assert worker.start() is False
        worker.notify()
        assert len(threads) == 1
    finally:
        release.set()
        assert exited.wait(5)
        assert worker.stop(5)
    assert not threads[0].is_alive()


def test_burst_has_one_pending_presentation_not_one_task_per_snapshot():
    from wingman.ui.fleetpresentation import FleetPresentationWorker

    entered = threading.Event()
    release = threading.Event()
    latest_delivered = threading.Event()
    latest = [0]
    delivered = []

    def present():
        value = latest[0]
        if value == 0:
            entered.set()
            assert release.wait(5)
        delivered.append(value)
        if value == 1000:
            latest_delivered.set()

    worker = FleetPresentationWorker(present)
    assert worker.start()
    worker.notify()
    try:
        assert entered.wait(5)
        for value in range(1, 1001):
            latest[0] = value
            worker.notify()
        release.set()
        assert latest_delivered.wait(5)
    finally:
        release.set()
        assert worker.stop(5)
    assert delivered == [0, 1000]


def snapshot(*names, generation=1, dps=10):
    return FleetSnapshot(
        rows=tuple(FleetRow(name, dps) for name in names),
        stream_health=StreamHealth(state="active"),
        activation_generation=generation,
    )


def test_shutdown_closes_detaches_then_times_out_without_reenable(
    tmp_path, monkeypatch
):
    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleetbar_window = FleetWindow()
    entered = threading.Event()
    release = threading.Event()
    detached = []
    old_bar = api._fleetbar_window

    def stall(_script):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(api._window, "evaluate_js", stall)
    api._install_fleet_generation(1)
    assert api._start_fleet_presentation()

    def detach():
        api._receive_fleet_snapshot(snapshot("Late"))
        assert api._fleet_snapshot is None
        detached.append(True)

    api._fleet_unsubscribe = detach
    api._receive_fleet_snapshot(snapshot("Alice"))
    try:
        assert entered.wait(5)
        assert api._stop_fleet_presentation(timeout=0) is False
        assert detached == [True]
        replacement = FleetWindow()
        api._fleetbar_window = replacement
        assert api.toggle_fleet_bar(True)["applied"] is False
        assert api._start_fleet_presentation() is False
        release.set()
        assert api._stop_fleet_presentation(timeout=5)
        assert old_bar.calls == []
        assert replacement.calls == []
    finally:
        release.set()
        api._stop_fleet_presentation(timeout=5)


def test_api_start_failure_does_not_subscribe_or_enable(tmp_path, monkeypatch):
    from tests.test_fleet_bar import FakeTelemetry

    telemetry = FakeTelemetry()
    subscribed = []
    telemetry.subscribe_fleet = subscribed.append
    api = make_api(tmp_path, telemetry=telemetry)
    api._fleet_worker._thread_factory = lambda **_kw: (_ for _ in ()).throw(
        RuntimeError("thread unavailable")
    )
    assert api._start_fleet_presentation() is False
    assert subscribed == []
    assert api.toggle_fleet_bar(True)["applied"] is False
    assert not api._state.settings.get("fleet_bar", {}).get("enabled")


@pytest.mark.parametrize(
    "transitions,expected",
    [
        ([("Alice",), ("Bravo",), ("Charlie",)], ["Charlie", "Bravo", "Alice"]),
        ([("Alice",), ("Bravo",), ("Alice",)], ["Alice", "Bravo"]),
        ([("bravo", "alice", "Alice"), ()], ["Alice", "alice", "bravo"]),
    ],
)
def test_roster_fold_preserves_transition_priority(transitions, expected):
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    for names in transitions:
        memory.admit(names)
    write = memory.take()
    assert list(write.priority) == expected
    saved = settings.validated_fleet_bar({"seen": [*write.priority, *write.pending]})[
        "seen"
    ]
    memory.acknowledge(write, saved)
    assert list(memory.pending) == []
    assert memory.take() is None


def test_failed_batch_becomes_pending_retry_tier_not_fictional_persisted_success():
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    memory.admit(("Alice",))
    memory.admit(("Bravo",))
    failed = memory.take()
    memory.acknowledge(failed, None)
    assert list(memory.pending) == ["Alice", "Bravo"]
    assert memory.take() is None  # no metric-only retry
    memory.admit(("Charlie",))
    retry = memory.take()
    assert list(dict.fromkeys([*retry.priority, *retry.pending])) == [
        "Charlie",
        "Alice",
        "Bravo",
    ]


def test_save_ack_does_not_remove_later_admissions_even_for_repeated_name():
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    memory.admit(("Alice",))
    captured = memory.take()
    memory.admit(("Bravo", "Alice"))
    memory.acknowledge(captured, ["Alice"])
    assert set(memory.pending) == {"Alice", "Bravo"}
    latest = memory.take()
    assert list(latest.priority) == ["Alice", "Bravo"]


def test_roster_cap_retains_unsaved_overflow_without_a_snapshot_queue():
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    names = [f"Pilot {index:03}" for index in range(70)]
    for name in names:
        memory.admit((name,))
    write = memory.take()
    saved = settings.validated_fleet_bar({"seen": [*write.priority, *write.pending]})[
        "seen"
    ]
    assert saved == list(reversed(names))[:64]
    memory.acknowledge(write, saved)
    assert list(memory.pending) == names[:6]
    memory.admit(("Newest",))
    retry = memory.take()
    candidate = list(dict.fromkeys([*retry.priority, *retry.pending, *saved]))[:64]
    assert candidate[:7] == ["Newest", *names[:6]]


@pytest.mark.parametrize("seed", range(5))
def test_roster_fold_matches_logical_transition_reducer(seed):
    import random

    from wingman.ui.fleetpresentation import RosterMemory

    randomizer = random.Random(seed)
    names = [f"Pilot {index:03}" for index in range(90)]
    memory = RosterMemory()
    logical_seen = []
    logical_pending = []
    admitted = set()
    for _ in range(50):
        roster = randomizer.sample(names, randomizer.randrange(91))
        memory.admit(roster)
        admitted.update(roster)
        logical_pending = list(dict.fromkeys([*logical_pending, *roster]))
        logical_seen = settings.validated_fleet_bar(
            {
                "seen": list(
                    dict.fromkeys(
                        [
                            *sorted(roster, key=lambda name: (name.casefold(), name)),
                            *logical_pending,
                            *logical_seen,
                        ]
                    )
                )
            }
        )["seen"]
        logical_pending = [name for name in logical_pending if name not in logical_seen]
    write = memory.take()
    assert list(write.priority) == logical_seen
    # Folding priority is not an acknowledgement of a skipped physical write.
    assert set(memory.pending) == admitted
    memory.acknowledge(write, logical_seen)
    assert set(memory.pending) == admitted - set(logical_seen)


def test_coalesced_cap_overflow_keeps_next_transition_priority():
    from wingman.ui.fleetpresentation import RosterMemory

    names = [f"Pilot {index:03}" for index in range(70)]
    memory = RosterMemory()
    memory.admit(names)
    memory.admit(())
    write = memory.take()
    candidate = settings.validated_fleet_bar(
        {"seen": [*write.priority, *write.pending]}
    )["seen"]
    # Normalization's excluded names are pending's next-transition tier,
    # even when no physical write separated those logical transitions.
    assert candidate == names[64:] + names[:58]


def test_old_ack_preserves_later_cap_overflow_priority_promotion():
    from wingman.ui.fleetpresentation import RosterMemory

    old = [f"A{index:02}" for index in range(65)]
    new = [f"B{index:02}" for index in range(64)]
    memory = RosterMemory()
    memory.admit(old)
    captured = memory.take()
    memory.admit(new)
    memory.admit(())
    memory.acknowledge(captured, old[:64])
    latest = memory.take()
    saved = settings.validated_fleet_bar(
        {"seen": [*latest.priority, *latest.pending, *old[:64]]}
    )["seen"]
    assert saved == [old[-1], *new[:63]]
    memory.acknowledge(latest, saved)
    memory.admit(("Newest",))
    following = memory.take()
    next_seen = settings.validated_fleet_bar(
        {"seen": [*following.priority, *following.pending, *saved]}
    )["seen"]
    assert old[-1] in next_seen  # wrong priority would evict A64 here


def test_failed_old_ack_demotes_inherited_priority_but_not_new_transitions():
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    memory.admit(("Bravo", "Alice"))
    failed = memory.take()
    memory.admit(("Charlie",))
    memory.acknowledge(failed, None)
    latest = memory.take()
    assert list(dict.fromkeys([*latest.priority, *latest.pending])) == [
        "Charlie",
        "Bravo",
        "Alice",
    ]


@pytest.mark.parametrize("stage", ["before_delivery", "during_main_push"])
def test_target_only_invalidation_reschedules_without_another_snapshot(
    tmp_path, monkeypatch, stage
):
    from tests.test_api import decode_payload

    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": False})
    entered = threading.Event()
    release = threading.Event()
    displayed = threading.Event()
    payloads = []
    original_validate = api._fleet_delivery_current

    def validate(delivery):
        if stage == "before_delivery" and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original_validate(delivery)

    def display(script):
        if stage == "during_main_push" and not entered.is_set():
            entered.set()
            assert release.wait(5)
        payloads.append(script)

    def mirror(script):
        displayed.set()

    monkeypatch.setattr(api, "_fleet_delivery_current", validate)
    monkeypatch.setattr(api._window, "evaluate_js", display)
    assert api._start_fleet_presentation()
    api._push_fleet_bar_state()
    try:
        assert entered.wait(5)
        # Sig-bar creation does not submit Fleet telemetry or wake Fleet.
        api._sigbar_window = FleetWindow()
        api._sigbar_window.evaluate_js = mirror
        release.set()
        assert displayed.wait(1), "target change stranded the only settings delivery"
        payload = decode_payload(
            payloads[-1].split("window.onFleetBarState(", 1)[1][:-1]
        )
        assert payload["enabled"] is False
    finally:
        release.set()
        assert api._stop_fleet_presentation(5)


def test_failed_multi_name_roster_keeps_original_pending_insertion_order():
    from wingman.ui.fleetpresentation import RosterMemory

    memory = RosterMemory()
    memory.admit(("Bravo", "Alice"))
    failed = memory.take()
    assert failed.priority == ("Alice", "Bravo")
    memory.acknowledge(failed, None)
    memory.admit(())
    retry = memory.take()
    assert retry.pending == ("Bravo", "Alice")


def test_coalesced_rosters_persist_intermediate_names_and_display_latest(
    tmp_path, monkeypatch
):
    import json

    from wingman import paths

    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleetbar_window = FleetWindow()
    entered = threading.Event()
    release = threading.Event()
    latest_displayed = threading.Event()
    original_main = api._window.evaluate_js
    displayed = []

    def stall_main(script):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        original_main(script)

    def display(script):
        payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
        displayed.append(payload)
        if payload["rows"][0]["character"] == "Charlie":
            latest_displayed.set()

    monkeypatch.setattr(api._window, "evaluate_js", stall_main)
    monkeypatch.setattr(api._fleetbar_window, "evaluate_js", display)
    api._install_fleet_generation(1)
    assert api._start_fleet_presentation()
    api._receive_fleet_snapshot(snapshot("Seed"))
    try:
        assert entered.wait(5)
        for name in ["Alice", "Bravo", "Charlie"]:
            api._receive_fleet_snapshot(snapshot(name))
        release.set()
        assert latest_displayed.wait(5)
        expected = ["Charlie", "Bravo", "Alice", "Seed"]
        assert api._state.settings["fleet_bar"]["seen"] == expected
        assert settings.load(paths.settings_file())["fleet_bar"]["seen"] == expected
        assert [row["name"] for row in api.fleet_bar_settings()["characters"]] == [
            "Charlie",
            "Alice",
            "Bravo",
            "Seed",
        ]
        assert len(displayed) == 1  # no backlog of intermediate DPS frames
        assert displayed[0]["revision"] == api.fleet_bar_snapshot()["revision"]
    finally:
        release.set()
        assert api._stop_fleet_presentation(5)


def test_disable_reenable_with_same_generation_retires_blocked_delivery(
    tmp_path, monkeypatch
):
    import json

    from tests.test_fleet_bar import FakeTelemetry
    from wingman.ui import fleetbar

    def unexpected_create(*args, **kwargs):
        raise AssertionError(
            "a live fake Fleet window must not trigger native creation"
        )

    monkeypatch.setattr(fleetbar, "create", unexpected_create)
    telemetry = FakeTelemetry()
    telemetry.reconcile = lambda: 1  # sharing keeps the coordinator activation alive
    telemetry.subscribe_fleet = lambda _cb: lambda: None
    api = make_api(tmp_path, telemetry=telemetry)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleetbar_window = FleetWindow()
    api._fleetbar_ready = True
    entered = threading.Event()
    release = threading.Event()
    toggled = threading.Event()
    delivered = threading.Event()
    frames = []
    toggle_results = []

    def stall(script):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    def display(script):
        frames.append(json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1]))
        delivered.set()

    bar = api._fleetbar_window
    monkeypatch.setattr(api._window, "evaluate_js", stall)
    monkeypatch.setattr(bar, "evaluate_js", display)
    api._install_fleet_generation(1)
    assert api._start_fleet_presentation()
    api._receive_fleet_snapshot(snapshot("Retired"))
    toggler = None
    try:
        assert entered.wait(5)

        def toggle():
            toggle_results.append(api.toggle_fleet_bar(False))
            toggle_results.append(api.toggle_fleet_bar(True))
            toggled.set()

        toggler = threading.Thread(target=toggle)
        toggler.start()
        assert toggled.wait(1), "WebView must not hold the native lifecycle lock"
        assert all(result["applied"] for result in toggle_results)
        assert api._fleetbar_window is bar
        assert not bar.hidden
        assert api._fleet_snapshot is None
        api._receive_fleet_snapshot(snapshot("Current"))
        release.set()
        assert delivered.wait(5)
        assert len(frames) == 1
        assert [row["character"] for row in frames[0]["rows"]] == ["Current"]
    finally:
        release.set()
        if toggler is not None:
            toggler.join(5)
        assert api._stop_fleet_presentation(5)


@pytest.mark.parametrize("save_fails", [False, True])
def test_save_ack_across_activation_and_window_replacement_keeps_new_admissions(
    tmp_path, monkeypatch, save_fails
):
    import json

    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar(
        {"enabled": True, "hidden": ["Bravo"]}
    )
    old_bar = FleetWindow()
    api._fleetbar_window = old_bar
    first_entered = threading.Event()
    first_release = threading.Event()
    second_entered = threading.Event()
    second_release = threading.Event()
    delivered = threading.Event()
    original_save = settings._save_locked
    candidates = []
    frames = []

    def save(data, *args, **kwargs):
        candidates.append(list(data["fleet_bar"]["seen"]))
        if len(candidates) == 1:
            first_entered.set()
            assert first_release.wait(5)
            if save_fails:
                raise OSError("disk full")
        elif len(candidates) == 2:
            second_entered.set()
            assert second_release.wait(5)
        original_save(data, *args, **kwargs)

    def display(script):
        frames.append(json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1]))
        delivered.set()

    monkeypatch.setattr(settings, "_save_locked", save)
    api._install_fleet_generation(1)
    assert api._start_fleet_presentation()
    api._receive_fleet_snapshot(snapshot("Alice"))
    try:
        assert first_entered.wait(5)
        # Sharing can keep the telemetry generation unchanged. The local
        # activation and concrete target, not that generation, retire work.
        api._close_fleet_presentation()
        api._install_fleet_generation(1)
        replacement = FleetWindow()
        replacement.evaluate_js = display
        api._fleetbar_window = replacement
        api._receive_fleet_snapshot(snapshot("Bravo", "Alice"))
        first_release.set()
        assert second_entered.wait(5)
        assert set(api._fleet_roster.pending) == {"Alice", "Bravo"}
        assert old_bar.calls == []
        assert frames == []
        second_release.set()
        assert delivered.wait(5)
        assert candidates == [["Alice"], ["Alice", "Bravo"]]
        assert list(api._fleet_roster.pending) == []
        assert frames[0]["running_count"] == 2
        assert [row["character"] for row in frames[0]["rows"]] == ["Alice"]
        assert api.fleet_bar_settings()["characters"] == [
            {"name": "Alice", "running": True, "visible": True},
            {"name": "Bravo", "running": True, "visible": False},
        ]
    finally:
        first_release.set()
        second_release.set()
        assert api._stop_fleet_presentation(5)
