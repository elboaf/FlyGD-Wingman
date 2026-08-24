"""The OAuth callback listener: a raw socket and a deliberately strict parser.

This is a RAW SOCKET, not http.server, and the strict parser is the entire
reason. http.server would happily accept duplicate query keys (last wins),
non-ASCII request bytes, an arbitrary Host header, and a target that merely
normalises to the callback path. Every one of those is a rejection here:

- duplicate query keys are how a parameter is smuggled past a check that
  read the first copy while the consumer reads the last,
- the Host check is the DNS-rebinding guard, and a duplicate Host is how
  that guard gets bypassed by whichever copy the checker did not read,
- non-ASCII is not something a browser sends to a loopback callback, so
  accepting it only widens what has to be reasoned about.

parse_request is pure over bytes so that all of the above is testable with
no socket, no browser, and no timing. It ports EveLoopbackCallback.cs.

Ports EveLoopbackCallback.cs, with one correction to the port itself: the C#
filters `error` through SafeOAuthCode and takes `code` raw
(EveLoopbackCallback.cs:38-39). RFC 6749 SS4.1.2 permits the whole
printable-ASCII range in an authorization code, so filtering it the way
`error` is filtered would silently corrupt a legitimate code into something
that reads as absent, and the listener would hang for the full
AUTH_TIMEOUT_S with no diagnostic anywhere. The code is protected by never
being logged or displayed, not by being rewritten; sso.exchange_code's own
non-blank / <=2048 / no-NUL checks are what validate it.
"""
import hmac
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import unquote

CONNECTION_TIMEOUT_S = 10.0
AUTH_TIMEOUT_S = 300.0
MAX_LINE_BYTES = 8192
MAX_HEADER_BYTES = 32 * 1024
MAX_QUERY_KEY_CHARS = 128
MAX_QUERY_VALUE_CHARS = 8192

# How long a blocking accept() waits before rechecking cancellation and the
# overall deadline. Short enough that cancel() feels immediate, long enough
# that a five-minute wait is not a busy loop.
_ACCEPT_POLL_S = 0.25

# The filter applied to the ERROR value only (never the code) before it can
# reach a log line or a user-visible message.
_CODE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
_HEX = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True)
class Callback:
    code: str
    error: str


class CallbackTimeout(Exception):
    """The browser never came back within the overall deadline."""


class CallbackCancelled(Exception):
    """The wait was cancelled from another thread."""


def _read_line(raw: bytes, offset: int) -> tuple[str, int]:
    """Read one CRLF-terminated ASCII line, returning it and the next offset."""
    end = raw.find(b"\n", offset)
    if end < 0:
        # A truncated request must fail rather than be parsed as far as it
        # got: a half-arrived header set could omit the Host line entirely,
        # and that line is the DNS-rebinding guard.
        raise ValueError("Local callback request ended without a complete line.")
    chunk = raw[offset:end]
    if chunk.endswith(b"\r"):
        chunk = chunk[:-1]
    if len(chunk) > MAX_LINE_BYTES:
        raise ValueError("Local callback line exceeded its configured limit.")
    for byte in chunk:
        # NUL and anything above 0x7F. A browser navigating to a loopback
        # callback sends neither, so accepting them only widens the surface
        # everything below has to be correct against.
        if byte == 0 or byte > 127:
            raise ValueError("Local callback contained non-ASCII request data.")
    return chunk.decode("ascii"), end + 1


def parse_request(raw: bytes, *, expected_host: str,
                  expected_path: str) -> dict[str, str]:
    """Parse a callback request, returning its query mapping.

    Raises ValueError on any violation. There is no tolerant mode.
    """
    request_line, offset = _read_line(raw, 0)
    # Split on a single space with no empty-entry collapsing: a tolerant
    # split accepts "GET  /callback/  HTTP/1.1" and "GET /x HTTP/1.1 extra",
    # neither of which any browser sends.
    pieces = request_line.split(" ")
    if (len(pieces) != 3 or pieces[0] != "GET" or pieces[2] != "HTTP/1.1"
            or not pieces[1].startswith("/")):
        # startswith("/") pins origin-form: an absolute-form target is
        # another way to name an authority the Host check never sees.
        raise ValueError("Local callback request line was not a plain GET.")
    return _parse_headers(pieces[1], raw, offset,
                          expected_host=expected_host,
                          expected_path=expected_path)


def _parse_headers(target: str, raw: bytes, offset: int, *,
                   expected_host: str, expected_path: str) -> dict[str, str]:
    host = None
    header_bytes = 0
    while True:
        line, offset = _read_line(raw, offset)
        if line == "":
            break
        # +2 for the CRLF the line reader stripped. Individually-legal lines
        # still have to stop somewhere.
        header_bytes += len(line) + 2
        if header_bytes > MAX_HEADER_BYTES:
            raise ValueError("Local callback headers exceeded their configured limit.")
        separator = line.find(":")
        if separator <= 0:
            # <= 0 rather than < 0: an empty header name is malformed, and
            # ": Host: evil.test" is a way to smuggle one past a checker
            # that splits on the first colon.
            raise ValueError("Local callback sent a malformed header.")
        if line[:separator].strip().lower() != "host":
            continue
        if host is not None:
            raise ValueError("Local callback contained duplicate Host headers.")
        host = line[separator + 1:].strip()

    # The DNS-rebinding guard. A page on any origin can point a name at
    # 127.0.0.1 and make the browser issue this exact request; what it
    # cannot do is forge the Host header, which still carries the name the
    # browser resolved. Compared case-insensitively because case carries no
    # meaning in a hostname, and by equality because a port-less or
    # differently-ported authority is a different authority.
    if host is None or host.lower() != expected_host.lower():
        raise ValueError("Local callback Host header did not match the redirect authority.")

    return _parse_target(target, expected_path=expected_path)


def _parse_target(target: str, *, expected_path: str) -> dict[str, str]:
    if "#" in target:
        # Browsers never send a fragment to a server, so its presence here
        # means something other than a browser assembled this request.
        raise ValueError("Local callback target contained a fragment.")
    marker = target.find("?")
    path = target if marker < 0 else target[:marker]
    query = "" if marker < 0 else target[marker + 1:]
    # An EXACT literal match. EVE echoes the registered redirect_uri back
    # verbatim, so exactness is achievable -- and accepting "/%63allback/"
    # or "/callback/../callback/" as the same path would mean re-deriving
    # every normalisation rule correctly, for no benefit at all.
    if path != expected_path:
        raise ValueError("Local callback target did not match the redirect path.")
    return _parse_query(query)


def _ensure_percent_encoding(value: str) -> None:
    """Reject malformed escapes BEFORE unquoting.

    unquote() is lenient: it leaves a malformed escape in place rather than
    failing, so "%zz" would survive into a value that reads as three
    characters nobody wrote.
    """
    index = 0
    while index < len(value):
        if value[index] == "%":
            if (index + 2 >= len(value) or value[index + 1] not in _HEX
                    or value[index + 2] not in _HEX):
                raise ValueError("Local callback query contained invalid percent encoding.")
            index += 2
        index += 1


def _parse_query(query: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key_text, separator, value_text = part.partition("=")
        _ensure_percent_encoding(key_text)
        if separator:
            _ensure_percent_encoding(value_text)
        # '+' means space here: this is form encoding, and leaving it alone
        # would make a state comparison fail for a state that matched.
        # errors="strict" so an escape that is syntactically valid but not
        # valid UTF-8 raises (UnicodeDecodeError is a ValueError) rather
        # than producing replacement characters.
        key = unquote(key_text.replace("+", " "), errors="strict")
        value = (unquote(value_text.replace("+", " "), errors="strict")
                 if separator else "")
        if len(key) > MAX_QUERY_KEY_CHARS or len(value) > MAX_QUERY_VALUE_CHARS:
            raise ValueError("Local callback query exceeded its configured limit.")
        if key in result:
            # No last-wins smuggling: two `state` values is the shape where
            # the checker and the consumer disagree about what was sent.
            raise ValueError("Local callback query contained a duplicate key.")
        result[key] = value
    return result


def safe_oauth_code(value: object) -> str:
    """Filter the ERROR value down to something safe to log or display.

    Everything outside [A-Za-z0-9_-] is dropped and the result is truncated
    to 64 characters. This is applied to `error` only -- never to `code`,
    see the module docstring -- because a hostile `error` string arrives
    straight from the network and must never carry markup, a newline that
    forges a second log record, or a URL, into the UI.

    Non-string input is coerced rather than rejected: this runs on the
    failure path, where a TypeError would replace the real diagnosis.

    It never returns "": an empty string in a message reads as "no error",
    which is a lie when the callback carried one.
    """
    text = value if isinstance(value, str) else ""
    safe = "".join(ch for ch in text if ch in _CODE_CHARS)[:64]
    return safe or "oauth_error"


_SUCCESS_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>FlyGD Wingman</title></head><body><p>Authentication complete. "
    "You can close this tab and return to Wingman.</p></body></html>")
_FAILURE_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>FlyGD Wingman</title></head><body><p>Authentication was not "
    "accepted. You can close this tab and return to Wingman.</p></body></html>")


def _reply(connection, success: bool) -> None:
    """Serve the tiny result page.

    Always 200 and never a redirect: a 3xx would hand the whole query string
    -- authorization code included -- to whatever the Location header named.
    The page never echoes the code either, because it ends up in a browser
    tab the user may well screenshot. no-store keeps the outcome out of the
    browser's history store.
    """
    body = (_SUCCESS_HTML if success else _FAILURE_HTML).encode("utf-8")
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n").encode("ascii")
    try:
        connection.sendall(headers + body)
    except OSError:
        # The browser closing first is normal and is not a failure of the
        # flow: the callback has already been read off the wire.
        pass


def _read_request(connection) -> bytes:
    """Read until the end of the header block, bounded."""
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = connection.recv(4096)
        if not chunk:
            break
        buffer += chunk
        if len(buffer) > MAX_HEADER_BYTES + MAX_LINE_BYTES:
            raise ValueError("Local callback request exceeded its configured limit.")
    return bytes(buffer)


class LoopbackListener:
    """A single-port loopback listener for one OAuth callback."""

    def __init__(self, *, host: str, port: int, path: str) -> None:
        self._host = host
        self._port = port
        self._path = path
        self._authority = f"{host}:{port}"
        self._socket = None
        self._cancelled = threading.Event()

    def __enter__(self) -> "LoopbackListener":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR is deliberately NOT set. The port is fixed because
        # the redirect URI is registered with CCP and must match exactly,
        # and a bind failure means something else already holds the port --
        # a plain, reportable condition, not something to paper over by
        # sharing the port with whatever that something is.
        try:
            sock.bind((self._host, self._port))
            sock.listen(4)
        except OSError:
            sock.close()
            raise
        self._socket = sock
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def cancel(self) -> None:
        """Make a pending wait() raise CallbackCancelled."""
        self._cancelled.set()

    def wait(self, expected_state: str, *,
             timeout_s: float = AUTH_TIMEOUT_S) -> Callback:
        """Serve callback hits until one carries the expected state.

        Raises CallbackTimeout at the overall deadline and CallbackCancelled
        when cancel() is called from another thread.
        """
        if self._socket is None:
            raise RuntimeError("The loopback listener is not open.")
        deadline = time.monotonic() + timeout_s
        while True:
            if self._cancelled.is_set():
                raise CallbackCancelled("EVE authentication was cancelled.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CallbackTimeout("EVE authentication timed out.")
            # Poll rather than block for the whole remaining time, so that
            # cancel() takes effect promptly without another thread having
            # to tear the listening socket down underneath this one.
            self._socket.settimeout(min(remaining, _ACCEPT_POLL_S))
            try:
                connection, _ = self._socket.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                if self._cancelled.is_set():
                    raise CallbackCancelled("EVE authentication was cancelled.")
                raise
            try:
                # Per-connection timeout: a client that connects and then
                # says nothing must not hold the whole flow hostage.
                connection.settimeout(CONNECTION_TIMEOUT_S)
                try:
                    query = parse_request(_read_request(connection),
                                          expected_host=self._authority,
                                          expected_path=self._path)
                except (ValueError, OSError):
                    # A rejected request is a probe -- a scanner, a stale
                    # tab, a forged navigation. It is not a failure of the
                    # flow, and consuming the wait would mean the real
                    # browser tab arrives to a closed port.
                    continue

                # compare_digest, not ==: the state is a CSRF token, and ==
                # leaks a prefix-length oracle to anything that can time the
                # failure page below.
                returned = query.get("state", "")
                if not hmac.compare_digest(expected_state, returned):
                    _reply(connection, False)
                    continue

                # Once the state matches, RETURN -- even when neither `code`
                # nor `error` is present. EveLoopbackCallback.cs:38-41 returns
                # immediately here; the caller (EveSso.cs:60-63) aborts on a
                # blank code. Staying open instead would mean hanging for
                # the full AUTH_TIMEOUT_S on an anomalous hit rather than
                # failing fast, and would let the state be presented a
                # second time -- it must be single-use.
                error = safe_oauth_code(query["error"]) if "error" in query else ""
                # The code is taken RAW -- never filtered or truncated. See
                # the module docstring for why: filtering would silently
                # corrupt a legitimate code, and the code is protected by
                # never being logged, not by being rewritten.
                code = query.get("code", "")
                _reply(connection, success=not error and bool(code))
                return Callback(code=code, error=error)
            finally:
                try:
                    connection.close()
                except OSError:
                    pass
