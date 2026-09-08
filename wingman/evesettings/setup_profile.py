"""Recipient-local setup construction, never publication or live-file mutation.

The richer manifest belongs only to setup creation. Ordinary profile copies and
backups keep their DAT-only membership. The controller owns confirmed pairing,
EVE-closed checks and final review revalidation before publishing the yielded
stage; byte revisions here are optimistic checks, not an external-writer lock.
"""

import contextlib
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .. import atomicio
from . import codec, profilecopy, setup_documents, tree
from .setup_model import ParsedSetup

_LOCAL_FILES = ("core_public__.yaml", "prefs.ini")


@dataclass(frozen=True)
class FileRevision:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ProfileManifest:
    profile: Path
    files: tuple[FileRevision, ...]


def _linked(info: os.stat_result) -> bool:
    # Windows junctions are not S_ISLNK, but share the reparse-point attribute.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _require_directory(path: Path) -> None:
    info = path.lstat()
    if _linked(info) or not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"Refusing a linked or non-directory profile path: {path}.")


def _require_plan(plan: profilecopy.ProfileCopyPlan) -> None:
    if plan.mode != "new":
        raise ValueError("Setup imports require a new profile.")
    for path in (plan.root, plan.server, plan.source):
        _require_directory(path)
        if ".." in path.parts:
            raise ValueError(f"Refusing a path alias: {path}.")
    for parent, child in (
        (plan.root, plan.server),
        (plan.server, plan.source),
        (plan.server, plan.destination),
    ):
        if parent == child == plan.root:
            continue
        if child.parent != parent:
            raise ValueError("The setup profile path is outside its selected parent.")
        tree.require_under(parent, child)
    if os.path.lexists(plan.destination):
        raise FileExistsError(f"{plan.destination_name!r} already exists.")


def _regular(path: Path) -> os.stat_result:
    info = path.lstat()
    if _linked(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"Refusing a nonregular file or linked alias: {path.name}.")
    tree.require_under(path.parent, path)
    return info


def _members(profile: Path) -> tuple[Path, ...]:
    _require_directory(profile)
    members = []
    for path in profile.iterdir():
        # Refuse Windows spelling aliases even on case-sensitive test volumes;
        # ignoring them could silently change the membership on Windows.
        name = path.name.casefold().rstrip(" .")
        if tree.file_kind(name) is None and name not in _LOCAL_FILES:
            continue
        if path.name != name:
            raise ValueError(f"Refusing a settings filename alias: {path.name}.")
        _regular(path)
        members.append(path)
    members = tuple(sorted(members))
    missing = set(_LOCAL_FILES) - {path.name for path in members}
    if missing:
        raise ValueError(
            f"The base profile is missing required local preferences: {', '.join(sorted(missing))}. "
            "Choose a normally initialized recipient profile."
        )
    return members


def _file_state(info: os.stat_result) -> tuple:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _revision(path: Path) -> FileRevision:
    before = _regular(path)
    # Do not follow a swapped symlink or block on a swapped FIFO where the OS
    # supports these flags. fstat also checks the opened object before reading.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.open(path, flags), "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            _file_state(before) != _file_state(opened)
            or not stat.S_ISREG(opened.st_mode)
            or _linked(opened)
        ):
            raise ValueError(f"The file {path.name} changed while being reviewed.")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(handle.fileno())
    if (
        size != before.st_size
        or _file_state(before) != _file_state(after)
        or _file_state(before) != _file_state(_regular(path))
    ):
        raise ValueError(f"The file {path.name} changed while being reviewed.")
    return FileRevision(path.name, size, digest.hexdigest())


def _files(profile: Path) -> tuple[FileRevision, ...]:
    members = _members(profile)
    result = tuple(_revision(path) for path in members)
    if _members(profile) != members:
        raise ValueError("The profile membership changed. Review the setup again.")
    return result


def _require_staged(
    path: Path, expected: ProfileManifest, updated: dict[str, str] | None = None
) -> None:
    actual = _files(path)
    expected_names = {row.name for row in expected.files}
    if {row.name for row in actual} != expected_names or {
        p.name for p in path.iterdir()
    } != expected_names:
        raise ValueError("The staged profile membership changed.")
    updates = updated or {}
    for original, current in zip(expected.files, actual, strict=True):
        if original.name in updates:
            matches = current.sha256 == updates[original.name]
        else:
            matches = original == current
        if not matches:
            raise ValueError(f"The staged file {original.name} changed.")


def capture_manifest(plan: profilecopy.ProfileCopyPlan) -> ProfileManifest:
    """Capture exact recognized DAT and required local preference bytes."""
    _require_plan(plan)
    files = _files(plan.source)
    _require_plan(plan)
    return ProfileManifest(plan.source, files)


def require_manifest(
    plan: profilecopy.ProfileCopyPlan, expected: ProfileManifest
) -> None:
    """Refuse a changed base, including additions/removals and same-size edits."""
    if capture_manifest(plan) != expected:
        raise ValueError("The base profile changed. Review the setup again.")


def _selected_revision(expected: ProfileManifest, name: str, kind: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or any(char in name for char in "/\\:")
        or tree.file_kind(name) != kind
    ):
        raise ValueError(f"Choose a local {kind} settings filename.")
    for row in expected.files:
        if row.name == name:
            return row.sha256
    raise ValueError(f"The selected {kind} file {name!r} is not in the base profile.")


@contextlib.contextmanager
def stage_setup(
    plan: profilecopy.ProfileCopyPlan,
    expected: ProfileManifest,
    account_filename: str,
    character_filename: str,
    parsed: ParsedSetup,
    *,
    keep_ship_labels: bool,
    now: float,
):
    """Yield a complete hidden profile for final controller checks/publication.

    Both documents must pass the pure adapter before either is encoded. Failures
    propagate through the original stage's cleanup/publication bookkeeping.
    """
    require_manifest(plan, expected)
    account_revision = _selected_revision(expected, account_filename, "account")
    character_revision = _selected_revision(expected, character_filename, "character")
    with profilecopy.stage_copy(plan) as staged:
        for name in _LOCAL_FILES:
            atomicio.copy_atomic(plan.source / name, staged.path / name)
        _require_staged(staged.path, expected)
        require_manifest(plan, expected)
        staged_account_path = staged.path / account_filename
        staged_character_path = staged.path / character_filename
        account = codec.read_snapshot(staged_account_path)
        character = codec.read_snapshot(staged_character_path)
        if (
            account.content_revision != account_revision
            or character.content_revision != character_revision
        ):
            raise ValueError(
                "The staged recipient documents changed. Review the setup again."
            )
        updated_account, updated_character = setup_documents.apply_setup(
            account.document,
            character.document,
            parsed,
            keep_ship_labels=keep_ship_labels,
            now=now,
        )
        # Disposable hidden staging has no live predecessor to back up. This is
        # not permission to skip backup for an existing profile's settings.
        written_account_revision = codec.write_document(
            staged_account_path,
            updated_account,
            backup=lambda _path: None,
            expected_content_revision=account_revision,
        )
        written_character_revision = codec.write_document(
            staged_character_path,
            updated_character,
            backup=lambda _path: None,
            expected_content_revision=character_revision,
        )
        _require_staged(
            staged.path,
            expected,
            {
                account_filename: written_account_revision,
                character_filename: written_character_revision,
            },
        )
        require_manifest(plan, expected)
        yield staged
