"""Fail-closed, resumable split of credentials from legacy Skills state."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..eveskills import state as skills_state
from .state import (
    MAX_REFRESH_TOKEN_BLOB_CHARS,
    MAX_SCOPES,
    ROW_DEGRADATION_WARNING_PREFIX,
    AuthorityCharacter,
    AuthorityState,
    load_authority,
    save_authority,
)


class LegacyDisposition(Enum):
    ABSENT = "absent"
    LOADED = "loaded"
    RECOVERED = "recovered"
    FAILED = "failed"


@dataclass(frozen=True)
class LegacyLoadResult:
    state: skills_state.SkillsState | None
    authority: AuthorityState | None
    disposition: LegacyDisposition
    warnings: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class MigrationResult:
    """Migration output safe for the next startup composition step.

    ``skills`` is present only after migration completed and contains either
    an already-marked document or the stripped state that was successfully
    persisted. An incomplete result never exposes credential-bearing legacy
    state (or an unpersisted stripped candidate) for a caller to save later.
    """

    authority: AuthorityState | None
    skills: skills_state.SkillsState | None
    completed: bool
    warnings: tuple[str, ...] = ()
    error: str = ""


def _legacy_scopes(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    scopes = []
    for item in raw:
        if len(scopes) >= MAX_SCOPES:
            break
        if isinstance(item, str) and item and item not in scopes:
            scopes.append(item)
    return tuple(scopes)


def _legacy_authority(raw: dict) -> AuthorityState:
    """Parse the old credential fields after Skills stops owning them.

    This mirrors the legacy normalisation order: scan the complete list, let
    the last duplicate value win while retaining its first position, then cap
    the deduplicated roster. Migration is the only remaining code allowed to
    know the old combined document shape.
    """
    by_id: dict[int, AuthorityCharacter] = {}
    for item in raw["characters"]:
        if not isinstance(item, dict):
            continue
        character_id = skills_state._coerce_int(item.get("character_id"))
        if character_id is None or character_id <= 0:
            continue
        blob = item.get("refresh_token_blob")
        blob = blob if isinstance(blob, str) else ""
        rejected_blob = len(blob) > MAX_REFRESH_TOKEN_BLOB_CHARS
        name = item.get("character_name")
        owner_hash = item.get("owner_hash")
        by_id[character_id] = AuthorityCharacter(
            character_id=character_id,
            character_name=name.strip() if isinstance(name, str) else "",
            owner_hash=owner_hash.strip() if isinstance(owner_hash, str) else "",
            scopes=_legacy_scopes(item.get("scopes")),
            authenticated_utc=skills_state._parse_utc(item.get("authenticated_utc")),
            needs_reauth=item.get("needs_reauth") is True or rejected_blob,
            refresh_token_blob="" if rejected_blob else blob,
        )
    return AuthorityState(list(by_id.values())[: skills_state.MAX_CHARACTERS])


def _read_legacy_document(
    path: Path,
) -> tuple[skills_state.SkillsState, AuthorityState]:
    limit = skills_state.MAX_STATE_FILE_BYTES
    if path.stat().st_size > limit:
        raise ValueError(f"{path.name} exceeds the {limit // (1024 * 1024)} MiB limit.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds the {limit // (1024 * 1024)} MiB limit.")
    raw = json.loads(data.decode("utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("characters"), list):
        # The ordinary Skills loader tolerates malformed envelopes by returning
        # an empty state. Migration cannot: empty becomes authoritative and the
        # next writes permanently remove the only credential evidence.
        raise ValueError("Legacy Skills state has an invalid document shape.")
    return skills_state.from_dict(raw), _legacy_authority(raw)


def _failed_legacy(error: str, warnings: tuple[str, ...] = ()) -> LegacyLoadResult:
    return LegacyLoadResult(None, None, LegacyDisposition.FAILED, warnings, error)


def inspect_legacy_skills(path: Path) -> LegacyLoadResult:
    """Inspect primary and backup without changing either piece of evidence."""
    path = Path(path)
    backup = path.with_name(path.name + ".bak")
    try:
        state, authority = _read_legacy_document(path)
    except FileNotFoundError:
        try:
            recovered, recovered_authority = _read_legacy_document(backup)
        except FileNotFoundError:
            return LegacyLoadResult(
                skills_state.SkillsState(), AuthorityState(), LegacyDisposition.ABSENT
            )
        except (OSError, ValueError, RecursionError) as exc:
            return _failed_legacy(
                f"{path.name} is missing and its backup could not be read ({exc})."
            )
        return LegacyLoadResult(
            recovered,
            recovered_authority,
            LegacyDisposition.RECOVERED,
            (f"{path.name} was missing; using {backup.name} without rewriting it.",),
        )
    except OSError as exc:
        # Access failure is not corrupt content and must not be reclassified as
        # an absent roster merely because a backup may also be inaccessible.
        return _failed_legacy(f"{path.name} could not be read ({exc}).")
    except (ValueError, RecursionError) as primary_error:
        try:
            recovered, recovered_authority = _read_legacy_document(backup)
        except (OSError, ValueError, RecursionError) as backup_error:
            return _failed_legacy(
                f"{path.name} was invalid ({primary_error}) and its backup could "
                f"not be read ({backup_error})."
            )
        return LegacyLoadResult(
            recovered,
            recovered_authority,
            LegacyDisposition.RECOVERED,
            (
                f"{path.name} was invalid; using backup {backup.name} without "
                "moving or rewriting either file.",
            ),
        )
    return LegacyLoadResult(state, authority, LegacyDisposition.LOADED)


def _authority_evidence(path: Path) -> tuple[bool, str]:
    for candidate in (path, path.with_name(path.name + ".bak")):
        try:
            candidate.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            return False, f"Authority state could not be inspected ({exc})."
        return True, ""

    # load_authority preserves an unrecoverable primary by moving it aside.
    # That evidence must remain one-way on later launches too: otherwise the
    # first launch fails safely, then the second sees an absent canonical path
    # and resurrects stale credentials from Skills.
    try:
        preserved = next(path.parent.glob(f"{path.name}.corrupt-*"), None)
    except OSError as exc:
        return False, f"Authority state could not be inspected ({exc})."
    if preserved is not None:
        return False, (
            f"A preserved corrupt authority document ({preserved.name}) exists; "
            "legacy credentials will not be resurrected."
        )
    return False, ""


def _authority_rows_degraded(warnings: tuple[str, ...]) -> bool:
    return any(
        warning.startswith(ROW_DEGRADATION_WARNING_PREFIX) for warning in warnings
    )


def _strip_authority(legacy: skills_state.SkillsState) -> skills_state.SkillsState:
    characters = [
        skills_state.Character(
            character_id=character.character_id,
            fetched_utc=character.fetched_utc,
            active_levels=dict(character.active_levels),
            trained_levels=dict(character.trained_levels),
            queue=tuple(character.queue),
            error=character.error,
            skills_etag=character.skills_etag,
            queue_etag=character.queue_etag,
            group=character.group,
        )
        for character in legacy.characters
    ]
    return skills_state.SkillsState(
        characters=characters,
        selected_plan_name=legacy.selected_plan_name,
        selected_group=legacy.selected_group,
        authority_migrated=True,
    )


def migrate_legacy_skills(
    legacy_path: Path,
    authority_path: Path,
    *,
    inspector: Callable[[Path], LegacyLoadResult] = inspect_legacy_skills,
    authority_loader: Callable[
        [Path], tuple[AuthorityState | None, tuple[str, ...]]
    ] = load_authority,
    authority_saver: Callable[[Path, AuthorityState], None] = save_authority,
    skills_saver: Callable[[skills_state.SkillsState, Path], None] = skills_state.save,
) -> MigrationResult:
    """Split credentials first, then mark Skills stripped; safely retry either gap."""
    legacy_path = Path(legacy_path)
    authority_path = Path(authority_path)
    authority_exists, evidence_error = _authority_evidence(authority_path)
    if evidence_error:
        return MigrationResult(None, None, False, error=evidence_error)

    authority = None
    authority_warnings: tuple[str, ...] = ()
    if authority_exists:
        authority, authority_warnings = authority_loader(authority_path)
        if authority is None:
            detail = authority_warnings[0] if authority_warnings else "unknown error"
            return MigrationResult(
                None,
                None,
                False,
                authority_warnings,
                f"Existing EVE authority could not be loaded: {detail}",
            )
        if not authority.characters and _authority_rows_degraded(authority_warnings):
            return MigrationResult(
                authority,
                None,
                False,
                authority_warnings,
                "Existing EVE authority retained no characters after invalid rows "
                "were dropped; legacy credentials were left unchanged.",
            )

    legacy = inspector(legacy_path)
    warnings = authority_warnings + legacy.warnings
    if legacy.disposition is LegacyDisposition.FAILED or legacy.state is None:
        return MigrationResult(authority, None, False, warnings, legacy.error)

    if authority is None and legacy.state.authority_migrated:
        return MigrationResult(
            None,
            None,
            False,
            warnings,
            "Skills has an authority migration completion marker, but authority "
            "state is missing; legacy credentials will not be resurrected.",
        )

    if authority is not None and legacy.state.authority_migrated:
        return MigrationResult(authority, legacy.state, True, warnings)

    stripped = _strip_authority(legacy.state)
    if authority is None:
        if legacy.authority is None:  # Defensive: failed inspection returned above.
            return MigrationResult(None, None, False, warnings, legacy.error)
        authority = legacy.authority
        try:
            authority_saver(authority_path, authority)
        except (OSError, ValueError) as exc:
            return MigrationResult(
                None,
                None,
                False,
                warnings,
                f"EVE authority could not be saved ({exc}).",
            )

    try:
        # This first stripped save is also the moment `eve_skills.json.bak`
        # stops being the recovery copy skills_state.save()'s docstring
        # describes and starts being a one-cycle liability instead:
        # save() first writes the stripped content durably to staging, then
        # rotates whatever is CURRENTLY at legacy_path into `.bak` before
        # installing that staging file; what is currently at the primary,
        # the first time this runs, is the pre-strip legacy document --
        # credentials included. So immediately after migration completes,
        # the primary is clean but `eve_skills.json.bak` still holds the
        # old credential-bearing document, until the NEXT ordinary Skills
        # save rotates a (by then already-stripped) primary into `.bak` in
        # its place. This is a deliberate tradeoff, not an oversight: the
        # alternative -- migration deleting or blanking `.bak` itself --
        # would remove the one recovery copy a crash between this save and
        # the next could still need, trading a bounded, one-cycle exposure
        # for the loss of the corruption-recovery guarantee `.bak` exists
        # to provide. Nothing here shortens that window on purpose; it
        # closes at the pace of ordinary Skills activity, not on a timer.
        skills_saver(stripped, legacy_path)
    except (OSError, ValueError) as exc:
        return MigrationResult(
            authority,
            None,
            False,
            warnings,
            f"EVE authority was saved, but Skills could not be stripped ({exc}).",
        )
    return MigrationResult(authority, stripped, True, warnings)
