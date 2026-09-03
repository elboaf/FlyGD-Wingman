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
import datetime
import hashlib
import json
import os
import re
import stat
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
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
    staging_root.mkdir(parents=True, exist_ok=True)

    if opener is None:
        opener = urllib.request.build_opener(SafeRedirectHandler())

    handle, tmp_name = tempfile.mkstemp(
        dir=str(staging_root), prefix="update-", suffix=_PARTIAL_SUFFIX
    )
    tmp_path = Path(tmp_name)
    try:
        digest = hashlib.sha256()
        total = 0
        request = urllib.request.Request(release.url)
        with os.fdopen(handle, "wb") as stream:
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
                    stream.write(chunk)
                    if on_progress is not None:
                        on_progress(total, release.size)
            stream.flush()
            os.fsync(stream.fileno())

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
        os.replace(tmp_path, ready_path)
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
    atomicio.write_atomic(
        marker,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
    return marker


def remove_handoff_marker(marker: Path) -> None:
    """Remove a handoff sidecar, leaving the installer it describes intact."""
    Path(marker).unlink(missing_ok=True)


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
