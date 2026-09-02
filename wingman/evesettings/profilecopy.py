"""Filesystem authority for whole-profile creation.

This module owns three things a copy of a single settings FILE never had to:
proving a caller's source and destination tokens still name what a fresh
`tree.discover()` actually finds, validating every hierarchy edge a request
crosses (root -> server -> profile -> file) rather than only the last one,
and staging a whole recognized file set so a caller sees either the complete
new profile or none of it.

Replacement (backup-first overwrite) and API integration are later tasks;
this module only creates a NEW profile from a validated source. `stage_copy`
and `StagedProfileCopy` are already shaped for a replacement publisher to
reuse.
"""

import contextlib
import hashlib
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .. import atomicio
from . import tree

ProfileCopyMode = Literal["new", "replace"]

# Reserved, never "settings_": discovery's own _is_profile_dir only matches
# that literal prefix, so a directory named with this one can never be
# offered back as a profile, including mid-copy or after a crash leaves it
# behind.
STAGE_PREFIX = ".wingman-profile-copy-"
STAGE_SUFFIX = ".stage"

# Design doc: "contains 1 to 80 characters".
MAX_FRIENDLY_NAME_CHARS = 80

# The nine characters Windows refuses in a filename outright, plus the
# traversal primitives -- ported from planstore.py's identical rule, kept
# as its own copy rather than a shared import because the two modules
# validate different identities (a plan stem vs. a profile's friendly
# name) that only coincidentally share Windows' filename grammar today.
_INVALID_CHARS = frozenset('<>:"/\\|?*')

# Device names, not files: CreateFile on CON.txt opens the console, and
# Windows applies the rule to the base name, so an extension does not
# escape it. Same set as planstore.py/library.py's rules.
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{n}" for n in range(1, 10)]
    + [f"LPT{n}" for n in range(1, 10)]
)


@dataclass(frozen=True)
class ProfileCopyPlan:
    root: Path
    server: Path
    source: Path
    destination: Path
    source_name: str
    destination_name: str
    mode: ProfileCopyMode


@dataclass(frozen=True)
class StagedProfileCopy:
    plan: ProfileCopyPlan
    path: Path
    members: tuple[str, ...]


def validate_friendly_name(value, existing) -> str:
    """Return the cleaned friendly name, or raise ValueError naming the
    first rule it breaks.

    *existing* is a `Tree.profiles` list: the collision check compares
    each existing profile's actual directory name against what this name
    would become on disk (`settings_` + cleaned), casefolded on both
    sides. That comparison is deliberately case-insensitive on every
    platform this runs on, not only Windows' own case-insensitive
    filesystem: the released app is Windows-only, so a policy that only
    caught the collision on this suite's case-sensitive Linux filesystem
    by accident would let two profiles differing only by case pass here
    and then collide for real at creation time.
    """
    if not isinstance(value, str):
        raise ValueError("Profile name is not text.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Profile name cannot be empty.")
    if len(cleaned) > MAX_FRIENDLY_NAME_CHARS:
        raise ValueError(
            f"Profile name cannot be longer than {MAX_FRIENDLY_NAME_CHARS} characters."
        )
    if any(ord(ch) < 32 for ch in cleaned):
        raise ValueError("Profile name cannot contain a control character.")
    if cleaned in (".", ".."):
        raise ValueError("Profile name cannot be '.' or '..'.")
    bad = sorted({ch for ch in cleaned if ch in _INVALID_CHARS})
    if bad:
        raise ValueError(f"Profile name cannot contain {' '.join(bad)}.")
    if cleaned.endswith((".", " ")):
        # The trailing-space arm is reachable only through characters
        # str.strip() does not treat as whitespace (a non-breaking space,
        # say); ordinary trailing spaces are already gone by here.
        raise ValueError("Profile name cannot end with a dot or a space.")
    if cleaned.split(".", 1)[0].upper() in _RESERVED:
        # Before the first dot, not the whole name: Windows reserves the
        # device name whatever follows it, so CON.txt is refused as
        # surely as CON.
        raise ValueError(f"{cleaned} is a name Windows reserves. Choose another.")
    if cleaned.casefold().startswith(tree.PROFILE_PREFIX):
        # A friendly name is what the user types; the settings_ prefix is
        # this module's job to add. Accepting it here would let a pasted
        # raw folder name silently produce settings_settings_<name>.
        raise ValueError(
            f"Enter the name without the {tree.PROFILE_PREFIX} prefix; "
            "it is added automatically."
        )
    wanted = (tree.PROFILE_PREFIX + cleaned).casefold()
    for profile in existing:
        if profile.path.name.casefold() == wanted:
            raise ValueError(f"A profile named {cleaned!r} already exists.")
    return cleaned


def _is_direct_child(parent: Path, candidate) -> bool:
    """Whether *candidate* is a direct entry of *parent* -- not merely a
    descendant of it -- and, following any symlink or Windows junction,
    still resolves inside *parent*.

    Lexical parent equality and `tree.require_under` close two different
    gaps and neither alone is enough. Lexical equality alone cannot see a
    reparse point sitting directly under *parent* whose target is outside
    it -- exactly what `tree.py`'s own `test_a_symlinked_keep_does_not_
    escape_the_root` exists to name for the rescued-server case, and what
    this same shape can do to a server or profile entry ordinary discovery
    happily lists. `require_under` alone would accept a candidate nested
    two directories deep that happens to still resolve inside *parent*
    (parent/other/parent-lookalike), which is not a DIRECT entry no matter
    where it resolves.
    """
    if Path(candidate).parent != Path(parent):
        return False
    try:
        tree.require_under(parent, candidate)
    except ValueError:
        return False
    return True


def _same_path(candidate, requested) -> bool:
    """Whether *candidate* IS the path *requested* names, not a fallback
    `discover()` supplied for it.

    Two-way containment, not a lexical `==`: this is the same idiom
    `ui/api.py`'s `_eve_same_path` uses for the identical reason -- a
    trailing separator or an unresolved symlink on either side must not
    make a genuine match look stale, and `discover()`'s own fallback-to-
    first behavior must not make a fabricated token look genuine.
    """
    if candidate is None or requested is None:
        return False
    return tree.is_under(candidate, requested) and tree.is_under(requested, candidate)


def prepare_copy(
    discovered: tree.Tree, expected_source, mode: ProfileCopyMode, destination_arg
) -> ProfileCopyPlan:
    """Validate a profile-copy request against a freshly discovered tree.

    *expected_source* is the source-profile token the caller last showed
    the user; it must still name `discovered`'s own selected profile, not
    whatever `discover()` fell back to. *destination_arg* is a friendly
    name for `mode == "new"`, or an existing destination-profile token for
    `mode == "replace"`.

    Every hierarchy edge a request crosses is validated here, not only the
    final file: the selected server must resolve beneath the root (or be
    the root itself, exactly when discovery found profiles directly under
    it), and the source/destination profiles must each be a direct,
    non-escaping entry of that same server.
    """
    if mode not in ("new", "replace"):
        raise ValueError(f"Unknown copy mode: {mode!r}.")
    root = discovered.root
    server = discovered.server
    source = discovered.profile
    if root is None or server is None or source is None:
        raise ValueError("Choose the EVE settings folder, server, and profile first.")

    # Edge 1: root -> server. `server == root` is permitted only when
    # discovery confirms the root directly holds profiles -- the one
    # layout _servers_in itself ever produces that way, by adding root as
    # a Server candidate exactly when _has_profiles(root) found something
    # beneath it. `discovered.profiles` being non-empty is that same
    # confirmation, already computed for this selected server.
    if server == root:
        if not discovered.profiles:
            raise ValueError(
                "The selected server is outside the configured EVE folder."
            )
    elif not _is_direct_child(root, server):
        raise ValueError("The selected server is outside the configured EVE folder.")

    # Edge 2: server -> source profile, and the caller's token still
    # names it. Both checks matter: a symlinked profile entry can pass
    # discovery lexically while resolving outside the server, and a
    # stale expected_source can pass discovery's OWN fallback-to-first
    # while naming a profile the user never actually has selected anymore.
    if not _is_direct_child(server, source):
        raise ValueError("The selected profile is outside the selected server.")
    source_profile = next((p for p in discovered.profiles if p.path == source), None)
    if source_profile is None or not _same_path(source, expected_source):
        raise ValueError("The selected profile changed. Reopen Profiles and try again.")

    if mode == "new":
        cleaned = validate_friendly_name(destination_arg, discovered.profiles)
        destination = server / f"{tree.PROFILE_PREFIX}{cleaned}"
        destination_name = cleaned
        if not _is_direct_child(server, destination):
            raise ValueError("That profile name resolves outside the selected server.")
    else:
        destination_profile = next(
            (
                p
                for p in discovered.profiles
                if _same_path(p.path, destination_arg)
                and _is_direct_child(server, p.path)
            ),
            None,
        )
        if destination_profile is None:
            raise ValueError("That destination is not on the selected server.")
        destination = destination_profile.path
        destination_name = destination_profile.name

    if source == destination or _same_path(source, destination):
        raise ValueError("Source and destination cannot be the same profile.")

    return ProfileCopyPlan(
        root=root,
        server=server,
        source=source,
        destination=destination,
        source_name=source_profile.name,
        destination_name=destination_name,
        mode=mode,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recognized_members(profile: Path) -> list[Path]:
    """The recognized settings files directly inside *profile*, sorted by
    name for a deterministic staging order.

    Both failure modes here abort the whole copy rather than ever
    publishing a partial clone. A source that cannot be read (vanished,
    permission denied) raises instead of being read as "no recognized
    files", which would otherwise let an unreadable source silently
    publish an EMPTY profile. A recognized-looking name that turns out to
    be a link escaping the profile also raises, rather than being quietly
    dropped as though it were merely unrecognized: full hierarchy
    validation means refusing the whole operation over one rogue entry,
    not cloning around it.
    """
    try:
        entries = list(os.scandir(str(profile)))
    except OSError as error:
        raise OSError(
            f"Could not read the source profile {profile}: {error}"
        ) from error
    members = []
    for entry in entries:
        if tree.file_kind(entry.path) is None:
            continue
        candidate = Path(entry.path)
        if not _is_direct_child(profile, candidate):
            raise ValueError(
                f"{candidate.name} is a link that resolves outside {profile}."
            )
        members.append(candidate)
    members.sort(key=lambda p: p.name)
    return members


def _is_reparse_point(path: Path) -> bool:
    """Whether *path* is a symlink or a Windows junction (mount point).

    `Path.is_symlink()` alone misses a junction: Windows only reports
    `os.path.islink()`/`is_symlink()` True for the narrower
    IO_REPARSE_TAG_SYMLINK, not IO_REPARSE_TAG_MOUNT_POINT, which is what
    `mklink /J` and most GUI "directory junction" tools create. The
    `FILE_ATTRIBUTE_REPARSE_POINT` bit is set for either kind, which is
    why it is checked as well rather than instead.
    """
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            attrs = os.lstat(str(path)).st_file_attributes
        except (AttributeError, OSError):
            return False
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def cleanup_abandoned_stages(server: Path) -> None:
    """Remove staging directories a crashed prior run left behind.

    Only a direct entry of *server*, whose name matches the reserved
    prefix/suffix grammar exactly, and that is not itself a reparse point,
    is removed. A stage-shaped symlink or junction is not followed and is
    not silently skipped either: it refuses the whole cleanup (and so the
    copy operation calling it), because a name in this reserved namespace
    that is not an ordinary directory this module created is exactly the
    kind of thing that must not be assumed safe to walk into or delete
    through. `os.scandir` itself only ever yields direct entries, so no
    separate direct-child check is needed for that half of the rule.

    A failure to even list *server* (vanished, permission denied) also
    propagates rather than being read as "nothing to clean up": cleanup
    failures must be visible to the caller, the same as a failure to
    remove a matched candidate already was.
    """
    entries = list(os.scandir(str(server)))
    for entry in entries:
        if not (
            entry.name.startswith(STAGE_PREFIX) and entry.name.endswith(STAGE_SUFFIX)
        ):
            continue
        path = Path(entry.path)
        if _is_reparse_point(path):
            raise OSError(f"Refusing to remove a linked staging entry: {path}")
        if not entry.is_dir(follow_symlinks=False):
            # Not ours: stage_copy only ever creates directories under
            # this name.
            continue
        shutil.rmtree(path)


@contextlib.contextmanager
def stage_copy(plan: ProfileCopyPlan, *, token_factory=lambda: uuid.uuid4().hex):
    """Copy every recognized source file into a fresh, non-discoverable
    staging directory beside the destination, verifying each copy byte-
    for-byte before yielding.

    Abandoned stages from a prior crashed run are removed first. The
    staging directory is always removed on exit UNLESS a caller (such as
    `publish_new`) has already renamed it away -- `stage.exists()` is then
    False and cleanup is correctly a no-op rather than deleting what was
    just published.
    """
    cleanup_abandoned_stages(plan.server)
    stage = plan.server / f"{STAGE_PREFIX}{token_factory()}{STAGE_SUFFIX}"
    stage.mkdir()
    try:
        members = _recognized_members(plan.source)
        for source in members:
            target = stage / source.name
            atomicio.copy_atomic(source, target)
            if _sha256(source) != _sha256(target):
                raise OSError(f"Staged copy did not match {source.name}.")
        yield StagedProfileCopy(plan, stage, tuple(p.name for p in members))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def publish_new(staged: StagedProfileCopy) -> Path:
    """Publish a staged new-profile copy by renaming it into place.

    Rechecks nonexistence immediately before the rename: another actor
    creating the destination between `prepare_copy` and here is a race,
    not a bug in the caller, and is refused rather than silently
    overwritten or merged.
    """
    plan = staged.plan
    if plan.destination.exists():
        raise FileExistsError(f"{plan.destination_name!r} already exists.")
    staged.path.rename(plan.destination)
    return plan.destination
