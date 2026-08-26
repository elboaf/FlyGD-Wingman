"""Settings persistence.

Key names match the pre-2.0 file: ``privacy`` and ``category`` (not
``category_id``).
"""

import contextlib
import copy
import json
import re
import threading
from pathlib import Path

from . import bookmarks, paths
from .alerts import patterns as alert_patterns
from .preview import gestures as preview_gestures
from .preview import layout as preview_layout
from .preview import roster as preview_roster

# Sounds that ship. An id present in the UI dropdown but missing here
# normalises to silence, which is indistinguishable from a broken alert --
# so the two lists are checked against the assets folder in the sound task.
VALID_SOUNDS = {"none", "alarm", "ring", "notify"}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Per-event shape. Colours are picked so the three are distinguishable at a
# glance on a small tile: red for damage, yellow for "you cannot leave",
# cyan for a decloak.
_ALERT_EVENT_DEFAULTS = {
    # Sounds are assigned by LENGTH against each event's cooldown, then by
    # urgency. combat re-alerts every 1s, so it gets the only sound short
    # enough to finish (0.77s); a longer one would be cut off by its own
    # next alert, since PlaySound replaces whatever is still playing.
    # scram and decloak have 8s to play with. Pitch falls with severity:
    # alarm is 1342 Hz, ring 1046 Hz, notify 523 Hz.
    "combat": {"cooldown_s": 1, "color": "#ff4d4d", "sound": "alarm"},
    "warp_scramble": {"cooldown_s": 8, "color": "#ffd24d", "sound": "ring"},
    "decloak": {"cooldown_s": 8, "color": "#4dd2ff", "sound": "notify"},
}


def _alerts_defaults() -> dict:
    """Fresh nested structure every call, like _preview_defaults.

    Off by default: enabling costs a second thread and a 1s folder poll on
    top of what previews already pay.
    """
    return {
        "enabled": False,
        # The filter is what makes `combat` mean "a player is shooting
        # you". Without it a Sleeper site alerts continuously on every
        # client, and a player landing mid-site is indistinguishable from
        # the NPCs already firing.
        "pve_filter": True,
        # An alert that expires while you are in a browser has told you
        # nothing, which is the whole case for the feature.
        "persist_until_selected": True,
        # Carried from the start on TriffView's evidence: it needed exactly
        # this migration, and rewrote only values that still equalled the
        # previous default so a customised setting was never overwritten.
        # No migration code exists yet and none should: at version 1 there
        # is nothing to migrate from. The field is here so a future v2 can
        # compare against a retained table of v1 defaults -- building that
        # harness now would be speculative machinery with no caller.
        "defaults_version": 1,
        "events": {
            name: {
                "enabled": True,
                "duration_ms": 1200,
                "pulses": 3,
                **_ALERT_EVENT_DEFAULTS[name],
            }
            for name in alert_patterns.EVENTS
        },
    }


# The preview opacity default from previews shipping through v3.3.0, when
# the key was validated but read by nothing.
_PREVIEW_V1_OPACITY = 235
_PREVIEW_DEFAULT_OPACITY = 255
_PREVIEW_DEFAULTS_VERSION = 2


def _preview_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global.

    Off by default, like eve_bookmarks: enabling it starts a thread, a
    700ms sweep, and a foreground hook. A user who never previews EVE
    clients should pay none of that.
    """
    return {
        "enabled": False,
        "width": 320,
        "height": 210,
        # Fully opaque -- it is what every preview has in practice always
        # rendered at, from PreviewWindow's own 255 default: opacity was
        # validated and clamped from the day it was added but read by
        # nothing. Task 4 wires this key through to the DWM thumbnail,
        # which turns stored config into something users actually see.
        #
        # Changing this default is NOT what protects existing installs --
        # a default only applies to an absent key, and _save_locked
        # projects the complete document from DEFAULTS, so every install
        # that has ever saved settings already has the old 235 written in
        # its file. The one-shot migration in validated_preview is what
        # delivers the guarantee. Translucency stays available, opt-in
        # through the Previews slider.
        "opacity": _PREVIEW_DEFAULT_OPACITY,
        # Bumped to 2 when opacity became a value users can see. See
        # validated_preview for the migration it gates.
        "defaults_version": _PREVIEW_DEFAULTS_VERSION,
        "layouts": {},
        # Flat cycle chords, not a group table. When named cycle groups
        # land these become the default group's, so the schema grows
        # without migrating anyone -- the same shape the parent design
        # used to defer profiles.
        "hotkeys": {"characters": {}, "cycle_next": "", "cycle_prev": ""},
        "seen": [],
        # Where a preview OPENS: on, at the rect the user last dragged
        # it to; off, at default_stack placement. Positions are
        # recorded either way, so switching back on restores what they
        # last had. On by default -- it is what shipped, and the
        # alternative silently discards existing layouts.
        "restore_preview_positions": True,
        "alerts": _alerts_defaults(),
        # On by default -- it is what shipped, and turning it off would
        # silently restyle every existing install's previews.
        "show_labels": True,
        # Off by default: it changes what happens to a real game window
        # (minimizing it), which must be asked for rather than assumed.
        "minimize_inactive_clients": False,
        # Character names exempt from minimize_inactive_clients. A plain
        # roster list like `seen`, not a per-preview flag.
        "never_minimize": [],
        # Character names whose preview position is locked against drag.
        # Deliberately a top-level list, NOT a flag inside a layouts entry:
        # layout.deserialize drops any entry missing a full rect
        # (layout.py:44-52), so a lock recorded against a character who has
        # never dragged their preview -- and so has no layouts entry --
        # would be silently discarded on the very next save.
        "locked": [],
        # On by default -- it is what shipped, and turning it off would
        # silently change how every existing install's previews drag.
        # A new key whose default matches current behaviour needs no
        # defaults_version bump: the migration exists for defaults that
        # CHANGE, and this one has no previous value to protect.
        "snap": True,
    }


def _eve_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global."""
    # Off by default. Every bind is now scoped to an enabled EVE window,
    # but enabling this still starts a process that installs a system-wide
    # keyboard hook, which an upgrading user has to ask for rather than be
    # given.
    return {"enabled": False, "keybinds": dict(bookmarks.DEFAULT_BINDS), "windows": {}}


def _eve_settings_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global."""
    # Three remembered paths and the prune depth. Everything else is derived
    # from disk on each state build, so there is nothing to migrate and
    # nothing that can drift out of step with reality.
    return {"root": None, "server": None, "profile": None, "auto_keep": 10}


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
    # Whether the EVE destinations and sections are offered at all. TRUE
    # for everyone, and nothing asks: in practice the people who install
    # this play EVE, so a first-run question about it was noise on the one
    # screen that has to stay short. It also keeps an upgrading user's file
    # -- which predates this key -- from silently losing four things they
    # already use. Someone who wants the plain uploader turns it off in
    # Settings > General.
    #
    # This governs VISIBILITY ONLY. It never starts or stops anything --
    # eve_bookmarks.enabled and preview.enabled remain the sole runtime
    # switches, read at launch by start_engine_if_enabled and
    # start_previews_if_enabled. See Api.set_show_eve_tools for the guard
    # that keeps this from hiding a running feature's off switch.
    "show_eve_tools": True,
    # Whether the user dismissed the first-run folder screen without
    # choosing a folder. A recording folder is the UPLOADER half's
    # configuration, and PRODUCT.md makes the two halves independent -- so
    # someone who installed Wingman for previews and bookmark keybinds has
    # to be able to get past it. Without this key that choice cannot
    # survive a restart: __main__ shows the screen whenever no folder
    # RESOLVES, so the skip would be re-asked on every launch.
    #
    # It records a DISMISSAL, not a folder state, which is why it is not
    # derived from recording_dir. The two cases __main__ cannot otherwise
    # tell apart are "never configured, and said so" and "configured once,
    # folder has since disappeared" -- the second still deserves the
    # screen. Api.set_folder clears it, so choosing a folder later returns
    # the install to the ordinary path.
    "first_run_skipped": False,
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
    # Same reasoning as eve_bookmarks and preview above: built by
    # _eve_settings_defaults() so callers never share one nested dict.
    "eve_settings": _eve_settings_defaults(),
}

VALID_PRIVACY = {"private", "unlisted", "public"}
VALID_NOTIFY = {"toast", "popup"}


def _fresh_defaults() -> dict:
    """dict(DEFAULTS) is shallow, so the nested sections are rebuilt."""
    data = dict(DEFAULTS)
    data["eve_bookmarks"] = _eve_defaults()
    data["preview"] = _preview_defaults()
    data["eve_settings"] = _eve_settings_defaults()
    return data


def validated_preview(raw) -> dict:
    """Same posture as validated_eve: a malformed section falls back
    whole, a malformed layout entry drops alone."""
    section = _preview_defaults()
    if not isinstance(raw, dict):
        return section
    if isinstance(raw.get("enabled"), bool):
        section["enabled"] = raw["enabled"]
    if isinstance(raw.get("restore_preview_positions"), bool):
        section["restore_preview_positions"] = raw["restore_preview_positions"]
    if isinstance(raw.get("snap"), bool):
        section["snap"] = raw["snap"]
    for key, floor in (("width", 120), ("height", 90)):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            section[key] = max(floor, value)
    opacity = raw.get("opacity")
    if isinstance(opacity, int) and not isinstance(opacity, bool):
        # Clamped, not rejected: a fully transparent preview is
        # indistinguishable from a broken one.
        section["opacity"] = max(20, min(255, opacity))
    # One-shot migration to the v2 opacity default, on TriffView's pattern
    # (see _alerts_defaults): rewrite only a value that still equals the
    # previous default, so a customised setting is never overwritten.
    #
    # It exists because the default change alone protects nobody.
    # _save_locked projects the complete document from DEFAULTS and
    # _normalize runs validated_preview on every write, so 235 is already
    # materialised in the file of every install that has ever saved
    # settings; a default only applies to an ABSENT key. Without this,
    # existing installs would render at 235 while new ones rendered at
    # 255.
    #
    # Safe precisely because preview.opacity had no user interface before
    # this branch: a stored 235 cannot be a deliberate choice, only the
    # old default. A missing marker identifies such a pre-branch file --
    # the key did not exist to be written.
    stored_version = raw.get("defaults_version")
    if not isinstance(stored_version, int) or isinstance(stored_version, bool):
        stored_version = 1
    if (
        stored_version < _PREVIEW_DEFAULTS_VERSION
        and section["opacity"] == _PREVIEW_V1_OPACITY
    ):
        section["opacity"] = _PREVIEW_DEFAULT_OPACITY
    # max(), so a file written by a future version keeps its own marker
    # and is not walked backwards into re-running this migration.
    section["defaults_version"] = max(stored_version, _PREVIEW_DEFAULTS_VERSION)
    # Round-tripped through the layout model so a corrupt entry is dropped
    # at load rather than at draw time. Kept as a local so the legacy-lock
    # migration below can read each entry's `locked` flag without
    # re-parsing the raw dict.
    parsed_layouts = preview_layout.deserialize(raw.get("layouts"))
    section["layouts"] = preview_layout.serialize(parsed_layouts)

    raw_hotkeys = raw.get("hotkeys")
    if isinstance(raw_hotkeys, dict):
        characters = raw_hotkeys.get("characters")
        if isinstance(characters, dict):
            for name, text in characters.items():
                if not isinstance(name, str) or name.startswith("hwnd:"):
                    continue
                parsed = preview_gestures.parse(text)
                if parsed is not None:
                    # Canonical form, so "Alt+Ctrl+F2" and "Ctrl+Alt+F2"
                    # cannot read as two different bindings to the clash
                    # check.
                    section["hotkeys"]["characters"][name] = preview_gestures.display(
                        parsed
                    )
        for key in ("cycle_next", "cycle_prev"):
            parsed = preview_gestures.parse(raw_hotkeys.get(key))
            if parsed is not None:
                section["hotkeys"][key] = preview_gestures.display(parsed)

    section["seen"] = preview_roster.deserialize(raw.get("seen"))
    # Without this line the whole section is rebuilt from defaults on every
    # _normalize -- which every update() runs -- so any writer touching any
    # preview key silently reverts the user's alert configuration.
    section["alerts"] = validated_alerts(raw.get("alerts"))
    if isinstance(raw.get("show_labels"), bool):
        section["show_labels"] = raw["show_labels"]
    if isinstance(raw.get("minimize_inactive_clients"), bool):
        section["minimize_inactive_clients"] = raw["minimize_inactive_clients"]
    # Both lists have exactly the roster's constraints, including the
    # hwnd: rejection: a client at character-select has no stable name to
    # exempt from minimizing or lock in place.
    section["never_minimize"] = preview_roster.deserialize(raw.get("never_minimize"))
    raw_locked = raw.get("locked")
    combined_locked = list(raw_locked) if isinstance(raw_locked, list) else []
    if stored_version < _PREVIEW_DEFAULTS_VERSION:
        # One-shot carry-over of the pre-branch lock storage, on the same
        # gate as the opacity migration above. Locking a preview used to
        # set `locked` on its entry inside preview.layouts; this branch
        # moved the source of truth to this top-level roster instead,
        # because layout.deserialize (preview/layout.py) drops any entry
        # missing a full rect, so a lock recorded against a character who
        # had never dragged their preview had nowhere to live in the new
        # scheme. Nothing reads Entry.locked any more -- without this,
        # a legacy `preview.layouts.<char>.locked = true` would open
        # unlocked, and the first drag would silently overwrite it to
        # false. Appended after the explicit list so an already-populated
        # preview.locked is never clobbered or duplicated; deserialize
        # below dedups and drops it if the name is not eligible (e.g. a
        # "hwnd:" client with no stable identity).
        combined_locked += [
            name for name, entry in parsed_layouts.items() if entry.locked
        ]
    section["locked"] = preview_roster.deserialize(combined_locked)
    return section


def _validated_alert_event(raw, defaults: dict) -> dict:
    event = dict(defaults)
    if not isinstance(raw, dict):
        return event
    if isinstance(raw.get("enabled"), bool):
        event["enabled"] = raw["enabled"]
    for key, low, high in (
        ("cooldown_s", 0, 120),
        ("duration_ms", 250, 15000),
        ("pulses", 1, 16),
    ):
        value = raw.get(key)
        # `not isinstance(value, bool)` because bool is an int in Python,
        # and True would silently become a one-second cooldown.
        if isinstance(value, int) and not isinstance(value, bool):
            event[key] = max(low, min(high, value))
    colour = raw.get("color")
    if isinstance(colour, str) and _HEX_RE.match(colour):
        # Rejected rather than coerced: chrome.render hands this to Pillow,
        # which raises on a malformed value -- on the preview thread, inside
        # the paint path.
        event["color"] = colour
    sound = raw.get("sound")
    if isinstance(sound, str):
        event["sound"] = sound if sound in VALID_SOUNDS else "none"
    return event


def validated_alerts(raw) -> dict:
    """Same two-tier posture as validated_preview: a malformed section
    falls back whole, a malformed event falls back alone."""
    section = _alerts_defaults()
    if not isinstance(raw, dict):
        return section
    for key in ("enabled", "pve_filter", "persist_until_selected"):
        if isinstance(raw.get(key), bool):
            section[key] = raw[key]
    version = raw.get("defaults_version")
    if isinstance(version, int) and not isinstance(version, bool):
        section["defaults_version"] = max(1, version)
    raw_events = raw.get("events")
    if isinstance(raw_events, dict):
        # Iterating EVENTS rather than raw_events is what drops an unknown
        # event: a hand-edited file cannot introduce one the renderer has
        # no colour or severity rank for.
        for name in alert_patterns.EVENTS:
            section["events"][name] = _validated_alert_event(
                raw_events.get(name), section["events"][name]
            )
    return section


def validated_eve_settings(raw) -> dict:
    """Same posture as validated_preview: a malformed section falls back
    whole, and a malformed single value falls back alone."""
    section = _eve_settings_defaults()
    if not isinstance(raw, dict):
        return section
    for key in ("root", "server", "profile"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            section[key] = value
    keep = raw.get("auto_keep")
    # `not isinstance(keep, bool)` because bool is an int in Python, and
    # True would silently become a keep depth of 1.
    if isinstance(keep, int) and not isinstance(keep, bool):
        # Clamped, not rejected: a depth of zero would delete the backup
        # taken moments earlier, which is the one nobody can afford to lose.
        section["auto_keep"] = max(1, min(100, keep))
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

    # home_zero, preface_return and return_preface used to be read here.
    # Naming is fixed in the engine now, with no INI setting behind it at
    # all. Dropping the reads is the whole of the removal: `section` starts
    # from _eve_defaults() and only the keys handled explicitly are copied
    # across, so the leftovers in an older settings.json go nowhere and are
    # gone from the file after the next save.

    windows = raw.get("windows")
    if isinstance(windows, dict):
        section["windows"] = {
            k: bool(v) for k, v in windows.items() if isinstance(k, str)
        }
    return section


def _normalize(data: dict) -> dict:
    """Apply load()'s validation/coercion rules to `data` in place.

    Factored out of load() so update() can run the same rules on the live
    in-memory dict after a caller's mutation, under the same lock that
    protects the save -- see update()'s docstring for why that matters.
    Idempotent: load() already re-validated every field on every write
    (the old rebind-from-disk this replaces), so running it again on
    already-valid data is a no-op.

    Tolerant of a partial `data`, the way _save_locked's DEFAULTS-projected
    payload already is: a caller passing a dict missing one of these scalar
    keys (tests/fakes.py builds exactly such a dict) gets that key filled
    from DEFAULTS instead of a KeyError. setdefault, not indexing, so a key
    that IS present is left exactly as validated below -- only an absent
    key is touched here.
    """
    for key in (
        "privacy",
        "notify_mode",
        "category",
        "recording_dir",
        "discord_webhook",
        "gamelogs_dir",
        "channel_id",
        "channel_title",
        "show_eve_tools",
        "first_run_skipped",
    ):
        data.setdefault(key, DEFAULTS[key])
    # Coerced rather than defaulted: a hand-edited file with a string here
    # would otherwise make every truthy string mean "shown" and the empty
    # string mean "hidden", which is not a distinction anyone intended.
    data["show_eve_tools"] = bool(data["show_eve_tools"])
    # Coerced for the same reason show_eve_tools is: a hand-edited file
    # with a string here would leave a non-bool in a value the rest of the
    # app tests with `is True`. The truthy/empty split this settles on is
    # the same one show_eve_tools accepts.
    data["first_run_skipped"] = bool(data["first_run_skipped"])
    if data["privacy"] not in VALID_PRIVACY:
        data["privacy"] = DEFAULTS["privacy"]
    if data["notify_mode"] not in VALID_NOTIFY:
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
    data["eve_bookmarks"] = validated_eve(data.get("eve_bookmarks"))
    data["preview"] = validated_preview(data.get("preview"))
    data["eve_settings"] = validated_eve_settings(data.get("eve_settings"))
    return data


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
    return _normalize(data)


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


@contextlib.contextmanager
def update(data: dict, path: Path | None = None):
    """Serialise a whole read-modify-write, not just the write.

    _SAVE_LOCK alone is not enough. save() projects the COMPLETE document
    from DEFAULTS, so a writer that reads, mutates and saves can be
    interleaved by another doing the same and have its keys reverted --
    silently, with no error and nothing in the log. Holding the lock across
    the caller's mutation closes that window.

    On any exception the live dict is restored to its prior contents and
    nothing is written, so a failed save cannot leave in-memory state and
    disk disagreeing. ui/api.py's save path depends on that property.

    Deep, not shallow: preview state lives in a nested section, and a
    shallow snapshot would leave a half-applied mutation behind.

    Normalises `data` in place, under this same lock, before saving --
    load()'s privacy/notify_mode/category/eve_bookmarks/preview coercions,
    applied to the live dict instead of a fresh object loaded back from
    disk. ui/api.py used to rebind `self._state.settings` to a brand-new
    `settings_mod.load()` result after every save to pick up those
    coercions; that rebind ran OUTSIDE any lock and swapped the dict
    object out from under LayoutStore, which keeps its own reference to
    the settings dict and updates it via this same update() call. A store
    write landing on the object between the save above and the rebind
    below was silently discarded once the rebind replaced it -- see
    rebind-race-repro.py. Normalizing in place instead means the object
    identity `self._state.settings` holds never changes, so a concurrent
    holder of that reference is never left writing to an orphaned dict.

    That stability is scoped to the DOCUMENT, not its nested sections:
    _normalize reassigns data["eve_bookmarks"], data["preview"] and
    data["eve_settings"] wholesale on every call (see validated_eve and
    friends above), so a reference held to one of those inner dicts across
    an update() call goes stale even though `data` itself does not. Hold
    `data`, not `data["preview"]`, across a call.

    DO NOT call save() or update() from inside an update() block. The lock
    is not reentrant and the process will deadlock.
    """
    with _SAVE_LOCK:
        before = copy.deepcopy(data)
        try:
            yield data
            _normalize(data)
            _save_locked(data, path)
        except BaseException:
            data.clear()
            data.update(before)
            raise


def update_section(
    data: dict, name: str, values: dict, path: Path | None = None
) -> dict:
    """Merge *values* into one section of the live settings document.

    A section-shaped wrapper over update(), not a second implementation of
    it: the hazard and the locking rule are documented there. This exists
    because the EVE Settings writers touch exactly one section and would
    otherwise each repeat the same read-merge-assign callback.

    Takes the LIVE settings dict rather than loading a fresh document from
    disk. Loading a fresh one was the earlier shape, and it forced every
    caller to rebind `AppState.settings` afterwards to see its own write --
    a rebind that ran outside this lock and swapped the dict object out
    from under LayoutStore, which holds its own reference and writes
    through this same lock. A store write landing between the save and the
    rebind was silently discarded. Mutating the live dict keeps its
    identity stable, so no caller needs to rebind and nothing is orphaned.

    The section is rebuilt rather than mutated in place for the same reason
    update() normalises before saving: a half-merged section must never be
    what another thread observes.
    """
    with update(data, path) as live:
        section = dict(live.get(name) or {})
        section.update(values)
        live[name] = section
    return data
