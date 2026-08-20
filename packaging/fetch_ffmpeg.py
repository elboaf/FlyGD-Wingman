# packaging/fetch_ffmpeg.py
"""Download and verify ffmpeg binaries at build time.

Binaries are not committed to git: they are large, and a pinned URL plus a
checksum gives reproducibility without the repository bloat.
"""
import hashlib
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Pinned release. Update URL and SHA256 together, never separately.
FFMPEG_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/"
    "7.1/ffmpeg-7.1-essentials_build.zip"
)
FFMPEG_SHA256 = "fa7d4d7e795db0e2503f49f105f46ed5852386f0cfdd819899be3b65ebde24fc"
OUT_DIR = Path(__file__).parent / "bin"
WANTED = ("ffmpeg.exe", "ffprobe.exe")
# Sidecar records which pin the binaries in OUT_DIR were extracted from, so a
# later bump of FFMPEG_SHA256 doesn't silently keep shipping the old binaries.
VERSION_FILE = OUT_DIR / ".ffmpeg-version"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (
        all((OUT_DIR / name).exists() for name in WANTED)
        and VERSION_FILE.exists()
        and VERSION_FILE.read_text().strip() == FFMPEG_SHA256
    ):
        print(f"ffmpeg binaries already present and match pin {FFMPEG_SHA256}; skipping download")
        return 0

    print(f"Downloading {FFMPEG_URL}")
    try:
        with urllib.request.urlopen(FFMPEG_URL) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: download failed: {exc}")
        return 1

    digest = hashlib.sha256(payload).hexdigest()
    if FFMPEG_SHA256 == "REPLACE_WITH_ACTUAL_SHA256_BEFORE_FIRST_RELEASE":
        print(f"ERROR: pin the checksum first. Downloaded archive is sha256={digest}")
        return 1
    if digest != FFMPEG_SHA256:
        print(f"ERROR: checksum mismatch\n  expected {FFMPEG_SHA256}\n  got      {digest}")
        return 1

    extracted = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.namelist():
                # Only the basename is used as the output filename, so a
                # malicious member path (e.g. "../../evil/ffmpeg.exe") cannot
                # escape OUT_DIR: Path(member).name discards all directory
                # components before it is joined with OUT_DIR.
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
    VERSION_FILE.write_text(FFMPEG_SHA256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
