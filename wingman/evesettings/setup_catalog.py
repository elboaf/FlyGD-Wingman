"""Stateless, read-only distribution metadata for bundled full UI setups.

Browsing never parses artifacts or authorizes a recipient. Selection hashes the
exact bundled bytes before using the existing public full-setup parser; later
review/create remains responsible for recipient applicability.
"""

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from .. import paths
from . import setup_model, setup_sharing

_MAX_MANIFEST_BYTES = 128 * 1024
_ENTRY_FIELDS = {
    "id",
    "revision",
    "title",
    "description",
    "sha256",
    "overview_sources",
    "layout_author",
    "display",
    "verification",
}
_SOURCE_FIELDS = {"name", "author", "reference", "version", "license", "license_file"}


class SetupCatalogError(ValueError):
    """Recoverable catalog failure, with safe context for the local picker."""


def _linked(info: os.stat_result) -> bool:
    # Windows junctions need the reparse bit, not just the POSIX symlink mode.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _directory() -> Path:
    directory = paths.setup_presets_dir()
    try:
        info = directory.lstat()
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise SetupCatalogError(
                "Bundled setup directory is linked or not a directory."
            )
    except OSError as error:
        raise SetupCatalogError(
            "Bundled setup directory is unavailable. Check the Wingman installation."
        ) from error
    return directory


def _regular(info: os.stat_result, name: str) -> None:
    # Package installers may hardlink read-only resources; the selected artifact
    # is still bound to its exact bytes by the catalog hash.
    if _linked(info) or not stat.S_ISREG(info.st_mode):
        raise SetupCatalogError(
            f"Bundled {name} is not a regular file or is a symlink/reparse alias."
        )


def _read_file(directory: Path, name: str, maximum: int | None) -> bytes:
    # Names reach here only from validated metadata or our derived filename.
    # A license is opened for readability without consuming its content: rights
    # and permission text remain an admission gate, not a parser inference.
    path = directory / name
    try:
        before = path.lstat()
        _regular(before, name)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            _regular(opened, name)
            if not os.path.samestat(before, opened):
                raise SetupCatalogError(f"Bundled {name} changed while opening. Retry.")
            raw = stream.read(maximum + 1) if maximum is not None else b""
        if maximum is not None and len(raw) > maximum:
            raise SetupCatalogError(f"Bundled {name} exceeds {maximum} bytes.")
    except OSError as error:
        raise SetupCatalogError(
            f"Cannot read bundled {name}. Check the Wingman installation."
        ) from error
    return raw


def _decode(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SetupCatalogError(f"{label} must be valid UTF-8.") from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SetupCatalogError("Duplicate JSON object field in catalog.json.")
        result[key] = value
    return result


def _constant(value):
    raise SetupCatalogError("catalog.json contains an invalid JSON number.")


def _fields(value, expected: set[str], label: str) -> None:
    if type(value) is not dict:
        raise SetupCatalogError(f"{label} must be an object.")
    if value.keys() != expected:
        raise SetupCatalogError(f"{label} has missing or unknown fields.")


def _text(value, maximum: int, label: str) -> None:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise SetupCatalogError(f"{label} must be 1 to {maximum} text code points.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SetupCatalogError(f"{label} must be valid UTF-8.") from error
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise SetupCatalogError(f"{label} must not contain control characters.")


def _integer(value, maximum: int, label: str) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise SetupCatalogError(f"{label} must be an integer from 1 to {maximum}.")


def _identity(preset_id, revision, sha256) -> None:
    _text(preset_id, 64, "id")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", preset_id) is None:
        raise SetupCatalogError("id must be a lowercase ASCII slug.")
    _integer(revision, 2147483647, "revision")
    _text(sha256, 64, "sha256")
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise SetupCatalogError("sha256 must be exactly 64 lowercase hex characters.")


def _entry(entry) -> None:
    _fields(entry, _ENTRY_FIELDS, "Catalog entry")
    _identity(entry["id"], entry["revision"], entry["sha256"])
    _text(entry["title"], 128, "title")
    _text(entry["description"], 2048, "description")
    _text(entry["layout_author"], 128, "layout_author")
    _text(entry["verification"], 2048, "verification")
    sources = entry["overview_sources"]
    if type(sources) is not list or not 1 <= len(sources) <= 8:
        raise SetupCatalogError("overview_sources must contain 1 to 8 records.")
    for source in sources:
        _fields(source, _SOURCE_FIELDS, "overview_sources record")
        for field in ("name", "author", "reference", "version", "license"):
            _text(source[field], 512, f"overview_sources.{field}")
        name = source["license_file"]
        _text(name, 128, "overview_sources.license_file")
        if re.fullmatch(r"[a-zA-Z0-9_-]+\.txt", name) is None:
            raise SetupCatalogError("license_file must be a plain ASCII .txt basename.")
    display = entry["display"]
    _fields(display, {"width", "height", "ui_scale_percent"}, "display")
    _integer(display["width"], 32768, "display.width")
    _integer(display["height"], 32768, "display.height")
    _integer(display["ui_scale_percent"], 1000, "display.ui_scale_percent")


def _entries(directory: Path) -> list[dict]:
    raw = _read_file(directory, "catalog.json", _MAX_MANIFEST_BYTES)
    text = _decode(raw, "catalog.json")
    try:
        manifest = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_constant
        )
    except SetupCatalogError:
        raise
    except (ValueError, RecursionError) as error:
        raise SetupCatalogError(
            "catalog.json is invalid or too deeply nested JSON."
        ) from error
    _fields(manifest, {"format", "version", "entries"}, "Catalog manifest")
    if manifest["format"] != "wingman-setup-catalog":
        raise SetupCatalogError(
            "Unsupported catalog format; expected wingman-setup-catalog."
        )
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise SetupCatalogError("Unsupported catalog version; expected integer 1.")
    entries = manifest["entries"]
    if type(entries) is not list or len(entries) > 64:
        raise SetupCatalogError("Catalog entries must be a list of at most 64 records.")
    seen = set()
    for entry in entries:
        _entry(entry)
        if entry["id"] in seen:
            raise SetupCatalogError(f"Duplicate catalog id: {entry['id']}.")
        seen.add(entry["id"])
    # Validate the entire shallow manifest before using any of its filenames.
    for entry in entries:
        for source in entry["overview_sources"]:
            _read_file(directory, source["license_file"], None)
    return entries


def list_entries() -> list[dict]:
    """Read fresh bounded metadata, without loading any preset artifact."""
    return _entries(_directory())


def read_entry(preset_id: str, revision: int, sha256: str) -> dict:
    """Return exact artifact text and a derived summary for a current identity."""
    _identity(preset_id, revision, sha256)
    directory = _directory()
    entry = next(
        (
            entry
            for entry in _entries(directory)
            if (entry["id"], entry["revision"], entry["sha256"])
            == (preset_id, revision, sha256)
        ),
        None,
    )
    if entry is None:
        raise SetupCatalogError("Preset no longer matches the catalog. Browse again.")
    name = f"{entry['id']}-r{entry['revision']}.json"
    raw = _read_file(directory, name, setup_model.MAX_BYTES)
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise SetupCatalogError(
            f"Bundled {name} has a SHA-256 hash mismatch. Check the installation."
        )
    text = _decode(raw, name)
    try:
        parsed = setup_sharing.parse_text(text)
    except setup_model.SetupError as error:
        raise SetupCatalogError(
            f"Bundled {name} is not a valid full setup: {error}"
        ) from error
    if parsed.source_kind != "wingman" or parsed.layout is None:
        raise SetupCatalogError(
            f"Bundled {name} must be a full Wingman UI setup with layout."
        )
    return {"entry": entry, "text": text, "summary": setup_model.summarize(parsed)}
