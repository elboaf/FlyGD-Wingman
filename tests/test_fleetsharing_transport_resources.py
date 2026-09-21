"""Generate frozen-limit widths, never check in a multi-megabyte fixture.

The subprocess exercises actual client framing/read/codec work. In-memory delivery
is not network latency, a Windows result or proof of a usable <=5s clock anchor.
"""

import io
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from email.message import Message
from hashlib import sha256
from uuid import UUID

import pytest

from wingman import combatprofile
from wingman.fleetsharing import client, protocol

LIMITS = combatprofile.LIMITS
MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 75.0


def maximum_row(index, *, read=False):
    names = [
        "\U0001f600" * (LIMITS["observed_name_scalars"] - 1) + chr(0x1F600 + i)
        for i in range(LIMITS["named_per_tackle"])
    ]
    effects = []
    for kind in LIMITS["effect_order"]:
        observations = (
            []
            if kind == "NEUT"
            else [{"name": name, "age_ms": LIMITS["activity_ms"] - 1} for name in names]
        )
        observations.append({"name": None, "age_ms": LIMITS["activity_ms"] - 1})
        effects.append({"kind": kind, "observations": observations})
    row = {
        "character_id": protocol.JS_SAFE_MAX - index,
        "outgoing_dps": protocol.MAX_DPS,
        "incoming_dps": protocol.MAX_DPS,
        "activity_age_ms": LIMITS["activity_ms"] - 1,
        "effects": effects,
    }
    if read:
        row.update(
            character_name="\U0001f600" * LIMITS["character_name_scalars"],
            state="stale",
            age_ms=LIMITS["transport_ms"] - 1,
            publication_id=str(UUID(int=index, version=4)),
        )
    return row


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def test_maximum_put_uses_actual_default_escaping_under_512k():
    value = {
        "protocol": 2,
        "sampled_at_ms": protocol.JS_SAFE_MAX,
        "rows": [maximum_row(i) for i in range(LIMITS["put_rows"])],
    }
    validated = protocol.parse_combat_put(value)
    requests = []

    def transport(request, **kwargs):
        requests.append(request)
        headers = {k.lower(): v for k, v in request.header_items()}
        canonical = "\n".join(
            (
                "fleet-v1",
                "PUT",
                "/api/fleet/v2/snapshot",
                headers["x-fleet-session"],
                headers["x-fleet-issued-at"],
                headers["x-fleet-revision"],
                headers["x-fleet-body-sha256"],
            )
        ).encode()
        response = io.BytesIO(b'{"protocol":2}')
        response.status = 200
        response.headers = Message()
        response.headers["Content-Type"] = "application/json"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Fleet-Request-Binding"] = sha256(
            b"fleet-api-v2\n" + canonical
        ).hexdigest()
        return response

    client.FleetRelayClient(
        "https://relay.example.test", transport=transport
    ).publish_snapshot(
        session_id="A" * 43,
        private_key=bytes(32),
        revision=1,
        sampled_at_ms=validated.sampled_at_ms,
        rows=validated.rows,
    )
    raw = requests[0].data
    assert raw == json.dumps(value).encode()
    assert len(raw) == 419900 and len(raw) < 524288
    assert len(compact(value)) == 154744
    assert len(compact(maximum_row(0))) == 4833
    assert len(compact(maximum_row(0, read=True))) == 5739


def memory_probe():
    # resource is absent on Windows. Keep that CI run executable without a new
    # dependency; traced allocations are a different metric, not process RSS.
    try:
        import resource
    except ImportError:
        import tracemalloc

        tracemalloc.start()
        return "traced_peak_bytes", lambda: tracemalloc.get_traced_memory()[1]
    unit = "bytes" if sys.platform == "darwin" else "kib"
    return (
        f"process_peak_rss_{unit}",
        lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )


def measure_response():
    buffer = io.BytesIO()
    buffer.write(b'{"protocol":2,"server_time_ms":9007199254740991,"rows":[')
    for index in range(LIMITS["get_rows"]):
        if index:
            buffer.write(b",")
        buffer.write(compact(maximum_row(index, read=True)))
    buffer.write(b"]}")
    raw = buffer.getvalue()
    assert len(raw) == 47022137
    buffer.close()
    observations = LIMITS["get_rows"] * LIMITS["observations_per_row"]
    responses = []

    class Response(io.BufferedReader):
        status = 200

        def __init__(self, headers):
            super().__init__(io.BytesIO(raw), buffer_size=65536)
            self.headers = headers
            self.reads = []
            self.read_seconds = 0

        def read(self, amount=-1):
            self.reads.append(amount)
            start = time.perf_counter()
            result = super().read(amount)
            self.read_seconds += time.perf_counter() - start
            return result

    def transport(request, **kwargs):
        sent = {k.lower(): v for k, v in request.header_items()}
        canonical = "\n".join(
            (
                "fleet-v1",
                "GET",
                "/api/fleet/v2/snapshot",
                sent["x-fleet-session"],
                sent["x-fleet-issued-at"],
                sent["x-fleet-revision"],
                sent["x-fleet-body-sha256"],
            )
        ).encode()
        headers = Message()
        headers["Content-Type"] = "application/json; charset=utf-8"
        headers["Cache-Control"] = "no-store"
        headers["X-Fleet-Request-Binding"] = sha256(
            b"fleet-api-v2\n" + canonical
        ).hexdigest()
        response = Response(headers)
        responses.append(response)
        return response

    metric, probe = memory_probe()
    before = probe()
    start = time.perf_counter()
    result = client.FleetRelayClient(
        "https://relay.example.test", transport=transport
    ).read_snapshot(
        session_id="A" * 43,
        private_key=bytes(32),
        revision=7,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    elapsed = time.perf_counter() - start
    peak = probe()
    assert result.server_time_ms == protocol.JS_SAFE_MAX
    assert len(result.rows) == LIMITS["get_rows"]
    assert (
        sum(len(effect.observations) for row in result.rows for effect in row.effects)
        == observations
    )
    assert responses[0].closed and responses[0].reads == [67108865]
    return {
        "raw_bytes": len(raw),
        "rows": len(result.rows),
        "observations": observations,
        "client_read_codec_seconds": elapsed,
        "reader_seconds": responses[0].read_seconds,
        "memory_metric": metric,
        "memory_peak": peak,
        "memory_before_client": before,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }


def test_memory_probe_falls_back_without_resource(monkeypatch):
    import tracemalloc

    monkeypatch.setitem(sys.modules, "resource", None)
    metric, probe = memory_probe()
    try:
        assert metric == "traced_peak_bytes"
        before = probe()
        allocation = bytearray(1024 * 1024)
        assert probe() >= before + len(allocation)
    finally:
        tracemalloc.stop()


@pytest.mark.resource
def test_maximum_legal_response_actual_reader_and_codec_in_subprocess(request):
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, __file__, "--measure"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    wall_seconds = time.perf_counter() - started
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    evidence["subprocess_wall_seconds"] = wall_seconds
    for name in (
        "subprocess_wall_seconds",
        "memory_metric",
        "memory_peak",
        "raw_bytes",
        "rows",
        "observations",
    ):
        request.node.user_properties.append((f"resource.{name}", str(evidence[name])))
    assert wall_seconds <= MAXIMUM_RESPONSE_RESOURCE_BUDGET_S, (
        "maximum response resource budget exceeded: "
        + json.dumps(evidence, sort_keys=True)
    )
    print(evidence)
    assert evidence["raw_bytes"] == 47022137
    assert evidence["rows"] == LIMITS["get_rows"]


if __name__ == "__main__":
    print(json.dumps(measure_response()))
