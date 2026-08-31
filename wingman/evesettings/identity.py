"""Account labels and conservative account/character identification.

EVE exposes character ids through ESI, but its account settings files contain
only an internal numeric id.  Associations here are Wingman-owned metadata:
filesystem changes can propose a pair, but only the user's confirmation makes
it persistent.
"""

from dataclasses import dataclass
from pathlib import Path

from . import tree


@dataclass(frozen=True)
class FileStamp:
    kind: str
    file_id: str
    size: int
    modified_ns: int


@dataclass(frozen=True)
class Snapshot:
    root: Path
    server: Path
    profile: Path
    files: dict[Path, FileStamp]


@dataclass(frozen=True)
class Changes:
    accounts: tuple[str, ...] = ()
    characters: tuple[str, ...] = ()
    invalidated: bool = False


def take_snapshot(found: tree.Tree) -> Snapshot:
    """Capture one selected profile without reading any settings document."""
    if found.root is None or found.server is None or found.profile is None:
        raise ValueError("Choose an EVE settings profile first.")
    files = {}
    for record in (*found.accounts, *found.characters):
        stat = record.path.stat()
        files[record.path] = FileStamp(
            record.kind, record.file_id, stat.st_size, stat.st_mtime_ns
        )
    return Snapshot(found.root, found.server, found.profile, files)


def changes_since(before: Snapshot, found: tree.Tree) -> Changes:
    """Return changed ids, invalidating a comparison whose context moved."""
    if (
        found.root != before.root
        or found.server != before.server
        or found.profile != before.profile
        or found.unreadable
        or found.too_broad
    ):
        return Changes(invalidated=True)

    current = {}
    for record in (*found.accounts, *found.characters):
        try:
            stat = record.path.stat()
        except OSError:
            return Changes(invalidated=True)
        current[record.path] = FileStamp(
            record.kind, record.file_id, stat.st_size, stat.st_mtime_ns
        )

    if any(path not in current for path in before.files):
        return Changes(invalidated=True)

    changed = [
        stamp
        for path, stamp in current.items()
        if path not in before.files or before.files[path] != stamp
    ]
    return Changes(
        accounts=tuple(sorted(s.file_id for s in changed if s.kind == "account")),
        characters=tuple(sorted(s.file_id for s in changed if s.kind == "character")),
    )


def account_identity(
    account_id: str,
    account_names: dict,
    associations: dict,
    character_name,
) -> dict:
    """One display representation for every account surface."""
    account_name = str(account_names.get(account_id) or "").strip()
    character_ids = associations.get(account_id) or []
    names = sorted((character_name(cid) for cid in character_ids), key=str.casefold)
    character_summary = ""
    if names:
        character_summary = names[0]
        if len(names) > 1:
            character_summary += f" + {len(names) - 1}"

    if account_name:
        primary = account_name
        secondary_parts = [character_summary] if character_summary else []
        secondary_parts.append(f"Account {account_id}")
    else:
        primary = f"Account {account_id}"
        secondary_parts = ["Not identified"]
    secondary = " · ".join(secondary_parts)
    return {
        "primary": primary,
        "secondary": secondary,
        "option": f"{primary} · {secondary}" if secondary else primary,
    }
