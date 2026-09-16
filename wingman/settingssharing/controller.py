"""Settings export/import runtime ownership.

Named file operations over borrowed bridge-call threads; ``ui/api.py`` keeps
one-line facades. The review slot holds at most one parsed import at a time,
on the setup-review pattern: a fresh read supersedes the previous offer, and
apply/discard claim it by identity so a superseded offer can never be
applied after its replacement arrived.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import atomicio
from .. import settings as settings_mod
from . import model

logger = logging.getLogger(__name__)

DEFAULT_FILENAME = "wingman-settings.json"


@dataclass(frozen=True)
class SettingsSharePorts:
    """Named effects only; no port is called during construction."""

    choose_settings_input: Callable[[], str]
    choose_settings_output: Callable[[str], str]
    # Called once after a successful apply, outside the settings.update()
    # block: the imported document is durable, and live consumers (preview
    # layouts, crops, companions) must be told to re-read it. Optional so
    # headless compositions need no stub.
    on_applied: Callable[[], None] | None = None


class SettingsShareController:
    """One pending import offer; exports read the live document directly.

    The live settings document is shared by reference, exactly as
    ProfilesController receives it -- apply_document mutates it inside
    settings.update(), which normalizes and persists under the save lock.
    """

    def __init__(self, settings: dict, *, ports: SettingsSharePorts):
        self._settings = settings
        self._ports = ports
        self._pending: dict | None = None
        # pywebview runs each bridge call on its own thread; the slot is
        # claimed by review_id so concurrent read/apply pairs stay ordered.
        self._lock = threading.Lock()

    def export_file(self) -> dict:
        reply = {"ok": False, "cancelled": False, "error": "", "path": ""}
        try:
            text = model.export_text(self._settings)
            chosen = self._ports.choose_settings_output(DEFAULT_FILENAME)
            if not chosen:
                return {**reply, "cancelled": True}
            destination = Path(chosen)
            if destination.suffix.lower() != ".json":
                raise model.SettingsShareError(
                    "invalid_request",
                    "Choose a .json filename for the settings export.",
                )
            atomicio.write_atomic(destination, text, encoding="utf-8")
            return {**reply, "ok": True, "path": str(destination)}
        except Exception as error:
            # A failed dialog/write is an error, never cancellation or a path.
            logger.exception("Could not save a settings export file")
            return {**reply, "error": str(error)}

    def import_read(self) -> dict:
        reply = {
            "ok": False,
            "cancelled": False,
            "error": "",
            "review_id": "",
            "summary": {},
        }
        try:
            chosen = self._ports.choose_settings_input()
            if not chosen:
                return {**reply, "cancelled": True}
            raw = Path(chosen).read_bytes()[: model.MAX_BYTES + 1]
            if len(raw) > model.MAX_BYTES:
                raise model.SettingsShareError(
                    "byte_limit",
                    f"A settings export exceeds the {model.MAX_BYTES} UTF-8 byte limit.",
                )
            document = model.parse_text(raw.decode("utf-8-sig"))
            review_id = str(uuid.uuid4())
            with self._lock:
                self._pending = {"id": review_id, "document": document}
            return {
                **reply,
                "ok": True,
                "review_id": review_id,
                "summary": model.review(document, self._settings),
            }
        except Exception as error:
            # Native dialog implementations can raise platform-specific
            # exceptions; a malformed file must read as a refusal, not a raise.
            logger.exception("Could not read a settings export file")
            return {**reply, "error": str(error)}

    def import_review(self, review_id: str) -> dict:
        reply = {"ok": False, "error": "", "summary": {}}
        with self._lock:
            pending = self._pending
        if pending is None or pending["id"] != review_id:
            return {**reply, "error": "That import offer is no longer current."}
        return {
            **reply,
            "ok": True,
            "summary": model.review(pending["document"], self._settings),
        }

    def import_apply(self, review_id: str) -> dict:
        reply = {"ok": False, "error": ""}
        with self._lock:
            pending = self._pending
            if pending is None or pending["id"] != review_id:
                return {**reply, "error": "That import offer is no longer current."}
            # Claimed before any I/O: a second apply of the same review_id
            # must fail even while the first is still saving.
            self._pending = None
        try:
            with settings_mod.update(self._settings):
                model.apply_document(pending["document"], self._settings)
        except (OSError, ValueError) as error:
            # update() rolled the live document back before re-raising, so
            # only the report is left to own here.
            logger.exception("Could not apply a settings import")
            return {**reply, "error": str(error)}
        if self._ports.on_applied is not None:
            try:
                # Outside the update() block on purpose: settings calls are
                # not re-entrant inside one. A live-refresh failure cannot
                # un-apply the durable import, so it must not reach the page
                # as an apply error inviting a second apply of a claimed id.
                self._ports.on_applied()
            except Exception:  # The import is already durable; swallow and log.
                logger.exception("Could not apply an import to live preview state")
        return {**reply, "ok": True}

    def import_discard(self, review_id: str) -> bool:
        with self._lock:
            if self._pending is None or self._pending["id"] != review_id:
                return False
            self._pending = None
            return True
