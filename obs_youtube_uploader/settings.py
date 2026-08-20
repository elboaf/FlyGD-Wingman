"""Settings persistence.

Key names match the pre-2.0 file: ``privacy`` and ``category`` (not
``category_id``). The privacy default is ``private``, resolving an
inconsistency in the old code where loading defaulted to ``unlisted`` but
uploading defaulted to ``private``.
"""
import json
from pathlib import Path

from . import paths

DEFAULTS = {
    "privacy": "private",
    "category": "20",
    "notify_mode": "toast",
    # Not a user-facing setting, but it must live here: save() projects onto
    # DEFAULTS keys, so anything undeclared is dropped on every write.
    "recording_dir": None,
}

_VALID_PRIVACY = {"private", "unlisted", "public"}
_VALID_NOTIFY = {"toast", "popup"}


def load(path: Path | None = None) -> dict:
    path = path or paths.settings_file()
    data = dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if not isinstance(raw, dict):
        return data
    for key in DEFAULTS:
        if key in raw:
            data[key] = raw[key]
    if data["privacy"] not in _VALID_PRIVACY:
        data["privacy"] = DEFAULTS["privacy"]
    if data["notify_mode"] not in _VALID_NOTIFY:
        data["notify_mode"] = DEFAULTS["notify_mode"]
    if not isinstance(data["category"], str) or not data["category"].isdigit():
        data["category"] = DEFAULTS["category"]
    if data["recording_dir"] is not None and not isinstance(data["recording_dir"], str):
        data["recording_dir"] = None
    return data


def save(data: dict, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
