# packaging/fetch_fightrecorder.py
"""Fetch the FightRecorder OBS plugin DLL for the installer.

Same contract as fetch_ffmpeg/fetch_autohotkey: stdlib only, writes into
packaging/bin/, returns 1 with an ERROR line on failure so the CI step
goes red.

Pin versus latest: ffmpeg and AutoHotkey pin a URL plus a sha256 because
those artifacts never move. FightRecorder releases move -- this feature
exists to track them -- so the fetcher resolves the LATEST release
through the GitHub API and verifies the download against the digest the
API itself publishes on the asset (a `sha256:...` field). That makes the
release metadata the pin: a download that does not match what GitHub
says it shipped never reaches packaging/bin, and a tampered release
would have to also tamper with its own digest record.

Skip-if-present: a .fightrecorder-version sidecar records the tag and
digest actually fetched. Re-running with the same release on disk is a
no-op, like the other fetchers' sidecars.

Wingman the APP does not bundle this DLL -- it is packed into the
INSTALLER (installer.iss dontcopy entry) and placed into the user's OBS
installation at install time or from the Settings card.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent / "bin"
OUT = OUT_DIR / "obs-fightrecorder.dll"
VERSION = OUT_DIR / ".fightrecorder-version"
RELEASES_API = "https://api.github.com/repos/elboaf/obs-fightrecorder/releases/latest"
DLL_NAME = "obs-fightrecorder.dll"

# GitHub's API rejects requests without a user agent.
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "FlyGD-Wingman-build",
}


def fail(message: str) -> int:
    print(f"ERROR: {message}")
    return 1


def api_latest() -> dict:
    request = urllib.request.Request(RELEASES_API, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        dest.write_bytes(response.read())


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        release = api_latest()
    except OSError as exc:
        return fail(f"could not reach {RELEASES_API}: {exc}")

    tag = release.get("tag_name", "")
    assets = release.get("assets", [])
    asset = next((a for a in assets if a.get("name") == DLL_NAME), None)
    if asset is None:
        return fail(f"{tag} has no {DLL_NAME} asset")

    digest = (asset.get("digest") or "").removeprefix("sha256:")
    if not digest:
        return fail(
            f"{tag}'s {DLL_NAME} asset carries no sha256 digest; refusing "
            "to bundle an unverifiable binary"
        )

    if OUT.is_file() and VERSION.is_file():
        recorded = VERSION.read_text(encoding="utf-8").strip()
        if recorded == f"{tag}:{digest}":
            print(f"FightRecorder {tag} already fetched ({digest[:12]}...)")
            return 0

    url = asset.get("browser_download_url", "")
    try:
        download(url, OUT)
    except OSError as exc:
        return fail(f"could not download {url}: {exc}")

    actual = hashlib.sha256(OUT.read_bytes()).hexdigest()
    if actual != digest:
        OUT.unlink(missing_ok=True)
        return fail(
            f"downloaded {DLL_NAME} hashes to {actual}, but {tag} says "
            f"{digest} -- not bundling it"
        )

    VERSION.write_text(f"{tag}:{digest}", encoding="utf-8")
    print(f"Fetched FightRecorder {tag} ({digest[:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
