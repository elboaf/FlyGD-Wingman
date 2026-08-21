"""Settings persistence.

Key names match the pre-2.0 file: ``privacy`` and ``category`` (not
``category_id``).
"""
import json
from pathlib import Path

from . import paths

DEFAULTS = {
    # unlisted, not private: a private upload nobody can watch defeats the
    # purpose of sharing a fight. This reverses an earlier decision that
    # chose private as the safer default for automatic uploads.
    "privacy": "unlisted",
    "category": "20",
    "notify_mode": "toast",
    # Not a user-facing preference, but it must live here: save() projects
    # onto DEFAULTS keys, so anything undeclared is dropped on every write.
    "recording_dir": None,
    "discord_webhook": "",
    "gamelogs_dir": None,
    # The YouTube channel the last successful upload actually landed on,
    # learned from the videos.insert response rather than looked up: the
    # app holds only the youtube.upload scope, and channels.list needs a
    # second one. Displayed so the user can see where uploads go, and
    # compared so a changed destination can be called out.
    "channel_id": "",
    "channel_title": "",
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
    if not isinstance(data["discord_webhook"], str):
        data["discord_webhook"] = ""
    if data["gamelogs_dir"] is not None and not isinstance(data["gamelogs_dir"], str):
        data["gamelogs_dir"] = None
    # Both reach a Label, so a non-string from a hand-edited file would be
    # rendered as its repr rather than failing loudly. Coerced to "" for the
    # same reason discord_webhook is.
    for key in ("channel_id", "channel_title"):
        if not isinstance(data[key], str):
            data[key] = ""
    return data


def save(data: dict, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
