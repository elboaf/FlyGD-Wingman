"""Custom alert authority and presentation-only Test, without a worker or UI."""

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, fields
from threading import Event

from .. import settings as settings_mod
from ..telemetry.model import CustomMatcherHealth
from .custom import (
    MAX_CUSTOM_RULES,
    AlertRuntimeSnapshot,
    CustomRule,
    RuleValidationError,
    presentation_spec,
    rule_is_current,
)


@dataclass(frozen=True)
class AlertsPorts:
    update_settings: Callable[[], AbstractContextManager[dict]]
    reader_state: Callable[[], dict]
    matcher_health: Callable[[], CustomMatcherHealth]
    preview_characters: Callable[[], tuple[str, ...]]
    preview_available: Callable[[], bool]
    raise_alert: Callable[[str, str, dict], None]
    play_sound: Callable[[str, int], None]


class _Unchanged(Exception):
    """Abort the settings context without persisting an unchanged document."""

    def __init__(self, error: str | None = None):
        self.error = error


_EDITABLE_FIELDS = frozenset(field.name for field in fields(CustomRule)) - {"id"}
_STYLE_FIELDS = _EDITABLE_FIELDS - {"name", "search", "enabled"}


def _test_result(applied: bool, error: str | None = None) -> dict:
    return {"applied": applied, "persisted": False, "error": error}


def _rule_index(rules: list[dict], rule_id: str) -> int:
    if isinstance(rule_id, str):
        for index, rule in enumerate(rules):
            if rule["id"] == rule_id:
                return index
    raise _Unchanged("This custom alert no longer exists.")


class AlertsController:
    def __init__(self, settings: dict, *, ports: AlertsPorts):
        self._ports = ports
        self._reader = settings_mod.committed_preview(settings)
        self._runtime_closed = Event()

    def runtime_snapshot(self) -> AlertRuntimeSnapshot:
        return self._reader.alerts_snapshot()

    def close_runtime(self) -> None:
        self._runtime_closed.set()

    def is_current(self, rule_id: str, generation: int, activation_epoch: int) -> bool:
        if self._runtime_closed.is_set():
            return False
        snapshot = self.runtime_snapshot()
        if (generation, activation_epoch) == (0, 0):
            # Only controller-created Test presentations use these reserved tokens.
            return any(row.rule.id == rule_id for row in snapshot.custom_rules)
        return rule_is_current(snapshot, rule_id, generation, activation_epoch)

    def state(self) -> dict:
        snapshot = self.runtime_snapshot()
        matcher = {"state": "inactive", "detail": None}
        if snapshot.executable:
            health = self._ports.matcher_health()
            if health.state == "degraded":
                # An edit or master toggle is not a successful matcher invocation.
                matcher = {"state": "degraded", "detail": health.detail}
            elif (
                health.state == "active"
                and health.rules_revision == snapshot.rules_revision
                and health.activation_epoch == snapshot.activation_epoch
            ):
                matcher = {"state": "active", "detail": health.detail}
            else:
                matcher = {"state": "waiting", "detail": None}
        return {
            "revision": snapshot.rules_revision,
            "rules": [asdict(row.rule) for row in snapshot.custom_rules],
            "limit": MAX_CUSTOM_RULES,
            "previews_enabled": snapshot.preview_enabled,
            "alerts_enabled": snapshot.alerts_enabled,
            "reader": self._ports.reader_state(),
            "matcher": matcher,
        }

    def _mutate(self, rule_id: str | None, change: Callable[[list[dict]], str]) -> dict:
        error = None
        try:
            with self._ports.update_settings() as document:
                preview = settings_mod.validated_preview(document.get("preview"))
                changed_id = change(preview["alerts"]["custom_rules"])
                document["preview"] = preview
            rule_id = changed_id
        except _Unchanged as exc:
            error = exc.error
        except RuleValidationError as exc:
            error = str(exc)
        except OSError:
            error = (
                "Could not save custom alerts. Your previous settings are unchanged."
            )
        # Ports and page serialization must run after releasing the settings lock.
        return {
            "applied": error is None,
            "persisted": error is None,
            "error": error,
            "state": self.state(),
            "rule_id": rule_id if isinstance(rule_id, str) else None,
        }

    def add(self) -> dict:
        def change(rules):
            if len(rules) >= MAX_CUSTOM_RULES:
                raise _Unchanged(
                    f"You can have at most {MAX_CUSTOM_RULES} custom alerts."
                )
            rule = CustomRule(uuid.uuid4().hex)
            rules.append(asdict(rule))
            return rule.id

        return self._mutate(None, change)

    def edit(self, rule_id: str, draft: object) -> dict:
        def change(rules):
            index = _rule_index(rules, rule_id)
            if not isinstance(draft, dict) or not draft.keys() >= _EDITABLE_FIELDS:
                raise _Unchanged("Provide all custom alert fields.")
            rule = settings_mod.validate_custom_rule_edit(rule_id, draft)
            canonical = asdict(rule)
            if canonical == rules[index]:
                raise _Unchanged()
            rules[index] = canonical
            return rule_id

        return self._mutate(rule_id, change)

    def set_enabled(self, rule_id: str, enabled: object) -> dict:
        def change(rules):
            rule = rules[_rule_index(rules, rule_id)]
            if not isinstance(enabled, bool):
                raise _Unchanged("Enabled must be a boolean.")
            if enabled and not rule["search"]:
                raise _Unchanged("Enter a search before enabling this alert.")
            if rule["enabled"] == enabled:
                raise _Unchanged()
            rule["enabled"] = enabled
            return rule_id

        return self._mutate(rule_id, change)

    def remove(self, rule_id: str) -> dict:
        def change(rules):
            rules.pop(_rule_index(rules, rule_id))
            return rule_id

        return self._mutate(rule_id, change)

    def test(self, rule_id: str, draft: object) -> dict:
        if not self.is_current(rule_id, 0, 0):
            return _test_result(
                False, "This custom alert is no longer available for Test."
            )
        if not isinstance(draft, dict) or not draft.keys() >= _STYLE_FIELDS:
            return _test_result(False, "Provide all custom alert style fields.")
        try:
            # Unfinished text and caller-supplied identity/tokens cannot affect
            # presentation. Reuse strict style validation, not an executable query.
            rule = settings_mod.validate_custom_rule_edit(
                rule_id, {key: draft[key] for key in _STYLE_FIELDS}
            )
        except RuleValidationError as exc:
            return _test_result(False, str(exc))
        volume = self.runtime_snapshot().volume
        available = self._ports.preview_available()
        characters = self._ports.preview_characters() if available else ()
        applied = False
        stopped = "This custom alert is no longer available for Test."
        if not self.is_current(rule_id, 0, 0):
            return _test_result(False, stopped)
        if rule.sound != "none" and volume > 0:
            self._ports.play_sound(rule.sound, volume)
            applied = True
        for character in characters:
            # Close/remove fence pending effects, not audio or a ring already begun.
            if not self.is_current(rule_id, 0, 0):
                return _test_result(applied, stopped)
            spec = presentation_spec(rule, persist=False)
            spec.update(
                custom_test=True,
                custom_rule_id=rule_id,
                custom_generation=0,
                custom_activation_epoch=0,
            )
            self._ports.raise_alert(character, "custom", spec)
            applied = True
        if not characters:
            reason = (
                "Previews are unavailable"
                if not available
                else "No EVE clients are open"
            )
            effect = (
                "only the sound played" if applied else "no sound or preview played"
            )
            return _test_result(applied, f"{reason}, so {effect}.")
        return _test_result(applied)
