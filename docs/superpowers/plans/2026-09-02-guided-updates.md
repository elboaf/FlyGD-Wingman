# Guided Application Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guided Wingman updater that checks GitHub once after page readiness, shows availability in Settings, securely downloads and verifies the stable installer, and launches the normal visible installer after explicit confirmation and orderly shutdown.

**Architecture:** A new `wingman/updates.py` owns strict release parsing, every-hop download validation, staging, attachment policy, protected final verification, and `ShellExecuteExW`. `Api` owns the process-local update state machine and a shared upload/update/quit claim boundary; the web layer only renders semantic state and requests actions. The existing Inno installer remains the only writer of the installed application tree.

**Tech Stack:** Python 3.11 stdlib (`urllib`, `json`, `hashlib`, `tempfile`, `ctypes`, `threading`), pytest, pywebview 6.2.1, plain ES5 JavaScript/HTML/CSS, Inno Setup, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-02-guided-updates-design.md`

## Global Constraints

- Windows-only installation; release lookup and pure validation remain importable and testable on Linux.
- Query `https://api.github.com/repos/elboaf/FlyGD-Wingman/releases/latest` once per process after page readiness, including `--hidden` login starts; never block startup and never poll.
- Only stable, non-draft releases with strict `vMAJOR.MINOR.PATCH` tags are eligible.
- Require exact release-tag, installer-filename, size, and SHA-256 metadata agreement. The expected asset is `FlyGD-Wingman-Setup-MAJOR.MINOR.PATCH.exe` and the defensive maximum is 256 MiB.
- Validate the initial asset URL and every redirect hop: HTTPS, default port, no userinfo, and an exact hostname allowlist. Never trust a suffix wildcard.
- GitHub's asset SHA-256 proves same-channel integrity, not publisher identity. Do not describe it as a signature.
- Run `IAttachmentExecute.Save` before final verification. Then hold a read-permitting, write/delete-denying file handle while hashing and through launch.
- Launch only with `ShellExecuteExW`, normal `open`, `SEE_MASK_NOASYNC | SEE_MASK_NOCLOSEPROCESS`, and no `SEE_MASK_NOZONECHECKS`. Do not use `CreateProcess` or `subprocess.Popen` for Setup.
- Installation is disabled outside a frozen Wingman build.
- Installation refuses a claimed or active upload. New uploads and retries refuse an active update handoff.
- Tray Quit refuses `handing_off`, `revalidating`, and `launching`; successful update launch owns one idempotent orderly shutdown.
- Staging is confined to `paths.tmp_dir() / "updates"`; handed-off files have durable classification and `UPDATE_STALE_AFTER = timedelta(days=7)`.
- Show availability via an accessible Settings-gear badge and Settings > General > About Wingman. No banner, tray notification, new destination, release-notes renderer, skipped-version state, or updater preference.
- Automatic failures are quiet; manual failures are specific and retryable.
- Every non-method `Api` attribute remains underscore-prefixed. Workers reach the page only through `_push`; every literal push is in `WM.HANDLERS` and registered.
- No framework, bundler, browser-native confirm, prompt, or alert. Use `WM.confirm` and existing design primitives.
- The published privacy policy must disclose the automatic GitHub request before release; this is a release gate, not optional documentation.

---

## File Structure

### New files

- `wingman/updates.py` — release metadata, strict origin policy, streamed staging, SHA-256, attachment services, protected file identity, shell launch, and stale cleanup.
- `tests/test_updates.py` — Linux-safe unit coverage for every pure/native seam in `updates.py`.
- `tests/test_api_updates.py` — update state machine, concurrency barriers, download/install orchestration, source-build guard, and recovery.
- `tests/manual/update_harness.py` — explicit opt-in Windows native harness; never packaged.
- `tests/manual/update_fixture.iss` — harmless Inno fixture using a test-only mutex.
- `tests/manual/README.md` — exact build/run/fault-injection commands and expected native outcomes.

### Modified files

- `wingman/ui/api.py` — process-local update state, worker orchestration, shared upload/update/quit claims, and bridge methods.
- `wingman/__main__.py` — idempotent window shutdown callback, tray Quit arbitration, and post-readiness startup composition.
- `wingman/web/app.js` — update handler allowlist and Settings-gear badge.
- `wingman/web/settings.js` — General-entry status read, update renderer, check/download/install actions, and confirmation.
- `wingman/web/index.html` — About-card update status, progress, and buttons.
- `wingman/web/style.css` — gear badge and compact update-block/progress styling using existing tokens.
- `wingman/web/dev.js` — bridge doubles and fake current/available/downloading/ready/error states.
- `tests/test_api_upload.py`, `tests/test_api_quit.py`, `tests/test_api_quick_actions.py`, `tests/test_upload_media_close.py` — update direct thread fixtures and pin claim cleanup.
- `tests/test_startup.py` — post-readiness auth plus updater ordering and hidden-start behavior.
- `tests/test_bridge_contract.py`, `tests/test_dev_harness.py`, `tests/test_settings_page.py`, `tests/test_page_conventions.py`, `tests/test_chrome.py` — lexical bridge/UI/accessibility contracts.
- `packaging/write_version_iss.py` — reusable tag/source agreement check and `--expect-tag` CLI option.
- `.github/workflows/release.yml`, `tests/test_packaging_version.py` — gate release build/publication on tag/source agreement.
- `README.md`, `DESIGN.md`, `docs/smoke-checklist.md` — network/privacy behavior, deliberate startup-fetch exception, repeatable native checks, and release policy gate.

---

### Task 1: Strict Release Discovery

**Files:**
- Create: `wingman/updates.py`
- Create: `tests/test_updates.py`

**Interfaces:**
- Produces: `Version = tuple[int, int, int]`
- Produces: `ReleaseInfo(version, tag, asset_name, url, size, sha256, content_type)`
- Produces: `UpdateFailure(stage: str, code: str, detail: str = "")`
- Produces: `parse_version(value: str, *, tagged: bool = False) -> Version`
- Produces: `release_from_payload(payload: object, current_version: str) -> ReleaseInfo | None`
- Produces: `latest_release(current_version: str = __version__, *, urlopen=urllib.request.urlopen, timeout: float = 10.0) -> ReleaseInfo | None`
- Consumed later by: Tasks 2, 3, 5, 6, and 9.

- [ ] **Step 1: Write failing tests for strict version and release parsing**

Add table-driven tests that establish the accepted grammar and exact metadata contract:

```python
@pytest.mark.parametrize(
    ("value", "tagged", "expected"),
    [
        ("4.8.0", False, (4, 8, 0)),
        ("v4.9.0", True, (4, 9, 0)),
    ],
)
def test_parse_version_accepts_only_three_numeric_segments(value, tagged, expected):
    assert updates.parse_version(value, tagged=tagged) == expected


@pytest.mark.parametrize("value", ["4.8", "4.8.0.1", "v4.8.0", "4.8.0-rc1", "04.8.0"])
def test_untagged_version_rejects_every_other_shape(value):
    with pytest.raises(updates.UpdateFailure, match="version"):
        updates.parse_version(value)


def test_release_metadata_must_agree_on_tag_filename_size_and_digest():
    payload = release_payload(tag="v4.9.0", version="4.9.0")
    release = updates.release_from_payload(payload, "4.8.0")
    assert release == updates.ReleaseInfo(
        version=(4, 9, 0),
        tag="v4.9.0",
        asset_name="FlyGD-Wingman-Setup-4.9.0.exe",
        url="https://github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/FlyGD-Wingman-Setup-4.9.0.exe",
        size=77_008_252,
        sha256="ab" * 32,
        content_type="application/x-msdos-program",
    )
```

Also cover draft/prerelease, same/older versions returning `None`, malformed JSON shape, duplicate expected assets, mismatched filename, zero/negative/over-256-MiB size, missing/malformed digest, non-HTTPS URL, userinfo, non-default port, and unexpected content type. Accept only `application/x-msdos-program` and `application/octet-stream` as executable asset metadata types.

- [ ] **Step 2: Run the discovery tests and verify RED**

Run:

```bash
uv run --no-sync python -m pytest tests/test_updates.py -k "parse_version or release_metadata or latest_release" -v
```

Expected: collection/import failure because `wingman.updates` does not exist.

- [ ] **Step 3: Implement immutable metadata and strict validation**

Start `wingman/updates.py` with these concrete definitions:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.request

from . import __version__

RELEASES_API = "https://api.github.com/repos/elboaf/FlyGD-Wingman/releases/latest"
MAX_INSTALLER_BYTES = 256 * 1024 * 1024
_VERSION_RE = re.compile(r"(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
_DIGEST_RE = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")
_CONTENT_TYPES = {"application/x-msdos-program", "application/octet-stream"}
Version = tuple[int, int, int]


class UpdateFailure(RuntimeError):
    def __init__(self, stage: str, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.stage = stage
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReleaseInfo:
    version: Version
    tag: str
    asset_name: str
    url: str
    size: int
    sha256: str
    content_type: str
```

Implement `parse_version`, `release_from_payload`, and `latest_release`. `latest_release` must construct a `urllib.request.Request` with:

```python
{
    "Accept": "application/vnd.github+json",
    "User-Agent": f"FlyGD-Wingman/{current_version} (+https://github.com/elboaf/FlyGD-Wingman)",
    "X-GitHub-Api-Version": "2022-11-28",
}
```

Decode UTF-8 JSON, turn network/JSON failures into `UpdateFailure("check", "network"|"metadata", detail)`, and never return arbitrary release URLs to the UI layer.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run --no-sync python -m pytest tests/test_updates.py -k "parse_version or release_metadata or latest_release" -v
```

Expected: all selected tests pass without network access.

- [ ] **Step 5: Run Ruff and commit**

```bash
uv run --extra dev ruff check wingman/updates.py tests/test_updates.py
uv run --extra dev ruff format --check wingman/updates.py tests/test_updates.py
git add wingman/updates.py tests/test_updates.py
git commit -m "feat: validate Wingman release metadata"
```

---

### Task 2: Safe Streaming and Staging Lifecycle

**Files:**
- Modify: `wingman/updates.py`
- Modify: `tests/test_updates.py`

**Interfaces:**
- Consumes: `ReleaseInfo`, `UpdateFailure` from Task 1.
- Produces: `SafeRedirectHandler(urllib.request.HTTPRedirectHandler)`
- Produces: `download_release(release: ReleaseInfo, staging_root: Path, *, opener=None, on_progress=None) -> Path`
- Produces: `write_handoff_marker(path: Path, release: ReleaseInfo) -> Path` and `remove_handoff_marker(marker: Path) -> None`, preserving the installer path across shell launch.
- Produces: `cleanup_staging(staging_root: Path, *, now=None) -> None`
- Produces: `UPDATE_STALE_AFTER = timedelta(days=7)`
- Consumed later by: Tasks 3, 6, 9, and 10.

- [ ] **Step 1: Write failing origin-policy and every-hop redirect tests**

Use an injected opener/redirect harness and assert each URL independently:

```python
@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://user@github.com/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://github.com:444/elboaf/FlyGD-Wingman/releases/download/v4.9.0/setup.exe",
        "https://github.com.evil.example/setup.exe",
    ],
)
def test_download_origin_rejects_unsafe_urls(url):
    with pytest.raises(updates.UpdateFailure, match="origin"):
        updates.validate_download_origin(url)


def test_redirect_handler_rejects_a_disallowed_intermediate_hop():
    handler = updates.SafeRedirectHandler()
    request = urllib.request.Request("https://github.com/owner/repo/releases/download/v1/setup.exe")
    with pytest.raises(updates.UpdateFailure, match="origin"):
        handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/hop")
```

Pin exact allowed hosts in the test from the module constant: initial `github.com`, plus only the currently observed exact GitHub release-asset host names. Do not accept `endswith("githubusercontent.com")`.

- [ ] **Step 2: Write failing streamed-download and cleanup tests**

Use a response fake that yields bounded chunks and records reads:

```python
def test_download_streams_and_reports_bytes(tmp_path):
    release = release_info(payload=b"installer")
    progress = []
    path = updates.download_release(
        release,
        tmp_path,
        opener=fake_opener(payload=b"installer"),
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert path.read_bytes() == b"installer"
    assert progress[-1] == (len(b"installer"), len(b"installer"))


def test_download_removes_partial_file_on_digest_mismatch(tmp_path):
    release = replace(release_info(payload=b"good"), sha256="00" * 32)
    with pytest.raises(updates.UpdateFailure, match="checksum"):
        updates.download_release(release, tmp_path, opener=fake_opener(payload=b"bad"))
    assert list(tmp_path.iterdir()) == []
```

Add cases for interrupted reads, final byte count below metadata, a stream exceeding metadata, a stream exceeding 256 MiB, and duplicate partial names. Add cleanup tests proving:

- ordinary `.partial` and `.ready.exe` files older than the policy are removed;
- a `.handoff.json` sidecar classification survives process memory without renaming the executable;
- handed-off files younger than seven days remain;
- handed-off files at least seven days old are removed;
- sharing violations are swallowed as safe retention; and
- no file outside the dedicated staging directory is touched.

- [ ] **Step 3: Run the focused tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_updates.py -k "origin or redirect or download or staging or handed" -v
```

Expected: failures for missing redirect, download, and cleanup interfaces.

- [ ] **Step 4: Implement redirect validation and bounded streaming**

Add:

```python
DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "release-assets.githubusercontent.com",
})
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
UPDATE_STALE_AFTER = datetime.timedelta(days=7)


def validate_download_origin(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or (parsed.hostname or "").lower() not in DOWNLOAD_HOSTS
    ):
        raise UpdateFailure("download", "origin", url)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_origin(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
```

Import `datetime`, `os`, `tempfile`, `urllib.parse`, `Path`, and the existing `atomicio` module. `download_release` must validate `release.url` before opening, build an opener containing `SafeRedirectHandler` when no opener is injected, create the staging directory and an exclusive `*.partial` file with `tempfile.mkstemp`, update SHA-256 while writing 1 MiB chunks, stop before writing a chunk that exceeds either bound, `flush` and `os.fsync`, compare exact byte count and digest, then atomically rename to `*.ready.exe`. Remove the partial on every exception while preserving the original `UpdateFailure` stage/code.

- [ ] **Step 5: Implement durable classification and bounded cleanup**

Keep the installer path stable after shell launch. Durable classification is an atomic, fsynced sidecar in the same updater directory:

```python
def write_handoff_marker(path: Path, release: ReleaseInfo) -> Path:
    if not path.name.endswith(".ready.exe"):
        raise UpdateFailure("cleanup", "unexpected-path", path.name)
    marker = path.with_name(path.name + ".handoff.json")
    payload = {
        "file": path.name,
        "sha256": release.sha256,
        "version": ".".join(map(str, release.version)),
    }
    atomicio.write_atomic(
        marker,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
    return marker


def remove_handoff_marker(marker: Path) -> None:
    marker.unlink(missing_ok=True)
```

Do not rename an installer after `ShellExecuteExW` has started it. Cleanup accepts only generated `*.partial`, `*.ready.exe`, and matching `*.ready.exe.handoff.json` names, uses `lstat`, rejects symlinks and marker paths that escape the directory, compares age against `UPDATE_STALE_AFTER`, and catches `PermissionError`/sharing-related `OSError` without forcing deletion. Ordinary shutdown deletes an unmarked ready file; a valid marker preserves its matching installer until stale cleanup.

- [ ] **Step 6: Run focused tests, full updater tests, and commit**

```bash
uv run --no-sync python -m pytest tests/test_updates.py -v
uv run --extra dev ruff check wingman/updates.py tests/test_updates.py
uv run --extra dev ruff format --check wingman/updates.py tests/test_updates.py
git add wingman/updates.py tests/test_updates.py
git commit -m "feat: stage verified update downloads"
```

---

### Task 3: Windows Attachment, Protected Verification, and Shell Launch

**Files:**
- Modify: `wingman/updates.py`
- Modify: `tests/test_updates.py`
- Reference: `wingman/fightrecorder.py:197-247`

**Interfaces:**
- Consumes: `ReleaseInfo`, staged `*.ready.exe` from Tasks 1–2.
- Produces: `save_attachment(path: Path, source_url: str) -> None`
- Produces: `verify_after_attachment(release: ReleaseInfo, path: Path, *, attachment=save_attachment, locked_open=None) -> None`
- Produces: `launch_verified(release: ReleaseInfo, path: Path, *, before_launch=None, attachment=save_attachment, locked_open=None, shell_execute=None) -> int`
- Produces: `close_process_handle(handle: int) -> None`
- Guarantees: attachment processing precedes final hash; one write/delete-denying handle is retained through `ShellExecuteExW`.
- Consumed later by: Tasks 6 and 9.

- [ ] **Step 1: Write failing order and mutation tests**

Use spies rather than Windows APIs in CI:

```python
def test_launch_orders_attachment_lock_hash_then_shell(tmp_path):
    events = []
    path = write_installer(tmp_path, b"verified")
    release = release_info(payload=b"verified", path=path)

    handle = FakeLockedFile(path, events)
    process = updates.launch_verified(
        release,
        path,
        attachment=lambda p, u: events.append("attachment"),
        locked_open=lambda p: handle,
        before_launch=lambda: events.append("marker"),
        shell_execute=lambda locked_path: events.append("shell") or 42,
    )

    assert process == 42
    assert events == ["attachment", "open-locked", "hash", "marker", "shell", "close-locked"]


def test_attachment_success_that_replaces_file_is_rehashed_and_rejected(tmp_path):
    path = write_installer(tmp_path, b"verified")
    release = release_info(payload=b"verified", path=path)

    def replace_after_scan(_path, _url):
        path.write_bytes(b"different")

    with pytest.raises(updates.UpdateFailure, match="checksum"):
        updates.launch_verified(release, path, attachment=replace_after_scan, shell_execute=fail_if_called)
```

Add deleted, truncated, quarantined, identity-changed, and attachment-failure cases. Add a barrier test where a replacement thread runs after hashing but before shell launch and receives a sharing violation while the shell spy still sees the verified path.

- [ ] **Step 2: Write failing ShellExecute contract tests**

Inject fake `ole32`, `kernel32`, and `shell32` callables and assert:

```python
def test_shell_launch_uses_zone_checked_open_and_returns_a_process_handle(monkeypatch):
    calls = FakeWin32(process_handle=123)
    assert updates._shell_execute(Path("C:/Temp/update.ready.exe"), libs=calls) == 123
    info = calls.shell_info
    assert info.lpVerb == "open"
    assert info.fMask == updates.SEE_MASK_NOASYNC | updates.SEE_MASK_NOCLOSEPROCESS
    assert not info.fMask & updates.SEE_MASK_NOZONECHECKS
```

Cover `ShellExecuteExW == 0`, null `hProcess`, `ERROR_CANCELLED`, COM initialization failure, and closing the returned process handle exactly once.

- [ ] **Step 3: Run native-seam tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_updates.py -k "attachment or locked or shell or launch" -v
```

Expected: failures for missing native interfaces.

- [ ] **Step 4: Implement `IAttachmentExecute` through a narrow ctypes wrapper**

Use the documented CLSID/IID and vtable order; do not add pywin32/comtypes:

```python
CLSID_ATTACHMENT_SERVICES = "{4125DD96-E03A-4103-8F70-E0597D803B9C}"
IID_IATTACHMENT_EXECUTE = "{73DB1241-1E85-4581-8E4F-A81E1D0F8C57}"
ATTACHMENT_CLIENT_GUID = "{F86ACFFD-F7CC-4C62-8FCE-C747D5D94DB7}"
# IUnknown = 0..2; IAttachmentExecute methods:
# 3 SetClientTitle, 4 SetClientGuid, 5 SetLocalPath, 6 SetFileName,
# 7 SetSource, 8 SetReferrer, 9 CheckPolicy, 10 Prompt, 11 Save,
# 12 Execute, 13 SaveWithUI, 14 ClearClientState.
```

`save_attachment` must initialize COM on its worker, create `AttachmentServices`, call `SetClientGuid` with one source constant, `SetLocalPath(str(path))`, `SetSource(source_url)`, then `Save`; release the interface and call `CoUninitialize` in `finally`. Convert any failing HRESULT into `UpdateFailure("verify", "attachment", hex_hresult)`.

- [ ] **Step 5: Implement protected open and post-attachment verification**

On Windows use `CreateFileW` with read access and `FILE_SHARE_READ` only, then read/hash through that handle (or an `msvcrt.open_osfhandle` wrapper that does not close ownership twice). Capture stable file identity with `GetFileInformationByHandle`; re-check it before shell launch. The context manager must close exactly once on every branch. The Linux-test fallback exists only behind the injected `locked_open` seam and must not be selected in a frozen Windows build.

`verify_after_attachment` performs `save_attachment -> protected open -> identity/size/hash -> close`. `launch_verified` performs `save_attachment -> protected open -> identity/size/hash -> before_launch callback -> ShellExecuteExW while still open -> close protected handle`, returning the process handle. If `before_launch` raises, do not call the shell. This callback is the only place Task 6 writes the durable handoff marker without opening a post-verification replacement window.

- [ ] **Step 6: Implement shell launch with explicit COM and flags**

Reuse the `_SHELLEXECUTEINFO` layout and constants from `fightrecorder.py`, but use:

```python
info.fMask = SEE_MASK_NOASYNC | SEE_MASK_NOCLOSEPROCESS
info.lpVerb = "open"
info.lpFile = str(path)
info.lpParameters = None
info.nShow = SW_SHOWNORMAL
```

Initialize an STA with `CoInitializeEx(COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)`, require `ShellExecuteExW` success and non-null `hProcess`, and never set `SEE_MASK_NOZONECHECKS`. Return the handle without waiting; `close_process_handle` owns `CloseHandle` after durable handoff classification.

- [ ] **Step 7: Run updater tests and commit**

```bash
uv run --no-sync python -m pytest tests/test_updates.py -v
uv run --extra dev ruff check wingman/updates.py tests/test_updates.py
uv run --extra dev ruff format --check wingman/updates.py tests/test_updates.py
git add wingman/updates.py tests/test_updates.py
git commit -m "feat: launch verified updates through Windows shell"
```

---

### Task 4: Atomic Upload, Update, and Quit Claims

**Files:**
- Modify: `wingman/ui/api.py:379-510,1307-1468,1800-1840`
- Create: `tests/test_api_updates.py`
- Modify: `tests/test_api_upload.py`
- Modify: `tests/test_api_quit.py`
- Modify: `tests/test_api_quick_actions.py`
- Modify: `tests/test_upload_media_close.py`

**Interfaces:**
- Produces in `api.py`: private `_WorkGate` with `claim_upload`, `release_upload`, `claim_handoff`, `release_handoff`, `claim_quit`, `handoff_phase`, and `begin_update_shutdown`.
- Produces on `Api`: `_work_gate`, `_run_claimed_upload`, `_claim_quit`.
- Changes: `_busy()` reads the upload claim rather than thread liveness.
- Consumed later by: Task 6 update installation and `__main__.on_quit`.

- [ ] **Step 1: Write failing gate state-machine tests**

Create `tests/test_api_updates.py` with a private gate section that later updater tests extend in Tasks 5–6:

```python
def test_handoff_and_upload_claims_are_mutually_exclusive():
    gate = api_mod._WorkGate()
    assert gate.claim_upload()
    assert not gate.claim_handoff("handing_off")
    gate.release_upload()
    assert gate.claim_handoff("handing_off")
    assert not gate.claim_upload()


def test_quit_is_refused_during_each_handoff_phase():
    for phase in ("handing_off", "revalidating", "launching"):
        gate = api_mod._WorkGate()
        assert gate.claim_handoff(phase)
        assert not gate.claim_quit(force_upload=False)
```

Add idempotent update-shutdown, failed-handoff release, and quitting-blocks-new-upload cases.

- [ ] **Step 2: Write failing upload and retry race tests**

Use `threading.Barrier` to start two bridge-like threads simultaneously. Assert exactly one of upload or handoff claims succeeds. Repeat for `retry()`. Add a worker target that raises and prove the upload claim clears in `finally`.

```python
def test_upload_claim_lives_until_worker_finally(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    api._confirm_then_upload = lambda job: (entered.set(), release.wait(5))
    api.start_upload("Fight", "", False, ["r1"])
    assert entered.wait(1)
    assert api._busy()
    release.set()
    join(api)
    assert not api._busy()
```

Update all tests that assign `_upload_thread` directly to claim/release `_work_gate` explicitly. Keep thread assignment assertions where they test worker creation, but do not let a fake thread silently bypass the new claim invariant.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_api_upload.py tests/test_api_quit.py tests/test_api_quick_actions.py tests/test_upload_media_close.py -k "claim or busy or retry or quit or second_upload" -v
```

Expected: failures for missing `_WorkGate` and claim wrappers.

- [ ] **Step 4: Implement `_WorkGate` with one lock and no external blocking**

Use one condition-free lock and explicit state:

```python
class _WorkGate:
    def __init__(self):
        self._lock = threading.Lock()
        self._upload = False
        self._handoff = ""
        self._quitting = False

    def claim_upload(self) -> bool:
        with self._lock:
            if self._upload or self._handoff or self._quitting:
                return False
            self._upload = True
            return True

    def release_upload(self) -> None:
        with self._lock:
            self._upload = False
```

Implement the remaining transitions with the same rule: mutate booleans/phase only while locked; never wait, confirm, push, perform I/O, or launch while locked. `claim_quit(force_upload)` fails during handoff, respects ordinary upload confirmation, and marks `_quitting` atomically. `begin_update_shutdown` is idempotent when handoff owns shutdown.

- [ ] **Step 5: Route upload and retry workers through a `finally` release**

Immediately before assigning/starting `_upload_thread`, claim the gate. Wrap both targets:

```python
def _run_claimed_upload(self, target, *args) -> None:
    try:
        target(*args)
    finally:
        self._work_gate.release_upload()
```

If `Thread.start()` raises, release the claim synchronously and clear `_upload_thread`. `retry()` follows the identical claim path. `_busy()` returns `_work_gate.upload_claimed()` so the claim covers the pre-start window.

- [ ] **Step 6: Add `_claim_quit` without changing `__main__` yet**

`_claim_quit` performs the existing bounded upload confirmation first. After a yes, it atomically calls `claim_quit(force_upload=True)`; when idle it calls `claim_quit(False)` directly. If handoff won during the dialog, show the window, raise one informational alert—“Update installation is being prepared.”—and return `False`. Keep `_confirm_quit_if_busy` as a compatibility wrapper until Task 6 switches `__main__`, so intermediate tests stay readable.

- [ ] **Step 7: Run focused and adjacent tests, then commit**

```bash
uv run --no-sync python -m pytest tests/test_api_upload.py tests/test_api_quit.py tests/test_api_quick_actions.py tests/test_upload_media_close.py tests/test_poll_tick.py -v
uv run --extra dev ruff check wingman/ui/api.py tests/test_api_upload.py tests/test_api_quit.py tests/test_api_quick_actions.py tests/test_upload_media_close.py
uv run --extra dev ruff format --check wingman/ui/api.py tests/test_api_upload.py tests/test_api_quit.py tests/test_api_quick_actions.py tests/test_upload_media_close.py
git add wingman/ui/api.py tests/test_api_updates.py tests/test_api_upload.py tests/test_api_quit.py tests/test_api_quick_actions.py tests/test_upload_media_close.py
git commit -m "refactor: serialize upload and shutdown claims"
```

---

### Task 5: Update Check State and Gear Badge Contract

**Files:**
- Modify: `tests/test_api_updates.py`
- Modify: `wingman/ui/api.py:382-510,4300-4400`
- Modify: `wingman/web/app.js:49-58,285-325`
- Modify: `wingman/web/settings.js`
- Modify: `wingman/web/dev.js:550-630`
- Modify: `tests/test_bridge_contract.py`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_chrome.py`

**Interfaces:**
- Consumes: `updates.latest_release`, `_WorkGate`.
- Produces on `Api`: `update_status() -> dict`, `check_for_updates() -> dict`, `_start_update_check(automatic: bool) -> dict`, `_push_update_status()`, `_update_snapshot()`.
- Produces bridge event: `onUpdateStatus(payload)`.
- Reserves the private `_start_update_check(True)` call for Task 6's `_page_ready()` startup hook.
- Status payload: `{state, installed_version, available_version, update_available, downloaded_bytes, total_bytes, can_check, can_download, can_install, error}`. Python derives `update_available`; the page does not infer it from phase names.

- [ ] **Step 1: Write failing API status/check tests**

Use an injected update service and deterministic thread spawner:

```python
def test_automatic_check_is_single_flight_and_caches_available_release(tmp_path):
    service = FakeUpdates(release=release_info("4.9.0"), block=True)
    api, window = make_update_api(tmp_path, service)
    api._start_update_check(automatic=True)
    api._start_update_check(automatic=True)
    assert service.check_calls == 1
    service.release()
    join_update(api)
    assert api.update_status()["state"] == "available"
    assert api.update_status()["available_version"] == "4.9.0"
    assert api.update_status()["update_available"] is True


def test_automatic_failure_is_quiet_but_manual_failure_has_copy(tmp_path):
    api, window = make_update_api(tmp_path, FakeUpdates(failure="network"))
    api._start_update_check(automatic=True)
    join_update(api)
    assert api.update_status()["state"] == "unavailable"
    assert api.update_status()["error"] == ""
    api.check_for_updates()
    join_update(api)
    assert "Could not check for updates" in api.update_status()["error"]
```

Add current-release, malformed-metadata, missed-push repair, repeated manual click, and underscore-only attribute tests. Assert `get_settings()` does not call the service.

- [ ] **Step 2: Run API update tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_api_updates.py -k "check or status or automatic" -v
```

Expected: failures for missing methods and state.

- [ ] **Step 3: Implement `_UpdateRuntime` and check orchestration**

Define a private dataclass in `api.py`:

```python
@dataclass
class _UpdateRuntime:
    state: str = "idle"
    release: updates_mod.ReleaseInfo | None = None
    staged: Path | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str = ""
    automatic_failure: bool = False
    worker: threading.Thread | None = None
```

Add constructor injections `update_service=updates_mod`, `update_spawn=threading.Thread`, and `is_frozen=lambda: bool(getattr(sys, "frozen", False))`; store all three with underscore names. Protect runtime with `_update_lock`, but release it before spawning, joining, I/O, or `_push`. Only `idle/current/available/unavailable/check_failed/download_failed` may enter `checking`; `ready` cannot check again. Map `UpdateFailure` to the exact spec copy in one helper.

`update_status()` always returns a fresh dict. It sets `update_available` whenever a validated newer release remains cached, including downloading, ready, and recoverable-download-failure phases, so the gear does not flicker off mid-flow. `_push_update_status()` calls `_push("onUpdateStatus", payload)` outside the lock. A read repairs missed pushes by returning the complete snapshot. If creating an update worker fails, roll the state back under the lock and expose a retryable stage-specific error rather than leaving a permanent in-flight state.

- [ ] **Step 4: Add the handler contract and badge renderer**

Add `'onUpdateStatus'` literally to `WM.HANDLERS`. Register it in `app.js`, not dynamically:

```javascript
function renderUpdateBadge(payload) {
  var gear = WM.el('btn-settings');
  var available = !!payload.update_available;
  gear.classList.toggle('update-available', available);
  gear.title = available ? 'Settings — update available' : 'Settings';
  gear.setAttribute('aria-label', gear.title);
  document.dispatchEvent(new CustomEvent('wm:update-status', {detail: payload}));
}
WM.handle('onUpdateStatus', renderUpdateBadge);
```

The About renderer is added in Task 7; for now `settings.js` only records the latest payload from `wm:update-status`, preventing a handler registration gap. Add dev doubles:

```javascript
api.update_status = function () { return Promise.resolve(devUpdateState()); };
api.check_for_updates = function () { return Promise.resolve(devUpdateState()); };
```

- [ ] **Step 5: Extend lexical contract tests**

Assert the literal handler, both dev doubles, gear `aria-label` update, and the absence of updater calls from `get_settings`. Run:

```bash
uv run --no-sync python -m pytest tests/test_api_updates.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_chrome.py -v
```

Expected: all pass.

- [ ] **Step 6: Run Ruff and commit**

```bash
uv run --extra dev ruff check wingman/ui/api.py tests/test_api_updates.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_chrome.py
uv run --extra dev ruff format --check wingman/ui/api.py tests/test_api_updates.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_chrome.py
git add wingman/ui/api.py wingman/web/app.js wingman/web/settings.js wingman/web/dev.js tests/test_api_updates.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_chrome.py
git commit -m "feat: check for Wingman updates after startup"
```

---

### Task 6: Download, Install, Quit Arbitration, and Startup Wiring

**Files:**
- Modify: `wingman/ui/api.py`
- Modify: `wingman/__main__.py:720-755,775-850`
- Modify: `tests/test_api_updates.py`
- Modify: `tests/test_api_quit.py`
- Modify: `tests/test_startup.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: `download_release`, `verify_after_attachment`, `launch_verified`, `write_handoff_marker`, `remove_handoff_marker`, `cleanup_staging`, `_WorkGate`.
- Produces on `Api`: `download_update() -> dict`, `install_update() -> dict`, `shutdown_updates() -> None`, `_request_shutdown: Callable[[], None] | None`.
- Changes startup callback: `window_mod.run(api._page_ready)`.
- Changes tray quit glue: `api._claim_quit()` followed by one idempotent `destroy_windows()`.

- [ ] **Step 1: Write failing download-state tests**

```python
def test_download_reports_progress_then_ready(tmp_path):
    service = FakeUpdates(release=release_info("4.9.0"), staged=tmp_path / "update.ready.exe")
    api, window = available_api(tmp_path, service)
    api.download_update()
    service.progress(10, 20)
    join_update(api)
    states = pushed_update_states(window)
    assert "downloading" in states
    assert states[-1] == "ready"
    assert api.update_status()["can_install"] is True


def test_source_checkout_can_check_and_download_but_cannot_install(tmp_path):
    api, _window = available_api(tmp_path, FakeUpdates(), frozen=False)
    assert api.update_status()["can_download"] is True
    api.download_update()
    join_update(api)
    assert api.update_status()["state"] == "ready"
    assert api.update_status()["can_install"] is False
    assert api.install_update()["state"] == "ready"
```

Cover interrupted, checksum, attachment, and staging failures with exact stage copy; verify one download at a time and partial cleanup delegated to the service.

- [ ] **Step 2: Write failing install and race tests**

Add barriers for each race required by the spec:

```python
def test_install_claim_excludes_upload_before_revalidation(tmp_path):
    barrier = threading.Barrier(2)
    api = ready_api(tmp_path, barrier_service(barrier))
    api.install_update()
    barrier.wait(timeout=1)  # worker is in revalidation with handoff claimed
    api.start_upload("Fight", "", False, ["r1"])
    assert api._alert.raised[-1][2] == "Update installation is being prepared."


def test_tray_quit_is_refused_during_every_handoff_phase(tmp_path):
    for phase in ("handing_off", "revalidating", "launching"):
        api = ready_api(tmp_path)
        api._work_gate.claim_handoff(phase)
        assert api._claim_quit() is False
```

Also race `retry()` against installation; delete/replace/truncate the ready file before install; simulate shell failure/null process handle; assert handoff clears and state recovers; assert successful shell launch durably classifies before closing process handle and before shutdown callback; assert updater shutdown is idempotent and no worker push/mutation occurs after cleanup begins.

- [ ] **Step 3: Run orchestration tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_api_updates.py tests/test_api_quit.py -k "download or install or handoff or quit or shutdown" -v
```

Expected: failures for missing download/install/lifecycle methods.

- [ ] **Step 4: Implement download and install workers**

`download_update()` requires `available`, changes to `downloading`, and spawns one named daemon worker; source checkouts may exercise this explicit download path but may not install or shell-launch it. A thread-construction or `.start()` failure rolls state back to a retryable failure and releases any claim. The progress callback updates only byte counts while state is still `downloading`, then pushes outside the lock. The success sequence is:

```python
path = self._update_service.download_release(release, staging_root, on_progress=progress)
self._update_service.verify_after_attachment(release, path)
# under _update_lock: state="ready", staged=path
self._push_update_status()
```

`install_update()` requires `ready`, atomically claims handoff, changes phase to `handing_off`, and spawns a named daemon worker. Thread-construction or `.start()` failure clears handoff and returns to `ready`. The worker changes gate/runtime to `revalidating` and captures the marker path through a callback:

```python
marker = None

def before_launch() -> None:
    nonlocal marker
    marker = self._update_service.write_handoff_marker(path, release)

try:
    process = self._update_service.launch_verified(
        release, path, before_launch=before_launch
    )
except Exception:
    if marker is not None:
        self._update_service.remove_handoff_marker(marker)
    raise
```

The callback runs after final hash while the protected file handle is held and before `ShellExecuteExW`; marker failure therefore prevents launch. After shell success, change to `launching`, close the returned process handle, atomically call `begin_update_shutdown`, then invoke `_request_shutdown`. If shell launch fails after the marker was written, remove the marker, release handoff, and return to `ready`. Changed/unverifiable bytes return to `download_failed`.

- [ ] **Step 5: Extract idempotent shutdown glue in `__main__.py`**

Replace direct closure destruction with:

```python
shutdown_lock = threading.Lock()
shutdown_started = False

def destroy_windows() -> None:
    nonlocal shutdown_started
    with shutdown_lock:
        if shutdown_started:
            return
        shutdown_started = True
    # existing sig-bar-first destruction, then window.destroy()


def on_quit() -> None:
    if window is not None and api._claim_quit():
        destroy_windows()
```

Assign `api._request_shutdown = destroy_windows` after defining it. The update worker reaches this callback only after shell success, durable handoff, and gate transition. Preserve the sig-bar-first reason/comment and close-hides behavior.

Call `api.shutdown_updates()` in final cleanup before preview/skills shutdown; it removes unhanded ready files, preserves durable handed-off files, marks update state closed, and prevents later worker pushes.

- [ ] **Step 6: Compose auth and update work after page readiness**

Implement:

```python
def _page_ready(self) -> None:
    self.refresh_auth()
    self._start_update_check(automatic=True)
```

Change `window_mod.run(api.refresh_auth)` to `window_mod.run(api._page_ready)`. Update `tests/test_startup.py` to assert `run` occurs before both calls, exactly one automatic check occurs on normal and `--hidden` launches, `get_settings` stays network-free, and the callback is `api._page_ready` rather than a fixed sleep/timer.

- [ ] **Step 7: Run lifecycle suites and commit**

```bash
uv run --no-sync python -m pytest tests/test_api_updates.py tests/test_api_upload.py tests/test_api_quit.py tests/test_startup.py tests/test_main.py tests/test_main_engine.py tests/test_poll_tick.py -v
uv run --extra dev ruff check wingman/ui/api.py wingman/__main__.py tests/test_api_updates.py tests/test_api_quit.py tests/test_startup.py
uv run --extra dev ruff format --check wingman/ui/api.py wingman/__main__.py tests/test_api_updates.py tests/test_api_quit.py tests/test_startup.py
git add wingman/ui/api.py wingman/__main__.py tests/test_api_updates.py tests/test_api_upload.py tests/test_api_quit.py tests/test_startup.py tests/test_main.py
git commit -m "feat: hand verified updates to Wingman installer"
```

---

### Task 7: About-Card Update UI and Guided Confirmation

**Files:**
- Modify: `wingman/web/index.html:1356-1402`
- Modify: `wingman/web/settings.js:200-315,470-520`
- Modify: `wingman/web/app.js`
- Modify: `wingman/web/style.css:490-505,3970-3990`
- Modify: `wingman/web/dev.js`
- Modify: `tests/test_settings_page.py`
- Modify: `tests/test_page_conventions.py`
- Modify: `tests/test_dev_harness.py`
- Modify: `tests/test_chrome.py`
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes bridge methods/events from Tasks 5–6.
- Produces UI states: idle/checking/current/unavailable/available/downloading/ready/check_failed/download_failed/handing_off/revalidating/launching.
- Produces page action flow: `WM.confirm('Install update?', ...) -> WM.send('install_update')`.

- [ ] **Step 1: Write failing lexical UI tests**

Assert exact accessible structure, not screenshots:

```python
def test_about_card_has_live_update_status_progress_and_actions():
    card = about_card_html()
    assert 'aria-label="Settings"' in HTML
    assert 'id="update-status"' in card and 'role="status"' in card
    assert 'id="update-progress"' in card and '<progress' in card
    for control in ("btn-update-check", "btn-update-download", "btn-update-install"):
        assert f'id="{control}"' in card


def test_install_uses_app_confirm_before_bridge_call():
    code = SETTINGS.read_text(encoding="utf-8")
    confirm = code.index("WM.confirm('Install update?'")
    send = code.index("WM.send('install_update')", confirm)
    assert confirm < send
    assert "window.confirm" not in code
```

Add tests for gear badge class/title/aria-label, `update-progress[hidden]`, determinate `max/value`, no second accent button, General-section fetch only on `wm:section === 'general'`, and every page method present in `dev.js`.

- [ ] **Step 2: Run UI tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_settings_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_chrome.py -k "update or about or gear" -v
```

Expected: failures for missing markup and renderer.

- [ ] **Step 3: Add About-card markup**

First give the existing `#btn-settings` button `aria-label="Settings"` so its name exists before the first update result. Inside the existing About Wingman card, after `about-version`, add:

```html
<div class="update-block">
  <p class="hint" id="update-status" role="status" aria-live="polite">
    Update status not checked.
  </p>
  <progress id="update-progress" max="1" value="0" hidden></progress>
  <div class="actions update-actions">
    <button class="btn" id="btn-update-check">Check again</button>
    <button class="btn" id="btn-update-download" hidden>Download update</button>
    <button class="btn" id="btn-update-install" hidden>Install update</button>
  </div>
</div>
```

Keep Start-on-login and `msg-about`; do not add an accent button or a new card heading.

- [ ] **Step 4: Implement one table-driven renderer in `settings.js`**

Use one `renderUpdate(payload)` that sets text, semantic progress, hidden states, and `WM.setEnabled` from payload booleans. It must not derive action permission independently from state. On General entry call `WM.send('update_status').then(renderUpdate)`; a running automatic check returns its cached state and is not restarted.

Button behavior:

```javascript
WM.el('btn-update-check').addEventListener('click', function () {
  WM.send('check_for_updates').then(function (p) { if (p) renderUpdate(p); });
});
WM.el('btn-update-download').addEventListener('click', function () {
  WM.send('download_update').then(function (p) { if (p) renderUpdate(p); });
});
function confirmInstall() {
  WM.confirm('Install update?',
             'Wingman will close and open the normal installer.').then(function (ok) {
    if (ok) WM.send('install_update').then(function (p) { if (p) renderUpdate(p); });
  });
}
WM.el('btn-update-install').addEventListener('click', confirmInstall);
```

Track the previous phase locally. When a download transitions from `downloading` to `ready`, invoke `confirmInstall()` once. Declining keeps the Install button. Later clicks confirm again. Automatic failures render neutral “Update status unavailable”; manual failures render Python's stage-specific `error`.

- [ ] **Step 5: Add token-only styling and dev-state controls**

Use existing color tokens only. Add a positioned `::after` badge on `.winbtn.gear.update-available`, with `pointer-events: none`; accessibility comes from title/aria-label. Style `<progress>` for the dark surface and add `#update-progress[hidden] { display: none; }`. Keep focus behavior inherited from existing button rules and stop any animation under reduced motion.

Extend `dev.js` with a `devUpdateState` function and query-string state selection such as `?dev=1&update=available|downloading|ready|error`; each returns the exact production payload shape. Do not fabricate update data anywhere else.

- [ ] **Step 6: Add UI smoke cases and run tests**

Add checklist entries for current, checking, available, automatic offline, manual failure, progress, declined install, retained Install action, active-upload refusal, gear tooltip/aria state, keyboard focus, 840x625 layout, and real WebView2 rendering.

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_chrome.py tests/test_bridge_contract.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit the web surface**

```bash
git add wingman/web/index.html wingman/web/settings.js wingman/web/app.js wingman/web/style.css wingman/web/dev.js tests/test_settings_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_chrome.py docs/smoke-checklist.md
git commit -m "feat: show and download Wingman updates in Settings"
```

---

### Task 8: Release Tag and Source-Version Gate

**Files:**
- Modify: `packaging/write_version_iss.py`
- Modify: `.github/workflows/release.yml:44-67`
- Modify: `tests/test_packaging_version.py`

**Interfaces:**
- Produces: `verify_release_tag(tag: str, source: Path = SOURCE) -> str`
- Produces CLI: `python packaging/write_version_iss.py --expect-tag vX.Y.Z`
- Workflow guarantee: build and publish cannot run when the pushed tag differs from `wingman.__version__`.

- [ ] **Step 1: Write failing generator and workflow tests**

```python
def test_release_tag_must_match_the_source_version(tmp_path):
    source = tmp_path / "__init__.py"
    source.write_text('__version__ = "4.9.0"\n', encoding="utf-8")
    assert write_version_iss.verify_release_tag("v4.9.0", source) == "4.9.0"
    with pytest.raises(SystemExit, match=r"tag v5\.0\.0.*source version 4\.9\.0"):
        write_version_iss.verify_release_tag("v5.0.0", source)


def test_release_workflow_checks_the_tag_before_building():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    check = text.index("--expect-tag")
    build = text.index("uses: ./.github/actions/build-installer")
    publish = text.index("uses: softprops/action-gh-release")
    assert check < build < publish
    assert "github.ref_name" in text[check - 300:check + 300]
```

- [ ] **Step 2: Run packaging tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_packaging_version.py -k "release_tag or workflow" -v
```

Expected: failure because `verify_release_tag` and workflow step do not exist.

- [ ] **Step 3: Extend the existing stdlib generator**

Use `argparse` only. `verify_release_tag` reads through existing `read_version`, computes `expected = f"v{version}"`, and raises `SystemExit(f"release tag {tag} does not match source version {version}")` on mismatch. `--expect-tag` verifies first, then preserves the current generation/write behavior so the existing build action remains unchanged.

Add this before the composite build action in `release.yml`:

```yaml
- name: Verify release tag matches source version
  run: python packaging/write_version_iss.py --expect-tag "${{ github.ref_name }}"
```

The script is already in CI's bare-Python allowlist; do not add a second parser or version source.

- [ ] **Step 4: Run packaging and workflow-adjacent tests**

```bash
uv run --no-sync python -m pytest tests/test_packaging_version.py tests/test_packaging_completeness.py -v
uv run --extra dev ruff check packaging/write_version_iss.py tests/test_packaging_version.py
uv run --extra dev ruff format --check packaging/write_version_iss.py tests/test_packaging_version.py
```

Expected: pass; generated `packaging/version.iss` remains ignored.

- [ ] **Step 5: Commit**

```bash
git add packaging/write_version_iss.py .github/workflows/release.yml tests/test_packaging_version.py
git commit -m "ci: reject mismatched Wingman release tags"
```

---

### Task 9: Repeatable Windows Native Integration Harness

**Files:**
- Create: `tests/manual/update_harness.py`
- Create: `tests/manual/update_fixture.iss`
- Create: `tests/manual/README.md`
- Modify: `tests/test_packaging_completeness.py`
- Modify: `docs/smoke-checklist.md`

**Interfaces:**
- Consumes production native seams from `wingman.updates`; adds no production override.
- Harness commands: `serve`, `attachment`, `lock-race`, `shell-launch`, `mutex-holder`.
- Fixture mutex: `Local\FlyGDWingmanUpdateHarness` only.

- [ ] **Step 1: Write failing harness-presence and packaging-exclusion tests**

```python
def test_manual_update_harness_is_not_packaged():
    spec = (ROOT / "packaging/uploader.spec").read_text(encoding="utf-8")
    assert "tests/manual" not in spec
    harness = ROOT / "tests/manual/update_harness.py"
    fixture = ROOT / "tests/manual/update_fixture.iss"
    assert harness.is_file() and fixture.is_file()
```

Add a source test that parses the harness arguments and asserts all five command names. It may import the harness on Linux but must not execute Win32 calls at import time.

- [ ] **Step 2: Run the harness source tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py -k "manual_update_harness" -v
```

Expected: failure because the files do not exist.

- [ ] **Step 3: Add the harmless Inno fixture**

Create `tests/manual/update_fixture.iss` with no application payload and no uninstall entry:

```ini
[Setup]
AppId=FlyGD Wingman Update Harness
AppName=FlyGD Wingman Update Harness
AppVersion=1.0.0
DefaultDirName={tmp}\FlyGD-Wingman-Update-Harness
PrivilegesRequired=lowest
Uninstallable=no
AppMutex=Local\FlyGDWingmanUpdateHarness
OutputBaseFilename=Wingman-Update-Harness-Setup

```

The fixture must never reference Wingman's real AppId, app directory, executable, or mutex.

- [ ] **Step 4: Implement explicit opt-in harness commands**

`update_harness.py` must require `--i-understand-this-launches-a-test-exe` for `attachment`, `lock-race`, and `shell-launch`. It creates one temporary staging root and deletes only that root. Commands:

- `serve --mode complete|truncated|checksum-mismatch` — local response fixture passed directly to the injected production download seam; it does not weaken production host validation.
- `attachment PATH SOURCE_URL` — run real `save_attachment`, then print file identity, size, digest, and Zone.Identifier presence.
- `lock-race PATH` — hold production's protected handle, release a barrier for a replacement thread, require sharing violation, and print unchanged identity/digest.
- `shell-launch PATH SOURCE_URL` — call production `launch_verified` on the harmless compiled fixture, print returned handle, then close it.
- `mutex-holder` — call `CreateMutexW` for `Local\FlyGDWingmanUpdateHarness` and wait for Enter, allowing deterministic prompt/no-prompt runs.

No environment variable, URL parameter, or API bridge method may enable these paths in the frozen app.

- [ ] **Step 5: Document exact Windows commands and outcomes**

In `tests/manual/README.md`, include:

```powershell
iscc /O"$PWD\dist" tests\manual\update_fixture.iss
uv run python tests\manual\update_harness.py mutex-holder
# In another terminal: open dist\Wingman-Update-Harness-Setup.exe; expect close/OK prompt.
uv run python tests\manual\update_harness.py shell-launch `
  --i-understand-this-launches-a-test-exe `
  dist\Wingman-Update-Harness-Setup.exe `
  https://github.com/elboaf/FlyGD-Wingman/releases/download/v0.0.0/test.exe
```

Also document the no-mutex run, attachment metadata inspection with PowerShell `Get-Item -Stream *`, checksum/truncation modes, launch-failure using a deleted fixture path, and expected safe-retention output for sharing violations.

- [ ] **Step 6: Add corresponding smoke-check commands and verify source tests**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py tests/test_updates.py -v
uv run --extra dev ruff check tests/manual/update_harness.py tests/test_packaging_completeness.py
uv run --extra dev ruff format --check tests/manual/update_harness.py tests/test_packaging_completeness.py
```

Expected: pass on Linux without invoking Win32; run the documented native commands on Windows before release.

- [ ] **Step 7: Commit**

```bash
git add tests/manual/update_harness.py tests/manual/update_fixture.iss tests/manual/README.md tests/test_packaging_completeness.py docs/smoke-checklist.md
git commit -m "test: add Windows updater integration harness"
```

---

### Task 10: Documentation, Privacy Gate, and Full Verification

**Files:**
- Modify: `README.md:125-145,269-288`
- Modify: `DESIGN.md` under “Routes and sections”
- Modify: `docs/smoke-checklist.md`
- External release action: deploy matching text at `https://wingman.zoolanders.vip/privacy`

**Interfaces:**
- Consumes: completed behavior and commands from Tasks 1–9.
- Produces: accurate network/privacy documentation and an explicit release blocker until the published policy matches.

- [ ] **Step 1: Write failing documentation contract tests**

Add focused lexical assertions to the nearest documentation test (`tests/test_settings_page.py` for UI copy and `tests/test_packaging_completeness.py` for release docs):

```python
def test_readme_discloses_automatic_github_update_checks():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "GitHub release API" in readme
    assert "once each time Wingman starts" in readme
    assert "SHA-256" in readme
    assert "does not prove publisher identity" in readme


def test_design_records_the_global_badge_fetch_exception():
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    assert "update availability" in design.lower()
    assert "after the page is ready" in design.lower()
```

- [ ] **Step 2: Run documentation tests and verify RED**

```bash
uv run --no-sync python -m pytest tests/test_packaging_completeness.py tests/test_settings_page.py -k "update_checks or badge_fetch" -v
```

Expected: failures because README/DESIGN do not yet describe the behavior.

- [ ] **Step 3: Update README and DESIGN with exact behavior**

Replace the “exactly two places, both user initiated” claim with a three-row table. The GitHub row must state: once each process starts, including hidden login starts; installed version and normal connection metadata only; no settings, EVE/account data, filenames, or telemetry. Explain manual **Check again**, explicit download, same-channel SHA-256 limitation, visible unsigned installer, and Windows warning.

Add a narrow DESIGN.md exception after the route/section fetch rule:

> Update availability is application chrome, not General-section content. Wingman therefore starts one background GitHub check after the page is ready so the Settings gear can show availability before General opens. It does not run inside `get_settings()`, block hydration, poll, download, or push before readiness; General reads the cached state and offers an explicit retry.

- [ ] **Step 4: Update and deploy the published privacy statement**

Add this substantive disclosure to the externally hosted policy before shipping:

> Wingman contacts GitHub's release API once when each application process starts, including when Windows starts Wingman hidden at sign-in. The request includes Wingman's version and ordinary network connection metadata. It does not include Wingman settings, EVE or Google account information, filenames, recordings, or telemetry. Further requests occur only when you choose Check again or Download update.

Fetch `https://wingman.zoolanders.vip/privacy` after deployment and verify that all four facts are present: automatic once-per-process request, hidden-start behavior, data sent, and data not sent. Record the deployed policy revision/date in the release verification record. If deployment credentials or the policy source are unavailable, stop and report this as a release blocker; do not mark the feature release-ready.

- [ ] **Step 5: Complete the smoke checklist**

Ensure `docs/smoke-checklist.md` has exact commands/outcomes for:

- dev states at 840x625 and keyboard navigation;
- automatic and manual check behavior;
- complete/truncated/checksum mismatch;
- post-attachment mutation rejection;
- protected replacement race;
- real MOTW/SmartScreen warning;
- shell-launch failure recovery;
- active-upload and retry exclusion;
- tray Quit during each handoff phase;
- both test-Inno mutex outcomes;
- normal in-place Wingman upgrade with settings preserved; and
- published privacy-policy verification.

- [ ] **Step 6: Run focused then full automated verification**

```bash
uv run --no-sync python -m pytest tests/test_updates.py tests/test_api_updates.py tests/test_api_upload.py tests/test_api_quit.py tests/test_startup.py tests/test_bridge_contract.py tests/test_dev_harness.py tests/test_settings_page.py tests/test_page_conventions.py tests/test_packaging_version.py tests/test_packaging_completeness.py -v
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: all automated gates pass; Windows-only tests remain explicitly recorded as pending until run on Windows, never implied by Linux results.

- [ ] **Step 7: Inspect final diff and run changed-code polish**

```bash
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git status --short
```

Run `polish-core --fix` against `origin/main...HEAD`, inspect every edit, then rerun Step 6. Confirm there are no debug endpoints, production origin-policy bypasses, public non-method `Api` attributes, arbitrary URL/path inputs, unfinished user-visible copy, untracked staging fixtures, or unrelated refactors.

- [ ] **Step 8: Commit documentation and verification updates**

```bash
git add README.md DESIGN.md docs/smoke-checklist.md tests/test_packaging_completeness.py tests/test_settings_page.py
git commit -m "docs: describe guided Wingman updates"
```

- [ ] **Step 9: Produce the reviewer handoff**

Use `change-explainer` after fresh verification. Report automated results separately from the Windows harness, real upgrade smoke pass, and external privacy-policy deployment. Do not call the feature release-ready until all three manual gates have evidence.
