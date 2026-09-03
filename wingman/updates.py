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

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import __version__

RELEASES_API = "https://api.github.com/repos/elboaf/FlyGD-Wingman/releases/latest"
MAX_INSTALLER_BYTES = 256 * 1024 * 1024
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
    _validate_asset_url(url)

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


def _validate_asset_url(url: object) -> None:
    """Basic URL sanity for the release metadata itself.

    This is deliberately not the full origin/host allowlist -- that lives
    with the download stage (Task 2), which also validates every redirect
    hop. Here we only reject shapes that could never be a legitimate GitHub
    release-asset URL: non-HTTPS, embedded userinfo, and a non-default port.
    """
    if not isinstance(url, str) or not url:
        raise UpdateFailure("check", "url", f"asset url is missing: {url!r}")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
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
