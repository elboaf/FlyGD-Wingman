"""Metadata lookup is explicit, bounded, and never publishes credential echoes."""

import io
import json
import threading
import urllib.error
import urllib.request

import pytest

from wingman import discord

URL = "https://discord.com/api/webhooks/1234567890/abcDEF-token_xyz"


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        assert 0 < size <= 16385, "metadata must never use an unbounded read"
        return super().read(size)


def lookup(body, *, raw=URL, status=200):
    hook, error = discord.parse_webhook(raw)
    assert hook is not None and not error
    response = Response(body, status)
    requests = []

    def transport(request, timeout=None):
        requests.append((request, timeout))
        return response

    name = discord.identify_webhook(hook, transport=transport)
    return name, requests, response


def test_identification_gets_only_webhook_name_with_bounded_request():
    name, requests, response = lookup(
        b'{"id":"1234567890","name":"Fleet logs","channel_id":"9876543210"}'
    )
    assert name == "Fleet logs"
    [(request, timeout)] = requests
    assert request.full_url == URL
    assert request.get_method() == "GET" and request.data is None
    assert request.get_header("User-agent").startswith("FlyGD-Wingman/")
    assert 0 < timeout <= 5
    assert response.closed


@pytest.mark.parametrize(
    "host", ["discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"]
)
def test_metadata_canonicalizes_permissive_legacy_urls(host):
    raw = f"https://user:password@{host}:9443//api//webhooks/1234567890/abcDEF-token_xyz/extra?wait=true#fragment"
    name, requests, _ = lookup(b'{"id":"1234567890","name":"Fleet"}', raw=raw)
    assert name == "Fleet"
    assert (
        requests[0][0].full_url
        == f"https://{host}/api/webhooks/1234567890/abcDEF-token_xyz"
    )


@pytest.mark.parametrize(
    "component",
    [
        "../abc",
        "123/..",
        "123/%2e%2e",
        "123/a%2fb",
        "123/a%3fb",
        "123/a;b",
        "abc/token",
        "\uff11\uff12\uff13/token",
    ],
)
def test_unsafe_identity_components_never_reach_transport(component):
    raw = f"https://discord.com/api/webhooks/{component}"
    hook, _ = discord.parse_webhook(raw)
    assert hook is not None  # Preserve the legacy posting parser boundary.
    calls = []
    assert (
        discord.identify_webhook(hook, transport=lambda *a, **k: calls.append(a)) == ""
    )
    assert calls == []


def test_forged_webhook_object_cannot_bypass_validated_host():
    hook = discord.Webhook(
        "https://evil.example/api/webhooks/123/token", "123", "token"
    )
    calls = []
    assert (
        discord.identify_webhook(hook, transport=lambda *a, **k: calls.append(a)) == ""
    )
    assert calls == []


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b"null",
        b'"Fleet"',
        b"{}",
        b'{"id":"other","name":"Fleet"}',
        b'{"id":1234567890,"name":"Fleet"}',
        b'{"id":"1234567890","name":42}',
        b'{"id":"1234567890","name":null}',
        b'{"id":"1234567890","name":""}',
        b'{"id":"1234567890","name":"   "}',
        b'{"id":"1234567890","name":"abcDEF-token_xyz"}',
        b'{"id":"1234567890","name":"Fleet abcDEF-token_xyz logs"}',
        b'{"id":"1234567890","name":"https://discord.com/api/webhooks/1234567890/abcDEF-token_xyz"}',
        b'{"id":"1234567890","name":"Fleet\\nlogs"}',
        b'{"id":"1234567890","name":"\\ud800"}',
        b'{"id":"1234567890","name":"\xff"}',
        json.dumps({"id": "1234567890", "name": "n" * 81}).encode(),
        pytest.param(
            b" " * 16385 + b'{"id":"1234567890","name":"Fleet"}', id="oversized"
        ),
    ],
)
def test_untrusted_metadata_is_not_an_identity_or_error_echo(body, caplog):
    name, _, response = lookup(body)
    assert name == ""
    assert response.closed
    assert "abcDEF-token_xyz" not in caplog.text


def test_name_limit_is_inclusive_and_whitespace_is_trimmed():
    name, _, _ = lookup(json.dumps({"id": "1234567890", "name": "n" * 80}).encode())
    assert name == "n" * 80
    name, _, _ = lookup(b'{"id":"1234567890","name":" Fleet "}')
    assert name == "Fleet"


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 404, 429, 500])
def test_non_success_bodies_are_not_read(status):
    name, _, response = lookup(URL.encode(), status=status)
    assert name == ""
    assert response.read_sizes == []


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(URL),
        OSError(URL),
        ValueError(URL),
        urllib.error.HTTPError(
            URL,
            302,
            URL,
            {"Location": "https://evil.example"},
            io.BytesIO(URL.encode()),
        ),
    ],
)
def test_transport_exceptions_do_not_escape_or_log_secrets(error, caplog):
    hook, _ = discord.parse_webhook(URL)

    def transport(request, timeout=None):
        raise error

    assert discord.identify_webhook(hook, transport=transport) == ""
    assert "abcDEF-token_xyz" not in caplog.text


def test_default_transport_uses_existing_no_redirect_opener(monkeypatch):
    calls = []

    def open_request(request, timeout=None):
        calls.append((request, timeout))
        return Response(b'{"id":"1234567890","name":"Fleet"}')

    monkeypatch.setattr(discord._opener, "open", open_request)
    hook, _ = discord.parse_webhook(URL)
    assert discord.identify_webhook(hook) == "Fleet"
    assert len(calls) == 1
    handler = next(
        h for h in discord._opener.handlers if isinstance(h, discord._NoRedirectHandler)
    )
    for code in (301, 302, 303, 307, 308):
        assert (
            handler.redirect_request(
                calls[0][0], None, code, "redirect", {}, "https://evil.example"
            )
            is None
        )


def test_invalid_host_error_does_not_echo_a_secret():
    _, error = discord.parse_webhook(
        "https://secret-token.evil.example/api/webhooks/123/secret-token"
    )
    assert error and "host" in error.lower()
    assert "secret-token" not in error


def test_lookup_lane_times_out_without_replacing_a_retained_dns_owner():
    webhook, _ = discord.parse_webhook(URL)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def blocked_transport(request, timeout=None):
        calls.append((request.full_url, timeout))
        entered.set()
        assert release.wait(5)
        return Response(b'{"id":"1234567890","name":"Fleet logs"}')

    lane = discord.WebhookLookupLane(
        lambda value: discord.identify_webhook(value, transport=blocked_transport),
        deadline_s=0.01,
    )
    try:
        assert lane.identify(webhook) == ""
        assert entered.wait(1)
        # A second optional request fails promptly, instead of replacing the
        # DNS owner or adding another blocked worker.
        assert lane.identify(webhook) == ""
        assert calls == [(URL, 5)]
    finally:
        release.set()
    assert lane.wait_idle(1)
    assert lane.identify(webhook) == "Fleet logs"
    assert calls == [(URL, 5), (URL, 5)]


def test_lookup_lane_keeps_each_completed_name_with_its_own_caller(monkeypatch):
    webhook, _ = discord.parse_webhook(URL)
    real_event = threading.Event
    first_waiting = real_event()
    release_first = real_event()
    event_count = 0

    class PausingEvent:
        def __init__(self, pause):
            self._event = real_event()
            self._pause = pause

        def set(self):
            self._event.set()

        def is_set(self):
            return self._event.is_set()

        def wait(self, timeout=None):
            result = self._event.wait(timeout)
            if self._pause and result:
                first_waiting.set()
                assert release_first.wait(1)
            return result

    def events():
        nonlocal event_count
        event_count += 1
        return PausingEvent(event_count == 1)

    names = iter(["First", "Second"])
    first = {}
    lane = None
    # Thread constructs its own start event, so create it before replacing the
    # lane's event seam below.
    caller = threading.Thread(
        target=lambda: first.setdefault("name", lane.identify(webhook))
    )
    monkeypatch.setattr(discord.threading, "Event", events)
    lane = discord.WebhookLookupLane(lambda value: next(names), deadline_s=1)
    caller.start()
    assert first_waiting.wait(1)
    assert lane.identify(webhook) == "Second"
    release_first.set()
    caller.join(1)
    assert first == {"name": "First"}


def test_lookup_lane_closes_admission_without_waiting_for_stuck_dns():
    webhook, _ = discord.parse_webhook(URL)
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(value):
        entered.set()
        assert release.wait(5)
        return "Fleet logs"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.01)
    try:
        assert lane.identify(webhook) == ""
        assert entered.wait(1)
        assert lane.close() is False
        assert lane.identify(webhook) == ""
    finally:
        release.set()
    assert lane.wait_idle(1)
