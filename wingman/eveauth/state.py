"""Persistent app-wide EVE character identities and OAuth grants.

This document deliberately excludes every capability's derived data. Skills
snapshots and fitting presence can be rebuilt; identities and DPAPI-wrapped
refresh tokens cannot. Keeping the authority document narrow also lets either
capability evolve without becoming another credential writer.
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

STATE_VERSION = 1
MAX_CHARACTERS = 50
MAX_SCOPES = 100
MAX_STATE_FILE_BYTES = 16 * 1024 * 1024
# SSO accepts at most 2 KiB of refresh-token text. DPAPI adds metadata before
# base64 encoding; 16 KiB is generous headroom while still bounding corrupt
# local input before it becomes long-lived authority state.
MAX_REFRESH_TOKEN_BLOB_CHARS = 16 * 1024
ROW_DEGRADATION_WARNING_PREFIX = "Authority state row degradation:"


@dataclass(frozen=True)
class AuthorityCharacter:
    character_id: int
    character_name: str = ""
    owner_hash: str = ""
    scopes: tuple[str, ...] = ()
    authenticated_utc: datetime | None = None
    needs_reauth: bool = False
    refresh_token_blob: str = ""


@dataclass
class AuthorityState:
    characters: list[AuthorityCharacter] = field(default_factory=list)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat()


def _parse_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _coerce_character_id(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            return None
    else:
        return None
    return value if value > 0 else None


def _coerce_trimmed_text(raw: object) -> str:
    return raw.strip() if isinstance(raw, str) else ""


def _coerce_scopes(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    scopes = []
    for item in raw:
        if len(scopes) >= MAX_SCOPES:
            break
        if isinstance(item, str) and item and item not in scopes:
            scopes.append(item)
    return tuple(scopes)


def _coerce_blob(raw: object) -> tuple[str, bool]:
    if not isinstance(raw, str):
        return "", False
    if len(raw) > MAX_REFRESH_TOKEN_BLOB_CHARS:
        return "", bool(raw)
    return raw, False


def _to_dict(authority: AuthorityState) -> dict:
    return {
        "version": STATE_VERSION,
        "characters": [
            {
                "character_id": character.character_id,
                "character_name": character.character_name,
                "owner_hash": character.owner_hash,
                "scopes": list(character.scopes),
                "authenticated_utc": _iso(character.authenticated_utc),
                "needs_reauth": character.needs_reauth,
                "refresh_token_blob": character.refresh_token_blob,
            }
            for character in authority.characters
        ],
    }


def _from_dict(raw: object) -> tuple[AuthorityState, int]:
    if not isinstance(raw, dict) or not isinstance(raw.get("characters"), list):
        # Per-row tolerance is safe; losing a malformed character asks only
        # that character to re-authenticate. Treating a malformed document
        # envelope as a valid empty authority would instead erase every grant.
        raise ValueError("Authority state has an invalid document shape.")
    rows = raw["characters"]

    by_id: dict[int, AuthorityCharacter] = {}
    dropped_rows = 0
    for item in rows:
        if not isinstance(item, dict):
            dropped_rows += 1
            continue
        character_id = _coerce_character_id(item.get("character_id"))
        if character_id is None:
            dropped_rows += 1
            continue
        blob, blob_was_rejected = _coerce_blob(item.get("refresh_token_blob"))
        by_id[character_id] = AuthorityCharacter(
            character_id=character_id,
            character_name=_coerce_trimmed_text(item.get("character_name")),
            owner_hash=_coerce_trimmed_text(item.get("owner_hash")),
            scopes=_coerce_scopes(item.get("scopes")),
            authenticated_utc=_parse_utc(item.get("authenticated_utc")),
            needs_reauth=item.get("needs_reauth") is True or blob_was_rejected,
            refresh_token_blob=blob,
        )
    return AuthorityState(list(by_id.values())[:MAX_CHARACTERS]), dropped_rows


def _read_bounded(path: Path) -> str:
    limit = MAX_STATE_FILE_BYTES
    if path.stat().st_size > limit:
        raise ValueError(f"{path.name} exceeds the {limit // (1024 * 1024)} MiB limit.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds the {limit // (1024 * 1024)} MiB limit.")
    return data.decode("utf-8")


def _read_document(path: Path) -> tuple[AuthorityState, tuple[str, ...]]:
    authority, dropped_rows = _from_dict(json.loads(_read_bounded(path)))
    if not dropped_rows:
        return authority, ()
    return authority, (
        f"{ROW_DEGRADATION_WARNING_PREFIX} {path.name} dropped {dropped_rows} "
        "invalid character rows.",
    )


def _preserve_corrupt(path: Path) -> str:
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


def _recover_missing_primary(path: Path, backup: Path) -> tuple:
    try:
        recovered, row_warnings = _read_document(backup)
    except (OSError, ValueError, RecursionError) as exc:
        return None, (
            f"{path.name} was missing and its authority backup could not be "
            f"read ({exc}); EVE identity features are unavailable.",
        )
    if row_warnings and not recovered.characters:
        return recovered, (
            *row_warnings,
            f"{path.name} was missing; {backup.name} retained no valid authority "
            "rows and was left unchanged.",
        )
    try:
        save_authority(path, recovered)
    except OSError as exc:
        return recovered, (
            *row_warnings,
            f"{path.name} was missing and was read from {backup.name}, but the "
            f"recovery could not be saved ({exc}).",
        )
    return recovered, (
        *row_warnings,
        f"{path.name} was missing and was recovered from {backup.name}.",
    )


def _recover_corrupt_primary(path: Path) -> tuple:
    preserved = _preserve_corrupt(path)
    backup = path.with_name(path.name + ".bak")
    try:
        recovered, row_warnings = _read_document(backup)
    except (OSError, ValueError, RecursionError) as exc:
        return None, (
            f"{path.name} could not be recovered from its authority backup "
            f"({exc}); it was preserved as {preserved or 'a copy'}. EVE "
            "identity features are unavailable.",
        )

    if not preserved:
        return recovered, (
            *row_warnings,
            f"Recovered {path.name} from {backup.name}, but the corrupt "
            "authority file could not be moved aside and remains in place.",
        )
    if row_warnings and not recovered.characters:
        return recovered, (
            *row_warnings,
            f"{backup.name} retained no valid authority rows and was left "
            f"unchanged; the corrupt primary was preserved as {preserved}.",
        )
    try:
        save_authority(path, recovered)
    except OSError as exc:
        return recovered, (
            *row_warnings,
            f"Recovered {path.name} from {backup.name}, but the recovery could "
            f"not be saved ({exc}); the corrupt file was preserved as {preserved}.",
        )
    return recovered, (
        *row_warnings,
        f"Recovered {path.name} from {backup.name}; the corrupt authority "
        f"file was preserved as {preserved}.",
    )


def load_authority(path: Path) -> tuple[AuthorityState | None, tuple[str, ...]]:
    """Load authority, returning ``None`` rather than an empty grant on failure.

    Missing state is a legitimate first launch. Any evidence of an authority
    document that cannot be read fails closed so stale credentials in another
    document can never be mistaken for the current grant.
    """
    path = Path(path)
    try:
        return _read_document(path)
    except FileNotFoundError:
        backup = path.with_name(path.name + ".bak")
        try:
            backup.stat()
        except FileNotFoundError:
            return AuthorityState(), ()
        except OSError as exc:
            return None, (
                f"{path.name} could not be read ({exc}); EVE identity features "
                "are unavailable.",
            )
        return _recover_missing_primary(path, backup)
    except OSError as exc:
        return None, (
            f"{path.name} could not be read ({exc}); EVE identity features are "
            "unavailable.",
        )
    except (ValueError, RecursionError):
        return _recover_corrupt_primary(path)


def _validate_for_save(authority: AuthorityState) -> None:
    if len(authority.characters) > MAX_CHARACTERS:
        raise ValueError(f"Wingman supports up to {MAX_CHARACTERS} EVE characters.")
    seen = set()
    for character in authority.characters:
        if (
            isinstance(character.character_id, bool)
            or not isinstance(character.character_id, int)
            or character.character_id <= 0
        ):
            raise ValueError("Authority character IDs must be positive integers.")
        if character.character_id in seen:
            raise ValueError("Authority character IDs must be unique.")
        seen.add(character.character_id)
        if len(character.scopes) > MAX_SCOPES:
            raise ValueError(
                f"An authority grant may contain at most {MAX_SCOPES} scopes."
            )
        if len(character.refresh_token_blob) > MAX_REFRESH_TOKEN_BLOB_CHARS:
            raise ValueError("The protected refresh token is too large.")


def save_authority(path: Path, authority: AuthorityState) -> None:
    """Atomically save authority, retaining one owner-only sibling backup."""
    _validate_for_save(authority)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".bak")
    staging = path.with_name(path.name + ".new")
    atomicio.write_atomic(staging, json.dumps(_to_dict(authority), indent=2))
    if path.exists():
        with contextlib.suppress(OSError):
            os.replace(path, backup)
    try:
        atomicio.replace_with_retry(str(staging), path)
    except BaseException:
        # A failed final swap leaves the previous authority safe in .bak;
        # discard only the unpublished staging file.
        with contextlib.suppress(OSError):
            staging.unlink()
        raise
    if backup.exists():
        with contextlib.suppress(OSError):
            os.chmod(backup, stat_module.S_IMODE(path.stat().st_mode))
