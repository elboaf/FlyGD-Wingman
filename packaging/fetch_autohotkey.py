# packaging/fetch_autohotkey.py
"""Download and verify the AutoHotkey v1.1 interpreter at build time.

Mirrors fetch_ffmpeg.py. v1.1 specifically: the vendored engine is v1
syntax, and v2 is a different, incompatible language.
"""
import hashlib
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Update URL and SHA256 together, never separately.
AHK_URL = ("https://github.com/AutoHotkey/AutoHotkey/releases/download/"
           "v1.1.37.02/AutoHotkey_1.1.37.02.zip")
AHK_SHA256 = "6f3663f7cdd25063c8c8728f5d9b07813ced8780522fd1f124ba539e2854215f"
OUT_DIR = Path(__file__).parent / "bin"
# license.txt (GPLv2) is bundled alongside the interpreter, not just fetched
# for reference -- the notices file this feeds (THIRD-PARTY-NOTICES.md)
# names it as the licence text installed beside the application.
WANTED = ("AutoHotkeyU64.exe", "license.txt")
# Sidecar records which pin the binary in OUT_DIR was extracted from, so a
# later bump of AHK_SHA256 doesn't silently keep shipping the old binary.
VERSION_FILE = OUT_DIR / ".autohotkey-version"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (
        all((OUT_DIR / name).exists() for name in WANTED)
        and VERSION_FILE.exists()
        and VERSION_FILE.read_text().strip() == AHK_SHA256
    ):
        print(f"AutoHotkey already present and matches pin {AHK_SHA256}; skipping")
        return 0

    print(f"Downloading {AHK_URL}")
    try:
        with urllib.request.urlopen(AHK_URL) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: download failed: {exc}")
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    if AHK_SHA256 == "REPLACE_WITH_MEASURED_DIGEST":
        print(f"ERROR: pin the checksum first. Downloaded archive is sha256={digest}")
        return 1
    if digest != AHK_SHA256:
        print(f"ERROR: checksum mismatch\n  expected {AHK_SHA256}\n  got      {digest}")
        return 1

    extracted = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.namelist():
                # Basename only: a malicious member path such as
                # "../../evil/AutoHotkeyU64.exe" cannot escape OUT_DIR
                # because Path(member).name discards every directory
                # component before the join.
                name = Path(member).name
                if name in WANTED:
                    (OUT_DIR / name).write_bytes(archive.read(member))
                    print(f"  extracted {name}")
                    extracted += 1
    except zipfile.BadZipFile as exc:
        print(f"ERROR: downloaded archive is not a valid zip file: {exc}")
        return 1

    if extracted != len(WANTED):
        print(f"ERROR: expected {len(WANTED)} binaries, extracted {extracted}")
        return 1
    VERSION_FILE.write_text(AHK_SHA256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
