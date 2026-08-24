"""Backup archives: naming, creation, listing, pruning, restore.

The filename is the index. Listing is one listdir and a parse -- no archive
is opened -- which is what keeps the tool from getting slower the more it is
used. The manifest inside stays authoritative for the full source path.

Archives are claimed then staged. Claiming with O_EXCL makes two writers in
the same second safe; staging keeps a half-written archive from ever
appearing under its final name, where filename-only listing would present it
as restorable. combatlog.build_archive stages for exactly this reason.
"""
import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import atomicio
from . import tree

MANIFEST_NAME = "wingman-eve-settings-backup.json"

_ORIGINS = ("auto", "manual")
_KINDS = ("character", "account", "profile")
# The alternations are BUILT from the tuples rather than spelled again
# beside them. Two copies of the same list is how a kind gets added to one
# and not the other, and the failure is silent: create_*_backup would write
# a name that parse_name then refuses to read, so the backup exists on disk
# and is invisible to listing, pruning and restore.
_NAME_RE = re.compile(
    r"^(?P<date>\d{8})-(?P<time>\d{6})-(?P<seq>\d{3})"
    rf"-(?P<origin>{'|'.join(_ORIGINS)})"
    rf"-(?P<kind>{'|'.join(_KINDS)})"
    r"-(?P<src>[0-9a-f]{8})"
    r"-(?P<stem>.+)$")
_MAX_SEQ = 1000


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created: str
    seq: int
    origin: str
    kind: str
    src: str
    stem: str

    @property
    def group(self) -> tuple:
        return self.kind, self.src, self.stem


def source_key(profile_dir) -> str:
    """Stable 8-hex identity for the settings set a backup came from.

    Not decoration: core_char_<id>.dat exists in every settings set, so a
    grouping key built from the stem alone would let a backup taken from one
    profile prune the rollback history belonging to another.
    """
    resolved = os.path.realpath(str(profile_dir))
    digest = hashlib.sha256(os.path.normcase(resolved).encode("utf-8"))
    return digest.hexdigest()[:8]


def _sanitize(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return cleaned[:80] or "unnamed"


def parse_name(name: str) -> BackupInfo | None:
    if not name.endswith(".zip"):
        return None
    match = _NAME_RE.match(name[:-len(".zip")])
    if match is None:
        return None
    return BackupInfo(
        path=Path(name),
        created=f"{match['date']}-{match['time']}",
        seq=int(match["seq"]),
        origin=match["origin"],
        kind=match["kind"],
        src=match["src"],
        stem=match["stem"])


def _claim(backup_dir: Path, stamp: str, origin: str, kind: str,
           src: str, stem: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for seq in range(_MAX_SEQ):
        candidate = backup_dir / (
            f"{stamp}-{seq:03d}-{origin}-{kind}-{src}-{stem}.zip")
        try:
            handle = os.open(str(candidate),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(handle)
        return candidate
    raise OSError("Too many backups were created in the same second.")


def _write_archive(claimed: Path, members, manifest: dict) -> None:
    staging = claimed.with_name(f"{claimed.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                with open(member, "rb") as source, \
                        archive.open(Path(member).name, "w") as entry:
                    shutil.copyfileobj(source, entry)
            archive.writestr(MANIFEST_NAME,
                             json.dumps(manifest, indent=2))
        os.replace(staging, claimed)
    except BaseException:
        for debris in (staging, claimed):
            try:
                debris.unlink()
            except OSError:
                pass
        raise


def _stamp(now) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("%Y%m%d-%H%M%S")


def create_file_backup(backup_dir, source, *, origin: str, now=None) -> Path:
    source = Path(source)
    kind = tree.file_kind(source)
    if kind is None:
        raise ValueError("Only EVE settings files can be backed up.")
    if origin not in _ORIGINS:
        raise ValueError(f"Unknown backup origin: {origin}")
    profile = source.parent
    claimed = _claim(Path(backup_dir), _stamp(now), origin, kind,
                     source_key(profile), _sanitize(source.stem))
    _write_archive(claimed, [source], {
        "kind": kind,
        "source": str(source),
        "profile": str(profile),
        "created": _stamp(now),
    })
    return claimed


def create_profile_backup(backup_dir, profile, *, origin: str,
                          now=None) -> Path:
    profile = Path(profile)
    if origin not in _ORIGINS:
        raise ValueError(f"Unknown backup origin: {origin}")
    members = sorted(child for child in profile.iterdir()
                     if tree.file_kind(child))
    label = profile.name
    label = label.removeprefix("settings_")
    claimed = _claim(Path(backup_dir), _stamp(now), origin, "profile",
                     source_key(profile), _sanitize(label))
    _write_archive(claimed, members, {
        "kind": "profile",
        "source": str(profile),
        "profile": str(profile),
        "created": _stamp(now),
    })
    return claimed


def enumerate_backups(backup_dir) -> tuple[list, bool]:
    """The backups on disk, plus whether the directory could not be read.

    The flag exists for the same reason tree._scan carries one: a store
    that has never been written and a store that denied us are different
    answers, and only one of them means something is wrong. Collapsing
    both into an empty list would tell the user "no backups yet" about a
    directory that is full of them -- and this design's own principle is
    that enumeration failures are reported, not swallowed into emptiness.

    Note that `except (FileNotFoundError, OSError)` could not have made
    this distinction even if the caller had wanted it: FileNotFoundError
    IS an OSError, so the first arm was never reached separately.
    """
    backup_dir = Path(backup_dir)
    found: list = []
    try:
        entries = list(os.scandir(str(backup_dir)))
    except FileNotFoundError:
        # Never written to yet. Genuinely "no backups".
        return found, False
    except OSError:
        return found, True
    for entry in entries:
        if not entry.is_file():
            continue
        # _claim() creates the FINAL name empty and only then stages and
        # replaces. Process death in that window leaves a 0-byte .zip under
        # a name this function would otherwise list as restorable -- and
        # which would consume a prune slot and evict a real backup. The
        # DirEntry already carries the stat, so this costs nothing.
        try:
            if entry.stat().st_size == 0:
                continue
        except OSError:
            continue
        info = parse_name(Path(entry.path).name)
        if info is None:
            continue
        found.append(BackupInfo(Path(entry.path), info.created, info.seq,
                                info.origin, info.kind, info.src, info.stem))
    found.sort(key=lambda i: (i.created, i.seq), reverse=True)
    return found, False


def prune(backup_dir, keep: int) -> list:
    """Drop all but the newest *keep* auto-backups per (kind, src, stem)."""
    groups: dict = {}
    # An unreadable store prunes nothing, which is what the empty list it
    # comes back with already achieves: there is nothing to reason about
    # and deleting on a guess is the one outcome that cannot be undone.
    listed, _unreadable = enumerate_backups(backup_dir)
    for info in listed:
        if info.origin != "auto":
            continue
        groups.setdefault(info.group, []).append(info)
    removed = []
    for infos in groups.values():
        infos.sort(key=lambda i: (i.created, i.seq), reverse=True)
        for info in infos[max(0, keep):]:
            try:
                info.path.unlink()
                removed.append(info.path)
            except OSError:
                pass
    return removed


def read_manifest(archive_path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        try:
            raw = archive.read(MANIFEST_NAME).decode("utf-8", "replace")
        except KeyError:
            raise ValueError("That archive has no Wingman manifest.") from None
    try:
        manifest = json.loads(raw)
    except ValueError:
        raise ValueError("That archive's manifest is unreadable.") from None
    if not isinstance(manifest, dict) or not manifest.get("source"):
        raise ValueError("That archive's manifest is incomplete.")
    return manifest


def _validated_members(archive: zipfile.ZipFile) -> list:
    """Every entry, checked before anything is deleted.

    Complete and up front rather than interleaved with extraction: a bad
    archive must not be able to leave a profile emptied and half-repopulated.
    Flattening basenames alone would silently ACCEPT an unexpected member
    rather than reject it.
    """
    members = []
    for name in archive.namelist():
        if name == MANIFEST_NAME:
            continue
        if name != Path(name).name or name in ("", ".", ".."):
            raise ValueError(
                f"That archive contains a path-bearing entry: {name!r}")
        if tree.file_kind(name) is None:
            raise ValueError(f"That archive contains an unexpected file: {name!r}")
        members.append(name)
    return members


def restore(backup_dir, archive_path, root, *, now=None) -> Path:
    """Restore one archive. Returns the directory that was written to."""
    archive_path = tree.require_under(backup_dir, archive_path, suffix=".zip")
    manifest = read_manifest(archive_path)
    source = Path(manifest["source"])
    kind = manifest.get("kind", "")

    target_dir = source if kind == "profile" else source.parent
    # Fails rather than restoring somewhere unexpected when the user has
    # repointed the root since the backup was taken.
    tree.require_under(root, target_dir)

    # Nothing in target_dir is touched until every member is staged: a
    # failure partway through extraction, or in the auto-backup that
    # follows, must leave the profile exactly as it was rather than
    # half-repopulated. Staging happens in target_dir itself (not a system
    # temp dir) so the final os.replace stays on one filesystem -- it is
    # only atomic within one.
    target_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _validated_members(archive)
            if kind != "profile" and members != [source.name]:
                # A character/account archive backs up exactly one file.
                # Extra members would be written into the live profile
                # directory while the pre-restore backup below covers only
                # `source`, silently clobbering an unrelated character with
                # no way back.
                raise ValueError(
                    "That archive does not hold exactly the file it claims "
                    "to back up.")
            for name in members:
                # Belt and braces behind _validated_members: basename again
                # on the way out, so nothing can escape even if validation
                # grows a hole later.
                destination = target_dir / Path(name).name
                staging = destination.with_name(
                    f"{destination.name}.{uuid.uuid4().hex}.tmp")
                # Recorded before the write: open(..., "wb") creates the
                # file even if the copy that follows raises immediately, so
                # cleanup must already know about it by then.
                staged.append((staging, destination))
                with archive.open(name) as entry, \
                        open(staging, "wb") as handle:
                    shutil.copyfileobj(entry, handle)

            # The pre-restore auto-backup, taken only once every member is
            # safely staged. A failure here must still abort -- nothing
            # live has been touched yet, so aborting just means unstaging.
            if kind == "profile":
                create_profile_backup(backup_dir, target_dir, origin="auto",
                                      now=now)
            elif source.exists():
                create_file_backup(backup_dir, source, origin="auto",
                                   now=now)
    except BaseException:
        for staging, _destination in staged:
            try:
                staging.unlink()
            except OSError:
                pass
        raise

    if kind == "profile":
        for existing in target_dir.iterdir():
            if tree.file_kind(existing):
                existing.unlink()

    for staging, destination in staged:
        # os.replace over open(..., "wb") is what makes this a restore
        # rather than a truncate-in-place: EVE holds core_*.dat open for a
        # whole session, and a straight write into that name corrupts it
        # instead of merely refusing. The same retry ops.copy_to_targets
        # uses for the identical Windows sharing-violation reason.
        atomicio.replace_with_retry(str(staging), destination)
    return target_dir


def delete(backup_dir, archive_path) -> None:
    target = tree.require_under(backup_dir, archive_path, suffix=".zip")
    target.unlink()
