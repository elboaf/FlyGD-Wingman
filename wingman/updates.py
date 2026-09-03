"""Release discovery: fetch and strictly validate the latest Wingman release.

This is the sole boundary between GitHub's release metadata and the rest of
the updater. Every later stage (download, staging, attachment security,
install) trusts a `ReleaseInfo` it received from here rather than
re-validating the payload, so validation here is deliberately strict and
fails closed: anything that does not exactly match the expected shape raises
`UpdateFailure` rather than being coerced or ignored.

Importable and fully testable on Linux -- `latest_release` takes an injected
`urlopen`, so nothing here touches the network unless a caller supplies the
real `urllib.request.urlopen`.
"""

from __future__ import annotations

import contextlib
import ctypes
import datetime
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import __version__, atomicio

RELEASES_API = "https://api.github.com/repos/elboaf/FlyGD-Wingman/releases/latest"
MAX_INSTALLER_BYTES = 256 * 1024 * 1024
# The exact host and owner/repo the initial metadata URL must resolve to.
# Task 2 owns the broader redirect-hop/CDN host allowlist for the actual
# download; this is narrower and stricter on purpose -- at the metadata
# stage nothing has been followed yet, so GitHub's own API response must
# already point at this repository's release-download path, or the release
# is not trustworthy enough to hand a URL to any later stage.
_ASSET_URL_HOST = "github.com"
_ASSET_URL_OWNER_REPO = "elboaf/FlyGD-Wingman"
_VERSION_RE = re.compile(r"(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
_DIGEST_RE = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")
_CONTENT_TYPES = {"application/x-msdos-program", "application/octet-stream"}
Version = tuple[int, int, int]


class UpdateFailure(RuntimeError):
    """A stage-tagged, code-tagged updater failure.

    `stage` and `code` let the API layer choose user-facing copy (see
    docs/superpowers/specs/2026-09-02-guided-updates-design.md's "Errors and
    recovery") without parsing exception strings; `detail` is diagnostic only
    and never shown to the user verbatim.
    """

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


def parse_version(value: str, *, tagged: bool = False) -> Version:
    """Parse a strict `MAJOR.MINOR.PATCH` version.

    `tagged` fixes whether a leading "v" is required (a release tag) or
    forbidden (`wingman.__version__`) -- both shapes exist in this codebase
    and neither may be silently accepted for the other, or a tag like
    "v4.8.0" could compare equal to "4.8.0" through string luck rather than
    through an explicit parse.
    """
    match = _VERSION_RE.match(value) if isinstance(value, str) else None
    if not match or value.startswith("v") != tagged:
        raise UpdateFailure(
            "check", "version", f"not a valid version string: {value!r}"
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def release_from_payload(payload: object, current_version: str) -> ReleaseInfo | None:
    """Validate a GitHub "releases/latest" payload into a `ReleaseInfo`.

    Returns `None` for a release that is legitimately not an update (draft,
    prerelease, or not newer than `current_version`). Raises `UpdateFailure`
    for anything that claims to be a newer release but does not meet the
    strict metadata contract -- a missing/duplicate asset, a mismatched
    filename, an out-of-range size, a malformed digest, an unsafe URL, or an
    unexpected content type. Those are surfaced to the user as "the latest
    release cannot be verified", never coerced into "no update available".
    """
    if not isinstance(payload, dict):
        raise UpdateFailure("check", "metadata", "release payload is not an object")

    if payload.get("draft") or payload.get("prerelease"):
        return None

    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateFailure("check", "metadata", "release is missing tag_name")
    version = parse_version(tag, tagged=True)

    if version <= parse_version(current_version):
        return None

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateFailure("check", "metadata", "release is missing an assets list")

    major, minor, patch = version
    expected_name = f"FlyGD-Wingman-Setup-{major}.{minor}.{patch}.exe"
    matches = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name") == expected_name
    ]
    if len(matches) != 1:
        raise UpdateFailure(
            "check",
            "asset",
            f"expected exactly one asset named {expected_name!r}, found {len(matches)}",
        )
    asset = matches[0]

    url = asset.get("browser_download_url")
    _validate_asset_url(url, tag=tag, asset_name=expected_name)

    size = asset.get("size")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or size > MAX_INSTALLER_BYTES
    ):
        raise UpdateFailure("check", "size", f"asset size is out of range: {size!r}")

    digest = asset.get("digest")
    digest_match = _DIGEST_RE.match(digest) if isinstance(digest, str) else None
    if not digest_match:
        raise UpdateFailure(
            "check", "digest", f"asset digest is missing or malformed: {digest!r}"
        )
    sha256 = digest_match.group(1).lower()

    content_type = asset.get("content_type")
    if content_type not in _CONTENT_TYPES:
        raise UpdateFailure(
            "check",
            "content_type",
            f"unexpected asset content type: {content_type!r}",
        )

    return ReleaseInfo(
        version=version,
        tag=tag,
        asset_name=expected_name,
        url=url,
        size=size,
        sha256=sha256,
        content_type=content_type,
    )


def _validate_asset_url(url: object, *, tag: str, asset_name: str) -> None:
    """The asset URL must be exactly the expected GitHub release-download URL.

    This is deliberately narrower than a host allowlist: Task 2 owns
    validating every redirect hop against a broader set of legitimate GitHub
    hosts reached only *after* following an initial redirect. Here, at the
    metadata-validation boundary, nothing has been followed yet -- the
    *initial* URL GitHub's own API reported must match the already-validated
    tag and asset filename exactly (scheme, default port, exact normalized
    host, and exact path, with no query or fragment). Anything less would let
    a release smuggle an arbitrary URL past validation inside a syntactically
    valid HTTPS wrapper, in violation of "never return arbitrary release URLs
    to the UI layer".
    """
    if not isinstance(url, str) or not url:
        raise UpdateFailure("check", "url", f"asset url is missing: {url!r}")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise UpdateFailure("check", "url", f"asset url is not https: {url!r}")
    if "@" in parsed.netloc:
        raise UpdateFailure("check", "url", f"asset url contains userinfo: {url!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UpdateFailure(
            "check", "url", f"asset url has an invalid port: {url!r}"
        ) from exc
    if port is not None and port != 443:
        raise UpdateFailure(
            "check", "url", f"asset url uses a non-default port: {url!r}"
        )
    if parsed.hostname != _ASSET_URL_HOST:
        raise UpdateFailure(
            "check", "url", f"asset url has an unexpected host: {url!r}"
        )
    if parsed.query or parsed.fragment:
        raise UpdateFailure(
            "check", "url", f"asset url has a query or fragment: {url!r}"
        )
    expected = (
        f"https://{_ASSET_URL_HOST}/{_ASSET_URL_OWNER_REPO}"
        f"/releases/download/{tag}/{asset_name}"
    )
    if url != expected:
        raise UpdateFailure(
            "check",
            "url",
            f"asset url does not match the expected release path: {url!r}",
        )


def latest_release(
    current_version: str = __version__,
    *,
    urlopen=urllib.request.urlopen,
    timeout: float = 10.0,
) -> ReleaseInfo | None:
    """The newest release's metadata, or `None` if not a newer stable release.

    Network and JSON failures become `UpdateFailure("check", ...)` rather
    than propagating urllib/json exceptions, so the API layer has one
    failure type to translate into user-facing copy regardless of where in
    the check the failure occurred.
    """
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub rejects a bare urllib user agent outright; a versioned
            # one also gives GitHub something meaningful in its own logs.
            "User-Agent": (
                f"FlyGD-Wingman/{current_version} "
                "(+https://github.com/elboaf/FlyGD-Wingman)"
            ),
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except OSError as exc:
        raise UpdateFailure("check", "network", str(exc)) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateFailure("check", "metadata", str(exc)) from exc

    return release_from_payload(payload, current_version)


# ---- Task 2: safe streaming and staging lifecycle -------------------------
#
# Everything below stays scoped to the download/staging boundary: the initial
# URL was already pinned to this exact repository/tag/asset above, but a real
# GitHub release-download URL redirects through a CDN, so every hop -- not
# only the final response -- must independently satisfy the same narrow
# origin policy. This is deliberately a *different, wider* set of hosts than
# Task 1's `_ASSET_URL_HOST`: the metadata boundary trusts only GitHub's own
# API response for this repository, while this boundary must also trust the
# CDN host that response's asset URL legitimately redirects to.

DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "release-assets.githubusercontent.com",
    }
)
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
UPDATE_STALE_AFTER = datetime.timedelta(days=7)
_PARTIAL_SUFFIX = ".partial"
_READY_SUFFIX = ".ready.exe"
_MARKER_SUFFIX = ".handoff.json"


def validate_download_origin(url: str) -> None:
    """Reject anything but an exact-host HTTPS origin for a download hop.

    Applied to both the initial download URL and every redirect hop
    `SafeRedirectHandler` follows. Never widens to a suffix match: an
    `endswith("githubusercontent.com")` check would also match an
    attacker-registered "evil-githubusercontent.com", so only exact
    membership in `DOWNLOAD_HOSTS` is accepted.
    """
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        port = -1  # deliberately not in (None, 443): falls through to reject
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or (parsed.hostname or "").lower() not in DOWNLOAD_HOSTS
    ):
        raise UpdateFailure("download", "origin", f"unsafe download origin: {url!r}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect hop, not only the initial URL.

    `urllib`'s default redirect handling follows a chain of 30x responses
    blindly. GitHub's release-download URLs redirect through its CDN, so
    checking only the final response would let a compromised or
    misconfigured intermediate hop point anywhere; each new hop is checked
    against the same `validate_download_origin` policy as the initial URL
    before it is followed.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_origin(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_release(
    release: ReleaseInfo,
    staging_root: Path,
    *,
    opener=None,
    on_progress=None,
) -> Path:
    """Stream *release*'s asset to a uniquely named, verified `.ready.exe`.

    The stream is bounded by both the advertised release size and
    `MAX_INSTALLER_BYTES`: a chunk that would push the running total past
    either bound is never written, so a compromised or misbehaving origin
    cannot make Wingman buffer or persist an unbounded amount of data before
    the final digest check would have caught it anyway. Success requires
    the exact advertised byte count *and* a matching SHA-256; either
    mismatch -- like any other failure -- removes the partial file rather
    than leaving debris behind. The destination filename is drawn from
    `tempfile.mkstemp`'s own randomness, so it stays unpredictable and never
    collides between concurrent or repeated downloads.
    """
    validate_download_origin(release.url)
    staging_root = Path(staging_root)
    try:
        staging_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UpdateFailure(
            "download",
            "filesystem",
            f"could not create the staging directory: {exc}",
        ) from exc

    if opener is None:
        opener = urllib.request.build_opener(SafeRedirectHandler())

    try:
        handle, tmp_name = tempfile.mkstemp(
            dir=str(staging_root), prefix="update-", suffix=_PARTIAL_SUFFIX
        )
    except OSError as exc:
        raise UpdateFailure(
            "download", "filesystem", f"could not create a staging file: {exc}"
        ) from exc
    tmp_path = Path(tmp_name)
    try:
        try:
            stream_cm = os.fdopen(handle, "wb")
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.close(handle)
            raise UpdateFailure(
                "download",
                "filesystem",
                f"could not open the staging file: {exc}",
            ) from exc

        digest = hashlib.sha256()
        total = 0
        request = urllib.request.Request(release.url)
        with stream_cm as stream:
            try:
                response_cm = opener.open(request, timeout=30.0)
            except OSError as exc:
                raise UpdateFailure("download", "network", str(exc)) from exc
            with response_cm as response:
                while True:
                    try:
                        chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    except OSError as exc:
                        raise UpdateFailure("download", "network", str(exc)) from exc
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > release.size or total > MAX_INSTALLER_BYTES:
                        raise UpdateFailure(
                            "download",
                            "size",
                            f"download exceeded the expected size: {total} bytes",
                        )
                    digest.update(chunk)
                    try:
                        stream.write(chunk)
                    except OSError as exc:
                        raise UpdateFailure(
                            "download",
                            "filesystem",
                            f"could not write staged bytes: {exc}",
                        ) from exc
                    if on_progress is not None:
                        on_progress(total, release.size)
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except OSError as exc:
                raise UpdateFailure(
                    "download",
                    "filesystem",
                    f"could not flush staged bytes to disk: {exc}",
                ) from exc

        if total != release.size:
            raise UpdateFailure(
                "download",
                "size",
                f"download size mismatch: expected {release.size} bytes, got {total}",
            )
        if digest.hexdigest() != release.sha256:
            raise UpdateFailure(
                "download",
                "checksum",
                "downloaded file does not match the expected checksum",
            )

        ready_path = tmp_path.with_name(
            tmp_path.name[: -len(_PARTIAL_SUFFIX)] + _READY_SUFFIX
        )
        try:
            os.replace(tmp_path, ready_path)
        except OSError as exc:
            raise UpdateFailure(
                "download",
                "filesystem",
                f"could not publish the staged download: {exc}",
            ) from exc
        return ready_path
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def write_handoff_marker(path: Path, release: ReleaseInfo) -> Path:
    """Durably classify *path* as handed-off without renaming it.

    Wingman must never rename an installer after `ShellExecuteExW` has
    started it, so classification is a separate atomic, fsynced sidecar
    beside the installer rather than a rename or an in-memory flag -- this
    is what lets `cleanup_staging` correctly retain a handed-off installer
    even across a process restart, purely from what is on disk.
    """
    path = Path(path)
    if not path.name.endswith(_READY_SUFFIX):
        raise UpdateFailure("cleanup", "unexpected-path", path.name)
    marker = path.with_name(path.name + _MARKER_SUFFIX)
    payload = {
        "file": path.name,
        "sha256": release.sha256,
        "version": ".".join(map(str, release.version)),
    }
    try:
        atomicio.write_atomic(
            marker,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
        )
    except OSError as exc:
        raise UpdateFailure(
            "cleanup", "filesystem", f"could not write the handoff marker: {exc}"
        ) from exc
    return marker


def remove_handoff_marker(marker: Path) -> None:
    """Remove a handoff sidecar, leaving the installer it describes intact."""
    try:
        Path(marker).unlink(missing_ok=True)
    except OSError as exc:
        raise UpdateFailure(
            "cleanup", "filesystem", f"could not remove the handoff marker: {exc}"
        ) from exc


def cleanup_staging(
    staging_root: Path, *, now: datetime.datetime | None = None
) -> None:
    """Remove abandoned updater files at least `UPDATE_STALE_AFTER` old.

    Constrained entirely to *staging_root*: only files matching this
    module's own generated names (`*.partial`, `*.ready.exe`, and a matching
    `*.ready.exe.handoff.json` sidecar) are ever considered, the directory
    is never traversed recursively, symlinks are never followed or removed
    (`lstat`/`follow_symlinks=False` throughout), and a name that resolves
    outside *staging_root* is skipped rather than deleted. A handoff marker
    classifies its matching installer as handed-off purely by filename
    correlation on disk, which is what lets that classification survive a
    process restart without ever renaming the installer. A sharing
    violation or other in-use deletion failure is caught and treated as safe
    retention, never forced.
    """
    staging_root = Path(staging_root)
    try:
        if not staging_root.is_dir():
            return
        resolved_root = staging_root.resolve()
        entries = list(os.scandir(staging_root))
    except OSError:
        return

    if now is None:
        now = datetime.datetime.now(datetime.UTC)
    cutoff = now - UPDATE_STALE_AFTER

    marker_names = set()
    candidates = []
    for entry in entries:
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            continue
        if entry.name.endswith(_READY_SUFFIX + _MARKER_SUFFIX):
            marker_names.add(entry.name[: -len(_MARKER_SUFFIX)])
        elif entry.name.endswith(_PARTIAL_SUFFIX) or entry.name.endswith(_READY_SUFFIX):
            candidates.append((entry.name, st))

    for name, st in candidates:
        mtime = datetime.datetime.fromtimestamp(st.st_mtime, datetime.UTC)
        if mtime > cutoff:
            continue
        path = staging_root / name
        try:
            if path.resolve().parent != resolved_root:
                continue
        except OSError:
            continue
        marker_path = (
            staging_root / (name + _MARKER_SUFFIX) if name in marker_names else None
        )
        try:
            path.unlink()
        except OSError:
            # Sharing violation or similar in-use failure: safe retention.
            continue
        if marker_path is not None:
            with contextlib.suppress(OSError):
                marker_path.unlink(missing_ok=True)


# ---- Task 3: attachment security, protected verification, shell launch ----

CLSID_ATTACHMENT_SERVICES = "{4125DD96-E03A-4103-8F70-E0597D803B9C}"
IID_IATTACHMENT_EXECUTE = "{73DB1241-1E85-4581-8E4F-A81E1D0F8C57}"
ATTACHMENT_CLIENT_GUID = "{F86ACFFD-F7CC-4C62-8FCE-C747D5D94DB7}"

CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2
COINIT_DISABLE_OLE1DDE = 0x4
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NOASYNC = 0x00000100
SEE_MASK_NOZONECHECKS = 0x00800000
SW_SHOWNORMAL = 1
ERROR_CANCELLED = 1223
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_VERIFY_CHUNK_BYTES = 64 * 1024
_STDCALL = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
_get_last_error = getattr(ctypes, "get_last_error", lambda: 0)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTime", _FILETIME),
        ("ftLastAccessTime", _FILETIME),
        ("ftLastWriteTime", _FILETIME),
        ("dwVolumeSerialNumber", ctypes.c_uint32),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("nNumberOfLinks", ctypes.c_uint32),
        ("nFileIndexHigh", ctypes.c_uint32),
        ("nFileIndexLow", ctypes.c_uint32),
    ]


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("fMask", ctypes.c_uint32),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int32),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


@dataclass(frozen=True)
class _Win32Libs:
    ole32: object
    kernel32: object
    shell32: object


@lru_cache(maxsize=1)
def _load_win32_libs() -> _Win32Libs:
    """Bind pointer-width-sensitive native calls only on the Windows path."""
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_int32
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CLSIDFromString.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(_GUID),
    ]
    ole32.CLSIDFromString.restype = ctypes.c_int32
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_int32

    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.GetFileInformationByHandle.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
    ]
    kernel32.GetFileInformationByHandle.restype = ctypes.c_int32
    kernel32.ReadFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    kernel32.ReadFile.restype = ctypes.c_int32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int32

    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = ctypes.c_int32
    return _Win32Libs(ole32=ole32, kernel32=kernel32, shell32=shell32)


def _hresult_failed(result: int) -> bool:
    return ctypes.c_int32(result).value < 0


def _hex_hresult(result: int) -> str:
    return f"0x{ctypes.c_uint32(result).value:08x}"


def _require_hresult(result: int, stage: str, code: str) -> None:
    if _hresult_failed(result):
        raise UpdateFailure(stage, code, _hex_hresult(result))


def _guid_from_string(value: str, ole32) -> _GUID:
    guid = _GUID()
    result = ole32.CLSIDFromString(value, ctypes.byref(guid))
    _require_hresult(result, "verify", "attachment")
    return guid


def _com_method(interface, index, restype, *argtypes):
    vtable = ctypes.cast(
        interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    prototype = _STDCALL(restype, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])


def save_attachment(path: Path, source_url: str) -> None:
    """Submit a staged installer to Windows Attachment Services.

    Attachment Services may replace, delete, truncate, or quarantine the file,
    so callers must treat success only as permission to perform a new protected
    verification pass. This function owns both its COM reference and this
    thread's successful COM initialization count on every branch.
    """
    libs = _load_win32_libs()
    ole32 = libs.ole32
    result = ole32.CoInitializeEx(
        None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE
    )
    _require_hresult(result, "verify", "attachment")
    interface = ctypes.c_void_p()
    try:
        clsid = _guid_from_string(CLSID_ATTACHMENT_SERVICES, ole32)
        iid = _guid_from_string(IID_IATTACHMENT_EXECUTE, ole32)
        client_guid = _guid_from_string(ATTACHMENT_CLIENT_GUID, ole32)
        result = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid),
            ctypes.byref(interface),
        )
        _require_hresult(result, "verify", "attachment")
        if not interface.value:
            raise UpdateFailure("verify", "attachment", "null COM interface")

        # IUnknown = 0..2; IAttachmentExecute: SetClientGuid = 4,
        # SetLocalPath = 5, SetSource = 7, Save = 11.
        set_client_guid = _com_method(
            interface, 4, ctypes.c_int32, ctypes.POINTER(_GUID)
        )
        set_local_path = _com_method(interface, 5, ctypes.c_int32, ctypes.c_wchar_p)
        set_source = _com_method(interface, 7, ctypes.c_int32, ctypes.c_wchar_p)
        save = _com_method(interface, 11, ctypes.c_int32)
        _require_hresult(
            set_client_guid(interface, ctypes.byref(client_guid)),
            "verify",
            "attachment",
        )
        _require_hresult(set_local_path(interface, str(path)), "verify", "attachment")
        _require_hresult(set_source(interface, source_url), "verify", "attachment")
        _require_hresult(save(interface), "verify", "attachment")
    finally:
        if interface.value:
            release = _com_method(interface, 2, ctypes.c_uint32)
            release(interface)
        ole32.CoUninitialize()


class _PortableLockedFile:
    """Held-descriptor test fallback; frozen Windows always uses CreateFileW."""

    def __init__(self, path: Path):
        # This object is itself the context manager that owns the stream.
        self._stream = Path(path).open("rb")  # noqa: SIM115

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._stream.close()
        return False

    def identity_and_size(self):
        info = os.fstat(self._stream.fileno())
        return ((info.st_dev, info.st_ino), info.st_size)

    def sha256(self):
        digest = hashlib.sha256()
        for chunk in iter(lambda: self._stream.read(_VERIFY_CHUNK_BYTES), b""):
            digest.update(chunk)
        return digest.hexdigest()


class _WindowsLockedFile:
    """A read handle that denies every writer and delete/rename attempt."""

    def __init__(self, path: Path, kernel32):
        self._kernel32 = kernel32
        self._handle = kernel32.CreateFileW(
            str(path),
            _GENERIC_READ,
            _FILE_SHARE_READ,
            None,
            _OPEN_EXISTING,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if self._handle == _INVALID_HANDLE_VALUE:
            error = _get_last_error()
            self._handle = None
            raise OSError(error, f"CreateFileW failed with error {error}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        handle = self._handle
        self._handle = None
        if handle is not None and not self._kernel32.CloseHandle(handle):
            error = _get_last_error()
            detail = f"CloseHandle failed with error {error}"
            if exc[1] is not None:
                exc[1].add_note(detail)
            else:
                raise UpdateFailure("verify", "file", detail)
        return False

    def identity_and_size(self):
        info = _BY_HANDLE_FILE_INFORMATION()
        if not self._kernel32.GetFileInformationByHandle(
            self._handle, ctypes.byref(info)
        ):
            error = _get_last_error()
            raise OSError(
                error, f"GetFileInformationByHandle failed with error {error}"
            )
        identity = (
            info.dwVolumeSerialNumber,
            (info.nFileIndexHigh << 32) | info.nFileIndexLow,
        )
        size = (info.nFileSizeHigh << 32) | info.nFileSizeLow
        return identity, size

    def sha256(self):
        digest = hashlib.sha256()
        buffer = ctypes.create_string_buffer(_VERIFY_CHUNK_BYTES)
        while True:
            read = ctypes.c_uint32()
            if not self._kernel32.ReadFile(
                self._handle,
                buffer,
                len(buffer),
                ctypes.byref(read),
                None,
            ):
                error = _get_last_error()
                raise OSError(error, f"ReadFile failed with error {error}")
            if not read.value:
                return digest.hexdigest()
            digest.update(buffer.raw[: read.value])


def _open_locked(path: Path):
    if sys.platform == "win32":
        return _WindowsLockedFile(path, _load_win32_libs().kernel32)
    return _PortableLockedFile(path)


def _locked_manager(path: Path, locked_open):
    try:
        opener = _open_locked if locked_open is None else locked_open
        return opener(path)
    except OSError as exc:
        raise UpdateFailure("verify", "file", str(exc)) from exc


def _locked_value(operation):
    try:
        return operation()
    except OSError as exc:
        raise UpdateFailure("verify", "file", str(exc)) from exc


def _verify_locked(release: ReleaseInfo, locked):
    identity, size = _locked_value(locked.identity_and_size)
    if size != release.size:
        raise UpdateFailure(
            "verify",
            "size",
            f"installer size mismatch: expected {release.size} bytes, got {size}",
        )
    digest = _locked_value(locked.sha256)
    if digest != release.sha256:
        raise UpdateFailure(
            "verify", "checksum", "installer does not match the expected checksum"
        )
    return identity, size


def _require_same_locked_file(locked, expected_identity, expected_size) -> None:
    identity, size = _locked_value(locked.identity_and_size)
    if identity != expected_identity:
        raise UpdateFailure("verify", "identity", "installer identity changed")
    if size != expected_size:
        raise UpdateFailure("verify", "size", "installer size changed")


def verify_after_attachment(
    release: ReleaseInfo,
    path: Path,
    *,
    attachment=save_attachment,
    locked_open=None,
) -> None:
    """Run attachment processing, then verify through one protected handle."""
    path = Path(path)
    attachment(path, release.url)
    with _locked_manager(path, locked_open) as locked:
        identity, size = _verify_locked(release, locked)
        _require_same_locked_file(locked, identity, size)


def launch_verified(
    release: ReleaseInfo,
    path: Path,
    *,
    before_launch=None,
    attachment=save_attachment,
    locked_open=None,
    shell_execute=None,
) -> int:
    """Verify and shell-launch *path* without opening a replacement window."""
    path = Path(path)
    attachment(path, release.url)
    if shell_execute is None:
        shell_execute = _shell_execute
    with _locked_manager(path, locked_open) as locked:
        identity, size = _verify_locked(release, locked)
        if before_launch is not None:
            before_launch()
        _require_same_locked_file(locked, identity, size)
        return shell_execute(path)


def _shell_execute(path: Path, *, libs=None) -> int:
    """Launch with zone checks and transfer the returned process handle."""
    if libs is None:
        libs = _load_win32_libs()
    result = libs.ole32.CoInitializeEx(
        None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE
    )
    _require_hresult(result, "launch", "com")
    try:
        info = _SHELLEXECUTEINFO()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOASYNC | SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "open"
        info.lpFile = str(path)
        info.lpParameters = None
        info.nShow = SW_SHOWNORMAL
        if not libs.shell32.ShellExecuteExW(ctypes.byref(info)):
            error = _get_last_error()
            code = "cancelled" if error == ERROR_CANCELLED else "shell"
            raise UpdateFailure("launch", code, f"ShellExecuteExW error {error}")
        if not info.hProcess:
            raise UpdateFailure(
                "launch", "shell", "ShellExecuteExW returned no process"
            )
        return int(info.hProcess)
    finally:
        libs.ole32.CoUninitialize()


def close_process_handle(handle: int) -> None:
    """Release the process handle returned by `launch_verified` exactly once."""
    if not _load_win32_libs().kernel32.CloseHandle(handle):
        error = _get_last_error()
        raise UpdateFailure("launch", "close-handle", f"CloseHandle error {error}")
