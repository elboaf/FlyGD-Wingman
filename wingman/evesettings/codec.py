"""Read and rewrite the contents of an EVE settings file.

This is the only module in Wingman that knows a ``.dat`` has structure. The
decoding itself happens in a bundled sidecar that is a pure filter — bytes on
stdin, JSON on stdout, and back — so it opens no files and has no path
handling to get wrong. Everything the settings layer already guarantees
(containment, backup-first, atomic publish, the sharing-violation retry) stays
in Python and is reused here unchanged. The sidecar's implementation is
deliberately not named in this module's public surface; a different one that
speaks the same two subcommands is a drop-in.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import atomicio, paths

# Same shape as stitch.py:27, hotkeys.py:30 and library.py:18: a console=False
# PyInstaller build would otherwise flash a console window per call.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# A settings file is ~150 KB and the codec runs in milliseconds; anything near
# this is a hung process, not a slow one. Applies per codec call --
# write_document makes two (encode, then a verifying decode) -- so the
# worker can hold the EVE mutation lock for up to 2x this value while
# waiting; it must not wait forever.
CODEC_TIMEOUT_S = 30.0

# TY_SIGNATURE2: every stream the codec writes starts with it (the client's
# own files start with 0x7e, version 0 — see the design doc's finding 7).
_SIGNATURE_V1 = b"\x7d"


class CodecError(Exception):
    """The settings file could not be read or safely rewritten."""


class ContentChangedError(CodecError):
    """The settings file no longer has the expected readable content."""


@dataclass(frozen=True)
class Document:
    doc: dict
    had_crc: bool


@dataclass(frozen=True)
class DocumentSnapshot:
    document: Document
    content_revision: str


def codec_available(*, exe=paths.codec_exe) -> bool:
    return exe() is not None


def _run(mode: str, payload: bytes, *, runner, exe) -> bytes:
    binary = exe()
    if binary is None:
        raise CodecError("The settings codec is not available in this install.")
    try:
        result = runner(
            [binary, mode],
            input=payload,
            capture_output=True,
            timeout=CODEC_TIMEOUT_S,
            **_NO_WINDOW_KWARGS,
        )
    except subprocess.TimeoutExpired as error:
        raise CodecError("The settings codec took too long and was stopped.") from error
    except OSError as error:
        raise CodecError(str(error)) from error
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", "replace").strip()
        detail = detail.removeprefix("error: ") or f"exit status {result.returncode}"
        raise CodecError(detail)
    return result.stdout or b""


def _decode_bytes(raw: bytes, *, runner, exe) -> Document:
    out = _run("decode", raw, runner=runner, exe=exe)
    try:
        envelope = json.loads(out)
        return Document(doc=envelope["doc"], had_crc=bool(envelope["had_crc"]))
    except (ValueError, KeyError, TypeError) as error:
        raise CodecError("The settings file could not be read.") from error


def read_document(
    path: Path, *, runner=subprocess.run, exe=paths.codec_exe
) -> Document:
    return _decode_bytes(Path(path).read_bytes(), runner=runner, exe=exe)


def read_snapshot(
    path: Path, *, runner=subprocess.run, exe=paths.codec_exe
) -> DocumentSnapshot:
    """Pair the decoded document with the revision of those exact input bytes."""
    raw = Path(path).read_bytes()
    document = _decode_bytes(raw, runner=runner, exe=exe)
    return DocumentSnapshot(document, hashlib.sha256(raw).hexdigest())


def _validate_content_revision(expected: str) -> None:
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise CodecError(
            "A content revision must be 64 lowercase hexadecimal characters."
        )


def require_content_revision(path: Path, expected: str) -> None:
    """Refuse mismatching or unavailable content without exposing file contents."""
    _validate_content_revision(expected)
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise ContentChangedError(
            "The settings file could not be read. Reload it before saving."
        ) from error
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ContentChangedError("The settings file changed. Reload it before saving.")


def write_document(
    path: Path,
    document: Document,
    *,
    backup,
    runner=subprocess.run,
    exe=paths.codec_exe,
    publish=atomicio.write_bytes_atomic,
    expected_content_revision: str | None = None,
) -> str:
    """Re-encode *document* and publish it at *path*, backing up first.

    Order matters: encode, verify, then backup, then publish. Encoding first
    means a codec failure leaves no backup debris; publishing last through the
    atomic writer means a sharing violation from a running client leaves the
    old file intact and surfaces as PermissionError, which ops._describe
    already turns into "Close EVE and retry."

    Verify means: decode our own output and require it to read back as the
    document we sent. A codec that returns garbage with exit 0 is the one
    failure that would replace a valid file with junk, and one extra call of
    a millisecond filter is cheap insurance against it.

    A supplied revision is checked before and after backup. This is optimistic,
    not an atomic compare-and-swap: an external writer can still race the final
    check and publication. Return the verified output's revision, never a reread
    that could belong to a later external write.
    """
    if expected_content_revision is not None:
        _validate_content_revision(expected_content_revision)
    envelope = {"had_crc": document.had_crc, "doc": document.doc}
    payload = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    data = _run("encode", payload, runner=runner, exe=exe)
    if not data:
        raise CodecError(
            "The settings codec produced an empty file; nothing was written."
        )
    if data[:1] != _SIGNATURE_V1:
        raise CodecError(
            "The settings codec produced something that is not a settings "
            "file; nothing was written."
        )
    try:
        readback = json.loads(_run("decode", data, runner=runner, exe=exe))
    except ValueError as error:
        raise CodecError(
            "The re-encoded settings file could not be verified; nothing was written."
        ) from error
    if readback != envelope:
        raise CodecError(
            "The re-encoded settings file did not read back identically; "
            "nothing was written."
        )
    committed_revision = hashlib.sha256(data).hexdigest()
    if expected_content_revision is not None:
        require_content_revision(Path(path), expected_content_revision)
    backup(Path(path))
    if expected_content_revision is not None:
        require_content_revision(Path(path), expected_content_revision)
    publish(Path(path), data)
    return committed_revision
