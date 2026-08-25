"""Discovery of EVE's settings tree, and containment checks over it.

Pure: scandir and stat, no mutation, no network. Every path that reaches a
destructive operation passes through require_under() first.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

# EVE's own three-level layout:
#   <root>/<server>/settings_<profile>/core_char_<id>.dat
_PROFILE_PREFIX = "settings_"
_KIND_PREFIXES = {"core_char_": "character", "core_user_": "account"}

# A real EVE root holds one directory per shared-cache install -- a
# handful. Every child directory of the root costs a scandir apiece to
# probe for settings_* children, on the bridge thread, so a mis-picked
# root like C:/Users/me turns discovery into hundreds of directory reads
# for a folder that was never going to be the answer. The cap is generous
# enough that no plausible EVE root reaches it, and a root that does is
# refused and SAID SO, rather than probed slowly or truncated silently --
# the same posture `unreadable` takes.
MAX_ROOT_CHILDREN = 64
# _has_profiles answers yes/no. A directory whose first entries hold no
# settings_* is not a settings server, and reading the remaining entries
# of, say, a package cache to confirm that buys nothing. Bounded AND
# lazy: the old code materialised every entry before testing any of them.
MAX_PROBE_ENTRIES = 4096

# Substring -> (key, display name). TriffView's list, kept as-is: a shard it
# does not know renders under its raw folder name, which is degraded rather
# than broken.
_SHARDS = (
    ("tranquil", "tranquility", "Tranquility"),
    ("serenity", "serenity", "Serenity"),
    ("singulari", "singularity", "Singularity"),
    ("duality", "duality", "Duality"),
    ("thunderdome", "thunderdome", "Thunderdome"),
    ("infinity", "infinity", "Infinity"),
    ("buckshot", "buckshot", "Buckshot"),
    ("tornado", "tornado", "Tornado"),
)


@dataclass(frozen=True)
class Server:
    path: Path
    name: str
    key: str


@dataclass(frozen=True)
class Profile:
    path: Path
    name: str
    file_count: int
    modified: float


@dataclass(frozen=True)
class SettingsFile:
    path: Path
    kind: str
    file_id: str


@dataclass(frozen=True)
class Tree:
    root: Path | None = None
    server: Path | None = None
    profile: Path | None = None
    servers: list = field(default_factory=list)
    profiles: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    accounts: list = field(default_factory=list)
    # True only when a directory existed and could not be read. A missing
    # directory is not unreadable -- conflating the two is what makes
    # TriffView say "no settings sets" when it means "denied".
    unreadable: bool = False
    # True when discovery was cut short by one of its own bounds: the
    # root held more than MAX_ROOT_CHILDREN directories so its children
    # were never probed, or a directory under it held more than
    # MAX_PROBE_ENTRIES entries so the probe stopped early. Either way
    # `servers` may be incomplete, and saying so is the point -- reported
    # rather than swallowed, for the same reason `unreadable` is: "that is
    # not an EVE folder" and "there is nothing in it" are different
    # answers, and only one of them is the user's mistake.
    too_broad: bool = False


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "CCP" / "EVE"
    return Path.home() / ".local" / "share" / "CCP" / "EVE"


def file_kind(path) -> str | None:
    """ "character", "account", or None for anything else.

    The id must be ASCII digits: str.isdigit() is True for Arabic-Indic and
    other Unicode numerals, none of which can be an EVE id.
    """
    name = Path(path).name
    if not name.endswith(".dat"):
        return None
    stem = name[: -len(".dat")]
    for prefix, kind in _KIND_PREFIXES.items():
        if stem.startswith(prefix):
            ident = stem[len(prefix) :]
            if ident and ident.isascii() and ident.isdigit():
                return kind
            return None
    return None


def file_id(path) -> str:
    stem = Path(path).name[: -len(".dat")]
    for prefix in _KIND_PREFIXES:
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    return ""


def _real(path) -> Path:
    """Expand, then resolve symlinks and junctions.

    realpath, not normpath: a lexical check cannot see a link, and either a
    POSIX symlink or a Windows junction beneath a legitimate root can
    redirect a delete or an overwrite outside it.
    """
    return Path(os.path.realpath(os.path.expandvars(str(path))))


def is_under(root, candidate) -> bool:
    try:
        _real(candidate).relative_to(_real(root))
    except ValueError:
        return False
    return True


def require_under(root, candidate, *, suffix: str | None = None) -> Path:
    """Resolve *candidate* and assert it is inside *root*."""
    resolved = _real(candidate)
    if not is_under(root, candidate):
        raise ValueError("That path is outside the configured EVE folder.")
    if suffix is not None and resolved.suffix.lower() != suffix:
        raise ValueError(f"Expected a {suffix} file.")
    return resolved


def _scan(path) -> tuple[list, bool]:
    """Directory entries, plus whether the read failed.

    Returns ([], False) for a directory that does not exist and ([], True)
    for one that exists but could not be read.
    """
    try:
        with os.scandir(str(path)) as entries:
            return list(entries), False
    except FileNotFoundError:
        return [], False
    except OSError:
        return [], True


def _shard(name: str) -> tuple[str, str]:
    lowered = name.lower()
    for needle, key, display in _SHARDS:
        if needle in lowered:
            return key, display
    return name, name


def _is_profile_dir(path) -> bool:
    return Path(path).name.startswith(_PROFILE_PREFIX)


class Probe(NamedTuple):
    """What one _has_profiles look found, and how much to trust it.

    A bare bool would make "no settings_* here", "I stopped counting" and
    "I was denied" the same answer, which is the conflation this whole
    module is written against.
    """

    found: bool
    truncated: bool = False
    denied: bool = False


def _has_profiles(path) -> Probe:
    """Does *path* hold any settings_* child? Bounded, and short-circuits.

    Deliberately NOT built on _scan(): that materialises every entry with
    list() before the first test, so probing one wrong directory could
    read hundreds of thousands of names to answer a question the first
    entry might have settled.

    The two failure flags exist because returning a bare False for either
    makes a directory vanish from the server list with nothing said --
    "the user is told there are no settings sets for a folder that plainly
    has them", which is the defect this design names as TriffView's.
    """
    try:
        with os.scandir(str(path)) as entries:
            for seen, entry in enumerate(entries):
                if seen >= MAX_PROBE_ENTRIES:
                    return Probe(False, truncated=True)
                try:
                    if entry.is_dir() and _is_profile_dir(entry.path):
                        return Probe(True)
                except OSError:
                    # One unstatable entry is not a verdict on the
                    # directory; keep looking at the rest.
                    continue
    except FileNotFoundError:
        return Probe(False)
    except OSError:
        return Probe(False, denied=True)
    return Probe(False)


def _servers_in(root, keep=None) -> tuple[list, bool, bool]:
    """Server directories under *root*, bounded.

    `keep` is the server normalize_selection already identified, and is
    probed even when the root is too broad to enumerate. Without that, the
    cap CANCELS the self-healing: picking the settings folder EVE itself
    shows you lifts the root to that folder's grandparent, and if the
    grandparent is something wide like C:/Games the user gets an empty
    tree and a warning about a folder they never chose -- from picking a
    folder that visibly contains their settings. Re-picking cannot escape
    it, because normalize_selection lifts to the same place every time.
    """
    entries, unreadable = _scan(root)
    found = []
    # The root itself counts as a server candidate: some installs put
    # settings_* directly under it. One scandir, always affordable.
    probe = _has_profiles(root)
    truncated = probe.truncated
    unreadable = unreadable or probe.denied
    if probe.found:
        key, display = _shard(Path(root).name)
        found.append(Server(Path(root), display, key))

    children = [e for e in entries if e.is_dir()]
    # Counted BEFORE probing, because the count is the cheap part: the
    # entries are already in hand, while each _has_profiles below is a
    # fresh scandir. Bailing here is what keeps a mis-picked root from
    # blocking the bridge thread for as long as C:/Users/me takes.
    too_broad = len(children) > MAX_ROOT_CHILDREN
    if too_broad and keep is not None:
        # One extra scandir, not hundreds: the selection is rescued while
        # the cap still holds. too_broad stays True, because the rest of
        # the list really was not enumerated and the page says so.
        keep = Path(keep)
        # _real on both sides, not a lexical compare: this module's whole
        # containment rule is that a lexical check cannot see a symlink or
        # a Windows junction, and `keep` is a stored value. The operations
        # themselves re-validate with require_under, so the exposure here
        # is listing a settings set from outside the root rather than
        # writing to one -- still not something to offer.
        if _real(keep).parent == _real(root) and _has_profiles(keep).found:
            key, display = _shard(keep.name)
            found.append(Server(keep, display, key))
    if not too_broad:
        for entry in children:
            name = Path(entry.path).name
            probe = _has_profiles(entry.path)
            # A child we could not finish reading, or were denied, must
            # not simply vanish from the dropdown: that tells the user
            # they have no settings sets for a folder that has them.
            truncated = truncated or probe.truncated
            unreadable = unreadable or probe.denied
            if probe.found or _shard(name)[0] != name:
                key, display = _shard(name)
                found.append(Server(Path(entry.path), display, key))
    found.sort(key=lambda s: (s.key != "tranquility", s.name.lower()))
    return found, unreadable, too_broad or truncated


def _profiles_in(server) -> tuple[list, bool]:
    entries, unreadable = _scan(server)
    found = []
    for entry in entries:
        if not entry.is_dir() or not _is_profile_dir(entry.path):
            continue
        path = Path(entry.path)
        children, _ = _scan(path)
        count = sum(1 for c in children if file_kind(c.path))
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        found.append(Profile(path, path.name[len(_PROFILE_PREFIX) :], count, modified))
    found.sort(key=lambda p: (p.name.lower() != "default", p.name.lower()))
    return found, unreadable


def _files_in(profile) -> tuple[list, list, bool]:
    entries, unreadable = _scan(profile)
    characters, accounts = [], []
    for entry in entries:
        kind = file_kind(entry.path)
        if kind is None:
            continue
        record = SettingsFile(Path(entry.path), kind, file_id(entry.path))
        (characters if kind == "character" else accounts).append(record)
    characters.sort(key=lambda f: f.file_id)
    accounts.sort(key=lambda f: f.file_id)
    return characters, accounts, unreadable


def normalize_selection(root, server, profile):
    """Self-heal a root pointed one or two levels too deep.

    Picking the folder EVE actually shows you lands on a settings_* or a
    server directory more often than on the root, and without this the tool
    shows an empty list for a folder that plainly has settings in it.
    """
    if root is None:
        return None, None, None
    root = Path(root)
    if _is_profile_dir(root):
        return root.parent.parent, root.parent, root
    if _has_profiles(root).found and root.parent != root:
        # A server directory: keep it as the server, lift the root above it.
        return root.parent, root, Path(profile) if profile else None
    return (root, Path(server) if server else None, Path(profile) if profile else None)


def discover(root, server=None, profile=None) -> Tree:
    """The whole visible tree, with the selection resolved against it."""
    if root is None:
        return Tree()
    root, server, profile = normalize_selection(root, server, profile)
    servers, unreadable, too_broad = _servers_in(root, keep=server)
    chosen_server = None
    if server is not None:
        chosen_server = next(
            (s.path for s in servers if _real(s.path) == _real(server)), None
        )
    if chosen_server is None and servers:
        chosen_server = servers[0].path

    profiles, profiles_unreadable = ([], False)
    if chosen_server is not None:
        profiles, profiles_unreadable = _profiles_in(chosen_server)
    chosen_profile = None
    if profile is not None:
        chosen_profile = next(
            (p.path for p in profiles if _real(p.path) == _real(profile)), None
        )
    if chosen_profile is None and profiles:
        chosen_profile = profiles[0].path

    characters, accounts, files_unreadable = ([], [], False)
    if chosen_profile is not None:
        characters, accounts, files_unreadable = _files_in(chosen_profile)

    return Tree(
        root=root,
        server=chosen_server,
        profile=chosen_profile,
        servers=servers,
        profiles=profiles,
        characters=characters,
        accounts=accounts,
        unreadable=unreadable or profiles_unreadable or files_unreadable,
        too_broad=too_broad,
    )
