"""Roster, skill snapshots, ETags, and wrapped refresh tokens in one file.

One document holds everything about a character, which is what makes forget
a single atomic write: there is no window in which a token exists without
its character, and no reconciliation sweep to get wrong. TriffView splits
these across Credential Manager and state.json and pays for it in rollback
paths (TriffSkillsAuthentication.cs:103,108) and a RecoverOwnCredentials()
that exists only to resurrect orphans.

Only the refresh token is wrapped. The metadata beside it stays plaintext so
a blob that will not decrypt costs one character a re-authentication rather
than making the whole document unparseable.

Normalisation on load is deliberately tolerant rather than versioned, which
is the same posture settings.py's validated_*() functions take and the
reason preview/layout.py:26-32 gives: a partially-written or hand-edited
file should cost one row, not the launch.
"""
import json
import os
import stat as stat_module
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import atomicio
from .evaluator import QueueEntry

MAX_CHARACTERS = 50
STATE_VERSION = 1

# TriffSkillsState.cs:79's MaxStateFileBytes, read via ReadBoundedText
# before either the primary or the backup document is ever decoded. Same
# shape as planstore.py's MAX_PLAN_FILE_BYTES: a size check against the
# file on disk, before its bytes are pulled into memory, so a multi-
# gigabyte state.json (bug or hostile drop-in -- this file is user-
# writable state, not a code path we control end to end) cannot cost more
# than a stat() call.
MAX_STATE_FILE_BYTES = 16 * 1024 * 1024

# Caps on the two unbounded per-character collections. A real character has
# a few hundred skills; 20,000 is far above anything EVE can produce and far
# below anything that would make the JSON load hurt.
MAX_LEVEL_ENTRIES = 20_000
# ESI's own skill queue tops out around 50 entries. 500 is headroom, not a
# guess at the real ceiling.
MAX_QUEUE_ENTRIES = 500
# TriffSkillsState.cs:198-199's MaxSelectedPlanNameLength -- shared with
# planstore.MAX_PLAN_NAME_CHARS in value only; kept as its own constant
# because the two bound different things (a plan file's own name vs. a
# pointer to one stored here) that happen to agree today.
MAX_SELECTED_PLAN_NAME_CHARS = 120


@dataclass
class Character:
    character_id: int
    character_name: str = ""
    owner_hash: str = ""
    scopes: tuple = ()
    authenticated_utc: "datetime | None" = None
    fetched_utc: "datetime | None" = None
    active_levels: dict = field(default_factory=dict)
    trained_levels: dict = field(default_factory=dict)
    queue: tuple = ()
    error: str = ""
    needs_reauth: bool = False
    # base64 text of the DPAPI blob; "" when the token is absent or was
    # deleted by a definitive auth failure.
    refresh_token_blob: str = ""
    # Per-endpoint ETags. These are request optimisation ONLY -- they are
    # not freshness state. fetched_utc is the single freshness fact, and it
    # means "both halves were confirmed current at this time".
    skills_etag: str = ""
    queue_etag: str = ""

    @property
    def has_snapshot(self) -> bool:
        return self.fetched_utc is not None

    @property
    def stale(self) -> bool:
        # The conjunction is the whole meaning: an error with no prior data
        # is a character that never loaded, not one showing stale data.
        return self.has_snapshot and bool(self.error)


@dataclass
class SkillsState:
    characters: list = field(default_factory=list)
    selected_plan_name: str = ""

    def find(self, character_id: int):
        for character in self.characters:
            if character.character_id == character_id:
                return character
        return None

    def upsert(self, character: Character) -> None:
        # Replace in place rather than remove-then-append: the roster order
        # is what the page renders inside each readiness group, and a
        # refresh must not reshuffle rows under the user's cursor.
        for index, existing in enumerate(self.characters):
            if existing.character_id == character.character_id:
                self.characters[index] = character
                return
        # TriffSkillsState.cs:212 throws at MaxCharacters. Only a NEW
        # character is refused here -- the loop above already returned for
        # an update to an existing id, so capacity is checked against
        # rows that would actually grow the roster.
        if len(self.characters) >= MAX_CHARACTERS:
            raise ValueError(
                f"TriffSkills supports up to {MAX_CHARACTERS} characters.")
        self.characters.append(character)

    def remove(self, character_id: int) -> bool:
        for index, existing in enumerate(self.characters):
            if existing.character_id == character_id:
                del self.characters[index]
                return True
        return False


def _iso(value) -> str:
    """UTC ISO 8601, or "" for absent. Never None, so the JSON has one
    shape for a field whether or not it is set."""
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(raw):
    """Parse an ISO 8601 string to an aware UTC datetime, or None.

    A naive value is read as UTC rather than local: everything this package
    writes is UTC, so a naive string can only be a hand edit, and reading it
    as local time would shift an ETA by the machine's offset. Python 3.11's
    fromisoformat accepts a trailing "Z"; the repo floor is 3.11, so no
    manual substitution is needed.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_int(raw):
    # bool is an int subclass, so JSON `true` would otherwise become 1 --
    # a skill id of 1 or a level of 1 that nothing in the file asked for.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _coerce_levels(raw) -> dict:
    """Skill id -> level, dropping malformed entries individually.

    Individually is the point: one unparseable id must cost that skill, not
    the character's whole snapshot. Dropping the snapshot would silently
    turn the character Unscored with no visible reason.

    0 is a legitimate level (a resolved-but-untrained skill), a different
    fact from a skill whose name never resolved (absent entirely) -- so the
    bound below is `0 <= level`, not `0 < level`. Filtering zeros out would
    erase that distinction the evaluator depends on.
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if len(out) >= MAX_LEVEL_ENTRIES:
            break
        skill_id = _coerce_int(key)
        level = _coerce_int(value)
        if skill_id is None or level is None:
            continue
        if skill_id <= 0 or not 0 <= level <= 5:
            continue
        out[skill_id] = level
    return out


def _coerce_queue(raw) -> tuple:
    """Queue entries, validated per entry and re-sorted by position.

    The stored order is not trusted: queue_position is the tie-break
    lowest_sufficient_entry depends on, and a hand-edited file can list the
    entries in any order at all. The cap is applied to accepted entries as
    they are read, before the sort -- a truncated 5,000-entry file should
    stop costing time immediately, not after parsing all of it.
    """
    if not isinstance(raw, list):
        return ()
    entries = []
    for item in raw:
        if len(entries) >= MAX_QUEUE_ENTRIES:
            break
        if not isinstance(item, dict):
            continue
        skill_id = _coerce_int(item.get("skill_id"))
        finished_level = _coerce_int(item.get("finished_level"))
        if skill_id is None or finished_level is None:
            continue
        if skill_id <= 0 or not 1 <= finished_level <= 5:
            continue
        position = _coerce_int(item.get("queue_position"))
        entries.append(QueueEntry(
            skill_id=skill_id,
            finished_level=finished_level,
            start_date=_parse_utc(item.get("start_date")),
            finish_date=_parse_utc(item.get("finish_date")),
            queue_position=len(entries) if position is None else position))
    entries.sort(key=lambda entry: entry.queue_position)
    return tuple(entries)


# TriffSkillsState.cs:159's `.Take(100)` on Scopes -- the one collection in
# the source that gets its own cap distinct from MAX_LEVEL_ENTRIES/
# MAX_QUEUE_ENTRIES, so it needs its own constant rather than reusing one
# of those. A real ESI grant is a handful of scope strings; 100 is
# headroom against a hand-edited file, not a real ceiling.
MAX_SCOPES = 100


def _coerce_scopes(raw) -> tuple:
    if not isinstance(raw, list):
        return ()
    out = []
    for item in raw:
        if len(out) >= MAX_SCOPES:
            break
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return tuple(out)


def _coerce_text(raw) -> str:
    return raw if isinstance(raw, str) else ""


def _coerce_trimmed_text(raw) -> str:
    """TriffSkillsState.cs:157-158,163 trims CharacterName, OwnerHash and
    Error. Used only for those three fields -- the token blob and the two
    ETags are opaque values, not display text, and trimming them would
    silently corrupt a blob or ETag that happened to start or end with
    whitespace-looking bytes."""
    return _coerce_text(raw).strip()


def _coerce_selected_plan_name(raw) -> str:
    """TriffSkillsState.cs:198-199: cleared, not truncated, beyond the cap.

    Truncating would silently point selected_plan_name at a DIFFERENT
    plan file (or none) on the next load -- a name is either the exact
    stem the user picked or it is not a usable pointer at all, so a name
    too long to be a real plan file (validate_plan_name in planstore.py
    rejects the same length) is dropped outright rather than mangled into
    something that happens to still parse.

    Trimmed BEFORE the length check (TriffSkillsState.cs:198's .Trim()
    precedes its length check on the same line) so a value that is only
    over the cap because of padding whitespace is kept rather than
    needlessly cleared.
    """
    text = _coerce_text(raw).strip()
    if len(text) > MAX_SELECTED_PLAN_NAME_CHARS:
        return ""
    return text


def to_dict(state: SkillsState) -> dict:
    return {
        "version": STATE_VERSION,
        "selected_plan_name": state.selected_plan_name,
        "characters": [{
            "character_id": character.character_id,
            "character_name": character.character_name,
            "owner_hash": character.owner_hash,
            "scopes": list(character.scopes),
            "authenticated_utc": _iso(character.authenticated_utc),
            "fetched_utc": _iso(character.fetched_utc),
            # JSON object keys are strings; from_dict coerces them back.
            "active_levels": {str(k): v
                              for k, v in character.active_levels.items()},
            "trained_levels": {str(k): v
                               for k, v in character.trained_levels.items()},
            "queue": [{
                "skill_id": entry.skill_id,
                "finished_level": entry.finished_level,
                "start_date": _iso(entry.start_date),
                "finish_date": _iso(entry.finish_date),
                "queue_position": entry.queue_position,
            } for entry in character.queue],
            "error": character.error,
            "needs_reauth": character.needs_reauth,
            "refresh_token_blob": character.refresh_token_blob,
            "skills_etag": character.skills_etag,
            "queue_etag": character.queue_etag,
        } for character in state.characters],
    }


def from_dict(raw: object) -> SkillsState:
    """Rebuild a roster, dropping anything malformed. Never raises.

    This runs at launch, so the only acceptable failure is a smaller roster
    plus a warning. The version field is written but deliberately not
    checked: tolerant normalisation already handles a document from a
    different shape better than a hard version gate would, which is the
    same trade settings.py makes.
    """
    result = SkillsState()
    if not isinstance(raw, dict):
        return result
    result.selected_plan_name = _coerce_selected_plan_name(
        raw.get("selected_plan_name"))

    characters = raw.get("characters")
    if not isinstance(characters, list):
        return result

    # Full scan, not truncated to some multiple of MAX_CHARACTERS before
    # dedup: a later row for an id must be able to win over an earlier one
    # no matter how far apart they sit in the file. by_id is a plain dict
    # assignment, which mirrors TriffSkillsState.cs:164's
    # `deduped[character.CharacterId] = character` exactly -- the LAST
    # occurrence's data wins, while the key's position in iteration order
    # stays wherever it was FIRST inserted (a property both C# Dictionary
    # and Python dict share). The final cap is applied afterwards, to the
    # deduped result, not to the raw scan.
    by_id: dict = {}
    for item in characters:
        if not isinstance(item, dict):
            continue
        character_id = _coerce_int(item.get("character_id"))
        # A row with no reachable id would be unreachable: find() and
        # upsert() both key on character_id, so a 0 or negative one can
        # never be refreshed and never be forgotten.
        if character_id is None or character_id <= 0:
            continue
        by_id[character_id] = Character(
            character_id=character_id,
            character_name=_coerce_trimmed_text(item.get("character_name")),
            owner_hash=_coerce_trimmed_text(item.get("owner_hash")),
            scopes=_coerce_scopes(item.get("scopes")),
            authenticated_utc=_parse_utc(item.get("authenticated_utc")),
            fetched_utc=_parse_utc(item.get("fetched_utc")),
            active_levels=_coerce_levels(item.get("active_levels")),
            trained_levels=_coerce_levels(item.get("trained_levels")),
            queue=_coerce_queue(item.get("queue")),
            error=_coerce_trimmed_text(item.get("error")),
            needs_reauth=item.get("needs_reauth") is True,
            refresh_token_blob=_coerce_text(item.get("refresh_token_blob")),
            skills_etag=_coerce_text(item.get("skills_etag")),
            queue_etag=_coerce_text(item.get("queue_etag")))
    result.characters = list(by_id.values())[:MAX_CHARACTERS]
    return result


def _read_bounded(path: Path) -> str:
    """Read *path* as UTF-8 text, refusing anything over MAX_STATE_FILE_BYTES.

    Sized BEFORE the bytes are read into memory -- TriffSkillsState.cs:79
    via AtomicFile.ReadBoundedText, and the same shape planstore.py's
    MAX_PLAN_FILE_BYTES check uses. Without this, a state.json grown huge
    by a bug (or a hostile file dropped where the app expects its own
    state) would be pulled entirely into memory before json.loads ever got
    a chance to reject it. Raises OSError/ValueError the same way
    path.read_text() would, so callers do not need a third exception shape.
    """
    if path.stat().st_size > MAX_STATE_FILE_BYTES:
        raise ValueError(
            f"{path.name} exceeds the "
            f"{MAX_STATE_FILE_BYTES // (1024 * 1024)} MiB limit.")
    return path.read_text(encoding="utf-8")


def _preserve_corrupt(path: Path) -> str:
    """Move an unreadable document aside, returning its new name or "".

    Moved, not copied: left in place it would be re-read, re-preserved and
    re-warned on every launch, and the user would accumulate one .corrupt-
    file per start with no way to tell which one mattered.

    Millisecond resolution (matching AtomicFile.PreserveCorrupt's
    "yyyyMMdd-HHmmssfff") rather than seconds: two corruptions inside the
    same wall-clock second -- plausible under a fast test suite, and not
    impossible in the field if a crash loop hits this path repeatedly --
    would otherwise share a filename, and os.replace onto an existing
    .corrupt- name would silently overwrite the earlier preserved copy
    before anyone could look at it.

    Millisecond precision still leaves a real, if narrow, chance of two
    corruptions landing in the same millisecond, so a numeric suffix is
    appended on top whenever the timestamped name is already taken --
    the actual uniqueness guarantee, with the millisecond stamp doing the
    practical work of keeping that loop to at most one or two iterations.
    """
    stamp = (time.strftime("%Y%m%d-%H%M%S")
             + f"{int(time.time() * 1000) % 1000:03d}")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    suffix = 0
    while target.exists():
        suffix += 1
        target = path.with_name(f"{path.name}.corrupt-{stamp}-{suffix}")
    try:
        os.replace(path, target)
    except OSError:
        return ""
    return target.name


def load(path: Path) -> tuple:
    """Read the roster. Returns (state, warnings) and never raises.

    A warning here reaches the UI notices strip, so it is written for the
    person reading it rather than for a log.
    """
    path = Path(path)
    warnings: list = []
    try:
        text = _read_bounded(path)
    except FileNotFoundError:
        # No primary. Usually first launch -- but save()'s rotate-then-swap
        # can also leave exactly this on disk if the process dies or the
        # final os.replace(staging, path) fails between rotating the old
        # primary into *.bak* and installing the new one: at that instant
        # there is a *.bak* but no primary. A *.bak* on disk is therefore
        # the one thing that tells the two apart -- first launch never has
        # one, so its absence is what makes this branch safe to treat as
        # silent.
        backup = path.with_name(path.name + ".bak")
        if not backup.exists():
            return SkillsState(), warnings
        return _recover_missing_primary(path, backup, warnings)
    except UnicodeDecodeError:
        # A bad UTF-8 decode is unreadable CONTENT, not an access failure --
        # TriffSkillsState.cs:104 groups this with JsonException and its own
        # size-cap exception under one catch, all three routed through
        # preserve-then-recover-from-backup. Handled here, before the
        # OSError branch below, because UnicodeDecodeError is a ValueError,
        # not an OSError, and would otherwise fall through to json.loads
        # with `text` never assigned.
        return _recover_from_backup(path, warnings)
    except OSError as exc:
        # A genuine access failure (permission denied, disk error) rather
        # than bad content -- TriffSkillsState.cs's other catch clause,
        # `IsFileFailure`. There is nothing to preserve or recover here:
        # if the file cannot even be opened, neither can its .bak sibling
        # for the same reason, and attempting os.replace() on a file we
        # just failed to read would likely fail identically.
        warnings.append(f"{path.name} could not be read ({exc.strerror}); "
                        "starting with an empty roster.")
        return SkillsState(), warnings
    except ValueError:
        # _read_bounded's own size-cap check. TriffSkillsState.cs:104 groups
        # this (InvalidDataException, ReadBoundedText's own overflow) with
        # JsonException under the SAME catch as corrupt content: an
        # oversized file is exactly as recoverable-from-backup as a
        # syntactically broken one, and treating it as a plain access
        # failure (the previous shape of this branch) meant an oversized
        # primary discarded the whole roster even with a good .bak sitting
        # right beside it, and never got moved aside -- so it was re-read,
        # re-rejected, and re-warned about on every single launch forever.
        return _recover_from_backup(path, warnings)

    try:
        # json.JSONDecodeError is a ValueError; UnicodeDecodeError from
        # decoding text (as opposed to the read above) is handled the same
        # way here too, for the same reason: bad content, not bad access.
        return from_dict(json.loads(text)), warnings
    except ValueError:
        return _recover_from_backup(path, warnings)


def _recover_missing_primary(path: Path, backup: Path, warnings: list) -> tuple:
    """The primary is gone but `.bak` is not: rebuild from it and restore
    the primary, then warn.

    This is a distinct case from `_recover_from_backup` -- there is no
    corrupt primary to preserve, because there is no primary at all. It
    exists because save()'s rotate-then-swap has no rollback: it renames
    the old primary to `.bak` and only then renames the new content into
    place, and a failure or a hard kill between those two renames leaves
    the directory holding a `.bak` and a `.new` staging file but no
    `eve_skills.json`. Without this, the next load() would take the
    FileNotFoundError branch, believe it is a first launch, and hand back
    an empty roster with every DPAPI-wrapped refresh token silently gone
    from view -- while a perfectly good `.bak` sits right beside it.
    """
    recovered = None
    for attempt in range(2):
        try:
            recovered = from_dict(json.loads(_read_bounded(backup)))
            break
        except ValueError:
            # The backup's own content is bad -- permanent, retrying reads
            # the same bytes again.
            break
        except OSError:
            # A transient sharing violation on a GOOD backup, not a missing
            # or genuinely unreadable one -- matching _recover_from_backup's
            # own retry for the identical reason.
            if attempt == 0:
                time.sleep(0.05)

    if recovered is None:
        warnings.append(
            f"{path.name} was missing and its backup ({backup.name}) could "
            "not be read either; starting with an empty roster. Any "
            "characters you had added will need re-authorising.")
        return SkillsState(), warnings

    # Write the recovered document back to *path* immediately. save() sees
    # no existing primary (there isn't one) so it will not touch `.bak` --
    # it only rotates a primary that exists -- and the directory ends up
    # holding a real primary again, backed by the same `.bak` it came from.
    try:
        save(recovered, path)
    except OSError as exc:
        warnings.append(
            f"{path.name} was missing; recovered it from {backup.name}, but "
            f"the recovery could not be saved back to disk ({exc}). If the "
            "app closes before the next successful save, this recovery "
            "will be lost.")
        return recovered, warnings

    warnings.append(
        f"{path.name} was missing (likely an interrupted save) and was "
        f"recovered from its backup, {backup.name}.")
    return recovered, warnings


def _recover_from_backup(path: Path, warnings: list) -> tuple:
    """The corrupt-content path shared by every unreadable-CONTENT case in
    load(): move the bad primary aside, then try to rebuild from `.bak`.

    Split out because three distinct failures upstream -- a JSON syntax
    error, a size-cap overflow, and a bad UTF-8 decode -- all mean exactly
    the same thing here: TriffSkillsState.cs:104 catches all three in one
    clause for the same reason.
    """
    preserved = _preserve_corrupt(path)
    backup = path.with_name(path.name + ".bak")
    recovered = None
    for attempt in range(2):
        try:
            recovered = from_dict(json.loads(_read_bounded(backup)))
            break
        except ValueError:
            # The backup's own content is bad (missing, not JSON, or over
            # the size cap). That is permanent -- retrying reads the same
            # bytes again -- so this is the genuine "no usable backup" case.
            break
        except OSError:
            # A transient sharing violation on a GOOD backup (a Windows
            # antivirus scan, a backup tool with the file briefly open) must
            # not be treated the same as a missing or genuinely unreadable
            # one. The single broad `except (OSError, ValueError)` this
            # replaced discarded a perfectly good .bak over a hiccup that a
            # moment's wait resolves, so OSError alone gets one retry before
            # giving up.
            if attempt == 0:
                time.sleep(0.05)
    if recovered is None:
        warnings.append(
            f"{path.name} could not be read and was preserved as "
            f"{preserved or 'a copy'}; starting with an empty roster. "
            "Any characters you had added will need re-authorising.")
        return SkillsState(), warnings

    if not preserved:
        # _preserve_corrupt's own os.replace failed, so the corrupt content
        # is STILL sitting at *path* -- it was never moved aside. Calling
        # save() here regardless would still see that corrupt file as the
        # current primary and rotate it into *backup* as save()'s own
        # second step, overwriting the good backup this very recovery just
        # read `recovered` from with the corrupt content it was recovering
        # FROM. Write-then-rotate (below) fixes the ordering bug where a
        # write failure could destroy a good backup; it does not fix this
        # one, because here the rotate step's SOURCE is already corrupt
        # before save() is ever called. The corrupt primary on disk is by
        # definition worse than the good backup `recovered` came from, so
        # the safest thing is to do nothing to either file: hand back the
        # recovered roster in memory and leave both exactly as they are.
        warnings.append(
            f"Recovered {path.name} from backup after the main file could "
            "not be read, but the corrupt file could not be moved aside "
            "and was left in place; the recovery could not be saved back "
            "to disk. If the app closes before the next successful save, "
            "this recovery will be lost.")
        return recovered, warnings

    # TriffSkillsState.cs:118-119: write the recovered document back to
    # *path* immediately, before returning. _preserve_corrupt already moved
    # the corrupt primary out of the way, so at this instant there is no
    # primary file at all -- if the process exits before the next save(),
    # the NEXT load() would find nothing at `path`, take the silent
    # first-launch branch above, and hand back an empty roster with no
    # warning shown. Re-persisting here closes that window: the primary
    # exists again as soon as recovery succeeds, backed by its own .bak.
    #
    # Wrapped in its own try: write_atomic can raise OSError (disk full,
    # permissions, or its own Windows sharing-violation retries exhausted),
    # and load()'s contract is that it never raises -- least of all here,
    # while the app is already in its worst state and recovering from
    # corruption. A failed write-back still returns the recovered roster
    # in memory; the roster is simply not durable until the next save().
    try:
        save(recovered, path)
    except OSError as exc:
        warnings.append(
            f"Recovered {path.name} from backup after the main file could "
            f"not be read, but the recovery could not be saved back to "
            f"disk ({exc}); it was preserved as {preserved or 'a copy'}. "
            "If the app closes before the next successful save, this "
            "recovery will be lost.")
        return recovered, warnings

    warnings.append(
        f"Recovered {path.name} from backup after the main file could not "
        f"be read; it was preserved as {preserved or 'a copy'}. Anything "
        "saved since the previous write is gone.")
    return recovered, warnings


def save(state: SkillsState, path: Path) -> None:
    """Write the roster atomically, keeping one previous copy.

    Write-then-rotate, not rotate-then-write: the new content is written to
    a staging file and confirmed durable BEFORE anything happens to the
    existing primary or its .bak. The previous shape copied the current
    primary to .bak first and only then wrote the new content -- so a
    primary that was itself corrupt (exactly the case _recover_from_backup
    calls this from) got copied over a good .bak an instant before the new
    write was known to succeed, destroying the one good copy on a write
    failure. Here, if anything fails before the final swap, the existing
    primary and its .bak are untouched.

    The .bak tier does NOT extend atomicio.py, deliberately. write_atomic
    makes no backup because it is shared with the Wingman/engine boundary,
    where a stray .bak sitting beside a polled INI would be its own problem
    -- the engine reads that directory. The rotation here is a few lines and
    only this subsystem wants it, because this is the only file holding
    something (the refresh tokens) that a refresh cannot rebuild.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_name(path.name + ".bak")
    staging = path.with_name(path.name + ".new")
    # Written and confirmed durable first. atomicio.write_atomic's own
    # mkstemp+fsync+rename gives *staging* the same durability guarantees a
    # direct write to *path* would have; only once this succeeds is the
    # existing primary touched at all.
    atomicio.write_atomic(staging, json.dumps(to_dict(state), indent=2))
    if path.exists():
        try:
            # Rename, not copy: os.replace carries the source file's own
            # mode across unchanged (it is the same inode under a new
            # name), matching what shutil.copy2 gave the old copy-then-write
            # shape -- and it only runs now, after the new content is
            # already safely on disk at *staging*, so a primary that was
            # itself corrupt never gets a chance to overwrite a good .bak
            # with more corruption.
            os.replace(path, bak)
        except OSError:
            # A backup that cannot be made must not stop the save. Losing
            # the tier is strictly better than losing the write that the
            # tier exists to protect.
            pass
    # Bounded retry, mirroring atomicio.write_atomic's own retry on this
    # exact rename: a Windows MoveFileExW sharing violation from a reader
    # that does not grant FILE_SHARE_DELETE is transient, so a short wait
    # clears it. This is defence in depth, not a substitute for load()'s
    # own recovery above -- if every attempt here is exhausted, the primary
    # has already been rotated into *bak* and this raises, but the next
    # load() finds `.bak` and recovers from it instead of taking the
    # silent first-launch branch.
    for attempt in range(5):
        try:
            os.replace(staging, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))
    if bak.exists():
        try:
            # write_atomic's own temp file is always created at 0600 by
            # tempfile.mkstemp and carries that mode across on replace, so
            # *path* is 0600 regardless of what mode the document it just
            # replaced had. Align .bak to match: without this, a document
            # that predates this package ever touching it (hand-created,
            # or migrated from an older release) leaves a laxer-permission
            # backup sitting beside the hardened primary it just replaced.
            #
            # This chmod is a no-op on Windows -- os.chmod there only ever
            # toggles the read-only attribute, never real permission bits
            # (uploader.py:286-293 makes the same point about the Google
            # token file). It costs nothing to still call it (POSIX gets
            # the real protection it describes), but the actual protection
            # for this document on Windows is the %LOCALAPPDATA% directory
            # ACL plus DPAPI-wrapping the refresh token itself (tokens.py,
            # dpapi.py), not these mode bits.
            os.chmod(bak, stat_module.S_IMODE(path.stat().st_mode))
        except OSError:
            pass
