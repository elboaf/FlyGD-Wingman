"""One independently protected Wanderer credential, bound to an instance and map.

The *entire* versioned binding is inside DPAPI, not just the token. Editing an
outer plaintext URL must never turn a valid blob into a credential for another
server. This protects data at rest, not against code running as the same user.
The controller owns serialization; this store caches no token or connection.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

from wingman import atomicio, paths
from wingman.eveauth import dpapi

from .model import normalize_base_url, normalize_map_identifier

MAX_AUTHORIZATION_BYTES = 512
MAX_DOCUMENT_BYTES = 16 * 1024
MAX_PROTECTED_BYTES = 8 * 1024
MAX_PLAINTEXT_BYTES = 4 * 1024
_VERSION = 1
_PURPOSE = "wingman.wanderer.credentials"


class CredentialError(OSError):
    """Fixed operation context only; never crypto, filesystem or token details."""


def validate_token(value: str) -> str:
    """Validate one opaque Bearer value without trimming or interpreting it."""
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_AUTHORIZATION_BYTES - len("Bearer ")
        or any(not 32 < ord(c) < 127 or c == "," for c in value)
    ):
        raise CredentialError("Wanderer token is invalid or exceeds supported limits.")
    return value


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


class CredentialStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        protect: Callable[[bytes], bytes] = dpapi.protect,
        unprotect: Callable[[bytes], bytes] = dpapi.unprotect,
    ) -> None:
        self._path = (
            path
            if path is not None
            else paths.state_dir() / "wanderer_credentials.json"
        )
        self._protect = protect
        self._unprotect = unprotect

    def load(self, base: str, map: str) -> str | None:
        """None only for absent/differently bound credentials; corrupt data raises.

        Reads and decrypts bounded data on every call. A caller may cache only
        under its own generation/connection lock, never implicitly in this store.
        """
        try:
            base, map = normalize_base_url(base), normalize_map_identifier(map)
            try:
                with self._path.open("rb") as stream:
                    raw = stream.read(MAX_DOCUMENT_BYTES + 1)
            except FileNotFoundError:
                return None
            outer = _document(raw, MAX_DOCUMENT_BYTES, {"version", "protected"})
            blob = base64.b64decode(outer["protected"], validate=True)
            if not 1 <= len(blob) <= MAX_PROTECTED_BYTES:
                raise ValueError("Invalid protected document.")
            inner = _document(
                self._unprotect(blob),
                MAX_PLAINTEXT_BYTES,
                {"version", "purpose", "base_url", "map_identifier", "token"},
            )
            if (
                inner["purpose"] != _PURPOSE
                or normalize_base_url(inner["base_url"]) != inner["base_url"]
                or normalize_map_identifier(inner["map_identifier"])
                != inner["map_identifier"]
            ):
                raise ValueError("Invalid protected document.")
            token = validate_token(inner["token"])
            return (
                token
                if (inner["base_url"], inner["map_identifier"]) == (base, map)
                else None
            )
        except Exception:  # noqa: BLE001, S110 - discard secret-bearing context; raise a fixed operation error below
            pass
        raise CredentialError("Wanderer credential could not be loaded.")

    def replace(self, base: str, map: str, token: str) -> None:
        """Protect and atomically replace; failure leaves the prior file intact."""
        try:
            inner = {
                "version": _VERSION,
                "purpose": _PURPOSE,
                "base_url": normalize_base_url(base),
                "map_identifier": normalize_map_identifier(map),
                "token": validate_token(token),
            }
            plaintext = json.dumps(inner, separators=(",", ":")).encode("utf-8")
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
            # Only ciphertext ever reaches atomic I/O, including its temp file.
            atomicio.write_atomic(self._path, outer)
            return
        except Exception:  # noqa: BLE001, S110 - discard secret-bearing context; raise a fixed operation error below
            pass
        raise CredentialError("Wanderer credential could not be saved.")

    def remove(self) -> None:
        """Idempotently delete only Wingman's credential, not configuration."""
        try:
            self._path.unlink(missing_ok=True)
            return
        except OSError:
            pass
        raise CredentialError("Wanderer credential could not be removed.")
