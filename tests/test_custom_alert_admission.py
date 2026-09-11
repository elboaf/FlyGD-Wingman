"""Custom pressure must never change the general telemetry delivery contract."""

import threading
from dataclasses import replace

import pytest

from tests.test_telemetry_coordinator import (
    FakePolicy,
    FakePreviewHost,
    FakeStream,
    _AttemptSignallingLock,
    _fact,
    _harness,
    _lifecycle,
    _roster,
    _session,
    _source_id,
)
from wingman import settings
from wingman.alerts.custom import MAX_CUSTOM_RULES, prepare_alert_snapshot
from wingman.telemetry.gamelogs import MAX_FILES
from wingman.telemetry.model import (
    CombatFact,
    CustomMatch,
    SourceLifecycle,
    StreamBatch,
)


def _snapshot(previous=None, *, count=1, search="fleet invite", enabled=True):
    return prepare_alert_snapshot(
        settings.validated_preview(
            {
                "enabled": enabled,
                "alerts": {
                    "enabled": True,
                    "custom_rules": [
                        {
                            "id": f"r{i}",
                            "name": "Fleet",
                            "search": search,
                            "enabled": True,
                        }
                        for i in range(count)
                    ],
                },
            }
        ),
        previous,
    )


def _match(snapshot, character="Alice", index=0, *, source_id=None, generation=1):
    rule = snapshot.custom_rules[index]
    return CustomMatch(
        character,
        generation,
        source_id or _source_id(),
        rule.rule.id,
        rule.generation,
        snapshot.activation_epoch,
    )


@pytest.fixture
def runtime(tmp_path):
    harnesses = []

    def make(*, snapshot=None, **kwargs):
        authority = [snapshot or _snapshot()]
        h = _harness(
            tmp_path,
            preview=True,
            alerts=True,
            alert_policy=FakePolicy(),
            custom_snapshot=lambda: authority[0],
            **kwargs,
        )
        harnesses.append(h)
        h.coordinator.reconcile()
        h.pump()
        return h, authority

    yield make
    for h in harnesses:
        h.coordinator.stop()


def test_repeated_custom_keys_use_one_sentinel(runtime):
    h, authority = runtime()
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    for _ in range(1000):
        h.stream.publish_batch(StreamBatch(custom_matches=(match,)))
    assert len(h.coordinator._custom_pending) == 1
    assert h.coordinator._queue.qsize() == 2
    h.pump()
    assert h.policy.custom_calls == [(match,)]
    assert h.stream.legacy_subscriptions == []
    assert len(h.stream.batch_subscriptions) == 1
    assert h.coordinator._custom_pending == {}
    assert h.coordinator._queue.empty()


def test_valid_saturation_refuses_only_excess_custom_keys(runtime):
    preview = FakePreviewHost()
    h, authority = runtime(
        snapshot=_snapshot(count=MAX_CUSTOM_RULES), preview_host=preview
    )
    h.subscribe()
    expected = []
    for i in range(MAX_FILES):
        character = f"Pilot{i}"
        lifecycle = _lifecycle(character)
        matches = tuple(
            _match(authority[0], character, j) for j in range(MAX_CUSTOM_RULES)
        )
        expected.extend(matches)
        h.stream.publish_batch(StreamBatch((lifecycle,), matches))
    overflow = _match(authority[0], "Overflow")
    # Both lifecycle and rule authority are valid: only capacity can refuse this key.
    h.stream.publish_batch(StreamBatch((_lifecycle("Overflow"),), (overflow,)))
    fact = _fact("Overflow", "incoming_damage", amount=20)
    h.stream.publish(fact)
    roster = _roster(_session("Overflow"))
    h.stream.sources["Overflow"] = _lifecycle("Overflow")
    h.discovery.publish(roster)
    h.coordinator._request_fleet_mode(False)
    h.coordinator._request_fleet_mode(True)
    # Fleet refresh must not reset custom work or other alert candidates.
    from wingman.telemetry.coordinator import _FLEET_REFRESH

    h.coordinator._queue.put(_FLEET_REFRESH)
    assert len(h.coordinator._custom_pending) == MAX_FILES * MAX_CUSTOM_RULES
    h.pump()
    assert h.policy.custom_calls == [tuple(expected)]
    assert [event.event for event in h.policy.calls[0][0]] == ["combat"]
    payloads = [envelope.payload for envelope in h.metrics.envelopes]
    assert payloads[:MAX_FILES] == [_lifecycle(f"Pilot{i}") for i in range(MAX_FILES)]
    assert payloads[MAX_FILES : MAX_FILES + 3] == [_lifecycle("Overflow"), fact, roster]
    assert preview.rosters == [roster]
    assert h.metrics.sequences == sorted(set(h.metrics.sequences))
    assert h.metrics.resets == 4
    assert len(h.snapshots) == 1
    assert all(
        isinstance(p, (SourceLifecycle, CombatFact, type(roster))) for p in payloads
    )
    # Prove the refused key can be delivered once capacity, not authority, changes.
    h.stream.publish_batch(StreamBatch(custom_matches=(overflow,)))
    h.pump()
    assert h.policy.custom_calls[-1] == (overflow,)


def test_new_rule_generation_supersedes_pending_and_old_cannot_replace_it(runtime):
    h, authority = runtime(snapshot=_snapshot(count=MAX_CUSTOM_RULES))
    for i in range(MAX_FILES):
        matches = tuple(
            _match(authority[0], f"Pilot{i}", j) for j in range(MAX_CUSTOM_RULES)
        )
        h.stream.publish_batch(StreamBatch((_lifecycle(f"Pilot{i}"),), matches))
    old = _match(authority[0], "Pilot0")
    authority[0] = _snapshot(authority[0], count=MAX_CUSTOM_RULES, search="new query")
    new = _match(authority[0], "Pilot0")
    h.stream.publish_batch(StreamBatch(custom_matches=(new, old)))
    assert new in h.coordinator._custom_pending.values()
    assert old not in h.coordinator._custom_pending.values()
    h.pump()
    assert h.policy.custom_calls == [(new,)]


@pytest.mark.parametrize("change", ["retire", "replace", "rule", "activation"])
def test_cutoff_revalidates_source_and_current_authority(runtime, change):
    h, authority = runtime(fleet=False)
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    if change == "retire":
        h.stream.publish(_lifecycle("Alice", available=False, active=False))
    elif change == "replace":
        h.stream.publish(_lifecycle("Alice", generation=2))
    elif change == "rule":
        authority[0] = _snapshot(authority[0], search="new query")
    else:
        authority[0] = _snapshot(authority[0], enabled=False)
        authority[0] = _snapshot(authority[0])
    fact = _fact("Alice", "incoming_scram")
    h.stream.publish(fact)
    h.pump()
    assert h.policy.custom_calls == [()]
    assert [event.event for event in h.policy.calls[0][0]] == ["warp_scramble"]


def test_no_roster_is_required_but_both_source_stamps_are(runtime):
    h, authority = runtime(fleet=False)
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    h.pump()
    assert h.policy.custom_calls == [(match,)]
    for stale in (
        replace(match, source_generation=2),
        replace(match, source_id=_source_id("C:/logs/other.txt")),
    ):
        h.stream.publish_batch(StreamBatch(custom_matches=(stale,)))
        h.pump()
    assert h.policy.custom_calls == [(match,)]


def test_close_rejects_custom_siblings_but_preserves_semantic_events(runtime):
    h, authority = runtime()
    callback = h.stream.batch_subscriptions[0]
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    h.coordinator.close_custom_admission()
    fact = _fact("Alice", "incoming_scram")
    callback(StreamBatch((_lifecycle("Alice"), fact), (match,)))
    assert not h.coordinator._custom_pending
    h.pump()
    assert h.policy.custom_calls == [()]
    assert h.metrics.envelopes[-1].payload == fact
    assert h.policy.calls[0][0][0].event == "warp_scramble"
    h.coordinator.stop()
    h.coordinator.reconcile()
    h.pump()
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    h.pump()
    assert h.policy.custom_calls == [()]


def test_detached_callback_is_custom_only_fenced_and_restart_accepts_new_epoch(runtime):
    h, authority = runtime()
    callback = h.stream.batch_subscriptions[0]
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    old_epoch = h.coordinator._stream_delivery_epoch
    h.coordinator.stop()
    h.coordinator.reconcile()
    h.pump()
    assert h.coordinator._stream_delivery_epoch != old_epoch
    fact = _fact("Alice", "incoming_damage")
    callback(StreamBatch((fact,), (match,)))
    assert not h.coordinator._custom_pending
    h.pump()
    assert h.metrics.envelopes[-1].payload == fact
    assert h.policy.custom_calls == [()]
    # No lifecycle has arrived in this new stream generation yet.
    h.stream.publish_batch(StreamBatch(custom_matches=(match,)))
    h.pump()
    assert h.policy.custom_calls == [()]
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    h.pump()
    assert h.policy.custom_calls[-1] == (match,)


def test_dispatcher_cannot_cut_off_half_admitted_semantic_siblings(
    runtime, monkeypatch
):
    h, authority = runtime()
    match = _match(authority[0])
    h.stream.publish(_lifecycle("Alice"))
    h.pump()
    first = _fact("Alice", "incoming_damage")
    second = _fact("Alice", "incoming_scram")
    entered, release = threading.Event(), threading.Event()
    gate = _AttemptSignallingLock()
    h.coordinator._ingress_lock = gate
    put = h.coordinator._queue.put

    def pause_first(item, *args, **kwargs):
        put(item, *args, **kwargs)
        if item is first:
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(h.coordinator._queue, "put", pause_first)
    producer = threading.Thread(
        target=lambda: h.stream.publish_batch(StreamBatch((first, second), (match,)))
    )

    def dispatch():
        gate.watch_current_thread()
        h.pump()

    dispatcher = threading.Thread(target=dispatch)
    producer.start()
    try:
        assert entered.wait(5)
        dispatcher.start()
        assert gate.attempted.wait(5)
        assert h.policy.calls == []
    finally:
        release.set()
        producer.join(5)
        if dispatcher.ident is not None:
            dispatcher.join(5)
    assert not producer.is_alive() and not dispatcher.is_alive()
    assert h.policy.custom_calls == [(match,)]
    assert [e.event for e in h.policy.calls[0][0]] == ["combat", "warp_scramble"]
    assert [e.payload for e in h.metrics.envelopes][-2:] == [first, second]


def test_ingress_is_not_held_across_consumers_or_source_republication(
    runtime, monkeypatch
):
    h, authority = runtime(preview_host=FakePreviewHost())
    match = _match(authority[0])
    gate = _AttemptSignallingLock()
    h.coordinator._ingress_lock = gate
    observations = []

    def observed(fn):
        def call(*args, **kwargs):
            observations.append(gate.held)
            assert not gate.held
            return fn(*args, **kwargs)

        return call

    monkeypatch.setattr(h.metrics, "consume", observed(h.metrics.consume))
    monkeypatch.setattr(h.stream, "request_source", observed(h.stream.request_source))
    monkeypatch.setattr(h.policy, "handle", observed(h.policy.handle))
    monkeypatch.setattr(h.preview, "apply_roster", observed(h.preview.apply_roster))
    # Queue.get_nowait delegates to get(block=False), so only the first wait
    # is required to be unlocked; subsequent nonblocking reads own ingress.
    get = h.coordinator._queue.get

    def get_checked(block=True, timeout=None):
        if block:
            assert not gate.held
        return get(block=block, timeout=timeout)

    monkeypatch.setattr(h.coordinator._queue, "get", get_checked)
    h.stream.sources["Alice"] = _lifecycle("Alice")
    h.discovery.publish(_roster(_session("Alice")))
    h.stream.publish_batch(StreamBatch(custom_matches=(match,)))
    h.pump()
    assert observations and not any(observations)
    assert h.stream.requested == ["Alice"]
    assert h.policy.custom_calls == [(match,)]


def test_producer_after_cutoff_belongs_wholly_to_next_batch(runtime, monkeypatch):
    h, authority = runtime()
    first = _match(authority[0])
    second = _match(authority[0], "Bob")
    first_fact = _fact("Alice", "incoming_damage")
    second_fact = _fact("Bob", "incoming_scram")
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"), first_fact), (first,)))
    entered, release = threading.Event(), threading.Event()
    dispatch = h.coordinator._dispatch_alerts

    def pause(alerts, custom_matches=()):
        entered.set()
        assert release.wait(5)
        dispatch(alerts, custom_matches)

    monkeypatch.setattr(h.coordinator, "_dispatch_alerts", pause)
    dispatcher = threading.Thread(target=h.pump)
    dispatcher.start()
    try:
        assert entered.wait(5)
        h.stream.publish_batch(StreamBatch((_lifecycle("Bob"), second_fact), (second,)))
        assert h.policy.calls == []
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    assert h.policy.custom_calls == [(first,)]
    assert [e.event for e in h.policy.calls[0][0]] == ["combat"]
    h.pump()
    assert h.policy.custom_calls == [(first,), (second,)]
    assert [e.event for e in h.policy.calls[1][0]] == ["warp_scramble"]
    assert h.metrics.sequences == sorted(set(h.metrics.sequences))


def test_prolonged_batch_takes_only_one_bounded_custom_tuple(runtime, monkeypatch):
    h, authority = runtime()
    latest = [_match(authority[0])]
    remaining = [1000]
    process = h.coordinator._process

    def replenish(payload, alerts):
        process(payload, alerts)
        if isinstance(payload, CombatFact) and remaining[0]:
            remaining[0] -= 1
            latest[0] = replace(
                latest[0], source_generation=latest[0].source_generation + 1
            )
            h.stream.publish_batch(
                StreamBatch(
                    (
                        _lifecycle("Alice", generation=latest[0].source_generation),
                        _fact("Alice", "incoming_damage"),
                    ),
                    (latest[0],),
                )
            )
            assert len(h.coordinator._custom_pending) <= 1

    monkeypatch.setattr(h.coordinator, "_process", replenish)
    h.stream.publish_batch(
        StreamBatch(
            (_lifecycle("Alice"), _fact("Alice", "incoming_damage")), (latest[0],)
        )
    )
    h.pump()
    assert remaining == [0]
    assert h.policy.custom_calls == [(latest[0],)]
    assert len(h.policy.calls[0][0]) == 1001
    assert len(h.metrics.envelopes) == 2002
    assert h.coordinator._queue.empty()


def test_alert_reset_discards_retired_candidates_not_later_siblings(
    runtime, monkeypatch
):
    h, authority = runtime()
    old = _match(authority[0])
    new = _match(authority[0], "Bob")
    first_fact = _fact("Alice", "incoming_damage")
    later_fact = _fact("Bob", "incoming_scram")
    process = h.coordinator._process

    def reset_between(payload, alerts):
        process(payload, alerts)
        if payload is first_fact:
            h.coordinator._request_alert_mode(False)
            h.stream.publish_batch(StreamBatch((_lifecycle("Bob"), later_fact), (new,)))

    monkeypatch.setattr(h.coordinator, "_process", reset_between)
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"), first_fact), (old,)))
    h.pump()
    assert h.policy.custom_calls == [(new,)]
    assert [event.event for event in h.policy.calls[0][0]] == ["warp_scramble"]
    assert [e.payload for e in h.metrics.envelopes] == [
        _lifecycle("Alice"),
        first_fact,
        _lifecycle("Bob"),
        later_fact,
    ]


def test_stop_mid_batch_discards_custom_and_retains_timed_out_owner(
    runtime, monkeypatch
):
    h, authority = runtime(stream=FakeStream(stop_results=[False, False, False]))
    callback = h.stream.batch_subscriptions[0]
    match = _match(authority[0])
    first_fact = _fact("Alice", "incoming_damage")
    process = h.coordinator._process
    entered, release = threading.Event(), threading.Event()

    def pause(payload, alerts):
        process(payload, alerts)
        if payload is first_fact:
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(h.coordinator, "_process", pause)
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"), first_fact), (match,)))
    dispatcher = threading.Thread(target=h.pump)
    dispatcher.start()
    try:
        assert entered.wait(5)
        assert h.coordinator.stop(timeout=0) is False
        callback(StreamBatch(custom_matches=(match,)))
        assert not h.coordinator._custom_pending
        h.coordinator.reconcile()
        assert len(h.stream.starts) == 1
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    assert h.policy.calls == []


@pytest.mark.parametrize(
    "transition", ["close", "detach", "reset", "rule", "activation"]
)
def test_sealed_custom_tuple_is_fenced_before_policy_delivery(
    runtime, monkeypatch, transition
):
    h, authority = runtime()
    match = _match(authority[0])
    fact = _fact("Alice", "incoming_damage")
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"), fact), (match,)))
    entered, release = threading.Event(), threading.Event()
    dispatch = h.coordinator._dispatch_alerts

    def pause(alerts, custom_matches=()):
        assert custom_matches == (match,)
        entered.set()
        assert release.wait(5)
        dispatch(alerts, custom_matches)

    monkeypatch.setattr(h.coordinator, "_dispatch_alerts", pause)
    dispatcher = threading.Thread(target=h.pump)
    dispatcher.start()
    try:
        assert entered.wait(5)
        if transition == "close":
            h.coordinator.close_custom_admission()
        elif transition == "detach":
            h.coordinator._reconcile_stream(None)
        elif transition == "reset":
            h.coordinator._queue_alert_reset()
        elif transition == "rule":
            authority[0] = _snapshot(authority[0], search="edited query")
        else:
            authority[0] = _snapshot(authority[0], enabled=False)
            authority[0] = _snapshot(authority[0])
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    assert h.policy.custom_calls == [()]
    assert h.policy.calls[0][0][0].event == "combat"


def test_detach_does_not_create_duplicate_sentinels_or_reject_semantic_siblings(
    runtime,
):
    h, authority = runtime()
    match = _match(authority[0])
    callback = h.stream.batch_subscriptions[0]
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    # Leave the old sentinel queued through detach and immediate reattachment.
    h.coordinator._reconcile_stream(None)
    h.coordinator._reconcile_stream(h.folder)
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    fact = _fact("Alice", "incoming_damage")
    callback(StreamBatch((_lifecycle("Alice"), fact), (match,)))
    from wingman.telemetry.coordinator import _CUSTOM_DRAIN

    assert list(h.coordinator._queue.queue).count(_CUSTOM_DRAIN) == 1
    h.pump()
    assert h.policy.custom_calls == [(match,)]
    assert [e.payload for e in h.metrics.envelopes][-2:] == [_lifecycle("Alice"), fact]


def test_repeated_stop_does_not_leave_custom_controls_without_a_dispatcher(runtime):
    h, authority = runtime()
    match = _match(authority[0])
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"),), (match,)))
    h.pump()
    assert h.coordinator.stop()
    assert h.coordinator._queue.empty()
    for _ in range(3):
        assert h.coordinator.stop()
    assert h.coordinator._queue.empty()
    assert h.coordinator._custom_sources == {}


def test_failed_authority_read_drops_only_custom_work(runtime, caplog):
    h, authority = runtime()
    match = _match(authority[0])
    fact = _fact("Alice", "incoming_damage")

    def fail():
        raise RuntimeError("private query or matching line")

    h.coordinator._custom_snapshot = fail
    h.stream.publish_batch(StreamBatch((_lifecycle("Alice"), fact), (match,)))
    h.pump()
    assert h.policy.custom_calls == [()]
    assert h.metrics.envelopes[-1].payload == fact
    assert "private query" not in caplog.text
    assert "Could not read custom alert authority" in caplog.text


def test_empty_custom_delivery_retains_legacy_policy_call_shape(tmp_path):
    calls = []

    class LegacyPolicy:
        def reset(self):
            pass

        def handle(self, events, now):
            calls.append((events, now))

    h = _harness(tmp_path, preview=True, alerts=True, alert_policy=LegacyPolicy())
    try:
        h.coordinator.reconcile()
        h.stream.publish(_fact("Alice", "incoming_damage"))
        h.pump()
        assert len(calls) == 1
    finally:
        h.coordinator.stop()
