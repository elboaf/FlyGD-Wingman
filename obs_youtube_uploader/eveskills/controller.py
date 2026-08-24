"""Orchestration for the EVE skills route: state ownership, workers, pushes.

This module is the only writer of the skills state document. Nothing else
opens it for writing -- not the auth worker, not the refresh worker, not the
bridge. `atomicio.py:1-5` is explicit that atomic replacement addresses torn
*reads* and says nothing about lost *updates*: "single writer ownership
settles who may write." Without a stated owner a forget completing during a
refresh is silently undone by the refresh's save, and a character authorised
mid-refresh disappears.

Auth, refresh, forget and plan selection can all be in flight at once -- the
two latches Task 13/14 add stop two refreshes and two authorisations, and
nothing else. So every read-modify-write of the roster happens under
`self._lock`, and the mutation and the save live in the same critical
section. It is never correct to read a snapshot, work from it, and save
later: the document is written whole, so a stale snapshot silently reverts
everything committed since it was taken.

Datetimes are timezone-aware `datetime` objects everywhere inside the
package. This module is the bridge boundary and the only place they become
ISO strings.
"""
import json
import logging
import os
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import application, evaluator, planstore, skillids
from . import esi as esi_mod
from . import state as state_mod

logger = logging.getLogger(__name__)

# TriffSkillsController.cs:847,857 caps both the warnings strip and each
# plan issue's own diagnostics list at 20 -- this is the largest payload in
# the app and crosses the bridge on every push, so an unbounded diagnostics
# list from a single pathologically malformed plan file (thousands of bad
# lines) would otherwise inflate every subsequent push, not just the one
# reload that found it.
MAX_WARNINGS = 20
MAX_DIAGNOSTICS_PER_ISSUE = 20


def _utcnow() -> datetime:
    """Injectable in tests; production reads the real clock exactly here."""
    return datetime.now(timezone.utc)


def _iso(value) -> str:
    """A datetime as ISO 8601, or "" when it is absent.

    "" rather than None because the page renders these directly and a
    JSON null would print as "null" in a table cell. Every timestamp in
    both payload shapes goes through this.
    """
    return value.isoformat() if value is not None else ""


def _default_open_folder(path: Path) -> None:
    """Open a folder in the shell. Windows only; a no-op elsewhere.

    `os.startfile` does not exist off Windows, so it is looked up at call
    time behind the platform check rather than imported -- the same posture
    `__main__.set_dpi_awareness()` takes with its Win32 calls. Off Windows
    this is a deliberate no-op: development boxes have no shell to ask, and
    a raised NotImplementedError would turn a cosmetic button into an
    alert.
    """
    if sys.platform != "win32":
        return
    os.startfile(str(path))  # noqa: attribute exists only on Windows


class SkillsController:
    """Owns the roster in memory and the state document on disk."""

    def __init__(self, *, state_path, cache_path, plans_dir, push, alert,
                 client=None, key_source=None, spawn=threading.Thread,
                 open_folder=None, launch_browser=webbrowser.open,
                 now=_utcnow, sso=None, listener_factory=None,
                 validate_token=None) -> None:
        self._state_path = Path(state_path)
        self._cache_path = Path(cache_path)
        self._plans_dir = Path(plans_dir)
        self._push_cb = push
        self._alert = alert
        self._now = now
        self._spawn = spawn
        self._launch_browser = launch_browser
        self._open_folder = (open_folder if open_folder is not None
                             else _default_open_folder)
        self._client = client if client is not None else esi_mod.EsiClient(
            user_agent=application.USER_AGENT)
        # Built lazily on first use rather than here: constructing a
        # SigningKeySource is cheap but a JWKS fetch is not, and a user who
        # never signs in must never pay for one. (Task 14.)
        self._key_source = key_source
        self._sso = sso
        self._listener_factory = listener_factory
        self._validate_token = validate_token

        # THE lock. Re-entrant because commit paths mutate the roster and
        # then call helpers that also save, and the save path takes this
        # same lock. A plain Lock would deadlock on the first such nesting,
        # and discovering that at runtime costs a hung worker rather than
        # an exception -- no traceback, no log line, just a refresh that
        # never finishes.
        self._lock = threading.RLock()

        self._state, warnings = state_mod.load(self._state_path)
        cache, cache_warnings = skillids.load(self._cache_path)
        self._cache = cache
        # Only the state document's and the id cache's OWN load warnings
        # (both plain strings) live here. Plan-folder problems are a
        # different shape (a filename and, sometimes, per-line diagnostics)
        # and get their own payload key below -- folding a PlanIssue into
        # this list would either lose that structure or force every
        # consumer of "warnings" to sniff two shapes out of one array.
        self._load_warnings = list(warnings) + list(cache_warnings)

        self._plans: list = []
        self._plan_issues: list = []
        self._plans_updated = None
        # The last payload actually sent, as JSON. `onSkills` carries the
        # whole world and is the largest payload in the app; mutation
        # handlers push it on both success and failure paths, so an
        # identical re-push is common and costs a full serialise plus a DOM
        # rebuild for nothing.
        self._last_push_json = ""

        # Seeded only when the folder is absent. Re-seeding on every launch
        # would resurrect a starter plan the user deliberately deleted.
        if not self._plans_dir.exists():
            try:
                planstore.seed_starter_plan(self._plans_dir)
            except OSError:
                logger.exception("Could not seed the starter skill plan")
        with self._lock:
            self._load_plans_locked()

    # ----- plans ----------------------------------------------------------

    def _load_plans_locked(self) -> None:
        """Refill `self._plans` and `self._plan_issues` from disk.

        `planstore.list_plans` is documented never to raise -- a bad
        entry, a bad file, even an unreadable folder all come back as
        `PlanIssue`s in its second return value. The `except OSError`
        below is therefore a belt-and-braces guard against a future
        change to that contract, not a path this suite exercises.
        """
        try:
            plans, issues = planstore.list_plans(self._plans_dir)
        except OSError as exc:
            plans, issues = [], [planstore.PlanIssue(
                "plans", f"Could not read the plans folder: {exc}", ())]
        self._plans = plans
        self._plan_issues = list(issues)
        self._plans_updated = self._now()

    def _find_plan_locked(self, name: str):
        """Case-insensitive, per the global rule for plan names."""
        target = str(name or "").casefold()
        if not target:
            return None
        for plan in self._plans:
            if plan.name.casefold() == target:
                return plan
        return None

    def _selected_plan_locked(self):
        return self._find_plan_locked(self._state.selected_plan_name)

    # ----- persistence ------------------------------------------------

    def _save_locked(self) -> bool:
        """Write the document. Returns False rather than raising.

        A refresh that fetched good data and then failed to save has live
        data in memory and nothing on disk. That is a degraded state, not a
        failed one, and the caller flags the row accordingly -- so this
        reports the failure instead of unwinding a commit that is already
        correct in memory.
        """
        try:
            state_mod.save(self._state, self._state_path)
            return True
        except OSError:
            logger.exception("Could not save the EVE skills state document")
            return False

    # ----- payload ----------------------------------------------------

    def state_payload(self) -> dict:
        with self._lock:
            return self._state_payload_locked()

    def _state_payload_locked(self) -> dict:
        selected = self._selected_plan_locked()
        ids = self._cache.type_ids()
        return {
            "auth_configured": application.is_configured(),
            "auth_in_progress": False,      # Task 14 supplies the real flag.
            "refresh_in_flight": False,     # Task 13 supplies the real flag.
            "selected_plan_name": selected.name if selected else "",
            "plans": [self._plan_row_locked(plan, ids) for plan in self._plans],
            "characters": [self._character_row(ch, selected, ids)
                           for ch in self._state.characters],
            # Every issue planstore.list_plans reported: a rejected file
            # (with its per-line diagnostics) and a folder-level problem
            # (empty diagnostics) both come through unchanged, keyed by
            # the PlanIssue's own file_name/message/diagnostics -- there is
            # no second, independent source of "broken plan" here, because
            # a PlanFile that made it into self._plans is `ok` by
            # construction (list_plans excludes anything with diagnostics).
            "plan_issues": [
                {"file_name": issue.file_name, "message": issue.message,
                 "diagnostics": [{"line": d.line, "message": d.message}
                                 for d in issue.diagnostics[
                                     :MAX_DIAGNOSTICS_PER_ISSUE]]}
                for issue in self._plan_issues],
            "warnings": list(self._load_warnings[:MAX_WARNINGS]),
            "plans_updated_utc": _iso(self._plans_updated),
        }

    def _plan_row_locked(self, plan, ids) -> dict:
        """One left-rail row: the plan's size and how many can fly it.

        Every character is evaluated against every plan here, which is
        O(plans x characters) evaluations per payload. Seven plans against
        forty characters is under three hundred passes over a few dozen
        requirements, which is far cheaper than caching it would be to keep
        correct across a refresh that lands mid-render.
        """
        ready = 0
        for ch in self._state.characters:
            if not ch.has_snapshot:
                continue
            analysis = evaluator.evaluate(
                plan.requirements, ids, ch.active_levels,
                ch.trained_levels, ch.queue, True)
            if analysis.readiness == evaluator.READY:
                ready += 1
        return {"name": plan.name,
                "requirement_count": len(plan.requirements),
                "ready_count": ready}

    def _character_row(self, ch, plan, ids) -> dict:
        """One roster row, scored against the selected plan.

        `analysis` is None when no plan is selected or the previously
        selected plan file is no longer in `self._plans` (deleted, or
        rejected on the last reload). A character with no snapshot at all
        scores `Unscored` with empty requirements from the evaluator
        itself, so both cases land on the same row shape -- `Unscored`
        with zero counts, which is the most common state a user sees and
        is not padding.
        """
        analysis = None
        if plan is not None:
            analysis = evaluator.evaluate(
                plan.requirements, ids, ch.active_levels, ch.trained_levels,
                ch.queue, ch.has_snapshot)
        return {
            "character_id": ch.character_id,
            "character_name": ch.character_name,
            "fetched_utc": _iso(ch.fetched_utc),
            "error": ch.error,
            "needs_reauth": bool(ch.needs_reauth),
            "stale": ch.stale,
            "readiness": analysis.readiness if analysis else evaluator.UNSCORED,
            "estimated_finish_utc": (_iso(analysis.estimated_finish_utc)
                                     if analysis else ""),
            "queue_timing_unknown": (bool(analysis.queue_timing_unknown)
                                     if analysis else False),
            "active_count": analysis.active_count if analysis else 0,
            "trained_inactive_count": (analysis.trained_inactive_count
                                       if analysis else 0),
            "queued_count": analysis.queued_count if analysis else 0,
            "missing_count": analysis.missing_count if analysis else 0,
            "unknown_count": analysis.unknown_count if analysis else 0,
        }

    # ----- pushing ------------------------------------------------------

    def _push_state(self, *, force: bool = False) -> None:
        """Send the whole world to the page, deduped against the last send.

        `force` is not an optimisation switch: every mutation path sets it,
        because a committed change that the dedupe swallows is a page
        showing state the controller no longer holds. The dedupe exists for
        the *idle* re-pushes -- a refresh pass that returns all-304, a
        no-op toggle -- where the payload genuinely has not moved.
        """
        payload = self.state_payload()
        blob = json.dumps(payload, sort_keys=True, default=str)
        with self._lock:
            if not force and blob == self._last_push_json:
                return
            self._last_push_json = blob
        # Outside the lock: `push` reaches pywebview, and holding the state
        # lock across a bridge call would let a slow page block a refresh
        # worker's commit.
        self._push_cb("onSkills", payload)

    # ----- plan commands --------------------------------------------------

    def reload_plans(self) -> None:
        with self._lock:
            self._load_plans_locked()
        self._push_state(force=True)

    def select_plan(self, plan_name) -> bool:
        """Select a plan by name. False when it no longer exists, or when
        the selection could not be made durable.

        The empty string is a valid selection -- it clears the choice -- so
        it is handled before the lookup rather than falling into it.

        On a save failure the in-memory value is rolled back to what was
        selected before this call. Without the rollback, the controller
        would hold a selection in memory that was never written to disk --
        the page would be told it succeeded, and if the process exits
        before some later, unrelated save happens to persist it, the
        selection silently reverts with nothing ever having been shown.
        `_save_locked`'s own docstring says "the caller flags the row
        accordingly"; this is that caller doing so.
        """
        name = str(plan_name or "")
        with self._lock:
            previous = self._state.selected_plan_name
            if name:
                plan = self._find_plan_locked(name)
                if plan is None:
                    # The page can hold a stale plan list across a reload
                    # that deleted the file. Reported rather than coerced to
                    # "no selection", which would silently discard a click.
                    return False
                # The file's own spelling, not the caller's: the rail
                # renders from the stored name.
                self._state.selected_plan_name = plan.name
            else:
                self._state.selected_plan_name = ""
            saved = self._save_locked()
            if not saved:
                self._state.selected_plan_name = previous
        # Both the push and the alert happen outside the lock, matching
        # _push_state's own rule: `push`/`alert` reach pywebview, and
        # holding the state lock across a bridge call would let a slow
        # page block a refresh worker's commit.
        self._push_state(force=True)
        if not saved:
            self._alert("warning", "Could not save the selected plan",
                        "Your selection was not saved and has been "
                        "reverted.")
            return False
        return True

    def open_plans_folder(self) -> None:
        """Show the plans folder in the shell. Never raises.

        The folder is created first: on a machine where the starter plan
        could not be seeded it may not exist, and opening a path that is
        not there is an error dialog from the shell rather than from us.
        """
        with self._lock:
            plans_dir = self._plans_dir
        try:
            plans_dir.mkdir(parents=True, exist_ok=True)
            self._open_folder(plans_dir)
        except Exception:
            logger.exception("Could not open the skill plans folder")
            self._alert("warning", "Could not open the plans folder",
                        f"The folder is {plans_dir}.")
