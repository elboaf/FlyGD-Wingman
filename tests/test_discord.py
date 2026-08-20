import io
import logging

import pytest

from obs_youtube_uploader import discord

GOOD = "https://discord.com/api/webhooks/1234567890/abcDEF-token_xyz"


def test_parses_a_valid_webhook():
    hook, err = discord.parse_webhook(GOOD)
    assert err == ""
    assert hook is not None and hook.webhook_id == "1234567890"


def test_accepts_discordapp_host():
    hook, err = discord.parse_webhook(
        "https://discordapp.com/api/webhooks/1234567890/tok")
    assert err == "" and hook is not None


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_rejects_empty(raw):
    hook, err = discord.parse_webhook(raw)
    assert hook is None and err


def test_rejects_http():
    hook, err = discord.parse_webhook(GOOD.replace("https://", "http://"))
    assert hook is None and "https" in err.lower()


def test_rejects_foreign_host():
    hook, err = discord.parse_webhook(
        "https://evil.example.com/api/webhooks/1234567890/tok")
    assert hook is None and "host" in err.lower()


def test_rejects_malformed_path():
    hook, err = discord.parse_webhook("https://discord.com/api/not-webhooks/1/2")
    assert hook is None and err


def test_rejects_missing_token():
    hook, err = discord.parse_webhook("https://discord.com/api/webhooks/1234567890")
    assert hook is None and err


def test_describe_shows_id_and_hides_token():
    hook, _ = discord.parse_webhook(GOOD)
    described = discord.describe(hook)
    assert "1234567890" in described
    assert "abcDEF-token_xyz" not in described


def test_redact_removes_the_full_url():
    hook, _ = discord.parse_webhook(GOOD)
    msg = f"POST {GOOD} failed with 500"
    out = discord.redact(msg, hook)
    assert GOOD not in out and "abcDEF-token_xyz" not in out


def test_redact_removes_a_bare_token():
    """The token can appear without the URL around it, e.g. in a JSON error."""
    hook, _ = discord.parse_webhook(GOOD)
    out = discord.redact('{"token": "abcDEF-token_xyz"}', hook)
    assert "abcDEF-token_xyz" not in out


def test_redact_is_a_noop_without_a_webhook():
    assert discord.redact("nothing to hide", None) == "nothing to hide"


def test_logging_filter_redacts_a_foreign_logger(caplog):
    """Call-site redaction cannot cover library loggers: configure_logging
    attaches to the ROOT logger, so an HTTP transport logging its request URL
    would write the token to disk without passing through our code."""
    hook, _ = discord.parse_webhook(GOOD)
    filt = discord.RedactingFilter(lambda: hook)
    logger = logging.getLogger("some.third.party.transport")
    logger.addFilter(filt)
    try:
        with caplog.at_level(logging.INFO, logger="some.third.party.transport"):
            logger.info("sending to %s", GOOD)
        rendered = "\n".join(r.getMessage() for r in caplog.records)
        assert "abcDEF-token_xyz" not in rendered
    finally:
        logger.removeFilter(filt)


def test_logging_filter_survives_no_webhook_configured():
    filt = discord.RedactingFilter(lambda: None)
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "plain message", (), None)
    assert filt.filter(record) is True
    assert record.getMessage() == "plain message"


def test_redact_does_not_corrupt_unrelated_text_when_token_is_short_and_common():
    """A malformed-but-parseable webhook could carry a one-character token.
    Blindly replacing every occurrence of it would mangle unrelated text."""
    hook, err = discord.parse_webhook("https://discord.com/api/webhooks/999/x")
    assert err == ""
    out = discord.redact("the x-ray machine can see x rays", hook)
    assert out == "the x-ray machine can see x rays"


def test_redact_does_not_corrupt_the_id_when_token_is_a_substring_of_it():
    """If the token happens to be a substring of the webhook id, redacting the
    bare token must not also mangle the id that describe() displays."""
    hook, err = discord.parse_webhook(
        "https://discord.com/api/webhooks/123999/abcDEF-token_xyz")
    assert err == ""
    msg = f"POST {hook.url} failed"
    out = discord.redact(msg, hook)
    assert "123999" in out
    assert "abcDEF-token_xyz" not in out


def test_redact_is_a_noop_for_non_string_input():
    """redact() must not crash if handed something other than a str."""
    hook, _ = discord.parse_webhook(GOOD)
    assert discord.redact(None, hook) is None
    assert discord.redact(42, hook) == 42


def test_describe_uses_the_actual_configured_host():
    """describe() must not hardcode discord.com: a ptb.discord.com or
    canary.discord.com webhook should be shown with its real host, not a
    silently wrong one."""
    hook, err = discord.parse_webhook(
        "https://ptb.discord.com/api/webhooks/1234567890/abcDEF-token_xyz")
    assert err == ""
    described = discord.describe(hook)
    assert "ptb.discord.com" in described
    assert "abcDEF-token_xyz" not in described


def test_logging_filter_redacts_exception_tracebacks():
    """The filter must not just rewrite record.msg: logger.exception() embeds
    the traceback text (str(exc)) via record.exc_info, which a Formatter
    renders separately from getMessage(). A test that only checks
    getMessage()/caplog.text is blind to this leak -- it must go through a
    real Formatter, exactly as a file handler would."""
    hook, _ = discord.parse_webhook(GOOD)
    filt = discord.RedactingFilter(lambda: hook)
    logger = logging.getLogger("test.discord.exc_info_redaction")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(filt)
    logger.addHandler(handler)
    try:
        try:
            raise ValueError(f"bad response from {GOOD}")
        except ValueError:
            logger.exception("post failed")
    finally:
        logger.removeHandler(handler)
    out = buf.getvalue()
    assert "abcDEF-token_xyz" not in out


def test_logging_filter_redacts_stack_info():
    """stack_info=True appends captured stack text the same way exc_info
    does; it must be redacted too."""
    hook, _ = discord.parse_webhook(GOOD)
    filt = discord.RedactingFilter(lambda: hook)
    logger = logging.getLogger("test.discord.stack_info_redaction")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(filt)
    logger.addHandler(handler)
    try:
        logger.info(f"webhook is {GOOD}", stack_info=True)
    finally:
        logger.removeHandler(handler)
    out = buf.getvalue()
    assert "abcDEF-token_xyz" not in out


class FakeResponse:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return b""


def _transport(status=204, exc=None):
    calls = []

    def send(request, timeout=None):
        calls.append(request)
        if exc is not None:
            raise exc
        return FakeResponse(status)

    send.calls = calls
    return send


def test_successful_post_reports_ok(tmp_path):
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    result = discord.post_archive(hook, zip_path, "fight", transport=_transport(204))
    assert result.ok


def test_post_sends_multipart_to_the_webhook_url(tmp_path):
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    t = _transport(200)
    discord.post_archive(hook, zip_path, "fight", transport=t)
    req = t.calls[0]
    assert req.full_url == GOOD
    assert "multipart/form-data" in req.headers.get("Content-type", "")
    assert b"payload" in req.data


@pytest.mark.parametrize("status,fragment", [
    (401, "invalid"), (404, "invalid"), (413, "too large"), (429, "rate"),
])
def test_error_statuses_map_to_plain_language(tmp_path, status, fragment):
    import urllib.error
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    err = urllib.error.HTTPError(GOOD, status, "err", {}, None)
    result = discord.post_archive(hook, zip_path, "fight", transport=_transport(exc=err))
    assert not result.ok
    assert fragment in result.message.lower()


def test_failure_message_never_contains_the_token(tmp_path):
    import urllib.error
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    err = urllib.error.HTTPError(GOOD, 500, f"boom at {GOOD}", {}, None)
    result = discord.post_archive(hook, zip_path, "fight", transport=_transport(exc=err))
    assert "abcDEF-token_xyz" not in result.message


def test_refuses_an_oversized_archive_without_posting(tmp_path):
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"x" * (discord.MAX_ATTACHMENT_BYTES + 1))
    t = _transport(204)
    result = discord.post_archive(hook, zip_path, "fight", transport=t)
    assert not result.ok
    assert "too large" in result.message.lower()
    assert t.calls == [], "must not hit the network when it cannot succeed"


def test_network_error_is_reported_not_raised(tmp_path):
    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    result = discord.post_archive(hook, zip_path, "fight",
                                  transport=_transport(exc=OSError("no route")))
    assert not result.ok and result.message


def test_unreadable_archive_is_reported_not_raised(tmp_path):
    """_build_multipart's read_bytes() sits outside the stat() guard above it.

    stat() can succeed on a file the process then cannot read (permissions
    revoked between the two calls, or any other unreadable-but-stat-able
    state); that must still come back as PostResult(ok=False), not a raised
    PermissionError, or post_archive's documented "never raises" contract is
    broken and app.py's recovery message (where the archive was kept) never
    gets shown.
    """
    import os

    hook, _ = discord.parse_webhook(GOOD)
    zip_path = tmp_path / "a.zip"
    zip_path.write_bytes(b"payload")
    os.chmod(zip_path, 0)
    try:
        result = discord.post_archive(hook, zip_path, "fight", transport=_transport(204))
    finally:
        # Restore so the fixture's tmp_path cleanup can remove the file.
        os.chmod(zip_path, 0o644)
    # Root (and some CI/container setups) ignores file permission bits, so
    # this would not raise PermissionError there -- assert the contract
    # rather than the specific errno.
    assert isinstance(result, discord.PostResult)
    assert result.ok is False


def test_the_default_opener_refuses_redirects():
    """Guards _default_transport's actual wiring, not just _NoRedirectHandler
    in isolation -- every other post_archive test injects a fake transport,
    so nothing else would catch a refactor that rebuilt _opener without the
    no-redirect handler (which would then silently follow a Location header
    to a host the allowlist in parse_webhook() never validated).
    """
    names = [type(h).__name__ for h in discord._opener.handlers]
    assert "HTTPRedirectHandler" not in names
    assert "_NoRedirectHandler" in names
