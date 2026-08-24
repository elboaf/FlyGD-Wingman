"""Refresh-token wrapping for storage inside the state document.

Only the refresh token is wrapped; the roster metadata beside it stays
plaintext. That split is deliberate: a corrupt or undecryptable blob costs
one character a re-authentication rather than making the whole document
unparseable.

The crypt callables are injected with production defaults, so everything
here -- including the undecryptable-blob path -- is tested on Linux while
only dpapi.py is Windows-only.

What this does NOT buy, stated so nobody reads more into it: against
malware running as the same user, DPAPI, Credential Manager and a plain
file are equivalent. CryptUnprotectData succeeds for that user with no
prompt. This is a defence for data at rest -- a stolen laptop, a disk
image, a backup, a %LOCALAPPDATA% redirected into OneDrive -- not against
local code execution.
"""
import base64
import binascii

from . import dpapi


def wrap(token: str, *, protect=dpapi.protect) -> str:
    """Encrypt *token* and return it as base64 text.

    Text, not bytes, because the result is stored as a JSON string field in
    the state document.

    "" in, "" out -- never encrypted. state.Character.refresh_token_blob
    documents "" as the sentinel for "no token stored", and unwrap("") is
    already the confirmed no-token case. Without this guard, protecting an
    empty string produces a non-empty blob that decrypts back to "": a
    value that reads as PRESENT to every `if character.refresh_token_blob:`
    check while carrying nothing, collapsing "never authenticated" and
    "authenticated with an empty token" into the same on-disk shape at
    exactly the point Task 14 decides whether to show a re-authenticate
    banner.
    """
    if not token:
        return ""
    return base64.b64encode(protect(token.encode("utf-8"))).decode("ascii")


def unwrap(blob: str, *, unprotect=dpapi.unprotect):
    """Decrypt *blob*, or return None if it cannot be read.

    None rather than an exception, and the except is deliberately broad.
    This is called while loading the state document, once per character. A
    blob fails to decrypt for reasons entirely outside our control -- the
    file was copied from another machine or another Windows account, the
    user's profile was recreated, a backup predates a key change, or the
    blob was hand-edited. Every one of those costs that character a
    re-authentication, which the UI already handles with a banner. Letting
    it propagate would take down the load and with it every OTHER
    character's authorisation, which is precisely the failure that putting
    the tokens in this document was meant to make impossible.
    """
    if not blob:
        return None
    try:
        # validate=True so stray characters are rejected here rather than
        # silently skipped, producing a shorter blob that then fails inside
        # crypt32 with a much less obvious message.
        raw = base64.b64decode(blob.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return None
    try:
        return unprotect(raw).decode("utf-8")
    except Exception:
        return None
