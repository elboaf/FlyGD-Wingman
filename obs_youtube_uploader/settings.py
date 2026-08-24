"""Settings persistence.

Key names match the pre-2.0 file: ``privacy`` and ``category`` (not
``category_id``).
"""
import json
import threading
from pathlib import Path

from . import bookmarks, paths
from .preview import layout as preview_layout


def _preview_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global.

    Off by default, like eve_bookmarks: enabling it starts a thread, a
    700ms sweep, and a foreground hook. A user who never previews EVE
    clients should pay none of that.
    """
    return {"enabled": False, "width": 320, "height": 210,
            "opacity": 235, "layouts": {}}


def _eve_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global."""
    # Off by default: Copy, Paste and Set Root register with no window
    # restriction (111unified.ahk:763-771), so enabling this really does
    # install hotkeys that fire outside EVE. An upgrading user has to ask
    # for that rather than be given it.
    return {"enabled": False,
            "keybinds": dict(bookmarks.DEFAULT_BINDS),
            "windows": {},
            # The standalone script's compiled-in default is the opposite
            # (HomeZeroIs0 := 1, 111unified.ahk:32). Wingman starts a fresh
            # install at .1 by maintainer decision; an imported INI carries
            # its own value across, so nobody upgrading is renumbered.
            "home_zero": False,
            "preface_return": True,
            "return_preface": "!"}


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
    # Nested, unlike every other key. save() projects onto DEFAULTS keys, so
    # this whole section travels as one value; load() rebuilds the inner
    # dicts rather than copying them, because dict(DEFAULTS) below is
    # shallow and would otherwise hand callers the module globals.
    #
    # Built by _eve_defaults() rather than restated here: load() returns
    # that function's output, and tests compare load() against DEFAULTS, so
    # two literals would have to be kept in step by hand.
    "eve_bookmarks": _eve_defaults(),
    # Same reasoning as eve_bookmarks above: built by _preview_defaults()
    # so callers never share one nested dict.
    "preview": _preview_defaults(),
}

_VALID_PRIVACY = {"private", "unlisted", "public"}
_VALID_NOTIFY = {"toast", "popup"}


def _fresh_defaults() -> dict:
    """dict(DEFAULTS) is shallow, so the nested section is rebuilt."""
    data = dict(DEFAULTS)
    data["eve_bookmarks"] = _eve_defaults()
    data["preview"] = _preview_defaults()
    return data


def validated_preview(raw) -> dict:
    """Same posture as validated_eve: a malformed section falls back
    whole, a malformed layout entry drops alone."""
    section = _preview_defaults()
    if not isinstance(raw, dict):
        return section
    if isinstance(raw.get("enabled"), bool):
        section["enabled"] = raw["enabled"]
    for key, floor in (("width", 120), ("height", 90)):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            section[key] = max(floor, value)
    opacity = raw.get("opacity")
    if isinstance(opacity, int) and not isinstance(opacity, bool):
        # Clamped, not rejected: a fully transparent preview is
        # indistinguishable from a broken one.
        section["opacity"] = max(20, min(255, opacity))
    # Round-tripped through the layout model so a corrupt entry is dropped
    # at load rather than at draw time.
    section["layouts"] = preview_layout.serialize(
        preview_layout.deserialize(raw.get("layouts")))
    return section


def validated_eve(raw) -> dict:
    section = _eve_defaults()
    if not isinstance(raw, dict):
        return section

    # `is True` rather than truthiness: a stray 1 or "yes" from a
    # hand-edited file must not start a keyboard hook.
    section["enabled"] = raw.get("enabled") is True

    binds = raw.get("keybinds")
    if isinstance(binds, dict):
        for bid in bookmarks.BIND_IDS:
            value = binds.get(bid)
            if isinstance(value, str):
                section["keybinds"][bid] = value.strip()
    # Ids not in BIND_IDS are dropped by construction: the loop is over the
    # known ids, so a key from a hand-edited file cannot reach the INI.

    # isinstance rather than `is True`: these two have different defaults,
    # so absence has to leave the default standing rather than resolve to
    # False. Unlike `enabled` there is no hook to start, so a garbage value
    # falling back to the default is the whole of the risk.
    for flag in ("home_zero", "preface_return"):
        if isinstance(raw.get(flag), bool):
            section[flag] = raw[flag]

    preface = raw.get("return_preface")
    if isinstance(preface, str):
        # Sanitised and capped here rather than only at generate_ini: this
        # is the boundary a hand-edited settings file crosses.
        section["return_preface"] = \
            bookmarks.sanitise(preface)[:bookmarks.PREFACE_MAX]

    windows = raw.get("windows")
    if isinstance(windows, dict):
        section["windows"] = {k: bool(v) for k, v in windows.items()
                              if isinstance(k, str)}
    return section


def load(path: Path | None = None) -> dict:
    path = path or paths.settings_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _fresh_defaults()
    if not isinstance(raw, dict):
        return _fresh_defaults()
    data = dict(DEFAULTS)
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
    data["eve_bookmarks"] = validated_eve(raw.get("eve_bookmarks"))
    data["preview"] = validated_preview(raw.get("preview"))
    return data


# save() projects the COMPLETE document from DEFAULTS, so two writers
# interleaving lose one side's keys entirely -- not a corrupt file, a
# silently reverted setting. Two writers already exist without previews:
# ui/api.py persists the channel from an upload worker thread, on purpose
# (see its docstring). The preview layout store makes three.
_SAVE_LOCK = threading.Lock()


def save(data: dict, path: Path | None = None) -> None:
    with _SAVE_LOCK:
        _save_locked(data, path)


def _save_locked(data: dict, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
