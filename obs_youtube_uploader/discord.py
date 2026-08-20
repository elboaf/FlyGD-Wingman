"""Discord webhook posting.

A webhook URL is a bearer credential: anyone holding it can post to that
channel indefinitely. Unlike the OAuth token it does not expire, cannot be
scoped, and has no revocation UI short of deleting the webhook server-side.
Nothing here may ever surface one in full.
"""
import logging
import traceback
from dataclasses import dataclass
from urllib.parse import urlparse

# The only hosts Discord serves webhooks from. Deliberately not a suffix
# match: "discord.com.evil.example" must not pass.
_ALLOWED_HOSTS = frozenset({"discord.com", "discordapp.com", "ptb.discord.com",
                            "canary.discord.com"})

# Real Discord webhook tokens are long, high-entropy strings (well over 60
# characters). A malformed-but-parseable URL could in principle carry a
# short or common token (e.g. a single letter); blindly replacing every
# occurrence of that substring anywhere in a log line would corrupt unrelated
# text instead of redacting a secret. Below this length we skip the bare
# token pass entirely; the full URL is still always redacted verbatim.
_MIN_REDACTABLE_TOKEN_LEN = 8

# Placeholder used while redacting so that a token which happens to be a
# substring of the webhook id can never corrupt the id text that describe()
# inserts. The URL is replaced with this sentinel first, the bare token is
# then redacted from what remains of the original text, and only afterwards
# is the sentinel swapped for the human-readable describe() string.
_SENTINEL = "\x00__discord_webhook__\x00"


@dataclass(frozen=True)
class Webhook:
    url: str
    webhook_id: str
    token: str
    host: str = "discord.com"


def parse_webhook(raw: str | None) -> tuple[Webhook | None, str]:
    """Validate a webhook URL. Returns (webhook, error); error is "" on success."""
    if raw is None or not raw.strip():
        return None, "Enter a Discord webhook URL."
    candidate = raw.strip()
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None, "That is not a valid URL."
    if parsed.scheme != "https":
        return None, "Webhook URL must use https."
    if parsed.hostname is None or parsed.hostname.lower() not in _ALLOWED_HOSTS:
        return None, f"'{parsed.hostname}' is not a Discord webhook host."
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4 or parts[0] != "api" or parts[1] != "webhooks":
        return None, ("That does not look like a Discord webhook URL "
                      "(expected .../api/webhooks/{id}/{token}).")
    host = parsed.hostname.lower()
    return Webhook(url=candidate, webhook_id=parts[2], token=parts[3], host=host), ""


def describe(webhook: Webhook | None) -> str:
    """A name for a webhook that omits its token, safe to display anywhere."""
    if webhook is None:
        return "(not configured)"
    return f"{webhook.host}/api/webhooks/{webhook.webhook_id}…"


def redact(text: str, webhook: Webhook | None) -> str:
    """Replace a webhook URL and its bare token with a safe description.

    Order matters: the full URL is redacted first (as a sentinel, not the
    final describe() text, so a token that is a substring of the webhook id
    cannot later corrupt the id once it's been inserted). The bare token is
    then stripped from whatever text remains, and only at the end is the
    sentinel swapped in for the human-readable description.
    """
    if webhook is None or not isinstance(text, str) or not text:
        return text
    out = text.replace(webhook.url, _SENTINEL)
    if webhook.token and len(webhook.token) >= _MIN_REDACTABLE_TOKEN_LEN:
        out = out.replace(webhook.token, "…")
    out = out.replace(_SENTINEL, describe(webhook))
    return out


class RedactingFilter(logging.Filter):
    """Redacts the configured webhook from every record, whatever emitted it.

    Installed on the root handler rather than applied at call sites: the app
    attaches its handler to the root logger, so every library logger inherits
    it, and an HTTP transport logging its request URL at DEBUG would write the
    token to disk without passing through any of our code. Call-site
    redaction cannot make that guarantee; this can.

    Covers the rendered message (record.msg/args), plus record.exc_text and
    record.stack_info -- a Formatter appends both of those independently of
    getMessage(), so logger.exception(...) or stack_info=True can otherwise
    write an unredacted token even when the message itself is clean.

    Takes a callable rather than a Webhook so it picks up a webhook the user
    configures after logging is already running.
    """

    def __init__(self, get_webhook):
        super().__init__()
        self._get_webhook = get_webhook

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            webhook = self._get_webhook()
        except Exception:
            return True
        if webhook is None:
            return True
        # Render once, then redact: the token may arrive via args rather than
        # in the format string.
        try:
            rendered = record.getMessage()
        except Exception:
            return True
        cleaned = redact(rendered, webhook)
        if cleaned != rendered:
            record.msg = cleaned
            record.args = ()
        # logger.exception(...)/exc_info=True embeds the traceback text
        # separately from getMessage() -- a Formatter appends record.exc_text
        # (deriving it from record.exc_info the first time it's needed) after
        # the rendered message. Rewriting record.msg alone leaves that text,
        # which can carry the webhook URL (e.g. "bad response from <url>"),
        # completely unredacted on disk. Pre-compute and redact it here so
        # the Formatter finds it already set and never re-derives it.
        if record.exc_info:
            try:
                if not record.exc_text:
                    record.exc_text = "".join(
                        traceback.format_exception(*record.exc_info))
                record.exc_text = redact(record.exc_text, webhook)
            except Exception:
                pass
        # stack_info=True appends record.stack_info the same way; it's
        # already a formatted string by the time a record carries it (built
        # eagerly by Logger._log), so it just needs redacting in place.
        if record.stack_info:
            try:
                record.stack_info = redact(record.stack_info, webhook)
            except Exception:
                pass
        return True
