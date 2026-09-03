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
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

# The shared owner, not `wingman.eveskills.application`'s compatibility
# re-export. Capability lookup and authorization now live in eveauth, so
# Skills names that same module when requesting its read-only capability.
from ..eveauth import application
from ..eveauth.controller import ACCESS_REASON_OWNER_CHANGED, MutationResult
from . import esi as esi_mod
from . import evaluator, plans, planstore, skillids
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

# Exact user-facing text. These land in a roster row next to the data they
# describe, so they say what the user must DO, not what the transport
# returned -- "401" in a row is not an instruction.
MSG_REAUTH = "EVE rejected the stored authorisation. Re-authenticate this character."
MSG_NO_TOKEN = "No stored authorisation. Re-authenticate this character."
MSG_SAVE_FAILED = "Fresh data is in memory but was not saved for offline use."
MSG_OWNER_CHANGE_DETECTED = (
    "Character ownership changed. Re-authenticate this character."
)
MSG_OWNER_CHANGED = "Character ownership changed; cached skill data was cleared."


# How many missing requirement names a roster row carries (round 6, P1-2).
#
# THREE, not six. ui/copy.py's _COPY_NAME_CAP is six and reasons that past
# a handful a list stops being read as a list -- but that is a modal the
# reader has stopped to check, one list, once. This is a line inside a row
# in a list of thirty-seven, read by scanning, and the row states its own
# remainder from missing_count beside it. Three fits the width the roster
# actually has at the 840 CSS floor without ellipsising the first name.
#
# A precedent for the SIZE of the word, not a derived value; the two are
# free to move apart. tests/test_skills_page.py asserts what this one is.
_ROSTER_NAME_CAP = 3


def _skills_path(character_id: int) -> str:
    return f"/v4/characters/{character_id}/skills/"


def _queue_path(character_id: int) -> str:
    return f"/v2/characters/{character_id}/skillqueue/"


def _clamp_level(value) -> int:
    """0..5. ESI is trusted but not blindly: a level outside the range would
    make an out-of-range requirement score Active."""
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, level))


def _parse_skills(data):
    """(active_levels, trained_levels) from /characters/{id}/skills/.

    Malformed entries are dropped individually rather than failing the
    document, matching state.py's tolerant normalisation: one bad entry
    should cost one skill, not the refresh.
    """
    active: dict[int, int] = {}
    trained: dict[int, int] = {}
    rows = data.get("skills") if isinstance(data, dict) else None
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        try:
            skill_id = int(row["skill_id"])
        except (KeyError, TypeError, ValueError):
            continue
        active[skill_id] = _clamp_level(row.get("active_skill_level"))
        trained[skill_id] = _clamp_level(row.get("trained_skill_level"))
    return active, trained


def _parse_date(value):
    """An ESI timestamp, or None.

    None is a real, expected value: a paused queue entry has no dates, and
    that is exactly what drives "Training -- timing unknown".
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clamp_position(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _parse_queue(data):
    """A tuple of evaluator.QueueEntry, in the order ESI returned them."""
    entries = []
    for row in data if isinstance(data, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            skill_id = int(row["skill_id"])
            finished_level = int(row["finished_level"])
        except (KeyError, TypeError, ValueError):
            continue
        entries.append(
            evaluator.QueueEntry(
                skill_id=skill_id,
                finished_level=max(1, min(5, finished_level)),
                start_date=_parse_date(row.get("start_date")),
                finish_date=_parse_date(row.get("finish_date")),
                queue_position=_clamp_position(row.get("queue_position")),
            )
        )
    return tuple(entries)


def _utcnow() -> datetime:
    """Injectable in tests; production reads the real clock exactly here."""
    return datetime.now(UTC)


def _iso(value) -> str:
    """A datetime as ISO 8601, or "" when it is absent.

    "" rather than None because the page renders these directly and a
    JSON null would print as "null" in a table cell. Every timestamp in
    both payload shapes goes through this.
    """
    return value.isoformat() if value is not None else ""


def _detail_error(character_id: int, plan_name: str, message: str) -> dict:
    """The failure shape, identical in every key to the success shape.

    Same keys either way so the page has one renderer: a payload that drops
    fields on failure means every access in skills.js needs a guard, and the
    one that gets forgotten throws inside a click handler.
    """
    return {
        "ok": False,
        "message": message,
        "character_id": character_id,
        "plan_name": plan_name,
        "readiness": evaluator.READINESS_UNKNOWN,
        "estimated_finish_utc": "",
        "queue_timing_unknown": False,
        "requirements": [],
    }


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
    os.startfile(str(path))


class SkillsController:
    """Owns the roster in memory and the state document on disk."""

    def __init__(
        self,
        *,
        state_path,
        cache_path,
        plans_dir,
        push,
        alert,
        authority,
        client=None,
        spawn=threading.Thread,
        open_folder=None,
        now=_utcnow,
        startup_warnings=(),
    ) -> None:
        self._state_path = Path(state_path)
        self._cache_path = Path(cache_path)
        self._plans_dir = Path(plans_dir)
        self._push_cb = push
        self._alert = alert
        self._authority = authority
        self._now = now
        self._spawn = spawn
        self._open_folder = (
            open_folder if open_folder is not None else _default_open_folder
        )
        self._client = (
            client
            if client is not None
            else esi_mod.EsiClient(user_agent=application.USER_AGENT)
        )
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
        self._load_warnings = (
            list(startup_warnings) + list(warnings) + list(cache_warnings)
        )
        self._authority_owners = {
            character.character_id: character.owner_hash
            for character in self._authority.characters
        }
        self._reconciled_once = False

        self._plans: list = []
        self._plan_issues: list = []
        self._plans_updated = None
        # The last payload actually sent, as JSON. `onSkills` carries the
        # whole world and is the largest payload in the app; mutation
        # handlers push it on both success and failure paths, so an
        # identical re-push is common and costs a full serialise plus a DOM
        # rebuild for nothing.
        self._last_push_json = ""

        # Single-flight latch. `_refresh_again` is the *request* that arrived
        # while a pass was running; the worker re-enters on it rather than
        # dropping it, so a click during a refresh is never silently lost.
        self._refresh_in_flight = False
        self._refresh_again = False
        # Set on shutdown so a refresh pass stops between characters rather
        # than finishing eighty requests after the window has gone.
        self._stopping = threading.Event()
        # The resolver is an attribute rather than a direct call so a test
        # can replace it without a network: skillids.resolve fans out to
        # three ESI endpoints and its own tests already cover that.
        self._resolve = skillids.resolve

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
            plans, issues = (
                [],
                [
                    planstore.PlanIssue(
                        "plans", f"Could not read the plans folder: {exc}", ()
                    )
                ],
            )
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

    # ----- groups ---------------------------------------------------------

    @staticmethod
    def _in_group(ch, group_name: str) -> bool:
        """True when no group is selected, or this character is in it.

        Folded with `.casefold()`, which is NOT the same fold the page
        applies with `.toLowerCase()` in `matching()` (wingman/web/skills.js)
        -- they disagree on input like German sharp S, where
        `'Straße'.casefold() == 'STRASSE'.casefold()` is True in Python but
        `'Straße'.toLowerCase() === 'STRASSE'.toLowerCase()` is false in JS.
        Python can therefore collapse two spellings into one group that the
        page's own matching then treats as two, so a count and its visible
        rows can disagree. Do not "fix" this by hand-rolling a Unicode fold
        in ES5 on the page side to match Python -- that is new surface area
        for a cosmetic mismatch on an edge case nobody has reported. Leave it
        commented rather than papered over.
        """
        if not group_name:
            return True
        return ch.group.casefold() == group_name.casefold()

    def _groups_locked(self) -> list:
        """Every group that has members, sorted, with the count each holds.

        Derived rather than stored: D1 puts membership on the character, so
        this list IS the roster's groups by definition and cannot drift
        from it. Keyed case-insensitively with the FIRST spelling kept,
        matching _find_plan_locked's rule for plan names -- `Wolfpack` and
        `wolfpack` are one crew, and two rail rows for it read as a bug.

        This is the other half of the invariant documented on
        `_selected_group_locked`: both iterate `self._state.characters` in
        the same order under the same lock hold, so the spelling recorded
        here for a given key is always the spelling that function returns
        for the current selection. Keep that ordering agreement if either
        function changes -- it is what keeps the page's `scopedTotal()`
        zero-fallback (wingman/web/skills.js) unreachable.
        """
        counts: dict = {}
        for ch in self._state.characters:
            if not ch.group:
                continue
            row = counts.get(ch.group.casefold())
            if row is None:
                counts[ch.group.casefold()] = {"name": ch.group, "member_count": 1}
            else:
                row["member_count"] += 1
        return sorted(counts.values(), key=lambda row: row["name"].casefold())

    def _selected_group_locked(self) -> str:
        """The stored selection, or "" when nobody holds that name.

        The same posture _selected_plan_locked takes toward a deleted plan
        file: a pointer that no longer resolves is REPORTED as no
        selection, never rewritten. Rewriting would discard the name at the
        moment its last member left, so re-adding that member would not
        bring the selection back.

        Returns the FIRST roster character's spelling for a casefold match,
        same as `_groups_locked` below. Both run under the same lock hold in
        `_state_payload_locked`, over the same `self._state.characters`
        iteration order, so this always returns the exact string
        `_groups_locked` recorded for that key -- which is what keeps the
        page's `scopedTotal()` zero-fallback (wingman/web/skills.js)
        unreachable: the selection it looks up in `groups()` is always
        present there, by construction. Reordering either loop, or having
        one of them prefer a different spelling, breaks that agreement
        silently -- `scopedTotal()` would then return 0 for a group that
        plainly has members, and nothing would flag it.
        """
        target = self._state.selected_group.casefold()
        if not target:
            return ""
        for ch in self._state.characters:
            if ch.group.casefold() == target:
                return ch.group
        return ""

    @staticmethod
    def _clean_group_name(raw) -> "str | None":
        """Trim, then refuse anything over the cap. None means refused.

        Refusing rather than truncating is the same rule state.py applies
        on load, and for the same reason: a shortened name is not a shorter
        pointer to the same group, it is a pointer to a DIFFERENT one that
        may already have members.
        """
        text = str(raw or "").strip()
        if len(text) > state_mod.MAX_GROUP_NAME_CHARS:
            return None
        return text

    def _existing_spelling_locked(self, name: str) -> str:
        """The roster's own spelling of *name*, or *name* when it is new."""
        target = name.casefold()
        for ch in self._state.characters:
            if ch.group and ch.group.casefold() == target:
                return ch.group
        return name

    def set_character_group(self, character_id, group_name) -> bool:
        """Put one character in a group, or clear it with "".

        There is no separate create step: D2 makes a group exist exactly as
        long as someone is in it, so assigning IS creating. Joining takes
        the spelling already on the roster rather than the caller's, which
        is the rule _find_plan_locked applies to plan names.
        """
        try:
            wanted = int(character_id)
        except (TypeError, ValueError):
            # Arrives from JavaScript, where a missing dataset attribute is
            # undefined -> None. Refused rather than coerced.
            logger.warning("Refusing a non-numeric character id: %r", character_id)
            return False
        name = self._clean_group_name(group_name)
        if name is None:
            logger.warning("Refusing an over-long group name: %r", group_name)
            self._alert(
                "warning",
                "Group name is too long",
                f"Group names are capped at {state_mod.MAX_GROUP_NAME_CHARS} "
                "characters. The character was not assigned.",
            )
            return False
        with self._lock:
            character = self._state.find(wanted)
            if character is None:
                return False
            previous = character.group
            character.group = self._existing_spelling_locked(name) if name else ""
            saved = self._save_locked()
            if not saved:
                character.group = previous
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Could not save the change",
                "The character's group was not changed.",
            )
            return False
        return True

    def _rewrite_group_locked(self, target: str, replacement: str) -> "tuple | None":
        """Point every member of *target* at *replacement*. None if unheld.

        Returns the undo record -- the (character, previous group) pairs
        plus the previous selection -- so the caller can restore ALL of it
        on a save failure. Membership and selected_group are two
        representations of one name; restoring one without the other
        recreates the dangling pointer this function exists to avoid.
        """
        key = target.casefold()
        touched = [ch for ch in self._state.characters if ch.group.casefold() == key]
        if not touched:
            return None
        # Which spelling the members end up holding. A rename that differs
        # from the current name only in case is a deliberate RESPELL, so it
        # wins outright. Any other rename onto a name another group already
        # holds is a MERGE, and must adopt that group's existing spelling --
        # set_character_group already normalises this way, and without it a
        # merge leaves two spellings on the roster and _groups_locked shows
        # whichever character happens to come first, so the rail's label
        # would depend on roster order.
        if replacement.casefold() == key:
            spelling = replacement
        else:
            spelling = self._existing_spelling_locked(replacement)
        undo = [(ch, ch.group) for ch in touched]
        for ch in touched:
            ch.group = spelling
        previous_selection = self._state.selected_group
        if previous_selection.casefold() == key:
            self._state.selected_group = spelling
        return (undo, previous_selection)

    def _undo_group_rewrite_locked(self, record) -> None:
        undo, previous_selection = record
        for ch, previous in undo:
            ch.group = previous
        self._state.selected_group = previous_selection

    def rename_group(self, old_name, new_name) -> bool:
        """Rename a group, moving its members and the selection together.

        Renaming onto a name that already has members MERGES the two, which
        is the honest reading of the operation -- the page confirms it
        first. A rename differing only in case is not a merge: it is one
        group respelled, and the page shows no confirmation for it.
        """
        target = self._clean_group_name(old_name)
        replacement = self._clean_group_name(new_name)
        if target is None or replacement is None:
            logger.warning("Refusing an over-long group name")
            self._alert(
                "warning",
                "Group name is too long",
                f"Group names are capped at {state_mod.MAX_GROUP_NAME_CHARS} "
                "characters. The group was not renamed.",
            )
            return False
        if not target or not replacement:
            # Delete is its own command with its own confirmation; a rename
            # that silently became one would bypass it.
            return False
        with self._lock:
            record = self._rewrite_group_locked(target, replacement)
            if record is None:
                return False
            saved = self._save_locked()
            if not saved:
                self._undo_group_rewrite_locked(record)
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Could not save the change",
                "The group was not renamed.",
            )
            return False
        return True

    def delete_group(self, name) -> bool:
        """Remove a group by clearing it from every member.

        D2: a group exists exactly as long as someone is in it, so there is
        nothing else to delete. The selection goes with it.
        """
        target = self._clean_group_name(name)
        if target is None or not target:
            return False
        with self._lock:
            record = self._rewrite_group_locked(target, "")
            if record is None:
                return False
            saved = self._save_locked()
            if not saved:
                self._undo_group_rewrite_locked(record)
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Could not save the change",
                "The group was not deleted.",
            )
            return False
        return True

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
        authority = {
            character.character_id: character
            for character in self._authority.characters
        }
        auth_in_progress = self._authority.auth_in_progress
        with self._lock:
            return self._state_payload_locked(authority, auth_in_progress)

    def _state_payload_locked(self, authority, auth_in_progress) -> dict:
        selected = self._selected_plan_locked()
        group = self._selected_group_locked()
        ids = self._cache.type_ids()
        return {
            "auth_configured": application.is_configured(),
            "auth_in_progress": auth_in_progress,
            "refresh_in_flight": self._refresh_in_flight,
            "selected_plan_name": selected.name if selected else "",
            "selected_group": group,
            "groups": self._groups_locked(),
            "plans": [self._plan_row_locked(plan, ids, group) for plan in self._plans],
            "characters": [
                self._character_row(ch, authority.get(ch.character_id), selected, ids)
                for ch in self._state.characters
                if ch.character_id in authority
            ],
            # Every issue planstore.list_plans reported: a rejected file
            # (with its per-line diagnostics) and a folder-level problem
            # (empty diagnostics) both come through unchanged, keyed by
            # the PlanIssue's own file_name/message/diagnostics -- there is
            # no second, independent source of "broken plan" here, because
            # a PlanFile that made it into self._plans is `ok` by
            # construction (list_plans excludes anything with diagnostics).
            "plan_issues": [
                {
                    "file_name": issue.file_name,
                    "message": issue.message,
                    "diagnostics": [
                        {"line": d.line, "message": d.message}
                        for d in issue.diagnostics[:MAX_DIAGNOSTICS_PER_ISSUE]
                    ],
                }
                for issue in self._plan_issues
            ],
            "warnings": list(self._load_warnings[:MAX_WARNINGS]),
            "plans_updated_utc": _iso(self._plans_updated),
        }

    def _plan_row_locked(self, plan, ids, group) -> dict:
        """One left-rail row: the plan's size and how many can fly it.

        Every character is evaluated against every plan here, which is
        O(plans x characters) evaluations per payload. Seven plans against
        forty characters is under three hundred passes over a few dozen
        requirements, which is far cheaper than caching it would be to keep
        correct across a refresh that lands mid-render.

        A group filter narrows this loop rather than adding a pass: the
        skipped characters are skipped before their evaluation, so scoping
        the count is strictly cheaper than not scoping it.
        """
        ready = 0
        for ch in self._state.characters:
            if not self._in_group(ch, group):
                continue
            if not ch.has_snapshot:
                continue
            analysis = evaluator.evaluate(
                plan.requirements,
                ids,
                ch.active_levels,
                ch.trained_levels,
                ch.queue,
                True,
            )
            if analysis.readiness == evaluator.READY:
                ready += 1
        return {
            "name": plan.name,
            "requirement_count": len(plan.requirements),
            "ready_count": ready,
        }

    def _character_row(self, ch, authority, plan, ids) -> dict:
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
                plan.requirements,
                ids,
                ch.active_levels,
                ch.trained_levels,
                ch.queue,
                ch.has_snapshot,
            )
        capability = self._authority.capability_status(
            ch.character_id, application.SKILLS
        )
        error = " ".join(
            message for message in (ch.error, authority.persistence_error) if message
        )
        return {
            "character_id": ch.character_id,
            "character_name": authority.character_name,
            "group": ch.group,
            "fetched_utc": _iso(ch.fetched_utc),
            "error": error,
            "needs_reauth": bool(authority.needs_reauth or capability != "enabled"),
            "stale": ch.stale,
            "readiness": analysis.readiness if analysis else evaluator.UNSCORED,
            "estimated_finish_utc": (
                _iso(analysis.estimated_finish_utc) if analysis else ""
            ),
            "queue_timing_unknown": (
                bool(analysis.queue_timing_unknown) if analysis else False
            ),
            "active_count": analysis.active_count if analysis else 0,
            "trained_inactive_count": (
                analysis.trained_inactive_count if analysis else 0
            ),
            "queued_count": analysis.queued_count if analysis else 0,
            "missing_count": analysis.missing_count if analysis else 0,
            # Round 6, P1-2. The roster's status column said "9
            # requirements" and the pane beside it was empty to the window
            # edge, so the one screen whose job is "which of my characters
            # can fly this" made you open a row to learn WHICH nine.
            #
            # Free: `analysis` is already built here to produce the counts
            # above, and these names come off the same tuple
            # `missing_count` counts (evaluator.missing_names). No extra
            # ESI call, no extra evaluation, and nothing to do with
            # requestDetail's per-row fetch, whose cost note in skills.js
            # is about a round trip this does not make.
            "missing_names": list(evaluator.missing_names(analysis, _ROSTER_NAME_CAP))
            if analysis
            else [],
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
            self._alert(
                "warning",
                "Could not save the selected plan",
                "Your selection was not saved and has been reverted.",
            )
            return False
        return True

    def select_group(self, group_name) -> bool:
        """Scope the screen to one group. "" is All and is always valid.

        Modelled on select_plan, including its rollback: a selection held
        in memory but never written would silently revert on the next
        launch with nothing ever having been shown.
        """
        name = self._clean_group_name(group_name)
        if name is None:
            logger.warning("Refusing an over-long group name: %r", group_name)
            self._alert(
                "warning",
                "Group name is too long",
                f"Group names are capped at {state_mod.MAX_GROUP_NAME_CHARS} "
                "characters. The selection was not changed.",
            )
            return False
        with self._lock:
            previous = self._state.selected_group
            if name:
                held = any(
                    ch.group.casefold() == name.casefold()
                    for ch in self._state.characters
                )
                if not held:
                    # The page can hold a stale rail across a change that
                    # emptied this group. Reported rather than coerced to
                    # All, which would silently discard a click.
                    return False
                self._state.selected_group = self._existing_spelling_locked(name)
            else:
                self._state.selected_group = ""
            saved = self._save_locked()
            if not saved:
                self._state.selected_group = previous
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Could not save the selected group",
                "Your selection was not saved and has been reverted.",
            )
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
            self._alert(
                "warning",
                "Could not open the plans folder",
                f"The folder is {plans_dir}.",
            )

    # ----- refresh --------------------------------------------------------

    def refresh_characters(self) -> None:
        """Start a refresh pass, or note that one is wanted.

        Returns immediately either way: this is called from the bridge
        thread, and a forty-character pass is eighty sequential HTTP
        requests.
        """
        with self._lock:
            if self._refresh_in_flight:
                self._refresh_again = True
                return
            self._refresh_in_flight = True
        self._push_state(force=True)  # The button becomes "Refreshing...".
        self._spawn(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            while True:
                self._refresh_pass()
                with self._lock:
                    if not self._refresh_again:
                        # Cleared inside the same critical section that
                        # reads the flag: clearing it after the check would
                        # drop a request that arrived in the gap, which is
                        # the exact bug the flag exists to prevent.
                        self._refresh_in_flight = False
                        break
                    self._refresh_again = False
        except Exception:
            logger.exception("EVE skills refresh failed")
            with self._lock:
                # A request that arrived during the failed pass must not be
                # dropped just because the pass blew up instead of finishing
                # cleanly -- re-kick a fresh one, matching
                # TriffSkillsController.cs:385's
                # `if (!cancelled && Volatile.Read(&_refreshRequested) == 1)
                # RefreshCharactersAsync()`. Checked against `_stopping`
                # rather than left unconditional: re-kicking during shutdown
                # would spawn a worker into a window that no longer exists.
                again = self._refresh_again and not self._stopping.is_set()
                self._refresh_again = False
                if not again:
                    self._refresh_in_flight = False
            if again:
                self._spawn(target=self._refresh_worker, daemon=True).start()
                return
        finally:
            # Unconditional: the page's "Refreshing..." state is driven by
            # refresh_in_flight, and a pass that died without this push
            # leaves the button stuck forever.
            self._push_state(force=True)

    def _refresh_pass(self) -> None:
        names = {
            character.character_id: character.character_name
            for character in self._authority.characters
        }
        with self._lock:
            targets = [
                (ch.character_id, names.get(ch.character_id, ""))
                for ch in self._state.characters
                if ch.character_id in names
            ]
        self._resolve_missing_skill_ids()
        total = len(targets)
        for index, (character_id, name) in enumerate(targets, start=1):
            if self._stopping.is_set():
                return
            error = self._refresh_one(character_id)
            self._push_cb(
                "onSkillsProgress",
                {
                    "character_id": character_id,
                    "character_name": name,
                    "completed": index,
                    "total": total,
                    "error": error,
                },
            )
            # Not forced: a character forgotten mid-pass makes _refresh_one
            # return "" without touching the roster, and the dedupe is what
            # keeps that no-op from rebuilding the page. (Every actual
            # commit -- even an all-304 one -- stamps fetched_utc and so
            # always changes the pushed blob; the dedupe never fires there.)
            self._push_state()

    def _refresh_one(self, character_id: int) -> str:
        """Refresh one character under shared lifecycle authority."""
        with ExitStack() as stack:
            try:
                stack.enter_context(
                    self._authority.lifecycle(character_id, application.SKILLS)
                )
            except KeyError:
                return ""
            except PermissionError:
                status = self._authority.capability_status(
                    character_id, application.SKILLS
                )
                message = MSG_NO_TOKEN if status == "missing" else MSG_REAUTH
                self._commit_failure(character_id, message)
                return message
            return self._refresh_one_leased(character_id)

    def _refresh_one_leased(self, character_id: int) -> str:
        """Fetch and commit while the authority lifecycle lease is held."""
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return ""  # Forgotten between the snapshot and here.
            skills_etag, queue_etag = ch.skills_etag, ch.queue_etag

        skills, error, _invalidated = self._authorised_get(
            character_id, _skills_path(character_id), skills_etag
        )
        if skills is None:
            # The queue result could not be committed on its own, so spending
            # the second request would only burn error-limit budget.
            self._commit_failure(character_id, error)
            return error

        queue, error, _invalidated = self._authorised_get(
            character_id, _queue_path(character_id), queue_etag
        )
        if queue is None:
            self._commit_failure(character_id, error)
            return error

        return self._commit_success(character_id, skills, queue)

    def _access_token(self, character_id: int, *, rejected=None):
        """Request one Skills-capable token from shared authority.

        A token may carry a non-empty persistence warning. Presence of the
        token, not an empty error string, decides success; the warning stays
        visible through the immutable authority row joined into the payload.
        """
        result = self._authority.access_token(
            character_id,
            application.SKILLS,
            rejected_token=rejected,
        )
        error = result.error
        if result.token is None and result.grant_invalidated:
            error = (
                MSG_OWNER_CHANGE_DETECTED
                if result.reason == ACCESS_REASON_OWNER_CHANGED
                else MSG_REAUTH
            )
        return result.token, error, result.grant_invalidated

    def _authorised_get(self, character_id: int, path: str, etag: str):
        """One authorised GET with exactly one 401 retry.

        Returns (response, error, definitive). `response` is None on
        failure; on success it is either a 200 or a 304, and the caller must
        treat both as "this half is current".
        """
        token, error, definitive = self._access_token(character_id)
        if token is None:
            return None, error, definitive

        response = self._client.get(path, token=token, etag=etag or None)
        if response.status == 401:
            # One retry, and only one. A token minted seconds ago and
            # rejected again is not a clock-skew problem, it is a revoked
            # grant, and retrying forever would spend the error-limit
            # budget discovering that repeatedly.
            token, error, definitive = self._access_token(character_id, rejected=token)
            if token is None:
                return None, error, definitive
            response = self._client.get(path, token=token, etag=etag or None)
            if response.status == 401:
                # An endpoint rejection is not evidence that the shared grant
                # is invalid. Authority alone classifies refresh/JWT outcomes.
                return None, MSG_REAUTH, False

        if response.status == 403:
            # Scope claims remain authoritative. This endpoint error belongs
            # to Skills and must not delete a grant Fittings may also use.
            return None, MSG_REAUTH, False
        if not (response.ok or response.not_modified):
            # Includes esi.py's synthetic 503 for retry exhaustion, which
            # did not necessarily come from ESI -- transient either way.
            return (
                None,
                f"ESI request failed ({response.status}): {response.error}",
                False,
            )
        return response, "", False

    def _commit_success(self, character_id: int, skills, queue) -> str:
        """Commit both halves, or neither. Returns "" or a degraded message.

        Both responses have already resolved 200 or 304 by the time this is
        called -- that check is the caller's, and it is what makes this
        method a commit rather than a decision. Parsing happens OUTSIDE the
        lock; only the merge is inside it, one short critical section per
        character rather than one held across eighty HTTP requests.
        """
        parsed_skills = _parse_skills(skills.data) if skills.ok else None
        parsed_queue = _parse_queue(queue.data) if queue.ok else None

        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                # Forgotten while its refresh was in flight. The commit
                # re-checks presence and drops the result: merging by
                # character id rather than replacing the roster is what
                # makes that safe, and a forgotten character must STAY
                # forgotten or forget silently does nothing.
                return ""
            if parsed_skills is not None:
                ch.active_levels, ch.trained_levels = parsed_skills
                # A 200 with no ETag header leaves the stored one alone
                # rather than clearing it -- an empty etag just means the
                # next request is unconditional, which is merely wasteful.
                ch.skills_etag = skills.etag or ch.skills_etag
            if parsed_queue is not None:
                ch.queue = parsed_queue
                ch.queue_etag = queue.etag or ch.queue_etag
            ch.fetched_utc = self._now()
            ch.error = ""
            if self._save_locked():
                return ""
            # The data is live in memory and correct; only the offline copy
            # is missing. Degraded, not failed, and the row says which.
            ch.error = MSG_SAVE_FAILED
            return MSG_SAVE_FAILED

    def _commit_failure(self, character_id: int, message: str) -> None:
        """Record the failure. The snapshot is deliberately left untouched.

        `fetched_utc` does not move here, which is the whole mechanism
        behind `stale`: last-good data plus an error. Discarding the
        snapshot would turn a transient ESI blip into apparent data loss.
        """
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return
            ch.error = message
            self._save_locked()

    def _resolve_missing_skill_ids(self) -> None:
        """Resolve plan skill names that are not yet in the id cache.

        Runs once per refresh pass, before any character is fetched: one
        unresolved name scores `Unknown` for EVERY character, so resolving
        after the fetches would leave the whole roster wrong until the next
        click.

        Failures are recorded as cache misses and nothing more. A name that
        does not resolve is a plan-authoring problem -- a typo, or a
        non-skill type -- and it already shows as `Unknown` on the row.
        """
        with self._lock:
            # `self._plans` holds only PlanFiles that parsed cleanly --
            # anything with a diagnostic became a PlanIssue instead and
            # never enters this list (see `_state_payload_locked`'s own
            # comment on that). The `ok` filter TriffSkillsController.cs
            # never needed for the same reason would be dead here too.
            names = sorted(
                {req.skill_name for plan in self._plans for req in plan.requirements}
            )
            missing = self._cache.unresolved(names)
        if not missing:
            return
        try:
            failures = self._resolve(self._cache, missing, self._client)
        except Exception:
            logger.exception("Skill id resolution failed")
            return
        if failures:
            logger.info("Unresolved skill names: %s", sorted(failures))
        with self._lock:
            try:
                skillids.save(self._cache, self._cache_path)
            except OSError:
                # The cache rebuilds completely by re-resolving names, so a
                # failed write costs requests on the next refresh and
                # nothing else.
                logger.warning("Could not save the skill id cache", exc_info=True)

    # ----- shared-authority participant --------------------------------

    def forget(self, character_id) -> bool:
        """Compatibility delegate for callers predating shared authority."""
        if isinstance(character_id, bool):
            return False
        try:
            wanted = int(character_id)
        except (TypeError, ValueError):
            return False
        if wanted <= 0:
            return False
        result = self._authority.forget(wanted)
        return result.applied

    def prepare_forget(self, character_id: int) -> MutationResult:
        """Check-only preflight; cleanup cannot start before authority saves."""
        del character_id
        with self._lock:
            return MutationResult(True, True, "")

    def authority_removed(self, character_id: int) -> None:
        """Prune derived state only after shared authority is durably absent."""
        with self._lock:
            removed = self._state.remove(character_id)
            self._authority_owners.pop(character_id, None)
            saved = not removed or self._save_locked()
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Character cleanup is incomplete",
                "Wingman removed the EVE authorisation, but could not save "
                "the Skills cleanup. It will retry at the next startup.",
            )

    def grant_invalidated(self, character_id: int) -> None:
        """Discard snapshots only when authority reports an ownership change."""
        authority = self._authority.character(character_id)
        new_owner = authority.owner_hash if authority is not None else ""
        with self._lock:
            previous_owner = self._authority_owners.get(character_id, "")
            self._authority_owners[character_id] = new_owner
            character = self._state.find(character_id)
            owner_changed = bool(
                character
                and previous_owner
                and new_owner
                and previous_owner != new_owner
            )
            saved = True
            if owner_changed:
                character.active_levels = {}
                character.trained_levels = {}
                character.queue = ()
                character.fetched_utc = None
                character.skills_etag = ""
                character.queue_etag = ""
                character.error = MSG_OWNER_CHANGED
                saved = self._save_locked()
        self._push_state(force=True)
        if not saved:
            self._alert(
                "warning",
                "Skills cleanup is not saved",
                "The character ownership changed, but the cleared Skills "
                "snapshot could not be saved. Wingman will retry cleanup "
                "at the next startup.",
            )

    def reconcile_characters(self, characters) -> None:
        """Make the Skills roster the derived projection of shared authority."""
        wanted = {character.character_id: character for character in characters}
        with self._lock:
            first_reconciliation = not self._reconciled_once
            self._reconciled_once = True
            existing = {character.character_id for character in self._state.characters}
            removed = existing - wanted.keys()
            added = wanted.keys() - existing
            if removed:
                self._state.characters = [
                    character
                    for character in self._state.characters
                    if character.character_id in wanted
                ]
            for character_id in added:
                self._state.upsert(state_mod.Character(character_id=character_id))
            self._authority_owners = {
                character_id: character.owner_hash
                for character_id, character in wanted.items()
            }
            changed = bool(removed or added)
            saved = not changed or self._save_locked()
        if changed and not first_reconciliation:
            self._push_state(force=True)
        if not saved:
            warning = (
                "Shared EVE characters are available for this session, but the "
                "Skills roster reconciliation could not be saved."
            )
            if first_reconciliation:
                # The page does not exist yet, so an alert would be dropped.
                # Keep this in the route payload beside migration warnings.
                with self._lock:
                    self._load_warnings.insert(0, warning)
            else:
                self._alert("warning", "Skills roster not saved", warning)
        if not first_reconciliation:
            # Preserve the existing sign-in behavior for both new characters
            # and reauthentication: every successful consent flow refreshes
            # Skills instead of leaving the row stale until another click.
            self.refresh_characters()

    # ----- interactive sign-in --------------------------------------------

    def authenticate(self) -> None:
        """Compatibility delegate; the bridge calls authority directly."""
        self._authority.authenticate_skills()

    def cancel_auth(self) -> None:
        """Compatibility delegate; the bridge calls authority directly."""
        self._authority.cancel_auth()

    # ----- detail -----------------------------------------------------

    def plan_text(self, plan_name) -> str:
        """One plan's requirements as plan-file text, or "" if it is gone.

        S7: the maintainer's answer to "what do you end up doing twice" was
        retyping a character's missing skills into EVE. They also supplied
        the cheap version -- the WHOLE plan is enough, because EVE drops
        already-trained skills on import -- so this needs no character and
        no evaluation, only the plan.

        A read, and deliberately not a payload key: the plan list is pushed
        on every mutation and is already the largest payload in the app.
        Carrying every requirement of every plan there would multiply it to
        serve a button that is pressed rarely, and character_detail's own
        docstring makes the same argument one level down.

        The formatting is plans.format_lines -- the grammar module that
        parses these files also writes them, so the text this puts on the
        clipboard is text this app would read back.
        """
        with self._lock:
            plan = self._find_plan_locked(str(plan_name or ""))
            if plan is None:
                return ""
            requirements = plan.requirements
        # Formatting outside the lock: it is pure, and the lock is held by
        # refresh workers committing snapshots.
        return plans.format_lines(requirements)

    def character_detail(self, character_id, plan_name) -> dict:
        """Re-evaluate one character against one plan, in full.

        Computed on demand rather than carried in the roster payload:
        forty characters times fifty requirements is two thousand rows the
        page would receive on every push to render at most one of.
        """
        name = str(plan_name or "")
        try:
            wanted = int(character_id)
        except (TypeError, ValueError):
            return _detail_error(0, name, "Unknown character.")

        with self._lock:
            ch = self._state.find(wanted)
            if ch is None:
                return _detail_error(
                    wanted, name, "That character is no longer in the roster."
                )
            plan = self._find_plan_locked(name)
            if plan is None:
                # Covers both "no such plan file" and "the file exists but
                # failed to parse" -- planstore.list_plans excludes a
                # rejected file from self._plans entirely and reports it as
                # a PlanIssue instead, so a PlanFile reachable from
                # _find_plan_locked is `ok` by construction. There is no
                # second, reachable branch here for "the plan has errors".
                return _detail_error(
                    wanted, name, "That plan is no longer available. Reload plans."
                )
            analysis = evaluator.evaluate(
                plan.requirements,
                self._cache.type_ids(),
                ch.active_levels,
                ch.trained_levels,
                ch.queue,
                ch.has_snapshot,
            )

        return {
            "ok": True,
            "message": "",
            "character_id": wanted,
            "plan_name": plan.name,
            "readiness": analysis.readiness,
            "estimated_finish_utc": _iso(analysis.estimated_finish_utc),
            "queue_timing_unknown": bool(analysis.queue_timing_unknown),
            # Active requirements are INCLUDED. The page filters them out of
            # the expanded row, which is a display decision; filtering here
            # would make the payload lie about what the plan requires.
            "requirements": [
                {
                    "skill_name": req.skill_name,
                    "required_level": req.required_level,
                    # Plain ints across the bridge: the page compares these
                    # arithmetically, and `null > 3` is quietly false in
                    # JavaScript rather than an error.
                    #
                    # This collapses None into 0 -- a deliberate, LOSSY
                    # collapse. None means the skill NAME never resolved
                    # (unrecognised by the type cache); 0 means it resolved
                    # but was never trained. Those are different facts
                    # (SkillPlanEvaluator.cs:73,77-78 passes null for the
                    # former and 0 for the latter, and that distinction
                    # survives all the way through evaluator.py). `state`
                    # is what still carries it on this side of the bridge:
                    # `state == "Unknown"` means the name did not resolve.
                    # Anything that renders active_level/trained_level
                    # (e.g. a future "Active n / Trained n" column) must
                    # check state first -- 0 is not a meaningful count when
                    # state is Unknown.
                    "active_level": int(req.active_level or 0),
                    "trained_level": int(req.trained_level or 0),
                    "state": req.state,
                    "queued_finish_utc": _iso(req.queued_finish_utc),
                    "queue_timing_unknown": bool(req.queue_timing_unknown),
                }
                for req in analysis.requirements
            ],
        }

    # ----- shutdown -----------------------------------------------------

    def shutdown(self) -> None:
        """Stop feature workers before shared authority is torn down."""
        self._stopping.set()
