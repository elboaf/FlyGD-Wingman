"""Fail-closed, resumable split of credentials from legacy Skills state."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..eveskills import state as skills_state
from .state import (
    MAX_REFRESH_TOKEN_BLOB_CHARS,
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


def _read_legacy_document(path: Path) -> skills_state.SkillsState:
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
    return skills_state.from_dict(raw)


def _failed_legacy(error: str, warnings: tuple[str, ...] = ()) -> LegacyLoadResult:
    return LegacyLoadResult(None, LegacyDisposition.FAILED, warnings, error)


def inspect_legacy_skills(path: Path) -> LegacyLoadResult:
    """Inspect primary and backup without changing either piece of evidence."""
    path = Path(path)
    backup = path.with_name(path.name + ".bak")
    try:
        state = _read_legacy_document(path)
    except FileNotFoundError:
        try:
            recovered = _read_legacy_document(backup)
        except FileNotFoundError:
            return LegacyLoadResult(
                skills_state.SkillsState(), LegacyDisposition.ABSENT
            )
        except (OSError, ValueError, RecursionError) as exc:
            return _failed_legacy(
                f"{path.name} is missing and its backup could not be read ({exc})."
            )
        return LegacyLoadResult(
            recovered,
            LegacyDisposition.RECOVERED,
            (f"{path.name} was missing; using {backup.name} without rewriting it.",),
        )
    except OSError as exc:
        # Access failure is not corrupt content and must not be reclassified as
        # an absent roster merely because a backup may also be inaccessible.
        return _failed_legacy(f"{path.name} could not be read ({exc}).")
    except (ValueError, RecursionError) as primary_error:
        try:
            recovered = _read_legacy_document(backup)
        except (OSError, ValueError, RecursionError) as backup_error:
            return _failed_legacy(
                f"{path.name} was invalid ({primary_error}) and its backup could "
                f"not be read ({backup_error})."
            )
        return LegacyLoadResult(
            recovered,
            LegacyDisposition.RECOVERED,
            (
                f"{path.name} was invalid; using backup {backup.name} without "
                "moving or rewriting either file.",
            ),
        )
    return LegacyLoadResult(state, LegacyDisposition.LOADED)


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


def _authority_from_legacy(legacy: skills_state.SkillsState) -> AuthorityState:
    characters = []
    for character in legacy.characters:
        blob = character.refresh_token_blob
        rejected_blob = len(blob) > MAX_REFRESH_TOKEN_BLOB_CHARS
        characters.append(
            AuthorityCharacter(
                character_id=character.character_id,
                character_name=character.character_name,
                owner_hash=character.owner_hash,
                scopes=tuple(character.scopes),
                authenticated_utc=character.authenticated_utc,
                needs_reauth=character.needs_reauth or rejected_blob,
                refresh_token_blob="" if rejected_blob else blob,
            )
        )
    return AuthorityState(characters)


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
        authority = _authority_from_legacy(legacy.state)
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
