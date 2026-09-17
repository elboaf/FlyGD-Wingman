"""Pure settings export/import semantics; no dialog, bridge or UI imports.

The export is the whole live document projected onto ``settings.DEFAULTS``
-- the same projection every save performs -- minus the keys in
``EXCLUDED_KEYS``. Import never replaces wholesale: absent keys keep their
current values, so a future version that adds a key (or a hand-edited file
that omits one) cannot blank a recipient's configuration. Validation is
delegated to the settings module's own ``validated_*`` functions, which run
inside every ``settings.update()``; nothing here re-implements a validator,
because a second table is exactly how the DEFAULTS keys drifted once before.
"""

import copy
import json

from .. import settings

FORMAT = "wingman-settings"
VERSION = 1
TYPE = "settings"

# A settings file is text and nested dicts, not the YAML monster the UI
# setup format parses, but the preview rosters and layout stores scale with
# fleet size. Generous; parse_text still checks before decoding.
MAX_BYTES = 4 * 1024 * 1024

# discord_webhook embeds its token in the URL -- the only secret that lives
# in settings.json. channel_id/channel_title are not configuration at all:
# they are learned from the last upload's videos.insert response and are a
# property of the connected Google account, so exporting them would only
# make the recipient's Settings card describe a channel they are not signed
# into. The webhook name is likewise bound to the local credential. These
# keys are dropped on export and again on import, so a hand-edited entry in
# a shared file cannot rename the recipient's webhook or account.
EXCLUDED_KEYS = frozenset(
    {"discord_webhook", "discord_webhook_name", "channel_id", "channel_title"}
)


class SettingsShareError(ValueError):
    """A stable boundary code plus a human-readable refusal, on the
    setup_model.SetupError pattern."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def export_document(config: dict) -> dict:
    """Fresh envelope over the live document; never the caller's dicts."""
    payload = {
        key: copy.deepcopy(config.get(key, settings.DEFAULTS[key]))
        for key in settings.DEFAULTS
        if key not in EXCLUDED_KEYS
    }
    return {
        "format": FORMAT,
        "version": VERSION,
        "type": TYPE,
        "settings": payload,
    }


def export_text(config: dict) -> str:
    return json.dumps(export_document(config), indent=2)


def parse_text(text: str) -> dict:
    """Decode one envelope and return the importable settings dict.

    Unknown top-level keys and excluded keys are dropped here rather than
    left for _normalize: the returned dict is what review() summarises, and
    the summary must never promise a change the apply will not make.
    """
    if not isinstance(text, str):
        raise SettingsShareError(
            "invalid_text", "A settings export must be UTF-8 text."
        )
    budget = f"A settings export exceeds the {MAX_BYTES} UTF-8 byte limit."
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SettingsShareError(
            "invalid_text", "A settings export must be valid UTF-8 text."
        ) from error
    if len(encoded) > MAX_BYTES:
        raise SettingsShareError("byte_limit", budget)
    try:
        document = json.loads(text)
    except ValueError as error:
        raise SettingsShareError(
            "invalid_json", "That file is not valid JSON."
        ) from error
    if not isinstance(document, dict):
        raise SettingsShareError("invalid_envelope", "Expected a JSON object.")
    if document.get("format") != FORMAT:
        raise SettingsShareError(
            "unsupported_format", f"Unsupported settings format; expected {FORMAT}."
        )
    if type(document.get("version")) is not int or document["version"] != VERSION:
        raise SettingsShareError(
            "unsupported_version", f"Unsupported settings version; expected {VERSION}."
        )
    if document.get("type") != TYPE:
        raise SettingsShareError(
            "unsupported_type", f"Unsupported settings type; expected {TYPE}."
        )
    raw = document.get("settings")
    if not isinstance(raw, dict):
        raise SettingsShareError(
            "invalid_envelope", "The envelope carries no settings object."
        )
    return {
        key: copy.deepcopy(value)
        for key, value in raw.items()
        if key in settings.DEFAULTS and key not in EXCLUDED_KEYS
    }


def review(imported: dict, current: dict) -> dict:
    """Which top-level keys the apply would change, and which it keeps.

    Computed against the live document the way apply_document will apply
    it, so the summary cannot promise something else. Keys absent from the
    import -- including discord_webhook, which parse_text always dropped --
    are reported as kept rather than silently omitted.
    """
    changed = sorted(
        key
        for key in imported
        if imported[key] != current.get(key, settings.DEFAULTS[key])
    )
    kept = sorted(key for key in settings.DEFAULTS if key not in imported)
    return {"changed": changed, "kept": kept}


def apply_document(imported: dict, live: dict) -> None:
    """Overlay the imported keys onto the live document, in place.

    Must run inside ``settings.update(live)``: update() normalizes the
    result through the validated_* functions and persists it, and its
    rollback restores the prior document if the save fails. Unknown keys
    are ignored (parse_text already dropped them, but a caller may hold an
    older parse); excluded keys are skipped for the same defence in depth
    that drops them at parse time.
    """
    for key, value in imported.items():
        if key in settings.DEFAULTS and key not in EXCLUDED_KEYS:
            live[key] = copy.deepcopy(value)
