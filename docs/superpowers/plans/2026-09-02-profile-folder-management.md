# Profile Folder Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make profile switching the primary Profiles context and safely create or replace profiles within the selected EVE server.

**Architecture:** A new `evesettings.profilecopy` module owns profile-name validation, hierarchy authority, staging, publication, cleanup, and caught-failure rollback. `ui.api.Api` continues to own canonical persisted selection, mutation locking, EVE-closed checks, confirmation, backups, retention, status, and bridge completion; the existing Profiles module renders one inline New/Replace disclosure.

**Tech Stack:** Python 3.11, pathlib/os/shutil, pytest, plain HTML/CSS, ES5 JavaScript, pywebview 6.2.1, Windows WebView2.

**Spec:** `docs/superpowers/specs/2026-09-02-profile-folder-management-design.md`

## Global Constraints

- Copy only numeric `core_char_<id>.dat` and `core_user_<id>.dat` files; preserve unrelated destination entries.
- Limit creation and replacement to the freshly discovered selected server; never trust page paths as filesystem authority.
- Validate the complete resolved hierarchy: canonical root → server → profile → recognized file. The root itself may be the server only when discovery confirms profiles directly beneath it.
- Persist `root`, `server`, and `profile` together after explicit selection; opening Profiles must not write settings.
- Require the new tri-state EVE probe to report `closed`; `running` and `unknown` both refuse whole-profile writes.
- Back up an existing destination before mutation and automatically roll back caught publication failures. Hard kills and power loss rely on the durable backup.
- New profile names are trimmed, 1–80 characters, omit `settings_`, satisfy Windows component rules, and do not collide case-insensitively.
- Creating selects the destination; replacing retains the source. A created profile survives a failed selection save and is reported as successful with a warning.
- Keep `onEveSettingsDone` as the sole Profiles mutation completion handler.
- Keep **Copy to selected** as the screen's only `.btn.acc` control.
- Add no dependency, package, route, or title-bar destination.
- Web tests are lexical only; complete the Windows smoke checklist before release.

---

## File Map

**Create**

- `wingman/evesettings/profilecopy.py`: whole-profile validation, request resolution, staging, publication, cleanup, and rollback result types.
- `tests/test_evesettings_profilecopy.py`: pure filesystem contract for the new module.

**Modify**

- `wingman/evesettings/tree.py`: stable profile ordering and hierarchy helpers used by profile copy.
- `wingman/preview/discovery.py`: separate tri-state whole-profile EVE probe; leave `list_clients()` behavior unchanged.
- `wingman/evesettings/backup.py`: restore an already-created durable backup without backing up a partial publication.
- `wingman/ui/api.py`: canonical selection, effective-root restore, profile-copy endpoint/worker, backup/pruning/status/completion orchestration.
- `wingman/web/index.html`: profile-first context and inline New/Replace disclosure.
- `wingman/web/evesettings.js`: disclosure state, rendering, bridge call, busy state, and extended completion handling.
- `wingman/web/style.css`: profile-first and disclosure geometry plus `[hidden]` rules.
- `wingman/web/dev.js`: profile-copy endpoint double and scenarios.
- `docs/smoke-checklist.md`: profile-first and whole-profile Windows checks.
- `tests/test_evesettings_tree.py`, `tests/test_preview_discovery.py`, `tests/test_evesettings_backup.py`, `tests/test_api_evesettings.py`, `tests/test_profiles_page.py`, `tests/test_bridge_contract.py`, `tests/test_dev_harness.py`, `tests/test_packaging_completeness.py`: focused regression coverage.

**Deliberately unchanged**

- `wingman/settings.py`: the existing `root`/`server`/`profile` schema is sufficient.
- `wingman/web/app.js`: no new Python-to-page handler is introduced.
- `pyproject.toml`: `wingman.evesettings` is already an explicit package; a new module needs no package-list entry.

---

### Task 1: Canonical Profile Selection

**Files:**
- Modify: `wingman/evesettings/tree.py:286-384`
- Modify: `wingman/ui/api.py:4715-5057,5671-5707`
- Test: `tests/test_evesettings_tree.py`
- Test: `tests/test_api_evesettings.py`

**Interfaces:**
- Consumes: existing `evesettings_tree.discover(root, server, profile) -> Tree` and `settings_mod.update_section(...)`.
- Produces: `Api._eve_persist_selection(found: Tree) -> None`, which persists that Tree's complete root/server/profile triple and takes no per-leg override; canonical picker/select behavior; restore validated against `_eve_discover().root`.

- [ ] **Step 1: Add failing normalization and stable-order tests**

Add tests that pin profile-root, server-root, and ordinary-root normalization without persistence, plus deterministic ordering for historical case-distinct names:

```python
def test_profile_root_normalizes_to_canonical_triple(tmp_path):
    profile = tmp_path / "EVE" / "server_tranquility" / "settings_Default"
    profile.mkdir(parents=True)
    found = tree.discover(profile)
    assert (found.root, found.server, found.profile) == (
        profile.parent.parent,
        profile.parent,
        profile,
    )


def test_profiles_have_a_stable_path_tiebreaker(tmp_path):
    server = tmp_path / "server_tranquility"
    (server / "settings_alt").mkdir(parents=True)
    (server / "settings_Alt").mkdir()
    found = tree.discover(tmp_path, server)
    assert [p.path.name for p in found.profiles] == ["settings_Alt", "settings_alt"]
```

Sort profiles by `(name.lower() != "default", name.casefold(), os.path.normcase(str(path)), str(path))`. The raw `str(path)` after `normcase` is the tie-breaker that actually settles it: `normcase` lowercases on Windows, so two names differing only by case — the very pair this rule exists for — tie under it and fall back to `os.scandir`'s filesystem-dependent order.

- [ ] **Step 2: Run the tree tests and verify the ordering test fails**

Run:

```bash
uv run --no-sync python -m pytest tests/test_evesettings_tree.py -k "normalizes_to_canonical_triple or stable_path_tiebreaker" -v
```

Expected: normalization passes against current discovery; stable tie-breaking fails or depends on directory enumeration order.

- [ ] **Step 3: Add failing API tests for canonical persistence**

Cover all explicit inputs and the no-write-on-read contract:

```python
@pytest.mark.parametrize("picked_level", ["root", "server", "profile"])
def test_pick_root_persists_the_canonical_selection(tmp_path, monkeypatch, picked_level):
    profile = eve_tree(tmp_path)
    root, server = profile.parent.parent, profile.parent
    api = build(tmp_path, monkeypatch)
    picked = {"root": root, "server": server, "profile": profile}[picked_level]
    api._window.create_file_dialog = lambda *a, **k: (str(picked),)
    assert api.eve_settings_pick_root() == str(root)
    assert api._eve_section()["root"] == str(root)
    assert api._eve_section()["server"] == str(server)
    assert api._eve_section()["profile"] == str(profile)


def test_state_normalizes_a_legacy_profile_root_without_saving(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._eve_section().update({"root": str(profile), "server": None, "profile": None})
    monkeypatch.setattr(api_mod.settings_mod, "update_section", lambda *a, **k: pytest.fail("state must not save"))
    state = api.eve_settings_state()
    assert state["root"] == str(profile.parent.parent)
    assert state["profile"] == str(profile)
```

Also test that `eve_settings_select()` rejects a fabricated server/profile, canonicalizes a legacy deep root, and chooses the requested server's first profile when `profile == ""`.

- [ ] **Step 4: Run the API tests and verify they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py -k "canonical or legacy_profile_root or fabricated_selection or first_profile" -v
```

Expected: picker stores the raw path and clears selection; `eve_settings_select()` writes only server/profile and accepts fabricated values.

- [ ] **Step 5: Implement one canonical persistence boundary**

Add to `Api` near `_eve_discover()`:

```python
def _eve_persist_selection(self, found) -> None:
    settings_mod.update_section(
        self._state.settings,
        "eve_settings",
        {
            "root": str(found.root) if found.root else None,
            "server": str(found.server) if found.server else None,
            "profile": str(found.profile) if found.profile else None,
        },
    )
```

There is no per-leg override argument. The whole point of the boundary is
that one discovered Tree is persisted whole, so the stored root can never
drift out of step with the server and profile saved beside it; pasting a
caller's preferred profile over a Tree that disagrees with it would put the
three legs back out of step. A caller that wants a particular profile
remembered rediscovers first and persists THAT Tree — the contract
`_eve_select_created_profile` follows for a freshly created profile:
`discover(plan.root, plan.server, created)`, confirm the result really is
`created`, then `_eve_persist_selection(found)`.

For picker and Detect, call `discover(picked)` or `discover(default_root())`, persist its complete triple, and return the canonical root. For selection, discover from the effective current root with the requested tokens, verify the requested server/profile actually matched an offered item, then persist the complete result. Preserve `_eve_hold()` and identification clearing.

- [ ] **Step 6: Validate restore against the effective root**

Change `_eve_restore_worker()` from the raw section root to:

```python
found = self._eve_discover()
if found.root is None:
    raise ValueError("Choose the EVE settings folder first.")
written = evesettings_backup.restore(store, archive, found.root)
```

Add a test that restores a sibling-profile backup when the stored legacy `root` points to the original profile.

- [ ] **Step 7: Run focused selection and restore tests**

Run:

```bash
uv run --no-sync python -m pytest tests/test_evesettings_tree.py tests/test_api_evesettings.py -k "root or select or restore" -v
```

Expected: PASS.

- [ ] **Step 8: Commit canonical selection**

```bash
git add wingman/evesettings/tree.py wingman/ui/api.py tests/test_evesettings_tree.py tests/test_api_evesettings.py
git commit -m "feat: canonicalize EVE profile selections"
```

---

### Task 2: Fail-Closed EVE Probe

**Files:**
- Modify: `wingman/preview/discovery.py:40-141`
- Test: `tests/test_preview_discovery.py`

**Interfaces:**
- Consumes: injected window enumerator, PID resolver, and image-name resolver used by `list_clients()`.
- Produces: `EveClientState`, `EveClientProbe`, and `probe_eve_client_state(...) -> EveClientProbe`; no change to `list_clients()`.

- [ ] **Step 1: Write failing tri-state tests**

Add exact probe cases:

```python
@pytest.mark.parametrize(
    ("windows", "pid", "image", "expected"),
    [
        ([], 7, "exefile.exe", discovery.EveClientState.CLOSED),
        ([(1, "Browser")], 7, None, discovery.EveClientState.CLOSED),
        ([(1, "EVE - Alice")], 7, "exefile.exe", discovery.EveClientState.RUNNING),
        ([(1, "EVE - Alice")], 7, "chrome.exe", discovery.EveClientState.CLOSED),
        ([(1, "EVE - Alice")], 0, "exefile.exe", discovery.EveClientState.UNKNOWN),
        ([(1, "EVE - Alice")], 7, None, discovery.EveClientState.UNKNOWN),
    ],
)
def test_profile_probe_states(windows, pid, image, expected):
    result = discovery.probe_eve_client_state(
        enumerator=lambda: windows,
        pids=lambda _hwnd: pid,
        image_name=lambda _pid: image,
    )
    assert result.state is expected
```

Add separate exception cases for enumeration, PID lookup, and image lookup. Add a mixed known-running plus unresolved candidate and assert `UNKNOWN` dominates. Retain an existing `list_clients(strict=True)` compatibility assertion.

- [ ] **Step 2: Run the tests and verify the missing interface failure**

```bash
uv run --no-sync python -m pytest tests/test_preview_discovery.py -k "profile_probe" -v
```

Expected: FAIL because `EveClientState` and `probe_eve_client_state` do not exist.

- [ ] **Step 3: Implement the separate probe**

Add:

```python
class EveClientState(enum.Enum):
    CLOSED = "closed"
    RUNNING = "running"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EveClientProbe:
    state: EveClientState
    errors: tuple[BaseException, ...] = ()
```

Implement `probe_eve_client_state()` by examining only titles beginning with `EVE`, collecting an `OSError` for zero PIDs or `None` images and caught exceptions for callback failures. Examine every candidate; return `UNKNOWN` when errors exist, otherwise `RUNNING` when any image is `CLIENT_IMAGE`, otherwise `CLOSED`. Do not route `list_clients()` through this function.

- [ ] **Step 4: Run discovery tests**

```bash
uv run --no-sync python -m pytest tests/test_preview_discovery.py -v
```

Expected: PASS, including unchanged preview discovery behavior.

- [ ] **Step 5: Commit the probe**

```bash
git add wingman/preview/discovery.py tests/test_preview_discovery.py
git commit -m "feat: add fail-closed EVE client probe"
```

---

### Task 3: Profile Request Authority and Creation

**Files:**
- Create: `wingman/evesettings/profilecopy.py`
- Create: `tests/test_evesettings_profilecopy.py`
- Modify: `wingman/evesettings/tree.py`

**Interfaces:**
- Consumes: `tree.Tree`, `tree.Profile`, `tree.file_kind()`, `tree.require_under()`, and `atomicio.copy_atomic()`.
- Produces: `ProfileCopyPlan`, `StagedProfileCopy`, `validate_friendly_name()`, `prepare_copy()`, `stage_copy()`, and `publish_new()`.

- [ ] **Step 1: Define failing name-validation tests**

Create `tests/test_evesettings_profilecopy.py` with a real discovered tree fixture:

```python
@pytest.fixture
def discovered_tree(tmp_path):
    server = tmp_path / "EVE" / "server_tranquility"
    profile = server / "settings_Default"
    profile.mkdir(parents=True)
    return tree.discover(tmp_path / "EVE", server, profile)


@pytest.mark.parametrize("value", ["", "settings_Fleet", ".", "..", "CON", "con.txt", "bad/name", "bad\\name", "bad:name", "bad.", "x" * 81, "bad\x00name"])
def test_new_profile_name_is_rejected(value, discovered_tree):
    with pytest.raises(ValueError):
        profilecopy.validate_friendly_name(value, discovered_tree.profiles)


def test_new_profile_name_is_trimmed(discovered_tree):
    assert profilecopy.validate_friendly_name("  Fleet UI  ", discovered_tree.profiles) == "Fleet UI"


def test_new_profile_name_rejects_a_case_insensitive_collision(discovered_tree):
    with pytest.raises(ValueError, match="already exists"):
        profilecopy.validate_friendly_name("default", discovered_tree.profiles)
```

Include Windows reserved basenames `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, and `LPT1`–`LPT9`, with or without extensions.

- [ ] **Step 2: Define failing request-authority tests**

Build a root with `server_tranquility/settings_Default` and `server_singularity/settings_Other`, then assert:

```python
def test_prepare_copy_rejects_a_stale_source(discovered_tree):
    with pytest.raises(ValueError, match="selected profile changed"):
        profilecopy.prepare_copy(discovered_tree, "settings_Old", "new", "Fleet")


def test_prepare_copy_rejects_cross_server_destination(tmp_path):
    root = tmp_path / "EVE"
    source = root / "server_tranquility" / "settings_Default"
    other = root / "server_singularity" / "settings_Other"
    source.mkdir(parents=True)
    other.mkdir(parents=True)
    found = tree.discover(root, source.parent, source)
    with pytest.raises(ValueError, match="selected server"):
        profilecopy.prepare_copy(found, str(source), "replace", str(other))
```

Also pin source-equals-destination, unknown mode, fabricated destination, server junction outside root, profile junction outside server, and recognized-file link outside profile. Permit `found.server == found.root` only when the root directly contains discovered profiles.

- [ ] **Step 3: Run the new tests and verify import failure**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_profilecopy.py -v
```

Expected: FAIL because `wingman.evesettings.profilecopy` does not exist.

- [ ] **Step 4: Implement result types and validation**

Create:

```python
ProfileCopyMode = Literal["new", "replace"]
STAGE_PREFIX = ".wingman-profile-copy-"
STAGE_SUFFIX = ".stage"

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
```

`validate_friendly_name()` trims first, applies the approved grammar, and compares `existing.name.casefold()` against `("settings_" + cleaned).casefold()`. The creation policy is case-insensitive on every test platform, independent of the host filesystem.

`prepare_copy()` matches the expected source and replacement destination against the fresh `Tree.profiles` list, derives new destinations from the validated friendly name, and validates each hierarchy edge. Add a private direct-child check that combines lexical parent equality with `tree.require_under(parent, child)`.

- [ ] **Step 5: Add failing staging and creation tests**

Cover byte identity, recognized-only membership, deterministic filename ordering, cleanup, and races:

```python
def test_stage_contains_only_byte_identical_recognized_files(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        assert staged.members == ("core_char_1.dat", "core_user_2.dat")
        assert (staged.path / "core_char_1.dat").read_bytes() == b"character"
        assert not (staged.path / "notes.txt").exists()


def test_publish_new_refuses_a_destination_race(staged_copy):
    staged_copy.plan.destination.mkdir()
    with pytest.raises(FileExistsError):
        profilecopy.publish_new(staged_copy)
    assert list(staged_copy.plan.destination.iterdir()) == []
```

Add cleanup tests proving `.wingman-profile-copy-*.stage` is never discovered, an ordinary abandoned directory is removed, and a stage-shaped symlink/junction refuses cleanup rather than being followed.

- [ ] **Step 6: Implement staging and new publication**

Use a context manager:

```python
@contextlib.contextmanager
def stage_copy(plan, *, token_factory=lambda: uuid.uuid4().hex):
    cleanup_abandoned_stages(plan.server)
    stage = plan.server / f"{STAGE_PREFIX}{token_factory()}{STAGE_SUFFIX}"
    stage.mkdir()
    staged = None
    try:
        members = _recognized_members(plan.source)
        for source in members:
            target = stage / source.name
            atomicio.copy_atomic(source, target)
            if _sha256(source) != _sha256(target):
                raise OSError(f"Staged copy did not match {source.name}.")
        staged = StagedProfileCopy(plan, stage, tuple(p.name for p in members))
        yield staged
    finally:
        if stage.exists():
            try:
                shutil.rmtree(stage)
            except OSError:
                if staged is None or not staged.published:
                    raise
                logger.exception(
                    "Could not remove the staging directory %s after "
                    "publishing %s; leaving it for the next run",
                    stage,
                    plan.destination,
                )
```

Removing the stage can itself fail (a scanner holding a handle open, a
permission change), and what that failure means depends entirely on whether
the copy landed. BEFORE publication it is the operation's own failure and
propagates: nothing succeeded, and a stage left behind unreported is a
silent one. AFTER publication — the caller marked the staged copy published
— the destination is settled, so the failure is logged and the stage is
left in its reserved, never-discoverable namespace for the next run's
`cleanup_abandoned_stages` to remove; the successful outcome is not
changed. Raising there would turn a replacement that DID happen into "Copy
failed" and invite a retry of work already done.

`cleanup_abandoned_stages()` accepts only direct, non-reparse directories matching the exact prefix/suffix grammar and propagates cleanup failures. Detect reparse points with `Path.is_symlink()` and, on Windows, `os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`. `publish_new()` rechecks nonexistence and calls `stage.path.rename(plan.destination)`; the context manager sees the old stage path no longer exists.

- [ ] **Step 7: Run profile-copy and tree tests**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_profilecopy.py tests/test_evesettings_tree.py -v
```

Expected: PASS on portable cases; Windows-only junction tests skip on Linux.

- [ ] **Step 8: Commit creation support**

```bash
git add wingman/evesettings/profilecopy.py wingman/evesettings/tree.py tests/test_evesettings_profilecopy.py
git commit -m "feat: stage and create EVE profiles safely"
```

---

### Task 4: Exact Replacement and Rollback

**Files:**
- Modify: `wingman/evesettings/profilecopy.py`
- Modify: `wingman/evesettings/backup.py:338-410`
- Modify: `tests/test_evesettings_profilecopy.py`
- Modify: `tests/test_evesettings_backup.py`

**Interfaces:**
- Consumes: `StagedProfileCopy` from Task 3 and existing profile backup archives.
- Produces: `ReplacementFailed`; `publish_replacement(staged, *, rollback) -> Path`; `backup.restore(..., backup_current: bool = True) -> Path`.

- [ ] **Step 1: Add failing backup-seam tests**

Pin existing and rollback behavior separately:

```python
def test_restore_backs_up_current_profile_by_default(store, archive, monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "create_profile_backup", lambda *a, **k: calls.append((a, k)))
    backup.restore(store, archive, root=archive_root)
    assert len(calls) == 1


def test_rollback_restore_does_not_back_up_partial_profile(store, archive, monkeypatch):
    monkeypatch.setattr(backup, "create_profile_backup", lambda *a, **k: pytest.fail("must reuse durable backup"))
    backup.restore(store, archive, root=archive_root, backup_current=False)
```

- [ ] **Step 2: Run the backup tests and verify the keyword failure**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_backup.py -k "backup_current or rollback_restore" -v
```

Expected: FAIL because `backup.restore()` does not accept `backup_current`.

- [ ] **Step 3: Add the rollback seam without changing default restore**

Change the signature to:

```python
def restore(backup_dir, archive_path, root, *, now=None, backup_current=True) -> Path:
```

Guard only the pre-restore backup block with `if backup_current:`. Keep archive validation, staging, recognized-file deletion, and atomic replacement unchanged.

- [ ] **Step 4: Add failing exact-replacement tests**

Test this concrete destination transition:

```text
source:      core_char_1.dat=A, core_user_2.dat=B
before:      core_char_1.dat=old, core_char_9.dat=remove, notes.txt=keep, extras/=keep
after:       core_char_1.dat=A, core_user_2.dat=B, notes.txt=keep, extras/=keep
```

Inject publication failure after one replacement and assert rollback restores the entire recognized before-set. Inject rollback failure and assert `ReplacementFailed.rollback_error` is populated. Raise `SystemExit` during publication and assert the rollback callback was not invoked.

- [ ] **Step 5: Implement replacement result and publication**

Add:

```python
class ReplacementFailed(Exception):
    def __init__(self, publication_error, rollback_error=None):
        super().__init__(str(publication_error))
        self.publication_error = publication_error
        self.rollback_error = rollback_error

    @property
    def destination_restored(self):
        return self.rollback_error is None
```

`publish_replacement()` computes and validates destination recognized members before mutation. It atomically replaces/adds every staged member, removes destination-only recognized files, and catches `Exception`. On caught failure it calls `rollback()` once, captures a rollback exception, and raises `ReplacementFailed` from the publication exception. Do not catch `BaseException`.

- [ ] **Step 6: Run replacement and backup tests**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_profilecopy.py tests/test_evesettings_backup.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit replacement support**

```bash
git add wingman/evesettings/profilecopy.py wingman/evesettings/backup.py tests/test_evesettings_profilecopy.py tests/test_evesettings_backup.py
git commit -m "feat: replace EVE profiles with rollback"
```

---

### Task 5: API Orchestration and Completion

**Files:**
- Modify: `wingman/ui/api.py:58-65,5386-5707`
- Modify: `tests/test_api_evesettings.py`
- Modify: `tests/test_bridge_contract.py`

**Interfaces:**
- Consumes: Tasks 1–4 interfaces.
- Produces: `Api.eve_settings_copy_profile(expected_source: str, mode: str, destination: str) -> dict`; `_eve_copy_profile_worker(plan) -> None`; extended `_eve_done(ok: bool, **details) -> None`.

- [ ] **Step 1: Add failing bridge and immediate-result tests**

Add:

```python
def test_profile_copy_bridge_shape():
    params = inspect.signature(Api.eve_settings_copy_profile).parameters
    assert list(params) == ["self", "expected_source", "mode", "destination"]


def test_profile_copy_returns_inline_refusal_when_busy(api):
    assert api._eve_mutation.acquire(blocking=False)
    try:
        assert api.eve_settings_copy_profile("source", "new", "Fleet") == {
            "accepted": False,
            "error": "Another Profiles operation is running.",
        }
    finally:
        api._eve_mutation.release()
```

Also test account-identification refusal and invalid/stale request errors.

- [ ] **Step 2: Add failing orchestration tests**

Use injected spies to pin this order:

```text
fresh discovery → expected-source validation → canonical settings save → first EVE probe → stage
→ replacement confirmation → second EVE probe → destination backup → publication
→ prune → completion
```

Separate tests must assert:

- canonical save failure starts no worker and touches no profile files;
- new mode never confirms or backs up;
- replacement cancellation creates no backup;
- running/unknown probe refuses before publication;
- backup failure leaves destination unchanged;
- caught publication failure rolls back from the named backup with `backup_current=False`;
- pruning happens only after success or settled rollback;
- every path releases `_eve_mutation` and pushes one completion.

- [ ] **Step 3: Run focused API tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_bridge_contract.py -k "copy_profile or profile_copy" -v
```

Expected: FAIL because the endpoint and extended completion do not exist.

- [ ] **Step 4: Implement lock-safe synchronous acceptance**

The endpoint must acquire the existing lock itself because validation and canonical persistence must happen before thread start:

```python
def eve_settings_copy_profile(self, expected_source, mode, destination):
    if self._eve_identification is not None:
        return {"accepted": False, "error": "Finish or cancel account identification first."}
    if not self._eve_mutation.acquire(blocking=False):
        return {"accepted": False, "error": "Another Profiles operation is running."}
    try:
        found = self._eve_discover()
        plan = evesettings_profilecopy.prepare_copy(found, expected_source, mode, destination)
        self._eve_persist_selection(found)
        self._spawn(target=self._eve_copy_profile_worker, args=(plan,), daemon=True).start()
    except (OSError, ValueError) as error:
        self._eve_mutation.release()
        return {"accepted": False, "error": str(error)}
    except Exception:
        self._eve_mutation.release()
        logger.exception("Could not start EVE profile copy")
        return {"accepted": False, "error": "Profile copy could not be started."}
    except BaseException:
        self._eve_mutation.release()
        raise
    return {"accepted": True, "error": None}
```

This handles thread-start failures like `_eve_begin()`: log them, release the lock, and return an actionable inline error. Do not expose a public non-method `Api` attribute.

- [ ] **Step 5: Extend completion without adding a handler**

Change:

```python
def _eve_done(self, ok: bool, **details) -> None:
    self._push("onEveSettingsDone", {"ok": bool(ok), **details})
```

Existing callers continue passing only `ok`. Profile-copy completions add:

```python
{
    "operation": "profile_copy",
    "mode": plan.mode,
    "published": published,
    "selection_persisted": selection_persisted,
    "error": error_message,
}
```

Do not add an allowlist entry or second JS handler.

- [ ] **Step 6: Implement the worker with explicit partial success**

Use `discovery.probe_eve_client_state()` and require `CLOSED`. In replacement mode, stage before `_eve_confirm(..., destructive=True)`, probe again after confirmation, create the automatic profile backup, and pass this rollback callback:

```python
def rollback():
    evesettings_backup.restore(
        paths.eve_settings_backup_dir(),
        archive,
        plan.root,
        backup_current=False,
    )
```

For new mode, call `publish_new()`, rediscover with `evesettings_tree.discover(plan.root, plan.server, published_path)`, then pass that result to `_eve_persist_selection()`. If that save fails, keep `ok=True`, set `published=True`, set `selection_persisted=False`, and raise a warning alert with the approved “Select it from Profile” instruction. For replacement, retain source selection.

Catch `ReplacementFailed` separately to distinguish restored versus failed rollback and include the durable archive name in failed-rollback recovery text. In `finally`, release `_eve_mutation` exactly once and call `_eve_done()` exactly once.

- [ ] **Step 7: Run API and subsystem tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_api_evesettings.py \
  tests/test_bridge_contract.py \
  tests/test_evesettings_profilecopy.py \
  tests/test_evesettings_backup.py \
  tests/test_preview_discovery.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit API support**

```bash
git add wingman/ui/api.py tests/test_api_evesettings.py tests/test_bridge_contract.py
git commit -m "feat: expose whole-profile copy through Profiles API"
```

---

### Task 6: Profile-First Web Interface

**Files:**
- Modify: `wingman/web/index.html:1410-1507`
- Modify: `wingman/web/evesettings.js:12-195,740-930,1230-1266`
- Modify: `wingman/web/style.css:2646-2706,3070-3210,3281-3283`
- Modify: `tests/test_profiles_page.py`
- Modify: `tests/test_page_conventions.py`

**Interfaces:**
- Consumes: `eve_settings_state.profile`, `.profiles`, `.server`, `.servers`, `.root`; Task 5 endpoint and completion payload.
- Produces: profile-first context and `profileCopy = {open, source, mode, name, destination, error, destinationInvalid}` page state.

- [ ] **Step 1: Write failing DOM convention tests**

Assert the context order and treatments:

```python
def test_profile_is_the_primary_context_control():
    context = profiles_context_body()
    assert context.index('id="es-profile"') < context.index('id="es-folder-summary"')
    assert 'id="es-profile-copy-open" class="btn"' in context
    assert 'id="es-profile-copy-open" class="btn acc"' not in context


def test_profile_copy_modes_use_shared_radio_markup():
    assert re.search(r'name="es-profile-copy-mode" value="new" checked><span class="ring"></span>', BODY)
    assert re.search(r'name="es-profile-copy-mode" value="replace"><span class="ring"></span>', BODY)
```

Also assert associated labels for the name and destination, **Change folder or server…**, no Profile select inside the secondary detail, one `.btn.acc` on the route, and `[hidden]` overrides for each new display-setting selector.

- [ ] **Step 2: Write failing JS lifecycle tests**

Lexically pin:

- one `profileCopy` object with all seven fields;
- `destinationInvalid` set by the render that first notices the chosen
  Replace destination has vanished, read back on every later render rather
  than re-derived from the select's own value (that render is what just
  overwrote it with the placeholder), and cleared only by the destination
  select's own `change` handler, which repaints;
- source frozen from `state.profile` on open;
- replace options exclude source;
- root/server/profile accepted changes reset the disclosure and character/account selection;
- `sendProfileCopy()` examines `result.accepted`, not object truthiness;
- immediate refusal writes `profileCopy.error` and clears busy;
- completion closes on `payload.published`, including `selection_persisted === false`;
- failed publication retains disclosure state;
- profile-copy controls join shared busy state while navigation remains enabled.

- [ ] **Step 3: Run page tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_profiles_page.py tests/test_page_conventions.py -k "profile or folder" -v
```

Expected: FAIL against the current folder-first markup and absent disclosure.

- [ ] **Step 4: Reshape the context markup**

Keep the EVE pill in the heading. Move `#es-profile` into an always-visible primary row beside `#es-profile-copy-open`. Keep folder path and `<name> server` in `#es-folder-summary`; rename the action **Change folder or server…**. Keep chooser, Detect, and `#es-server` in the collapsible detail.

Add an initially hidden inline disclosure with these IDs:

```text
es-profile-copy-panel
es-profile-copy-source
es-profile-copy-new
es-profile-copy-replace
es-profile-copy-new-fields
es-profile-copy-replace-fields
es-profile-copy-name
es-profile-copy-destination
es-profile-copy-submit
es-profile-copy-cancel
es-profile-copy-status
```

Use `.radio > input + .ring`, `.lab`, `.field`, and ordinary `.btn` controls.

- [ ] **Step 5: Implement explicit disclosure state and rendering**

Add near module state:

```javascript
var profileCopy = {
  open: false,
  source: '',
  mode: 'new',
  name: '',
  destination: '',
  error: '',
  destinationInvalid: false
};
```

Add `resetProfileCopy()`, `openProfileCopy()`, and `renderProfileCopy()`. `renderProfileCopy()` must derive replace options from `state.profiles`, exclude `profileCopy.source`, render `No other profiles` as a disabled empty option, switch fields by mode, and preserve entered values across ordinary `refresh()` calls.

- [ ] **Step 6: Add a result-aware sender**

Do not reuse `mutate()`, which treats any returned object as truthy. Implement:

```javascript
function sendProfileCopy() {
  if (busy || !profileCopy.source) return;
  profileCopy.name = WM.el('es-profile-copy-name').value;
  profileCopy.destination = WM.el('es-profile-copy-destination').value;
  profileCopy.error = '';
  pendingMutation = 'eve_settings_copy_profile';
  setBusy(true);
  WM.send('eve_settings_copy_profile', profileCopy.source, profileCopy.mode,
    profileCopy.mode === 'new' ? profileCopy.name : profileCopy.destination)
    .then(function (result) {
      if (result && result.accepted) return;
      pendingMutation = '';
      profileCopy.error = result && result.error || 'Profile copy could not be started.';
      setBusy(false);
      renderProfileCopy();
    });
}
```

Wire Enter on the name field, explicit Cancel, mode changes, and submit. Changing root/server/profile resets `profileCopy` only after Python accepts the selection.

- [ ] **Step 7: Extend the sole completion handler**

Inside `onEveSettingsDone`, add a profile-copy branch before the generic success branch:

```javascript
if (completedMutation === 'eve_settings_copy_profile') {
  if (payload.published) resetProfileCopy();
  else profileCopy.error = payload.error || profileCopy.error;
} else if (completedMutation === 'eve_settings_copy') {
  copyFollowup = !!payload.ok;
  if (payload.ok) selected = {};
} else if (payload.ok) {
  clearCopyFollowup();
}
```

Always clear busy and refresh afterward. Do not register another handler.

- [ ] **Step 8: Add focused CSS**

Use the existing Profiles spacing, field, radio, and button tokens. Give the profile select the available row width, keep server/path subordinate, and make the disclosure a bordered inline region rather than a nested card or modal. Add explicit rules such as:

```css
#es-profile-copy-panel[hidden],
#es-profile-copy-new-fields[hidden],
#es-profile-copy-replace-fields[hidden] { display: none; }
```

Use the route scrollbar only. Add a `max-width: 840px` tier only if the base geometry does not fit the measured floor.

- [ ] **Step 9: Run web contract tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_profiles_page.py \
  tests/test_page_conventions.py \
  tests/test_bridge_contract.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit the integrated web change**

```bash
git add wingman/web/index.html wingman/web/evesettings.js wingman/web/style.css tests/test_profiles_page.py tests/test_page_conventions.py
git commit -m "feat: make Profiles profile-first"
```

---

### Task 7: Harness, Packaging, and Manual Contract

**Files:**
- Modify: `wingman/web/dev.js:1180-1695`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes: final Task 5 bridge result/completion shape and Task 6 element IDs.
- Produces: browser scenarios, packaging guard, and Windows release checklist.

- [ ] **Step 1: Add failing dev-harness tests**

Assert a specialized `api.eve_settings_copy_profile` double and named scenarios for:

```text
multiple profiles with Default selected
new profile disclosure
replace profile disclosure
invalid name
case-insensitive collision
accepted busy operation
successful create with selected destination
successful replace with retained source
EVE-running refusal
rollback failure
created profile with unsaved selection
```

Require the stub to validate expected source/mode/destination and to call the existing `onEveSettingsDone` rather than a new handler.

- [ ] **Step 2: Run harness tests and verify failure**

```bash
uv run --no-sync python -m pytest tests/test_dev_harness.py -k "profile" -v
```

Expected: FAIL because no profile-copy double or scenarios exist.

- [ ] **Step 3: Implement the dev double and scenarios**

Add a dedicated stub:

```javascript
api.eve_settings_copy_profile = function (expectedSource, mode, destination) {
  if (expectedSource !== eve.profile) {
    return Promise.resolve({ accepted: false, error: 'The selected profile changed.' });
  }
  window.setTimeout(function () {
    window.onEveSettingsDone({
      ok: true,
      operation: 'profile_copy',
      mode: mode,
      published: true,
      selection_persisted: true
    });
  }, 250);
  return Promise.resolve({ accepted: true, error: null });
};
```

Scenario-specific branches may return the approved inline errors or completion flags, but must not perform filesystem-like validation in JavaScript.

- [ ] **Step 4: Add the packaging assertion**

Extend `tests/test_packaging_completeness.py` so `wingman/evesettings/profilecopy.py` is covered by the existing explicit `wingman.evesettings` package. Do not edit `pyproject.toml`.

- [ ] **Step 5: Replace obsolete smoke expectations**

In `docs/smoke-checklist.md`, update the Profiles section rather than appending contradictory steps. Include:

- no folder, one/multiple profiles, multiple servers;
- root/server/profile folder picks showing canonical context;
- route re-entry and keyboard-only disclosure use;
- create success and launcher visibility observation;
- replace confirm/decline, backup, and retained source;
- running and unknown EVE refusal;
- created-but-selection-unsaved warning;
- caught publication failure with rollback and failed rollback recovery;
- hard-kill boundary relying on Backups;
- actual Windows server/profile junction refusal;
- 840×625 at 100% and 200% scaling.

- [ ] **Step 6: Run harness and packaging tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_dev_harness.py \
  tests/test_packaging_completeness.py \
  tests/test_profiles_page.py \
  tests/test_bridge_contract.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit supporting contracts**

```bash
git add wingman/web/dev.js tests/test_dev_harness.py tests/test_packaging_completeness.py docs/smoke-checklist.md
git commit -m "test: cover profile folder management flows"
```

---

### Task 8: Polish and Full Verification

**Files:**
- Review: every file changed since `999cc8d`
- Modify: only high-confidence fixes found by required polish

**Interfaces:**
- Consumes: completed Tasks 1–7.
- Produces: review-ready branch with fresh verification evidence.

- [ ] **Step 1: Run focused subsystem verification**

```bash
uv run --no-sync python -m pytest \
  tests/test_evesettings_tree.py \
  tests/test_evesettings_profilecopy.py \
  tests/test_evesettings_backup.py \
  tests/test_preview_discovery.py \
  tests/test_api_evesettings.py \
  tests/test_profiles_page.py \
  tests/test_page_conventions.py \
  tests/test_bridge_contract.py \
  tests/test_dev_harness.py \
  tests/test_packaging_completeness.py -v
```

Expected: PASS with only platform-declared skips.

- [ ] **Step 2: Run the required changed-code polish pass**

Invoke `polish-core --fix` against `999cc8d..HEAD`. Inspect every edit, keep only high-confidence in-scope corrections, and rerun the focused command from Step 1.

- [ ] **Step 3: Run all CI-equivalent automated gates**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: 0 failures and 0 lint/format errors.

- [ ] **Step 4: Inspect final scope and diff**

```bash
git status --short
git diff --check 999cc8d..HEAD
git diff --stat 999cc8d..HEAD
git diff 999cc8d..HEAD -- wingman tests docs/smoke-checklist.md
```

Confirm no debug output, placeholder text, second Profiles completion handler, second accent action, unrelated refactor, package-list change, or historical-doc edit.

- [ ] **Step 5: Complete Windows-only verification**

Run the focused Python suite on Windows and execute the revised Profiles smoke checklist on a real WebView2 page. Record any unperformed manual item explicitly; do not claim the screen is verified from lexical pytest coverage.

- [ ] **Step 6: Explain the final change**

Invoke `change-explainer` after fresh verification. Include architecture, rollback boundary, legacy-root behavior, exact copy domain, verification performed, manual gaps, and reviewer focus.

- [ ] **Step 7: Commit polish-only changes when present**

If Step 2 changed files:

```bash
git add wingman tests docs/smoke-checklist.md
git commit -m "fix: polish profile folder management"
```

If Step 2 made no changes, leave the existing task commits unchanged.
