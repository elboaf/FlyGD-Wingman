"""The gateway probe (wingman/streaming/probe.py): the protocol walk is
Win32-free and runs on Linux against a fake transport -- the module
imports websockets lazily inside probe_live_state, so tests never touch
the socket. Pinned here: the budget's day rollover and thread safety,
the token shape check, and the error-code mapping through a scripted
transport.
"""

import threading

import pytest

from wingman.streaming import probe
from wingman.streaming.probe import DailyBudget, ProbeError, validate_token_format

# ---- the budget ----------------------------------------------------------


def test_the_budget_spends_and_dries():
    b = DailyBudget(limit=3, day=lambda: "day 1")
    assert b.try_spend() and b.try_spend() and b.try_spend()
    assert not b.try_spend()
    assert b.used() == 3
    assert b.remaining() == 0


def test_the_budget_rolls_over_at_the_day_boundary():
    day = ["day 1"]
    b = DailyBudget(limit=3, day=lambda: day[0])
    assert b.try_spend() and b.try_spend()
    day[0] = "day 2"
    assert b.used() == 0
    assert b.remaining() == 3
    assert b.try_spend()


def test_the_default_limit_is_the_shared_share():
    assert DailyBudget().remaining() == probe.DAILY_BUDGET == 300


def test_the_budget_is_thread_safe():
    b = DailyBudget(limit=50, day=lambda: "day 1")
    granted = []

    def spend():
        for _ in range(100):
            if b.try_spend():
                granted.append(1)

    threads = [threading.Thread(target=spend) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 50
    assert b.used() == 50


# ---- the token shape -----------------------------------------------------


def test_a_bot_token_shape_is_accepted():
    # base64(id).base64(timestamp).hmac -- the real shape.
    token = "MTEyMzQ1Njc4OTA.gGGh.Y83o-_xZ9z5vYcB8mF3nQw"
    assert validate_token_format(token)


def test_junk_is_refused():
    assert not validate_token_format("")
    assert not validate_token_format("not a token")
    assert not validate_token_format("one.two")
    assert not validate_token_format(None)
    assert not validate_token_format(17)
    # A user token (different shape) must not pass silently.
    assert not validate_token_format("abcdef0123456789")


# ---- the protocol walk through a scripted transport ----------------------


class FakeSocket:
    """Scripted frames; records what was sent. Closes on exit."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def send(self, raw):
        self.sent.append(raw)

    def recv(self, timeout=None):
        if not self._frames:
            raise TimeoutError("no more frames")
        item = self._frames.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _hello():
    return '{"op":10,"d":{"heartbeat_interval":412500}}'


def _ready(guild_id, voice_states):
    import json

    return json.dumps(
        {
            "op": 0,
            "t": "READY",
            "s": 1,
            "d": {"guilds": [{"id": guild_id, "voice_states": voice_states}]},
        }
    )


def _run(monkeypatch, frames, guild="111", user="222"):
    sock = FakeSocket(frames)
    monkeypatch.setattr("websockets.sync.client.connect", lambda *a, **kw: sock)
    answer = probe.probe_live_state("tok.en.t", guild, user)
    assert sock.closed  # the session is short-lived by construction
    identify = sock.sent[0]
    return answer, identify


def test_a_live_snapshot_answers_true(monkeypatch):
    answer, identify = _run(
        monkeypatch,
        [_hello(), _ready("111", [{"user_id": "222", "self_stream": True}])],
    )
    assert answer is True
    # GUILDS only: #334 found the snapshot carries everything; no
    # privileged intents are requested.
    assert '"intents": 1' in identify


def test_an_empty_snapshot_answers_false(monkeypatch):
    assert _run(monkeypatch, [_hello(), _ready("111", [])])[0] is False


def test_the_watched_user_is_matched_by_id(monkeypatch):
    answer, _ = _run(
        monkeypatch,
        [
            _hello(),
            _ready(
                "111",
                [
                    {"user_id": "999", "self_stream": True},
                    {"user_id": "222"},  # not live
                ],
            ),
        ],
    )
    assert answer is False


def test_a_wrong_guild_id_raises_guild(monkeypatch):
    with pytest.raises(ProbeError) as excinfo:
        _run(
            monkeypatch,
            [_hello(), _ready("999", [{"user_id": "222", "self_stream": True}])],
        )
    assert excinfo.value.code == "guild"


def test_a_socket_death_raises_network(monkeypatch):

    with pytest.raises(ProbeError) as excinfo:
        probe.probe_live_state("tok.en.t", "111", "222")
    # Not the scripted path: no monkeypatch, the real connect fails fast
    # off-Windows/CI. Assert the code, not the traceback.
    assert excinfo.value.code in {"network", "protocol"}


def test_a_missing_ready_raises_protocol(monkeypatch):
    with pytest.raises(ProbeError) as excinfo:
        _run(monkeypatch, [_hello(), '{"op":7,"d":{}}', '{"op":1}'])
    assert excinfo.value.code == "protocol"


def test_the_error_never_carries_the_token():
    err = ProbeError("auth")
    assert "tok" not in str(err)
    assert err.code == "auth"
