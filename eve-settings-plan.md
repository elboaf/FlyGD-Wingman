# EVE Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copy one EVE character's settings onto many others from inside Wingman, with every overwrite backed up first and every backup restorable.

**Architecture:** A new `obs_youtube_uploader/evesettings/` package of four modules with one-way dependencies (`tree` and `names` standalone, `backup` → `tree`, `ops` → `tree` + `backup`), reached through thin delegating methods on the existing `ui/api.py` bridge and a fourth flat route in `web/`. Almost all logic is pure filesystem work that tests on Linux against `tmp_path`; only the bridge wiring and the Windows sharing-violation behaviour need a real machine.

**Tech Stack:** Python 3.11+, stdlib only (`zipfile`, `urllib.request`, `hashlib`, `os`), pywebview 6.2.1 bridge, pytest.

**Spec:** `eve-settings-design.md` (committed at `917f581`)

## Global Constraints

- **Python `>=3.11`** (`pyproject.toml:19`). No syntax or stdlib newer than that.
- **No new dependencies.** Network access uses stdlib `urllib.request`, following `obs_youtube_uploader/discord.py:11-12,253`.
- **Licence is GPL-3.0-only** (`pyproject.toml:25`). This code derives from TriffView; do not relicense or add MIT headers.
- **Every new subpackage must be added to `tool.setuptools.packages`** in `pyproject.toml:64-68`. An omission installs cleanly and fails only in the frozen build. `tests/test_packaging_completeness.py` enforces it.
- **Tests must pass on Linux.** CI is `ubuntu-latest` and has no webview, no display (`tests/fakes.py:1-7`). Anything Windows-specific is injected and faked.
- **`.dat` file contents are never parsed or rewritten.** Files are copied byte-for-byte.
- **Run the suite with `python -m pytest`** from the repository root.

---

### Task 1: Binary atomic copy

The ordering constraint from the design: `atomicio.write_atomic` is `str`-only (`atomicio.py:13,35`), and everything in `ops.py` depends on a binary equivalent existing.

**Files:**
- Modify: `obs_youtube_uploader/atomicio.py`
- Test: `tests/test_atomicio.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `atomicio.copy_atomic(source: Path, target: Path, *, attempts: int = 5, sleep=time.sleep) -> None`. Raises `OSError` on failure; leaves `target` untouched when it raises.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_atomicio.py`:

```python
def test_copy_atomic_writes_bytes(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"\x00\x01\x02payload")
    target = tmp_path / "dst.dat"
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"\x00\x01\x02payload"


def test_copy_atomic_overwrites_existing(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"new")
    target = tmp_path / "dst.dat"
    target.write_bytes(b"old")
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"new"


def test_copy_atomic_creates_parent_directories(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "nested" / "deep" / "dst.dat"
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"x"


def test_copy_atomic_leaves_target_intact_when_source_is_missing(tmp_path):
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")
    with pytest.raises(OSError):
        atomicio.copy_atomic(tmp_path / "absent.dat", target)
    assert target.read_bytes() == b"original"


def test_copy_atomic_leaves_no_temp_files_behind(tmp_path):
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")
    with pytest.raises(OSError):
        atomicio.copy_atomic(tmp_path / "absent.dat", target)
    assert [p.name for p in tmp_path.iterdir()] == ["dst.dat"]


def test_copy_atomic_retries_a_locked_destination(tmp_path):
    """Windows raises PermissionError from os.replace when the destination
    is held open without FILE_SHARE_DELETE. EVE holds core_*.dat open."""
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "dst.dat"
    slept = []
    calls = []
    real_replace = os.replace

    def flaky(tmp_name, dest):
        calls.append(dest)
        if len(calls) < 3:
            raise PermissionError(32, "in use")
        real_replace(tmp_name, dest)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(atomicio.os, "replace", flaky)
    try:
        atomicio.copy_atomic(source, target, sleep=slept.append)
    finally:
        monkey.undo()
    assert target.read_bytes() == b"x"
    assert len(calls) == 3 and len(slept) == 2


def test_copy_atomic_gives_up_after_the_attempt_budget(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")

    def always_locked(tmp_name, dest):
        raise PermissionError(32, "in use")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(atomicio.os, "replace", always_locked)
    try:
        with pytest.raises(PermissionError):
            atomicio.copy_atomic(source, target, attempts=3, sleep=lambda _: None)
    finally:
        monkey.undo()
    assert target.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dst.dat", "src.dat"]
```

Add `import os` to the top of `tests/test_atomicio.py` if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_atomicio.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.atomicio' has no attribute 'copy_atomic'`

- [ ] **Step 3: Extract the retry loop and add the binary copy**

In `obs_youtube_uploader/atomicio.py`, add `import shutil` alongside the existing imports, then replace the retry block inside `write_atomic` with a call to a shared helper and add the new function.

Replace these lines in `write_atomic`:

```python
        for attempt in range(attempts):
            try:
                os.replace(tmp_name, path)
                break
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                sleep(0.05 * (attempt + 1))
```

with:

```python
        _replace_with_retry(tmp_name, path, attempts, sleep)
```

Then add, after `write_atomic`:

```python
def _replace_with_retry(tmp_name: str, path: Path, attempts: int, sleep) -> None:
    """os.replace, retried briefly against a locked destination.

    Windows only: os.replace maps to MoveFileExW, which raises a sharing
    violation if the destination is open by a reader that did not grant
    FILE_SHARE_DELETE. Shared by both writers here because both destinations
    are files another process may hold -- the engine polls the INI files, and
    EVE holds core_*.dat open for the whole session.
    """
    for attempt in range(attempts):
        try:
            os.replace(tmp_name, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            sleep(0.05 * (attempt + 1))


def copy_atomic(source: Path, target: Path, *, attempts: int = 5,
                sleep=time.sleep) -> None:
    """Copy *source* over *target* by rename, leaving it intact on error.

    The binary sibling of write_atomic, and separate from it rather than a
    mode flag: this one streams from a file rather than taking text, so the
    signature has no honest overlap.

    Streamed rather than read_bytes()'d. A settings .dat is tens of KB today,
    but nothing in the format guarantees that, and copyfileobj costs nothing
    to use.
    """
    source = Path(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(target.parent),
                                        prefix=target.name + ".",
                                        suffix=".tmp")
    try:
        with open(source, "rb") as src, os.fdopen(handle, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        _replace_with_retry(tmp_name, target, attempts, sleep)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_atomicio.py -v`
Expected: PASS, including the pre-existing `write_atomic` tests — the extracted helper must not change its behaviour.

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/atomicio.py tests/test_atomicio.py
git commit -m "feat(atomicio): add a binary copy_atomic beside write_atomic"
```

---

### Task 2: `tree.py` — discovery and containment

**Files:**
- Create: `obs_youtube_uploader/evesettings/__init__.py`
- Create: `obs_youtube_uploader/evesettings/tree.py`
- Modify: `pyproject.toml:64-68`
- Test: `tests/test_evesettings_tree.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `tree.default_root() -> Path`
  - `tree.file_kind(path) -> str | None` — `"character"`, `"account"`, or `None`
  - `tree.is_under(root, candidate) -> bool`
  - `tree.require_under(root, candidate, *, suffix=None) -> Path` — raises `ValueError`
  - `tree.normalize_selection(root, server, profile) -> tuple[Path | None, Path | None, Path | None]`
  - `tree.discover(root, server=None, profile=None) -> Tree`
  - dataclasses `Server(path, name, key)`, `Profile(path, name, file_count, modified)`, `SettingsFile(path, kind, file_id)`, `Tree(root, servers, profiles, characters, accounts, unreadable)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evesettings_tree.py`:

```python
"""Discovery and containment. Every case builds a fake EVE tree in tmp_path,
so the whole module tests on Linux."""
import os
from pathlib import Path

import pytest

from obs_youtube_uploader.evesettings import tree


def build(root: Path, server="c_eve_sharedcache_tq_tranquility",
          profile="settings_Default", files=("core_char_98123456.dat",)):
    target = root / server / profile
    target.mkdir(parents=True)
    for name in files:
        (target / name).write_bytes(b"x")
    return target


@pytest.mark.parametrize("name,expected", [
    ("core_char_98123456.dat", "character"),
    ("core_user_12345.dat", "account"),
    ("core_char_abc.dat", None),
    ("core_char_.dat", None),
    ("core_char_98123456.txt", None),
    ("settings.dat", None),
    ("core_char_٣.dat", None),
])
def test_file_kind(name, expected):
    """The id must be ASCII digits. isdigit() alone accepts Arabic-Indic
    numerals, which cannot be a character id."""
    assert tree.file_kind(Path("/x") / name) == expected


def test_discover_finds_servers_profiles_and_files(tmp_path):
    build(tmp_path, files=("core_char_98123456.dat", "core_user_12345.dat"))
    found = tree.discover(tmp_path)
    assert [s.key for s in found.servers] == ["tranquility"]
    assert [p.name for p in found.profiles] == ["Default"]
    assert [c.file_id for c in found.characters] == ["98123456"]
    assert [a.file_id for a in found.accounts] == ["12345"]


def test_discover_ignores_files_with_non_numeric_ids(tmp_path):
    build(tmp_path, files=("core_char_98123456.dat", "core_char_abc.dat"))
    found = tree.discover(tmp_path)
    assert [c.file_id for c in found.characters] == ["98123456"]


def test_unknown_server_folder_keeps_its_raw_name(tmp_path):
    build(tmp_path, server="c_eve_sharedcache_xx_newshard")
    found = tree.discover(tmp_path)
    assert found.servers[0].name == "c_eve_sharedcache_xx_newshard"
    assert found.servers[0].key == "c_eve_sharedcache_xx_newshard"


def test_tranquility_sorts_first(tmp_path):
    build(tmp_path, server="c_eve_sharedcache_sisi_singularity")
    build(tmp_path, server="c_eve_sharedcache_tq_tranquility")
    found = tree.discover(tmp_path)
    assert found.servers[0].key == "tranquility"


def test_default_profile_sorts_first(tmp_path):
    build(tmp_path, profile="settings_Alt")
    build(tmp_path, profile="settings_Default")
    found = tree.discover(tmp_path)
    assert found.profiles[0].name == "Default"


def test_normalize_selection_heals_a_root_pointed_at_a_profile(tmp_path):
    profile = build(tmp_path)
    root, server, selected = tree.normalize_selection(profile, None, None)
    assert root == tmp_path
    assert server == profile.parent
    assert selected == profile


def test_normalize_selection_heals_a_root_pointed_at_a_server(tmp_path):
    profile = build(tmp_path)
    root, server, selected = tree.normalize_selection(profile.parent, None, None)
    assert root == tmp_path
    assert server == profile.parent


def test_unreadable_root_is_reported_not_silently_empty(tmp_path):
    def boom(_path):
        raise PermissionError(13, "denied")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(tree.os, "scandir", boom)
    try:
        found = tree.discover(tmp_path)
    finally:
        monkey.undo()
    assert found.unreadable is True and found.servers == []


def test_missing_root_is_not_unreadable(tmp_path):
    found = tree.discover(tmp_path / "absent")
    assert found.unreadable is False and found.servers == []


def test_is_under_accepts_a_child(tmp_path):
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert tree.is_under(tmp_path, child) is True


def test_is_under_rejects_a_parent_escape(tmp_path):
    assert tree.is_under(tmp_path / "root", tmp_path / "root" / ".." / "other") is False


def test_is_under_rejects_a_sibling_with_a_shared_prefix(tmp_path):
    """C:\\EVE-evil must not read as being under C:\\EVE."""
    (tmp_path / "EVE").mkdir()
    (tmp_path / "EVE-evil").mkdir()
    assert tree.is_under(tmp_path / "EVE", tmp_path / "EVE-evil") is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_is_under_rejects_a_symlink_escaping_the_root(tmp_path):
    """A lexical check cannot see this. Windows junctions behave the same
    way and are something mklink /J creates by accident."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    assert tree.is_under(root, root / "link") is False


def test_require_under_raises_for_an_escape(tmp_path):
    with pytest.raises(ValueError):
        tree.require_under(tmp_path, tmp_path / ".." / "elsewhere")


def test_require_under_enforces_the_suffix(tmp_path):
    target = tmp_path / "core_char_1.txt"
    target.write_bytes(b"x")
    with pytest.raises(ValueError):
        tree.require_under(tmp_path, target, suffix=".dat")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_evesettings_tree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.evesettings'`

- [ ] **Step 3: Create the package and implement `tree.py`**

Create `obs_youtube_uploader/evesettings/__init__.py`:

```python
"""EVE Online settings management: browse, copy, back up, restore.

Ported from TriffView (GPL-3.0-only). See eve-settings-design.md for what
was deliberately not carried across.
"""
```

Create `obs_youtube_uploader/evesettings/tree.py`:

```python
"""Discovery of EVE's settings tree, and containment checks over it.

Pure: scandir and stat, no mutation, no network. Every path that reaches a
destructive operation passes through require_under() first.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

# EVE's own three-level layout:
#   <root>/<server>/settings_<profile>/core_char_<id>.dat
_PROFILE_PREFIX = "settings_"
_KIND_PREFIXES = {"core_char_": "character", "core_user_": "account"}

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


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "CCP" / "EVE"
    return Path.home() / ".local" / "share" / "CCP" / "EVE"


def file_kind(path) -> str | None:
    """"character", "account", or None for anything else.

    The id must be ASCII digits: str.isdigit() is True for Arabic-Indic and
    other Unicode numerals, none of which can be an EVE id.
    """
    name = Path(path).name
    if not name.endswith(".dat"):
        return None
    stem = name[:-len(".dat")]
    for prefix, kind in _KIND_PREFIXES.items():
        if stem.startswith(prefix):
            ident = stem[len(prefix):]
            if ident and ident.isascii() and ident.isdigit():
                return kind
            return None
    return None


def file_id(path) -> str:
    stem = Path(path).name[:-len(".dat")]
    for prefix in _KIND_PREFIXES:
        if stem.startswith(prefix):
            return stem[len(prefix):]
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


def _has_profiles(path) -> bool:
    entries, _ = _scan(path)
    return any(e.is_dir() and _is_profile_dir(e.path) for e in entries)


def _servers_in(root) -> tuple[list, bool]:
    entries, unreadable = _scan(root)
    found = []
    # The root itself counts as a server candidate: some installs put
    # settings_* directly under it.
    if _has_profiles(root):
        key, display = _shard(Path(root).name)
        found.append(Server(Path(root), display, key))
    for entry in entries:
        if not entry.is_dir():
            continue
        name = Path(entry.path).name
        if _has_profiles(entry.path) or _shard(name)[0] != name:
            key, display = _shard(name)
            found.append(Server(Path(entry.path), display, key))
    found.sort(key=lambda s: (s.key != "tranquility", s.name.lower()))
    return found, unreadable


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
        found.append(Profile(path, path.name[len(_PROFILE_PREFIX):],
                             count, modified))
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
    if _has_profiles(root) and root.parent != root:
        # A server directory: keep it as the server, lift the root above it.
        return root.parent, root, Path(profile) if profile else None
    return (root,
            Path(server) if server else None,
            Path(profile) if profile else None)


def discover(root, server=None, profile=None) -> Tree:
    """The whole visible tree, with the selection resolved against it."""
    if root is None:
        return Tree()
    root, server, profile = normalize_selection(root, server, profile)
    servers, unreadable = _servers_in(root)
    chosen_server = None
    if server is not None:
        chosen_server = next((s.path for s in servers
                              if _real(s.path) == _real(server)), None)
    if chosen_server is None and servers:
        chosen_server = servers[0].path

    profiles, profiles_unreadable = ([], False)
    if chosen_server is not None:
        profiles, profiles_unreadable = _profiles_in(chosen_server)
    chosen_profile = None
    if profile is not None:
        chosen_profile = next((p.path for p in profiles
                               if _real(p.path) == _real(profile)), None)
    if chosen_profile is None and profiles:
        chosen_profile = profiles[0].path

    characters, accounts, files_unreadable = ([], [], False)
    if chosen_profile is not None:
        characters, accounts, files_unreadable = _files_in(chosen_profile)

    return Tree(root=root, server=chosen_server, profile=chosen_profile,
                servers=servers, profiles=profiles,
                characters=characters, accounts=accounts,
                unreadable=unreadable or profiles_unreadable
                or files_unreadable)
```

- [ ] **Step 4: Declare the package**

In `pyproject.toml`, extend the list at lines 64-68:

```toml
packages = [
    "obs_youtube_uploader",
    "obs_youtube_uploader.ui",
    "obs_youtube_uploader.preview",
    "obs_youtube_uploader.evesettings",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_evesettings_tree.py tests/test_packaging_completeness.py -v`
Expected: PASS. The packaging test is included deliberately — it is the one that catches a missing entry, and it fails only in the frozen build otherwise.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/evesettings/ pyproject.toml tests/test_evesettings_tree.py
git commit -m "feat(evesettings): discover EVE's settings tree, with containment"
```

---

### Task 3: `names.py` — ESI character-name resolution

**Files:**
- Create: `obs_youtube_uploader/evesettings/names.py`
- Test: `tests/test_evesettings_names.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - constants `names.RESOLVED`, `names.INVALID`, `names.TRANSIENT`
  - `names.classify(status: int, body: str) -> tuple[str, dict[int, str]]`
  - `names.resolve(ids, known_invalid: set[int], fetch) -> dict[int, str]` where `fetch(ids) -> tuple[str, dict[int, str]]`
  - `names.fetch_batch(ids, *, transport=urllib.request.urlopen, timeout=8.0) -> tuple[str, dict[int, str]]`
  - `names.NameCache` with `.names: dict[int, str]`, `.invalid: set[int]`, `.resolve_missing(ids, fetch=fetch_batch) -> bool`

**Decision recorded here, not in the spec:** the cache is in-memory for the
process lifetime, matching TriffView's `_characterNames`. Names cost one
batch call per launch and are cosmetic; a disk cache would add a corrupt-file
recovery path for data that is free to re-fetch.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evesettings_names.py`:

```python
"""ESI universe/names. The transport is injected everywhere, so nothing here
touches the network."""
import json

import pytest

from obs_youtube_uploader.evesettings import names


def test_classify_reads_a_successful_body():
    body = json.dumps([{"id": 1, "name": "Pilot One"},
                       {"id": 2, "name": "Pilot Two"}])
    outcome, resolved = names.classify(200, body)
    assert outcome == names.RESOLVED
    assert resolved == {1: "Pilot One", 2: "Pilot Two"}


def test_classify_treats_a_json_error_404_as_invalid_ids():
    outcome, _ = names.classify(404, json.dumps({"error": "not found"}))
    assert outcome == names.INVALID


def test_classify_treats_a_plain_text_404_as_transient():
    """A route-level 404 says nothing about the ids. Bisecting on it would
    permanently blacklist every character the user has."""
    outcome, _ = names.classify(404, "page not found")
    assert outcome == names.TRANSIENT


def test_classify_treats_an_empty_error_404_as_transient():
    outcome, _ = names.classify(404, json.dumps({"error": "   "}))
    assert outcome == names.TRANSIENT


@pytest.mark.parametrize("status", [420, 429, 500, 502, 503])
def test_classify_treats_other_failures_as_transient(status):
    outcome, _ = names.classify(status, "")
    assert outcome == names.TRANSIENT


def test_classify_treats_unparseable_success_as_transient():
    outcome, _ = names.classify(200, "not json")
    assert outcome == names.TRANSIENT


def test_classify_drops_entries_with_no_usable_name():
    body = json.dumps([{"id": 1, "name": "  "}, {"id": 0, "name": "x"},
                       {"id": 3, "name": "Pilot"}])
    _, resolved = names.classify(200, body)
    assert resolved == {3: "Pilot"}


def test_resolve_returns_names_from_one_clean_batch():
    def fetch(ids):
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    assert names.resolve([1, 2], set(), fetch) == {1: "Pilot 1", 2: "Pilot 2"}


def test_resolve_bisects_to_isolate_a_bad_id():
    bad = 3

    def fetch(ids):
        if bad in ids:
            return names.INVALID, {}
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    invalid = set()
    resolved = names.resolve([1, 2, 3, 4], invalid, fetch)
    assert invalid == {bad}
    assert resolved == {1: "Pilot 1", 2: "Pilot 2", 4: "Pilot 4"}


def test_resolve_never_poisons_the_cache_on_a_transient_failure():
    def fetch(ids):
        return names.TRANSIENT, {}

    invalid = set()
    assert names.resolve([1, 2, 3], invalid, fetch) == {}
    assert invalid == set()


def test_resolve_does_not_bisect_a_transient_failure():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.TRANSIENT, {}

    names.resolve([1, 2, 3, 4], set(), fetch)
    assert calls == [[1, 2, 3, 4]]


def test_resolve_skips_ids_already_known_invalid():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    names.resolve([1, 2], {2}, fetch)
    assert calls == [[1]]


def test_resolve_deduplicates_and_drops_non_positive_ids():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.RESOLVED, {}

    names.resolve([1, 1, 0, -5, 2], set(), fetch)
    assert calls == [[1, 2]]


def test_resolve_with_nothing_to_do_makes_no_call():
    def fetch(ids):  # pragma: no cover - must never run
        raise AssertionError("should not be called")

    assert names.resolve([], set(), fetch) == {}


def test_cache_reports_whether_it_learned_anything():
    cache = names.NameCache()

    def fetch(ids):
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    assert cache.resolve_missing([1], fetch=fetch) is True
    assert cache.names == {1: "Pilot 1"}
    # Second pass has nothing missing, so nothing was learned.
    assert cache.resolve_missing([1], fetch=fetch) is False


def test_cache_labels_unresolved_ids_with_a_fallback():
    cache = names.NameCache()
    assert cache.label(98123456) == "Character 98123456"
    cache.names[98123456] = "Pilot"
    assert cache.label(98123456) == "Pilot"


def test_fetch_batch_classifies_an_http_error(monkeypatch):
    import urllib.error

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            self.code = 404

        def read(self):
            return json.dumps({"error": "not found"}).encode()

    def transport(request, timeout=None):
        raise FakeError()

    outcome, _ = names.fetch_batch([1], transport=transport)
    assert outcome == names.INVALID


def test_fetch_batch_treats_a_network_error_as_transient():
    def transport(request, timeout=None):
        raise OSError("no route to host")

    outcome, _ = names.fetch_batch([1], transport=transport)
    assert outcome == names.TRANSIENT


def test_fetch_batch_posts_the_ids_as_json():
    seen = {}

    class FakeResponse:
        status = 200

        def read(self):
            return json.dumps([{"id": 1, "name": "Pilot"}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def transport(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        return FakeResponse()

    outcome, resolved = names.fetch_batch([1], transport=transport)
    assert outcome == names.RESOLVED and resolved == {1: "Pilot"}
    assert seen["body"] == [1]
    assert "universe/names" in seen["url"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_evesettings_names.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.evesettings.names'`

- [ ] **Step 3: Implement `names.py`**

Create `obs_youtube_uploader/evesettings/names.py`:

```python
"""Character id -> name, against ESI's universe/names.

Unauthenticated: no SSO, no token, no scopes. Names are cosmetic and every
failure degrades to "Character 98123456", so the tool is fully usable offline.

The endpoint rejects an ENTIRE batch with 404 when one id in it is
unresolvable, so a rejection identifies no particular id -- hence the bisect.
The trap is that ESI also 404s a moved or renamed route, and treating that as
invalid-ids would blacklist every character the user has. The two are
separated by response shape, not wording, so CCP can reword the message.
"""
import json
import urllib.error
import urllib.request

from .. import __version__ as _version

ESI_URL = ("https://esi.evetech.net/latest/universe/names/"
           "?datasource=tranquility")
_USER_AGENT = f"FlyGD-Wingman/{_version} (+https://wingman.zoolanders.vip/)"
_TIMEOUT_SECONDS = 8.0
# ESI's documented cap for this endpoint.
MAX_BATCH = 1000

RESOLVED = "resolved"
INVALID = "invalid"
TRANSIENT = "transient"


def _is_invalid_ids_body(body: str) -> bool:
    """A JSON object carrying a non-empty "error" string.

    Matched on shape rather than exact wording: the alternative is a
    plain-text gateway body, and a reworded message must not start
    blacklisting ids.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return False
    error = parsed.get("error") if isinstance(parsed, dict) else None
    return isinstance(error, str) and bool(error.strip())


def classify(status: int, body: str) -> tuple[str, dict]:
    if status == 404:
        return (INVALID if _is_invalid_ids_body(body) else TRANSIENT), {}
    if not 200 <= status < 300:
        return TRANSIENT, {}
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return TRANSIENT, {}
    if not isinstance(parsed, list):
        return TRANSIENT, {}
    resolved = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        ident, name = item.get("id"), item.get("name")
        if (isinstance(ident, int) and not isinstance(ident, bool)
                and ident > 0 and isinstance(name, str) and name.strip()):
            resolved[ident] = name.strip()
    return RESOLVED, resolved


def fetch_batch(ids, *, transport=urllib.request.urlopen,
                timeout: float = _TIMEOUT_SECONDS) -> tuple[str, dict]:
    payload = json.dumps(list(ids)).encode("utf-8")
    request = urllib.request.Request(
        ESI_URL, data=payload,
        headers={"Content-type": "application/json",
                 "User-agent": _USER_AGENT},
        method="POST")
    try:
        with transport(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a body we cannot read is not a verdict
            body = ""
        return classify(exc.code, body)
    except Exception:  # noqa: BLE001 - reported as transient, never raised
        return TRANSIENT, {}
    return classify(status, body)


def resolve(ids, known_invalid: set, fetch) -> dict:
    """Names for *ids*, bisecting around any the endpoint rejects."""
    candidates = [i for i in dict.fromkeys(ids)
                  if isinstance(i, int) and i > 0 and i not in known_invalid]
    resolved: dict = {}
    for start in range(0, len(candidates), MAX_BATCH):
        _resolve_batch(candidates[start:start + MAX_BATCH],
                       known_invalid, fetch, resolved)
    return resolved


def _resolve_batch(ids, known_invalid: set, fetch, resolved: dict) -> None:
    if not ids:
        return
    outcome, names = fetch(ids)
    if outcome == RESOLVED:
        resolved.update(names)
        return
    if outcome == TRANSIENT:
        # Says nothing about validity: leave them unresolved and try again
        # on the next pass. Never bisect, never remember.
        return
    if len(ids) == 1:
        known_invalid.add(ids[0])
        return
    half = len(ids) // 2
    _resolve_batch(ids[:half], known_invalid, fetch, resolved)
    _resolve_batch(ids[half:], known_invalid, fetch, resolved)


class NameCache:
    """Process-lifetime memo. Names are free to re-fetch on the next launch."""

    def __init__(self):
        self.names: dict = {}
        self.invalid: set = set()

    def resolve_missing(self, ids, fetch=fetch_batch) -> bool:
        """Resolve what is not cached. True when at least one name was new."""
        missing = [i for i in ids
                   if i not in self.names and i not in self.invalid]
        if not missing:
            return False
        found = resolve(missing, self.invalid, fetch)
        self.names.update(found)
        return bool(found)

    def label(self, character_id: int) -> str:
        return self.names.get(character_id, f"Character {character_id}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_evesettings_names.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/evesettings/names.py tests/test_evesettings_names.py
git commit -m "feat(evesettings): resolve character names, bisecting ESI batch rejections"
```

---

### Task 4: `backup.py` — archives, listing, pruning, restore

**Files:**
- Create: `obs_youtube_uploader/evesettings/backup.py`
- Test: `tests/test_evesettings_backup.py`

**Interfaces:**
- Consumes: `tree.require_under`, `tree.file_kind`.
- Produces:
  - `backup.MANIFEST_NAME`
  - `backup.BackupInfo(path, created, seq, origin, kind, src, stem)`
  - `backup.source_key(profile_dir) -> str` (8 hex chars)
  - `backup.parse_name(name: str) -> BackupInfo | None`
  - `backup.create_file_backup(backup_dir, source, *, origin, now=None) -> Path`
  - `backup.create_profile_backup(backup_dir, profile, *, origin, now=None) -> Path`
  - `backup.enumerate_backups(backup_dir) -> list[BackupInfo]`
  - `backup.prune(backup_dir, keep: int) -> list[Path]`
  - `backup.restore(backup_dir, archive, root) -> Path`
  - `backup.delete(backup_dir, archive) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evesettings_backup.py`:

```python
"""Archive naming, integrity, pruning and restore. All on tmp_path."""
import zipfile
from datetime import datetime, timezone

import pytest

from obs_youtube_uploader.evesettings import backup


def at(second=0):
    return datetime(2026, 8, 24, 12, 34, second, tzinfo=timezone.utc)


def profile_with(tmp_path, name="settings_Default",
                 files=("core_char_98123456.dat",)):
    target = tmp_path / "root" / "server" / name
    target.mkdir(parents=True)
    for filename in files:
        (target / filename).write_bytes(b"payload-" + filename.encode())
    return target


def test_source_key_is_stable_and_short(tmp_path):
    key = backup.source_key(tmp_path)
    assert key == backup.source_key(tmp_path)
    assert len(key) == 8 and all(c in "0123456789abcdef" for c in key)


def test_source_key_differs_between_profiles(tmp_path):
    a = tmp_path / "settings_Default"
    b = tmp_path / "settings_Alt"
    a.mkdir()
    b.mkdir()
    assert backup.source_key(a) != backup.source_key(b)


def test_parse_name_round_trips_a_created_archive(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="auto", now=at())
    info = backup.parse_name(made.name)
    assert info.origin == "auto" and info.kind == "character"
    assert info.stem == "core_char_98123456"
    assert info.src == backup.source_key(profile)


def test_parse_name_rejects_a_foreign_file():
    assert backup.parse_name("holiday-photos.zip") is None
    assert backup.parse_name("20260824-123456-000-auto-character-xx-stem.zip") is None


def test_parse_name_keeps_hyphens_in_the_stem():
    name = "20260824-123456-000-manual-profile-a1b2c3d4-my-odd-profile.zip"
    info = backup.parse_name(name)
    assert info.stem == "my-odd-profile" and info.kind == "profile"


def test_two_backups_in_the_same_second_both_survive(tmp_path):
    """Second-granularity names collide; TriffView's loop dies on the second
    one, leaving a multi-target copy half-applied."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    first = backup.create_file_backup(store, source, origin="auto", now=at())
    second = backup.create_file_backup(store, source, origin="auto", now=at())
    assert first != second
    assert first.exists() and second.exists()
    assert len(backup.enumerate_backups(store)) == 2


def test_a_failed_build_leaves_nothing_listable(tmp_path):
    """A truncated archive under its final name would list as restorable."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(backup.shutil, "copyfileobj", explode)
    try:
        with pytest.raises(OSError):
            backup.create_file_backup(store, source, origin="auto", now=at())
    finally:
        monkey.undo()
    assert backup.enumerate_backups(store) == []
    assert list(store.iterdir()) == []


def test_backup_contains_the_file_and_a_manifest(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_98123456.dat", backup.MANIFEST_NAME]


def test_profile_backup_holds_every_settings_file(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",
                                            "core_user_2.dat",
                                            "notes.txt"))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_1.dat", "core_user_2.dat", backup.MANIFEST_NAME]


def test_prune_keeps_the_newest_auto_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(5):
        backup.create_file_backup(store, source, origin="auto", now=at(second))
    removed = backup.prune(store, keep=2)
    assert len(removed) == 3
    assert len(backup.enumerate_backups(store)) == 2


def test_prune_never_touches_manual_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(4):
        backup.create_file_backup(store, source, origin="manual",
                                  now=at(second))
    assert backup.prune(store, keep=1) == []
    assert len(backup.enumerate_backups(store)) == 4


def test_prune_does_not_cross_profiles_for_the_same_character(tmp_path):
    """core_char_<id>.dat exists in EVERY settings set. Grouping by stem
    alone would let one profile's backups evict another's."""
    default = profile_with(tmp_path, name="settings_Default")
    alt = profile_with(tmp_path, name="settings_Alt")
    store = tmp_path / "backups"
    for second in range(3):
        backup.create_file_backup(store, default / "core_char_98123456.dat",
                                  origin="auto", now=at(second))
    backup.create_file_backup(store, alt / "core_char_98123456.dat",
                              origin="auto", now=at(9))
    backup.prune(store, keep=1)
    remaining = backup.enumerate_backups(store)
    assert len(remaining) == 2
    assert {info.src for info in remaining} == {
        backup.source_key(default), backup.source_key(alt)}


def test_restore_puts_the_file_back(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    made = backup.create_file_backup(store, source, origin="manual", now=at())
    source.write_bytes(b"clobbered")
    backup.restore(store, made, tmp_path / "root")
    assert source.read_bytes() == b"payload-core_char_98123456.dat"


def test_profile_restore_removes_files_absent_from_the_archive(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    (profile / "core_char_2.dat").write_bytes(b"added later")
    backup.restore(store, made, tmp_path / "root")
    assert (profile / "core_char_1.dat").exists()
    assert not (profile / "core_char_2.dat").exists()


def test_profile_restore_backs_up_before_deleting(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    backup.restore(store, made, tmp_path / "root", now=at(5))
    autos = [i for i in backup.enumerate_backups(store) if i.origin == "auto"]
    assert len(autos) == 1


def test_restore_rejects_an_archive_with_a_path_bearing_entry(tmp_path):
    """Validation is complete and up front, so a bad archive cannot leave
    the profile emptied and half-repopulated."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = store / "20260824-123456-000-manual-profile-{}-Default.zip".format(
        backup.source_key(profile))
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(backup.MANIFEST_NAME, '{"kind": "profile", '
                         '"source": "%s"}' % profile.as_posix())
        archive.writestr("../escape.dat", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")
    assert (profile / "core_char_98123456.dat").exists()


def test_restore_rejects_an_unexpected_member(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = store / "20260824-123456-000-manual-profile-{}-Default.zip".format(
        backup.source_key(profile))
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(backup.MANIFEST_NAME, '{"kind": "profile", '
                         '"source": "%s"}' % profile.as_posix())
        archive.writestr("payload.exe", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")


def test_restore_rejects_a_target_outside_the_current_root(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    with pytest.raises(ValueError):
        backup.restore(store, made, tmp_path / "elsewhere")


def test_delete_removes_one_archive(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    backup.delete(store, made)
    assert backup.enumerate_backups(store) == []


def test_delete_refuses_a_path_outside_the_backup_folder(tmp_path):
    store = tmp_path / "backups"
    store.mkdir()
    outsider = tmp_path / "important.zip"
    outsider.write_bytes(b"x")
    with pytest.raises(ValueError):
        backup.delete(store, outsider)
    assert outsider.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_evesettings_backup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.evesettings.backup'`

- [ ] **Step 3: Implement `backup.py`**

Create `obs_youtube_uploader/evesettings/backup.py`:

```python
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
from datetime import datetime, timezone
from pathlib import Path

from . import tree

MANIFEST_NAME = "wingman-eve-settings-backup.json"

_ORIGINS = ("auto", "manual")
_KINDS = ("character", "account", "profile")
_NAME_RE = re.compile(
    r"^(?P<date>\d{8})-(?P<time>\d{6})-(?P<seq>\d{3})"
    r"-(?P<origin>auto|manual)"
    r"-(?P<kind>character|account|profile)"
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
    now = now or datetime.now(timezone.utc)
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
    if label.startswith("settings_"):
        label = label[len("settings_"):]
    claimed = _claim(Path(backup_dir), _stamp(now), origin, "profile",
                     source_key(profile), _sanitize(label))
    _write_archive(claimed, members, {
        "kind": "profile",
        "source": str(profile),
        "profile": str(profile),
        "created": _stamp(now),
    })
    return claimed


def enumerate_backups(backup_dir) -> list:
    backup_dir = Path(backup_dir)
    found = []
    try:
        entries = list(os.scandir(str(backup_dir)))
    except (FileNotFoundError, OSError):
        return found
    for entry in entries:
        if not entry.is_file():
            continue
        info = parse_name(Path(entry.path).name)
        if info is None:
            continue
        found.append(BackupInfo(Path(entry.path), info.created, info.seq,
                                info.origin, info.kind, info.src, info.stem))
    found.sort(key=lambda i: (i.created, i.seq), reverse=True)
    return found


def prune(backup_dir, keep: int) -> list:
    """Drop all but the newest *keep* auto-backups per (kind, src, stem)."""
    groups: dict = {}
    for info in enumerate_backups(backup_dir):
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

    with zipfile.ZipFile(archive_path) as archive:
        members = _validated_members(archive)
        if kind == "profile":
            create_profile_backup(backup_dir, target_dir, origin="auto",
                                  now=now)
            for existing in target_dir.iterdir():
                if tree.file_kind(existing):
                    existing.unlink()
        else:
            if source.exists():
                create_file_backup(backup_dir, source, origin="auto", now=now)
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in members:
            # Belt and braces behind _validated_members: basename again on
            # the way out, so nothing can escape even if validation grows a
            # hole later.
            destination = target_dir / Path(name).name
            with archive.open(name) as entry, \
                    open(destination, "wb") as handle:
                shutil.copyfileobj(entry, handle)
    return target_dir


def delete(backup_dir, archive_path) -> None:
    target = tree.require_under(backup_dir, archive_path, suffix=".zip")
    target.unlink()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_evesettings_backup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/evesettings/backup.py tests/test_evesettings_backup.py
git commit -m "feat(evesettings): backup archives with staged writes and per-source pruning"
```

---

### Task 5: `ops.py` — copy one onto many

**Files:**
- Create: `obs_youtube_uploader/evesettings/ops.py`
- Test: `tests/test_evesettings_ops.py`

**Interfaces:**
- Consumes: `tree.file_kind`, `atomicio.copy_atomic`.
- Produces:
  - `ops.TargetOutcome(path: Path, ok: bool, reason: str)`
  - `ops.CopyReport(outcomes: list)` with `.succeeded -> list`, `.failed -> list`
  - `ops.copy_to_targets(source, targets, *, backup, copy=atomicio.copy_atomic) -> CopyReport`, where `backup(path) -> None` raises on failure

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evesettings_ops.py`:

```python
"""Copy one settings file onto many. Backup and copy are both injected, so
every failure path is reachable without a real filesystem fault."""
import pytest

from obs_youtube_uploader.evesettings import ops


def make(tmp_path, name, body=b"payload"):
    path = tmp_path / name
    path.write_bytes(body)
    return path


def test_copies_to_every_target(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    targets = [make(tmp_path, "core_char_2.dat"),
               make(tmp_path, "core_char_3.dat")]
    report = ops.copy_to_targets(source, targets, backup=lambda _p: None)
    assert len(report.succeeded) == 2 and report.failed == []
    assert all(t.read_bytes() == b"source" for t in targets)


def test_backs_up_each_target_before_writing(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")
    seen = []

    def record(path):
        seen.append(path.read_bytes())

    ops.copy_to_targets(source, [target], backup=record)
    assert seen == [b"original"]


def test_refuses_a_kind_mismatch(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    target = make(tmp_path, "core_user_2.dat")
    report = ops.copy_to_targets(source, [target], backup=lambda _p: None)
    assert report.succeeded == [] and len(report.failed) == 1
    assert "account" in report.failed[0].reason


def test_refuses_a_source_that_is_not_a_settings_file(tmp_path):
    source = make(tmp_path, "notes.txt")
    target = make(tmp_path, "core_char_2.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [target], backup=lambda _p: None)


def test_excludes_the_source_from_its_own_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    other = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [source, other],
                                 backup=lambda _p: None)
    assert [o.path for o in report.succeeded] == [other]


def test_collapses_duplicate_targets(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")
    report = ops.copy_to_targets(source, [target, target],
                                 backup=lambda _p: None)
    assert len(report.outcomes) == 1


def test_a_failing_backup_leaves_the_target_untouched(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat", b"original")

    def refuse(_path):
        raise OSError("disk full")

    report = ops.copy_to_targets(source, [target], backup=refuse)
    assert report.succeeded == [] and len(report.failed) == 1
    assert target.read_bytes() == b"original"


def test_a_failing_write_is_reported_and_the_loop_continues(tmp_path):
    """TriffView throws on the first failure, leaving an unknown mix of
    copied and uncopied targets."""
    source = make(tmp_path, "core_char_1.dat", b"source")
    first = make(tmp_path, "core_char_2.dat")
    second = make(tmp_path, "core_char_3.dat")
    attempted = []

    def flaky(src, dst, **kwargs):
        attempted.append(dst)
        if dst == first:
            raise PermissionError(32, "in use")
        dst.write_bytes(src.read_bytes())

    report = ops.copy_to_targets(source, [first, second],
                                 backup=lambda _p: None, copy=flaky)
    assert attempted == [first, second]
    assert [o.path for o in report.succeeded] == [second]
    assert [o.path for o in report.failed] == [first]


def test_a_locked_target_explains_what_to_do(tmp_path):
    source = make(tmp_path, "core_char_1.dat", b"source")
    target = make(tmp_path, "core_char_2.dat")

    def locked(src, dst, **kwargs):
        raise PermissionError(32, "in use")

    report = ops.copy_to_targets(source, [target],
                                 backup=lambda _p: None, copy=locked)
    assert "close eve" in report.failed[0].reason.lower()


def test_no_targets_is_an_error(tmp_path):
    source = make(tmp_path, "core_char_1.dat")
    with pytest.raises(ValueError):
        ops.copy_to_targets(source, [], backup=lambda _p: None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_evesettings_ops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.evesettings.ops'`

- [ ] **Step 3: Implement `ops.py`**

Create `obs_youtube_uploader/evesettings/ops.py`:

```python
"""Copy one settings file onto many, reporting per target.

The loop never aborts. TriffView throws on the first failure, leaving an
unknown mix of copied and uncopied targets and discarding the count it
computed; library.delete's (deleted, failures) shape is the one followed here.
"""
from dataclasses import dataclass, field
from pathlib import Path

from .. import atomicio
from . import tree


@dataclass(frozen=True)
class TargetOutcome:
    path: Path
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class CopyReport:
    outcomes: list = field(default_factory=list)

    @property
    def succeeded(self) -> list:
        return [o for o in self.outcomes if o.ok]

    @property
    def failed(self) -> list:
        return [o for o in self.outcomes if not o.ok]


def _describe(error: BaseException) -> str:
    if isinstance(error, PermissionError):
        # The visible cost of temp-then-replace: os.replace needs
        # FILE_SHARE_DELETE, which EVE does not grant while it is running.
        # Reported as an instruction rather than an OS error code.
        return "The file is in use. Close EVE and retry."
    return str(error) or error.__class__.__name__


def copy_to_targets(source, targets, *, backup,
                    copy=atomicio.copy_atomic) -> CopyReport:
    """Copy *source* onto each of *targets*, backing each one up first.

    `backup` is called with the target path before it is overwritten and
    must raise on failure -- a target whose backup could not be taken is
    skipped untouched rather than overwritten unprotected.
    """
    source = Path(source)
    source_kind = tree.file_kind(source)
    if source_kind is None:
        raise ValueError("Only EVE settings files can be copied.")

    chosen = []
    seen = set()
    for candidate in targets:
        candidate = Path(candidate)
        key = str(candidate).casefold()
        if key in seen or candidate == source:
            continue
        seen.add(key)
        chosen.append(candidate)
    if not chosen:
        raise ValueError("Choose at least one target to copy to.")

    outcomes = []
    for target in chosen:
        target_kind = tree.file_kind(target)
        if target_kind != source_kind:
            outcomes.append(TargetOutcome(
                target, False,
                f"Cannot copy {source_kind} settings onto "
                f"{target_kind or 'an unknown file'}."))
            continue
        if target.exists():
            try:
                backup(target)
            except Exception as error:  # noqa: BLE001 - reported per target
                outcomes.append(TargetOutcome(
                    target, False,
                    f"Skipped: its backup could not be made. {_describe(error)}"))
                continue
        try:
            copy(source, target)
        except Exception as error:  # noqa: BLE001 - reported per target
            outcomes.append(TargetOutcome(target, False, _describe(error)))
            continue
        outcomes.append(TargetOutcome(target, True))
    return CopyReport(outcomes)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_evesettings_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/evesettings/ops.py tests/test_evesettings_ops.py
git commit -m "feat(evesettings): copy one settings file onto many, reporting per target"
```

---

### Task 6: Settings section and a merging writer

**Files:**
- Modify: `obs_youtube_uploader/settings.py`
- Modify: `obs_youtube_uploader/paths.py`
- Test: `tests/test_settings_evesettings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `settings._eve_settings_defaults() -> dict`
  - `settings.validated_eve_settings(raw) -> dict`
  - `settings.update_section(name: str, values: dict, path=None) -> dict`
  - `paths.eve_settings_backup_dir() -> Path`
  - `DEFAULTS["eve_settings"]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_evesettings.py`:

```python
"""EVE Settings section validation. Mirrors test_settings_preview.py."""
import json

import pytest

from obs_youtube_uploader import paths, settings


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_whole_section_of_wrong_type_falls_back(raw):
    assert settings.validated_eve_settings(raw) == settings._eve_settings_defaults()


def test_unknown_keys_are_dropped():
    out = settings.validated_eve_settings({"root": "C:\\EVE", "nonsense": 1})
    assert "nonsense" not in out and out["root"] == "C:\\EVE"


def test_defaults_are_a_fresh_dict_every_call():
    """dict(DEFAULTS) is shallow; handing callers the module global would
    let one mutation leak into every later load."""
    first = settings._eve_settings_defaults()
    first["root"] = "mutated"
    assert settings._eve_settings_defaults()["root"] is None


def test_blank_paths_fall_back_to_none():
    out = settings.validated_eve_settings({"root": "   ", "server": ""})
    assert out["root"] is None and out["server"] is None


def test_non_string_paths_fall_back_to_none():
    out = settings.validated_eve_settings({"root": 7, "profile": ["x"]})
    assert out["root"] is None and out["profile"] is None


@pytest.mark.parametrize("given,expected", [(0, 1), (500, 100), (25, 25)])
def test_auto_keep_is_clamped_not_rejected(given, expected):
    assert settings.validated_eve_settings({"auto_keep": given})["auto_keep"] == expected


def test_booleans_are_not_accepted_as_auto_keep():
    """bool is an int in Python; True would silently become a keep depth."""
    out = settings.validated_eve_settings({"auto_keep": True})
    assert out["auto_keep"] == settings._eve_settings_defaults()["auto_keep"]


def test_section_survives_a_load_save_round_trip(tmp_path):
    target = tmp_path / "settings.json"
    data = settings.load(target)
    data["eve_settings"]["root"] = "C:\\EVE"
    settings.save(data, target)
    assert settings.load(target)["eve_settings"]["root"] == "C:\\EVE"


def test_update_section_does_not_drop_another_writers_key(tmp_path):
    """_SAVE_LOCK covers the write, not the surrounding read-modify-write.
    A writer that saves a snapshot it built earlier silently reverts keys
    another writer set in between."""
    target = tmp_path / "settings.json"
    stale = settings.load(target)

    settings.update_section("eve_settings", {"root": "C:\\EVE"}, target)
    # `stale` predates that write. Merging must not resurrect its version.
    stale["discord_webhook"] = "https://example.invalid/hook"
    settings.update_section("eve_settings", {"server": "tq"}, target)

    live = settings.load(target)
    assert live["eve_settings"]["root"] == "C:\\EVE"
    assert live["eve_settings"]["server"] == "tq"


def test_update_section_returns_the_live_document(tmp_path):
    target = tmp_path / "settings.json"
    live = settings.update_section("eve_settings", {"root": "C:\\EVE"}, target)
    assert live["eve_settings"]["root"] == "C:\\EVE"


def test_a_corrupt_section_does_not_take_the_file_down(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"eve_settings": "garbage",
                                  "privacy": "public"}))
    loaded = settings.load(target)
    assert loaded["eve_settings"] == settings._eve_settings_defaults()
    assert loaded["privacy"] == "public"


def test_backup_dir_sits_beside_the_other_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.eve_settings_backup_dir().parent == paths.state_dir()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings_evesettings.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.settings' has no attribute 'validated_eve_settings'`

- [ ] **Step 3: Add the section, the merging writer, and the backup path**

In `obs_youtube_uploader/paths.py`, add after `durations_file()`:

```python
def eve_settings_backup_dir() -> Path:
    """Where EVE settings backups live.

    Beside settings.json and the token, never inside the EVE tree: that
    directory belongs to CCP, and writing archives into it risks confusing
    the launcher and losing every backup to a reinstall.
    """
    return state_dir() / "eve-settings-backups"
```

In `obs_youtube_uploader/settings.py`, add after `_preview_defaults()`:

```python
def _eve_settings_defaults() -> dict:
    """Fresh nested structure every call. Never return the module global."""
    # Three remembered paths and the prune depth. Everything else is derived
    # from disk on each state build, so there is nothing to migrate and
    # nothing that can drift out of step with reality.
    return {"root": None, "server": None, "profile": None, "auto_keep": 10}
```

Add to `DEFAULTS`, after the `"preview"` entry:

```python
    # Same reasoning as eve_bookmarks and preview above: built by
    # _eve_settings_defaults() so callers never share one nested dict.
    "eve_settings": _eve_settings_defaults(),
```

Extend `_fresh_defaults()`:

```python
def _fresh_defaults() -> dict:
    """dict(DEFAULTS) is shallow, so the nested sections are rebuilt."""
    data = dict(DEFAULTS)
    data["eve_bookmarks"] = _eve_defaults()
    data["preview"] = _preview_defaults()
    data["eve_settings"] = _eve_settings_defaults()
    return data
```

Add the validator beside `validated_preview`:

```python
def validated_eve_settings(raw) -> dict:
    """Same posture as validated_preview: a malformed section falls back
    whole, and a malformed single value falls back alone."""
    section = _eve_settings_defaults()
    if not isinstance(raw, dict):
        return section
    for key in ("root", "server", "profile"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            section[key] = value
    keep = raw.get("auto_keep")
    # `not isinstance(keep, bool)` because bool is an int in Python, and
    # True would silently become a keep depth of 1.
    if isinstance(keep, int) and not isinstance(keep, bool):
        # Clamped, not rejected: a depth of zero would delete the backup
        # taken moments earlier, which is the one nobody can afford to lose.
        section["auto_keep"] = max(1, min(100, keep))
    return section
```

Add the call in `load()`, beside the other two:

```python
    data["eve_settings"] = validated_eve_settings(raw.get("eve_settings"))
```

Finally, add the merging writer after `_save_locked`:

```python
def update_section(name: str, values: dict, path: Path | None = None) -> dict:
    """Merge *values* into one section, reading live under the save lock.

    _SAVE_LOCK serializes the projection and the write; it does NOT make the
    surrounding read-modify-write atomic. A caller that builds a payload from
    a snapshot and then saves it silently reverts any key another writer set
    in between -- and because save() projects the complete document from
    DEFAULTS, that is a quietly reverted setting rather than a corrupt file.

    preview/store.py:56-68 solves this the same way: re-read, merge, save.
    """
    with _SAVE_LOCK:
        live = load(path)
        section = dict(live.get(name) or {})
        section.update(values)
        live[name] = section
        _save_locked(live, path)
        return live
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_settings_evesettings.py tests/test_settings.py tests/test_paths.py -v`
Expected: PASS. `tests/test_settings.py` is included because it compares `load()` against `DEFAULTS`, and a new key must not break it.

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/settings.py obs_youtube_uploader/paths.py tests/test_settings_evesettings.py
git commit -m "feat(settings): add the eve_settings section and a merging section writer"
```

---

### Task 7: Bridge methods and the mutation lock

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py`
- Test: `tests/test_api_evesettings.py`

**Interfaces:**
- Consumes: everything from Tasks 2-6.
- Produces, on `Api`:
  - `eve_settings_state() -> dict`
  - `eve_settings_pick_root() -> str`
  - `eve_settings_select(server: str, profile: str) -> bool`
  - `eve_settings_copy(source: str, targets: list) -> bool`
  - `eve_settings_backup(path: str, kind: str) -> bool`
  - `eve_settings_restore(archive: str) -> bool`
  - `eve_settings_delete_backup(archive: str) -> bool`
  - push handler name `onEveSettingsNames`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_evesettings.py`:

```python
"""The bridge is tested headless through FakeWindow (tests/fakes.py)."""
import threading

import pytest

from obs_youtube_uploader import settings
from obs_youtube_uploader.ui import api as api_mod
from tests.fakes import FakeWindow


class ImmediateThread:
    """Runs the worker inline, so a test never races a real thread."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def build(tmp_path, monkeypatch, answer=True):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = api_mod.AppState()
    state.settings = settings.load(tmp_path / "settings.json")
    built = api_mod.Api(state, spawn=ImmediateThread)
    built._window = FakeWindow()
    built._confirm = lambda title, body: answer
    return built


def eve_tree(tmp_path, files=("core_char_1.dat", "core_char_2.dat")):
    profile = tmp_path / "EVE" / "server_tranquility" / "settings_Default"
    profile.mkdir(parents=True)
    for name in files:
        (profile / name).write_bytes(b"payload-" + name.encode())
    return profile


def test_state_is_empty_before_a_root_is_chosen(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    state = api.eve_settings_state()
    assert state["root"] == "" and state["characters"] == []


def test_state_lists_characters_once_a_root_is_set(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    state = api.eve_settings_state()
    assert {c["id"] for c in state["characters"]} == {"1", "2"}
    assert state["profile"] == str(profile)


def test_state_labels_unresolved_characters_with_their_id(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    state = api.eve_settings_state()
    assert state["characters"][0]["name"] == "Character 1"


def test_state_reports_an_unreadable_folder(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    eve_tree(tmp_path)

    def boom(_path):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(api_mod.evesettings_tree.os, "scandir", boom)
    assert api.eve_settings_state()["unreadable"] is True


def test_copy_writes_every_target(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_1.dat"


def test_copy_takes_a_backup_of_each_target(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert len(api.eve_settings_state()["backups"]) == 1


def test_copy_declined_at_the_prompt_changes_nothing(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch, answer=False)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_a_second_mutation_is_refused_while_one_holds_the_lock(tmp_path,
                                                               monkeypatch):
    """_confirm parks each worker independently, so without a lock two
    approved operations can interleave over the same files."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_mutation.acquire()
    try:
        accepted = api.eve_settings_copy(str(profile / "core_char_1.dat"),
                                          [str(profile / "core_char_2.dat")])
    finally:
        api._eve_mutation.release()
    assert accepted is False
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_the_lock_is_released_even_when_the_worker_raises(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_mod.evesettings_ops, "copy_to_targets", explode)
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_select_persists_through_the_merging_writer(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_select(str(profile.parent), str(profile))
    stored = settings.load(tmp_path / "OBSYouTubeUploader" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(profile)


def test_names_are_pushed_once_a_pass_resolves_something(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.resolve_missing = lambda ids, **kw: True
    api.eve_settings_resolve_names()
    assert any("onEveSettingsNames" in call for call in api._window.calls)


def test_no_push_when_a_pass_resolves_nothing(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.resolve_missing = lambda ids, **kw: False
    api.eve_settings_resolve_names()
    assert not any("onEveSettingsNames" in call for call in api._window.calls)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_api_evesettings.py -v`
Expected: FAIL with `AttributeError: 'Api' object has no attribute 'eve_settings_state'`

- [ ] **Step 3: Wire the bridge**

In `obs_youtube_uploader/ui/api.py`, add to the imports at the top:

```python
from ..evesettings import backup as evesettings_backup
from ..evesettings import names as evesettings_names
from ..evesettings import ops as evesettings_ops
from ..evesettings import tree as evesettings_tree
```

In `Api.__init__`, after `self._preview_host = preview_host`, add:

```python
        # One mutation at a time. A per-mutation worker says nothing about
        # how many may exist at once, and _confirm() parks each one
        # independently -- so two operations approved moments apart could
        # otherwise interleave over the same files.
        self._eve_mutation = threading.Lock()
        # Process-lifetime memo. Names are cosmetic and free to re-fetch.
        self._eve_names = evesettings_names.NameCache()
```

Add the methods to the page-facing section:

```python
    # ----- EVE Settings ---------------------------------------------------

    def _eve_section(self) -> dict:
        return self._state.settings.setdefault(
            "eve_settings", settings_mod._eve_settings_defaults())

    def eve_settings_state(self) -> dict:
        """The whole visible tree. Cheap enough to answer on the bridge
        thread: scandir over a few dozen files, and listing backups is one
        listdir with no archive opened."""
        section = self._eve_section()
        root = section.get("root")
        found = evesettings_tree.discover(root, section.get("server"),
                                          section.get("profile"))
        store = paths.eve_settings_backup_dir()

        def describe(record):
            name = (self._eve_names.label(int(record.file_id))
                    if record.kind == "character" and record.file_id.isdigit()
                    else f"Account {record.file_id}")
            return {"path": str(record.path), "id": record.file_id,
                    "name": name}

        return {
            "root": str(found.root) if found.root else "",
            "default_root": str(evesettings_tree.default_root()),
            "server": str(found.server) if found.server else "",
            "profile": str(found.profile) if found.profile else "",
            "unreadable": found.unreadable,
            "eve_running": self._eve_client_running(),
            "servers": [{"path": str(s.path), "name": s.name}
                        for s in found.servers],
            "profiles": [{"path": str(p.path), "name": p.name,
                          "file_count": p.file_count}
                         for p in found.profiles],
            "characters": [describe(c) for c in found.characters],
            "accounts": [describe(a) for a in found.accounts],
            "backups": [{"path": str(b.path), "created": b.created,
                         "origin": b.origin, "kind": b.kind, "stem": b.stem}
                        for b in evesettings_backup.enumerate_backups(store)],
        }

    def _eve_client_running(self) -> bool:
        """Advisory only -- nothing is blocked. preview.discovery already
        matches CLIENT_IMAGE ("exefile.exe"), handles an unopenable process
        as "not a client", and caches per PID."""
        try:
            from ..preview import discovery
            return bool(discovery.list_clients())
        except Exception:  # noqa: BLE001 - a pill, never a failure
            logger.debug("Could not check for a running EVE client",
                         exc_info=True)
            return False

    def eve_settings_pick_root(self) -> str:
        section = self._eve_section()
        start = str(section.get("root") or evesettings_tree.default_root())
        chosen = self._window.create_file_dialog(_folder_dialog_kind(),
                                                 directory=start)
        if not chosen:
            return ""
        picked = str(chosen[0])
        # Selection is cleared, not carried: the old server and profile
        # belong to a tree that is no longer the one on screen.
        settings_mod.update_section("eve_settings", {
            "root": picked, "server": None, "profile": None})
        self._state.settings = settings_mod.load()
        return picked

    def eve_settings_select(self, server: str, profile: str) -> bool:
        settings_mod.update_section("eve_settings", {
            "server": server or None, "profile": profile or None})
        self._state.settings = settings_mod.load()
        return True

    def eve_settings_resolve_names(self) -> None:
        """Resolve on a background thread, then tell the page to refetch.

        The one thing a request/response bridge cannot express on its own:
        the state that triggered this was already returned, carrying
        fallback ids. One push per pass, not per name.
        """
        def worker() -> None:
            try:
                found = evesettings_tree.discover(
                    self._eve_section().get("root"),
                    self._eve_section().get("server"),
                    self._eve_section().get("profile"))
                ids = [int(c.file_id) for c in found.characters
                       if c.file_id.isdigit()]
                if self._eve_names.resolve_missing(ids):
                    self._push("onEveSettingsNames", {})
            except Exception:  # noqa: BLE001 - names are cosmetic
                logger.warning("EVE character name lookup failed",
                               exc_info=True)

        self._spawn(target=worker, daemon=True).start()

    def _eve_begin(self, worker, args) -> bool:
        """Claim the mutation lock and hand the work to a thread.

        Refused rather than queued: a queued operation's own confirmation
        would describe state that has since changed.
        """
        if not self._eve_mutation.acquire(blocking=False):
            self._alert("warning", "EVE Settings busy",
                        "Another EVE Settings operation is still running.")
            return False
        self._spawn(target=worker, args=args, daemon=True).start()
        return True

    def _eve_auto_backup(self, target):
        store = paths.eve_settings_backup_dir()
        evesettings_backup.create_file_backup(store, target, origin="auto")

    def eve_settings_copy(self, source: str, targets: list) -> bool:
        return self._eve_begin(self._eve_copy_worker,
                               (source, [str(t) for t in targets or []]))

    def _eve_copy_worker(self, source: str, targets: list) -> None:
        try:
            if not self._confirm(
                    "Confirm Copy",
                    f"Copy these settings onto {len(targets)} other "
                    f"file(s)?\n\nEach one is backed up first.\n\n"
                    "This cannot be undone except by restoring a backup."):
                return
            report = evesettings_ops.copy_to_targets(
                source, targets, backup=self._eve_auto_backup)
            keep = int(self._eve_section().get("auto_keep", 10))
            evesettings_backup.prune(paths.eve_settings_backup_dir(), keep)
            if report.failed:
                names = "\n".join(f"  • {Path(o.path).stem}: {o.reason}"
                                  for o in report.failed)
                self._alert("error", "Some copies did not happen",
                            f"Copied to {len(report.succeeded)} of "
                            f"{len(report.outcomes)}.\n\n{names}")
            else:
                self._push("onStatus", {
                    "text": f"Copied to {len(report.succeeded)} file(s).",
                    "kind": "FG"})
        except Exception as error:  # noqa: BLE001 - reported, never raised
            logger.exception("EVE settings copy failed")
            self._alert("error", "Copy failed", str(error))
        finally:
            self._eve_mutation.release()

    def eve_settings_backup(self, path: str, kind: str) -> bool:
        return self._eve_begin(self._eve_backup_worker, (path, kind))

    def _eve_backup_worker(self, path: str, kind: str) -> None:
        try:
            store = paths.eve_settings_backup_dir()
            if kind == "profile":
                made = evesettings_backup.create_profile_backup(
                    store, path, origin="manual")
            else:
                made = evesettings_backup.create_file_backup(
                    store, path, origin="manual")
            self._push("onStatus", {"text": f"Backed up to {made.name}.",
                                    "kind": "FG"})
        except Exception as error:  # noqa: BLE001 - reported, never raised
            logger.exception("EVE settings backup failed")
            self._alert("error", "Backup failed", str(error))
        finally:
            self._eve_mutation.release()

    def eve_settings_restore(self, archive: str) -> bool:
        return self._eve_begin(self._eve_restore_worker, (archive,))

    def _eve_restore_worker(self, archive: str) -> None:
        try:
            if not self._confirm(
                    "Confirm Restore",
                    "Restore this backup?\n\nThe current settings are backed "
                    "up first. For a whole settings set, any file not in the "
                    "backup is removed."):
                return
            store = paths.eve_settings_backup_dir()
            root = self._eve_section().get("root")
            written = evesettings_backup.restore(store, archive, root)
            keep = int(self._eve_section().get("auto_keep", 10))
            evesettings_backup.prune(store, keep)
            self._push("onStatus", {"text": f"Restored into {written.name}.",
                                    "kind": "FG"})
        except Exception as error:  # noqa: BLE001 - reported, never raised
            logger.exception("EVE settings restore failed")
            self._alert("error", "Restore failed", str(error))
        finally:
            self._eve_mutation.release()

    def eve_settings_delete_backup(self, archive: str) -> bool:
        return self._eve_begin(self._eve_delete_backup_worker, (archive,))

    def _eve_delete_backup_worker(self, archive: str) -> None:
        try:
            if not self._confirm(
                    "Confirm Delete",
                    f"Permanently delete {Path(archive).name}?\n\n"
                    "This cannot be undone."):
                return
            evesettings_backup.delete(paths.eve_settings_backup_dir(), archive)
            self._push("onStatus", {"text": "Backup deleted.", "kind": "FG"})
        except Exception as error:  # noqa: BLE001 - reported, never raised
            logger.exception("EVE settings backup delete failed")
            self._alert("error", "Delete failed", str(error))
        finally:
            self._eve_mutation.release()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_api_evesettings.py tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/api.py tests/test_api_evesettings.py
git commit -m "feat(ui): expose EVE Settings on the bridge behind a mutation lock"
```

---

### Task 8: The route, and the smoke checklist

**Files:**
- Create: `obs_youtube_uploader/web/evesettings.js`
- Modify: `obs_youtube_uploader/web/index.html:18-22,334-340`
- Modify: `obs_youtube_uploader/web/app.js:91-94`
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes: every `eve_settings_*` bridge method from Task 7.
- Produces: the `evesettings` route.

There is no JavaScript test harness in this repo (`webview-replatform-design.md:545`), which is why every decision worth testing already lives in Python. This file captures events, sends them, and renders the answer.

- [ ] **Step 1: Add the nav button and the route container**

In `obs_youtube_uploader/web/index.html`, extend the nav at lines 18-22:

```html
      <button class="navbtn" id="nav-evesettings" data-route="evesettings">EVE Settings</button>
```

Add the route container after the `route-previews` div closes:

```html
  <div class="route" id="route-evesettings">
    <div class="settings">
      <section class="card">
        <h2>EVE Settings</h2>
        <div class="row">
          <span id="es-root">No folder selected</span>
          <button id="es-pick">Choose folder…</button>
          <span id="es-eve-state" class="pill">EVE closed</span>
        </div>
        <div class="row">
          <label for="es-server">Server</label>
          <select id="es-server"></select>
          <label for="es-profile">Settings set</label>
          <select id="es-profile"></select>
        </div>
        <p id="es-warning" class="warn" hidden></p>
      </section>

      <section class="card">
        <h2>Copy settings</h2>
        <div class="row">
          <label><input type="radio" name="es-kind" value="characters" checked> Characters</label>
          <label><input type="radio" name="es-kind" value="accounts"> Accounts</label>
        </div>
        <div class="row">
          <label for="es-source">Copy from</label>
          <select id="es-source"></select>
        </div>
        <div class="row">
          <input id="es-filter" type="search" placeholder="Filter…">
          <button id="es-all">Select all</button>
          <button id="es-none">Clear</button>
        </div>
        <div id="es-targets" class="list-scroll"></div>
        <div class="row">
          <button id="es-copy" class="primary">Copy to selected</button>
        </div>
      </section>

      <section class="card">
        <h2>Backups</h2>
        <div class="row">
          <button id="es-backup-profile">Back up this settings set</button>
        </div>
        <div id="es-backups" class="list-scroll"></div>
      </section>
    </div>
  </div>
```

Register the script beside the others at lines 334-340:

```html
  <script src="evesettings.js"></script>
```

- [ ] **Step 2: Register the route and the push handler**

In `obs_youtube_uploader/web/app.js`, extend the `routes` map at lines 91-94:

```javascript
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun',
                   bookmarks: 'route-bookmarks',
                   previews: 'route-previews',
                   evesettings: 'route-evesettings' };
```

Then add the new handler name to `WM.HANDLERS` at lines 49-52. `WM.handle`
throws for a name not in this list (`app.js:54-57`), so this edit is not
optional:

```javascript
  WM.HANDLERS = ['onRows', 'onDuration', 'onProgress', 'onStatus',
                 'onRetryAvailable', 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog', 'onFirstRun',
                 'onBookmarks', 'onEveStatus', 'onEveSettingsNames'];
```

- [ ] **Step 3: Write the route script**

Create `obs_youtube_uploader/web/evesettings.js`:

```javascript
/* FlyGD Wingman — the EVE Settings route.
 *
 * Deliberately dumb, for the same reason bookmarks.js is: this repo has no
 * way to test JavaScript (webview-replatform-design.md:545), so every
 * decision -- what is a valid target, what may be overwritten, what gets
 * backed up -- happens in Python. This file captures events, sends them,
 * and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var selected = {};

  function kind() {
    var checked = document.querySelector('input[name="es-kind"]:checked');
    return checked ? checked.value : 'characters';
  }

  function rows() {
    if (!state) return [];
    return kind() === 'accounts' ? state.accounts : state.characters;
  }

  function refresh() {
    WM.send('eve_settings_state').then(render);
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('es-root').textContent = payload.root || 'No folder selected';
    WM.el('es-eve-state').textContent =
      payload.eve_running ? 'EVE running' : 'EVE closed';

    var warning = WM.el('es-warning');
    // "Couldn't read" and "nothing there" are different answers, and only
    // one of them means the folder is wrong.
    warning.hidden = !payload.unreadable;
    warning.textContent = payload.unreadable
      ? "Couldn't read that folder. Check it still exists and is readable."
      : '';

    fill('es-server', payload.servers, payload.server);
    fill('es-profile', payload.profiles, payload.profile);
    renderSource();
    renderTargets();
    renderBackups();
  }

  function fill(id, items, current) {
    var el = WM.el(id);
    el.innerHTML = '';
    (items || []).forEach(function (item) {
      var option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.name;
      option.selected = item.path === current;
      el.appendChild(option);
    });
  }

  function renderSource() {
    var el = WM.el('es-source');
    var previous = el.value;
    el.innerHTML = '';
    rows().forEach(function (row) {
      var option = document.createElement('option');
      option.value = row.path;
      option.textContent = row.name;
      option.selected = row.path === previous;
      el.appendChild(option);
    });
  }

  function renderTargets() {
    var host = WM.el('es-targets');
    var needle = (WM.el('es-filter').value || '').toLowerCase();
    var source = WM.el('es-source').value;
    host.innerHTML = '';
    rows().forEach(function (row) {
      if (row.path === source) return;
      if (needle && row.name.toLowerCase().indexOf(needle) === -1) return;
      var label = document.createElement('label');
      label.className = 'row';
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = row.path;
      box.checked = !!selected[row.path];
      box.addEventListener('change', function () {
        selected[row.path] = box.checked;
      });
      label.appendChild(box);
      label.appendChild(document.createTextNode(' ' + row.name));
      host.appendChild(label);
    });
  }

  function renderBackups() {
    var host = WM.el('es-backups');
    host.innerHTML = '';
    (state.backups || []).forEach(function (item) {
      var line = document.createElement('div');
      line.className = 'row';
      line.appendChild(document.createTextNode(
        item.created + ' · ' + item.kind + ' · ' + item.stem
        + (item.origin === 'auto' ? ' (auto)' : '')));
      line.appendChild(button('Restore', function () {
        WM.send('eve_settings_restore', item.path).then(refresh);
      }));
      line.appendChild(button('Delete', function () {
        WM.send('eve_settings_delete_backup', item.path).then(refresh);
      }));
      host.appendChild(line);
    });
  }

  function button(text, handler) {
    var el = document.createElement('button');
    el.textContent = text;
    el.addEventListener('click', handler);
    return el;
  }

  function chosenTargets() {
    return Object.keys(selected).filter(function (path) {
      return selected[path];
    });
  }

  function wire() {
    WM.el('es-pick').addEventListener('click', function () {
      WM.send('eve_settings_pick_root').then(function () {
        selected = {};
        refresh();
        WM.send('eve_settings_resolve_names');
      });
    });

    ['es-server', 'es-profile'].forEach(function (id) {
      WM.el(id).addEventListener('change', function () {
        // A source picked in the old settings set does not exist in the new
        // one, so the selection is dropped rather than carried.
        selected = {};
        WM.send('eve_settings_select', WM.el('es-server').value,
                WM.el('es-profile').value).then(function () {
          refresh();
          WM.send('eve_settings_resolve_names');
        });
      });
    });

    Array.prototype.forEach.call(
      document.querySelectorAll('input[name="es-kind"]'), function (radio) {
        radio.addEventListener('change', function () {
          selected = {};
          renderSource();
          renderTargets();
        });
      });

    WM.el('es-filter').addEventListener('input', renderTargets);
    WM.el('es-source').addEventListener('change', renderTargets);

    WM.el('es-all').addEventListener('click', function () {
      rows().forEach(function (row) { selected[row.path] = true; });
      renderTargets();
    });

    WM.el('es-none').addEventListener('click', function () {
      selected = {};
      renderTargets();
    });

    WM.el('es-copy').addEventListener('click', function () {
      var targets = chosenTargets();
      if (!targets.length) return;
      WM.send('eve_settings_copy', WM.el('es-source').value, targets)
        .then(function () { window.setTimeout(refresh, 250); });
    });

    WM.el('es-backup-profile').addEventListener('click', function () {
      WM.send('eve_settings_backup', state.profile, 'profile')
        .then(function () { window.setTimeout(refresh, 250); });
    });

    document.addEventListener('wm:route', function (event) {
      if (event.detail !== 'evesettings') return;
      refresh();
      // Names are resolved on first open, never at launch: the tray app
      // starts hidden and must not make a network call nobody asked for.
      WM.send('eve_settings_resolve_names');
    });
  }

  WM.handle('onEveSettingsNames', function () { refresh(); });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
```

- [ ] **Step 4: Add the manual checks**

Append to `docs/smoke-checklist.md`:

```markdown
## EVE Settings

The suite cannot exercise Windows file locking or a real `os.replace` retry,
so these are the checks that matter and only a Windows machine can run them.

- [ ] Choose the EVE folder. Servers and settings sets populate; characters
      show names within a second or two of the route opening.
- [ ] Pull the network cable and reopen the route — characters render as
      `Character <id>`, nothing errors.
- [ ] Point the folder picker at a `settings_*` directory. The root heals
      upward and the tree still populates.
- [ ] Copy one character onto three others with EVE closed. All three
      update; three auto-backups appear.
- [ ] Copy with EVE running. It fails with "The file is in use. Close EVE
      and retry", and every target is left intact.
- [ ] Restore the pre-copy backup for one character. The original settings
      come back.
- [ ] Back up a settings set, delete a `.dat` from it, restore. The deleted
      file returns.
- [ ] Add a file to a settings set that was not in its backup, then restore.
      It is removed, and the pre-restore auto-backup contains it.
- [ ] Start a copy and immediately try a second one. The second is refused
      with "EVE Settings busy" rather than interleaving.
- [ ] With `auto_keep` at its default, copy the same character eleven times.
      Ten auto-backups remain; the manual ones are untouched.
- [ ] Check the packaged build: the EVE Settings route appears and the
      folder picker opens.
```

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest`
Expected: PASS. `tests/test_packaging_completeness.py` and `tests/test_no_tk.py` both run here and both can fail on a new module.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/web/ docs/smoke-checklist.md
git commit -m "feat(ui): add the EVE Settings route"
```

---

## Self-review

**Spec coverage.** Every section of `eve-settings-design.md` maps to a task: architecture and the package split (2-5), the threading contract and mutation lock (7), the bridge shape and the names push (7), `tree.py` (2), `names.py` (3), `backup.py` (4), `ops.py` (5), persisted state and the merging writer (6), the user interface (8), error handling (7-8), testing (every task), and the smoke checks the suite cannot cover (8).

Two things in the spec are deliberately **not** in any task, both listed there as deferred: notes, and settings-set create/duplicate/rename/delete. Profile *backup and restore* are in scope and land in Tasks 4 and 7.

One decision is recorded in Task 3 that the spec left open: the name cache is in-memory for the process lifetime rather than on disk.

**Placeholder scan.** No `TBD`, no "add error handling", no "similar to Task N". Every code step carries the code, including the exact `WM.HANDLERS` edit that `WM.handle` requires — an earlier draft left that for the implementer to look up, which is precisely the kind of gap that turns into a runtime throw in a console nobody is watching.

**Type consistency.** `tree.file_kind` returns `"character"` / `"account"` / `None` and is used with those exact values in `backup.py`, `ops.py`, and `api.py`. `BackupInfo.origin` is `"auto"` / `"manual"` throughout. `CopyReport.succeeded` / `.failed` are used as written in Task 7. `settings.update_section(name, values, path=None)` is called with that signature in three places in Task 7. `paths.eve_settings_backup_dir()` is defined in Task 6 and used in Task 7.
