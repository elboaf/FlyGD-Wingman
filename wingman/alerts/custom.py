"""Pure local custom-alert rules and literal visible-text matching."""

import html
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from .patterns import EVENTS

MAX_CUSTOM_RULES = 8
MAX_CUSTOM_NAME = 80
MIN_CUSTOM_SEARCH = 3
MAX_CUSTOM_SEARCH = 200

_TIMESTAMP_RE = re.compile(
    r"^\s*\[\s*[0-9]{4}\.[0-9]{2}\.[0-9]{2}\s+"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\s*\]"
)
_TAG_RE = re.compile(r"<[^>]*>")
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True)
class CustomRule:
    id: str
    name: str = "Custom alert"
    search: str = ""
    enabled: bool = False
    color: str = "#ff8c42"
    sound: str = "none"
    cooldown_s: int = 8


@dataclass(frozen=True)
class RuntimeRule:
    rule: CustomRule
    generation: int
    position: int
    needle: str


@dataclass(frozen=True)
class BuiltinRule:
    event: str
    enabled: bool
    color: str
    sound: str
    cooldown_s: int
    pulses: int
    flash_rate: str


@dataclass(frozen=True)
class AlertRuntimeSnapshot:
    preview_enabled: bool
    alerts_enabled: bool
    pve_filter: bool
    persist_until_selected: bool
    volume: int
    rules_revision: int
    activation_epoch: int
    builtins: tuple[BuiltinRule, ...]
    custom_rules: tuple[RuntimeRule, ...]
    executable: tuple[RuntimeRule, ...]


def _decoded_visible(text: str) -> str:
    text = _TIMESTAMP_RE.sub("", text, count=1)
    return html.unescape(_TAG_RE.sub("", text))


def normalize_visible(text: str) -> str:
    """Keep visible adjacency and category markers, unlike ownership parsing."""
    return " ".join(_decoded_visible(text).split()).casefold()


class RuleValidationError(ValueError):
    """A fixed user-facing refusal that never echoes private rule text."""


def _has_controls(text: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in text)


def validate_search(search: object, *, allow_blank: bool) -> tuple[str, str]:
    """Return display text separately from its executable folded needle."""
    if not isinstance(search, str):
        raise RuleValidationError("Search must be text.")
    # Inspect the actual decoded visible text before whitespace collapse can
    # erase controls, including entities made adjacent by removing tags.
    if _has_controls(search) or _has_controls(_decoded_visible(search)):
        raise RuleValidationError("Search cannot contain control characters.")
    display = search.strip()
    if not display and allow_blank:
        return "", ""
    needle = normalize_visible(display)
    if not MIN_CUSTOM_SEARCH <= len(needle) <= MAX_CUSTOM_SEARCH:
        raise RuleValidationError(
            f"Search must contain {MIN_CUSTOM_SEARCH}-{MAX_CUSTOM_SEARCH} visible characters."
        )
    return display, needle


def validate_rule(
    raw: object, *, normalize_style: Callable[[dict], dict], strict_style: bool
) -> CustomRule:
    """Validate authority; the injected adapter owns existing style semantics."""
    if not isinstance(raw, dict):
        raise RuleValidationError("Alert must be an object.")
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or _ID_RE.fullmatch(rule_id) is None:
        raise RuleValidationError("Alert ID is invalid.")
    defaults = CustomRule(rule_id)
    name = raw.get("name", defaults.name)
    if (
        not isinstance(name, str)
        or _has_controls(name)
        or not 1 <= len(name.strip()) <= MAX_CUSTOM_NAME
    ):
        raise RuleValidationError(
            f"Name must contain 1-{MAX_CUSTOM_NAME} characters and no controls."
        )
    enabled = raw.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise RuleValidationError("Enabled must be a boolean.")
    search, needle = validate_search(
        raw.get("search", defaults.search), allow_blank=True
    )
    style = normalize_style(raw)
    if strict_style:
        for key in ("color", "sound", "cooldown_s"):
            value = raw.get(key, getattr(defaults, key))
            # Equality alone accepts True as 1 and 8.0 as 8. A discrete edit
            # must not acknowledge a value that the normalizer actually refused.
            if type(value) is not type(style[key]) or value != style[key]:
                raise RuleValidationError("Alert style is invalid.")
    return CustomRule(
        id=rule_id,
        name=name.strip(),
        search=search,
        enabled=enabled and bool(needle),
        color=style["color"],
        sound=style["sound"],
        cooldown_s=style["cooldown_s"],
    )


def prepare_alert_snapshot(
    preview: dict, previous: AlertRuntimeSnapshot | None = None
) -> AlertRuntimeSnapshot:
    """Project normalized settings before persistence, without I/O or mutation.

    Settings owns validation, including the eight-rule bound and unique IDs.
    Position affects arbitration, but must not invalidate an unchanged query.
    """
    alerts = preview["alerts"]
    rules = tuple(CustomRule(**raw) for raw in alerts["custom_rules"])
    revision = 1
    old_rows = {}
    if previous is not None:
        old_rows = {row.rule.id: row for row in previous.custom_rules}
        changed = rules != tuple(row.rule for row in previous.custom_rules)
        revision = previous.rules_revision + int(changed)

    rows = []
    for position, rule in enumerate(rules):
        old = old_rows.get(rule.id)
        unchanged = old is not None and old.rule == rule
        rows.append(
            RuntimeRule(
                rule=rule,
                generation=old.generation if unchanged else revision,
                position=position,
                needle=old.needle if unchanged else normalize_visible(rule.search),
            )
        )
    custom_rules = tuple(rows)
    executable = (
        tuple(row for row in custom_rules if row.rule.enabled and row.needle)
        if preview["enabled"] and alerts["enabled"]
        else ()
    )
    epoch = 1
    if previous is not None:
        epoch = previous.activation_epoch + int(
            bool(executable) != bool(previous.executable)
        )
    return AlertRuntimeSnapshot(
        preview_enabled=preview["enabled"],
        alerts_enabled=alerts["enabled"],
        pve_filter=alerts["pve_filter"],
        persist_until_selected=alerts["persist_until_selected"],
        volume=alerts["volume"],
        rules_revision=revision,
        activation_epoch=epoch,
        builtins=tuple(
            BuiltinRule(event=event, **alerts["events"][event]) for event in EVENTS
        ),
        custom_rules=custom_rules,
        executable=executable,
    )


def match_line(line: str, snapshot: AlertRuntimeSnapshot) -> tuple[RuntimeRule, ...]:
    """Normalize once per active line, then perform bounded literal searches."""
    if not snapshot.executable:
        return ()
    visible = normalize_visible(line)
    return tuple(row for row in snapshot.executable if row.needle in visible)


def rule_is_current(
    snapshot: AlertRuntimeSnapshot,
    rule_id: str,
    generation: int,
    activation_epoch: int,
) -> bool:
    """Refuse queued matches from replaced rules or a retired activation."""
    return activation_epoch == snapshot.activation_epoch and any(
        row.rule.id == rule_id and row.generation == generation
        for row in snapshot.executable
    )


def presentation_spec(rule: CustomRule, *, persist: bool) -> dict:
    """Return only renderer style — identity/text never belong in the spec."""
    return {
        "enabled": True,
        "color": rule.color,
        "sound": rule.sound,
        "cooldown_s": rule.cooldown_s,
        "pulses": 3,
        "flash_rate": "normal",
        "persist_until_selected": persist,
    }
