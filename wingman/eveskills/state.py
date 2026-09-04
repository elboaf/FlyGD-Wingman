"""Persistent Skills snapshots, groups, plan selection, errors, and ETags.

Character identity, scopes, and credentials live in :mod:`wingman.eveauth`.
This document keeps only data produced or curated by Skills. Its rows are
reconciled against shared authority at startup, so a crash after global
forget can leave harmless derived metadata but never an orphan credential.

Normalisation on load is deliberately tolerant rather than versioned, which
is the same posture settings.py's validated_*() functions take and the
reason preview/layout.py:26-32 gives: a partially-written or hand-edited
file should cost one row, not the launch.
"""

import contextlib
import json
import os
import stat as stat_module
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import atomicio
from ..eveauth.cleanup import LoadHealth
from .evaluator import QueueEntry
from .training import ATTRIBUTE_NAMES

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

# A group name is rendered in the rail's ~180px column, which is what
# bounds it -- a different constraint from the 120 above, which bounds a
# pointer to a plan FILE. Kept as its own constant rather than reusing
# that one, so a change to either cannot silently move the other.
MAX_GROUP_NAME_CHARS = 40


@dataclass
class Character:
    character_id: int
    fetched_utc: "datetime | None" = None
    active_levels: dict = field(default_factory=dict)
    trained_levels: dict = field(default_factory=dict)
    queue: tuple = ()
    error: str = ""
    # Per-endpoint ETags. These are request optimisation ONLY -- they are
    # not freshness state. fetched_utc is the single freshness fact, and it
    # means "both halves were confirmed current at this time".
    skills_etag: str = ""
    queue_etag: str = ""
    # Membership, not a display field. D1: it lives here so that remove()
    # prunes it atomically and there is no second collection to keep in
    # step with the roster.
    group: str = ""
    # Total skill points per skill, keyed the same as active_levels/
    # trained_levels. Complete is a separate flag rather than "non-empty",
    # because a character with zero trained skills is a real, valid state
    # and must not be indistinguishable from "never downloaded".
    skill_points: dict = field(default_factory=dict)
    skill_points_complete: bool = False
    # ESI's five learning attributes, keyed by name. Populated from a
    # separate endpoint from skills/skillqueue, so it carries its own
    # freshness fact and ETag rather than reusing fetched_utc/skills_etag.
    attributes: dict = field(default_factory=dict)
    attributes_fetched_utc: "datetime | None" = None
    attributes_error: str = ""
    attributes_etag: str = ""

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
    selected_group: str = ""
    # One-way migration marker: if authority is later missing or corrupt,
    # stale credential fields must never be recreated from this document.
    authority_migrated: bool = False

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
            raise ValueError(f"TriffSkills supports up to {MAX_CHARACTERS} characters.")
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
    return value.astimezone(UTC).isoformat()


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
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def _coerce_skill_points(raw) -> tuple:
    """Skill id -> total SP, or ({}, False) if `raw` is not a structurally
    valid map.

    Unlike _coerce_levels, one bad entry invalidates the WHOLE map rather
    than being dropped individually: active_levels/trained_levels tolerate
    a partial drop because the evaluator already treats an absent skill id
    as untrained, so losing one entry just understates a single skill.
    skill_points has no such fallback meaning for "missing" -- a partial SP
    map has no way to signal that it is partial, so a caller trusting it
    would show a confidently wrong total rather than an honestly absent
    one. `{}` itself is structurally valid: a character with zero trained
    skills is a real state, not evidence of corruption.

    Reuses MAX_LEVEL_ENTRIES rather than its own cap: both collections are
    keyed by the same bounded set of real EVE skill ids, so anything that
    bounds one legitimately bounds the other.
    """
    if not isinstance(raw, dict):
        return {}, False
    if len(raw) > MAX_LEVEL_ENTRIES:
        return {}, False
    out: dict = {}
    for key, value in raw.items():
        skill_id = _coerce_int(key)
        sp = _coerce_int(value)
        if skill_id is None or sp is None or skill_id <= 0 or sp < 0:
            return {}, False
        out[skill_id] = sp
    return out, True


def _coerce_attributes(raw) -> tuple:
    """Name -> value for exactly the five ESI learning attributes, or
    ({}, False) if `raw` is missing a name, carries an extra one, or holds
    a non-positive or non-integer value for any of them.

    Positive-only: 0 or negative is not a value ESI has ever reported for a
    trained attribute, so it is closer to a corrupt read than a real one.
    """
    # ATTRIBUTE_NAMES is training.py's own canonical frozenset -- the same
    # five names the calculator validates metadata against -- not retyped
    # here, so persisted attributes and the calculator can never drift on
    # what "the five attributes" means. set(raw) != ATTRIBUTE_NAMES compares
    # fine across set/frozenset by element, so no conversion is needed.
    if not isinstance(raw, dict) or set(raw) != ATTRIBUTE_NAMES:
        return {}, False
    out: dict = {}
    for name in ATTRIBUTE_NAMES:
        value = _coerce_int(raw.get(name))
        if value is None or value <= 0:
            return {}, False
        out[name] = value
    return out, True


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
        entries.append(
            QueueEntry(
                skill_id=skill_id,
                finished_level=finished_level,
                start_date=_parse_utc(item.get("start_date")),
                finish_date=_parse_utc(item.get("finish_date")),
                queue_position=len(entries) if position is None else position,
            )
        )
    entries.sort(key=lambda entry: entry.queue_position)
    return tuple(entries)


def _coerce_text(raw) -> str:
    return raw if isinstance(raw, str) else ""


def _coerce_trimmed_text(raw) -> str:
    """Trim the user-visible Skills error; ETags remain opaque."""
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


def _coerce_group_name(raw) -> str:
    """Cleared, not truncated, beyond the cap -- and the reason is stronger
    here than in _coerce_selected_plan_name above.

    That function refuses to truncate because a mangled name would point at
    a DIFFERENT plan file. A plan name at least has a folder to fail to
    match against, so a mangled one usually resolves to nothing. A group
    name IS the identity: nothing checks it, and nothing can. Truncating
    two distinct 45-character names to 40 does not fail to match -- it
    merges two crews into one, silently, which is the exact outcome the
    rename confirmation exists to stop happening without being asked.

    Trimmed BEFORE the length check, for the reason given there: a value
    over the cap only because of padding is kept, not needlessly cleared.
    """
    text = _coerce_text(raw).strip()
    if len(text) > MAX_GROUP_NAME_CHARS:
        return ""
    return text


def to_dict(state: SkillsState) -> dict:
    return {
        "version": STATE_VERSION,
        "selected_plan_name": state.selected_plan_name,
        "selected_group": state.selected_group,
        "authority_migrated": state.authority_migrated,
        "characters": [
            {
                "character_id": character.character_id,
                "fetched_utc": _iso(character.fetched_utc),
                # JSON object keys are strings; from_dict coerces them back.
                "active_levels": {
                    str(k): v for k, v in character.active_levels.items()
                },
                "trained_levels": {
                    str(k): v for k, v in character.trained_levels.items()
                },
                "queue": [
                    {
                        "skill_id": entry.skill_id,
                        "finished_level": entry.finished_level,
                        "start_date": _iso(entry.start_date),
                        "finish_date": _iso(entry.finish_date),
                        "queue_position": entry.queue_position,
                    }
                    for entry in character.queue
                ],
                "error": character.error,
                "skills_etag": character.skills_etag,
                "queue_etag": character.queue_etag,
                "group": character.group,
                "skill_points": {str(k): v for k, v in character.skill_points.items()},
                "skill_points_complete": character.skill_points_complete,
                "attributes": dict(character.attributes),
                "attributes_fetched_utc": _iso(character.attributes_fetched_utc),
                "attributes_error": character.attributes_error,
                "attributes_etag": character.attributes_etag,
            }
            for character in state.characters
        ],
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
        raw.get("selected_plan_name")
    )
    result.selected_group = _coerce_group_name(raw.get("selected_group"))
    result.authority_migrated = raw.get("authority_migrated") is True

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
        points, points_valid = _coerce_skill_points(item.get("skill_points"))
        # A skills_etag earned against a response body is only trustworthy
        # once skill_points is itself trustworthy and marked complete -- a
        # document written before this package tracked SP at all has an
        # ETag but no SP map, and a malformed-but-marked-complete map must
        # not leave a stale ETag standing in for data this load just
        # discarded. Either case must fall through to a real request, not
        # a 304 that hides the backfill.
        points_complete = item.get("skill_points_complete") is True and points_valid
        skills_etag = _coerce_text(item.get("skills_etag")) if points_complete else ""
        attrs, attrs_valid = _coerce_attributes(item.get("attributes"))
        attrs_fetched = _parse_utc(item.get("attributes_fetched_utc"))
        attrs_complete = attrs_valid and attrs_fetched is not None
        by_id[character_id] = Character(
            character_id=character_id,
            fetched_utc=_parse_utc(item.get("fetched_utc")),
            active_levels=_coerce_levels(item.get("active_levels")),
            trained_levels=_coerce_levels(item.get("trained_levels")),
            queue=_coerce_queue(item.get("queue")),
            error=_coerce_trimmed_text(item.get("error")),
            skills_etag=skills_etag,
            queue_etag=_coerce_text(item.get("queue_etag")),
            group=_coerce_group_name(item.get("group")),
            skill_points=points if points_valid else {},
            skill_points_complete=points_complete,
            attributes=attrs if attrs_complete else {},
            attributes_fetched_utc=attrs_fetched if attrs_complete else None,
            attributes_error=_coerce_trimmed_text(item.get("attributes_error")),
            attributes_etag=(
                _coerce_text(item.get("attributes_etag")) if attrs_complete else ""
            ),
        )
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
            f"{MAX_STATE_FILE_BYTES // (1024 * 1024)} MiB limit."
        )
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
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
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


def _load_health(
    cleanup_verifiable: bool, rewrite_required: bool = False
) -> LoadHealth:
    return LoadHealth(
        cleanup_verifiable=cleanup_verifiable,
        rewrite_required=rewrite_required,
    )


def _load_normalized_document(path: Path) -> tuple[SkillsState, bool]:
    raw = json.loads(_read_bounded(path))
    loaded = from_dict(raw)
    return loaded, raw != to_dict(loaded)


def load_with_health(path: Path) -> tuple[SkillsState, list[str], LoadHealth]:
    """Read the roster and report whether cleanup can trust the durable load."""
    path = Path(path)
    warnings: list[str] = []
    try:
        loaded, rewrite_required = _load_normalized_document(path)
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
            return SkillsState(), warnings, _load_health(True)
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
        warnings.append(
            f"{path.name} could not be read ({exc.strerror}); "
            "starting with an empty roster."
        )
        return SkillsState(), warnings, _load_health(False)
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

    return loaded, warnings, _load_health(not rewrite_required, rewrite_required)


def load(path: Path) -> tuple:
    """Read the roster. Returns (state, warnings) and never raises.

    A warning here reaches the UI notices strip, so it is written for the
    person reading it rather than for a log.
    """
    loaded, warnings, _health = load_with_health(path)
    return loaded, warnings


def _recover_missing_primary(
    path: Path, backup: Path, warnings: list[str]
) -> tuple[SkillsState, list[str], LoadHealth]:
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
    an empty derived roster while a perfectly good `.bak` sits beside it.
    """
    recovered = None
    for attempt in range(2):
        try:
            recovered, _rewrite_required = _load_normalized_document(backup)
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
            "characters you had added will need re-authorising."
        )
        return SkillsState(), warnings, _load_health(False)

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
            "will be lost."
        )
        return recovered, warnings, _load_health(False, rewrite_required=True)

    warnings.append(
        f"{path.name} was missing (likely an interrupted save) and was "
        f"recovered from its backup, {backup.name}."
    )
    return recovered, warnings, _load_health(True)


def _recover_from_backup(
    path: Path, warnings: list[str]
) -> tuple[SkillsState, list[str], LoadHealth]:
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
            recovered, _rewrite_required = _load_normalized_document(backup)
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
            "Any characters you had added will need re-authorising."
        )
        return SkillsState(), warnings, _load_health(False)

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
            "this recovery will be lost."
        )
        return recovered, warnings, _load_health(False, rewrite_required=True)

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
            "recovery will be lost."
        )
        return recovered, warnings, _load_health(False, rewrite_required=True)

    warnings.append(
        f"Recovered {path.name} from backup after the main file could not "
        f"be read; it was preserved as {preserved or 'a copy'}. Anything "
        "saved since the previous write is gone."
    )
    return recovered, warnings, _load_health(True)


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
    only this subsystem wants it, because plan/group choices and the last
    coherent offline snapshot should survive one failed replacement.
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
        # Rename, not copy: os.replace carries the source file's own
        # mode across unchanged (it is the same inode under a new
        # name), matching what shutil.copy2 gave the old copy-then-write
        # shape -- and it only runs now, after the new content is
        # already safely on disk at *staging*, so a primary that was
        # itself corrupt never gets a chance to overwrite a good .bak
        # with more corruption.
        #
        # A backup that cannot be made must not stop the save. Losing
        # the tier is strictly better than losing the write that the
        # tier exists to protect.
        with contextlib.suppress(OSError):
            os.replace(path, bak)
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
        # for this document on Windows is the %LOCALAPPDATA% directory ACL,
        # not these POSIX mode bits. Credentials live in eve_authority.json
        # and remain DPAPI-wrapped independently of this Skills document.
        with contextlib.suppress(OSError):
            os.chmod(bak, stat_module.S_IMODE(path.stat().st_mode))
