"""Generate frozen-limit widths, never check in a multi-megabyte fixture.

The subprocess exercises actual client framing/read/codec work. In-memory delivery
is not network latency, a Windows result or proof of a usable <=5s clock anchor.
"""

import ctypes
import io
import json
import os
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
_MISSING = object()


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


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


def _windows_memory_probe(*, win_dll=None, get_last_error=None, win_error=None):
    if win_dll is None:
        win_dll = ctypes.WinDLL
    kernel32 = win_dll("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_process_memory_info = kernel32.K32GetProcessMemoryInfo
    get_current_process.argtypes = []
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        ctypes.c_uint32,
    ]
    get_process_memory_info.restype = ctypes.c_int
    if get_last_error is None:
        get_last_error = ctypes.get_last_error
    if win_error is None:
        win_error = ctypes.WinError
    structure_size = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)

    def sample():
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = structure_size
        process = get_current_process()
        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):
            saved_error = get_last_error()
            raise win_error(saved_error)
        return int(counters.PeakWorkingSetSize)

    return "process_peak_working_set_bytes", sample


def memory_probe(
    *,
    platform=None,
    win_dll=None,
    get_last_error=None,
    win_error=None,
    resource_module=_MISSING,
    tracemalloc_module=_MISSING,
):
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return _windows_memory_probe(
            win_dll=win_dll,
            get_last_error=get_last_error,
            win_error=win_error,
        )
    if resource_module is _MISSING:
        try:
            import resource as resource_module
        except ImportError:
            resource_module = None
    if resource_module is None:
        if tracemalloc_module is _MISSING:
            import tracemalloc as tracemalloc_module
        tracemalloc_module.start()
        return (
            "traced_peak_bytes",
            lambda: tracemalloc_module.get_traced_memory()[1],
        )
    unit = "bytes" if platform == "darwin" else "kib"
    return (
        f"process_peak_rss_{unit}",
        lambda: resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss,
    )


def _require_untraced_windows_decode(*, platform=None, tracemalloc_module=None):
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return
    if tracemalloc_module is None:
        import tracemalloc as tracemalloc_module
    if tracemalloc_module.is_tracing():
        raise RuntimeError(
            "Windows maximum-response measurement requires tracemalloc to be disabled."
        )


def _measure_protocol_crossings(operation):
    original_decode = protocol.decode_wire_json
    original_parse = protocol.parse_snapshot
    calls = {"decode": 0, "parse": 0}

    def counted_decode(*args, **kwargs):
        calls["decode"] += 1
        return original_decode(*args, **kwargs)

    def counted_parse(*args, **kwargs):
        calls["parse"] += 1
        return original_parse(*args, **kwargs)

    protocol.decode_wire_json = counted_decode
    protocol.parse_snapshot = counted_parse
    try:
        result = operation()
    finally:
        protocol.decode_wire_json = original_decode
        protocol.parse_snapshot = original_parse
    return result, calls["decode"], calls["parse"]


def measure_response():
    _require_untraced_windows_decode()
    buffer = io.BytesIO()
    buffer.write(b'{"protocol":2,"server_time_ms":9007199254740991,"rows":[')
    for index in range(LIMITS["get_rows"]):
        if index:
            buffer.write(b",")
        buffer.write(compact(maximum_row(index, read=True)))
    buffer.write(b"]}")
    raw = buffer.getvalue()
    assert len(raw) == 47_022_137, "maximum raw payload size changed"
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
    result, decode_calls, parse_calls = _measure_protocol_crossings(
        lambda: client.FleetRelayClient(
            "https://relay.example.test", transport=transport
        ).read_snapshot(
            session_id="A" * 43,
            private_key=bytes(32),
            revision=7,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    elapsed = time.perf_counter() - start
    peak = probe()
    assert result.server_time_ms == protocol.JS_SAFE_MAX
    assert len(result.rows) == LIMITS["get_rows"], "maximum row cardinality changed"
    assert (
        sum(len(effect.observations) for row in result.rows for effect in row.effects)
        == observations
    ), "maximum observation cardinality changed"
    assert responses[0].closed, "maximum response was not closed"
    assert responses[0].reads == [67_108_865], "maximum response read amount changed"
    assert decode_calls == 1, "wire decoder crossing count changed"
    assert parse_calls == 1, "snapshot parser crossing count changed"
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
    metric, probe = memory_probe(platform="linux")
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
    if evidence["platform"] == "win32":
        assert evidence["memory_metric"] == "process_peak_working_set_bytes"
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


class _FakeExport:
    def __init__(self, callback):
        self._callback = callback
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self._callback(*args)


class _FakeKernel32:
    def __init__(self, exports):
        self._exports = exports
        self.lookups = []

    def __getattr__(self, name):
        self.lookups.append(name)
        value = self._exports[name]
        if isinstance(value, BaseException):
            raise value
        return value


class _TraceSeam:
    def __init__(self, *, active=False):
        self.active = active
        self.is_tracing_calls = 0
        self.starts = 0
        self.stops = 0

    def is_tracing(self):
        self.is_tracing_calls += 1
        return self.active

    def start(self):
        self.starts += 1
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False

    def get_traced_memory(self):
        return (0, 0)


class _ResourceSeam:
    RUSAGE_SELF = object()

    def __init__(self):
        self.accesses = []

    def getrusage(self, who):
        self.accesses.append(who)
        return type("Usage", (), {"ru_maxrss": 123})()


class _WinErrorSeam:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def test_windows_memory_probe_reports_peak_working_set_without_tracing(monkeypatch):
    pointer_size = ctypes.sizeof(ctypes.c_size_t)
    if pointer_size == 8:
        peaks = [(1 << 32) + 12_345, (1 << 32) + 67_890]
        currents = [345_678_901, 456_789_012]
        pagefiles = [234_567_890, 123_456_789]
    else:
        peaks = [0xF1234567, 0xE2345678]
        currents = [0x71234567, 0x62345678]
        pagefiles = [0x51234567, 0x42345678]
    pseudo_handle = 0xFFFF_FFFF
    structures = []
    samples = []

    def current_process():
        return pseudo_handle

    def memory_info(handle, counters_pointer, byte_size):
        counters = counters_pointer._obj
        sample_index = len(samples)
        structures.append(counters)
        samples.append(
            {
                "handle": handle,
                "cb": counters.cb,
                "byte_size": byte_size,
            }
        )
        counters.PeakWorkingSetSize = peaks[sample_index]
        counters.WorkingSetSize = currents[sample_index]
        counters.PagefileUsage = pagefiles[sample_index]
        counters.PeakPagefileUsage = pagefiles[sample_index] - 1
        return 1

    get_current_process = _FakeExport(current_process)
    get_process_memory_info = _FakeExport(memory_info)
    close_handle = _FakeExport(lambda _handle: 1)
    kernel32 = _FakeKernel32(
        {
            "GetCurrentProcess": get_current_process,
            "K32GetProcessMemoryInfo": get_process_memory_info,
            "CloseHandle": close_handle,
        }
    )
    loads = []

    def load_library(name, **kwargs):
        loads.append((name, kwargs))
        return kernel32

    tracing = _TraceSeam()
    resource = _ResourceSeam()
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)

    def unused_error_seam(*_args):
        raise AssertionError("success path consulted an error seam")

    metric, probe = memory_probe(
        platform="win32",
        win_dll=load_library,
        get_last_error=unused_error_seam,
        win_error=unused_error_seam,
        resource_module=resource,
    )
    _require_untraced_windows_decode(platform="win32")

    assert metric == "process_peak_working_set_bytes"
    assert loads == [("kernel32", {"use_last_error": True})]
    assert get_current_process.argtypes == []
    assert get_current_process.restype is ctypes.c_void_p
    assert get_process_memory_info.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        ctypes.c_uint32,
    ]
    assert get_process_memory_info.restype is ctypes.c_int
    assert PROCESS_MEMORY_COUNTERS._fields_ == [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]
    assert PROCESS_MEMORY_COUNTERS.cb.offset == 0
    assert PROCESS_MEMORY_COUNTERS.PageFaultCount.offset == 4
    pointer_fields = [
        "PeakWorkingSetSize",
        "WorkingSetSize",
        "QuotaPeakPagedPoolUsage",
        "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage",
        "PagefileUsage",
        "PeakPagefileUsage",
    ]
    assert [
        getattr(PROCESS_MEMORY_COUNTERS, name).offset for name in pointer_fields
    ] == [8 + index * pointer_size for index in range(8)]
    assert ctypes.sizeof(PROCESS_MEMORY_COUNTERS) == 8 + 8 * pointer_size
    assert ctypes.alignment(PROCESS_MEMORY_COUNTERS) == ctypes.alignment(
        ctypes.c_size_t
    )
    assert ctypes.alignment(PROCESS_MEMORY_COUNTERS) in (4, 8)
    assert not hasattr(PROCESS_MEMORY_COUNTERS, "_pack_")

    assert [probe(), probe()] == peaks
    assert close_handle.calls == []
    assert kernel32.lookups == ["GetCurrentProcess", "K32GetProcessMemoryInfo"]
    assert len(structures) == 2 and structures[0] is not structures[1]
    expected_size = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    assert samples == [
        {"handle": pseudo_handle, "cb": expected_size, "byte_size": expected_size},
        {"handle": pseudo_handle, "cb": expected_size, "byte_size": expected_size},
    ]
    assert resource.accesses == []
    assert tracing.is_tracing_calls == 1
    monkeypatch.undo()
    assert tracing.starts == tracing.stops == 0


def test_windows_memory_probe_fails_closed_and_restores_crossings(monkeypatch):
    def assert_no_fallback(resource, tracing):
        assert resource.accesses == []
        assert tracing.starts == tracing.stops == 0

    def unexpected_last_error():
        raise AssertionError("native failure consulted last error too early")

    loader_error = OSError("kernel32 load failed")
    loader_win_error = _WinErrorSeam(OSError("unused loader WinError"))

    def failed_loader(_name, **_kwargs):
        raise loader_error

    resource = _ResourceSeam()
    tracing = _TraceSeam()
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
    with pytest.raises(OSError) as caught:
        memory_probe(
            platform="win32",
            win_dll=failed_loader,
            get_last_error=unexpected_last_error,
            win_error=loader_win_error,
            resource_module=resource,
        )
    assert caught.value is loader_error
    assert loader_win_error.calls == []
    assert_no_fallback(resource, tracing)

    for missing_name in ("GetCurrentProcess", "K32GetProcessMemoryInfo"):
        missing_error = AttributeError(f"missing {missing_name}")
        exports = {
            "GetCurrentProcess": _FakeExport(lambda: 123),
            "K32GetProcessMemoryInfo": _FakeExport(lambda *_args: 1),
        }
        exports[missing_name] = missing_error
        kernel32 = _FakeKernel32(exports)
        resource = _ResourceSeam()
        tracing = _TraceSeam()
        named_win_error = _WinErrorSeam(OSError("unused named-export WinError"))
        monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
        try:
            memory_probe(
                platform="win32",
                win_dll=lambda _name, **_kwargs: kernel32,
                get_last_error=unexpected_last_error,
                win_error=named_win_error,
                resource_module=resource,
            )
        except AttributeError as error:
            caught_error = error
        else:
            caught_error = None
        assert caught_error is missing_error
        assert kernel32.lookups[-1] == missing_name
        assert named_win_error.calls == []
        assert_no_fallback(resource, tracing)

    events = []
    saved_error = 1_234
    win_error_result = OSError("native memory query failed")

    def failed_memory_info(_handle, counters_pointer, _byte_size):
        events.append("api")
        counters_pointer._obj.PeakWorkingSetSize = 999_999
        counters_pointer._obj.WorkingSetSize = 888_888
        return 0

    def get_last_error():
        events.append("get_last_error")
        return saved_error

    kernel32 = _FakeKernel32(
        {
            "GetCurrentProcess": _FakeExport(lambda: 123),
            "K32GetProcessMemoryInfo": _FakeExport(failed_memory_info),
        }
    )
    resource = _ResourceSeam()
    tracing = _TraceSeam()
    win_error = _WinErrorSeam(win_error_result)
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
    metric, probe = memory_probe(
        platform="win32",
        win_dll=lambda _name, **_kwargs: kernel32,
        get_last_error=get_last_error,
        win_error=win_error,
        resource_module=resource,
    )
    assert metric == "process_peak_working_set_bytes"
    with pytest.raises(OSError) as caught:
        probe()
    assert caught.value is win_error_result
    assert events == ["api", "get_last_error"]
    assert win_error.calls == [(saved_error,)]
    assert_no_fallback(resource, tracing)

    active_trace = _TraceSeam(active=True)
    monkeypatch.setitem(sys.modules, "tracemalloc", active_trace)
    with pytest.raises(RuntimeError, match="requires tracemalloc to be disabled"):
        _require_untraced_windows_decode(platform="win32")
    assert active_trace.active
    assert active_trace.is_tracing_calls == 1
    assert active_trace.starts == active_trace.stops == 0

    if sys.platform == "win32":
        child_command = [sys.executable, __file__, "--measure"]
    else:
        child_code = (
            "import json, runpy, sys; "
            f"sys.argv = [{__file__!r}, '--measure']; "
            f"scope = runpy.run_path({__file__!r}, run_name='memory_probe_child'); "
            "sys.platform = 'win32'; "
            "print(json.dumps(scope['measure_response']()))"
        )
        child_command = [sys.executable, "-c", child_code]
    child = subprocess.run(
        child_command,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONTRACEMALLOC": "1"},
    )
    assert child.returncode != 0
    assert child.stdout == ""
    assert "requires tracemalloc to be disabled" in child.stderr

    original_decode = protocol.decode_wire_json
    original_parse = protocol.parse_snapshot
    sentinel = RuntimeError("crossing sentinel")

    def failed_operation():
        decoded = protocol.decode_wire_json(
            b'{"protocol":2,"server_time_ms":0,"rows":[]}'
        )
        protocol.parse_snapshot(decoded)
        raise sentinel

    with pytest.raises(RuntimeError) as caught:
        _measure_protocol_crossings(failed_operation)
    assert caught.value is sentinel
    assert protocol.decode_wire_json is original_decode
    assert protocol.parse_snapshot is original_parse
    monkeypatch.undo()
    assert active_trace.active
    assert active_trace.starts == active_trace.stops == 0


if __name__ == "__main__":
    print(json.dumps(measure_response()))
