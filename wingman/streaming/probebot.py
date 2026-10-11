"""The probe bot's credential (#335): one DPAPI-protected bot token.

Mirrors wanderer/credentials.py's shape: the whole versioned binding is
inside DPAPI (purpose string included), only ciphertext reaches atomic
I/O, and nothing is cached. Separate purpose and file from the Wanderer
store -- two credentials must never share a document -- and separate
validation: bot tokens are three dot-separated base64 parts, not opaque
Bearer values.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

from wingman import atomicio, paths
from wingman.eveauth import dpapi
from wingman.streaming.probe import validate_token_format

MAX_DOCUMENT_BYTES = 16 * 1024
MAX_PROTECTED_BYTES = 8 * 1024
MAX_PLAINTEXT_BYTES = 1 * 1024
_VERSION = 1
_PURPOSE = "wingman.streaming.probe-bot"
_KEYS = {"version", "purpose", "token"}


class CredentialError(OSError):
    """Fixed operation context only; never crypto, filesystem or token detail."""


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Invalid protected document.")
        result[key] = value
    return result


def _document(raw: bytes, limit: int, keys: set[str]) -> dict:
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError("Invalid protected document.")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    if (
        not isinstance(data, dict)
        or data.keys() != keys
        or type(data["version"]) is not int
        or data["version"] != _VERSION
    ):
        raise ValueError("Invalid protected document.")
    return data


class BotTokenStore:
    """Load/replace/remove the probe bot's token, bound to this purpose."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        protect: Callable[[bytes], bytes] = dpapi.protect,
        unprotect: Callable[[bytes], bytes] = dpapi.unprotect,
    ) -> None:
        self._path = (
            path if path is not None else paths.state_dir() / "probe_bot_token.json"
        )
        self._protect = protect
        self._unprotect = unprotect

    def load(self) -> str | None:
        """The token, or None when none is stored. Corrupt/unreadable
        data raises CredentialError -- a silent None would read as "not
        configured" and the card would offer setup for a broken store."""
        try:
            try:
                with self._path.open("rb") as stream:
                    raw = stream.read(MAX_DOCUMENT_BYTES + 1)
            except FileNotFoundError:
                return None
            outer = _document(raw, MAX_DOCUMENT_BYTES, {"version", "protected"})
            blob = base64.b64decode(outer["protected"], validate=True)
            if not 1 <= len(blob) <= MAX_PROTECTED_BYTES:
                raise ValueError("Invalid protected document.")
            inner = _document(self._unprotect(blob), MAX_PLAINTEXT_BYTES, _KEYS)
            if inner["purpose"] != _PURPOSE:
                raise ValueError("Invalid protected document.")
            token = inner["token"]
            if not validate_token_format(token):
                raise ValueError("Invalid protected document.")
            return token
        except Exception:  # noqa: BLE001, S110 - discard secret-bearing context
            pass
        raise CredentialError("Probe bot token could not be loaded.")

    def replace(self, token: str) -> None:
        """Protect and atomically replace; failure leaves the prior file intact."""
        try:
            if not validate_token_format(token):
                raise CredentialError("That is not a Discord bot token.")
            plaintext = json.dumps(
                {"version": _VERSION, "purpose": _PURPOSE, "token": token},
                separators=(",", ":"),
            ).encode("utf-8")
            if len(plaintext) > MAX_PLAINTEXT_BYTES:
                raise ValueError("Invalid protected document.")
            blob = self._protect(plaintext)
            if not isinstance(blob, bytes) or not 1 <= len(blob) <= MAX_PROTECTED_BYTES:
                raise ValueError("Invalid protected document.")
            outer = json.dumps(
                {
                    "version": _VERSION,
                    "protected": base64.b64encode(blob).decode("ascii"),
                },
                separators=(",", ":"),
            )
            if len(outer) > MAX_DOCUMENT_BYTES:
                raise ValueError("Invalid protected document.")
            atomicio.write_atomic(self._path, outer)
            return
        except CredentialError:
            raise
        except Exception:  # noqa: BLE001, S110 - discard secret-bearing context
            pass
        raise CredentialError("Probe bot token could not be saved.")

    def remove(self) -> None:
        """Idempotently delete only Wingman's probe bot credential."""
        try:
            self._path.unlink(missing_ok=True)
            return
        except OSError:
            pass
        raise CredentialError("Probe bot token could not be removed.")
