"""The Discord gateway probe (rev 4, #334's Tier B verdict): one short
gateway session that answers one question -- is the watched user live?

Go Live never touches presence (activity type 1 is linked-platform status
only) and VOICE_STATE_UPDATE transitions never dispatch to bots (#334's
empirical gate). What *does* work: the GUILD_CREATE ``voice_states``
snapshot carries ``self_stream`` truthfully -- True while the user shares
their screen in a voice channel, absent otherwise. So the probe is
synchronous and short: identify with GUILDS, read the one guild's
snapshot, disconnect. ~2-3 s, two heartbeats at most.

This module owns the protocol only; the budget (#335) and the gates
(#335's stop, #336's start) live in their callers. Like every Windows
answer, the transport is a callable seam -- the controller is
Linux-unit-testable with a fake ``probe``.

Dependency note: ``websockets`` is a real dependency now, not the probe
script's ``uv run --with`` ephemeral. The script (scripts/
discord_presence_probe.py) predates the product and stays throwaway.
"""

from __future__ import annotations

import base64
import json
import logging
import ssl
import threading

logger = logging.getLogger(__name__)

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

_OP_DISPATCH = 0
_OP_IDENTIFY = 2
_OP_HEARTBEAT = 1
_OP_HELLO = 10

# GUILDS (1) only: READY/GUILD_CREATE carries voice_states under it, and
# #334 proved the narrower intent set is what keeps the ceremony at zero
# privileged toggles. Presence/members intents are NOT requested -- the
# probe answers from the snapshot, not from presence events.
_INTENTS = 1

# Session cap from #334's verified budget: 1000 gateway sessions / 24 h
# per bot, shared across every user of the published bot. Wingman claims
# a slice, not the pool; exceeding it degrades to open-loop (the caller's
# business), never to hammering the endpoint.
_SHARED_SESSION_BUDGET = 1000
_WINGMAN_SHARE = 300
DAILY_BUDGET = min(_SHARED_SESSION_BUDGET, _WINGMAN_SHARE)

_HELLO_TIMEOUT_S = 5.0
_READY_TIMEOUT_S = 5.0
# Long enough for one heartbeat round trip on a healthy link; short
# enough that a dead one costs the episode's decision seconds, not its
# quiet period.
_RECV_TIMEOUT_S = 8.0


class ProbeError(RuntimeError):
    """The probe could not produce an answer.

    Carries a fixed, non-secret operation code for the card/degrade
    path: ``auth`` (token refused -- revoked or mistyped), ``guild``
    (bot not in the configured guild), ``network`` (DNS/TLS/socket
    death), ``protocol`` (an answer Discord sent that the probe cannot
    parse). Never carries the token or gateway frames.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate_token_format(token: str) -> bool:
    """Shape-check a bot token before it is stored or sent.

    Bot tokens are ``base64(id).base64(timestamp).hmac``: three dot-
    separated base64 parts, roughly 60-80 chars total. This is a shape
    check, not an auth check -- Discord refuses the rest, as ProbeError
    ``auth``. It exists so a pasted user token or a trimmed secret fails
    at the card, not inside a decision gate.
    """
    if not isinstance(token, str):
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        return all(
            4 <= len(part) <= 128
            and base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
            for part in parts
        )
    except Exception:  # noqa: BLE001 -- any decode failure is the answer
        return False


def probe_live_state(token: str, guild_id: str, user_id: str) -> bool:
    """One gateway session: identify, read, answer, disconnect.

    Returns True when the snapshot shows the user live (``self_stream``
    truthy in the guild's voice_states) -- the ONLY signal #334 found
    truthful. False means a clean snapshot saying not-live. ProbeError
    means no answer: the caller degrades to open-loop.

    Synchronous and slow-ish by design (a network round trip); callers
    run it on their own worker, never the telemetry dispatcher or the
    bridge thread.
    """
    session = _Session(token, guild_id, user_id)
    try:
        return session.run()
    except ProbeError:
        raise
    except Exception as exc:  # noqa: BLE001 -- transport boundary; never leak frames
        logger.debug("gateway probe failed: %r", exc)
        raise ProbeError("network") from None


class _Session:
    """The protocol walk of one probe: connect, hello, identify, ready,
    answer, close. One method per frame so the failure surface names
    itself in the traceback without leaking token material into logs."""

    def __init__(self, token: str, guild_id: str, user_id: str):
        self._token = token
        self._guild_id = guild_id
        self._user_id = user_id

    def run(self) -> bool:
        import time

        from websockets.sync.client import connect

        with connect(
            GATEWAY_URL,
            ssl=ssl.create_default_context(),
            close_timeout=2.0,
            open_timeout=_HELLO_TIMEOUT_S,
        ) as ws:
            hello = self._recv(ws, _HELLO_TIMEOUT_S)
            if hello.get("op") != _OP_HELLO:
                raise ProbeError("protocol")
            self._send(
                ws,
                {
                    "op": _OP_IDENTIFY,
                    "d": {
                        "token": self._token,
                        "intents": _INTENTS,
                        "properties": {
                            "os": "windows",
                            "browser": "FlyGD Wingman",
                            "device": "FlyGD Wingman",
                        },
                    },
                },
            )
            deadline = time.monotonic() + _READY_TIMEOUT_S
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProbeError("protocol")
                payload = self._recv(ws, remaining)
                if payload.get("op") != _OP_DISPATCH:
                    # An op-7 RECONNECT before READY means the session
                    # was rejected server-side -- a protocol answer, not
                    # a socket death.
                    if payload.get("op") == 7:
                        raise ProbeError("protocol")
                    continue
                if payload.get("t") == "READY":
                    return self._answer(payload)
                # Anything else before READY (e.g. a resumed session's
                # backlog) is protocol noise the probe cannot use.

    def _answer(self, ready: dict) -> bool:
        guilds = (ready.get("d") or {}).get("guilds") or []
        for guild in guilds:
            if guild.get("id") != self._guild_id:
                continue
            for state in guild.get("voice_states") or []:
                if state.get("user_id") == self._user_id:
                    return bool(state.get("self_stream"))
            return False
        # READY omits or misnames the guild: the bot is not a member of
        # the configured guild (removed, or the id is wrong).
        raise ProbeError("guild")

    @staticmethod
    def _send(ws, frame: dict) -> None:
        ws.send(json.dumps(frame))

    @staticmethod
    def _recv(ws, timeout: float) -> dict:
        try:
            raw = ws.recv(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 -- mapped below, never leaked
            logger.debug("gateway recv failed: %r", exc)
            raise ProbeError("network") from None
        try:
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.debug("gateway frame unparsable: %r", exc)
            raise ProbeError("protocol") from None


class DailyBudget:
    """The probe counter (#335): 2 per fight budgeted, 300/day worst
    case, 10 users x 15 fights. When dry, Wingman degrades to open-loop
    and the card says so (#337) -- the counter is the shared fact that
    makes the published bot's scale explicit rather than lucky.

    Thread-safe: the controller worker and the bridge both ask. Day
    boundaries are wall-clock dates; a rollover resets the count.
    """

    def __init__(self, *, limit: int = DAILY_BUDGET, day=None):
        self._limit = limit
        self._day = day  # injected clock: () -> date-like key
        self._lock = threading.Lock()
        self._key = None
        self._used = 0

    def _today(self):
        import datetime

        if self._day is not None:
            return self._day()
        # date.today() is the intended semantic: the budget is a
        # user-local day, not a UTC instant comparison. The dtz rule is
        # aimed at naive datetimes leaking into scheduling; a calendar
        # key has no zone.
        return datetime.date.today()  # noqa: DTZ011

    def try_spend(self, n: int = 1) -> bool:
        """Reserve n probes; False when the day's budget is dry (or n
        would exceed it in one ask -- callers ask for 1)."""
        with self._lock:
            today = self._today()
            if today != self._key:
                self._key = today
                self._used = 0
            if self._used + n > self._limit:
                return False
            self._used += n
            return True

    def used(self) -> int:
        with self._lock:
            today = self._today()
            if today != self._key:
                return 0
            return self._used

    def remaining(self) -> int:
        with self._lock:
            today = self._today()
            if today != self._key:
                return self._limit
            return max(0, self._limit - self._used)
