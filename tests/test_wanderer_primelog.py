"""The prime debug log: an always-on, tailable trace of the staging lane.

The debug branch's sink (wingman/wanderer/primelog.py). One JSON object per
line, appended and flushed per entry, so `tail -f` in Git Bash or
`Get-Content -Wait` in PowerShell shows the staging lane live. The wire
record is logged in full; credentials are never passed to the sink, so
nothing secret can reach the file.
"""

import json
import threading

from tests.test_wanderer_controller import Rig
from tests.test_wanderer_staging import make_identity, make_prime
from wingman.wanderer import primelog
from wingman.wanderer.staging import Staged


def entries(tmp_path):
    lines = (
        (tmp_path / "wanderer_prime_debug.log").read_text(encoding="utf-8").splitlines()
    )
    return [json.loads(line) for line in lines]


def test_an_entry_is_one_tailable_json_line(tmp_path):
    log = primelog.Sink(tmp_path)
    log.write("staged", event_id="0f2e-uuid", system_name="J123456")

    record = entries(tmp_path)[-1]
    assert record["event"] == "staged"
    assert record["event_id"] == "0f2e-uuid"
    assert record["system_name"] == "J123456"
    assert isinstance(record["ts"], float)


def test_entries_append_across_sink_instances(tmp_path):
    # Each launch builds its own sink; the file must survive and grow.
    primelog.Sink(tmp_path).write("prime_received", event_id="a")
    primelog.Sink(tmp_path).write("staged", event_id="b")

    assert [record["event"] for record in entries(tmp_path)] == [
        "prime_received",
        "staged",
    ]


def test_a_broken_sink_never_raises_and_stays_quiet(tmp_path):
    log = primelog.Sink(tmp_path)
    (tmp_path / "wanderer_prime_debug.log").write_text("", encoding="utf-8")
    (tmp_path / "wanderer_prime_debug.log").chmod(0o444)

    log.write("prime_received", event_id="a")  # must not raise
    log.write("staged", event_id="b")  # and never again this launch

    assert entries(tmp_path) == []


def test_concurrent_writers_keep_every_line_intact(tmp_path):
    log = primelog.Sink(tmp_path)

    def hammer(n):
        for i in range(25):
            log.write("prime_received", event_id=f"{n}-{i}")

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = entries(tmp_path)
    assert len(records) == 100


# ---- Slice 2: the controller's gates, logged -------------------------------


def capture(rig):
    """The rig's captured sink entries so far."""
    return rig.prime_log.captured()


def test_a_staged_prime_logs_the_engine_record_then_the_wire_outcome(tmp_path):
    rig = Rig(tmp_path, with_prime_credential=True)
    try:
        prime, identity = make_prime(), make_identity()
        assert rig.controller.stage_prime(prime, identity) is True
        call = rig.staging.call(1)
        call.reply(Staged())
        assert rig.prime_log.wait_for(lambda e: any(r["event"] == "staged" for r in e))
        received, post, outcome = capture(rig)
        assert received["event"] == "prime_received"
        assert received["engine_event"] == prime.event  # the engine's 32-hex form
        assert received["system_name"] == "J123456"
        assert received["character_id"] == identity.character_id
        assert received["flags"] == "ef"
        assert post["event"] == "post"
        assert post["attempt"] == 1
        assert post["url"].endswith("/api/maps/map/prejump-primes")
        assert outcome["event"] == "staged"
        assert outcome["event_id"] == call.args[3]["event_id"]  # hyphenated wire form
        assert outcome["attempt"] == 1
    finally:
        rig.close()


def test_every_decline_gate_logs_exactly_one_declined_line(tmp_path):
    rigs = [
        (
            "no_saved_connection",
            Rig(
                tmp_path / "no-saved-connection",
                with_prime_credential=True,
                section={"enabled": True, "base_url": "", "map_identifier": ""},
            ),
        ),
        ("no_prime_token", Rig(tmp_path / "no-prime-token")),
        ("no_identity", Rig(tmp_path / "no-identity", with_prime_credential=True)),
    ]
    try:
        for reason, rig in rigs:
            identity = None if reason == "no_identity" else make_identity()
            assert rig.controller.stage_prime(make_prime(), identity) is False
            assert rig.staging.calls == []
            assert [(r["event"], r["reason"]) for r in capture(rig)] == [
                ("declined", reason)
            ], reason
    finally:
        for _, rig in rigs:
            rig.close()


def test_the_relay_tick_relogging_is_suppressed_but_a_new_event_logs(tmp_path):
    rig = Rig(tmp_path / "tick-suppression")
    try:
        identity = make_identity()
        assert rig.controller.stage_prime(make_prime(), identity) is False
        assert rig.controller.stage_prime(make_prime(), identity) is False
        assert rig.controller.stage_prime(make_prime(event="f" * 32), identity) is False
        assert [(r["event"], r["reason"]) for r in capture(rig)] == [
            ("declined", "no_prime_token"),
            ("declined", "no_prime_token"),
        ]
    finally:
        rig.close()


def test_the_post_attempt_logs_the_full_wire_record(tmp_path):
    rig = Rig(tmp_path, with_prime_credential=True)
    try:
        from tests.test_wanderer_staging import EVENT

        assert rig.controller.stage_prime(make_prime(), make_identity()) is True
        call = rig.staging.call(1)
        call.reply(Staged())
        assert rig.prime_log.wait_for(lambda e: any(r["event"] == "staged" for r in e))
        outcomes = [
            {k: v for k, v in r.items() if k != "ts"}
            for r in capture(rig)
            if r["event"] == "staged"
        ]
        assert outcomes == [
            {
                "event": "staged",
                "attempt": 1,
                "event_id": EVENT,
                "record": call.args[3],
            }
        ]
    finally:
        rig.close()
