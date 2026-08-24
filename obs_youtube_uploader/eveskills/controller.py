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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import application, evaluator, planstore, skillids, tokens
from . import esi as esi_mod
from . import sso as sso_mod
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
MSG_TOKEN_UNREADABLE = (
    "The stored authorisation could not be decrypted. Re-authenticate this character.")
MSG_SAVE_FAILED = "Fresh data is in memory but was not saved for offline use."
MSG_OWNER_CHANGED = "Character ownership changed; cached skill data was cleared."

# An access token is refreshed when it expires within this many seconds. The
# window has to cover the round trip that is about to use it, or a token that
# was valid when checked is rejected when sent.
TOKEN_EXPIRY_MARGIN_S = 30


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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
        entries.append(evaluator.QueueEntry(
            skill_id=skill_id,
            finished_level=max(1, min(5, finished_level)),
            start_date=_parse_date(row.get("start_date")),
            finish_date=_parse_date(row.get("finish_date")),
            queue_position=_clamp_position(row.get("queue_position"))))
    return tuple(entries)


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

        # Single-flight latch. `_refresh_again` is the *request* that arrived
        # while a pass was running; the worker re-enters on it rather than
        # dropping it, so a click during a refresh is never silently lost.
        self._refresh_in_flight = False
        self._refresh_again = False
        # character_id -> (access_token, expires_at). Memory only, and
        # deliberately so: an access token lives twenty minutes and writing
        # one to disk would widen what a stolen state file is worth.
        self._access_tokens: dict[int, tuple[str, datetime]] = {}
        # Set on shutdown so a refresh pass stops between characters rather
        # than finishing eighty requests after the window has gone.
        self._stopping = threading.Event()
        # Task 14 drives this; a real flag now so the payload does not lie.
        self._auth_in_progress = False
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
            "auth_in_progress": self._auth_in_progress,
            "refresh_in_flight": self._refresh_in_flight,
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
        self._push_state(force=True)     # The button becomes "Refreshing...".
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
                self._refresh_in_flight = False
                self._refresh_again = False
        finally:
            # Unconditional: the page's "Refreshing..." state is driven by
            # refresh_in_flight, and a pass that died without this push
            # leaves the button stuck forever.
            self._push_state(force=True)

    def _refresh_pass(self) -> None:
        with self._lock:
            targets = [(ch.character_id, ch.character_name)
                       for ch in self._state.characters]
        self._resolve_missing_skill_ids()
        total = len(targets)
        for index, (character_id, name) in enumerate(targets, start=1):
            if self._stopping.is_set():
                return
            error = self._refresh_one(character_id)
            self._push_cb("onSkillsProgress",
                          {"character_id": character_id,
                           "character_name": name,
                           "completed": index, "total": total,
                           "error": error})
            # Not forced: an all-304 pass changes only fetched_utc, and the
            # dedupe is what keeps a no-change refresh from rebuilding the
            # roster once per character.
            self._push_state()

    def _refresh_one(self, character_id: int) -> str:
        """Refresh one character. Returns "" on success, else the message."""
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return ""      # Forgotten between the snapshot and here.
            skills_etag, queue_etag = ch.skills_etag, ch.queue_etag

        skills, error, definitive = self._authorised_get(
            character_id, _skills_path(character_id), skills_etag)
        if skills is None:
            # Short-circuit, ported verbatim: the queue result could not be
            # committed on its own anyway, so spending the second request
            # would only burn error-limit budget to throw the answer away.
            self._commit_failure(character_id, error, definitive)
            return error

        queue, error, definitive = self._authorised_get(
            character_id, _queue_path(character_id), queue_etag)
        if queue is None:
            self._commit_failure(character_id, error, definitive)
            return error

        return self._commit_success(character_id, skills, queue)

    def _access_token(self, character_id: int, *, rejected=None):
        """(access_token, error, definitive) for one character.

        Refreshed when absent, when it expires within TOKEN_EXPIRY_MARGIN_S,
        or when a caller forces it AND the cached token is still the one ESI
        just rejected. That last clause is the stampede fix: N concurrent
        401s from one stale token produce exactly one refresh, because every
        caller after the first finds a cached token that no longer matches
        what it was handed.
        """
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return None, "", False
            blob = ch.refresh_token_blob
            cached = self._access_tokens.get(character_id)

        now = self._now()
        if cached is not None:
            token, expires_at = cached
            fresh = (expires_at - now).total_seconds() > TOKEN_EXPIRY_MARGIN_S
            if fresh and (rejected is None or token != rejected):
                return token, "", False

        if not blob:
            # Definitive: no amount of retrying invents a refresh token.
            return None, MSG_NO_TOKEN, True
        refresh = tokens.unwrap(blob)
        if refresh is None:
            # A DPAPI blob that will not decrypt costs this one character a
            # re-authentication, which is exactly why only the token is
            # wrapped and the roster metadata beside it is not.
            return None, MSG_TOKEN_UNREADABLE, True

        try:
            token_set = self._sso_module().refresh_token(refresh)
        except sso_mod.OAuthError as exc:
            # `definitive` is the OAuth error's own classification --
            # invalid_grant, identity_mismatch, owner_changed. Everything
            # else is transient and must not delete the stored token.
            return None, (MSG_REAUTH if exc.definitive
                          else f"EVE SSO refused the token refresh: {exc}"), \
                exc.definitive
        except Exception as exc:
            # Network, DNS, TLS. Transient by definition: last-good data
            # stays visible and the row is merely stale.
            logger.warning("Token refresh failed", exc_info=True)
            return None, f"Could not reach EVE SSO: {exc}", False

        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return None, "", False
            # EVE rotates the refresh token on every use, so the new one is
            # stored before it is used. Losing this write means the NEXT
            # launch cannot authenticate at all, with nothing on screen to
            # explain why.
            #
            # EVE sometimes omits the refresh token on a response (it means
            # "the previous one is still valid"), and sso.refresh_token
            # reports that as "" rather than distinguishing "omitted" from
            # "empty" -- it can't, EveSso.cs does not either at that layer.
            # tokens.wrap("") returns "", the no-token sentinel, so writing
            # it unconditionally would overwrite a valid stored credential
            # with the empty-blob sentinel: the character looks authorised
            # until the NEXT refresh, which then fails for good with
            # nothing on screen explaining why. Only overwrite when EVE
            # actually sent a new one; otherwise the previously stored blob
            # is still correct and is left alone.
            if token_set.refresh_token:
                ch.refresh_token_blob = tokens.wrap(token_set.refresh_token)
            self._access_tokens[character_id] = (
                token_set.access_token,
                now + timedelta(seconds=max(0, int(token_set.expires_in))))
            self._save_locked()
        return token_set.access_token, "", False

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
            token, error, definitive = self._access_token(character_id,
                                                          rejected=token)
            if token is None:
                return None, error, definitive
            response = self._client.get(path, token=token, etag=etag or None)
            if response.status == 401:
                return None, MSG_REAUTH, True

        if response.status == 403:
            # Definitive: the grant exists but no longer carries the scope,
            # which only a fresh consent screen can fix.
            return None, MSG_REAUTH, True
        if not (response.ok or response.not_modified):
            # Includes esi.py's synthetic 503 for retry exhaustion, which
            # did not necessarily come from ESI -- transient either way.
            return None, f"ESI request failed ({response.status}): {response.error}", False
        return response, "", False

    def _sso_module(self):
        """The SSO seam, resolved once. Injected whole in tests."""
        if self._sso is None:
            self._sso = sso_mod
        return self._sso

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
            ch.needs_reauth = False
            if self._save_locked():
                return ""
            # The data is live in memory and correct; only the offline copy
            # is missing. Degraded, not failed, and the row says which.
            ch.error = MSG_SAVE_FAILED
            return MSG_SAVE_FAILED

    def _commit_failure(self, character_id: int, message: str,
                        definitive: bool) -> None:
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
            if definitive:
                ch.needs_reauth = True
                # The stored grant cannot work again, so it is deleted
                # rather than retried on every future refresh -- and the row
                # shows a re-authenticate banner instead of an error that
                # never clears.
                ch.refresh_token_blob = ""
                self._access_tokens.pop(character_id, None)
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
            names = sorted({req.skill_name for plan in self._plans
                            for req in plan.requirements})
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
