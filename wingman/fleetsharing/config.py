"""One configured relay, with an explicit identity boundary on origin changes."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

DEFAULT_RELAY_ORIGIN = "https://authgd.zoolanders.space"


def canonical_origin(value: str) -> str:
    """Bare HTTPS URL.origin, never userinfo or URL-parser cleanup of hostile input.

    DNS names are ASCII (IDNs must be supplied as punycode). Ambiguous numeric
    host spellings are refused rather than disagreeing with a browser's IPv4
    parser. No request is made while choosing an origin.
    """
    error = "Fleet relay origin must be a bare https:// origin."
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
        or any(c in value for c in "\\?#@%")
    ):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (
            parsed.scheme != "https"
            or not host
            or parsed.path not in ("", "/")
            or parsed.netloc.endswith(":")
        ):
            raise ValueError(error)
        if "[" in parsed.netloc or "]" in parsed.netloc:
            # CPython also accepts bracketed IPvFuture and removes its brackets
            # in .hostname. Validate the original authority before it can become
            # a different DNS credential destination or hide a prefix/suffix.
            authority = re.fullmatch(r"\[([^\[\]]+)\](?::[0-9]+)?", parsed.netloc)
            if authority is None:
                raise ValueError(error)
            host = f"[{ipaddress.IPv6Address(authority[1]).compressed}]"
        else:
            if len(host) > 253 or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in host.rstrip(".").split(".")
            ):
                raise ValueError(error)
            last = host.rstrip(".").split(".")[-1]
            if last.isdigit() or last.startswith("0x"):
                host = str(ipaddress.IPv4Address(host))
        return f"https://{host}" + (f":{port}" if port not in (None, 443) else "")
    except ValueError:
        raise ValueError(error) from None


def resolve_relay_origin(
    *, paired_origin: str | None = None, configured_origin: str | None = None
) -> str:
    """Default only unpaired installs; never forward an old identity to a new host.

    A caller choosing a different explicit origin must perform fresh pairing
    with a new key. This function neither drops nor rotates that identity.
    """
    paired = canonical_origin(paired_origin) if paired_origin is not None else None
    explicit = (
        canonical_origin(configured_origin) if configured_origin is not None else None
    )
    if paired is not None and explicit is not None and paired != explicit:
        raise ValueError("A different relay origin requires new pairing and a new key.")
    return paired or explicit or canonical_origin(DEFAULT_RELAY_ORIGIN)
