"""The OAuth loopback callback listener.

parse_request is a PURE function over bytes, which is the whole reason it
exists as a separate function: every rejection rule below is exercised on
Linux with no socket, no browser, and no timing. The listener tests further
down do open a real loopback socket, but the security surface is proved here.
"""
import socket as _socket
import threading
import time

import pytest

from obs_youtube_uploader.eveskills import loopback

HOST = "127.0.0.1:51779"
PATH = "/callback/"


def request(target="/callback/?code=abc&state=xyz", *,
            host=HOST, method="GET", version="HTTP/1.1", extra=()):
    """Assemble a raw HTTP/1.1 request as bytes."""
    lines = [f"{method} {target} {version}"]
    if host is not None:
        lines.append(f"Host: {host}")
    lines.extend(extra)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def parse(raw):
    return loopback.parse_request(raw, expected_host=HOST, expected_path=PATH)


# ---------------------------------------------------------------------------
# Cycle 1 -- the request line
# ---------------------------------------------------------------------------

def test_parses_a_well_formed_callback():
    assert parse(request()) == {"code": "abc", "state": "xyz"}


def test_rejects_any_method_other_than_get():
    """The callback is a browser navigation. Anything else is a probe, and
    the lowercase spelling is included because HTTP methods are
    case-sensitive and a tolerant comparison is one more thing to get right.
    """
    for method in ("POST", "HEAD", "OPTIONS", "get"):
        with pytest.raises(ValueError):
            parse(request(method=method))


def test_rejects_any_version_other_than_http_1_1():
    for version in ("HTTP/1.0", "HTTP/2", "HTTP/1.1x", ""):
        with pytest.raises(ValueError):
            parse(request(version=version))


def test_rejects_a_request_line_with_the_wrong_number_of_fields():
    """Split on a single space, with no empty-entry collapsing.

    A tolerant split accepts "GET  /callback/  HTTP/1.1" and, worse,
    "GET /callback/ HTTP/1.1 extra" -- neither of which any browser sends.
    """
    for line in (b"GET /callback/\r\n", b"GET  /callback/ HTTP/1.1\r\n",
                 b"GET /callback/ HTTP/1.1 extra\r\n", b"\r\n"):
        with pytest.raises(ValueError):
            parse(line + b"Host: 127.0.0.1:51779\r\n\r\n")


def test_rejects_an_absolute_form_target():
    """Only origin-form. An absolute-form target is another way to name an
    authority that the Host check never gets to see."""
    with pytest.raises(ValueError):
        parse(request(target="http://127.0.0.1:51779/callback/?state=xyz"))


def test_rejects_a_request_that_ends_mid_line():
    """A truncated request must fail, not be parsed as far as it got.

    A half-arrived request could omit the Host line entirely, which is the
    one header the DNS-rebinding guard depends on.
    """
    with pytest.raises(ValueError):
        parse(b"GET /callback/?state=xyz HTTP/1.1\r\nHost: 127.0.0.1:51779")


# ---------------------------------------------------------------------------
# Cycle 2 -- headers, the Host guard, and the byte caps
# ---------------------------------------------------------------------------

def test_rejects_a_duplicate_host_header():
    """The DNS-rebinding guard, bypassed.

    With two Host headers, whichever copy the checker reads is not
    necessarily the one anything downstream reads. Rejecting outright is
    the only answer that does not depend on agreeing about which one wins.
    """
    with pytest.raises(ValueError, match="duplicate Host"):
        parse(request(extra=["Host: evil.test"]))


def test_rejects_a_missing_host_header():
    with pytest.raises(ValueError, match="Host"):
        parse(request(host=None))


def test_rejects_a_host_that_is_not_the_redirect_authority():
    """This is the DNS-rebinding guard itself.

    A page on any origin can point a name at 127.0.0.1 and have the browser
    issue this exact request; what it cannot do is forge the Host header,
    which still carries the name the browser resolved. The bare "127.0.0.1"
    case matters because a port-less Host is a different authority.
    """
    for host in ("evil.test", "evil.test:51779", "127.0.0.1:51780",
                 "localhost:51779", "127.0.0.1"):
        with pytest.raises(ValueError, match="Host"):
            parse(request(host=host))


def test_host_comparison_is_case_insensitive():
    """Case carries no meaning in a hostname."""
    assert parse(request(target="/callback/", host="127.0.0.1:51779")) == {}


def test_rejects_a_header_line_without_a_colon():
    with pytest.raises(ValueError):
        parse(request(extra=["NotAHeader"]))


def test_rejects_a_header_line_that_starts_with_a_colon():
    """An empty header name is malformed, and ": Host: evil.test" is a way
    to smuggle one past a checker that splits on the first colon."""
    with pytest.raises(ValueError):
        parse(request(extra=[": Host: evil.test"]))


def test_rejects_a_line_over_the_line_cap():
    """8 KiB per line. Without a cap, a single header line is unbounded
    memory before any check runs."""
    with pytest.raises(ValueError, match="line exceeded"):
        parse(request(extra=["X-Pad: " + "a" * (loopback.MAX_LINE_BYTES + 1)]))


def test_rejects_headers_over_the_total_cap():
    """32 KiB of headers. Individually-legal lines still have to stop."""
    filler = [f"X-Pad-{index:04d}: {'a' * 200}" for index in range(300)]
    with pytest.raises(ValueError, match="headers"):
        parse(request(extra=filler))


def test_rejects_non_ascii_request_bytes():
    """A browser sends none to a loopback callback."""
    raw = request().replace(b"code=abc", b"code=ab\xc3\xa9")
    with pytest.raises(ValueError, match="non-ASCII"):
        parse(raw)


def test_rejects_a_nul_byte():
    raw = request().replace(b"code=abc", b"code=ab\x00")
    with pytest.raises(ValueError, match="non-ASCII"):
        parse(raw)


# ---------------------------------------------------------------------------
# Cycle 3 -- the target path and the query
# ---------------------------------------------------------------------------

def test_target_path_must_match_exactly():
    """No normalisation, no prefix match, no trailing-slash tolerance.

    EVE echoes the registered redirect_uri back verbatim, so an exact match
    is achievable -- and accepting an encoded or dot-segment spelling of the
    same path would mean re-deriving every normalisation rule correctly for
    no benefit at all.
    """
    for bad in ("/callback", "/callback//", "/Callback/", "/callback/x",
                "/other/", "/", "/%63allback/", "/callback/../callback/"):
        with pytest.raises(ValueError, match="path"):
            parse(request(target=bad + "?state=xyz"))


def test_target_with_no_query_parses_to_an_empty_mapping():
    """A bare callback hit is well-formed; it just carries nothing."""
    assert parse(request(target="/callback/")) == {}
    assert parse(request(target="/callback/?")) == {}


def test_rejects_a_fragment_in_the_target():
    """Browsers never send one to a server, so its presence means something
    other than a browser assembled this request."""
    with pytest.raises(ValueError, match="fragment"):
        parse(request(target="/callback/?state=xyz#frag"))


def test_rejects_duplicate_query_keys():
    """No last-wins parameter smuggling.

    Two `state` values is the shape where a checker reading the first copy
    and a consumer reading the last disagree about what the request said.
    Rejecting is the only answer that does not depend on agreeing which copy
    wins.
    """
    with pytest.raises(ValueError, match="duplicate"):
        parse(request(target="/callback/?state=xyz&state=abc"))
    with pytest.raises(ValueError, match="duplicate"):
        parse(request(target="/callback/?code=a&state=xyz&code=b"))


def test_rejects_invalid_percent_encoding():
    """Validated BEFORE unquoting, because unquote() is lenient: it leaves a
    malformed escape in place rather than failing, so "%zz" would survive
    into a value that later reads as three characters nobody wrote."""
    for bad in ("state=%zz", "state=%", "state=%A", "%zz=xyz"):
        with pytest.raises(ValueError, match="percent"):
            parse(request(target="/callback/?" + bad))


def test_percent_encoding_is_decoded():
    assert parse(request(target="/callback/?state=a%2Fb")) == {"state": "a/b"}


def test_plus_becomes_a_space():
    """Form encoding, which is what a browser produces here. Leaving '+'
    alone would make a state comparison fail for a state that matched."""
    assert parse(request(target="/callback/?state=a+b")) == {"state": "a b"}


def test_a_key_with_no_equals_reads_as_an_empty_value():
    assert parse(request(target="/callback/?state")) == {"state": ""}


def test_empty_segments_are_skipped():
    assert parse(request(target="/callback/?&state=xyz&")) == {"state": "xyz"}


def test_rejects_an_oversized_query_key_or_value():
    """MAX_QUERY_KEY_CHARS (128) is well under MAX_LINE_BYTES, so an
    oversized key is reachable on its own line. An oversized *value* is not
    independently testable this way: MAX_QUERY_VALUE_CHARS equals
    MAX_LINE_BYTES (8192, matching ReadAsciiLineAsync's cap in the C# source),
    so any request line carrying a value one character over that limit is
    already over the *line* limit before the query check ever runs, and
    rejects with that message instead. That is not a bug in this parser --
    the two caps are the same number on purpose -- it just means only the
    key half of this rule is exercisable in isolation.
    """
    with pytest.raises(ValueError, match="query"):
        parse(request(target="/callback/?" + "k" * 129 + "=v"))


# ---------------------------------------------------------------------------
# Cycle 4 -- safe_oauth_code and the listener's success path
# ---------------------------------------------------------------------------

def test_safe_oauth_code_filters_and_truncates():
    """Anything outside [A-Za-z0-9_-] is dropped; anything past 64 is cut.

    This is the filter the ERROR value passes through before it can reach a
    log line or a user-visible message. It is NOT applied to the
    authorization code -- see the listener tests below.
    """
    assert loopback.safe_oauth_code("access_denied") == "access_denied"
    assert loopback.safe_oauth_code("a b<script>c") == "abscriptc"
    assert len(loopback.safe_oauth_code("x" * 200)) == 64


def test_safe_oauth_code_never_returns_empty():
    """An empty string in a message reads as "no error", which is a lie
    when the callback carried one. Non-string inputs land here too, because
    this runs on the failure path where a TypeError would replace the real
    diagnosis."""
    for value in ("", "   ", "<<<>>>", None, 42, ["a"]):
        assert loopback.safe_oauth_code(value) == "oauth_error"


def free_port() -> int:
    """A port nothing is listening on right now.

    Tests take a fresh port each rather than sharing one: SO_REUSEADDR is
    deliberately OFF in the listener, so a TIME_WAIT connection left behind
    by an earlier test would make the next bind fail.
    """
    probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


def send(port: int, raw: bytes) -> bytes:
    """Send one raw request to the listener and read the whole reply."""
    client = _socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        client.sendall(raw)
        chunks = []
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        client.close()


def listener_request(port, target, host=None):
    host = host or f"127.0.0.1:{port}"
    return (f"GET {target} HTTP/1.1\r\nHost: {host}\r\n\r\n").encode("ascii")


def deliver(port, target, into=None):
    """Start a thread that sends one request; returns (thread, sink list)."""
    sink = into if into is not None else []
    worker = threading.Thread(
        target=lambda: sink.append(send(port, listener_request(port, target))))
    worker.start()
    return worker, sink


def test_listener_returns_the_callback_on_a_matching_state():
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=abc123&state=expected-state")
        callback = listener.wait("expected-state", timeout_s=5)
        worker.join(5)

    assert callback.code == "abc123"
    assert callback.error == ""
    assert sink[0].startswith(b"HTTP/1.1 200 OK")


def test_the_reply_is_a_page_not_a_redirect_and_is_never_cached():
    """A redirect would hand the whole query string -- authorization code
    included -- to whatever the Location header named. A cacheable page
    would leave the outcome in the browser's history store."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=abc123&state=s")
        listener.wait("s", timeout_s=5)
        worker.join(5)

    reply = sink[0]
    assert b"HTTP/1.1 200 OK" in reply
    assert b"Cache-Control: no-store" in reply
    assert b"Location:" not in reply


def test_the_authorization_code_is_never_echoed_into_the_page():
    """The served page ends up in a browser tab the user may screenshot,
    and the code is a live one-time credential until it is exchanged."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=SUPERSECRETCODE&state=s")
        listener.wait("s", timeout_s=5)
        worker.join(5)

    assert b"SUPERSECRETCODE" not in sink[0]


def test_a_hostile_error_value_cannot_escape_the_filter():
    """The error string reaches a user-visible message, so it goes through
    the [A-Za-z0-9_-] filter first. Without it a hostile value carries
    markup, a newline that forges a second log record, or a URL, straight
    into the UI."""
    port = free_port()
    hostile = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, _ = deliver(port, f"/callback/?error={hostile}&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.error == "scriptalert1script"
    assert "<" not in callback.error and ">" not in callback.error


def test_the_authorization_code_is_taken_raw_not_filtered():
    """EveLoopbackCallback.cs:38-39: 'error' passes through SafeOAuthCode,
    'code' does not. RFC 6749 SS4.1.2 permits the whole printable-ASCII
    range in an authorization code, so filtering it to [A-Za-z0-9_-] would
    silently corrupt a legitimate code into something that reads as
    absent -- the listener would then hang for the full AUTH_TIMEOUT_S with
    no diagnostic anywhere. The code is protected by never being logged or
    displayed, not by being rewritten; sso.exchange_code's own non-blank /
    <=2048 / no-NUL checks are what validate it.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, _ = deliver(port, "/callback/?code=abc.def~123&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.code == "abc.def~123"


# ---------------------------------------------------------------------------
# Cycle 5 -- wait(): state comparison, persistence, timeout, cancellation
# ---------------------------------------------------------------------------

def test_a_wrong_state_does_not_end_the_wait():
    """The listener serves the failure page and KEEPS LISTENING.

    This is what makes the flow survive a stray hit on the callback port: an
    unrelated request -- a scanner, a stale tab, a forged navigation -- must
    not consume the one callback the user is about to deliver. The real
    browser tab may still be coming.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        replies = []

        def both():
            replies.append(send(port, listener_request(
                port, "/callback/?code=wrong&state=not-the-state")))
            replies.append(send(port, listener_request(
                port, "/callback/?code=right&state=expected-state")))

        worker = threading.Thread(target=both)
        worker.start()
        callback = listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    assert callback.code == "right"
    # Both requests were answered; only the second ended the wait.
    assert len(replies) == 2
    assert replies[0].startswith(b"HTTP/1.1 200 OK")
    assert b"not accepted" in replies[0]


def test_a_malformed_request_does_not_end_the_wait():
    """A parse rejection is a probe, not a failure of the flow."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        def both():
            send(port, b"GET /callback/?state=expected-state HTTP/1.1\r\n"
                       b"Host: evil.test\r\n\r\n")
            send(port, listener_request(
                port, "/callback/?code=right&state=expected-state"))

        worker = threading.Thread(target=both)
        worker.start()
        callback = listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    assert callback.code == "right"


def test_state_is_compared_in_constant_time():
    """hmac.compare_digest, not ==.

    The state is a CSRF token the caller minted; comparing it with == leaks
    a prefix-length oracle to anything that can time the failure page. This
    is asserted on the source because the timing itself is not observable
    from a test, and the invariant is what matters. Checked in both
    operand orders so a rewrite that merely swaps ("returned ==
    expected_state" for "expected_state == returned") does not slip past.
    """
    import inspect
    source = inspect.getsource(loopback.LoopbackListener.wait)
    assert "compare_digest" in source
    assert "expected_state ==" not in source
    assert "== returned" not in source


def test_a_non_ascii_state_does_not_crash_the_listener():
    """hmac.compare_digest raises TypeError when compared against a
    non-ASCII str -- Python explicitly refuses to time-compare non-ASCII
    text -- and a state of "%C3%A9" is valid UTF-8 that survives
    percent-decoding intact, so any page in the browser can forge it. That
    must be rejected as an ordinary mismatch (failure page, keep
    listening), not propagate an unhandled TypeError out of wait() and
    kill the whole auth attempt -- exactly the rejection-vs-exception
    inversion this module exists to prevent.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        replies = []

        def both():
            replies.append(send(port, listener_request(
                port, "/callback/?code=x&state=%C3%A9")))
            replies.append(send(port, listener_request(
                port, "/callback/?code=right&state=expected-state")))

        worker = threading.Thread(target=both)
        worker.start()
        callback = listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    assert callback.code == "right"
    assert len(replies) == 2
    assert b"not accepted" in replies[0]


def test_wait_times_out_when_the_browser_never_returns():
    """The overall deadline. Without it the auth worker thread never ends
    and the callback port is held for the life of the process."""
    port = free_port()
    with (
        loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener,
        pytest.raises(loopback.CallbackTimeout),
    ):
        listener.wait("expected-state", timeout_s=0.5)


def test_cancel_makes_a_pending_wait_raise():
    """The user closing the auth dialog must not leave a thread parked for
    five minutes holding the callback port."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        canceller = threading.Timer(0.2, listener.cancel)
        canceller.start()
        try:
            with pytest.raises(loopback.CallbackCancelled):
                listener.wait("expected-state", timeout_s=10)
        finally:
            canceller.cancel()


def test_cancel_interrupts_a_connection_mid_read():
    """cancel() must interrupt a read already in progress, not just the
    idle time between connections.

    connection.settimeout() alone bounds a single recv(), not the
    connection: a client that sends one byte every few seconds resets that
    clock on every read and is never cut off by it. The fix gives the
    connection a real deadline and polls `cancelled` while reading, so a
    slow or stalled client sitting mid-request does not leave wait()
    parked. The test above only cancels while idle in accept() and would
    have passed either way; this one cancels while a connection is stuck
    mid-header, which is what actually exercises the fix.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        client = _socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            # A request line with no terminating blank line: the server is
            # left waiting for more bytes that never arrive.
            client.sendall(b"GET /callback/?state=s HTTP/1.1\r\n"
                            b"Host: 127.0.0.1:%d\r\n" % port)
            canceller = threading.Timer(0.3, listener.cancel)
            canceller.start()
            start = time.monotonic()
            try:
                with pytest.raises(loopback.CallbackCancelled):
                    listener.wait("s", timeout_s=10)
            finally:
                canceller.cancel()
            elapsed = time.monotonic() - start
        finally:
            client.close()

    # Cancelled promptly (around the 0.3s timer plus polling slack), not
    # only once the full 10s wait deadline arrived.
    assert elapsed < 5


def test_an_error_callback_with_a_matching_state_is_returned():
    """A user clicking "Deny" is a real outcome, not a timeout: it must come
    back promptly so the UI can say what happened."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, _ = deliver(port, "/callback/?error=access_denied&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.error == "access_denied"
    assert callback.code == ""


def test_a_matching_state_with_neither_code_nor_error_returns_promptly():
    """EveLoopbackCallback.cs:38-41 returns as soon as the state matches,
    even when neither `code` nor `error` is present; the caller
    (EveSso.cs:60-63) is the one that aborts on a blank code. Two reasons
    the source does this rather than looping: it fails fast with "no
    authorization code" instead of hanging for the full AUTH_TIMEOUT_S, and
    it keeps the state single-use -- a listener that stayed open after a
    match would accept a second request bearing an already-matched state.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.code == ""
    assert callback.error == ""
    # Served as a failure page (neither code nor error is a usable outcome),
    # but the wait still ended -- it did not keep listening for another hit.
    assert b"not accepted" in sink[0]


def test_the_failure_reply_is_also_never_cached_and_not_a_redirect():
    """The success-path reply is checked elsewhere
    (test_the_reply_is_a_page_not_a_redirect_and_is_never_cached); the
    failure page is served far more often -- every mismatched state and
    every probe gets one -- and shares the same _reply() code path, but
    that was previously asserted only implicitly."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        replies = []

        def both():
            replies.append(send(port, listener_request(
                port, "/callback/?code=wrong&state=not-the-state")))
            replies.append(send(port, listener_request(
                port, "/callback/?code=right&state=expected-state")))

        worker = threading.Thread(target=both)
        worker.start()
        listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    failure = replies[0]
    assert b"HTTP/1.1 200 OK" in failure
    assert b"Cache-Control: no-store" in failure
    assert b"Location:" not in failure


def test_a_whitespace_only_code_reads_as_absent_for_the_reply_but_not_the_callback():
    """Whitespace-aware, matching IsNullOrWhiteSpace at
    EveLoopbackCallback.cs:40: a code of "  " is not a usable one, so the
    reply must be the failure page even though the code is technically
    non-empty. The Callback itself still carries the code RAW and
    untrimmed, consistent with test_the_authorization_code_is_taken_raw_
    not_filtered -- the whitespace check governs the reply only, not what
    is returned to the caller.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=%20%20&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.code == "  "
    assert b"not accepted" in sink[0]


# ---------------------------------------------------------------------------
# Bind retry -- a fixed port recovering from a recent TIME_WAIT, and a
# genuinely held port still failing, with a clearer message either way
# ---------------------------------------------------------------------------

def test_a_transient_bind_conflict_is_retried_and_recovers(monkeypatch):
    """The fixed port is very likely to have been listening a moment ago
    (this app's own previous run, or the previous auth attempt), sitting
    in TIME_WAIT after this side closed the connection. That is not
    another owner -- it clears on its own within the retry window -- so
    __enter__ must not fail on the first attempt."""
    real_bind = _socket.socket.bind
    attempts = []

    def flaky_bind(self, address):
        attempts.append(address)
        if len(attempts) < 3:
            raise OSError(98, "Address already in use")
        return real_bind(self, address)

    port = free_port()
    monkeypatch.setattr(_socket.socket, "bind", flaky_bind)
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH):
        pass
    assert len(attempts) == 3


def test_a_persistent_bind_conflict_still_fails_with_a_clear_message():
    """A port genuinely held by something else -- here, another listening
    socket bound for the whole retry window -- must still be reported as a
    conflict rather than retried forever, and the message must name the
    port and suggest what a user can do about it."""
    port = free_port()
    holder = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        with pytest.raises(OSError) as excinfo, loopback.LoopbackListener(
            host="127.0.0.1", port=port, path=PATH
        ):
            pass
        assert str(port) in str(excinfo.value)
    finally:
        holder.close()
